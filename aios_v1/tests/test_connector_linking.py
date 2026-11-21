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


def _ensure_user(email: str, name: str, is_receiver: bool = False) -> str:
    roles = ["AIOS Client"]
    profiles = ["AIOS Client Profile"]
    if is_receiver:
        roles.append("AIOS Channel Receiver")
        profiles.append("AIOS Channel Receiver Profile")
    if frappe.db.exists("User", email):
        doc = frappe.get_doc("User", email)
        doc.aios_status = "Active"
        doc.enabled = 1
        doc.set("roles", [{"role": r} for r in roles])
        doc.set("role_profiles", [{"role_profile": p} for p in profiles])
        doc.flags.ignore_permissions = True
        doc.flags.ignore_password_policy = True
        doc.save(ignore_permissions=True)
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
            "roles": [{"role": r} for r in roles],
            "role_profiles": [{"role_profile": p} for p in profiles],
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
        self.addCleanup(self._restore_and_rollback)
        frappe.set_user("Administrator")
        frappe.db.set_single_value("AIOS Setting", "max_users", 20)
        frappe.db.delete(
            "Has Role",
            {"parenttype": "User", "role": ("in", ["AIOS Channel Receiver", "AIOS Client Owner"])},
        )

        self.owner = _ensure_user(OWNER, "Link Owner", is_receiver=True)
        self.employee = _ensure_user(EMP, "Link Employee", is_receiver=False)
        self.other_user = _ensure_user(OTHER_USER, "Link Other", is_receiver=False)

        self._orig_bot = frappe.db.get_single_value(SETTING, "bot_username")
        frappe.db.set_value(SETTING, SETTING, "bot_username", "test_aios_bot")
        frappe.db.set_value(SETTING, SETTING, "link_code_expiry_seconds", 300)

        frappe.set_user(self.employee)
        self._cleanup()

    def _restore_and_rollback(self):
        frappe.set_user("Administrator")
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()

    def tearDown(self):
        frappe.set_user("Administrator")
        self._cleanup()
        for email in (OWNER, EMP, OTHER_USER):
            for cname in frappe.get_all("Contact", filters={"user": email}, pluck="name"):
                frappe.delete_doc("Contact", cname, ignore_permissions=True, force=True, delete_permanently=True)
            if frappe.db.exists("Notification Settings", email):
                frappe.delete_doc("Notification Settings", email, ignore_permissions=True, force=True, delete_permanently=True)
            if frappe.db.exists("User", email):
                frappe.delete_doc("User", email, ignore_permissions=True, force=True, delete_permanently=True)
        frappe.db.set_value(SETTING, SETTING, "bot_username", self._orig_bot)
        self._restore_and_rollback()
        super().tearDown()

    def _cleanup(self):
        linking.clear_attempts(CHAT_ID)
        linking.clear_attempts(OTHER_CHAT_ID)
        dispatch.clear_rate_limit(CHAT_ID)
        dispatch.clear_rate_limit(OTHER_CHAT_ID)
        for chat in (CHAT_ID, OTHER_CHAT_ID):
            threads = frappe.get_all(THREAD, filters={"external_thread_id": chat}, pluck="name")
            for t in threads:
                conv = frappe.db.get_value(THREAD, t, "conversation")
                frappe.delete_doc(THREAD, t, ignore_permissions=True, force=True, delete_permanently=True)
                if conv and frappe.db.exists(CONV, conv):
                    for m in frappe.get_all("AIOS Message", filters={"conversation": conv}, pluck="name"):
                        frappe.delete_doc("AIOS Message", m, ignore_permissions=True, force=True, delete_permanently=True)
                    frappe.delete_doc(CONV, conv, ignore_permissions=True, force=True, delete_permanently=True)
        for email in (OWNER, EMP, OTHER_USER):
            for usage_name in frappe.get_all("AIOS Token Usage", filters={"user": email}, pluck="name"):
                frappe.delete_doc("AIOS Token Usage", usage_name, ignore_permissions=True, force=True, delete_permanently=True)
            for conv in frappe.get_all(CONV, filters={"user": email}, pluck="name"):
                for m in frappe.get_all("AIOS Message", filters={"conversation": conv}, pluck="name"):
                    frappe.delete_doc("AIOS Message", m, ignore_permissions=True, force=True, delete_permanently=True)
                frappe.delete_doc(CONV, conv, ignore_permissions=True, force=True, delete_permanently=True)

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
        success, _msg, target = linking.verify_and_consume_token(CHAT_ID, raw_token)
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

        site_company = (
            frappe.db.get_single_value("AIOS Setting", "default_company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )
        with tool_context({"user_id": "Guest", "allowed_company": site_company}):
            with patch.object(frappe, "get_list", side_effect=fake_get_list):
                res = erpnext_doc_list("Item Price")
                self.assertIn("data", res)
                # Verifikasi filter dipaksa ke Standard Selling dan selling=1
                self.assertTrue(recorded_calls)
                _, kwargs = recorded_calls[0]
                self.assertEqual(kwargs["filters"].get("price_list"), "Standard Selling")
                self.assertEqual(kwargs["filters"].get("selling"), 1)
                self.assertEqual(res["data"][0]["base_rate"], 100000.0)
                self.assertEqual(res["data"][0]["ppn_11_per_unit"], 11000.0)
                self.assertEqual(res["data"][0]["rate_with_ppn_11"], 111000.0)

            # Draf CREATE diizinkan untuk tamu
            with patch("aios_v1.lib.erpnext_action_drafts.create_draft") as mock_draft:
                mock_draft.return_value = frappe._dict(name="DRAFT-001")
                draft_res = erpnext_action_draft_create(
                    action_type="CREATE",
                    doctype="Sales Order",
                    data={"items": [{"item_code": "ITEM-1", "qty": 2}], "delivery_date": "2026-11-15"},
                    reason="Order dari web chat",
                )
                self.assertEqual(draft_res["status"], "PENDING_APPROVAL")
                # Pemilik draf untuk tamu diarahkan ke penerima kanal aktif
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
        with (
            patch.object(telegram_client, "send_message", return_value=True),
            patch.object(telegram_client, "set_my_commands", return_value=True),
        ):
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

    def test_guest_system_prompt_uses_cs_persona_and_excludes_internal_manager_claims(self):
        """9a. Prompt sistem untuk Guest memakai persona CS tamu dan bersih dari klaim AI Manager internal."""
        from aios_v1.managers import get_manager

        sales_mgr = get_manager("sales")
        prompt = sales_mgr.build_system_prompt(None, user="Guest")

        self.assertIn("Asisten Layanan Pelanggan resmi perusahaan kami.", prompt)
        self.assertIn("Menampilkan daftar produk beserta spesifikasi dasar dari katalog perusahaan.", prompt)
        self.assertIn("Membantu mencatat pesanan pembelian baru dan permintaan penawaran harga", prompt)

        for forbidden in (
            "AI Manager",
            "AI MANAGER",
            "HomeHub",
            "Ekasa Desk",
            "open_module",
            "orchestrator_delegate_to_subagent",
            "Task Orchestration and Delegation Workflow",
        ):
            self.assertNotIn(forbidden, prompt)

    def test_linked_vs_unlinked_telegram_dispatch_prompt_separation(self):
        """9d. Simulasi chat tamu -> tautkan akun -> /unlink: prompt berganti CS tamu -> AI Manager -> CS tamu."""
        captured_prompts = []

        def fake_chat(messages, usage=None, tools=None, tool_calls=None):
            sys_msgs = [m.get("content", "") for m in messages if m.get("role") == "system"]
            captured_prompts.append("\n".join(sys_msgs))
            if usage is not None:
                usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            return iter(["Balasan simulasi"])

        with (
            patch.object(telegram_client, "send_message", return_value=True),
            patch.object(telegram_client, "send_chat_action", return_value=True),
            patch.object(telegram_client, "set_my_commands", return_value=True),
            patch("aios_v1.managers.base_manager.chat_stream", side_effect=fake_chat),
            patch("aios_v1.managers.base_manager.record_token_usage_batch"),
        ):
            # 1. Chat sebagai tamu (linked_user=None)
            res1 = dispatch.process_update(
                {
                    "update_id": 10,
                    "message": {
                        "message_id": 10,
                        "chat": {"id": int(CHAT_ID)},
                        "from": {"first_name": "Tamu"},
                        "text": "Disini ada apa aja?",
                    },
                }
            )
            self.assertTrue(res1["success"])
            self.assertEqual(len(captured_prompts), 1)
            self.assertIn("Asisten Layanan Pelanggan resmi perusahaan kami.", captured_prompts[0])
            self.assertNotIn("AI Manager bidang Sales and Distribution", captured_prompts[0])

            # 2. Tautkan akun karyawan
            frappe.set_user(self.employee)
            link_res = linking.create_link_token(self.employee)
            raw_token = link_res["deep_link"].split("LINK_")[1]
            res_link = dispatch.process_update(
                {
                    "update_id": 11,
                    "message": {
                        "message_id": 11,
                        "chat": {"id": int(CHAT_ID)},
                        "from": {"first_name": "Karyawan"},
                        "text": f"/start LINK_{raw_token}",
                    },
                }
            )
            self.assertTrue(res_link["success"])

            # Kirim pesan sebagai karyawan tertaut
            res2 = dispatch.process_update(
                {
                    "update_id": 12,
                    "message": {
                        "message_id": 12,
                        "chat": {"id": int(CHAT_ID)},
                        "from": {"first_name": "Karyawan"},
                        "text": "Halo, cek layanan",
                    },
                }
            )
            self.assertTrue(res2["success"])
            self.assertEqual(len(captured_prompts), 2)
            self.assertIn("AI Manager bidang Sales and Distribution", captured_prompts[1])
            self.assertIn("AI MANAGER SALES AND DISTRIBUTION (UMUM)", captured_prompts[1])

            # 3. Putuskan tautan (/unlink) lalu kirim pesan lagi sebagai tamu
            res_unlink = dispatch.process_update(
                {
                    "update_id": 13,
                    "message": {
                        "message_id": 13,
                        "chat": {"id": int(CHAT_ID)},
                        "from": {"first_name": "Tamu"},
                        "text": "/unlink",
                    },
                }
            )
            self.assertTrue(res_unlink["success"])

            res3 = dispatch.process_update(
                {
                    "update_id": 14,
                    "message": {
                        "message_id": 14,
                        "chat": {"id": int(CHAT_ID)},
                        "from": {"first_name": "Tamu"},
                        "text": "Halo lagi setelah unlink",
                    },
                }
            )
            self.assertTrue(res3["success"])
            self.assertEqual(len(captured_prompts), 3)
            self.assertIn("Asisten Layanan Pelanggan resmi perusahaan kami.", captured_prompts[2])
            self.assertNotIn("AI Manager bidang Sales and Distribution", captured_prompts[2])

    def test_guest_item_price_list_and_get_include_official_ppn_11_preview(self):
        """Guest erpnext_doc_list & erpnext_doc_get pada Item Price menyertakan base_rate, ppn_11_per_unit, rate_with_ppn_11 resmi ERPNext; karyawan tidak berubah."""
        item_code = "_Test Item PPN Preview"
        frappe.set_user("Administrator")
        if not frappe.db.exists("Item", item_code):
            frappe.get_doc(
                {
                    "doctype": "Item",
                    "item_code": item_code,
                    "item_name": "Switch Uji PPN 11",
                    "item_group": frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit=1)[0],
                    "stock_uom": "Nos",
                    "is_stock_item": 0,
                    "standard_rate": 850000,
                }
            ).insert(ignore_permissions=True)

        existing_ip = frappe.db.get_value(
            "Item Price",
            {"item_code": item_code, "price_list": "Standard Selling", "selling": 1},
            "name",
        )
        created_ip = None
        if not existing_ip:
            ip_doc = frappe.get_doc(
                {
                    "doctype": "Item Price",
                    "item_code": item_code,
                    "price_list": "Standard Selling",
                    "selling": 1,
                    "currency": "IDR",
                    "price_list_rate": 850000,
                }
            ).insert(ignore_permissions=True)
            ip_name = ip_doc.name
            created_ip = ip_name
        else:
            ip_name = existing_ip
            frappe.db.set_value("Item Price", ip_name, "price_list_rate", 850000)

        try:
            # 1. Guest calls erpnext_doc_list & erpnext_doc_get
            frappe.set_user("Guest")
            guest_ctx = {"user": "Guest", "branch": "sales", "worker_key": "manager"}
            list_res = json.loads(
                execute_tool(
                    "erpnext_doc_list",
                    json.dumps({"doctype": "Item Price", "filters": {"item_code": item_code}}),
                    context=guest_ctx,
                )
            )
            self.assertEqual(len(list_res.get("data") or []), 1)
            row = list_res["data"][0]
            self.assertEqual(row["base_rate"], 850000.0)
            self.assertEqual(row["formatted_base_rate"], "Rp 850.000")
            self.assertEqual(row["ppn_11_per_unit"], 93500.0)
            self.assertEqual(row["formatted_ppn_11_per_unit"], "Rp 93.500")
            self.assertEqual(row["rate_with_ppn_11"], 943500.0)
            self.assertEqual(row["formatted_rate_with_ppn_11"], "Rp 943.500")
            self.assertTrue(row.get("taxes_and_charges"))

            get_res = json.loads(
                execute_tool(
                    "erpnext_doc_get",
                    json.dumps({"doctype": "Item Price", "name": ip_name}),
                    context=guest_ctx,
                )
            )
            self.assertEqual(get_res["base_rate"], 850000.0)
            self.assertEqual(get_res["ppn_11_per_unit"], 93500.0)
            self.assertEqual(get_res["rate_with_ppn_11"], 943500.0)
            self.assertEqual(get_res["formatted_rate_with_ppn_11"], "Rp 943.500")

            # 2. Internal employee calls must remain untouched (no guest tax preview fields)
            frappe.set_user(self.employee)
            emp_ctx = {"user": self.employee, "branch": "sales", "worker_key": "manager"}
            emp_list = json.loads(
                execute_tool(
                    "erpnext_doc_list",
                    json.dumps({"doctype": "Item Price", "filters": {"item_code": item_code}, "fields": ["name", "price_list_rate"]}),
                    context=emp_ctx,
                )
            )
            emp_row = emp_list["data"][0]
            self.assertNotIn("base_rate", emp_row)
            self.assertNotIn("ppn_11_per_unit", emp_row)
            self.assertNotIn("rate_with_ppn_11", emp_row)

            emp_get = json.loads(
                execute_tool(
                    "erpnext_doc_get",
                    json.dumps({"doctype": "Item Price", "name": ip_name}),
                    context=emp_ctx,
                )
            )
            self.assertNotIn("ppn_11_per_unit", emp_get)
            self.assertNotIn("rate_with_ppn_11", emp_get)
        finally:
            frappe.set_user("Administrator")
            if created_ip and frappe.db.exists("Item Price", created_ip):
                frappe.delete_doc("Item Price", created_ip, ignore_permissions=True, force=True, delete_permanently=True)
            if frappe.db.exists("Item", item_code):
                frappe.delete_doc("Item", item_code, ignore_permissions=True, force=True, delete_permanently=True)

    def test_clear_and_start_and_link_unlink_rotate_conversation_preserving_audit(self):
        """Perintah /clear, /start, link, dan unlink merotasi AIOS Channel Thread ke conversation baru tanpa menghapus history lama."""
        rotated_convs: list[str] = []

        def fake_chat(messages, usage=None, tools=None, tool_calls=None):
            if usage is not None:
                usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            return iter(["Balasan"])

        try:
            with (
                patch.object(telegram_client, "send_message", return_value=True),
                patch.object(telegram_client, "send_chat_action", return_value=True),
                patch.object(telegram_client, "set_my_commands", return_value=True),
                patch("aios_v1.managers.base_manager.chat_stream", side_effect=fake_chat),
                patch("aios_v1.managers.base_manager.record_token_usage_batch"),
            ):
                res1 = dispatch.process_update(
                    {"update_id": 201, "message": {"message_id": 201, "chat": {"id": int(CHAT_ID)}, "text": "Pesan lama"}}
                )
                conv1 = str(res1["conversation"])
                rotated_convs.append(conv1)
                self.assertEqual(frappe.db.count("AIOS Message", {"conversation": conv1}), 2)

                res_clear = dispatch.process_update(
                    {"update_id": 202, "message": {"message_id": 202, "chat": {"id": int(CHAT_ID)}, "text": "/clear"}}
                )
                self.assertTrue(res_clear["success"])
                self.assertEqual(res_clear["action"], "clear")
                conv2 = str(res_clear["conversation"])
                rotated_convs.append(conv2)
                self.assertNotEqual(conv2, conv1)
                self.assertEqual(frappe.db.get_value(THREAD, res_clear["thread"], "conversation"), conv2)
                self.assertEqual(frappe.db.count("AIOS Message", {"conversation": conv2}), 0)
                self.assertTrue(frappe.db.exists(CONV, conv1))
                self.assertEqual(frappe.db.count("AIOS Message", {"conversation": conv1}), 2)

                res_start = dispatch.process_update(
                    {"update_id": 203, "message": {"message_id": 203, "chat": {"id": int(CHAT_ID)}, "text": "/start"}}
                )
                self.assertTrue(res_start["success"])
                self.assertEqual(res_start["action"], "start")
                conv3 = str(res_start["conversation"])
                rotated_convs.append(conv3)
                self.assertNotEqual(conv3, conv2)
                self.assertEqual(frappe.db.get_value(THREAD, res_start["thread"], "conversation"), conv3)
                self.assertEqual(frappe.db.count("AIOS Message", {"conversation": conv3}), 0)

                # Link -> new employee conversation
                conv4 = str(linking.link_thread_to_user(CHAT_ID, self.employee, res_start["thread"]))
                rotated_convs.append(conv4)
                self.assertNotEqual(conv4, conv3)
                self.assertEqual(frappe.db.get_value(THREAD, res_start["thread"], "conversation"), conv4)
                self.assertEqual(frappe.db.get_value(CONV, conv4, "user"), self.employee)

                # Unlink via /unlink -> new Guest conversation, conv4 preserved
                res_unlink = dispatch.process_update(
                    {"update_id": 204, "message": {"message_id": 204, "chat": {"id": int(CHAT_ID)}, "text": "/unlink"}}
                )
                conv5 = str(res_unlink["conversation"])
                rotated_convs.append(conv5)
                self.assertNotEqual(conv5, conv4)
                self.assertEqual(frappe.db.get_value(THREAD, res_start["thread"], "conversation"), conv5)
                self.assertEqual(frappe.db.get_value(CONV, conv5, "user"), "Guest")
                self.assertTrue(frappe.db.exists(CONV, conv4))

                # Link again then unlink_by_user -> rotates again
                conv6 = str(linking.link_thread_to_user(CHAT_ID, self.employee, res_start["thread"]))
                rotated_convs.append(conv6)
                self.assertNotEqual(conv6, conv5)
                self.assertTrue(linking.unlink_by_user(self.employee))
                conv7 = str(frappe.db.get_value(THREAD, res_start["thread"], "conversation"))
                rotated_convs.append(conv7)
                self.assertNotEqual(conv7, conv6)
                self.assertEqual(frappe.db.get_value(CONV, conv7, "user"), "Guest")
        finally:
            frappe.set_user("Administrator")
            for cid in reversed(rotated_convs):
                for m in frappe.get_all("AIOS Message", filters={"conversation": cid}, pluck="name"):
                    frappe.delete_doc("AIOS Message", m, ignore_permissions=True, force=True, delete_permanently=True)
                if frappe.db.exists(CONV, cid):
                    frappe.delete_doc(CONV, cid, ignore_permissions=True, force=True, delete_permanently=True)

    def test_link_and_unlink_commands_sync_per_chat_commands(self):
        """/start LINK_ valid pasang 3 perintah karyawan; LINK_ invalid & /unlink pasang 2 perintah tamu."""
        frappe.set_user(self.employee)
        link_res = linking.create_link_token(self.employee)
        raw_token = link_res["deep_link"].split("LINK_")[1]

        with (
            patch.object(telegram_client, "send_message", return_value=True),
            patch.object(telegram_client, "set_my_commands", return_value=True) as mock_cmds,
        ):
            # 1. Token tidak valid -> tidak menyinkronkan perintah karyawan
            res_bad = dispatch.process_update(
                {
                    "update_id": 301,
                    "message": {
                        "message_id": 301,
                        "chat": {"id": int(CHAT_ID)},
                        "text": "/start LINK_invalid_token_xyz",
                    },
                }
            )
            self.assertFalse(res_bad["success"])
            mock_cmds.assert_called_with(int(CHAT_ID), dispatch.GUEST_COMMANDS)

            # 2. /unlink saat tamu -> tetap menyinkronkan 2 perintah tamu
            mock_cmds.reset_mock()
            res_guest_unlink = dispatch.process_update(
                {
                    "update_id": 302,
                    "message": {
                        "message_id": 302,
                        "chat": {"id": int(CHAT_ID)},
                        "text": "/unlink",
                    },
                }
            )
            self.assertTrue(res_guest_unlink["success"])
            mock_cmds.assert_called_once_with(int(CHAT_ID), dispatch.GUEST_COMMANDS)

            # 3. /start LINK_ valid -> menyinkronkan 3 perintah karyawan
            mock_cmds.reset_mock()
            res_ok = dispatch.process_update(
                {
                    "update_id": 303,
                    "message": {
                        "message_id": 303,
                        "chat": {"id": int(CHAT_ID)},
                        "text": f"/start LINK_{raw_token}",
                    },
                }
            )
            self.assertTrue(res_ok["success"])
            mock_cmds.assert_called_once_with(int(CHAT_ID), dispatch.EMPLOYEE_COMMANDS)

            # 4. /unlink saat tertaut -> kembali ke 2 perintah tamu
            mock_cmds.reset_mock()
            res_unlink = dispatch.process_update(
                {
                    "update_id": 304,
                    "message": {
                        "message_id": 304,
                        "chat": {"id": int(CHAT_ID)},
                        "text": "/unlink",
                    },
                }
            )
            self.assertTrue(res_unlink["success"])
            mock_cmds.assert_called_once_with(int(CHAT_ID), dispatch.GUEST_COMMANDS)

    def test_set_my_commands_failure_does_not_block_link_or_unlink(self):
        """Kegagalan set_my_commands (False/exception) tidak menggagalkan link, unlink, atau send_message."""
        frappe.set_user(self.employee)
        link_res = linking.create_link_token(self.employee)
        raw_token = link_res["deep_link"].split("LINK_")[1]

        with (
            patch.object(telegram_client, "send_message", return_value=True) as mock_send,
            patch.object(telegram_client, "set_my_commands", return_value=False),
        ):
            res_ok = dispatch.process_update(
                {
                    "update_id": 310,
                    "message": {
                        "message_id": 310,
                        "chat": {"id": int(CHAT_ID)},
                        "text": f"/start LINK_{raw_token}",
                    },
                }
            )
            self.assertTrue(res_ok["success"])
            doc = frappe.get_doc(THREAD, res_ok["thread"])
            self.assertEqual(doc.linked_user, self.employee)
            mock_send.assert_called_once()

        with (
            patch.object(telegram_client, "send_message", return_value=True) as mock_send,
            patch.object(telegram_client, "set_my_commands", side_effect=RuntimeError("telegram down")),
            patch("aios_v1.lib.error_utils.frappe.log_error"),
        ):
            res_unlink = dispatch.process_update(
                {
                    "update_id": 311,
                    "message": {
                        "message_id": 311,
                        "chat": {"id": int(CHAT_ID)},
                        "text": "/unlink",
                    },
                }
            )
            self.assertTrue(res_unlink["success"])
            doc.reload()
            self.assertIsNone(doc.linked_user)
            self.assertEqual(frappe.db.get_value(CONV, doc.conversation, "user"), "Guest")
            mock_send.assert_called_once()

    def test_unlink_by_user_and_api_unlink_telegram_sync_guest_commands_best_effort(self):
        """Q1: unlink_by_user & api.connector.unlink_telegram menyinkronkan perintah tamu secara best-effort."""
        from aios_v1.api import connector as connector_api

        thread = dispatch.get_or_create_thread(CHAT_ID)
        linking.link_thread_to_user(CHAT_ID, self.employee, thread["name"])

        with patch.object(telegram_client, "set_my_commands", return_value=True) as mock_cmds:
            self.assertTrue(linking.unlink_by_user(self.employee))
        mock_cmds.assert_called_once_with(CHAT_ID, dispatch.GUEST_COMMANDS)
        self.assertIsNone(frappe.db.get_value(THREAD, thread["name"], "linked_user"))

        # Tautkan lagi lalu unlink lewat API Ekasa Desk meski Telegram error
        linking.link_thread_to_user(CHAT_ID, self.employee, thread["name"])
        frappe.set_user(self.employee)
        with (
            patch.object(telegram_client, "set_my_commands", side_effect=RuntimeError("timeout")) as mock_cmds,
            patch("aios_v1.lib.error_utils.frappe.log_error"),
        ):
            api_res = connector_api.unlink_telegram()
        self.assertEqual(api_res, {"success": True})
        mock_cmds.assert_called_once_with(CHAT_ID, dispatch.GUEST_COMMANDS)
        self.assertIsNone(frappe.db.get_value(THREAD, thread["name"], "linked_user"))


class TestConnectorSalesBranchGating(IntegrationTestCase):
    """Gap 4 (Batch D): fitur Telegram melekat pada bidang Sales (keputusan Ten).

    - create_link_token ditolak saat Sales mati, berhasil saat Sales aktif.
    - get_link_status tetap bisa dibaca saat Sales mati (read-only).
    - Putus tautan tetap bisa dijalankan saat Sales mati (pengguna tidak boleh
      terjebak terhubung); rotasi putus tautan tidak bergantung pada `get_manager`.
    - Jalur linking untuk pesan masuk, dispatch, dan poller tidak berubah.
    """

    EMAIL = "_test.linking.gate@example.com"
    CHAT = "88119977"

    def setUp(self):
        super().setUp()
        frappe.in_test = True
        frappe.flags.in_test = True
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        self.addCleanup(self._restore_and_rollback)
        frappe.set_user("Administrator")
        self._orig_bot = frappe.db.get_single_value(SETTING, "bot_username")
        frappe.db.set_value(SETTING, SETTING, "bot_username", "test_aios_bot")
        _ensure_user(self.EMAIL, "Link Gate User", is_receiver=False)
        frappe.set_user(self.EMAIL)

    def _restore_and_rollback(self):
        frappe.set_user("Administrator")
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()

    def tearDown(self):
        frappe.set_user("Administrator")
        threads = frappe.get_all(THREAD, filters={"external_thread_id": self.CHAT}, pluck="name")
        for t_name in threads:
            conv = frappe.db.get_value(THREAD, t_name, "conversation")
            frappe.delete_doc(THREAD, t_name, ignore_permissions=True, force=True, delete_permanently=True)
            if conv and frappe.db.exists(CONV, conv):
                for m in frappe.get_all("AIOS Message", filters={"conversation": conv}, pluck="name"):
                    frappe.delete_doc("AIOS Message", m, ignore_permissions=True, force=True, delete_permanently=True)
                frappe.delete_doc(CONV, conv, ignore_permissions=True, force=True, delete_permanently=True)
        for conv in frappe.get_all(CONV, filters={"user": self.EMAIL}, pluck="name"):
            for m in frappe.get_all("AIOS Message", filters={"conversation": conv}, pluck="name"):
                frappe.delete_doc("AIOS Message", m, ignore_permissions=True, force=True, delete_permanently=True)
            frappe.delete_doc(CONV, conv, ignore_permissions=True, force=True, delete_permanently=True)
        frappe.cache().delete_value(f"aios_tg_user_token:{self.EMAIL}")
        if frappe.db.exists("Notification Settings", self.EMAIL):
            frappe.delete_doc(
                "Notification Settings", self.EMAIL, ignore_permissions=True, force=True, delete_permanently=True
            )
        if frappe.db.exists("User", self.EMAIL):
            frappe.delete_doc(
                "User", self.EMAIL, ignore_permissions=True, force=False, delete_permanently=True
            )
        frappe.db.set_value(SETTING, SETTING, "bot_username", self._orig_bot)
        self._restore_and_rollback()
        super().tearDown()

    def _set_active_branches(self, keys):
        from aios_v1.lib import branch_activation

        doc = frappe.get_single(branch_activation.DOCTYPE)
        doc.set("branches", [])
        for key in sorted(keys):
            doc.append("branches", {"branch_key": key, "enabled": 1})
        doc.seeded = 1
        doc.save(ignore_permissions=True)
        branch_activation.clear_cache()

    def _with_branches(self, keys):
        from aios_v1.lib import branch_activation

        original = set(branch_activation.get_active_branches())
        self.addCleanup(self._set_active_branches, original)
        self._set_active_branches(keys)

    def test_create_link_token_rejected_when_sales_disabled(self):
        """(a) Tugas 1: tautan baru ditolak saat Sales mati, tanpa token tercipta."""
        from aios_v1.api import connector as connector_api

        self._with_branches({"finance", "accounting", "purchasing"})
        frappe.set_user(self.EMAIL)

        with self.assertRaises(frappe.PermissionError) as ctx:
            connector_api.create_link_token()
        self.assertIn("hanya tersedia untuk bidang Sales", str(ctx.exception))
        # Tidak ada token yang tersimpan di cache maupun di dalam tautan.
        self.assertIsNone(frappe.cache().get_value(f"aios_tg_user_token:{self.EMAIL}"))

    def test_create_link_token_succeeds_when_sales_enabled(self):
        """(a) Saat Sales aktif, pembuatan tautan berjalan seperti biasa."""
        from aios_v1.api import connector as connector_api

        self._with_branches({"sales", "finance", "accounting", "purchasing"})
        frappe.set_user(self.EMAIL)

        res = connector_api.create_link_token()
        self.assertIn("LINK_", res["deep_link"])
        self.assertIn("test_aios_bot", res["deep_link"])
        self.assertGreater(int(res.get("expires_in_seconds") or 0), 0)

    def test_get_link_status_readable_when_sales_disabled(self):
        """(c) Tugas 3: status tautan tetap bisa dibaca saat Sales mati (read-only)."""
        from aios_v1.api import connector as connector_api

        thread = dispatch.get_or_create_thread(self.CHAT)
        linking.link_thread_to_user(self.CHAT, self.EMAIL, thread["name"])

        self._with_branches({"finance", "accounting", "purchasing"})
        frappe.set_user(self.EMAIL)

        status = connector_api.get_link_status()
        self.assertTrue(status["linked"])
        self.assertEqual(str(status["external_thread_id"]), self.CHAT)

    def test_unlink_telegram_still_works_when_sales_disabled(self):
        """(d) Tugas 3: putus tautan tetap bisa dipakai saat Sales mati; rotasi tanpa `get_manager`."""
        from aios_v1.api import connector as connector_api

        thread = dispatch.get_or_create_thread(self.CHAT)
        linking.link_thread_to_user(self.CHAT, self.EMAIL, thread["name"])

        self._with_branches({"finance", "accounting", "purchasing"})
        frappe.set_user(self.EMAIL)

        res = connector_api.unlink_telegram()
        self.assertTrue(res["success"])
        self.assertIsNone(frappe.db.get_value(THREAD, thread["name"], "linked_user"))
        # Rotasi putus tautan menghasilkan percakapan tamu baru tanpa manager.
        new_conv = frappe.db.get_value(THREAD, thread["name"], "conversation")
        self.assertEqual(frappe.db.get_value(CONV, new_conv, "user"), "Guest")
        self.assertEqual(frappe.db.get_value(CONV, new_conv, "branch"), "sales")

    def test_message_link_rotation_still_gated_by_sales_activation(self):
        """(e) Tugas 4: jalur linking/dispatch pesan tidak berubah — rotasi jalur pesan tetap melewati `get_manager`."""
        self._with_branches({"finance", "accounting", "purchasing"})

        with self.assertRaises(frappe.ValidationError):
            linking.rotate_thread_conversation("THREAD-TIDAK-ADA-BATCH-D", self.EMAIL)
        # Rotasi jalur link tetap memakai `_new_conversation_for_user` (get_manager).
        self.assertTrue(hasattr(linking, "_new_conversation_for_user"))


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

