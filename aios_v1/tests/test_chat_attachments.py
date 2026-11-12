"""H5 fase 1: endpoint upload lampiran + validasi `file_ids` di `/stream`.

Fase 1 migrasi Opsi A: dispatcher kustom `/api/chat/*` digantikan pemanggilan
LANGSUNG ke `aios_v1.api.chat.upload_file` / `aios_v1.api.chat.stream_chat` /
`aios_v1.api.chat.get_conversation`.

Kontrak baru:
- `upload_file` mengembalikan dict (bukan `Response` + `status_code`).
- `stream_chat` mengembalikan `werkzeug.wrappers.Response` SSE ber-generator.
- Status error kustom lama (401/403/404/400/429) dipetakan ke exception resmi
  Frappe (`PermissionError` / `DoesNotExistError` / `ValidationError` /
  `TooManyRequestsError`); kode error lama tetap diverifikasi lewat argumen
  yang diteruskan ke `chat._raise_safe`.

Butuh site + DB -> `bench --site aios-v16.localhost run-tests --app aios_v1`.
Request HTTP palsu memakai pola `EnvironBuilder` + `werkzeug.wrappers.Request`.
"""

import json
import os
import uuid
from io import BytesIO
from unittest.mock import MagicMock, patch

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from aios_v1.api import chat
from aios_v1.api import chat as chat_api  # alias: some tests define a local `chat` mock
from aios_v1.lib.workspace import WorkspaceError, save_private_file

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


def _install_request(builder):
    """Pasang `werkzeug` Request palsu + `form_dict` kosong (kontrak method resmi)."""
    frappe.local.request = Request(builder.get_environ())
    frappe.local.form_dict = frappe._dict()


def _json_request(body):
    """Request JSON palsu untuk `chat.stream_chat`."""
    _install_request(
        EnvironBuilder(
            path="/api/method/aios_v1.api.chat.stream_chat",
            method="POST",
            data=json.dumps(body),
            content_type="application/json",
        )
    )


class TestChatAttachments(IntegrationTestCase):
    ALPHA = "_test.chat.attach.alpha@example.com"
    BETA = "_test.chat.attach.beta@example.com"

    def setUp(self):
        super().setUp()
        self.original_commit = frappe.db.commit
        frappe.db.commit = lambda *args, **kwargs: None
        self._physical_files = []
        self.addCleanup(self._restore_and_rollback)
        _make_user(self.ALPHA, "_Test Attach Alpha")
        _make_user(self.BETA, "_Test Attach Beta")
        self.alpha_conv = frappe.get_doc(
            {"doctype": "AIOS Conversation", "user": self.ALPHA, "branch": "sales", "title": "_Test Attach A"}
        ).insert(ignore_permissions=True)
        self.beta_conv = frappe.get_doc(
            {"doctype": "AIOS Conversation", "user": self.BETA, "branch": "sales", "title": "_Test Attach B"}
        ).insert(ignore_permissions=True)

    def _restore_and_rollback(self):
        frappe.local.request = None
        frappe.set_user("Administrator")
        frappe.db.commit = self.original_commit
        frappe.db.rollback()
        for path in getattr(self, "_physical_files", []):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def tearDown(self):
        frappe.set_user("Administrator")
        for email in (self.ALPHA, self.BETA):
            for conv in frappe.get_all("AIOS Conversation", filters={"user": email}, pluck="name"):
                for msg in frappe.get_all("AIOS Message", filters={"conversation": conv}, pluck="name"):
                    frappe.delete_doc("AIOS Message", msg, ignore_permissions=True, force=True, delete_permanently=True)
                frappe.delete_doc("AIOS Conversation", conv, ignore_permissions=True, force=True, delete_permanently=True)
            for cname in frappe.get_all("Contact", filters={"user": email}, pluck="name"):
                frappe.delete_doc("Contact", cname, ignore_permissions=True, force=True, delete_permanently=True)
            if frappe.db.exists("Notification Settings", email):
                frappe.delete_doc("Notification Settings", email, ignore_permissions=True, force=True, delete_permanently=True)
            if frappe.db.exists("User", email):
                frappe.delete_doc("User", email, ignore_permissions=True, force=True, delete_permanently=True)
        self._restore_and_rollback()

    def _call_ok(self, fn, *args, **kwargs):
        """Panggil method/helper yang diharapkan berhasil.

        Kegagalan dari lapisan workspace/Frappe (mis. `save_private_file` yang
        menulis ke `private/files` read-only di environment ini) diangkat jadi
        assertion failure lengkap dengan penyebabnya, bukan error tanpa konteks.
        Exception tak terduga sengaja dibiarkan sebagai error agar bug rewrite
        tidak tersamarkan.
        """
        try:
            return fn(*args, **kwargs)
        except (
            frappe.ValidationError,
            frappe.PermissionError,
            frappe.DoesNotExistError,
            frappe.TooManyRequestsError,
            WorkspaceError,
            OSError,
        ) as exc:
            self.fail(f"{getattr(fn, '__name__', str(fn))} gagal: {type(exc).__name__}: {exc}")

    def _assert_error(self, exc_type, code, fn, *args, **kwargs):
        """Verifikasi kontrak error baru: exception Frappe + kode error lama.

        Method resmi memetakan `(status, code, message)` lewat `chat._raise_safe`
        ke exception resmi (`frappe.throw`); tangkap argumen `code` agar
        assertion kode lama tetap utuh tanpa body JSON yang sudah dihapus.
        """
        with patch("aios_v1.api.chat._raise_safe", wraps=chat._raise_safe) as raise_safe:
            with self.assertRaises(exc_type):
                fn(*args, **kwargs)
        codes = [call.args[1] for call in raise_safe.call_args_list]
        self.assertIn(code, codes, f"kode error {code!r} tidak dipetakan: {codes}")

    def _upload(self, file_name, data, conversation_id=None, branch=None, user=None):
        frappe.set_user(user or self.ALPHA)
        form = {}
        if conversation_id is not None:
            form["conversationId"] = str(conversation_id)
        if branch is not None:
            form["branch"] = branch
        multipart = dict(form)
        multipart["file"] = (BytesIO(data), file_name)
        _install_request(
            EnvironBuilder(
                path="/api/method/aios_v1.api.chat.upload_file",
                method="POST",
                data=multipart,
            )
        )
        try:
            return chat.upload_file()
        finally:
            frappe.local.request = None

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

    def test_upload_without_session_denied_403(self):
        with self.assertRaises(frappe.PermissionError):
            self._upload("laporan.csv", b"a,b\n1,2\n", conversation_id=self.alpha_conv.name, user="Guest")

    def test_upload_to_other_users_conversation_returns_404(self):
        self._assert_error(
            frappe.DoesNotExistError, "CONVERSATION_NOT_FOUND",
            self._upload, "curi.csv", b"a\n1\n",
            conversation_id=self.beta_conv.name, user=self.ALPHA,
        )

    def test_upload_traversal_name_returns_400_without_file(self):
        before = frappe.db.count("File")
        self._assert_error(
            frappe.ValidationError, "INVALID_FILENAME",
            self._upload, "../../evil.csv", b"a\n1\n",
            conversation_id=self.alpha_conv.name,
        )
        self.assertEqual(frappe.db.count("File"), before)

    def test_upload_success_creates_private_file_and_returns_metadata(self):
        marker = uuid.uuid4().hex[:6]
        upload_name = f"laporan {marker}.csv"
        result = self._call_ok(self._upload, upload_name, b"name,amount\nINV-1,10\n", conversation_id=self.alpha_conv.name)
        self.assertIn("conversationId", result)
        self.assertEqual(str(result["conversationId"]), str(self.alpha_conv.name))
        attachment = result["attachment"]
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
        first_response = self._call_ok(self._upload, first_name, content, conversation_id=self.alpha_conv.name)
        second_response = self._call_ok(self._upload, second_name, content, conversation_id=self.alpha_conv.name)

        self.assertIn("attachment", first_response)
        self.assertIn("attachment", second_response)
        first = first_response["attachment"]
        second = second_response["attachment"]
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
        result = self._call_ok(self._upload, upload_name, b"a\n1\n", branch="sales")
        self.assertIn("conversationId", result)
        conversation_id = result["conversationId"]
        owner = frappe.db.get_value("AIOS Conversation", str(conversation_id), "user")
        self.assertEqual(owner, self.ALPHA)
        self.assertTrue(result["attachment"]["id"])
        self._track(
            [upload_name, os.path.basename(frappe.db.get_value("File", result["attachment"]["id"], "file_url"))],
            "private",
            "files",
        )

    def test_stream_with_file_ids_without_conversation_returns_400_before_manager(self):
        frappe.set_user(self.ALPHA)
        _json_request({"message": "halo", "file_ids": ["beberapa-file"]})
        with patch("aios_v1.api.chat.get_manager") as get_manager:
            get_manager.side_effect = AssertionError("get_manager tidak boleh dipanggil")
            self._assert_error(
                frappe.ValidationError, "CONVERSATION_REQUIRED",
                chat.stream_chat, branch="sales", message="halo",
            )
        get_manager.assert_not_called()

    def test_stream_with_foreign_file_returns_403_before_manager(self):
        foreign = self._call_ok(
            self._save_workspace_file,
            self.beta_conv, self.BETA, f"milik beta {uuid.uuid4().hex[:6]}.csv", b"x\n1\n",
        )
        frappe.set_user(self.ALPHA)
        _json_request({
            "message": "halo",
            "conversationId": str(self.alpha_conv.name),
            "file_ids": [foreign["file_id"]],
        })
        with patch("aios_v1.api.chat.get_manager") as get_manager:
            get_manager.side_effect = AssertionError("get_manager tidak boleh dipanggil")
            self._assert_error(
                frappe.PermissionError, "FILE_FORBIDDEN",
                chat.stream_chat, branch="sales", message="halo",
                conversation_id=str(self.alpha_conv.name),
            )
        get_manager.assert_not_called()

    def test_stream_valid_passes_attachment_metadata_to_manager(self):
        marker = uuid.uuid4().hex[:6]
        uploaded = self._call_ok(
            self._save_workspace_file,
            self.alpha_conv, self.ALPHA, f"valid {marker}.csv", f"col\n{marker}\n".encode(),
        )
        frappe.set_user(self.ALPHA)
        manager = MagicMock()
        manager.handle_stream.return_value = iter(['data: {"type": "delta", "text": "ok"}\n\n'])
        _json_request({
            "message": "tolong analisis",
            "conversationId": str(self.alpha_conv.name),
            "file_ids": [uploaded["file_id"]],
        })
        with patch("aios_v1.api.chat.get_manager", return_value=manager):
            response = chat.stream_chat(
                branch="sales",
                message="tolong analisis",
                conversation_id=str(self.alpha_conv.name),
            )
        self.assertEqual(response.mimetype, "text/event-stream")
        self.assertEqual(response.headers["Cache-Control"], "no-cache, no-transform")
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")
        self.assertTrue(hasattr(response.response, "__next__"), "SSE response harus ber-generator/iterator")
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

        saved = self._call_ok(
            self._save_workspace_file,
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

        detail_payload = chat_api.get_conversation(str(self.alpha_conv.name), branch="sales")
        self.assertIn("conversation", detail_payload)
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
        # `get_conversation` mengembalikan `frappe._dict` dengan `createdAt`
        # datetime mentah (dulu dispatcher serialisasi via `default=str`).
        self.assertIn(saved["file_id"], json.dumps(message_payload, default=str))

    def test_handle_stream_binds_generated_file_to_assistant_message_without_exposing_id(self):
        from aios_v1.managers.base_manager import BaseManager

        saved = self._call_ok(
            self._save_workspace_file,
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
