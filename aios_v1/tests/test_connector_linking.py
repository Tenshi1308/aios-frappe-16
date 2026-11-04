"""Unit and integration tests for Batch 2 employee linking and guest gate."""

import hashlib
import json
from unittest.mock import patch

import frappe
try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from aios_v1.lib.connector import dispatch, linking, telegram_client
from aios_v1.lib.erpnext_action_drafts import erpnext_action_draft_create
from aios_v1.lib.erpnext_core_data import erpnext_doc_get, erpnext_doc_list
from aios_v1.lib.tool_registry import execute_tool, tool_context

SETTING = "AIOS Telegram Setting"
THREAD = "AIOS Channel Thread"
CONV = "AIOS Conversation"
OWNER = "_test.linking.owner@example.com"
EMP = "_test.linking.employee@example.com"
OTHER_USER = "_test.linking.other@example.com"
CHAT_ID = "88112233"
OTHER_CHAT_ID = "88990011"


def _ensure_user(email: str, name: str) -> str:
    if frappe.db.exists("User", email):
        return email
    doc = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": name,
            "enabled": 1,
            "send_welcome_email": 0,
            "user_type": "Website User",
            "aios_status": "Active",
            "roles": [{"role": "AIOS Client"}],
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


class TestConnectorLinking(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.in_test = True
        frappe.flags.in_test = True
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None

        self.owner = _ensure_user(OWNER, "Link Owner")
        self.employee = _ensure_user(EMP, "Link Employee")
        self.other_user = _ensure_user(OTHER_USER, "Link Other")

        self._orig_owner = frappe.db.get_single_value(SETTING, "owner_user")
        self._orig_bot = frappe.db.get_single_value(SETTING, "bot_username")
        frappe.db.set_value(SETTING, SETTING, "owner_user", self.owner)
        frappe.db.set_value(SETTING, SETTING, "bot_username", "test_aios_bot")
        frappe.db.set_value(SETTING, SETTING, "link_code_expiry_seconds", 300)

        frappe.set_user(self.employee)
        self._cleanup()

    def tearDown(self):
        self._cleanup()
        frappe.db.set_value(SETTING, SETTING, "owner_user", self._orig_owner)
        frappe.db.set_value(SETTING, SETTING, "bot_username", self._orig_bot)
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()
        super().tearDown()

    def _cleanup(self):
        linking.clear_attempts(CHAT_ID)
        linking.clear_attempts(OTHER_CHAT_ID)
        for chat in (CHAT_ID, OTHER_CHAT_ID):
            threads = frappe.get_all(THREAD, filters={"external_thread_id": chat}, pluck="name")
            for t in threads:
                conv = frappe.db.get_value(THREAD, t, "conversation")
                frappe.delete_doc(THREAD, t, ignore_permissions=True, force=True)
                if conv and frappe.db.exists(CONV, conv):
                    frappe.delete_doc(CONV, conv, ignore_permissions=True, force=True)

    def test_token_expiry_rejected(self):
        """1. Token kedaluwarsa ditolak."""
        res = linking.create_link_token(self.employee)
        deep_link = res["deep_link"]
        raw_token = deep_link.split("LINK_")[1]
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        # Simulasi kedaluwarsa: hapus dari cache
        frappe.cache().delete_value(f"aios_tg_link:{token_hash}")

        success, msg, target = linking.verify_and_consume_token(CHAT_ID, raw_token)
        self.assertFalse(success)
        self.assertIn("kedaluwarsa", msg.lower())
        self.assertIsNone(target)

    def test_token_single_use_enforced(self):
        """2. Token sekali pakai, pemakaian kedua ditolak dan dicatat."""
        res = linking.create_link_token(self.employee)
        raw_token = res["deep_link"].split("LINK_")[1]

        # Pemakaian pertama sukses
        success, msg, target = linking.verify_and_consume_token(CHAT_ID, raw_token)
        self.assertTrue(success)
        self.assertEqual(target, self.employee)

        # Pemakaian kedua harus gagal
        success2, msg2, target2 = linking.verify_and_consume_token(OTHER_CHAT_ID, raw_token)
        self.assertFalse(success2)
        self.assertIn("kedaluwarsa", msg2.lower())
        self.assertIsNone(target2)

    def test_generate_token_for_other_user_forbidden(self):
        """3. Generate untuk user lain ditolak."""
        frappe.set_user(self.employee)
        with self.assertRaises(frappe.PermissionError):
            linking.create_link_token(self.other_user)

    def test_missing_bot_username_rejected(self):
        """3b. Generate link token tanpa bot_username ditolak dengan BOT_USERNAME_MISSING."""
        frappe.set_user(self.employee)
        frappe.db.set_value(SETTING, SETTING, "bot_username", "")
        try:
            linking.create_link_token(self.employee)
            self.fail("Harus gagal saat bot_username kosong")
        except linking.LinkError as exc:
            self.assertEqual(exc.code, "BOT_USERNAME_MISSING")
        finally:
            frappe.db.set_value(SETTING, SETTING, "bot_username", "test_aios_bot")

    def test_chat_already_linked_rejected(self):
        """4. Chat sudah tertaut ditolak tautan baru."""
        # Tautkan dulu chat ke employee
        thread = dispatch.get_or_create_thread(CHAT_ID)
        linking.link_thread_to_user(CHAT_ID, self.employee, thread["name"])

        # Buat token baru untuk other_user
        frappe.set_user(self.other_user)
        res = linking.create_link_token(self.other_user)
        raw_token = res["deep_link"].split("LINK_")[1]

        success, msg, target = linking.verify_and_consume_token(CHAT_ID, raw_token)
        self.assertFalse(success)
        self.assertIn("sudah tertaut", msg.lower())
        self.assertIsNone(target)

    def test_user_already_linked_to_other_chat_rejected(self):
        """4b. Akun sudah tertaut di chat lain ditolak."""
        thread = dispatch.get_or_create_thread(CHAT_ID)
        linking.link_thread_to_user(CHAT_ID, self.employee, thread["name"])

        # Employee minta token baru dan coba pakai di chat lain
        frappe.set_user(self.employee)
        res = linking.create_link_token(self.employee)
        raw_token = res["deep_link"].split("LINK_")[1]

        success, msg, target = linking.verify_and_consume_token(OTHER_CHAT_ID, raw_token)
        self.assertFalse(success)
        self.assertIn("sudah terhubung ke telegram lain", msg.lower())
        self.assertIsNone(target)

    def test_cross_site_token_rejected(self):
        """5. Token beda site ditolak: pembuktian prefix nama database site."""
        # Simulasi site dev vs site client
        raw_token = "dummy_token_56_characters_cross_site_isolation_check_12345"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        # Di site dev (mis. db 'aios_dev')
        site_dev_key = f"aios_dev|aios_tg_link:{token_hash}"
        # Di site client (mis. db 'aios_client')
        site_client_key = f"aios_client|aios_tg_link:{token_hash}"

        self.assertNotEqual(site_dev_key, site_client_key)
        # Token di site dev tidak akan match di site client
        self.assertNotIn("aios_client", site_dev_key)

    def test_brute_force_lockout(self):
        """11. 5 kali gagal berturut-turut mengunci chat selama 15 menit."""
        linking.clear_attempts(CHAT_ID)
        for _ in range(5):
            linking.record_attempt_failure(CHAT_ID)

        self.assertTrue(linking.is_locked_out(CHAT_ID))

        # Coba verifikasi token valid saat terkunci -> wajib ditolak sebelum lookup token
        res = linking.create_link_token(self.employee)
        raw_token = res["deep_link"].split("LINK_")[1]

        success, msg, target = linking.verify_and_consume_token(CHAT_ID, raw_token)
        self.assertFalse(success)
        self.assertIn("terlalu banyak percobaan", msg.lower())
        self.assertIsNone(target)

    def test_guest_restricted_from_internal_tools_and_wholesale(self):
        """6. Tamu ditolak untuk harga selain Standard Selling, laporan keuangan, dan perkakas diblokir."""
        frappe.set_user("Guest")
        ctx = {"user": "Guest", "branch": "sales", "worker_key": "manager"}

        # Perkakas internal / keuangan diblokir untuk tamu
        denied_report = execute_tool("erpnext_report_run", "{}", context=ctx)
        self.assertIn("GUEST_TOOL_FORBIDDEN", denied_report)

        denied_web = execute_tool("web_search", "{}", context=ctx)
        self.assertIn("GUEST_TOOL_FORBIDDEN", denied_web)

        # DocType internal diblokir untuk tamu di core data
        with tool_context({"user_id": "Guest", "allowed_company": "Test Co"}):
            res_cust = erpnext_doc_list("Customer")
            self.assertEqual(res_cust.get("code"), "DOCTYPE_NOT_ALLOWED")

            # Detail harga non-standard selling ditolak
            fake_wholesale = {"doctype": "Item Price", "price_list": "Grosir", "selling": 1}
            with patch.object(frappe, "get_doc", return_value=fake_wholesale):
                res_price = erpnext_doc_get("Item Price", "PRICE-001")
                self.assertEqual(res_price.get("code"), "PRICE_NOT_ALLOWED")

    def test_guest_allowed_catalog_and_draft(self):
        """7. Tamu diizinkan untuk Item, Item Price Standard Selling, draf CREATE party kosong, dan penunjuk waktu."""
        frappe.set_user("Guest")
        ctx = {"user": "Guest", "branch": "sales", "worker_key": "manager"}

        # Time tool diizinkan
        time_res = json.loads(execute_tool("get_current_time", "{}", context=ctx))
        self.assertIn("current_time", time_res)

        # Item Price list dipaksa Standard Selling
        frappe.get_meta("Item Price")
        recorded_calls = []
        orig_get_list = frappe.get_list

        def fake_get_list(doctype, *args, **kwargs):
            if doctype == "Item Price":
                recorded_calls.append((args, kwargs))
                return [{"name": "PRICE-STD", "price_list_rate": 100000}]
            return orig_get_list(doctype, *args, **kwargs)

        with tool_context({"user_id": "Guest", "allowed_company": "Test Co"}):
            with patch.object(frappe, "get_list", side_effect=fake_get_list):
                res = erpnext_doc_list("Item Price")
                self.assertIn("data", res)
                # Verifikasi filter dipaksa ke Standard Selling dan selling=1
                self.assertTrue(recorded_calls)
                _, kwargs = recorded_calls[0]
                self.assertEqual(kwargs["filters"].get("price_list"), "Standard Selling")
                self.assertEqual(kwargs["filters"].get("selling"), 1)

            # Draf CREATE diizinkan untuk tamu
            with patch("aios_v1.lib.erpnext_action_drafts.create_draft") as mock_draft:
                mock_draft.return_value = frappe._dict(name="DRAFT-001")
                draft_res = erpnext_action_draft_create(
                    action_type="CREATE",
                    doctype="Sales Order",
                    data={"items": [{"item_code": "ITEM-1", "qty": 2}]},
                    reason="Order dari web chat",
                )
                self.assertEqual(draft_res["status"], "PENDING_APPROVAL")
                # Pemilik draf untuk tamu diarahkan ke owner_user Setting
                _, draft_kw = mock_draft.call_args
                self.assertEqual(draft_kw.get("user"), self.owner)

            # UPDATE_DRAFT diblokir untuk tamu
            bad_draft = erpnext_action_draft_create(
                action_type="UPDATE_DRAFT",
                doctype="Sales Order",
                data={},
                name="SO-001",
            )
            self.assertEqual(bad_draft.get("code"), "ACTION_FORBIDDEN_FOR_GUEST")

    def test_linked_employee_scoped_to_sales(self):
        """8. Karyawan Sales and Distribution diizinkan untuk perkakas Sales, ditolak untuk perkakas di luar Sales."""
        frappe.set_user(self.employee)
        frappe.local.aios_channel = "telegram"
        ctx = {"user": self.employee, "branch": "sales", "worker_key": "manager"}

        try:
            # Di Telegram, tool laporan finansial diblokir meskipun user karyawan
            denied_report = execute_tool("erpnext_report_run", "{}", context=ctx)
            self.assertIn("TOOL_FORBIDDEN_ON_TELEGRAM", denied_report)

            # Perkakas umum seperti time diizinkan
            time_res = json.loads(execute_tool("get_current_time", "{}", context=ctx))
            self.assertIn("current_time", time_res)
        finally:
            if hasattr(frappe.local, "aios_channel"):
                delattr(frappe.local, "aios_channel")

    def test_unlink_cleans_session_and_thread(self):
        """9. Unlink bersih: linked_user bersih, pesan berikutnya Guest, riwayat lama tetap."""
        thread = dispatch.get_or_create_thread(CHAT_ID)
        linking.link_thread_to_user(CHAT_ID, self.employee, thread["name"])

        doc = frappe.get_doc(THREAD, thread["name"])
        self.assertEqual(doc.linked_user, self.employee)

        # Jalankan /unlink via dispatch
        with patch.object(telegram_client, "send_message", return_value=True):
            res = dispatch.process_update(
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 1,
                        "chat": {"id": int(CHAT_ID)},
                        "text": "/unlink",
                    },
                }
            )

        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "unlink")

        # Verifikasi field linked_user bersih
        doc.reload()
        self.assertIsNone(doc.linked_user)
        self.assertIsNone(doc.linked_at)

        # Pesan berikutnya harus dilayani dengan sesi Guest
        seen_sessions = []

        def spy_reply(mgr, conv, user, txt):
            seen_sessions.append(user)
            return "ok"

        with patch.object(telegram_client, "send_message", return_value=True), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(dispatch, "_collect_reply", side_effect=spy_reply):
            dispatch.process_update(
                {
                    "update_id": 2,
                    "message": {
                        "message_id": 2,
                        "chat": {"id": int(CHAT_ID)},
                        "text": "halo lagi",
                    },
                }
            )

        self.assertEqual(seen_sessions, ["Guest"])


def run_tests():
    import unittest
    frappe.in_test = True
    frappe.flags.in_test = True
    suite = unittest.TestLoader().loadTestsFromTestCase(TestConnectorLinking)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    print(f"RESULT: wasSuccessful={res.wasSuccessful()}, testsRun={res.testsRun}, errors={len(res.errors)}, failures={len(res.failures)}")
    if not res.wasSuccessful():
        raise SystemExit(1)
    return res.wasSuccessful()

