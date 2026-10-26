"""P0: isolasi endpoint `/api/chat` — daftar, detail, dan `/stream` (N2).

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import json
import os
from io import BytesIO

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from aios_v1.api.dispatcher import MAX_PDF_BYTES, CustomAPIResponse, _parse_bool_flag, handle_api_request
from aios_v1.lib.workspace import save_private_file

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


def _call(path, method="GET", body=None):
    """Panggil dispatcher dengan request HTTP palsu, kembalikan Response."""
    data = json.dumps(body) if body is not None else None
    builder = EnvironBuilder(
        path=path,
        method=method,
        data=data,
        content_type="application/json" if data else None,
    )
    frappe.local.request = Request(builder.get_environ())
    try:
        handle_api_request()
    except CustomAPIResponse as exc:
        return exc._custom_response
    finally:
        frappe.local.request = None
    raise AssertionError(f"{path} tidak mengembalikan response")


class TestChatEndpointIsolation(IntegrationTestCase):
    ALPHA = "_test.endpoint.alpha@example.com"
    BETA = "_test.endpoint.beta@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
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
        self._physical_files = []

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.local.request = None
        frappe.set_user("Administrator")
        frappe.db.rollback()
        for path in self._physical_files:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

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
        builder = EnvironBuilder(
            path="/api/chat/upload",
            method="POST",
            data=data,
        )
        frappe.local.request = Request(builder.get_environ())
        try:
            handle_api_request()
        except CustomAPIResponse as exc:
            return exc._custom_response
        finally:
            frappe.local.request = None
        raise AssertionError("upload tidak mengembalikan response")

    def test_list_only_own_conversations(self):
        frappe.set_user(self.ALPHA)
        res = _call("/api/chat/sales/conversations")
        self.assertEqual(res.status_code, 200)
        body = json.loads(res.get_data(as_text=True))
        ids = [item["id"] for item in body["conversations"]]
        self.assertIn(self.alpha_conv.name, ids)
        self.assertNotIn(self.beta_conv.name, ids)

    def test_detail_other_user_returns_404(self):
        frappe.set_user(self.ALPHA)
        res = _call(f"/api/chat/sales/conversations/{self.beta_conv.name}")
        self.assertEqual(res.status_code, 404)

    def test_detail_own_returns_200(self):
        frappe.set_user(self.ALPHA)
        res = _call(f"/api/chat/sales/conversations/{self.alpha_conv.name}")
        self.assertEqual(res.status_code, 200)

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
        saved = save_private_file(
            f"_test_inline_attachment_{marker}.csv",
            b"name\nalpha\n",
            self.alpha_conv.name,
            self.ALPHA,
        )
        duplicate = save_private_file(
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

        res = _call(f"/api/chat/sales/conversations/{self.alpha_conv.name}")

        self.assertEqual(res.status_code, 200)
        body = json.loads(res.get_data(as_text=True))
        message_payload = body["conversation"]["messages"][0]
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
        self.assertIn(saved["file_id"], json.dumps(message_payload))

    def test_detail_keeps_legacy_files_attached_to_conversation(self):
        frappe.set_user(self.ALPHA)
        saved = save_private_file(
            "_test_legacy_file.csv",
            b"name\nlegacy\n",
            self.alpha_conv.name,
            self.ALPHA,
        )
        self._track_private_file(saved["file_url"])

        res = _call(f"/api/chat/sales/conversations/{self.alpha_conv.name}")

        self.assertEqual(res.status_code, 200)
        body = json.loads(res.get_data(as_text=True))
        legacy_files = body["conversation"]["legacyFiles"]
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
        res = _call(
            "/api/chat/sales/stream",
            method="POST",
            body={"message": "halo", "conversationId": str(self.beta_conv.name)},
        )
        self.assertEqual(res.status_code, 404)

    def test_stream_without_session_returns_401(self):
        frappe.set_user("Guest")
        res = _call(
            "/api/chat/sales/stream",
            method="POST",
            body={"message": "halo"},
        )
        self.assertEqual(res.status_code, 401)

    def test_stream_blocked_when_site_quota_exhausted(self):
        frappe.set_user(self.ALPHA)
        frappe.db.set_single_value("AIOS Setting", "site_token_limit", 100)
        frappe.db.set_single_value("AIOS Setting", "site_tokens_used", 100)

        res = _call(
            "/api/chat/sales/stream",
            method="POST",
            body={"message": "halo"},
        )

        self.assertEqual(res.status_code, 429)

    def test_aios_endpoints_without_session_return_401(self):
        frappe.set_user("Guest")
        cases = (
            ("GET", "/api/chatbot/sessions", None),
            ("POST", "/api/chat/parse-pdf", {}),
            ("POST", "/api/chat/upload", None),
            ("GET", "/api/chat/sales/conversations", None),
        )
        for method, path, body in cases:
            with self.subTest(method=method, path=path):
                res = _call(path, method=method, body=body)
                self.assertEqual(res.status_code, 401)

    def test_parse_pdf_rejects_oversize_before_reading(self):
        frappe.set_user(self.ALPHA)
        builder = EnvironBuilder(
            path="/api/chat/parse-pdf",
            method="POST",
            data=b"x",
            content_type="application/pdf",
        )
        environ = builder.get_environ()
        environ["CONTENT_LENGTH"] = str(MAX_PDF_BYTES + 1)
        frappe.local.request = Request(environ)
        try:
            handle_api_request()
        except CustomAPIResponse as exc:
            response = exc._custom_response
        finally:
            frappe.local.request = None

        self.assertEqual(response.status_code, 413)

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
        builder = EnvironBuilder(
            path="/api/chat/parse-pdf",
            method="POST",
            data={"file": (BytesIO(pdf_file.getvalue()), "_Test text.pdf")},
        )
        frappe.local.request = Request(builder.get_environ())
        try:
            handle_api_request()
        except CustomAPIResponse as exc:
            response = exc._custom_response
        finally:
            frappe.local.request = None

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.get_data(as_text=True))
        self.assertEqual(body["pages"], 1)
        self.assertIn("PoC PDF text", body["text"])

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
        response = self._upload_multipart({"branch": "sales", "new_conversation": "1"})
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.get_data(as_text=True))
        new_conv = str(body["conversationId"])
        self.assertNotEqual(new_conv, str(self.alpha_conv.name))
        self.assertEqual(
            frappe.db.get_value("AIOS Conversation", new_conv, "user"), self.ALPHA
        )
        # File terikat ke conversation BARU, bukan yang lama.
        self.assertEqual(
            frappe.db.get_value("File", body["attachment"]["id"], "attached_to_name"),
            new_conv,
        )
        self.assertEqual(
            frappe.db.count("File", {"attached_to_name": str(self.alpha_conv.name)}),
            before_files,
        )
        self._track_private_file(
            frappe.db.get_value("File", body["attachment"]["id"], "file_url")
        )

    def test_upload_flag_wins_over_provided_conversation_id(self):
        frappe.set_user(self.ALPHA)
        response = self._upload_multipart(
            {"conversationId": str(self.alpha_conv.name), "new_conversation": "1"}
        )
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.get_data(as_text=True))
        self.assertNotEqual(str(body["conversationId"]), str(self.alpha_conv.name))
        self._track_private_file(
            frappe.db.get_value("File", body["attachment"]["id"], "file_url")
        )

    def test_upload_flag_is_user_scoped(self):
        frappe.set_user(self.BETA)
        response = self._upload_multipart({"branch": "sales", "new_conversation": "1"})
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.get_data(as_text=True))
        new_conv = str(body["conversationId"])
        self.assertEqual(frappe.db.get_value("AIOS Conversation", new_conv, "user"), self.BETA)
        self.assertNotEqual(new_conv, str(self.alpha_conv.name))
        self._track_private_file(
            frappe.db.get_value("File", body["attachment"]["id"], "file_url")
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
        response = _call("/api/chat/sales/conversations")
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.get_data(as_text=True))
        ids = [str(c["id"]) for c in body["conversations"]]
        self.assertEqual(ids[0], str(self.alpha_conv.name))
        self.assertIn(str(extra_conv.name), ids)
        first = body["conversations"][0]
        # updatedAt pesan hari ini, bukan modified yang sudah dimundurkan 3 hari.
        self.assertGreater(str(first["updatedAt"]), str(extra_conv.modified))
        # Pesan milik user lain tidak bocor ke list ALPHA.
        self.assertNotIn(str(self.beta_conv.name), ids)
