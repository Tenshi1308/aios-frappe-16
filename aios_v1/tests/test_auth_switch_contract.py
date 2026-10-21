"""Kontrak statis switch auth ke Frappe (login, registrasi, logout).

Test ini tidak mengimpor frappe sehingga bisa jalan di CI tanpa site.
Bukti runtime tetap butuh `bench --site ... run-tests` dan browser.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTH = REPO_ROOT / "aios_v1" / "auth.py"
DISPATCHER = REPO_ROOT / "aios_v1" / "api" / "dispatcher.py"
LOGIN = REPO_ROOT / "frontend" / "app" / "login" / "page.tsx"
DEV_LOGIN = REPO_ROOT / "frontend" / "app" / "developer" / "login" / "page.tsx"
TOPBAR = REPO_ROOT / "frontend" / "components" / "shared" / "TopBar.tsx"
DASHBOARD = REPO_ROOT / "frontend" / "app" / "developer" / "dashboard" / "page.tsx"
HOME = REPO_ROOT / "frontend" / "app" / "home" / "page.tsx"
CHATDOCK = REPO_ROOT / "frontend" / "components" / "chat" / "ChatDock.tsx"


class TestRegisterAccountContract(unittest.TestCase):
    def test_uses_frappe_user(self):
        src = AUTH.read_text(encoding="utf-8")
        self.assertIn('frappe.new_doc("User")', src)
        self.assertIn("@frappe.whitelist(allow_guest=True)", src)
        self.assertIn("@rate_limit(", src)
        self.assertIn('"AIOS Client Profile"', src)
        self.assertIn('"Pending Provisioning"', src)
        self.assertIn("send_welcome_email = 0", src)
        self.assertIn("no_welcome_mail", src)
        self.assertIn("aios_company_name", src)
        self.assertIn("aios_persona", src)
        self.assertIn("aios_tokens_used", src)
        self.assertNotIn('frappe.new_doc("AIOS Tenant")', src)


class TestDispatcherAuthContract(unittest.TestCase):
    def test_old_login_register_deprecated(self):
        src = DISPATCHER.read_text(encoding="utf-8")
        self.assertIn("/api/method/login", src)
        self.assertIn("/api/method/aios_v1.auth.register_account", src)
        self.assertNotIn('doc = frappe.new_doc("AIOS Tenant")', src)


class TestFrontendAuthContract(unittest.TestCase):
    def test_client_login_uses_frappe(self):
        src = LOGIN.read_text(encoding="utf-8")
        self.assertIn('"/method/login"', src)
        self.assertIn("apiMethod", src)
        self.assertIn('"/method/aios_v1.setup.get_session_context"', src)
        self.assertNotIn('"/auth/login"', src)
        self.assertNotIn('"/auth/register"', src)
        self.assertIn("Pendaftaran Diterima", src)

    def test_developer_login_uses_frappe(self):
        src = DEV_LOGIN.read_text(encoding="utf-8")
        self.assertIn('"/method/login"', src)
        self.assertIn("apiMethod", src)
        self.assertNotIn('"/auth/login"', src)

    def test_api_method_unwraps_message(self):
        src = (REPO_ROOT / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")
        self.assertIn("export async function apiMethod", src)
        self.assertIn("data.message", src)

    def test_logout_uses_frappe(self):
        for path in (TOPBAR, DASHBOARD):
            src = path.read_text(encoding="utf-8")
            self.assertIn('"/method/logout"', src)
            self.assertNotIn('"/auth/logout"', src)

    def test_home_has_no_legacy_gate(self):
        src = HOME.read_text(encoding="utf-8")
        self.assertNotIn('router.replace("/payment")', src)
        self.assertNotIn('router.replace("/onboarding")', src)

    def test_raw_posts_send_csrf(self):
        src = CHATDOCK.read_text(encoding="utf-8")
        self.assertIn("getCsrfToken()", src)
        self.assertIn("X-Frappe-CSRF-Token", src)


if __name__ == "__main__":
    unittest.main()
