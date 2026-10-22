"""Kontrak statis #1: endpoint auth, register anti-enumeration, payment gate, path mesin.

Test ini tidak mengimpor frappe sehingga bisa jalan di CI tanpa site.
Bukti perilaku penuh tetap butuh `bench --site ... run-tests`.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DISPATCHER = REPO_ROOT / "aios_v1" / "api" / "dispatcher.py"


def _source() -> str:
    return DISPATCHER.read_text(encoding="utf-8")


class TestEndpointAuthContract(unittest.TestCase):
    def test_require_session_helper_exists(self):
        self.assertIn("def require_session(", _source())

    def test_chatbot_requires_admin_session(self):
        src = _source()
        idx = src.index('if path.startswith("api/chatbot")')
        self.assertIn('require_session(role="DEVELOPER")', src[idx : idx + 300])

    def test_parse_pdf_requires_session_and_size_limit(self):
        src = _source()
        idx = src.index('if path == "api/chat/parse-pdf"')
        self.assertIn("require_session()", src[idx : idx + 700])
        self.assertIn("MAX_PDF_BYTES", src)

    def test_session_supports_frappe_sid(self):
        self.assertIn("frappe.session.user", _source())

    def test_stream_has_no_company_id(self):
        self.assertNotIn('sess.get("companyId")', _source())


class TestRegisterAndPaymentContract(unittest.TestCase):
    def test_register_does_not_reveal_email_existence(self):
        src = _source()
        self.assertNotIn('"Email sudah terdaftar"', src)
        self.assertNotIn("}, 409)", src)

    def test_payment_status_not_hardcoded_active(self):
        src = _source()
        self.assertNotIn('"companyStatus": "ACTIVE"', src)
        self.assertNotIn('"payment": "ACTIVE"', src)

    def test_payment_checkout_not_fake_success(self):
        src = _source()
        self.assertNotIn('"Pembayaran berhasil', src)
        self.assertIn('"Pembayaran belum dikonfigurasi"', src)


class TestNoMachinePaths(unittest.TestCase):
    # check_db.py adalah skrip debug K3 yang dihapus di #2.
    ALLOWED = ("check_db.py",)

    def test_no_machine_specific_paths(self):
        offenders = []
        # Dipecah supaya file test ini sendiri tidak ikut terdeteksi.
        needles = ("/mnt" + "/g/", "/home/" + "samue/")
        for path in (REPO_ROOT / "aios_v1").rglob("*.py"):
            if path.name in self.ALLOWED or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in needles:
                if needle in text:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {needle}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
