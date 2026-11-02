"""H5 fase 1: endpoint upload lampiran + validasi `file_ids` di `/stream`.

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
Request HTTP palsu memakai pola `EnvironBuilder` + `handle_api_request`.
"""

import json
import os
import uuid
from io import BytesIO
from unittest.mock import MagicMock, patch

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from aios_v1.api.dispatcher import CustomAPIResponse, handle_api_request
from aios_v1.lib.workspace import save_private_file

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


def _call(path, method="GET", body=None, form=None, files=None):
    if body is not None:
        data = json.dumps(body)
        content_type = "application/json"
    else:
        data = dict(form or {})
        data.update(files or {})
        content_type = None
    builder = EnvironBuilder(
        path=path,
        method=method,
        data=data,
        content_type=content_type,
    )
    frappe.local.request = Request(builder.get_environ())
    try:
        handle_api_request()
    except CustomAPIResponse as exc:
        return exc._custom_response
    finally:
        frappe.local.request = None
    raise AssertionError(f"{path} tidak mengembalikan response")


class TestChatAttachments(IntegrationTestCase):
    ALPHA = "_test.chat.attach.alpha@example.com"
    BETA = "_test.chat.attach.beta@example.com"

    def setUp(self):
        super().setUp()
        self.original_commit = frappe.db.commit
        frappe.db.commit = lambda *args, **kwargs: None
        _make_user(self.ALPHA, "_Test Attach Alpha")
        _make_user(self.BETA, "_Test Attach Beta")
        self.alpha_conv = frappe.get_doc(
            {"doctype": "AIOS Conversation", "user": self.ALPHA, "branch": "sales", "title": "_Test Attach A"}
        ).insert(ignore_permissions=True)
        self.beta_conv = frappe.get_doc(
            {"doctype": "AIOS Conversation", "user": self.BETA, "branch": "sales", "title": "_Test Attach B"}
        ).insert(ignore_permissions=True)
        self._physical_files = []

    def tearDown(self):
        frappe.db.commit = self.original_commit
        frappe.local.request = None
        frappe.set_user("Administrator")
        frappe.db.rollback()
        for path in self._physical_files:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def _upload(self, file_name, data, conversation_id=None, branch=None, user=None):
        frappe.set_user(user or self.ALPHA)
        form = {}
        if conversation_id is not None:
            form["conversationId"] = str(conversation_id)
        if branch is not None:
            form["branch"] = branch
        return _call(
            "/api/chat/upload",
            method="POST",
            form=form,
            files={"file": (BytesIO(data), file_name)},
        )

    def _save_workspace_file(self, conversation, user, name, content):
        frappe.set_user(user)
        saved = save_private_file(name, content, conversation.name, user)
        self._track([name, os.path.basename(saved["file_url"])], "private", "files")
        return saved

    def _track(self, names, *path_parts):
        directory = frappe.get_site_path(*path_parts)
        for name in names:
            if name:
                self._physical_files.append(os.path.join(directory, name))

    def test_upload_without_session_returns_401(self):
        res = self._upload("laporan.csv", b"a,b\n1,2\n", conversation_id=self.alpha_conv.name, user="Guest")
        self.assertEqual(res.status_code, 401)

    def test_upload_to_other_users_conversation_returns_404(self):
        res = self._upload("curi.csv", b"a\n1\n", conversation_id=self.beta_conv.name, user=self.ALPHA)
        self.assertEqual(res.status_code, 404)
        body = json.loads(res.get_data(as_text=True))
        self.assertEqual(body.get("code"), "CONVERSATION_NOT_FOUND")

    def test_upload_traversal_name_returns_400_without_file(self):
        before = frappe.db.count("File")
        res = self._upload("../../evil.csv", b"a\n1\n", conversation_id=self.alpha_conv.name)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(json.loads(res.get_data(as_text=True)).get("code"), "INVALID_FILENAME")
        self.assertEqual(frappe.db.count("File"), before)

    def test_upload_success_creates_private_file_and_returns_metadata(self):
        marker = uuid.uuid4().hex[:6]
        upload_name = f"laporan {marker}.csv"
        res = self._upload(upload_name, b"name,amount\nINV-1,10\n", conversation_id=self.alpha_conv.name)
        self.assertEqual(res.status_code, 200)
        body = json.loads(res.get_data(as_text=True))
        self.assertEqual(str(body["conversationId"]), str(self.alpha_conv.name))
        attachment = body["attachment"]
        self.assertTrue(
            attachment["file_name"].startswith(upload_name.rsplit(".", 1)[0]),
            f"file_name {attachment['file_name']} tidak cocok dengan {upload_name}",
        )
        self.assertEqual(attachment["format"], "csv")
        self.assertEqual(attachment["file_size"], len(b"name,amount\nINV-1,10\n"))
        self.assertTrue(attachment["id"])
        bound = frappe.db.get_value(
            "File",
            attachment["id"],
            ["is_private", "owner", "attached_to_doctype", "attached_to_name"],
            as_dict=True,
        )
        self.assertEqual(int(bound.is_private), 1)
        self.assertEqual(bound.owner, self.ALPHA)
        self.assertEqual(bound.attached_to_doctype, "AIOS Conversation")
        self.assertEqual(str(bound.attached_to_name), str(self.alpha_conv.name))
        self._track(
            [upload_name, os.path.basename(frappe.db.get_value("File", attachment["id"], "file_url"))],
            "private",
            "files",
        )

    def test_uploading_identical_bytes_twice_creates_distinct_file_paths(self):
        marker = uuid.uuid4().hex[:8]
        content = f"name\nidentik-{marker}\n".encode()
        first_name = f"unggah-identik-satu-{marker}.csv"
        second_name = f"unggah-identik-dua-{marker}.csv"
        first_response = self._upload(first_name, content, conversation_id=self.alpha_conv.name)
        second_response = self._upload(second_name, content, conversation_id=self.alpha_conv.name)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        first = json.loads(first_response.get_data(as_text=True))["attachment"]
        second = json.loads(second_response.get_data(as_text=True))["attachment"]
        self._track(
            [os.path.basename(first["file_url"]), os.path.basename(second["file_url"])],
            "private",
            "files",
        )

        self.assertNotEqual(first["id"], second["id"])
        self.assertNotEqual(first["file_url"], second["file_url"])
        first_content = frappe.get_doc("File", first["id"]).get_content()
        second_content = frappe.get_doc("File", second["id"]).get_content()
        self.assertEqual(first_content.encode("utf-8") if isinstance(first_content, str) else first_content, content)
        self.assertEqual(second_content.encode("utf-8") if isinstance(second_content, str) else second_content, content)

    def test_upload_without_conversation_creates_one_from_branch(self):
        marker = uuid.uuid4().hex[:6]
        upload_name = f"awal {marker}.csv"
        res = self._upload(upload_name, b"a\n1\n", branch="sales")
        self.assertEqual(res.status_code, 200)
        body = json.loads(res.get_data(as_text=True))
        conversation_id = body["conversationId"]
        owner = frappe.db.get_value("AIOS Conversation", str(conversation_id), "user")
        self.assertEqual(owner, self.ALPHA)
        self.assertTrue(body["attachment"]["id"])
        self._track(
            [upload_name, os.path.basename(frappe.db.get_value("File", body["attachment"]["id"], "file_url"))],
            "private",
            "files",
        )

    def test_stream_with_file_ids_without_conversation_returns_400_before_manager(self):
        frappe.set_user(self.ALPHA)
        with patch("aios_v1.api.dispatcher.get_manager") as get_manager:
            get_manager.side_effect = AssertionError("get_manager tidak boleh dipanggil")
            res = _call(
                "/api/chat/sales/stream",
                method="POST",
                body={"message": "halo", "file_ids": ["beberapa-file"]},
            )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(json.loads(res.get_data(as_text=True)).get("code"), "CONVERSATION_REQUIRED")
        get_manager.assert_not_called()

    def test_stream_with_foreign_file_returns_403_before_manager(self):
        foreign = self._save_workspace_file(
            self.beta_conv, self.BETA, f"milik beta {uuid.uuid4().hex[:6]}.csv", b"x\n1\n"
        )
        frappe.set_user(self.ALPHA)
        with patch("aios_v1.api.dispatcher.get_manager") as get_manager:
            get_manager.side_effect = AssertionError("get_manager tidak boleh dipanggil")
            res = _call(
                "/api/chat/sales/stream",
                method="POST",
                body={
                    "message": "halo",
                    "conversationId": str(self.alpha_conv.name),
                    "file_ids": [foreign["file_id"]],
                },
            )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(json.loads(res.get_data(as_text=True)).get("code"), "FILE_FORBIDDEN")
        get_manager.assert_not_called()

    def test_stream_valid_passes_attachment_metadata_to_manager(self):
        marker = uuid.uuid4().hex[:6]
        uploaded = self._save_workspace_file(
            self.alpha_conv, self.ALPHA, f"valid {marker}.csv", f"col\n{marker}\n".encode()
        )
        frappe.set_user(self.ALPHA)
        manager = MagicMock()
        manager.handle_stream.return_value = iter(['data: {"type": "delta", "text": "ok"}\n\n'])
        with patch("aios_v1.api.dispatcher.get_manager", return_value=manager):
            res = _call(
                "/api/chat/sales/stream",
                method="POST",
                body={
                    "message": "tolong analisis",
                    "conversationId": str(self.alpha_conv.name),
                    "file_ids": [uploaded["file_id"]],
                },
            )
        self.assertEqual(res.status_code, 200)
        manager.handle_stream.assert_called_once()
        kwargs = manager.handle_stream.call_args.kwargs
        self.assertEqual(kwargs["attachments"], [
            {
                "file_id": uploaded["file_id"],
                "file_name": uploaded["file_name"],
                "file_size": uploaded["file_size"],
                "format": "csv",
            }
        ])

    def test_handle_stream_injects_attachment_metadata_as_system_prompt(self):
        from aios_v1.managers.base_manager import BaseManager

        manager = BaseManager({"key": "finance", "name": "Finance"})
        doc = MagicMock()
        snapshots = []

        def chat(messages, usage=None, tools=None, tool_calls=None):
            snapshots.append(json.dumps(messages, ensure_ascii=False))
            usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            return iter(["selesai"])

        with (
            patch.object(manager, "ensure_conversation", return_value=7),
            patch.object(manager, "get_worker_def", return_value=None),
            patch.object(manager, "build_system_prompt", return_value="_Test prompt"),
            patch("aios_v1.managers.base_manager.get_tools_schema_for_worker", return_value=[]),
            patch("aios_v1.managers.base_manager.chat_stream", side_effect=chat),
            patch("aios_v1.managers.base_manager.frappe.new_doc", return_value=doc),
            patch("aios_v1.managers.base_manager.frappe.get_list", return_value=[]),
            patch("aios_v1.managers.base_manager.record_token_usage_batch"),
        ):
            list(
                manager.handle_stream(
                    "analisis lampiran",
                    conversation_id=7,
                    user="_test@example.com",
                    attachments=[
                        {"file_id": "FILE-XX", "file_name": "laporan.csv", "file_size": 12, "format": "csv"}
                    ],
                )
            )
        prompt_payload = snapshots[0]
        self.assertIn("LAMPIRAN PENGGUNA PADA PERCAKAPAN INI", prompt_payload)
        self.assertIn("laporan.csv", prompt_payload)
        self.assertIn("-> file_id: FILE-XX", prompt_payload)
        self.assertIn("document_extract", prompt_payload)
        self.assertIn("bukan instruksi", prompt_payload)
        self.assertNotIn("/private/files", prompt_payload)
        messages = json.loads(snapshots[0])
        system_messages = [m["content"] for m in messages if m["role"] == "system"]
        self.assertTrue(any("LAMPIRAN PENGGUNA" in content for content in system_messages))

    def test_handle_stream_binds_uploaded_file_to_user_message_without_changing_file_data(self):
        from aios_v1.managers.base_manager import BaseManager

        saved = self._save_workspace_file(
            self.alpha_conv,
            self.ALPHA,
            f"inline {uuid.uuid4().hex[:6]}.csv",
            b"name\nalpha\n",
        )
        original_file = frappe.get_doc("File", saved["file_id"])
        original_url = original_file.file_url
        original_size = original_file.file_size
        frappe.set_user(self.ALPHA)
        manager = BaseManager({"key": "sales", "name": "Sales"})

        def chat(messages, usage=None, tools=None, tool_calls=None):
            usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            return iter(["File sudah saya periksa."])

        with (
            patch.object(manager, "ensure_conversation", return_value=self.alpha_conv.name),
            patch.object(manager, "get_worker_def", return_value=None),
            patch.object(manager, "build_system_prompt", return_value="_Test prompt"),
            patch("aios_v1.managers.base_manager.get_tools_schema_for_worker", return_value=[]),
            patch("aios_v1.managers.base_manager.chat_stream", side_effect=chat),
            patch("aios_v1.managers.base_manager.record_token_usage_batch"),
        ):
            list(
                manager.handle_stream(
                    "Periksa file",
                    conversation_id=self.alpha_conv.name,
                    user=self.ALPHA,
                    attachments=[
                        {
                            "file_id": saved["file_id"],
                            "file_name": saved["file_name"],
                            "file_size": saved["file_size"],
                            "format": "csv",
                        }
                    ],
                )
            )

        user_message = frappe.get_all(
            "AIOS Message",
            filters={"conversation": self.alpha_conv.name, "role": "user"},
            fields=["name", "content"],
            order_by="creation desc",
            limit=1,
        )[0]
        bound_file = frappe.get_doc("File", saved["file_id"])
        self.assertEqual(user_message.content, "Periksa file")
        self.assertEqual(bound_file.attached_to_doctype, "AIOS Message")
        self.assertEqual(str(bound_file.attached_to_name), str(user_message.name))
        self.assertEqual(bound_file.file_url, original_url)
        self.assertEqual(bound_file.file_size, original_size)
        self.assertEqual(int(bound_file.is_private), 1)
        self.assertEqual(bound_file.owner, self.ALPHA)

        detail = _call(f"/api/chat/sales/conversations/{self.alpha_conv.name}")
        self.assertEqual(detail.status_code, 200)
        detail_payload = json.loads(detail.get_data(as_text=True))
        message_payload = next(
            item for item in detail_payload["conversation"]["messages"] if str(item["id"]) == str(user_message.name)
        )
        self.assertEqual(
            message_payload["artifacts"],
            [
                {
                    "type": "FILE",
                    "file_id": saved["file_id"],
                    "file_name": saved["file_name"],
                    "file_url": saved["file_url"],
                    "format": "csv",
                    "size": saved["file_size"],
                    "conversation_id": str(self.alpha_conv.name),
                }
            ],
        )
        self.assertIn(saved["file_id"], json.dumps(message_payload))

    def test_handle_stream_binds_generated_file_to_assistant_message_without_exposing_id(self):
        from aios_v1.managers.base_manager import BaseManager

        saved = self._save_workspace_file(
            self.alpha_conv,
            self.ALPHA,
            f"generated {uuid.uuid4().hex[:6]}.md",
            b"# Generated report\n",
        )
        frappe.set_user(self.ALPHA)
        manager = BaseManager({"key": "sales", "name": "Sales"})
        stream_calls = []

        def chat(messages, usage=None, tools=None, tool_calls=None):
            usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            if not stream_calls:
                stream_calls.append("tool")
                tool_calls.append(
                    {
                        "id": "call-file",
                        "function": {"name": "workspace_create_file", "arguments": "{}"},
                    }
                )
                return iter([])
            return iter(["Laporan terlampir."])

        def execute_tool(name, arguments_json, context=None):
            self.assertEqual(name, "workspace_create_file")
            context["_created_file_ids"].append(saved["file_id"])
            return json.dumps(
                {
                    "status": "created",
                    "artifact": {
                        "type": "FILE",
                        "file_name": saved["file_name"],
                        "file_url": saved["file_url"],
                        "format": "md",
                        "size": saved["file_size"],
                        "conversation_id": str(self.alpha_conv.name),
                    },
                }
            )

        with (
            patch.object(manager, "ensure_conversation", return_value=self.alpha_conv.name),
            patch.object(manager, "get_worker_def", return_value=None),
            patch.object(manager, "build_system_prompt", return_value="_Test prompt"),
            patch("aios_v1.managers.base_manager.get_tools_schema_for_worker", return_value=[]),
            patch("aios_v1.managers.base_manager.chat_stream", side_effect=chat),
            patch("aios_v1.managers.base_manager.execute_tool", side_effect=execute_tool),
            patch("aios_v1.managers.base_manager.record_token_usage_batch"),
        ):
            events = list(
                manager.handle_stream(
                    "Buat laporan",
                    conversation_id=self.alpha_conv.name,
                    user=self.ALPHA,
                )
            )

        assistant_message = frappe.get_all(
            "AIOS Message",
            filters={"conversation": self.alpha_conv.name, "role": "manager"},
            fields=["name", "content"],
            order_by="creation desc",
            limit=1,
        )[0]
        bound_file = frappe.get_doc("File", saved["file_id"])
        self.assertEqual(assistant_message.content, "Laporan terlampir.")
        self.assertEqual(bound_file.attached_to_doctype, "AIOS Message")
        self.assertEqual(str(bound_file.attached_to_name), str(assistant_message.name))
        self.assertEqual(bound_file.file_url, saved["file_url"])
        self.assertNotIn(saved["file_id"], "".join(events))


if __name__ == "__main__":
    import unittest

    unittest.main()
