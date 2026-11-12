"""Fase 1 — regresi 401 Peringatan Kanal setelah klik "Sudah Bayar" (D3).

Urutan yang direproduksi (bukan sekadar "sid valid -> 200", karena itu lolos
di kode lama lewat fallback `frappe.session.user`):
    1. Staf login: sesi `sid` berupa hash + `session.data` terisi.
    2. Klik "Sudah Bayar" -> `confirm_draft_cash_payment` menaikkan hak ke
       Administrator lewat `frappe.set_user("Administrator")` dan memulihkan
       lewat `frappe.set_user(prev_user)` di `finally`.
    3. Frappe menjadwalkan `Session.update()` di after-response
       (`frappe/app.py:471-472`); `update` menulis `self.data` ke Redis
       `session:<sid>` (`frappe/sessions.py:445`). `self.data` ADALAH objek
       yang sama dengan `frappe.local.session` (`frappe/auth.py:239`,
       `frappe/sessions.py:233`), jadi state itulah yang dipersist.
    4. Request berikutnya (refresh F5 / polling Peringatan Kanal) me-resume
       dari cookie `sid` yang sama.

Bug lama: `frappe.set_user` menimpa `session.sid` dengan *username* dan
mengosongkan `session.data` (`frappe/__init__.py:386-392`). `set_user(prev_user)`
TIDAK memulihkannya -> yang dipersist adalah sesi rusak, polling berikutnya
tidak me-resume staf yang sama -> dispatcher kustom menjawab 401.

KENAPA TEST INI GAGAL DI KODE LAMA: `test_payment_elevation_preserves_session_state`
dan `test_polling_after_payment_resumes_same_sid` meng-assert `sid` masih hash
dan `data.user` masih ada. Di kode lama keduanya rusak.

Catatan disiplin (AGENTS.md §6): fixture sesi dibangun in-memory menyerupai
`Session.resume()` (`frappe/sessions.py:325`), tanpa membuat/mengubah data di
DB. `Session.update` dipatch HANYA untuk menangkap `self.data` (input persist) —
kode Frappe yang menulis ke Redis tidak diuji ulang, yang diuji adalah state
yang dikirimkan ke sana. Komit DB dijadikan no-op; `tearDown` rollback.

Jalankan (site + DB):
    bench --site <site> run-tests --app aios_v1 \
        --module aios_v1.tests.test_session_payment_regression
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore

STAFF = "_test.session.staff@example.com"


def _install_session(user: str) -> str:
    """Pasang `frappe.local.session` persis seperti hasil `Session.resume()`.

    Bentuknya mengikuti `frappe/sessions.py:325`:
        {"data": <sessiondata>, "user": <user>, "sid": <hash>}
    Tidak menyentuh DB dan tidak membutuhkan User doc nyata.
    """
    sid = frappe.generate_hash()
    frappe.local.request = Request(
        EnvironBuilder(path="/api/method/x", method="POST").get_environ()
    )
    frappe.local.form_dict = frappe._dict()
    frappe.local.request_ip = "127.0.0.1"
    frappe.local.session = frappe._dict(
        {
            "sid": sid,
            "user": user,
            "data": frappe._dict(
                {
                    "user": user,
                    "csrf_token": "test-csrf-token",
                    "user_type": "System User",
                    "full_name": "Test Staff",
                    "last_updated": frappe.utils.now(),
                    "session_expiry": "240:00:00",
                }
            ),
        }
    )
    # `Session.update` adalah bound method dari objek yang `data`-nya sama
    # dengan `frappe.local.session` (frappe/auth.py:239). Pakai instance
    # `Session` nyata (tanpa __init__, agar tidak menyentuh DB) supaya patch
    # `frappe.sessions.Session.update` terikat sebagai bound method.
    from frappe.sessions import Session

    holder = object.__new__(Session)
    holder.data = frappe.local.session
    holder.sid = sid
    holder._update_in_cache = False
    holder.time_diff = None
    frappe.local.session_obj = holder
    return sid


class TestSessionPaymentRegression(IntegrationTestCase):
    """Regresi: elevasi hak payment tidak boleh merusak sesi login."""

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        self._orig_request = getattr(frappe.local, "request", None)
        self._orig_session = getattr(frappe.local, "session", None)
        self._orig_session_obj = getattr(frappe.local, "session_obj", None)
        self._orig_form_dict = getattr(frappe.local, "form_dict", None)
        self._orig_request_ip = getattr(frappe.local, "request_ip", None)
        # Jangan menyentuh DB nyata.
        frappe.db.commit = lambda *a, **k: None
        self.persisted = {}
        self.addCleanup(self._restore)

    def _restore(self):
        frappe.db.commit = self._orig_commit
        frappe.local.request = self._orig_request
        frappe.local.session = self._orig_session
        frappe.local.session_obj = self._orig_session_obj
        frappe.local.form_dict = self._orig_form_dict
        frappe.local.request_ip = self._orig_request_ip
        frappe.db.rollback()

    def _run_payment_elevation(self):
        """Jalankan `confirm_draft_cash_payment` + simulasi persist sesi.

        Dependensi ERPNext di-mock agar tidak membuat Payment Entry sungguhan,
        tetapi blok `set_user` / `get_payment_entry` / `finally` TETAP dijalankan
        apa adanya (itulah yang diuji).
        """
        fake_pe = MagicMock()
        fake_pe.name = "ACC-PAY-TEST-00001"
        fake_pe.paid_amount = 100000

        captured = self.persisted

        def _capture_update(session_obj, force=False):
            # `Session.update` menulis `self.data` ke cache (sessions.py:445)
            # dan `self.data["sid"]` ke DB (sessions.py:433). Tangkap keduanya.
            # Nama argumen sengaja bukan `self` agar closure `self` (TestCase)
            # tidak tertimpa saat fungsi ini dipakai sebagai bound method.
            captured["value"] = frappe._dict(session_obj.data)
            captured["sid"] = session_obj.sid
            return True

        with (
            patch("aios_v1.lib.draft_manager._lock_draft") as lock,
            patch("aios_v1.lib.draft_manager._assert_draft_owner"),
            patch("aios_v1.lib.draft_manager._site_company", return_value="Test Co"),
            patch("aios_v1.lib.draft_manager._send_proactive_guest_notification"),
            patch("aios_v1.lib.draft_manager._format_currency_amount", return_value="Rp 100.000"),
            patch(
                "erpnext.accounts.doctype.journal_entry.journal_entry.get_default_bank_cash_account",
                return_value=frappe._dict({"account": "Cash - TC"}),
            ),
            patch(
                "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
                return_value=fake_pe,
            ),
            patch.object(frappe.db, "exists", return_value=True),
            patch.object(frappe.db, "savepoint", return_value=None),
            patch("frappe.get_all", return_value=[]),
            patch("frappe.sessions.Session.update", new=_capture_update),
        ):
            draft = frappe._dict()
            draft.status = "EXECUTED"
            draft.type = "CREATE"
            draft.payload = json.dumps(
                {
                    "doctype": "Sales Order",
                    "data": {},
                    "result": {"name": "SO-TEST-00001", "currency": "IDR"},
                }
            )
            draft.save = lambda *a, **k: None
            lock.return_value = draft

            from aios_v1.lib.draft_manager import confirm_draft_cash_payment

            result = confirm_draft_cash_payment("DRAFT-TEST-00001")

            # after-response: sync_database menjadwalkan session.update
            # (frappe/app.py:471-472). Jalankan pada objek yang SAMA dengan
            # frappe.local.session.
            frappe.local.session_obj.update(force=True)

        return result

    # ------------------------------------------------------------------
    def test_payment_elevation_preserves_session_state(self):
        """UTAMA: payment -> state sesi (sid + data) harus tetap utuh.

        KODE LAMA GAGAL di sini: setelah `set_user("Administrator")` +
        `set_user(prev_user)`, `frappe.session.sid == STAFF` (username) dan
        `frappe.session.data == {}`.
        """
        sid = _install_session(STAFF)
        self.assertTrue(sid and sid != STAFF, "sid harus hash, bukan username")
        self.assertEqual(frappe.session.user, STAFF)
        self.assertEqual(frappe.session.sid, sid)

        result = self._run_payment_elevation()

        # Payment Entry tetap terbentuk (logika bisnis tidak berubah).
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["payment_entry"], "ACC-PAY-TEST-00001")

        # (1) Sesi live di request yang sama tidak rusak.
        self.assertEqual(frappe.session.user, STAFF, "user sesi berubah")
        self.assertEqual(
            frappe.session.sid, sid, "sid rusak: set_user menimpa dengan username"
        )
        self.assertEqual(
            frappe.session.data.get("user"),
            STAFF,
            "data sesi kosong: set_user menghapus session.data",
        )
        self.assertEqual(
            frappe.session.data.get("csrf_token"),
            "test-csrf-token",
            "csrf_token hilang: POST berikutnya akan ditolak CSRF",
        )

    def test_polling_after_payment_resumes_same_sid(self):
        """URUTAN: payment -> persist -> polling me-resume sid yang SAMA.

        Mensimulasikan refresh F5 / polling Peringatan Kanal. Yang dipersist
        `Session.update` harus tetap memetakan ke sid hash asli dengan user
        staf; di kode lama keduanya rusak sehingga polling tidak me-resume
        sesi staf (-> Guest -> 401).
        """
        sid = _install_session(STAFF)
        result = self._run_payment_elevation()
        self.assertEqual(result["status"], "success")

        # Apa yang ditulis ke Redis `session:<sid>` (sessions.py:445).
        self.assertIn("value", self.persisted, "Session.update tidak dijalankan")
        persisted = self.persisted["value"]
        self.assertEqual(
            persisted["sid"], sid, "sid yang dipersist berubah -> cookie lama tak cocok"
        )
        self.assertEqual(persisted["user"], STAFF, "user yang dipersist bukan staf")
        self.assertEqual(
            persisted["data"].get("user"),
            STAFF,
            "sessiondata kosong -> resume jatuh ke Guest",
        )

        # Request berikutnya memakai cookie sid yang sama (same-origin).
        builder = EnvironBuilder(path="/api/connector/flags", method="GET")
        builder.headers["Cookie"] = f"sid={sid}"
        frappe.local.request = Request(builder.get_environ())

        # Pasang ulang session dari hasil persist, lalu cek gate connector.
        frappe.local.session = persisted
        from aios_v1.lib.connector.views import _require_user

        self.assertEqual(
            _require_user(frappe.session.user),
            STAFF,
            "polling connector me-resume sesi bukan staf -> 401 (bug D3)",
        )

    def test_guest_still_denied(self):
        """Gate tidak longgar: tamu tetap ditolak oleh `_require_user`."""
        from aios_v1.lib.connector.views import _require_user
        from aios_v1.lib.workspace import WorkspaceError

        _install_session("Guest")
        with self.assertRaises(WorkspaceError) as ctx:
            _require_user(frappe.session.user)
        self.assertEqual(ctx.exception.status, 401)


if __name__ == "__main__":
    unittest.main()
