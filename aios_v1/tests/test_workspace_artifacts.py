"""H5 fase 1: tool `workspace_create_file` — artefak file privat per conversation.

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
Render PDF dimock agar tidak bergantung pada binary wkhtmltopdf.
"""

import io
import json
import os
import uuid
from unittest.mock import patch

import frappe

from aios_v1.lib.tool_registry import execute_tool, tool_context
from aios_v1.lib.workspace_artifacts import workspace_create_file
from aios_v1.setup import ensure_builtin_plugins

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _blank_pdf() -> bytes:
    """PDF minimal valid (lolos validasi File Frappe) via pypdf."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _make_user(email, first_name):
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    return frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "enabled": 1,
            "send_welcome_email": 0,
            "user_type": "Website User",
            "aios_status": "Active",
            "roles": [{"role": "AIOS Client"}],
        }
    ).insert(ignore_permissions=True)


class TestWorkspaceArtifacts(IntegrationTestCase):
    USER = "_test.artifact.builder@example.com"

    def setUp(self):
        super().setUp()
        self.original_commit = frappe.db.commit
        frappe.db.commit = lambda *args, **kwargs: None
        _make_user(self.USER, "_Test Artifact Builder")
        ensure_builtin_plugins()
        self.conversation = frappe.get_doc(
            {"doctype": "AIOS Conversation", "user": self.USER, "branch": "finance", "title": "_Test Artifacts"}
        ).insert(ignore_permissions=True)
        self._physical_files = []

    def tearDown(self):
        frappe.db.commit = self.original_commit
        frappe.set_user("Administrator")
        frappe.db.rollback()
        for path in self._physical_files:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def _create(self, file_name, file_format, rows=None, content=None, conversation_id=None, user=None):
        frappe.set_user(user or self.USER)
        requested_name = file_name
        result = json.loads(
            execute_tool(
                "workspace_create_file",
                json.dumps({"file_name": file_name, "format": file_format, "rows": rows, "content": content}),
                context={
                    "user": user or self.USER,
                    "allowed_company": "_Test Company",
                    "branch": "finance",
                    "worker_key": "manager",
                    "conversation_id": str(conversation_id or self.conversation.name),
                },
            )
        )
        if result.get("status") == "created":
            self._track_physical(requested_name, result["file_name"])
        return result

    def _track_physical(self, *names):
        # save_file Frappe dapat menulis dua nama fisik: nama input dan nama+hash doctype.
        directory = frappe.get_site_path("private", "files")
        for name in names:
            if name:
                self._physical_files.append(os.path.join(directory, name))

    def test_builder_creates_all_formats_as_private_files_bound_to_conversation(self):
        marker = uuid.uuid4().hex[:8]
        cases = (
            ("csv", [["name", "amount"], [f"INV-{marker}", 125]], None),
            ("xlsx", [["name", "amount"], [f"INV-{marker}", 125]], None),
            ("md", None, f"# Laporan {marker}\nIsi ringkas."),
        )
        for file_format, rows, content in cases:
            with self.subTest(format=file_format):
                file_name = f"laporan {marker}.{file_format}"
                result = self._create(file_name, file_format, rows=rows, content=content)
                self.assertEqual(result.get("status"), "created")
                self.assertEqual(result["artifact"]["type"], "FILE")
                file_id = self._find_file_id(result["file_name"])
                bound = frappe.db.get_value(
                    "File",
                    file_id,
                    ["is_private", "owner", "attached_to_doctype", "attached_to_name"],
                    as_dict=True,
                )
                self.assertEqual(int(bound.is_private), 1)
                self.assertEqual(bound.owner, self.USER)
                self.assertEqual(bound.attached_to_doctype, "AIOS Conversation")
                self.assertEqual(str(bound.attached_to_name), str(self.conversation.name))

        pdf_bytes = _blank_pdf()
        with patch("frappe.utils.pdf.get_pdf", return_value=pdf_bytes) as render:
            pdf_name = f"laporan {marker}.pdf"
            result = self._create(pdf_name, "pdf", content=f"Laporan {marker}")
        self.assertEqual(result.get("status"), "created")
        render.assert_called_once()
        physical = os.path.join(
            frappe.get_site_path("private", "files"),
            os.path.basename(frappe.db.get_value("File", self._find_file_id(result["file_name"]), "file_url")),
        )
        with open(physical, "rb") as stream:
            pdf_content = stream.read()
        self.assertTrue(pdf_content.startswith(b"%PDF"))
        self.assertEqual(pdf_content, pdf_bytes)

    def _find_file_id(self, file_name):
        names = frappe.get_all("File", filters={"file_name": file_name}, pluck="name", order_by="creation desc", limit=1)
        self.assertTrue(names, f"File {file_name} tidak ditemukan")
        return names[0]

    def test_artifact_payload_has_no_file_id_local_path_or_content(self):
        result = self._create("aman.csv", "csv", rows=[["name"], [uuid.uuid4().hex[:6]]])
        self.assertEqual(result.get("status"), "created")
        artifact = result["artifact"]
        self.assertEqual(set(artifact.keys()), {"type", "file_name", "file_url", "format", "size", "conversation_id"})
        self.assertTrue(str(artifact["file_url"]).startswith("/private/files/"))
        serialized = json.dumps(result)
        self.assertNotIn("file_id", serialized)
        file_id = self._find_file_id(result["file_name"])
        self.assertNotIn(file_id, serialized)

    def test_builder_rejects_traversal_extension_and_format_mismatch(self):
        for file_name, file_format, expected in (
            ("../../evil.csv", "csv", "INVALID_FILENAME"),
            ("laporan.txt", "csv", "FORMAT_UNSUPPORTED"),
            ("laporan.csv", "xlsx", "FORMAT_MISMATCH"),
            ("laporan.csv", "exe", "FORMAT_UNSUPPORTED"),
        ):
            with self.subTest(name=file_name, format=file_format):
                result = self._create(file_name, file_format, rows=[["h"]])
                self.assertEqual(result.get("code"), expected)
                self.assertEqual(result.get("success"), False)

    def test_builder_requires_rows_and_content_per_format(self):
        self.assertEqual(self._create("tanpa rows.csv", "csv")["code"], "ROWS_REQUIRED")
        self.assertEqual(self._create("tanpa rows.xlsx", "xlsx")["code"], "ROWS_REQUIRED")
        self.assertEqual(self._create("kosong.md", "md", content="   ")["code"], "CONTENT_REQUIRED")
        self.assertEqual(
            self._create("salah tipe.csv", "csv", content="hanya teks")["code"], "ROWS_REQUIRED"
        )

    def test_builder_rejects_missing_conversation_or_user_context(self):
        frappe.set_user(self.USER)
        with patch("frappe.log_error"):
            with tool_context({"conversation_id": str(self.conversation.name)}):
                result = workspace_create_file("tanpa user.csv", "csv", rows=[["h"]])
            self.assertEqual(result["code"], "USER_REQUIRED")
            with tool_context({"user_id": self.USER}):
                result = workspace_create_file("tanpa conv.csv", "csv", rows=[["h"]])
            self.assertEqual(result["code"], "CONVERSATION_REQUIRED")

    def test_formula_cells_are_prefixed_for_csv_and_xlsx(self):
        marker = uuid.uuid4().hex[:6]
        result = self._create(
            f"formula {marker}.csv", "csv", rows=[["header"], ["=1+1"], ["+SUM(A1)"], ["-2+3"], ["@cmd"]]
        )
        self.assertEqual(result.get("status"), "created")
        file_id = self._find_file_id(result["file_name"])
        content = frappe.get_doc("File", file_id).get_content()
        if isinstance(content, str):
            content = content.encode("utf-8")
        text = content.decode("utf-8")
        self.assertIn("'=1+1", text)
        self.assertIn("'+SUM(A1)", text)
        self.assertIn("'-2+3", text)
        self.assertIn("'@cmd", text)
        self.assertNotIn("\n=1+1", text)

        from openpyxl import load_workbook

        result = self._create(f"formula {marker}.xlsx", "xlsx", rows=[["header"], ["=1+1"]])
        self.assertEqual(result.get("status"), "created")
        xlsx_id = self._find_file_id(result["file_name"])
        workbook = load_workbook(io.BytesIO(frappe.get_doc("File", xlsx_id).get_content()))
        self.assertEqual(workbook["Data"]["A2"].value, "'=1+1")

    def test_pdf_content_is_html_escaped(self):
        captured = {}

        def fake_get_pdf(html, *args, **kwargs):
            captured["html"] = html
            return _blank_pdf()

        with patch("frappe.utils.pdf.get_pdf", side_effect=fake_get_pdf):
            result = self._create(
                f"angka {uuid.uuid4().hex[:6]}.pdf", "pdf", content="<script>alert(1)</script> & <b>tebal</b> 'quote'"
            )
        self.assertEqual(result.get("status"), "created")
        html = captured["html"]
        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&amp;", html)
        self.assertIn("<pre>", html)

    def test_oversize_rows_cells_and_payload_are_rejected(self):
        self.assertEqual(
            self._create("banyak baris.csv", "csv", rows=[["h"]] * 5001)["code"], "ROW_LIMIT_EXCEEDED"
        )
        self.assertEqual(
            self._create("sel panjang.csv", "csv", rows=[["h"], ["x" * 32768]])["code"], "CONTENT_TOO_LARGE"
        )
        self.assertEqual(
            self._create("besar.md", "md", content="a" * (10 * 1024 * 1024 + 1))["code"], "FILE_TOO_LARGE"
        )

    def test_pdf_render_failure_is_safe(self):
        with (
            patch("frappe.utils.pdf.get_pdf", side_effect=OSError("wkhtmltopdf missing")),
            patch("aios_v1.lib.workspace_artifacts.log_exception"),
        ):
            result = self._create("gagal.pdf", "pdf", content="tidak jadi")
        self.assertEqual(result.get("code"), "PDF_RENDER_FAILED")
        self.assertNotIn("wkhtmltopdf", json.dumps(result))


if __name__ == "__main__":
    import unittest

    unittest.main()
