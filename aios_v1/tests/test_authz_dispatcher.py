"""P0: isolasi endpoint `/api/chat` — daftar, detail, dan `/stream` (N2).

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import json
from io import BytesIO

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from aios_v1.api.dispatcher import MAX_PDF_BYTES, CustomAPIResponse, handle_api_request

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

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.local.request = None
        frappe.set_user("Administrator")
        frappe.db.rollback()

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
