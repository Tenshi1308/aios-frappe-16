"""In-memory format parsing and private File access contract tests."""

import builtins
import io
from unittest.mock import Mock, patch

import frappe
from openpyxl import Workbook

from aios_v1.lib.document_intelligence import document_extract, extract_document_content
from aios_v1.lib.tool_registry import tool_context

try:
	from frappe.tests import IntegrationTestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _text_pdf_fixture():
	stream = b"BT /F1 12 Tf 72 720 Td (Invoice TEST) Tj ET"
	objects = [
		b"<< /Type /Catalog /Pages 2 0 R >>",
		b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
		b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
		b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
		b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
	]
	buffer = bytearray(b"%PDF-1.4\n")
	offsets = [0]
	for index, body in enumerate(objects, start=1):
		offsets.append(len(buffer))
		buffer.extend(f"{index} 0 obj\n".encode())
		buffer.extend(body)
		buffer.extend(b"\nendobj\n")
	xref_offset = len(buffer)
	buffer.extend(f"xref\n0 {len(offsets)}\n".encode())
	buffer.extend(b"0000000000 65535 f \n")
	for offset in offsets[1:]:
		buffer.extend(f"{offset:010d} 00000 n \n".encode())
	buffer.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode())
	return bytes(buffer)


def _xlsx_fixture():
	workbook = Workbook()
	worksheet = workbook.active
	worksheet.title = "Orders"
	worksheet.append(["invoice", "amount"])
	worksheet.append(["INV-1", 125])
	output = io.BytesIO()
	workbook.save(output)
	return output.getvalue()


class TestDocumentIntelligence(IntegrationTestCase):
	USER = "_test.document.intelligence@example.com"
	CONVERSATION = "_Test Conversation 77"

	def setUp(self):
		super().setUp()
		self.original_commit = frappe.db.commit
		frappe.db.commit = lambda *args, **kwargs: None
		frappe.set_user(self.USER)

	def tearDown(self):
		frappe.db.commit = self.original_commit
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _file(self, **overrides):
		values = {
			"name": "_Test File",
			"file_name": "_Test document.csv",
			"file_url": "/private/files/_Test document.csv",
			"file_size": 16,
			"is_private": 1,
			"owner": self.USER,
			"attached_to_doctype": "AIOS Conversation",
			"attached_to_name": self.CONVERSATION,
		}
		values.update(overrides)
		doc = frappe._dict(values)
		doc.get_content = Mock(return_value=b"name,amount\nINV-1,10\n")
		return doc

	def _extract_file(self, file_doc, **kwargs):
		with (
			patch("aios_v1.lib.document_intelligence.frappe.get_doc", return_value=file_doc),
			patch("frappe.log_error"),
			tool_context({"conversation_id": self.CONVERSATION}),
		):
			return document_extract(file_doc.name, **kwargs)

	def test_pure_csv_extraction_handles_duplicate_and_empty_headers(self):
		result = extract_document_content(
			"_Test CSV",
			"_Test data.csv",
			"csv",
			b"name,name,\nAlice,Bob,ok\n",
		)
		self.assertEqual(result["columns"], ["name", "name_2", "column_3"])
		self.assertEqual(result["rows"], [{"name": "Alice", "name_2": "Bob", "column_3": "ok"}])
		self.assertFalse(result["truncated"])

	def test_pure_csv_decodes_invalid_utf8_with_replacement(self):
		result = extract_document_content("_Test CSV", "_Test data.csv", "csv", b"name\nA\xffB\n")
		self.assertEqual(result["rows"][0]["name"], "A\ufffdB")

	def test_pure_xlsx_extraction_uses_headers_and_sheet_name(self):
		result = extract_document_content(
			"_Test XLSX", "_Test data.xlsx", "xlsx", _xlsx_fixture(), sheet_name="Orders"
		)
		self.assertEqual(result["sheet"], "Orders")
		self.assertEqual(result["columns"], ["invoice", "amount"])
		self.assertEqual(result["rows"], [{"invoice": "INV-1", "amount": 125}])

	def test_pure_xlsx_uses_active_sheet_and_rejects_missing_sheet(self):
		content = _xlsx_fixture()
		self.assertEqual(extract_document_content("f", "x.xlsx", "xlsx", content)["sheet"], "Orders")
		with self.assertRaises(ValueError) as raised:
			extract_document_content("f", "x.xlsx", "xlsx", content, sheet_name="_Test Missing")
		self.assertEqual(raised.exception.code, "SHEET_NOT_FOUND")

	def test_pure_pdf_returns_page_text_and_page_count(self):
		result = extract_document_content("_Test PDF", "_Test invoice.pdf", "pdf", _text_pdf_fixture())
		self.assertEqual(len(result["pages"]), 1)
		self.assertEqual(result["pages"][0]["page"], 1)
		self.assertIn("Invoice TEST", result["content"])
		self.assertFalse(result["truncated"])

	def test_private_file_owned_by_session_user_extracts_without_disk_io(self):
		file_doc = self._file()
		with (
			patch("aios_v1.lib.document_intelligence.frappe.get_doc", return_value=file_doc),
			patch("frappe.log_error"),
			patch.object(builtins, "open", side_effect=AssertionError("unexpected disk access")),
			tool_context({"conversation_id": self.CONVERSATION}),
		):
			result = document_extract(file_doc.name)
		self.assertEqual(result["format"], "csv")
		self.assertEqual(result["rows"], [{"name": "INV-1", "amount": "10"}])
		file_doc.get_content.assert_called_once_with(encodings=[])

	def test_file_owner_and_privacy_are_enforced_before_read(self):
		other_owner = self._file(owner="_test.someone.else@example.com")
		result = self._extract_file(other_owner)
		self.assertEqual(result.get("code"), "FILE_FORBIDDEN")
		other_owner.get_content.assert_not_called()

		public_file = self._file(is_private=0)
		result = self._extract_file(public_file)
		self.assertEqual(result.get("code"), "FILE_NOT_PRIVATE")
		public_file.get_content.assert_not_called()

	def test_file_bound_to_other_conversation_is_rejected(self):
		file_doc = self._file(attached_to_name="_Test Conversation 78")
		result = self._extract_file(file_doc)
		self.assertEqual(result.get("code"), "FILE_FORBIDDEN")
		file_doc.get_content.assert_not_called()

		unbound = self._file(attached_to_doctype=None, attached_to_name=None)
		result = self._extract_file(unbound)
		self.assertEqual(result.get("code"), "FILE_FORBIDDEN")
		unbound.get_content.assert_not_called()

	def test_message_bound_file_is_allowed_only_in_parent_conversation(self):
		file_doc = self._file(attached_to_doctype="AIOS Message", attached_to_name="_Test Message 77")
		with (
			patch("aios_v1.lib.document_intelligence.frappe.get_doc", return_value=file_doc),
			patch("aios_v1.lib.document_intelligence.frappe.db.get_value", return_value=self.CONVERSATION),
			patch("frappe.log_error"),
			tool_context({"conversation_id": self.CONVERSATION}),
		):
			result = document_extract(file_doc.name)
		self.assertEqual(result["format"], "csv")

		file_doc = self._file(attached_to_doctype="AIOS Message", attached_to_name="_Test Message 78")
		with (
			patch("aios_v1.lib.document_intelligence.frappe.get_doc", return_value=file_doc),
			patch("aios_v1.lib.document_intelligence.frappe.db.get_value", return_value="_Test Conversation 78"),
			patch("frappe.log_error"),
			tool_context({"conversation_id": self.CONVERSATION}),
		):
			result = document_extract(file_doc.name)
		self.assertEqual(result.get("code"), "FILE_FORBIDDEN")
		file_doc.get_content.assert_not_called()

	def test_extract_without_conversation_context_is_rejected(self):
		file_doc = self._file()
		with (
			patch("aios_v1.lib.document_intelligence.frappe.get_doc", return_value=file_doc),
			patch("frappe.log_error"),
			tool_context({}),
		):
			result = document_extract(file_doc.name)
		self.assertEqual(result.get("code"), "CONVERSATION_REQUIRED")
		file_doc.get_content.assert_not_called()

	def test_administrator_may_read_private_file_with_different_owner(self):
		frappe.set_user("Administrator")
		file_doc = self._file(owner="_test.someone.else@example.com")
		result = self._extract_file(file_doc)
		self.assertEqual(result["rows"][0]["name"], "INV-1")

	def test_file_format_size_and_max_rows_guards(self):
		file_doc = self._file(file_name="_Test data.exe")
		self.assertEqual(self._extract_file(file_doc)["code"], "FORMAT_UNSUPPORTED")

		file_doc = self._file()
		self.assertEqual(self._extract_file(file_doc, format="xlsx")["code"], "FORMAT_MISMATCH")

		large_file = self._file(file_size=10 * 1024 * 1024 + 1)
		self.assertEqual(self._extract_file(large_file)["code"], "FILE_TOO_LARGE")
		large_file.get_content.assert_not_called()

		csv_bytes = b"name\nfirst\nsecond\n"
		file_doc = self._file(file_size=len(csv_bytes))
		file_doc.get_content = Mock(return_value=csv_bytes)
		result = self._extract_file(file_doc, max_rows=1)
		self.assertEqual(len(result["rows"]), 1)
		self.assertTrue(result["truncated"])


if __name__ == "__main__":
	import unittest
	unittest.main()
