"""H5 fase 1: isolasi workspace — Private File terikat conversation milik user.

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import os
import uuid
from unittest.mock import patch

import frappe

from aios_v1.lib.document_intelligence import document_extract
from aios_v1.lib.tool_registry import tool_context
from aios_v1.lib.workspace import (
    ATTACHMENT_EXTENSIONS,
    WorkspaceError,
    build_attachment_context,
    sanitize_filename,
    save_private_file,
    validate_attachments,
)
from aios_v1.setup import ensure_builtin_plugins

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


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


class TestWorkspaceIsolation(IntegrationTestCase):
    USER_A = "_test.workspace.alpha@example.com"
    USER_B = "_test.workspace.beta@example.com"

    def setUp(self):
        super().setUp()
        self.original_commit = frappe.db.commit
        frappe.db.commit = lambda *args, **kwargs: None
        _make_user(self.USER_A, "_Test Workspace Alpha")
        _make_user(self.USER_B, "_Test Workspace Beta")
        ensure_builtin_plugins()
        self.conv_a = frappe.get_doc(
            {"doctype": "AIOS Conversation", "user": self.USER_A, "branch": "finance", "title": "_Test WS A"}
        ).insert(ignore_permissions=True)
        self.conv_b = frappe.get_doc(
            {"doctype": "AIOS Conversation", "user": self.USER_B, "branch": "finance", "title": "_Test WS B"}
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

    def _save(self, file_name, content, conversation, user):
        frappe.set_user(user)
        unique_name = f"{file_name.rsplit('.', 1)[0]} {uuid.uuid4().hex[:6]}.{file_name.rsplit('.', 1)[1]}"
        saved = save_private_file(unique_name, content, conversation.name, user)
        # save_file Frappe dapat menulis dua nama fisik: nama input dan nama+hash doctype.
        self._track([unique_name, os.path.basename(saved["file_url"])], "private", "files")
        return saved

    def _track(self, names, *path_parts):
        directory = frappe.get_site_path(*path_parts)
        for name in names:
            self._physical_files.append(os.path.join(directory, name))

    def _extract(self, file_id, conversation_id, user):
        frappe.set_user(user)
        with (
            patch("frappe.log_error"),
            tool_context({"conversation_id": str(conversation_id)}),
        ):
            return document_extract(file_id)

    def test_private_file_is_bound_to_conversation_and_owner(self):
        saved = self._save("laporan a.csv", b"name,amount\nINV-1,10\n", self.conv_a, self.USER_A)
        file_doc = frappe.db.get_value(
            "File",
            saved["file_id"],
            ["is_private", "owner", "attached_to_doctype", "attached_to_name"],
            as_dict=True,
        )
        self.assertEqual(int(file_doc.is_private), 1)
        self.assertEqual(file_doc.owner, self.USER_A)
        self.assertEqual(file_doc.attached_to_doctype, "AIOS Conversation")
        self.assertEqual(str(file_doc.attached_to_name), str(self.conv_a.name))

    def test_user_b_cannot_read_file_of_user_a(self):
        saved = self._save("rahasia a.csv", b"name\nA\n", self.conv_a, self.USER_A)
        file_doc = frappe.get_doc("File", saved["file_id"])
        frappe.set_user(self.USER_B)
        self.assertFalse(frappe.has_permission("File", "read", doc=file_doc))
        result = self._extract(saved["file_id"], self.conv_b.name, self.USER_B)
        self.assertEqual(result.get("code"), "FILE_FORBIDDEN")

    def test_traversal_filenames_are_rejected_without_creating_file(self):
        frappe.set_user(self.USER_A)
        before = frappe.db.count("File")
        for evil in ("../../evil.csv", "..\\evil.csv", "/tmp/evil.csv", "a/b.csv", "evil%2f.csv"):
            with self.subTest(name=evil):
                with self.assertRaises(WorkspaceError) as raised:
                    sanitize_filename(evil, ATTACHMENT_EXTENSIONS)
                self.assertEqual(raised.exception.code, "INVALID_FILENAME")
                with self.assertRaises(WorkspaceError):
                    save_private_file(evil, b"data\n", self.conv_a.name, self.USER_A)
        self.assertEqual(frappe.db.count("File"), before)

    def test_public_file_is_rejected(self):
        from frappe.utils.file_manager import save_file as frappe_save_file

        marker = uuid.uuid4().hex[:6]
        frappe.set_user(self.USER_A)
        public_name = f"_Test public {marker}.csv"
        public = frappe_save_file(
            public_name, b"name\nP\n", "AIOS Conversation",
            str(self.conv_a.name), is_private=0,
        )
        self._track([public_name, os.path.basename(public.file_url)], "public", "files")
        result = self._extract(public.name, self.conv_a.name, self.USER_A)
        self.assertEqual(result.get("code"), "FILE_NOT_PRIVATE")
        frappe.set_user(self.USER_A)
        with self.assertRaises(WorkspaceError) as raised:
            validate_attachments([public.name], self.conv_a.name, self.USER_A)
        self.assertEqual(raised.exception.code, "FILE_NOT_PRIVATE")

    def test_file_from_conversation_b_is_forbidden_for_conversation_a(self):
        saved_b = self._save("milik b.csv", b"name\nB\n", self.conv_b, self.USER_B)
        frappe.set_user(self.USER_A)
        with self.assertRaises(WorkspaceError) as raised:
            validate_attachments([saved_b["file_id"]], self.conv_a.name, self.USER_A)
        self.assertEqual(raised.exception.code, "FILE_FORBIDDEN")
        result = self._extract(saved_b["file_id"], self.conv_a.name, self.USER_A)
        self.assertEqual(result.get("code"), "FILE_FORBIDDEN")

    def test_document_extract_success_and_cross_conversation_rejection(self):
        saved = self._save(
            "data a.csv",
            f"name,amount\nINV-1,{uuid.uuid4().hex[:6]}\n".encode(),
            self.conv_a,
            self.USER_A,
        )
        result = self._extract(saved["file_id"], self.conv_a.name, self.USER_A)
        self.assertEqual(result["format"], "csv")
        self.assertEqual(result["rows"][0]["name"], "INV-1")

        cross = self._extract(saved["file_id"], self.conv_b.name, self.USER_A)
        self.assertEqual(cross.get("code"), "FILE_FORBIDDEN")

    def test_document_extract_without_conversation_context_is_rejected(self):
        saved = self._save("tanpa ctx.csv", b"name\nX\n", self.conv_a, self.USER_A)
        frappe.set_user(self.USER_A)
        with patch("frappe.log_error"):
            result = document_extract(saved["file_id"])
        self.assertEqual(result.get("code"), "CONVERSATION_REQUIRED")

    def test_validate_attachments_caps_at_five_and_dedupes(self):
        file_ids = [
            self._save(f"lampiran {i}.csv", f"col\n{uuid.uuid4().hex}\n".encode(), self.conv_a, self.USER_A)["file_id"]
            for i in range(3)
        ]
        metadata = validate_attachments(file_ids + file_ids[:2], self.conv_a.name, self.USER_A)
        self.assertEqual([item["file_id"] for item in metadata], file_ids)

        six = file_ids + [
            self._save(f"extra {i}.csv", f"col\n{uuid.uuid4().hex}\n".encode(), self.conv_a, self.USER_A)["file_id"]
            for i in range(3)
        ]
        with self.assertRaises(WorkspaceError) as raised:
            validate_attachments(six, self.conv_a.name, self.USER_A)
        self.assertEqual(raised.exception.code, "TOO_MANY_ATTACHMENTS")

    def test_attachment_metadata_has_no_content_or_url(self):
        saved = self._save("meta a.csv", b"name\nA\n", self.conv_a, self.USER_A)
        metadata = validate_attachments([saved["file_id"]], self.conv_a.name, self.USER_A)
        self.assertEqual(len(metadata), 1)
        self.assertEqual(set(metadata[0].keys()), {"file_id", "file_name", "file_size", "format"})
        context_text = build_attachment_context(metadata)
        self.assertIn(saved["file_name"], context_text)
        self.assertIn("file_id=", context_text)
        self.assertNotIn("/private/files", context_text)
        self.assertNotIn("/files/", context_text)
        self.assertNotIn("name\nA", context_text)

    def test_session_user_mismatch_fails_closed(self):
        frappe.set_user(self.USER_B)
        with self.assertRaises(WorkspaceError) as raised:
            save_private_file("curi.csv", b"x\n", self.conv_a.name, self.USER_A)
        self.assertEqual(raised.exception.code, "WORKSPACE_CONTEXT_MISMATCH")
        with self.assertRaises(WorkspaceError) as raised:
            validate_attachments(["whatever"], self.conv_a.name, self.USER_A)
        self.assertEqual(raised.exception.code, "WORKSPACE_CONTEXT_MISMATCH")

    def test_attachment_format_md_is_rejected_for_chat(self):
        with self.assertRaises(WorkspaceError) as raised:
            sanitize_filename("catatan.md", ATTACHMENT_EXTENSIONS)
        self.assertEqual(raised.exception.code, "FORMAT_UNSUPPORTED")


if __name__ == "__main__":
    import unittest

    unittest.main()
