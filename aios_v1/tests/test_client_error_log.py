"""Tes integrasi untuk endpoint pelaporan error klien (aios_v1.api.desktop.log_client_error).

Aturan:
- Endpoint berbatas laju (@rate_limit) dan hanya POST.
- Menolak Guest, mengizinkan user yang telah login (termasuk Administrator).
- Memotong payload panjang (message: 500, context: 200, stack: 4000).
- Menyimpan ke DocType Error Log lewat frappe.log_error dengan teks tersanitasi.
- Mengisolasi Error Log: hanya mencatat ID yang dibuat oleh tes ini dan membersihkannya.
"""

from threading import Thread
from unittest.mock import patch

import frappe

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore
from frappe.utils import get_test_client, get_url


class TestClientErrorLog(IntegrationTestCase):
    USER = "_test.client.error@example.com"

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.user = self._ensure_user(
            self.USER,
            first_name="_Test Client Error",
            aios_persona="finance",
            aios_status="Active",
            roles=["AIOS Client"],
        )
        frappe.set_user(self.user.name)
        frappe.local.session_obj = object()
        self.created_error_logs: list[str] = []
        # Bersihkan kunci redis rate limit agar tes terisolasi
        frappe.cache.delete_keys("rl:aios_v1.api.desktop.log_client_error*")

    def tearDown(self):
        frappe.set_user("Administrator")
        # Hanya bersihkan Error Log yang dibuat oleh tes ini (K3)
        for log_name in self.created_error_logs:
            if frappe.db.exists("Error Log", log_name):
                frappe.db.delete("Error Log", log_name)
        frappe.cache.delete_keys("rl:aios_v1.api.desktop.log_client_error*")
        super().tearDown()

    def _ensure_user(self, email: str, first_name: str, aios_persona: str, aios_status: str, roles: list[str]):
        if frappe.db.exists("User", email):
            doc = frappe.get_doc("User", email)
        else:
            doc = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": first_name,
                    "enabled": 1 if aios_status == "Active" else 0,
                    "send_welcome_email": 0,
                    "user_type": "Website User",
                    "aios_persona": aios_persona,
                    "aios_status": aios_status,
                    "roles": [{"role": r} for r in roles],
                }
            ).insert(ignore_permissions=True)
        doc.first_name = first_name
        doc.aios_persona = aios_persona
        doc.aios_status = aios_status
        doc.enabled = 1 if aios_status == "Active" else 0
        doc.set("roles", [{"role": r} for r in roles])
        doc.save(ignore_permissions=True)
        return doc

    def test_endpoint_is_whitelisted_and_post_only(self):
        from aios_v1.api.desktop import log_client_error

        self.assertIn(log_client_error, frappe.whitelisted)
        allowed_methods = frappe.allowed_http_methods_for_whitelisted_func.get(log_client_error)
        self.assertEqual(allowed_methods, ["POST"])

    def test_guest_is_rejected_and_authenticated_user_accepted(self):
        from aios_v1.api.desktop import log_client_error

        frappe.set_user("Guest")
        with self.assertRaises(frappe.AuthenticationError):
            log_client_error(message="Network timeout")

        frappe.set_user(self.user.name)
        res = log_client_error(message="Bootstrap failed", context="loadBootstrap")
        self.assertEqual(res, {"ok": True})

        # Administrator juga diizinkan karena kegagalan bootstrap bisa dialami admin saat debugging
        frappe.set_user("Administrator")
        res_admin = log_client_error(message="Admin bootstrap notice", context="loadBootstrap")
        self.assertEqual(res_admin, {"ok": True})

    def test_empty_message_is_rejected(self):
        from aios_v1.api.desktop import log_client_error

        frappe.set_user(self.user.name)
        with self.assertRaises(frappe.ValidationError):
            log_client_error(message="")
        with self.assertRaises(frappe.ValidationError):
            log_client_error(message="   \n\t  ")

    def test_payload_truncation_and_error_log_creation_with_sanitization(self):
        from aios_v1.api.desktop import log_client_error

        frappe.set_user(self.user.name)

        # Catat Error Log terbaru sebelum pemanggilan
        existing_logs = set(
            frappe.get_all("Error Log", filters={"method": "AIOS Desk Client Error"}, pluck="name")
        )

        sensitive_token = "sk-1234567890abcdefghijklmnop"
        db_name = frappe.conf.get("db_name") or ""
        long_message = f"token={sensitive_token} " + "M" * 600
        long_context = "C" * 300
        long_stack = (f"db={db_name} " if db_name else "") + "S" * 5000

        res = log_client_error(message=long_message, context=long_context, stack=long_stack)
        self.assertEqual(res, {"ok": True})

        # Cari Error Log baru yang dibuat
        new_logs = [
            name
            for name in frappe.get_all("Error Log", filters={"method": "AIOS Desk Client Error"}, pluck="name")
            if name not in existing_logs
        ]
        self.assertTrue(new_logs, "Tidak ada Error Log baru yang tercatat")
        self.created_error_logs.extend(new_logs)

        # Ambil record terbaru
        doc = frappe.get_doc("Error Log", new_logs[0])
        self.assertEqual(doc.method, "AIOS Desk Client Error")
        # Pastikan tidak ada token mentah di pesan yang tersimpan
        self.assertNotIn(sensitive_token, doc.error)
        self.assertIn("[REDACTED]", doc.error)
        if db_name:
            self.assertNotIn(db_name, doc.error)
            self.assertIn("[DB]", doc.error)

    def test_http_post_log_client_error_with_csrf(self):
        from frappe.auth import CookieManager, LoginManager
        from frappe.sessions import get_csrf_token
        from frappe.utils import set_request

        set_request(path="/")
        frappe.local.cookie_manager = CookieManager()
        frappe.local.login_manager = LoginManager()
        frappe.local.login_manager.login_as(self.user.name)
        csrf_token = get_csrf_token()
        sid = frappe.session.sid
        site = frappe.local.site
        main_db = frappe.local.db
        client = get_test_client()
        url = f"{get_url()}/api/method/aios_v1.api.desktop.log_client_error"
        response = []

        existing_logs = set(
            frappe.get_all("Error Log", filters={"method": "AIOS Desk Client Error"}, pluck="name")
        )

        def share_test_db(set_admin_as_user=True):
            frappe.local.db = main_db

        def dispatch():
            with (
                patch("frappe.app.get_site_name", return_value=site),
                patch("frappe.connect", side_effect=share_test_db),
                patch("frappe.app.sync_database"),
            ):
                response.append(
                    client.post(
                        url,
                        json={
                            "sid": sid,
                            "message": "HTTP Client Error Test",
                            "context": "loadBootstrap",
                        },
                        headers={"X-Frappe-CSRF-Token": csrf_token},
                    )
                )

        thread = Thread(target=dispatch)
        thread.start()
        thread.join()

        self.assertEqual(response[0].status_code, 200, response[0].get_data(as_text=True))
        data = response[0].get_json()
        self.assertEqual(data.get("message"), {"ok": True})

        # Catat baris Error Log untuk dibersihkan
        new_logs = [
            name
            for name in frappe.get_all("Error Log", filters={"method": "AIOS Desk Client Error"}, pluck="name")
            if name not in existing_logs
        ]
        self.created_error_logs.extend(new_logs)

    def test_http_post_rate_limiting(self):
        from frappe.auth import CookieManager, LoginManager
        from frappe.sessions import get_csrf_token
        from frappe.utils import set_request

        set_request(path="/")
        frappe.local.cookie_manager = CookieManager()
        frappe.local.login_manager = LoginManager()
        frappe.local.login_manager.login_as(self.user.name)
        csrf_token = get_csrf_token()
        sid = frappe.session.sid
        site = frappe.local.site
        main_db = frappe.local.db
        client = get_test_client()
        url = f"{get_url()}/api/method/aios_v1.api.desktop.log_client_error"

        def share_test_db(set_admin_as_user=True):
            frappe.local.db = main_db

        # Kirim 11 permintaan: 10 pertama sukses (limit=10), permintaan ke-11 memicu HTTP 429
        statuses = []
        for i in range(11):
            res_box = []

            def dispatch():
                with (
                    patch("frappe.app.get_site_name", return_value=site),
                    patch("frappe.connect", side_effect=share_test_db),
                    patch("frappe.app.sync_database"),
                ):
                    res_box.append(
                        client.post(
                            url,
                            json={"sid": sid, "message": f"Rate limit test #{i}"},
                            headers={"X-Frappe-CSRF-Token": csrf_token},
                        )
                    )

            thread = Thread(target=dispatch)
            thread.start()
            thread.join()
            statuses.append(res_box[0].status_code)

        # 10 pertama harus 200
        self.assertEqual(statuses[:10], [200] * 10, f"Status awal tidak 200: {statuses[:10]}")
        # Ke-11 harus 429 (Too Many Requests)
        self.assertEqual(statuses[10], 429, f"Request ke-11 tidak menghasilkan 429: {statuses[10]}")
