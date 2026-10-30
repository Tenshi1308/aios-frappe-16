"""Tests for specific validation feedback to LLM and smart document lookup."""

import json
from unittest.mock import Mock, patch

import frappe

from aios_v1.lib.document_intelligence import document_extract
from aios_v1.lib.draft_manager import validate_data_fields
from aios_v1.lib.tool_registry import ai_tool, execute_tool, tool_context
from aios_v1.lib.workspace import build_attachment_context

try:
	from frappe.tests import IntegrationTestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


@ai_tool(
	name="_test_validation_probe",
	description="Tool probe for testing validation exceptions.",
	branch=["finance", "sales"],
	roles=[],
	parameters={"action": {"type": "string"}},
)
def _test_validation_probe(action: str):
	if action == "validation_error":
		frappe.throw("Field 'customer' tidak dikenal untuk DocType 'Quotation'.")
	elif action == "value_error":
		raise ValueError("Nilai tidak valid.")
	elif action == "unexpected_crash":
		raise RuntimeError("Koneksi internal terputus.")
	return {"status": "ok"}


class TestValidationFeedbackAndSmartLookup(IntegrationTestCase):
	USER = "_test.feedback.user@example.com"
	CONVERSATION = "_Test Conversation 99"

	def setUp(self):
		super().setUp()
		frappe.set_user(self.USER)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_validate_data_fields_rejects_unknown_field_with_doctype_name_and_schema_hint(self):
		"""Unknown field error must identify the field and advise using erpnext_doctype_schema."""
		meta = frappe.get_meta("Quotation")
		data = {"customer": "Toko Berkah Elektronik"}
		with self.assertRaises(frappe.ValidationError) as exc_info:
			validate_data_fields(meta, data)
		message = str(exc_info.exception)
		self.assertIn("Field 'customer' tidak dikenal untuk DocType 'Quotation'", message)
		self.assertIn("erpnext_doctype_schema", message)

	def test_execute_tool_returns_validation_failed_with_clean_message_on_validation_error(self):
		"""frappe.ValidationError in execute_tool returns clean VALIDATION_FAILED, not generic TOOL_FAILED."""
		context = {
			"user": self.USER,
			"allowed_company": "_Test Company",
			"branch": "finance",
			"worker_key": "manager",
			"conversation_id": self.CONVERSATION,
		}
		raw_result = execute_tool(
			"_test_validation_probe",
			json.dumps({"action": "validation_error"}),
			context=context,
		)
		result = json.loads(raw_result)
		self.assertFalse(result.get("success", True))
		self.assertEqual(result.get("code"), "VALIDATION_FAILED")
		self.assertIn("Field 'customer' tidak dikenal", result.get("error", ""))
		self.assertIn("Quotation", result.get("error", ""))

	def test_execute_tool_returns_validation_failed_on_value_error(self):
		"""ValueError in execute_tool returns clean VALIDATION_FAILED."""
		context = {
			"user": self.USER,
			"allowed_company": "_Test Company",
			"branch": "finance",
			"worker_key": "manager",
			"conversation_id": self.CONVERSATION,
		}
		raw_result = execute_tool(
			"_test_validation_probe",
			json.dumps({"action": "value_error"}),
			context=context,
		)
		result = json.loads(raw_result)
		self.assertEqual(result.get("code"), "VALIDATION_FAILED")
		self.assertIn("Nilai tidak valid", result.get("error", ""))

	def test_execute_tool_masks_unexpected_crash_as_tool_failed(self):
		"""Unexpected crashes (RuntimeError, DB crash) remain masked as TOOL_FAILED for security."""
		context = {
			"user": self.USER,
			"allowed_company": "_Test Company",
			"branch": "finance",
			"worker_key": "manager",
			"conversation_id": self.CONVERSATION,
		}
		raw_result = execute_tool(
			"_test_validation_probe",
			json.dumps({"action": "unexpected_crash"}),
			context=context,
		)
		result = json.loads(raw_result)
		self.assertEqual(result.get("code"), "TOOL_FAILED")
		self.assertEqual(result.get("error"), "Tool gagal dijalankan.")

	def test_document_extract_smart_lookup_with_filename(self):
		"""If LLM passes file_name instead of file_id, smart lookup resolves the File in conversation."""
		mock_file = frappe._dict({
			"name": "291138620b",
			"file_name": "TES DATA ADMIN_KARINDO GROUP.csv",
			"file_url": "/private/files/TES DATA ADMIN_KARINDO GROUP.csv",
			"file_size": 32,
			"is_private": 1,
			"owner": self.USER,
			"attached_to_doctype": "AIOS Conversation",
			"attached_to_name": self.CONVERSATION,
		})
		mock_file.get_content = Mock(return_value=b"name,amount\nINV-100,500\n")

		def fake_get_doc(doctype, name, **kwargs):
			if name == "291138620b":
				return mock_file
			raise frappe.DoesNotExistError(f"File {name} not found")

		with (
			patch("aios_v1.lib.document_intelligence.frappe.get_doc", side_effect=fake_get_doc),
			patch(
				"aios_v1.lib.document_intelligence.frappe.get_all",
				return_value=[{
					"name": "291138620b",
					"attached_to_doctype": "AIOS Conversation",
					"attached_to_name": self.CONVERSATION,
					"owner": self.USER,
				}],
			),
			patch("frappe.log_error"),
			tool_context({"conversation_id": self.CONVERSATION}),
		):
			result = document_extract("TES DATA ADMIN_KARINDO GROUP.csv")

		self.assertEqual(result.get("format"), "csv")
		self.assertEqual(result.get("rows"), [{"name": "INV-100", "amount": "500"}])

	def test_document_extract_returns_file_not_found_when_file_does_not_exist(self):
		"""Nonexistent file in document_extract returns FILE_NOT_FOUND, not misleading FILE_FORBIDDEN."""
		with (
			patch(
				"aios_v1.lib.document_intelligence.frappe.get_doc",
				side_effect=frappe.DoesNotExistError("File missing not found"),
			),
			patch("aios_v1.lib.document_intelligence.frappe.get_all", return_value=[]),
			patch("frappe.log_error"),
			tool_context({"conversation_id": self.CONVERSATION}),
		):
			result = document_extract("nonexistent_file.xlsx")

		self.assertEqual(result.get("code"), "FILE_NOT_FOUND")
		self.assertIn("tidak ditemukan", result.get("error", ""))

	def test_build_attachment_context_directive(self):
		"""Attachment context shows file_name -> file_id and instructs model to use file_id."""
		attachments = [{
			"file_name": "rekap.xlsx",
			"format": "xlsx",
			"file_size": 1024,
			"file_id": "abc123hash",
		}]
		context = build_attachment_context(attachments)
		self.assertIn("Nama file: rekap.xlsx", context)
		self.assertIn("file_id: abc123hash", context)
		self.assertIn("document_extract(file_id=...)", context)
