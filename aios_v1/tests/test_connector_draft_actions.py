"""Integration tests for linked-employee Telegram draft actions (approve/reject/pay)."""

from __future__ import annotations

import json
from unittest.mock import patch

import frappe
from frappe.utils import nowdate

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore

from aios_v1.lib.connector import dispatch, linking, notify, telegram_client
from aios_v1.lib.draft_manager import approve_and_execute_draft, create_draft
from aios_v1.lib.tool_registry import GUEST_ALLOWED_TOOLS, execute_tool, get_tools_schema_for_worker

SETTING = "AIOS Telegram Setting"
THREAD = "AIOS Channel Thread"
RECEIVER = "_test.tg.draft.receiver@example.com"
OWNER = "_test.tg.draft.owner@example.com"
STAFF = "_test.tg.draft.staff@example.com"
CHAT_RECEIVER = "99110001"
CHAT_OWNER = "99110002"
CHAT_STAFF = "99110003"
CHAT_CUSTOMER = "99110004"


def _ensure_user(email: str, name: str, extra_roles: list[str] | None = None) -> str:
    roles = ["AIOS Client"]
    for role in extra_roles or []:
        if role != "AIOS Client":
            roles.append(role)
    if frappe.db.exists("User", email):
        doc = frappe.get_doc("User", email)
        doc.enabled = 1
        doc.user_type = "Website User"
        doc.aios_status = "Active"
        doc.set("roles", [{"role": r} for r in roles])
        doc.flags.ignore_permissions = True
        doc.flags.ignore_password_policy = True
        doc.save(ignore_permissions=True)
    else:
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
            }
        )
        doc.insert(ignore_permissions=True)
    frappe.clear_cache(user=email)
    return email


def _ensure_thread(chat_id: str, linked_user: str | None) -> str:
    thread = dispatch.get_or_create_thread(chat_id, {"first_name": "Tester"})
    if linked_user:
        linking.link_thread_to_user(chat_id, linked_user, thread["name"])
    return thread["name"]


class TestConnectorDraftActions(IntegrationTestCase):
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
        self.receiver = _ensure_user(RECEIVER, "_Test TG Receiver", extra_roles=["AIOS Channel Receiver"])
        self.owner = _ensure_user(OWNER, "_Test TG Owner", extra_roles=["AIOS Client Owner"])
        self.staff = _ensure_user(STAFF, "_Test TG Staff")

        self._orig_active = frappe.db.get_single_value(SETTING, "is_active")
        frappe.db.set_single_value(SETTING, "is_active", 1)
        for cid in (CHAT_RECEIVER, CHAT_OWNER, CHAT_STAFF, CHAT_CUSTOMER):
            dispatch.clear_rate_limit(cid)

        self.company = (
            frappe.db.get_single_value("AIOS Setting", "default_company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )
        self.currency = frappe.db.get_value("Company", self.company, "default_currency") or "IDR"
        price_lists = frappe.get_all("Price List", filters={"selling": 1, "enabled": 1}, pluck="name", limit=1)
        self.price_list = price_lists[0] if price_lists else "Standard Selling"

        non_stock = frappe.get_all("Item", filters={"disabled": 0, "is_stock_item": 0}, fields=["name", "item_name"], limit=1)
        if non_stock:
            self.item_code = non_stock[0]["name"]
            self.item_name = non_stock[0]["item_name"] or self.item_code
            self.warehouse = None
        else:
            stock_items = frappe.get_all("Item", filters={"disabled": 0}, fields=["name", "item_name"], limit=1)
            self.item_code = stock_items[0]["name"]
            self.item_name = stock_items[0]["item_name"] or self.item_code
            warehouses = frappe.get_all("Warehouse", filters={"company": self.company, "is_group": 0}, pluck="name", limit=1)
            self.warehouse = warehouses[0] if warehouses else None

        ip_rate = frappe.db.get_value(
            "Item Price",
            {"item_code": self.item_code, "price_list": self.price_list, "selling": 1},
            "price_list_rate",
        )
        self.item_rate = float(ip_rate) if ip_rate else float(frappe.db.get_value("Item", self.item_code, "standard_rate") or 125000)

        self.created_customers: list[str] = []
        self.created_drafts: list[str] = []
        self._cache_keys_to_clear: list[str] = []
        self._cleanup_threads()

        self.thread_receiver = _ensure_thread(CHAT_RECEIVER, self.receiver)
        self.thread_owner = _ensure_thread(CHAT_OWNER, self.owner)
        self.thread_staff = _ensure_thread(CHAT_STAFF, self.staff)
        self.thread_customer = _ensure_thread(CHAT_CUSTOMER, None)

    def _restore_and_rollback(self):
        if hasattr(frappe.local, "aios_channel"):
            delattr(frappe.local, "aios_channel")
        if hasattr(frappe.local, "aios_channel_thread"):
            delattr(frappe.local, "aios_channel_thread")
        frappe.set_user("Administrator")
        cache = frappe.cache()
        for key in getattr(self, "_cache_keys_to_clear", []):
            cache.delete_value(key)
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()

    def tearDown(self):
        frappe.set_user("Administrator")
        cache = frappe.cache()
        for draft_id in getattr(self, "created_drafts", []):
            for usr in (self.receiver, self.owner, self.staff):
                for act in ("approve", "reject", "confirm_cash_payment"):
                    cache.delete_value(f"aios_tg_confirm:{usr}:{act}:{draft_id}")
        self._cleanup_threads()
        for cid in (CHAT_RECEIVER, CHAT_OWNER, CHAT_STAFF, CHAT_CUSTOMER):
            dispatch.clear_rate_limit(cid)
        for email in (RECEIVER, OWNER, STAFF):
            for cname in frappe.get_all("Contact", filters={"user": email}, pluck="name"):
                frappe.delete_doc("Contact", cname, ignore_permissions=True, force=True, delete_permanently=True)
            if frappe.db.exists("Notification Settings", email):
                frappe.delete_doc("Notification Settings", email, ignore_permissions=True, force=True, delete_permanently=True)
            if frappe.db.exists("User", email):
                frappe.delete_doc("User", email, ignore_permissions=True, force=True, delete_permanently=True)
        for cust in getattr(self, "created_customers", []):
            if frappe.db.exists("Customer", cust):
                for pe in frappe.get_all("Payment Entry", filters={"party_type": "Customer", "party": cust}, pluck="name"):
                    frappe.db.set_value("Payment Entry", pe, "docstatus", 2)
                    frappe.delete_doc("Payment Entry", pe, ignore_permissions=True, force=True)
                for so in frappe.get_all("Sales Order", filters={"customer": cust}, pluck="name"):
                    frappe.db.set_value("Sales Order", so, "docstatus", 2)
                    frappe.delete_doc("Sales Order", so, ignore_permissions=True, force=True)
        frappe.db.set_single_value(SETTING, "is_active", self._orig_active)
        self._restore_and_rollback()
        super().tearDown()

    def _cleanup_threads(self):
        for name in frappe.get_all(
            THREAD,
            filters={"external_thread_id": ("in", [CHAT_RECEIVER, CHAT_OWNER, CHAT_STAFF, CHAT_CUSTOMER])},
            pluck="name",
        ):
            for flag in frappe.get_all("AIOS Conversation Flag", filters={"thread": name}, pluck="name"):
                frappe.delete_doc("AIOS Conversation Flag", flag, ignore_permissions=True, force=True, delete_permanently=True)
            conv = frappe.db.get_value(THREAD, name, "conversation")
            frappe.delete_doc(THREAD, name, ignore_permissions=True, force=True, delete_permanently=True)
            if conv and frappe.db.exists("AIOS Conversation", conv):
                frappe.delete_doc("AIOS Conversation", conv, ignore_permissions=True, force=True, delete_permanently=True)

    def _create_guest_order_draft(self, customer_name: str, qty: int = 2, draft_owner: str | None = None):
        self.created_customers.append(customer_name)
        item = {
            "item_code": self.item_code,
            "qty": qty,
            "rate": self.item_rate,
            "delivery_date": nowdate(),
        }
        if self.warehouse:
            item["warehouse"] = self.warehouse
        payload = {
            "doctype": "Sales Order",
            "source_telegram_chat_id": CHAT_CUSTOMER,
            "data": {
                "customer": customer_name,
                "company": self.company,
                "selling_price_list": self.price_list,
                "transaction_date": nowdate(),
                "delivery_date": nowdate(),
                "items": [item],
            },
            "customer_info": {
                "customer_type": "Individual",
                "customer_name": customer_name,
                "mobile_no": "081288887777",
                "address": "Jalan Merdeka No. 10, Bandung",
                "payment_method": "Cash",
            },
            "reason": "Pesanan pelanggan via Telegram",
        }
        draft = create_draft(
            task_id=f"TEST-TG-DRF-{frappe.generate_hash(length=6)}",
            action_type="CREATE",
            payload=payload,
            branch="sales",
            created_by_agent="manager",
            user=draft_owner or self.receiver,
        )
        self.created_drafts.append(draft.name)
        with patch.object(telegram_client, "send_message", return_value=True):
            notify.notify_order_draft(draft, thread={"name": self.thread_customer})
        return draft

    def _update(self, chat_id: str, text: str, update_id: int = 1) -> dict:
        return {
            "update_id": update_id,
            "message": {
                "message_id": update_id,
                "chat": {"id": int(chat_id)},
                "from": {"first_name": "Karyawan"},
                "text": text,
            },
        }

    def test_guest_cannot_see_or_call_telegram_draft_tools(self):
        draft = self._create_guest_order_draft("_Test TG Guest Deny Cust")
        frappe.local.aios_channel = "telegram"
        try:
            guest_tools = {
                s["function"]["name"]
                for s in get_tools_schema_for_worker("sales", "manager", user="Guest")
            }
            self.assertEqual(guest_tools, set(GUEST_ALLOWED_TOOLS))
            for tool_name in ("approve_draft", "reject_draft", "confirm_cash_payment"):
                self.assertNotIn(tool_name, guest_tools)
                raw = execute_tool(
                    tool_name,
                    json.dumps({"draft_id": draft.name, "confirmed": True}),
                    context={"user": "Guest", "branch": "sales", "worker_key": "manager"},
                )
                res = json.loads(raw)
                self.assertEqual(res.get("code"), "GUEST_TOOL_FORBIDDEN")
        finally:
            if hasattr(frappe.local, "aios_channel"):
                delattr(frappe.local, "aios_channel")
        self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")

    def test_non_telegram_excludes_draft_tools_and_telegram_blocks_other_tools(self):
        # Non-Telegram (Ekasa Desk web chat) tidak mengekspos TELEGRAM_DRAFT_TOOLS
        if hasattr(frappe.local, "aios_channel"):
            delattr(frappe.local, "aios_channel")
        web_tools = {
            s["function"]["name"]
            for s in get_tools_schema_for_worker("sales", "manager", user=self.receiver)
        }
        for tool_name in ("approve_draft", "reject_draft", "confirm_cash_payment"):
            self.assertNotIn(tool_name, web_tools)

        # Pada Telegram: manager non-Guest melihat 5 guest tool + 3 tool draf; subagent tidak
        frappe.local.aios_channel = "telegram"
        try:
            from aios_v1.plugin_manager.registry import get_branch

            tg_manager_tools = {
                s["function"]["name"]
                for s in get_tools_schema_for_worker("sales", "manager", user=self.receiver)
            }
            for tool_name in ("approve_draft", "reject_draft", "confirm_cash_payment"):
                self.assertIn(tool_name, tg_manager_tools)
            self.assertNotIn("erpnext_report_run", tg_manager_tools)

            subagent_key = get_branch("sales")["workers"][0]["key"]
            tg_subagent_tools = {
                s["function"]["name"]
                for s in get_tools_schema_for_worker("sales", subagent_key, user=self.receiver)
            }
            for tool_name in ("approve_draft", "reject_draft", "confirm_cash_payment"):
                self.assertNotIn(tool_name, tg_subagent_tools)

            frappe.set_user(self.receiver)
            denied_report = execute_tool(
                "erpnext_report_run",
                "{}",
                context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
            )
            self.assertIn("TOOL_FORBIDDEN_ON_TELEGRAM", denied_report)
        finally:
            if hasattr(frappe.local, "aios_channel"):
                delattr(frappe.local, "aios_channel")

    def test_linked_staff_without_authority_rejected_and_owner_fallback_works(self):
        draft = self._create_guest_order_draft("_Test TG Staff Auth Cust")
        frappe.local.aios_channel = "telegram"
        try:
            # Karyawan AIOS Client biasa (tanpa AIOS Channel Receiver / fallback Owner) ditolak
            frappe.set_user(self.staff)
            for tool_name in ("approve_draft", "reject_draft", "confirm_cash_payment"):
                raw = execute_tool(
                    tool_name,
                    json.dumps({"draft_id": draft.name}),
                    context={"user": self.staff, "branch": "sales", "worker_key": "manager"},
                )
                res = json.loads(raw)
                self.assertEqual(res.get("code"), "NOT_AUTHORIZED")
                self.assertTrue(res.get("error"))

            # Cabut role AIOS Channel Receiver dari self.receiver -> kini Owner menjadi fallback aktif
            frappe.set_user("Administrator")
            frappe.db.delete(
                "Has Role",
                {"parent": self.receiver, "parenttype": "User", "role": "AIOS Channel Receiver"},
            )
            frappe.clear_cache(user=self.receiver)

            # Ex-receiver wajib ditolak meski draft.user sebelumnya tercatat ke dia
            frappe.set_user(self.receiver)
            revoked_res = json.loads(
                execute_tool(
                    "approve_draft",
                    json.dumps({"draft_id": draft.name}),
                    context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(revoked_res.get("code"), "NOT_AUTHORIZED")

            # Client Owner fallback kini berwenang meminta konfirmasi dan mengeksekusi draf kanal
            frappe.set_user(self.owner)
            owner_res = json.loads(
                execute_tool(
                    "approve_draft",
                    json.dumps({"draft_id": draft.name}),
                    context={"user": self.owner, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(owner_res.get("status"), "CONFIRMATION_REQUIRED")
            self.assertEqual(owner_res["summary"]["draft_id"], draft.name)
            with patch.object(telegram_client, "send_message", return_value=True):
                exec_res = json.loads(
                    execute_tool(
                        "approve_draft",
                        json.dumps(
                            {
                                "draft_id": draft.name,
                                "confirmed": True,
                                "confirmation_token": owner_res["confirmation_token"],
                            }
                        ),
                        context={"user": self.owner, "branch": "sales", "worker_key": "manager"},
                    )
                )
            self.assertTrue(exec_res.get("executed"))
            so_doc = frappe.get_doc("Sales Order", exec_res["sales_order"])
            self.assertEqual(so_doc.owner, self.owner)
            self.assertEqual(so_doc.modified_by, self.owner)
            self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "modified_by"), self.owner)
        finally:
            if hasattr(frappe.local, "aios_channel"):
                delattr(frappe.local, "aios_channel")

    def test_confirmation_required_blocks_same_turn_bypass_and_decline_aborts(self):
        draft = self._create_guest_order_draft("_Test TG Confirm Guard Cust")
        frappe.local.aios_channel = "telegram"
        try:
            frappe.set_user(self.receiver)
            # 1. Memaksa confirmed=True tanpa tantangan awal ditolak
            forced = json.loads(
                execute_tool(
                    "approve_draft",
                    json.dumps({"draft_id": draft.name, "confirmed": True}),
                    context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(forced.get("status"), "CONFIRMATION_REQUIRED")
            self.assertFalse(forced.get("executed"))
            self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")

            # 2. Simulasi LLM mencoba mengeksekusi dalam 1 turn dispatch sebelum user membalas
            sent_messages: list[tuple[str, str]] = []
            round_results: list[dict] = []
            turn_state = {"calls": 0}

            def same_turn_bypass_llm(messages, usage=None, tools=None, tool_calls=None):
                turn_state["calls"] += 1
                if turn_state["calls"] == 1:
                    tool_calls.append(
                        {
                            "id": "c1",
                            "function": {
                                "name": "approve_draft",
                                "arguments": json.dumps({"draft_id": draft.name}),
                            },
                        }
                    )
                    if False:
                        yield ""
                    return
                if turn_state["calls"] == 2:
                    tool_res = json.loads(messages[-1]["content"])
                    round_results.append(tool_res)
                    tok = tool_res.get("confirmation_token", "")
                    tool_calls.append(
                        {
                            "id": "c2",
                            "function": {
                                "name": "approve_draft",
                                "arguments": json.dumps(
                                    {"draft_id": draft.name, "confirmed": True, "confirmation_token": tok}
                                ),
                            },
                        }
                    )
                    if False:
                        yield ""
                    return
                tool_res = json.loads(messages[-1]["content"])
                round_results.append(tool_res)
                yield f"Mohon konfirmasi setujui {draft.name} (ya/tidak)."

            with patch("aios_v1.managers.base_manager.chat_stream", side_effect=same_turn_bypass_llm), \
                 patch.object(telegram_client, "send_chat_action", return_value=True), \
                 patch.object(telegram_client, "send_message", side_effect=lambda cid, txt: sent_messages.append((str(cid), txt)) or True):
                dispatch.process_update(self._update(CHAT_RECEIVER, f"setujui draf {draft.name}", update_id=10))

            self.assertEqual(round_results[0].get("status"), "CONFIRMATION_REQUIRED")
            self.assertEqual(round_results[1].get("code"), "CONFIRMATION_PENDING_USER_REPLY")
            self.assertFalse(round_results[1].get("executed"))
            self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")
            self.assertFalse(frappe.get_all("Sales Order", filters={"customer": "_Test TG Confirm Guard Cust"}))

            # 2b. Pertanyaan klarifikasi/netral meskipun disertai token valid tidak boleh mengeksekusi
            neutral_results: list[dict] = []
            neutral_step = {"calls": 0}
            first_tok = round_results[0].get("confirmation_token", "")

            def neutral_llm(messages, usage=None, tools=None, tool_calls=None):
                neutral_step["calls"] += 1
                if neutral_step["calls"] == 1:
                    tool_calls.append(
                        {
                            "id": "c2b",
                            "function": {
                                "name": "approve_draft",
                                "arguments": json.dumps(
                                    {
                                        "draft_id": draft.name,
                                        "confirmed": True,
                                        "confirmation_token": first_tok,
                                    }
                                ),
                            },
                        }
                    )
                    if False:
                        yield ""
                    return
                neutral_results.append(json.loads(messages[-1]["content"]))
                yield f"Ongkir sesuai tarif normal. Konfirmasi ulang: setujui {draft.name} (ya/tidak)?"

            with patch("aios_v1.managers.base_manager.chat_stream", side_effect=neutral_llm), \
                 patch.object(telegram_client, "send_chat_action", return_value=True), \
                 patch.object(telegram_client, "send_message", side_effect=lambda cid, txt: sent_messages.append((str(cid), txt)) or True):
                dispatch.process_update(self._update(CHAT_RECEIVER, "Ongkir ke Jakarta berapa?", update_id=11))

            self.assertEqual(neutral_results[0].get("status"), "CONFIRMATION_REQUIRED")
            self.assertFalse(neutral_results[0].get("executed"))
            self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")
            self.assertFalse(frappe.get_all("Sales Order", filters={"customer": "_Test TG Confirm Guard Cust"}))

            # 3. Karyawan membalas "tidak, batalkan" -> token dihapus, tidak dieksekusi
            decline_results: list[dict] = []
            decline_step = {"calls": 0}

            def decline_llm(messages, usage=None, tools=None, tool_calls=None):
                decline_step["calls"] += 1
                if decline_step["calls"] == 1:
                    tool_calls.append(
                        {
                            "id": "c3",
                            "function": {
                                "name": "approve_draft",
                                "arguments": json.dumps({"draft_id": draft.name, "confirmed": True}),
                            },
                        }
                    )
                    if False:
                        yield ""
                    return
                decline_results.append(json.loads(messages[-1]["content"]))
                yield f"Baik, draf {draft.name} dibatalkan konfirmasinya dan tidak dieksekusi."

            with patch("aios_v1.managers.base_manager.chat_stream", side_effect=decline_llm), \
                 patch.object(telegram_client, "send_chat_action", return_value=True), \
                 patch.object(telegram_client, "send_message", side_effect=lambda cid, txt: sent_messages.append((str(cid), txt)) or True):
                dispatch.process_update(self._update(CHAT_RECEIVER, "tidak, batalkan", update_id=12))

            self.assertEqual(decline_results[0].get("code"), "CONFIRMATION_DECLINED")
            self.assertFalse(decline_results[0].get("executed"))
            self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")
            self.assertFalse(frappe.get_all("Sales Order", filters={"customer": "_Test TG Confirm Guard Cust"}))
        finally:
            if hasattr(frappe.local, "aios_channel"):
                delattr(frappe.local, "aios_channel")

    def test_employee_approve_draft_two_turns_via_telegram_sets_audit_and_notifies_customer(self):
        cust_name = "_Test TG Approve Two Turns"
        draft = self._create_guest_order_draft(cust_name, qty=2)
        sent_messages: list[tuple[str, str]] = []
        turn1_tool_res: dict = {}
        turn2_tool_res: dict = {}

        def approve_turn1_llm(messages, usage=None, tools=None, tool_calls=None):
            if messages[-1]["role"] != "tool":
                tool_names = {t["function"]["name"] for t in (tools or [])}
                self.assertIn("approve_draft", tool_names)
                tool_calls.append(
                    {
                        "id": "app1",
                        "function": {
                            "name": "approve_draft",
                            "arguments": json.dumps({"draft_id": draft.name}),
                        },
                    }
                )
                if False:
                    yield ""
                return
            turn1_tool_res.update(json.loads(messages[-1]["content"]))
            s = turn1_tool_res["summary"]
            item_desc = ", ".join(f"{it['item_name']} x{it['qty']}" for it in s["items"])
            yield (
                f"Konfirmasi setujui draf {s['draft_id']} untuk {s['customer']}, "
                f"item: {item_desc}, total {s['formatted_total']}. Balas ya atau tidak."
            )

        def approve_turn2_llm(messages, usage=None, tools=None, tool_calls=None):
            if messages[-1]["role"] != "tool":
                # Sengaja menguji panggilan Turn 2 tanpa confirmation_token (real-world AIOS Message history)
                tool_calls.append(
                    {
                        "id": "app2",
                        "function": {
                            "name": "approve_draft",
                            "arguments": json.dumps({"draft_id": draft.name, "confirmed": True}),
                        },
                    }
                )
                if False:
                    yield ""
                return
            turn2_tool_res.update(json.loads(messages[-1]["content"]))
            yield f"Draf {draft.name} berhasil disetujui. Nomor Sales Order: {turn2_tool_res['sales_order']} (status: {turn2_tool_res['draft_status']})."

        with patch("aios_v1.managers.base_manager.chat_stream", side_effect=approve_turn1_llm), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(telegram_client, "send_message", side_effect=lambda cid, txt: sent_messages.append((str(cid), txt)) or True):
            r1 = dispatch.process_update(self._update(CHAT_RECEIVER, f"setujui draf {draft.name}", update_id=20))

        self.assertTrue(r1["success"])
        self.assertEqual(turn1_tool_res.get("status"), "CONFIRMATION_REQUIRED")
        self.assertEqual(turn1_tool_res["summary"]["customer"], cust_name)
        self.assertIn(self.item_name, json.dumps(turn1_tool_res["summary"]["items"]))
        self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")
        self.assertIn(cust_name, sent_messages[-1][1])
        self.assertIn(draft.name, sent_messages[-1][1])

        sent_messages.clear()
        with patch("aios_v1.managers.base_manager.chat_stream", side_effect=approve_turn2_llm), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(telegram_client, "send_message", side_effect=lambda cid, txt: sent_messages.append((str(cid), txt)) or True):
            r2 = dispatch.process_update(self._update(CHAT_RECEIVER, "ya, setuju", update_id=21))

        self.assertTrue(r2["success"])
        self.assertTrue(turn2_tool_res.get("executed"))
        so_name = turn2_tool_res.get("sales_order")
        self.assertTrue(so_name and frappe.db.exists("Sales Order", so_name))

        so_doc = frappe.get_doc("Sales Order", so_name)
        draft_doc = frappe.get_doc("Pending Action Draft", draft.name)
        self.assertEqual(so_doc.docstatus, 1)
        self.assertEqual(so_doc.owner, self.receiver)
        self.assertEqual(so_doc.modified_by, self.receiver)
        self.assertEqual(draft_doc.status, "EXECUTED")
        self.assertEqual(draft_doc.modified_by, self.receiver)

        customer_msgs = [txt for cid, txt in sent_messages if cid == CHAT_CUSTOMER]
        employee_msgs = [txt for cid, txt in sent_messages if cid == CHAT_RECEIVER]
        self.assertEqual(len(customer_msgs), 1)
        self.assertIn("disetujui", customer_msgs[0].lower())
        self.assertNotIn(so_name, customer_msgs[0])
        self.assertNotIn(draft.name, customer_msgs[0])
        self.assertEqual(len(employee_msgs), 1)
        self.assertIn(so_name, employee_msgs[0])

    def test_employee_confirm_cash_payment_two_turns_sets_payment_entry_audit_and_notifies_customer(self):
        cust_name = "_Test TG Cash Pay Two Turns"
        draft = self._create_guest_order_draft(cust_name, qty=1)
        frappe.set_user(self.receiver)
        with patch.object(telegram_client, "send_message", return_value=True):
            exec_res = approve_and_execute_draft(draft.name)
        so_name = exec_res["name"]
        frappe.set_user("Administrator")

        sent_messages: list[tuple[str, str]] = []
        turn1_res: dict = {}
        turn2_res: dict = {}

        def pay_turn1_llm(messages, usage=None, tools=None, tool_calls=None):
            if messages[-1]["role"] != "tool":
                tool_calls.append(
                    {
                        "id": "pay1",
                        "function": {
                            "name": "confirm_cash_payment",
                            "arguments": json.dumps({"draft_id": draft.name}),
                        },
                    }
                )
                if False:
                    yield ""
                return
            turn1_res.update(json.loads(messages[-1]["content"]))
            s = turn1_res["summary"]
            yield f"Konfirmasi bayar Cash draf {s['draft_id']} ({s['sales_order']}) untuk {s['customer']} total {s['formatted_total']}. Ya/tidak?"

        def pay_turn2_llm(messages, usage=None, tools=None, tool_calls=None):
            if messages[-1]["role"] != "tool":
                tool_calls.append(
                    {
                        "id": "pay2",
                        "function": {
                            "name": "confirm_cash_payment",
                            "arguments": json.dumps(
                                {
                                    "draft_id": draft.name,
                                    "confirmed": True,
                                    "confirmation_token": turn1_res.get("confirmation_token", ""),
                                }
                            ),
                        },
                    }
                )
                if False:
                    yield ""
                return
            turn2_res.update(json.loads(messages[-1]["content"]))
            yield f"Pembayaran Cash tercatat: {turn2_res['payment_entry']} untuk {turn2_res['sales_order']} (status: lunas)."

        with patch("aios_v1.managers.base_manager.chat_stream", side_effect=pay_turn1_llm), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(telegram_client, "send_message", side_effect=lambda cid, txt: sent_messages.append((str(cid), txt)) or True):
            r1 = dispatch.process_update(self._update(CHAT_RECEIVER, f"sudah bayar cash {draft.name}", update_id=30))

        self.assertTrue(r1["success"])
        self.assertEqual(turn1_res.get("status"), "CONFIRMATION_REQUIRED")
        self.assertEqual(turn1_res["summary"]["sales_order"], so_name)
        self.assertEqual(
            frappe.get_all("Payment Entry Reference", filters={"reference_name": so_name, "docstatus": 1}),
            [],
        )

        sent_messages.clear()
        with patch("aios_v1.managers.base_manager.chat_stream", side_effect=pay_turn2_llm), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(telegram_client, "send_message", side_effect=lambda cid, txt: sent_messages.append((str(cid), txt)) or True):
            r2 = dispatch.process_update(self._update(CHAT_RECEIVER, "ya", update_id=31))

        self.assertTrue(r2["success"])
        self.assertTrue(turn2_res.get("payment_confirmed"))
        pe_name = turn2_res.get("payment_entry")
        self.assertTrue(pe_name and frappe.db.exists("Payment Entry", pe_name))

        pe_doc = frappe.get_doc("Payment Entry", pe_name)
        so_doc = frappe.get_doc("Sales Order", so_name)
        draft_doc = frappe.get_doc("Pending Action Draft", draft.name)
        self.assertEqual(pe_doc.docstatus, 1)
        self.assertEqual(pe_doc.mode_of_payment, "Cash")
        self.assertEqual(pe_doc.owner, self.receiver)
        self.assertEqual(pe_doc.modified_by, self.receiver)
        self.assertEqual(so_doc.owner, self.receiver)
        self.assertEqual(so_doc.modified_by, self.receiver)
        self.assertEqual(draft_doc.modified_by, self.receiver)

        customer_msgs = [txt for cid, txt in sent_messages if cid == CHAT_CUSTOMER]
        employee_msgs = [txt for cid, txt in sent_messages if cid == CHAT_RECEIVER]
        self.assertEqual(len(customer_msgs), 1)
        self.assertIn("pembayaran cash anda sebesar", customer_msgs[0].lower())
        self.assertNotIn(pe_name, customer_msgs[0])
        self.assertNotIn(so_name, customer_msgs[0])
        self.assertEqual(len(employee_msgs), 1)
        self.assertIn(pe_name, employee_msgs[0])
        self.assertIn(so_name, employee_msgs[0])

    def test_employee_reject_draft_two_turns_sets_modified_by_and_notifies_customer(self):
        cust_name = "_Test TG Reject Two Turns"
        draft = self._create_guest_order_draft(cust_name, qty=1)
        sent_messages: list[tuple[str, str]] = []
        turn1_res: dict = {}
        turn2_res: dict = {}

        def reject_turn1_llm(messages, usage=None, tools=None, tool_calls=None):
            if messages[-1]["role"] != "tool":
                tool_calls.append(
                    {
                        "id": "rej1",
                        "function": {
                            "name": "reject_draft",
                            "arguments": json.dumps({"draft_id": draft.name, "reason": "Stok kosong"}),
                        },
                    }
                )
                if False:
                    yield ""
                return
            turn1_res.update(json.loads(messages[-1]["content"]))
            yield f"Konfirmasi tolak draf {draft.name} ({turn1_res['summary']['customer']}) alasan Stok kosong. Ya/tidak?"

        def reject_turn2_llm(messages, usage=None, tools=None, tool_calls=None):
            if messages[-1]["role"] != "tool":
                tool_calls.append(
                    {
                        "id": "rej2",
                        "function": {
                            "name": "reject_draft",
                            "arguments": json.dumps({"draft_id": draft.name, "confirmed": True}),
                        },
                    }
                )
                if False:
                    yield ""
                return
            turn2_res.update(json.loads(messages[-1]["content"]))
            yield f"Draf {draft.name} telah ditolak (status: {turn2_res['draft_status']})."

        with patch("aios_v1.managers.base_manager.chat_stream", side_effect=reject_turn1_llm), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(telegram_client, "send_message", side_effect=lambda cid, txt: sent_messages.append((str(cid), txt)) or True):
            r1 = dispatch.process_update(self._update(CHAT_RECEIVER, f"tolak {draft.name} stok kosong", update_id=40))

        self.assertTrue(r1["success"])
        self.assertEqual(turn1_res.get("status"), "CONFIRMATION_REQUIRED")
        self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")

        sent_messages.clear()
        with patch("aios_v1.managers.base_manager.chat_stream", side_effect=reject_turn2_llm), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(telegram_client, "send_message", side_effect=lambda cid, txt: sent_messages.append((str(cid), txt)) or True):
            r2 = dispatch.process_update(self._update(CHAT_RECEIVER, "ya, batalkan", update_id=41))

        self.assertTrue(r2["success"])
        self.assertEqual(turn2_res.get("draft_status"), "REJECTED")
        draft_doc = frappe.get_doc("Pending Action Draft", draft.name)
        self.assertEqual(draft_doc.status, "REJECTED")
        self.assertEqual(draft_doc.rejection_reason, "Stok kosong")
        self.assertEqual(draft_doc.modified_by, self.receiver)
        self.assertFalse(frappe.get_all("Sales Order", filters={"customer": cust_name}))

        customer_msgs = [txt for cid, txt in sent_messages if cid == CHAT_CUSTOMER]
        employee_msgs = [txt for cid, txt in sent_messages if cid == CHAT_RECEIVER]
        self.assertEqual(len(customer_msgs), 1)
        self.assertIn("Stok kosong", customer_msgs[0])
        self.assertEqual(len(employee_msgs), 1)
        self.assertIn("REJECTED", employee_msgs[0])

    def test_reply_intent_classification_variants_and_negation(self):
        from aios_v1.lib.erpnext_action_drafts import _classify_reply_intent

        for phrase in ("approve", "setujui", "boleh", "gas", "deal", "silakan", "silahkan", "ya, approve draf ini"):
            self.assertEqual(_classify_reply_intent(phrase, "approve"), "affirmative", phrase)

        self.assertEqual(_classify_reply_intent("tolak", "reject"), "affirmative")
        self.assertEqual(_classify_reply_intent("tolak draf ini", "reject"), "affirmative")
        self.assertEqual(_classify_reply_intent("jangan tolak", "reject"), "negative")
        self.assertEqual(_classify_reply_intent("tolak", "approve"), "neutral")
        self.assertEqual(_classify_reply_intent("Ongkir ke Jakarta berapa?", "approve"), "neutral")

    def test_sales_manager_telegram_system_prompt_directive_preserves_guest_persona(self):
        from aios_v1.managers.base_manager import BaseManager
        from aios_v1.plugin_manager.registry import get_branch

        mgr = BaseManager(get_branch("sales"))
        frappe.local.aios_channel = "telegram"
        try:
            emp_prompt = mgr.build_system_prompt(worker_def=None, user=self.receiver)
            guest_prompt = mgr.build_system_prompt(worker_def=None, user="Guest")
        finally:
            if hasattr(frappe.local, "aios_channel"):
                delattr(frappe.local, "aios_channel")

        self.assertIn("approve_draft", emp_prompt)
        self.assertIn("confirm_cash_payment", emp_prompt)
        self.assertIn("konfirmasi", emp_prompt.lower())
        self.assertNotIn("approve_draft", guest_prompt)
        self.assertNotIn("confirm_cash_payment", guest_prompt)
