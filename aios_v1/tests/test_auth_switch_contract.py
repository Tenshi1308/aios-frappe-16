"""Kontrak statis switch auth ke Frappe (login, registrasi, logout).

Test ini tidak mengimpor frappe sehingga bisa jalan di CI tanpa site.
Bukti runtime tetap butuh `bench --site ... run-tests` dan browser.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTH = REPO_ROOT / "aios_v1" / "auth.py"
DISPATCHER = REPO_ROOT / "aios_v1" / "api" / "dispatcher.py"
LOGIN = REPO_ROOT / "frontend" / "src" / "views" / "LoginView.vue"
SESSION_API = REPO_ROOT / "frontend" / "src" / "api" / "session.ts"
CLIENT_API = REPO_ROOT / "frontend" / "src" / "api" / "client.ts"
REGISTER_VIEW = REPO_ROOT / "frontend" / "src" / "views" / "RegisterView.vue"
ROUTER = REPO_ROOT / "frontend" / "src" / "router" / "index.ts"


class TestRegisterAccountContract(unittest.TestCase):
    def test_creates_lead_in_developer_site(self):
        src = AUTH.read_text(encoding="utf-8")
        self.assertIn('frappe.new_doc("Lead")', src)
        self.assertNotIn('frappe.new_doc("User")', src)
        self.assertIn("@frappe.whitelist(allow_guest=True)", src)
        self.assertIn("@rate_limit(", src)
        self.assertIn('"AIOS Signup"', src)
        self.assertIn("company_name", src)
        self.assertIn("country", src)
        self.assertIn("aios_site_role", src)
        self.assertIn("developer", src)
        self.assertNotIn('frappe.new_doc("AIOS Tenant")', src)


class TestDispatcherAuthContract(unittest.TestCase):
    def test_old_login_register_deprecated(self):
        src = DISPATCHER.read_text(encoding="utf-8")
        self.assertIn("/api/method/login", src)
        self.assertIn("/api/method/aios_v1.auth.register_account", src)
        self.assertNotIn('doc = frappe.new_doc("AIOS Tenant")', src)


class TestFrontendAuthContract(unittest.TestCase):
    def test_client_login_uses_frappe(self):
        src = SESSION_API.read_text(encoding="utf-8")
        self.assertTrue("'/api/method/login'" in src or '"/api/method/login"' in src)
        self.assertTrue("'/api/method/aios_v1.setup.get_session_context'" in src or '"/api/method/aios_v1.setup.get_session_context"' in src)
        self.assertNotIn('"/auth/login"', src)
        self.assertNotIn("'/auth/login'", src)
        self.assertNotIn('"/auth/register"', src)
        self.assertNotIn("'/auth/register'", src)
        reg_src = REGISTER_VIEW.read_text(encoding="utf-8")
        self.assertIn("menunggu persetujuan", reg_src)

    def test_developer_login_uses_frappe(self):
        src = LOGIN.read_text(encoding="utf-8")
        self.assertIn("session.login", src)
        self.assertNotIn('"/auth/login"', src)
        self.assertNotIn("'/auth/login'", src)

    def test_api_method_unwraps_message(self):
        src = CLIENT_API.read_text(encoding="utf-8")
        self.assertIn("export function unwrapMessage", src)
        self.assertTrue(".message" in src or "'message'" in src)

    def test_logout_uses_frappe(self):
        src = SESSION_API.read_text(encoding="utf-8")
        self.assertIn("logout", src)
        self.assertTrue("'/api/auth/logout'" in src or '"/api/auth/logout"' in src)

    def test_home_has_no_legacy_gate(self):
        src = ROUTER.read_text(encoding="utf-8")
        self.assertNotIn('"/payment"', src)
        self.assertNotIn("'/payment'", src)
        self.assertNotIn('"/onboarding"', src)
        self.assertNotIn("'/onboarding'", src)

    def test_raw_posts_send_csrf(self):
        src = CLIENT_API.read_text(encoding="utf-8")
        self.assertIn("csrfToken", src)
        self.assertIn("X-Frappe-CSRF-Token", src)

    def test_no_silent_catch_in_frontend_auth(self):
        """Zero Silent Errors: login dan boot tidak boleh menelan error dengan catch kosong."""
        for path in (SESSION_API, LOGIN, CLIENT_API):
            src = path.read_text(encoding="utf-8")
            self.assertNotRegex(
                src,
                r"catch\s*\{\s*(?://[^\n]*)?\s*\}",
                f"Ditemukan silent catch kosong di {path.name}",
            )
            if path == SESSION_API:
                self.assertIn("safeMessage(", src, "login() harus membaca response error server via safeMessage")
                self.assertIn("console.error", src, "login() harus mencatat network error ke console")


if __name__ == "__main__":
    unittest.main()
