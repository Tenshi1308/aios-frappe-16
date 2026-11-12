"""P0: isolasi endpoint chat/list/detail/stream lewat method whitelisted resmi.

Fase 1 migrasi Opsi A: dispatcher kustom `/api/chat/*` + `/api/connector/*`
digantikan pemanggilan LANGSUNG ke `aios_v1.api.chat.*`,
`aios_v1.api.connector.*`, dan `aios_v1.api.branches.*`.

Kontrak baru:
- Method sederhana mengembalikan dict (bukan `Response` + `status_code`).
- `stream_chat` mengembalikan `werkzeug.wrappers.Response` SSE ber-generator.
- Tamu ditolak 403 `frappe.PermissionError` (bukan 401 kustom dispatcher).
- 404 -> `frappe.DoesNotExistError`, 429 -> `frappe.TooManyRequestsError`,
  413/400 -> `frappe.ValidationError`.

Butuh site + DB -> `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import json
import os
from io import BytesIO
from unittest.mock import patch

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from aios_v1.api import chat, connector
from aios_v1.api.branches import list_branches
from aios_v1.api.chat import MAX_PDF_BYTES, _parse_bool_flag
from aios_v1.lib.workspace import WorkspaceError, save_private_file
from aios_v1.plugin_manager.registry import get_branches

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _make_test_user(email, first_name):
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    doc = frappe.get_doc(
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
    )
    doc.insert(ignore_permissions=True)
    return doc


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


class TestChatEndpointIsolation(IntegrationTestCase):
    ALPHA = "_test.endpoint.alpha@example.com"
    BETA = "_test.endpoint.beta@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        self._physical_files = []
        self.addCleanup(self._restore_and_rollback)
        _make_test_user(self.ALPHA, "_Test Endpoint Alpha")
        _make_test_user(self.BETA, "_Test Endpoint Beta")
        self.alpha_conv = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": self.ALPHA,
                "branch": "sales",
                "title": "_Test Alpha endpoint",
            }
        ).insert(ignore_permissions=True)
        self.beta_conv = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": self.BETA,
                "branch": "sales",
                "title": "_Test Beta endpoint",
            }
        ).insert(ignore_permissions=True)

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

    def test_branches_endpoint_returns_display_fields_only(self):
        frappe.set_user(self.ALPHA)

        result = list_branches()

        self.assertIn("branches", result)
        branches = result["branches"]
        self.assertTrue(branches)
        branch_fields = {"key", "name", "description", "tagline", "enabled", "workers"}
        worker_fields = {"key", "branch", "jobRole", "description", "exampleQuestions", "enabled"}
        forbidden_branch_fields = {"manager_persona", "icon"}
        forbidden_worker_fields = {
            "personality",
            "priorities",
            "antiPatterns",
            "answerStructure",
            "relevantEntities",
        }

        for branch in branches:
            self.assertTrue(forbidden_branch_fields.isdisjoint(branch))
            self.assertEqual(set(branch), branch_fields)
            self.assertIsInstance(branch["enabled"], bool)
            self.assertTrue(branch["workers"])
            for worker in branch["workers"]:
                self.assertTrue(forbidden_worker_fields.isdisjoint(worker))
                self.assertEqual(set(worker), worker_fields)
                self.assertIn("jobRole", worker)
                self.assertIn("exampleQuestions", worker)

    def test_internal_get_branches_keeps_prompt_persona(self):
        branches = get_branches()

        self.assertTrue(branches)
        self.assertTrue(all(branch.get("manager_persona") for branch in branches))

    def _restore_and_rollback(self):
        frappe.local.request = None
        frappe.set_user("Administrator")
        frappe.db.commit = self._orig_commit
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

    def _track_private_file(self, file_url):
        import frappe.utils

        self._physical_files.append(
            os.path.join(
                frappe.utils.get_site_path("private", "files"),
                os.path.basename(file_url or ""),
            )
        )

    def _upload_multipart(self, form):
        data = dict(form)
        data["file"] = (BytesIO(b"kolom\nnilai\n"), "_test upload flag.csv")
        _install_request(
            EnvironBuilder(
                path="/api/method/aios_v1.api.chat.upload_file",
                method="POST",
                data=data,
            )
        )
        try:
            return chat.upload_file()
        finally:
            frappe.local.request = None

    def test_list_only_own_conversations(self):
        frappe.set_user(self.ALPHA)
        result = chat.list_conversations("sales")
        self.assertIn("conversations", result)
        ids = [item["id"] for item in result["conversations"]]
        self.assertIn(self.alpha_conv.name, ids)
        self.assertNotIn(self.beta_conv.name, ids)

    def test_detail_other_user_returns_404(self):
        frappe.set_user(self.ALPHA)
        with self.assertRaises(frappe.DoesNotExistError):
            chat.get_conversation(str(self.beta_conv.name), branch="sales")

    def test_detail_own_returns_200(self):
        frappe.set_user(self.ALPHA)
        result = chat.get_conversation(str(self.alpha_conv.name), branch="sales")
        self.assertIn("conversation", result)
        self.assertEqual(str(result["conversation"]["id"]), str(self.alpha_conv.name))

    def test_detail_returns_file_attachments_per_message(self):
        frappe.set_user(self.ALPHA)
        marker = os.urandom(4).hex()
        message = frappe.get_doc(
            {
                "doctype": "AIOS Message",
                "conversation": self.alpha_conv.name,
                "role": "user",
                "content": "Lihat file ini",
            }
        ).insert(ignore_permissions=True)
        saved = self._call_ok(
            save_private_file,
            f"_test_inline_attachment_{marker}.csv",
            b"name\nalpha\n",
            self.alpha_conv.name,
            self.ALPHA,
        )
        duplicate = self._call_ok(
            save_private_file,
            f"_test_inline_attachment_copy_{marker}.csv",
            b"name\nalpha\n",
            self.alpha_conv.name,
            self.ALPHA,
        )
        self._track_private_file(saved["file_url"])
        self._track_private_file(duplicate["file_url"])
        for item in (saved, duplicate):
            file_doc = frappe.get_doc("File", item["file_id"])
            file_doc.attached_to_doctype = "AIOS Message"
            file_doc.attached_to_name = message.name
            file_doc.save(ignore_permissions=True)

        result = chat.get_conversation(str(self.alpha_conv.name), branch="sales")

        self.assertIn("conversation", result)
        message_payload = result["conversation"]["messages"][0]
        self.assertEqual(
            message_payload.get("artifacts"),
            [
                {
                    "type": "FILE",
                    "file_id": saved["file_id"],
                    "file_name": saved["file_name"],
                    "file_url": saved["file_url"],
                    "format": "csv",
                    "size": saved["file_size"],
                    "conversation_id": str(self.alpha_conv.name),
                },
                {
                    "type": "FILE",
                    "file_id": duplicate["file_id"],
                    "file_name": duplicate["file_name"],
                    "file_url": duplicate["file_url"],
                    "format": "csv",
                    "size": duplicate["file_size"],
                    "conversation_id": str(self.alpha_conv.name),
                },
            ],
        )
        self.assertNotEqual(saved["file_url"], duplicate["file_url"])
        # `get_conversation` mengembalikan objek `frappe._dict` dengan `createdAt`
        # berupa datetime mentah (dulu dispatcher serialisasi via `default=str`).
        self.assertIn(saved["file_id"], json.dumps(message_payload, default=str))

    def test_detail_keeps_legacy_files_attached_to_conversation(self):
        frappe.set_user(self.ALPHA)
        saved = self._call_ok(
            save_private_file,
            "_test_legacy_file.csv",
            b"name\nlegacy\n",
            self.alpha_conv.name,
            self.ALPHA,
        )
        self._track_private_file(saved["file_url"])

        result = chat.get_conversation(str(self.alpha_conv.name), branch="sales")

        self.assertIn("conversation", result)
        legacy_files = result["conversation"]["legacyFiles"]
        self.assertEqual(len(legacy_files), 1)
        legacy_file = legacy_files[0]
        self.assertEqual(
            {key: legacy_file.get(key) for key in (
                "file_id", "conversation_id", "conversation_title", "branch", "file_name", "file_url", "file_size", "format"
            )},
            {
                "file_id": saved["file_id"],
                "conversation_id": str(self.alpha_conv.name),
                "conversation_title": self.alpha_conv.title,
                "branch": self.alpha_conv.branch,
                "file_name": saved["file_name"],
                "file_url": saved["file_url"],
                "file_size": saved["file_size"],
                "format": "csv",
            },
        )
        self.assertIn("creation", legacy_file)
        bound = frappe.db.get_value(
            "File", saved["file_id"], ["attached_to_doctype", "attached_to_name"], as_dict=True
        )
        self.assertEqual(bound.attached_to_doctype, "AIOS Conversation")
        self.assertEqual(str(bound.attached_to_name), str(self.alpha_conv.name))

    def test_stream_other_conversation_returns_404(self):
        frappe.set_user(self.ALPHA)
        _json_request({"message": "halo", "conversationId": str(self.beta_conv.name)})
        with self.assertRaises(frappe.DoesNotExistError):
            chat.stream_chat(
                branch="sales",
                message="halo",
                conversation_id=str(self.beta_conv.name),
            )

    def test_stream_without_session_denied_403(self):
        frappe.set_user("Guest")
        _json_request({"message": "halo"})
        with self.assertRaises(frappe.PermissionError):
            chat.stream_chat(branch="sales", message="halo")

    def test_stream_blocked_when_site_quota_exhausted(self):
        frappe.set_user(self.ALPHA)
        frappe.db.set_single_value("AIOS Setting", "site_token_limit", 100)
        frappe.db.set_single_value("AIOS Setting", "site_tokens_used", 100)
        _json_request({"message": "halo"})

        with patch("aios_v1.api.chat.check_site_token_quota", return_value=False):
            with self.assertRaises(frappe.TooManyRequestsError):
                chat.stream_chat(branch="sales", message="halo")

    def test_aios_endpoints_without_session_denied_403(self):
        frappe.set_user("Guest")
        cases = (
            ("connector.list_flags", lambda: connector.list_flags()),
            ("connector.list_threads", lambda: connector.list_threads()),
            ("chat.parse_pdf", lambda: chat.parse_pdf()),
            ("chat.upload_file", lambda: chat.upload_file()),
            ("chat.list_conversations", lambda: chat.list_conversations("sales")),
        )
        for name, call in cases:
            with self.subTest(method=name):
                with self.assertRaises(frappe.PermissionError):
                    call()

    def test_parse_pdf_rejects_oversize_before_reading(self):
        frappe.set_user(self.ALPHA)
        builder = EnvironBuilder(
            path="/api/method/aios_v1.api.chat.parse_pdf",
            method="POST",
            data=b"x",
            content_type="application/pdf",
        )
        environ = builder.get_environ()
        environ["CONTENT_LENGTH"] = str(MAX_PDF_BYTES + 1)
        frappe.local.request = Request(environ)
        frappe.local.form_dict = frappe._dict()

        with self.assertRaises(frappe.ValidationError):
            chat.parse_pdf()

    def test_parse_pdf_extracts_text_and_page_count(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

        writer = PdfWriter()
        page = writer.add_blank_page(width=200, height=200)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        font_ref = writer._add_object(font)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
        )
        content = DecodedStreamObject()
        content.set_data(b"BT /F1 12 Tf 20 150 Td (PoC PDF text) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(content)
        pdf_file = BytesIO()
        writer.write(pdf_file)

        frappe.set_user(self.ALPHA)
        _install_request(
            EnvironBuilder(
                path="/api/method/aios_v1.api.chat.parse_pdf",
                method="POST",
                data={"file": (BytesIO(pdf_file.getvalue()), "_Test text.pdf")},
            )
        )
        result = chat.parse_pdf()

        self.assertEqual(result["pages"], 1)
        self.assertIn("PoC PDF text", result["text"])

    def test_parse_bool_flag_accepts_only_true_forms(self):
        for value in (True, 1, "true", "1"):
            with self.subTest(value=value):
                self.assertTrue(_parse_bool_flag(value))
        for value in (False, 0, "0", "false", "False", "", None, "yes", 2, [1]):
            with self.subTest(value=value):
                self.assertFalse(_parse_bool_flag(value))

    def test_upload_with_new_conversation_flag_creates_fresh_conversation(self):
        frappe.set_user(self.ALPHA)
        before_files = frappe.db.count("File", {"attached_to_name": str(self.alpha_conv.name)})
        result = self._call_ok(self._upload_multipart, {"branch": "sales", "new_conversation": "1"})
        self.assertIn("conversationId", result)
        new_conv = str(result["conversationId"])
        self.assertNotEqual(new_conv, str(self.alpha_conv.name))
        self.assertEqual(
            frappe.db.get_value("AIOS Conversation", new_conv, "user"), self.ALPHA
        )
        # File terikat ke conversation BARU, bukan yang lama.
        self.assertEqual(
            frappe.db.get_value("File", result["attachment"]["id"], "attached_to_name"),
            new_conv,
        )
        self.assertEqual(
            frappe.db.count("File", {"attached_to_name": str(self.alpha_conv.name)}),
            before_files,
        )
        self._track_private_file(
            frappe.db.get_value("File", result["attachment"]["id"], "file_url")
        )

    def test_upload_flag_wins_over_provided_conversation_id(self):
        frappe.set_user(self.ALPHA)
        result = self._call_ok(
            self._upload_multipart,
            {"conversationId": str(self.alpha_conv.name), "new_conversation": "1"},
        )
        self.assertIn("conversationId", result)
        self.assertNotEqual(str(result["conversationId"]), str(self.alpha_conv.name))
        self._track_private_file(
            frappe.db.get_value("File", result["attachment"]["id"], "file_url")
        )

    def test_upload_flag_is_user_scoped(self):
        frappe.set_user(self.BETA)
        result = self._call_ok(self._upload_multipart, {"branch": "sales", "new_conversation": "1"})
        self.assertIn("conversationId", result)
        new_conv = str(result["conversationId"])
        self.assertEqual(frappe.db.get_value("AIOS Conversation", new_conv, "user"), self.BETA)
        self.assertNotEqual(new_conv, str(self.alpha_conv.name))
        self._track_private_file(
            frappe.db.get_value("File", result["attachment"]["id"], "file_url")
        )

    def test_conversations_list_orders_by_last_message_and_updates_timestamp(self):
        # alpha_conv dimundurkan modified-nya (raw SQL: set_value menimpa
        # modified dengan now), lalu diberi pesan HARI INI — updatedAt harus
        # mengikuti pesan dan urutannya pertama di atas dokumen yang lebih baru.
        import datetime

        frappe.db.sql(
            "update `tabAIOS Conversation` set modified=%s where name=%s",
            (datetime.datetime.now() - datetime.timedelta(days=3), str(self.alpha_conv.name)),
        )
        extra_conv = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": self.ALPHA,
                "branch": "sales",
                "title": "_Test Alpha newer doc",
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "AIOS Message",
                "conversation": str(self.alpha_conv.name),
                "role": "user",
                "worker_key": "manager",
                "content": "_test last message",
            }
        ).insert(ignore_permissions=True)

        frappe.set_user(self.ALPHA)
        result = chat.list_conversations("sales")
        self.assertIn("conversations", result)
        ids = [str(c["id"]) for c in result["conversations"]]
        self.assertEqual(ids[0], str(self.alpha_conv.name))
        self.assertIn(str(extra_conv.name), ids)
        first = result["conversations"][0]
        # updatedAt pesan hari ini, bukan modified yang sudah dimundurkan 3 hari.
        self.assertGreater(str(first["updatedAt"]), str(extra_conv.modified))
        # Pesan milik user lain tidak bocor ke list ALPHA.
        self.assertNotIn(str(self.beta_conv.name), ids)
