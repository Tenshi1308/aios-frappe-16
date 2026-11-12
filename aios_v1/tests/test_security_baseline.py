"""Kontrak statis #1: gate endpoint, register anti-enumerasi, payment gate.

Fase 1: dispatcher kustom sudah digantikan 17 method `@frappe.whitelist()`
resmi. Kontrak ini kini mengunci modul-modul baru (bukan teks dispatcher),
termasuk perubahan status tamu 401 -> 403 (`frappe.PermissionError`).

Test ini tidak mengimpor frappe sehingga bisa jalan di CI tanpa site.
Bukti perilaku penuh tetap butuh `bench --site ... run-tests`.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API = REPO_ROOT / "aios_v1" / "api"
CHAT = API / "chat.py"
CONNECTOR = API / "connector.py"
MONITORING = API / "monitoring.py"
BRANCHES = API / "branches.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestEndpointAuthContract(unittest.TestCase):
    def test_all_methods_are_whitelisted_without_allow_guest(self):
        for path in (CHAT, CONNECTOR, MONITORING, BRANCHES):
            src = _source(path)
            self.assertIn("@frappe.whitelist(methods=", src, f"{path.name}: tidak ada whitelist")
            self.assertNotIn("allow_guest=True", src, f"{path.name}: allow_guest dilarang")

    def test_connector_routes_require_login(self):
        src = _source(CONNECTOR)
        for name in (
            "list_threads",
            "list_flags",
            "close_flag",
            "list_orders",
            "review_order",
            "create_link_token",
            "get_link_status",
            "unlink_telegram",
        ):
            self.assertIn(f"def {name}(", src, f"method {name} hilang")
        self.assertIn("frappe.session.user", src)
        self.assertIn("frappe.PermissionError", src)

    def test_dead_chatbot_routes_are_gone(self):
        for path in (CHAT, CONNECTOR):
            src = _source(path)
            self.assertNotIn("api/chatbot", src)
            self.assertNotIn("TELEGRAM_DISABLED", src)

    def test_parse_pdf_requires_session_and_size_limit(self):
        src = _source(CHAT)
        self.assertIn("def parse_pdf(", src)
        self.assertIn("_current_user()", src)
        self.assertIn("MAX_PDF_BYTES", src)

    def test_sse_stream_returns_response(self):
        """SSE-1: `stream_chat` mengembalikan `Response` ber-generator."""
        src = _source(CHAT)
        self.assertIn("def stream_chat(", src)
        self.assertIn('mimetype="text/event-stream', src)
        self.assertIn('res.headers["X-Accel-Buffering"] = "no"', src)
        self.assertIn("return res", src)
        self.assertNotIn("Test koneksi sukses", src)  # stub mock lama hilang

    def test_monitoring_uses_is_admin_helper(self):
        """System Manager dicabut; gate memakai `_is_admin` (diperketat)."""
        src = _source(MONITORING)
        self.assertIn("from aios_v1.permissions import _is_admin", src)
        self.assertIn("if not user or not _is_admin(user)", src)
        # Tidak ada lagi logika peran legacy (dulu `role == "DEVELOPER"`).
        self.assertNotIn('role") != "DEVELOPER"', src)
        self.assertNotIn('"System Manager" in roles', src)

    def test_stream_has_no_company_id(self):
        self.assertNotIn('sess.get("companyId")', _source(CHAT))


class TestRegisterAndPaymentContract(unittest.TestCase):
    def test_register_does_not_reveal_email_existence(self):
        src = _source(REPO_ROOT / "aios_v1" / "auth.py")
        self.assertNotIn('"Email sudah terdaftar"', src)
        self.assertNotIn("}, 409)", src)

    def test_payment_status_not_hardcoded_active(self):
        # Rute `/api/payment/status` (hardcoded ACTIVE) sudah DIHAPUS;
        # tidak ada modul payment baru.
        self.assertFalse((API / "payment.py").exists())
        self.assertFalse((API / "auth.py").exists())

    def test_removed_routes_have_no_module(self):
        """6 rute dihapus Ten: tidak ada modul auth/payment baru."""
        self.assertFalse((API / "payment.py").exists())
        self.assertFalse((API / "auth.py").exists())


class TestNoMachinePaths(unittest.TestCase):
    ALLOWED = ("check_db.py",)

    def test_no_machine_specific_paths(self):
        needles = ("/mnt" + "/g/", "/home/" + "samue/")
        offenders = []
        for path in (REPO_ROOT / "aios_v1").rglob("*.py"):
            if "__pycache__" in path.parts or path.name in self.ALLOWED:
                continue
            text = path.read_text(encoding="utf-8")
            for needle in needles:
                if needle in text:
                    offenders.append(f"{path.name}: {needle}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
