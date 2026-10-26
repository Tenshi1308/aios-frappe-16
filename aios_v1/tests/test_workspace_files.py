"""Integration tests for the read-only conversation file explorer endpoint."""

import json
import os
import uuid
from unittest.mock import patch

import frappe

from aios_v1.lib import workspace
from aios_v1.lib.workspace import list_my_files, save_private_file

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


class TestWorkspaceFiles(IntegrationTestCase):
    USER_A = "_test.workspace.files.alpha@example.com"
    USER_B = "_test.workspace.files.beta@example.com"

    def setUp(self):
        super().setUp()
        self.original_commit = frappe.db.commit
        frappe.db.commit = lambda *args, **kwargs: None
        _make_user(self.USER_A, "_Test Workspace Files Alpha")
        _make_user(self.USER_B, "_Test Workspace Files Beta")
        frappe.set_user("Administrator")
        self.conv_a = frappe.get_doc(
            {"doctype": "AIOS Conversation", "user": self.USER_A, "branch": "_test_branch", "title": "Alpha"}
        ).insert(ignore_permissions=True)
        self.conv_a2 = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": self.USER_A,
                "branch": "_test_branch",
                "title": "Alpha second",
            }
        ).insert(ignore_permissions=True)
        self.conv_b = frappe.get_doc(
            {"doctype": "AIOS Conversation", "user": self.USER_B, "branch": "_test_branch", "title": "Beta"}
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

    def _save(self, conversation, user, marker):
        frappe.set_user(user)
        file_name = f"{marker}-{uuid.uuid4().hex[:8]}.csv"
        content_marker = f"PRIVATE-BODY-{uuid.uuid4().hex}"
        content = f"name\n{content_marker}\n".encode("utf-8")
        saved = save_private_file(file_name, content, conversation.name, user)
        directory = frappe.get_site_path("private", "files")
        self._physical_files.extend(
            [os.path.join(directory, file_name), os.path.join(directory, os.path.basename(saved["file_url"]))]
        )
        return saved, content_marker

    def test_list_my_files_endpoint_is_exposed(self):
        self.assertTrue(
            callable(getattr(workspace, "list_my_files", None)),
            "workspace.list_my_files must expose the read-only file listing endpoint",
        )

    def test_user_a_sees_only_private_files_from_owned_conversations(self):
        own, _ = self._save(self.conv_a, self.USER_A, "alpha-owned")
        second, _ = self._save(self.conv_a2, self.USER_A, "alpha-second")
        self._save(self.conv_b, self.USER_B, "beta-private")

        frappe.set_user(self.USER_A)
        files = list_my_files()

        self.assertEqual({row["file_name"] for row in files}, {own["file_name"], second["file_name"]})
        self.assertEqual({row["conversation_id"] for row in files}, {str(self.conv_a.name), str(self.conv_a2.name)})
        self.assertNotIn(self.USER_B, json.dumps(files, default=str))

    def test_conversation_filter_is_owner_scoped(self):
        first, _ = self._save(self.conv_a, self.USER_A, "alpha-filter-first")
        second, _ = self._save(self.conv_a2, self.USER_A, "alpha-filter-second")
        self._save(self.conv_b, self.USER_B, "beta-filter")

        frappe.set_user(self.USER_A)
        filtered = list_my_files(str(self.conv_a2.name))
        self.assertEqual([row["file_name"] for row in filtered], [second["file_name"]])
        self.assertEqual(list_my_files(str(self.conv_b.name)), [])
        self.assertNotEqual(first["file_name"], second["file_name"])

    def test_payload_has_no_file_id_filesystem_path_or_content(self):
        saved, content_marker = self._save(self.conv_a, self.USER_A, "private-content-marker")
        frappe.set_user(self.USER_A)

        files = list_my_files(str(self.conv_a.name))

        self.assertEqual(len(files), 1)
        self.assertEqual(
            set(files[0]),
            {
                "conversation_id",
                "conversation_title",
                "branch",
                "file_name",
                "file_url",
                "file_size",
                "format",
                "creation",
            },
        )
        self.assertTrue(files[0]["file_url"].startswith("/private/files/"))
        serialized = json.dumps(files, default=str)
        self.assertNotIn("file_id", serialized)
        self.assertNotIn(saved["file_id"], serialized)
        self.assertNotIn(content_marker, serialized)
        self.assertNotIn(frappe.get_site_path("private", "files"), serialized)

    def test_conversation_without_files_returns_empty_list(self):
        frappe.set_user(self.USER_A)
        self.assertEqual(list_my_files(str(self.conv_a.name)), [])

    def test_file_query_is_explicitly_scoped_and_excludes_folders(self):
        frappe.set_user(self.USER_A)
        frappe_get_all = frappe.get_all
        with patch("aios_v1.lib.workspace.frappe.get_all", wraps=frappe_get_all) as get_all:
            self.assertEqual(list_my_files(str(self.conv_a.name)), [])

        file_calls = [call for call in get_all.call_args_list if call.args and call.args[0] == "File"]
        self.assertEqual(len(file_calls), 1)
        file_call = file_calls[0]
        self.assertEqual(file_call.kwargs["filters"]["owner"], self.USER_A)
        self.assertEqual(file_call.kwargs["filters"]["is_private"], 1)
        self.assertEqual(file_call.kwargs["filters"]["is_folder"], 0)
        self.assertEqual(file_call.kwargs["filters"]["attached_to_doctype"], "AIOS Conversation")
        self.assertEqual(file_call.kwargs["filters"]["attached_to_name"], ["in", [str(self.conv_a.name)]])
        self.assertTrue(file_call.kwargs["ignore_permissions"])
        self.assertEqual(file_call.kwargs["limit"], 500)

    def test_guest_is_rejected(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.ValidationError):
            list_my_files()


if __name__ == "__main__":
    import unittest

    unittest.main()
