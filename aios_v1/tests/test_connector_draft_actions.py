"""Integration tests for linked-employee Telegram draft actions (approve/reject/pay)."""

from __future__ import annotations

import json
from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime, nowdate

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore

from aios_v1.lib.connector import dispatch, linking, notify, telegram_client
from aios_v1.lib.draft_manager import approve_and_execute_draft, create_draft
from aios_v1.lib.erpnext_core_data import DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT
from aios_v1.lib.tool_registry import (
    DRAFT_TOOLS,
    GUEST_ALLOWED_TOOLS,
    execute_tool,
    get_tools_schema_for_worker,
)

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
        self.created_conversations: list[str] = []
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
        frappe.clear_document_cache("AIOS Setting", "AIOS Setting")

    def tearDown(self):
        frappe.set_user("Administrator")
        cache = frappe.cache()
        for draft_id in getattr(self, "created_drafts", []):
            for usr in (self.receiver, self.owner, self.staff):
                for act in ("approve", "reject", "confirm_cash_payment"):
                    cache.delete_value(f"aios_tg_confirm:{usr}:{act}:{draft_id}")
        self._cleanup_threads()
        for conv_id in getattr(self, "created_conversations", []):
            for msg_name in frappe.get_all("AIOS Message", filters={"conversation": str(conv_id)}, pluck="name"):
                frappe.delete_doc("AIOS Message", msg_name, ignore_permissions=True, force=True, delete_permanently=True)
            if frappe.db.exists("AIOS Conversation", str(conv_id)):
                frappe.delete_doc("AIOS Conversation", str(conv_id), ignore_permissions=True, force=True, delete_permanently=True)
        for cid in (CHAT_RECEIVER, CHAT_OWNER, CHAT_STAFF, CHAT_CUSTOMER):
            dispatch.clear_rate_limit(cid)
        for email in (RECEIVER, OWNER, STAFF):
            for conv_name in frappe.get_all("AIOS Conversation", filters={"user": email}, pluck="name"):
                for msg_name in frappe.get_all("AIOS Message", filters={"conversation": conv_name}, pluck="name"):
                    frappe.delete_doc("AIOS Message", msg_name, ignore_permissions=True, force=True, delete_permanently=True)
                frappe.delete_doc("AIOS Conversation", conv_name, ignore_permissions=True, force=True, delete_permanently=True)
            for usage_name in frappe.get_all("AIOS Token Usage", filters={"user": email}, pluck="name"):
                frappe.delete_doc("AIOS Token Usage", usage_name, ignore_permissions=True, force=True, delete_permanently=True)
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
            for tool_name in ("list_pending_drafts", "approve_draft", "reject_draft", "confirm_cash_payment"):
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

    def test_ekasa_desk_exposes_draft_tools_and_telegram_keeps_scope(self):
        from aios_v1.plugin_manager.registry import get_branch
        from aios_v1.setup import ensure_builtin_plugins

        ensure_builtin_plugins()
        subagent_key = get_branch("sales")["workers"][0]["key"]

        # Ekasa Desk (aios_channel tidak diset): manager sales non-Guest melihat DRAFT_TOOLS dan open_module; subagent & Guest tidak
        if hasattr(frappe.local, "aios_channel"):
            delattr(frappe.local, "aios_channel")
        web_manager_tools = {
            s["function"]["name"]
            for s in get_tools_schema_for_worker("sales", "manager", user=self.receiver)
        }
        self.assertTrue(DRAFT_TOOLS.issubset(web_manager_tools))
        self.assertIn("list_pending_drafts", web_manager_tools)
        self.assertIn("open_module", web_manager_tools)

        web_subagent_tools = {
            s["function"]["name"]
            for s in get_tools_schema_for_worker("sales", subagent_key, user=self.receiver)
        }
        self.assertTrue(web_subagent_tools.isdisjoint(DRAFT_TOOLS))

        web_guest_tools = {
            s["function"]["name"]
            for s in get_tools_schema_for_worker("sales", "manager", user="Guest")
        }
        self.assertEqual(web_guest_tools, set(GUEST_ALLOWED_TOOLS))
        self.assertTrue(web_guest_tools.isdisjoint(DRAFT_TOOLS))

        # Pada Telegram: manager non-Guest melihat 5 guest tool + 4 tool draf, tetap blokir open_module & laporan; subagent tidak melihat DRAFT_TOOLS
        frappe.local.aios_channel = "telegram"
        try:
            tg_manager_tools = {
                s["function"]["name"]
                for s in get_tools_schema_for_worker("sales", "manager", user=self.receiver)
            }
            self.assertTrue(DRAFT_TOOLS.issubset(tg_manager_tools))
            self.assertIn("list_pending_drafts", tg_manager_tools)
            self.assertNotIn("open_module", tg_manager_tools)
            self.assertNotIn("erpnext_report_run", tg_manager_tools)

            tg_subagent_tools = {
                s["function"]["name"]
                for s in get_tools_schema_for_worker("sales", subagent_key, user=self.receiver)
            }
            self.assertTrue(tg_subagent_tools.isdisjoint(DRAFT_TOOLS))

            frappe.set_user(self.receiver)
            for blocked_tool, raw_args in (
                ("open_module", json.dumps({"module": "sales_invoice"})),
                ("erpnext_report_run", "{}"),
            ):
                denied = json.loads(
                    execute_tool(
                        blocked_tool,
                        raw_args,
                        context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                    )
                )
                self.assertEqual(denied.get("code"), "TOOL_FORBIDDEN_ON_TELEGRAM")
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

            # 2b. Pertanyaan klarifikasi netral: LLM menjawab pertanyaan tanpa memanggil confirmed=True -> tidak dieksekusi
            neutral_tool_calls: list[str] = []

            def neutral_llm(messages, usage=None, tools=None, tool_calls=None):
                neutral_tool_calls.append("no-tool")
                yield f"Ongkir sesuai tarif normal. Apakah jadi setujui {draft.name}?"

            with patch("aios_v1.managers.base_manager.chat_stream", side_effect=neutral_llm), \
                 patch.object(telegram_client, "send_chat_action", return_value=True), \
                 patch.object(telegram_client, "send_message", side_effect=lambda cid, txt: sent_messages.append((str(cid), txt)) or True):
                r_neutral = dispatch.process_update(self._update(CHAT_RECEIVER, "Ongkir ke Jakarta berapa?", update_id=11))

            self.assertTrue(r_neutral["success"])
            self.assertEqual(len(neutral_tool_calls), 1)
            self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")
            self.assertFalse(frappe.get_all("Sales Order", filters={"customer": "_Test TG Confirm Guard Cust"}))

            # 3. Karyawan menolak: LLM tidak memanggil confirmed=True -> tidak ada eksekusi, draf tetap pending
            def decline_llm(messages, usage=None, tools=None, tool_calls=None):
                yield f"Baik, draf {draft.name} belum diproses dan tetap menunggu peninjauan."

            with patch("aios_v1.managers.base_manager.chat_stream", side_effect=decline_llm), \
                 patch.object(telegram_client, "send_chat_action", return_value=True), \
                 patch.object(telegram_client, "send_message", side_effect=lambda cid, txt: sent_messages.append((str(cid), txt)) or True):
                r_decline = dispatch.process_update(self._update(CHAT_RECEIVER, "tidak jadi bos, tahan dulu", update_id=12))

            self.assertTrue(r_decline["success"])
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

    def test_freeform_and_multilingual_confirmation_executes_and_token_guards_hold(self):
        # 1. Konfirmasi kalimat bebas bahasa Inggris (di luar daftar kata lama) mengeksekusi saat token + pesan baru valid
        cust_name = "_Test TG Freeform Confirm"
        draft = self._create_guest_order_draft(cust_name, qty=1)
        sent_messages: list[tuple[str, str]] = []
        turn1_res: dict = {}
        turn2_res: dict = {}

        def free_turn1_llm(messages, usage=None, tools=None, tool_calls=None):
            if messages[-1]["role"] != "tool":
                tool_calls.append(
                    {
                        "id": "ff1",
                        "function": {"name": "approve_draft", "arguments": json.dumps({"draft_id": draft.name})},
                    }
                )
                if False:
                    yield ""
                return
            turn1_res.update(json.loads(messages[-1]["content"]))
            yield f"Ringkasan draf {draft.name} sudah tampil. Silakan konfirmasi."

        def free_turn2_llm(messages, usage=None, tools=None, tool_calls=None):
            if messages[-1]["role"] != "tool":
                tool_calls.append(
                    {
                        "id": "ff2",
                        "function": {
                            "name": "approve_draft",
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
            yield f"Selesai: {turn2_res.get('sales_order')}"

        with patch("aios_v1.managers.base_manager.chat_stream", side_effect=free_turn1_llm), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(telegram_client, "send_message", side_effect=lambda cid, txt: sent_messages.append((str(cid), txt)) or True):
            r1 = dispatch.process_update(self._update(CHAT_RECEIVER, f"tolong approve {draft.name}", update_id=50))

        self.assertTrue(r1["success"])
        self.assertEqual(turn1_res.get("status"), "CONFIRMATION_REQUIRED")

        with patch("aios_v1.managers.base_manager.chat_stream", side_effect=free_turn2_llm), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(telegram_client, "send_message", side_effect=lambda cid, txt: sent_messages.append((str(cid), txt)) or True):
            r2 = dispatch.process_update(
                self._update(CHAT_RECEIVER, "Please go ahead and process it now", update_id=51)
            )

        self.assertTrue(r2["success"])
        self.assertTrue(turn2_res.get("executed"))
        so_name = turn2_res.get("sales_order")
        self.assertTrue(so_name and frappe.db.exists("Sales Order", so_name))
        so_doc = frappe.get_doc("Sales Order", so_name)
        self.assertEqual(so_doc.owner, self.receiver)
        self.assertEqual(so_doc.modified_by, self.receiver)

        # 2. Kalimat bebas non-keyword bahasa daerah untuk confirm_cash_payment (juga tanpa token dalam AIOS Conversation)
        cash_turn1: dict = {}
        cash_turn2: dict = {}

        def cash_free_1(messages, usage=None, tools=None, tool_calls=None):
            if messages[-1]["role"] != "tool":
                tool_calls.append(
                    {
                        "id": "cf1",
                        "function": {"name": "confirm_cash_payment", "arguments": json.dumps({"draft_id": draft.name})},
                    }
                )
                if False:
                    yield ""
                return
            cash_turn1.update(json.loads(messages[-1]["content"]))
            yield f"Konfirmasi cash {draft.name}."

        def cash_free_2(messages, usage=None, tools=None, tool_calls=None):
            if messages[-1]["role"] != "tool":
                tool_calls.append(
                    {
                        "id": "cf2",
                        "function": {
                            "name": "confirm_cash_payment",
                            "arguments": json.dumps({"draft_id": draft.name, "confirmed": True}),
                        },
                    }
                )
                if False:
                    yield ""
                return
            cash_turn2.update(json.loads(messages[-1]["content"]))
            yield f"Cash masuk: {cash_turn2.get('payment_entry')}"

        with patch("aios_v1.managers.base_manager.chat_stream", side_effect=cash_free_1), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(telegram_client, "send_message", return_value=True):
            dispatch.process_update(self._update(CHAT_RECEIVER, f"catat cash {draft.name}", update_id=52))
        self.assertEqual(cash_turn1.get("status"), "CONFIRMATION_REQUIRED")

        with patch("aios_v1.managers.base_manager.chat_stream", side_effect=cash_free_2), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(telegram_client, "send_message", return_value=True):
            dispatch.process_update(self._update(CHAT_RECEIVER, "mangga sikat ayeuna", update_id=53))
        self.assertTrue(cash_turn2.get("payment_confirmed"))
        pe_doc = frappe.get_doc("Payment Entry", cash_turn2["payment_entry"])
        self.assertEqual(pe_doc.owner, self.receiver)

        # 3. Guard token: di luar AIOS Conversation wajib token; salah token, salah aksi/draf, expired TTL, dan replay ditolak
        draft_guard = self._create_guest_order_draft("_Test TG Token Guard", qty=1)
        draft_other = self._create_guest_order_draft("_Test TG Token Guard Other", qty=1)
        frappe.local.aios_channel = "telegram"
        try:
            frappe.set_user(self.receiver)
            issued = json.loads(
                execute_tool(
                    "approve_draft",
                    json.dumps({"draft_id": draft_guard.name}),
                    context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(issued.get("status"), "CONFIRMATION_REQUIRED")
            valid_tok = issued["confirmation_token"]

            # Token dari draft_guard dipakai untuk draft_other ditolak
            wrong_draft = json.loads(
                execute_tool(
                    "approve_draft",
                    json.dumps({"draft_id": draft_other.name, "confirmed": True, "confirmation_token": valid_tok}),
                    context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(wrong_draft.get("status"), "CONFIRMATION_REQUIRED")
            self.assertFalse(wrong_draft.get("executed"))

            # Tanpa token di luar AIOS Conversation ditolak
            no_tok = json.loads(
                execute_tool(
                    "approve_draft",
                    json.dumps({"draft_id": draft_guard.name, "confirmed": True}),
                    context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(no_tok.get("status"), "CONFIRMATION_REQUIRED")
            self.assertFalse(no_tok.get("executed"))

            # Token salah ditolak
            wrong_tok = json.loads(
                execute_tool(
                    "approve_draft",
                    json.dumps({"draft_id": draft_guard.name, "confirmed": True, "confirmation_token": "wrong-token"}),
                    context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(wrong_tok.get("status"), "CONFIRMATION_REQUIRED")
            self.assertFalse(wrong_tok.get("executed"))

            # Token valid diterbitkan ulang saat langkah validasi gagal di atas; uji salah aksi & salah draf + expired TTL
            latest_tok = wrong_tok["confirmation_token"]
            wrong_action = json.loads(
                execute_tool(
                    "reject_draft",
                    json.dumps({"draft_id": draft_guard.name, "confirmed": True, "confirmation_token": latest_tok}),
                    context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(wrong_action.get("status"), "CONFIRMATION_REQUIRED")
            self.assertFalse(wrong_action.get("executed"))

            # Simulasi tantangan kedaluwarsa (TTL 300 detik habis / dihapus dari cache)
            frappe.cache().delete_value(f"aios_tg_confirm:{self.receiver}:approve:{draft_guard.name}")
            expired = json.loads(
                execute_tool(
                    "approve_draft",
                    json.dumps({"draft_id": draft_guard.name, "confirmed": True, "confirmation_token": latest_tok}),
                    context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(expired.get("status"), "CONFIRMATION_REQUIRED")
            self.assertFalse(expired.get("executed"))
            self.assertEqual(frappe.db.get_value("Pending Action Draft", draft_guard.name, "status"), "PENDING_APPROVAL")

            # Eksekusi sukses sekali dengan token aktif terbaru, lalu replay token yang sama ditolak
            fresh_tok = expired["confirmation_token"]
            with patch.object(telegram_client, "send_message", return_value=True):
                ok_res = json.loads(
                    execute_tool(
                        "approve_draft",
                        json.dumps({"draft_id": draft_guard.name, "confirmed": True, "confirmation_token": fresh_tok}),
                        context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                    )
                )
            self.assertTrue(ok_res.get("executed"))
            so_guard_name = ok_res.get("sales_order")
            self.assertTrue(so_guard_name and frappe.db.exists("Sales Order", so_guard_name))
            so_before_replay = frappe.db.count("Sales Order")
            self.assertIsNone(frappe.cache().get_value(f"aios_tg_confirm:{self.receiver}:approve:{draft_guard.name}"))
            replay_res = json.loads(
                execute_tool(
                    "approve_draft",
                    json.dumps({"draft_id": draft_guard.name, "confirmed": True, "confirmation_token": fresh_tok}),
                    context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertTrue(replay_res.get("already_executed"))
            self.assertEqual(replay_res.get("sales_order"), so_guard_name)
            self.assertEqual(frappe.db.count("Sales Order"), so_before_replay)

            # Conversation tanpa baris user AIOS Message (issued_user_msg kosong) tidak boleh mengeksekusi confirmed=True
            no_msg_ctx = {
                "user": self.receiver,
                "branch": "sales",
                "worker_key": "manager",
                "conversation_id": "CONV-NO-USER-MSG",
            }
            empty_conv_req = json.loads(
                execute_tool("approve_draft", json.dumps({"draft_id": draft_other.name}), context=no_msg_ctx)
            )
            self.assertEqual(empty_conv_req.get("status"), "CONFIRMATION_REQUIRED")
            empty_conv_exec = json.loads(
                execute_tool(
                    "approve_draft",
                    json.dumps({"draft_id": draft_other.name, "confirmed": True}),
                    context=no_msg_ctx,
                )
            )
            self.assertEqual(empty_conv_exec.get("code"), "CONFIRMATION_PENDING_USER_REPLY")
            self.assertFalse(empty_conv_exec.get("executed"))
            self.assertEqual(
                frappe.db.get_value("Pending Action Draft", draft_other.name, "status"), "PENDING_APPROVAL"
            )
        finally:
            if hasattr(frappe.local, "aios_channel"):
                delattr(frappe.local, "aios_channel")

    def test_sales_manager_draft_protocol_prompt_parity_preserves_guest_and_scope(self):
        from aios_v1.managers.base_manager import BaseManager
        from aios_v1.plugin_manager.registry import get_branch

        sales_mgr = BaseManager(get_branch("sales"))
        finance_mgr = BaseManager(get_branch("finance"))
        sales_subagent = sales_mgr.branch["workers"][0]

        protocol_elements = [
            "approve_draft",
            "reject_draft",
            "confirm_cash_payment",
            "list_pending_drafts",
            "confirmed=true",
            "WAJIB panggil tool terlebih dahulu",
            "Sales Order",
            "Payment Entry",
            "memanggil tool yang sama LAGI dengan `confirmed=true`",
            "TANPA `confirmation_token`",
            "JANGAN mengarang token atau memanggil ulang tanpa `confirmed=true`",
            "kalimat bebas",
            "1. Untuk menyetujui draf (`approve_draft`)",
            "2. Tampilkan ringkasan persis sesuai data tool",
            "3. Jika pada pesan berikutnya karyawan menjawab ya/setuju/konfirmasi",
            "4. Jika karyawan menjawab tidak/batal",
            "5. Setelah eksekusi berhasil, sampaikan nomor dokumen resmi",
            "6. Jika karyawan menanyakan draf apa yang sedang pending",
            "WAJIB panggil tool `list_pending_drafts` terlebih dahulu",
            "JANGAN menyimpulkan atau menebak dari data `Sales Order`",
            "JANGAN pernah menjawab belum ada draf baru tanpa memanggil `list_pending_drafts`",
            "expired=true",
        ]
        old_header_token = " ".join(["PROTOKOL", "AKSI", "DRAF", "TELEGRAM"])

        try:
            # 1. Telegram dan Ekasa Desk (aios_channel unset)
            for channel in ("telegram", None):
                if channel:
                    frappe.local.aios_channel = channel
                elif hasattr(frappe.local, "aios_channel"):
                    delattr(frappe.local, "aios_channel")

                emp_prompt = sales_mgr.build_system_prompt(worker_def=None, user=self.receiver)
                guest_prompt = sales_mgr.build_system_prompt(worker_def=None, user="Guest")

                # Karyawan berwenang mendapatkan header kanal-netral dan 4 langkah protokol
                self.assertIn("PROTOKOL AKSI DRAF (KARYAWAN BERWENANG):", emp_prompt)
                self.assertNotIn(old_header_token, emp_prompt)
                for line in emp_prompt.splitlines():
                    if "PROTOKOL AKSI DRAF" in line:
                        self.assertNotIn("TELEGRAM", line)

                for elem in protocol_elements:
                    self.assertIn(elem, emp_prompt)

                # 2. Guest persona tetap terlindungi di kedua kanal
                self.assertNotIn("approve_draft", guest_prompt)
                self.assertNotIn("reject_draft", guest_prompt)
                self.assertNotIn("confirm_cash_payment", guest_prompt)
                self.assertNotIn("list_pending_drafts", guest_prompt)
                self.assertNotIn("PROTOKOL AKSI DRAF", guest_prompt)

            # 3. Ekasa Desk: finance manager dan sales sub-agent tidak memuat protokol aksi draf
            if hasattr(frappe.local, "aios_channel"):
                delattr(frappe.local, "aios_channel")

            finance_prompt = finance_mgr.build_system_prompt(worker_def=None, user=self.receiver)
            subagent_prompt = sales_mgr.build_system_prompt(worker_def=sales_subagent, user=self.receiver)

            self.assertNotIn("PROTOKOL AKSI DRAF", finance_prompt)
            self.assertNotIn("list_pending_drafts", finance_prompt)
            self.assertNotIn("PROTOKOL AKSI DRAF", subagent_prompt)
            self.assertNotIn("list_pending_drafts", subagent_prompt)
        finally:
            if hasattr(frappe.local, "aios_channel"):
                delattr(frappe.local, "aios_channel")

    def _clear_channel_context(self) -> None:
        if hasattr(frappe.local, "aios_channel"):
            delattr(frappe.local, "aios_channel")
        if hasattr(frappe.local, "aios_channel_thread"):
            delattr(frappe.local, "aios_channel_thread")
        self.assertIsNone(getattr(frappe.local, "aios_channel", None))

    def _create_ekasa_conversation(self, user: str, branch: str = "sales") -> int:
        conv = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": user,
                "branch": branch,
                "title": f"Ekasa Desk {branch}",
            }
        ).insert(ignore_permissions=True)
        self.created_conversations.append(str(conv.name))
        return int(conv.name)

    def _run_ekasa_stream(
        self,
        user_message: str,
        conversation_id: int,
        user: str,
        llm_side_effect,
        sent_messages: list[tuple[str, str]] | None = None,
        branch: str = "sales",
    ) -> tuple[list[dict], str]:
        from aios_v1.managers.base_manager import BaseManager
        from aios_v1.plugin_manager.registry import get_branch
        from aios_v1.setup import ensure_builtin_plugins

        ensure_builtin_plugins()
        self._clear_channel_context()
        prev_user = frappe.session.user
        frappe.set_user(user)
        send_patch = (
            patch.object(
                telegram_client,
                "send_message",
                side_effect=lambda cid, txt: sent_messages.append((str(cid), txt)) or True,
            )
            if sent_messages is not None
            else patch.object(telegram_client, "send_message", return_value=True)
        )
        try:
            with patch("aios_v1.managers.base_manager.chat_stream", side_effect=llm_side_effect), send_patch:
                raw_chunks = list(
                    BaseManager(get_branch(branch)).handle_stream(
                        user_message=user_message,
                        conversation_id=conversation_id,
                        user=user,
                    )
                )
        finally:
            frappe.set_user(prev_user)
            self._clear_channel_context()

        events: list[dict] = []
        for chunk in raw_chunks:
            for line in (chunk or "").splitlines():
                stripped = line.strip()
                if stripped.startswith("data:"):
                    events.append(json.loads(stripped[5:].strip()))
        reply = "".join(evt.get("text") or "" for evt in events if evt.get("type") == "delta")
        return events, reply

    def _assert_ekasa_sales_protocol_and_tools(self, system_prompt: str, tool_names: set[str]) -> None:
        self.assertTrue(DRAFT_TOOLS.issubset(tool_names))
        self.assertIn("open_module", tool_names)
        self.assertIn("PROTOKOL AKSI DRAF (KARYAWAN BERWENANG):", system_prompt)
        for step in (
            "1. Untuk menyetujui draf (`approve_draft`)",
            "2. Tampilkan ringkasan persis sesuai data tool",
            "3. Jika pada pesan berikutnya karyawan menjawab ya/setuju/konfirmasi",
            "4. Jika karyawan menjawab tidak/batal",
            "5. Setelah eksekusi berhasil, sampaikan nomor dokumen resmi",
            "6. Jika karyawan menanyakan draf apa yang sedang pending",
        ):
            self.assertIn(step, system_prompt)
        self.assertIn("`list_pending_drafts`", system_prompt)
        self.assertIn("JANGAN menyimpulkan atau menebak dari data `Sales Order`", system_prompt)
        self.assertIn("expired=true", system_prompt)

    def _make_tool_turn_llm(
        self,
        tool_name: str,
        args_fn,
        result_out: dict,
        reply_fn,
        inspect_round1=None,
    ):
        def fake_llm(messages, usage=None, tools=None, tool_calls=None):
            if messages[-1]["role"] != "tool":
                if inspect_round1:
                    inspect_round1(messages, tools)
                tool_calls.append(
                    {
                        "id": f"ekasa_{tool_name}",
                        "function": {"name": tool_name, "arguments": json.dumps(args_fn())},
                    }
                )
                if False:
                    yield ""
                return
            result_out.update(json.loads(messages[-1]["content"]))
            yield reply_fn(result_out)

        return fake_llm

    def test_ekasa_desk_approve_draft_two_turns_with_natural_reply_sets_audit_and_notifies_customer(self):
        cust_name = "_Test Ekasa Approve Two Turns"
        draft = self._create_guest_order_draft(cust_name, qty=2)
        conv_id = self._create_ekasa_conversation(self.receiver, "sales")
        sent_messages: list[tuple[str, str]] = []
        turn1_res: dict = {}
        turn2_res: dict = {}
        seen_turn1: dict = {}

        def inspect_t1(messages, tools):
            seen_turn1["system_prompt"] = messages[0]["content"]
            seen_turn1["tool_names"] = {t["function"]["name"] for t in (tools or [])}

        def inspect_t2(messages, _tools):
            self.assertTrue(
                any(m.get("role") == "assistant" and draft.name in (m.get("content") or "") for m in messages)
            )

        def _t1_reply(res: dict) -> str:
            s = res["summary"]
            item_desc = ", ".join(f"{it['item_name']} x{it['qty']}" for it in s["items"])
            return (
                f"Konfirmasi setujui draf {s['draft_id']} untuk {s['customer']}, "
                f"item: {item_desc}, total {s['formatted_total']}. Balas ya atau tidak."
            )

        events1, reply1 = self._run_ekasa_stream(
            f"setujui draf {draft.name}",
            conv_id,
            self.receiver,
            self._make_tool_turn_llm(
                "approve_draft",
                lambda: {"draft_id": draft.name},
                turn1_res,
                _t1_reply,
                inspect_round1=inspect_t1,
            ),
            sent_messages=sent_messages,
        )

        self._assert_ekasa_sales_protocol_and_tools(seen_turn1["system_prompt"], seen_turn1["tool_names"])
        self.assertTrue(any(e.get("type") == "meta" and e.get("conversationId") == conv_id for e in events1))
        self.assertTrue(any(e.get("type") == "done" for e in events1))
        self.assertEqual(turn1_res.get("status"), "CONFIRMATION_REQUIRED")
        self.assertTrue(turn1_res.get("confirmation_token"))
        cache_key = f"aios_tg_confirm:{self.receiver}:approve:{draft.name}"
        self.assertIsNotNone(frappe.cache().get_value(cache_key))
        self.assertEqual(turn1_res["summary"]["customer"], cust_name)
        self.assertTrue(turn1_res["summary"]["formatted_total"])
        self.assertIn(self.item_name, json.dumps(turn1_res["summary"]["items"]))
        self.assertIn(cust_name, reply1)
        self.assertIn(draft.name, reply1)
        self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")
        self.assertFalse(frappe.get_all("Sales Order", filters={"customer": cust_name}))
        self.assertEqual(sent_messages, [])

        events2, reply2 = self._run_ekasa_stream(
            "ya lanjutkan, proses sekarang",
            conv_id,
            self.receiver,
            self._make_tool_turn_llm(
                "approve_draft",
                lambda: {
                    "draft_id": draft.name,
                    "confirmed": True,
                    "confirmation_token": turn1_res["confirmation_token"],
                },
                turn2_res,
                lambda res: f"Draf {draft.name} berhasil disetujui. Nomor Sales Order: {res['sales_order']} (status: {res['draft_status']}).",
                inspect_round1=inspect_t2,
            ),
            sent_messages=sent_messages,
        )

        self.assertTrue(any(e.get("type") == "done" for e in events2))
        self.assertTrue(turn2_res.get("executed"))
        so_name = turn2_res.get("sales_order")
        self.assertTrue(so_name and frappe.db.exists("Sales Order", so_name))
        self.assertIsNone(frappe.cache().get_value(cache_key))

        msgs = frappe.get_all(
            "AIOS Message",
            filters={"conversation": str(conv_id)},
            fields=["role", "content"],
            order_by="name asc",
        )
        self.assertEqual([m["role"] for m in msgs], ["user", "manager", "user", "manager"])

        so_doc = frappe.get_doc("Sales Order", so_name)
        draft_doc = frappe.get_doc("Pending Action Draft", draft.name)
        self.assertEqual(so_doc.docstatus, 1)
        self.assertEqual(so_doc.owner, self.receiver)
        self.assertEqual(so_doc.modified_by, self.receiver)
        self.assertEqual(draft_doc.status, "EXECUTED")
        self.assertEqual(draft_doc.modified_by, self.receiver)
        self.assertIn(so_name, reply2)

        customer_msgs = [txt for cid, txt in sent_messages if cid == CHAT_CUSTOMER]
        self.assertEqual(len(customer_msgs), 1)
        self.assertIn("disetujui", customer_msgs[0].lower())
        for internal_ref in (so_name, draft.name, "SO-", "DRF-"):
            self.assertNotIn(internal_ref, customer_msgs[0])
        self.assertEqual([txt for cid, txt in sent_messages if cid == CHAT_RECEIVER], [])

        # Sub-kasus: konfirmasi natural dalam AIOS Conversation yang sama (LLM kirim confirmed=True tanpa token setelah giliran baru)
        draft2 = self._create_guest_order_draft("_Test Ekasa Approve Natural Sub", qty=1)
        sub_t1: dict = {}
        sub_t2: dict = {}
        self._run_ekasa_stream(
            f"setujui draf {draft2.name}",
            conv_id,
            self.receiver,
            self._make_tool_turn_llm(
                "approve_draft",
                lambda: {"draft_id": draft2.name},
                sub_t1,
                lambda res: f"Konfirmasi {draft2.name} ({res['summary']['customer']}).",
            ),
        )
        self.assertEqual(sub_t1.get("status"), "CONFIRMATION_REQUIRED")

        self._run_ekasa_stream(
            "oke lanjut eksekusi sekarang",
            conv_id,
            self.receiver,
            self._make_tool_turn_llm(
                "approve_draft",
                lambda: {"draft_id": draft2.name, "confirmed": True},
                sub_t2,
                lambda res: f"Sales Order {res.get('sales_order')} selesai.",
            ),
        )
        self.assertTrue(sub_t2.get("executed"))
        sub_so_name = sub_t2.get("sales_order")
        self.assertTrue(sub_so_name and frappe.db.exists("Sales Order", sub_so_name))
        sub_so_doc = frappe.get_doc("Sales Order", sub_so_name)
        self.assertEqual(sub_so_doc.owner, self.receiver)
        self.assertEqual(sub_so_doc.modified_by, self.receiver)
        self.assertIsNone(frappe.cache().get_value(f"aios_tg_confirm:{self.receiver}:approve:{draft2.name}"))

    def test_ekasa_desk_two_turns_without_token_executes_all_draft_actions_without_loop(self):
        # 1. approve_draft: 2 turns without confirmation_token in Turn 2
        cust_approve = "_Test Ekasa NoTok Approve"
        draft_approve = self._create_guest_order_draft(cust_approve, qty=2)
        conv_approve = self._create_ekasa_conversation(self.receiver, "sales")
        t1_approve_res: dict = {}
        t2_approve_res: dict = {}
        inspected_t2_approve: list[bool] = []

        self._run_ekasa_stream(
            f"setujui draf {draft_approve.name}",
            conv_approve,
            self.receiver,
            self._make_tool_turn_llm(
                "approve_draft",
                lambda: {"draft_id": draft_approve.name},
                t1_approve_res,
                lambda res: f"Konfirmasi {res['summary']['draft_id']} ({res['summary']['customer']}). Ya/tidak?",
            ),
        )
        self.assertEqual(t1_approve_res.get("status"), "CONFIRMATION_REQUIRED")
        tok_approve = t1_approve_res.get("confirmation_token")
        self.assertTrue(tok_approve)

        def inspect_approve_t2(messages, _tools):
            self.assertTrue(all(m.get("role") != "tool" for m in messages))
            self.assertNotIn(tok_approve, json.dumps(messages))
            inspected_t2_approve.append(True)

        self._run_ekasa_stream(
            "Ya",
            conv_approve,
            self.receiver,
            self._make_tool_turn_llm(
                "approve_draft",
                lambda: {"draft_id": draft_approve.name, "confirmed": True},
                t2_approve_res,
                lambda res: f"Sales Order {res.get('sales_order')} selesai.",
                inspect_round1=inspect_approve_t2,
            ),
        )
        self.assertTrue(inspected_t2_approve)
        self.assertNotEqual(t2_approve_res.get("status"), "CONFIRMATION_REQUIRED")
        self.assertNotEqual(t2_approve_res.get("status"), "CONFIRMATION_PENDING_USER_REPLY")
        self.assertTrue(t2_approve_res.get("executed"))
        so_name = t2_approve_res.get("sales_order")
        self.assertTrue(so_name and frappe.db.exists("Sales Order", so_name))
        so_doc = frappe.get_doc("Sales Order", so_name)
        self.assertEqual(so_doc.docstatus, 1)
        self.assertEqual(so_doc.owner, self.receiver)
        self.assertEqual(so_doc.modified_by, self.receiver)

        # 2. reject_draft: 2 turns without confirmation_token and without repeating reason in Turn 2
        cust_reject = "_Test Ekasa NoTok Reject"
        draft_reject = self._create_guest_order_draft(cust_reject, qty=1)
        conv_reject = self._create_ekasa_conversation(self.receiver, "sales")
        t1_reject_res: dict = {}
        t2_reject_res: dict = {}
        inspected_t2_reject: list[bool] = []

        self._run_ekasa_stream(
            f"tolak draf {draft_reject.name} karena stok kosong",
            conv_reject,
            self.receiver,
            self._make_tool_turn_llm(
                "reject_draft",
                lambda: {"draft_id": draft_reject.name, "reason": "Stok kosong"},
                t1_reject_res,
                lambda res: f"Konfirmasi tolak draf {draft_reject.name} alasan {res['summary']['reason']}. Ya/tidak?",
            ),
        )
        self.assertEqual(t1_reject_res.get("status"), "CONFIRMATION_REQUIRED")
        tok_reject = t1_reject_res.get("confirmation_token")
        self.assertTrue(tok_reject)
        self.assertEqual(t1_reject_res["summary"]["reason"], "Stok kosong")

        def inspect_reject_t2(messages, _tools):
            self.assertTrue(all(m.get("role") != "tool" for m in messages))
            self.assertNotIn(tok_reject, json.dumps(messages))
            inspected_t2_reject.append(True)

        self._run_ekasa_stream(
            "oke sip lanjutkan",
            conv_reject,
            self.receiver,
            self._make_tool_turn_llm(
                "reject_draft",
                lambda: {"draft_id": draft_reject.name, "confirmed": True},
                t2_reject_res,
                lambda res: f"Draf {draft_reject.name} ditolak (status: {res.get('draft_status')}).",
                inspect_round1=inspect_reject_t2,
            ),
        )
        self.assertTrue(inspected_t2_reject)
        self.assertNotEqual(t2_reject_res.get("status"), "CONFIRMATION_REQUIRED")
        self.assertNotEqual(t2_reject_res.get("status"), "CONFIRMATION_PENDING_USER_REPLY")
        self.assertEqual(t2_reject_res.get("draft_status"), "REJECTED")
        draft_doc_rej = frappe.get_doc("Pending Action Draft", draft_reject.name)
        self.assertEqual(draft_doc_rej.status, "REJECTED")
        self.assertEqual(draft_doc_rej.rejection_reason, "Stok kosong")
        self.assertEqual(draft_doc_rej.modified_by, self.receiver)
        self.assertFalse(frappe.get_all("Sales Order", filters={"customer": cust_reject}))

        # 3. confirm_cash_payment: 2 turns without confirmation_token in Turn 2
        cust_cash = "_Test Ekasa NoTok Cash"
        draft_cash = self._create_guest_order_draft(cust_cash, qty=1)
        frappe.set_user(self.receiver)
        try:
            with patch.object(telegram_client, "send_message", return_value=True):
                exec_res = approve_and_execute_draft(draft_cash.name)
        finally:
            frappe.set_user("Administrator")
        cash_so_name = exec_res["name"]
        self.assertTrue(cash_so_name and frappe.db.exists("Sales Order", cash_so_name))

        conv_cash = self._create_ekasa_conversation(self.receiver, "sales")
        t1_cash_res: dict = {}
        t2_cash_res: dict = {}
        inspected_t2_cash: list[bool] = []

        self._run_ekasa_stream(
            f"konfirmasi bayar cash draf {draft_cash.name}",
            conv_cash,
            self.receiver,
            self._make_tool_turn_llm(
                "confirm_cash_payment",
                lambda: {"draft_id": draft_cash.name},
                t1_cash_res,
                lambda res: f"Konfirmasi bayar Cash {res['summary']['draft_id']}. Ya/tidak?",
            ),
        )
        self.assertEqual(t1_cash_res.get("status"), "CONFIRMATION_REQUIRED")
        tok_cash = t1_cash_res.get("confirmation_token")
        self.assertTrue(tok_cash)

        def inspect_cash_t2(messages, _tools):
            self.assertTrue(all(m.get("role") != "tool" for m in messages))
            self.assertNotIn(tok_cash, json.dumps(messages))
            inspected_t2_cash.append(True)

        self._run_ekasa_stream(
            "gas konfirmasi cash",
            conv_cash,
            self.receiver,
            self._make_tool_turn_llm(
                "confirm_cash_payment",
                lambda: {"draft_id": draft_cash.name, "confirmed": True},
                t2_cash_res,
                lambda res: f"Payment Entry {res.get('payment_entry')} selesai.",
                inspect_round1=inspect_cash_t2,
            ),
        )
        self.assertTrue(inspected_t2_cash)
        self.assertNotEqual(t2_cash_res.get("status"), "CONFIRMATION_REQUIRED")
        self.assertNotEqual(t2_cash_res.get("status"), "CONFIRMATION_PENDING_USER_REPLY")
        self.assertTrue(t2_cash_res.get("payment_confirmed"))
        pe_name = t2_cash_res.get("payment_entry")
        self.assertTrue(pe_name and frappe.db.exists("Payment Entry", pe_name))
        pe_doc = frappe.get_doc("Payment Entry", pe_name)
        self.assertEqual(pe_doc.docstatus, 1)
        self.assertEqual(pe_doc.owner, self.receiver)
        self.assertEqual(pe_doc.modified_by, self.receiver)
        pe_refs = frappe.get_all(
            "Payment Entry Reference",
            filters={"parent": pe_name, "reference_name": cash_so_name, "docstatus": 1},
        )
        self.assertEqual(len(pe_refs), 1)

        # 4. Guard verification:
        # a. Token salah/buatan ("token-ngarang") pada Turn 2 dalam AIOS Conversation yang sama ditolak
        draft_fake = self._create_guest_order_draft("_Test Ekasa Fake Tok Guard", qty=1)
        conv_guard = self._create_ekasa_conversation(self.receiver, "sales")
        t1_fake: dict = {}
        t2_fake: dict = {}

        self._run_ekasa_stream(
            f"setujui draf {draft_fake.name}",
            conv_guard,
            self.receiver,
            self._make_tool_turn_llm(
                "approve_draft",
                lambda: {"draft_id": draft_fake.name},
                t1_fake,
                lambda res: f"Konfirmasi {res['summary']['draft_id']}. Ya/tidak?",
            ),
        )
        self.assertEqual(t1_fake.get("status"), "CONFIRMATION_REQUIRED")

        self._run_ekasa_stream(
            "ya",
            conv_guard,
            self.receiver,
            self._make_tool_turn_llm(
                "approve_draft",
                lambda: {"draft_id": draft_fake.name, "confirmed": True, "confirmation_token": "token-ngarang"},
                t2_fake,
                lambda _res: "Token salah.",
            ),
        )
        self.assertEqual(t2_fake.get("status"), "CONFIRMATION_REQUIRED")
        self.assertFalse(t2_fake.get("executed"))
        self.assertEqual(frappe.db.get_value("Pending Action Draft", draft_fake.name, "status"), "PENDING_APPROVAL")
        self.assertFalse(frappe.get_all("Sales Order", filters={"customer": "_Test Ekasa Fake Tok Guard"}))

        # b. Di luar AIOS Conversation (tanpa conversation_id), confirmed=True tanpa token tetap ditolak CONFIRMATION_REQUIRED
        draft_no_conv = self._create_guest_order_draft("_Test Guard No Conv", qty=1)
        frappe.set_user(self.receiver)
        try:
            issued = json.loads(
                execute_tool(
                    "approve_draft",
                    json.dumps({"draft_id": draft_no_conv.name}),
                    context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(issued.get("status"), "CONFIRMATION_REQUIRED")
            no_conv_res = json.loads(
                execute_tool(
                    "approve_draft",
                    json.dumps({"draft_id": draft_no_conv.name, "confirmed": True}),
                    context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
        finally:
            frappe.set_user("Administrator")
        self.assertEqual(no_conv_res.get("status"), "CONFIRMATION_REQUIRED")
        self.assertFalse(no_conv_res.get("executed"))
        self.assertEqual(frappe.db.get_value("Pending Action Draft", draft_no_conv.name, "status"), "PENDING_APPROVAL")
        self.assertFalse(frappe.get_all("Sales Order", filters={"customer": "_Test Guard No Conv"}))

    def test_ekasa_desk_list_pending_drafts_then_two_step_approve_workflow(self):
        cust_name = "_Test Ekasa List Then Approve"
        draft = self._create_guest_order_draft(cust_name, qty=2)
        conv_id = self._create_ekasa_conversation(self.receiver, "sales")
        sent_messages: list[tuple[str, str]] = []
        turn1_list_res: dict = {}
        turn2_approve_res: dict = {}
        turn3_exec_res: dict = {}
        seen_turn1: dict = {}

        def inspect_t1(messages, tools):
            seen_turn1["system_prompt"] = messages[0]["content"]
            seen_turn1["tool_names"] = {t["function"]["name"] for t in (tools or [])}

        def _t1_reply(res: dict) -> str:
            d_list = ", ".join(f"{d['draft_id']} ({d['customer']})" for d in res.get("drafts", []))
            return f"Draf pending saat ini: {d_list}. Balas dengan draf yang ingin disetujui."

        # Turn 1: Karyawan meminta daftar draf pending -> AI memanggil list_pending_drafts
        events1, reply1 = self._run_ekasa_stream(
            "ada draf apa saja yang pending?",
            conv_id,
            self.receiver,
            self._make_tool_turn_llm(
                "list_pending_drafts",
                lambda: {},
                turn1_list_res,
                _t1_reply,
                inspect_round1=inspect_t1,
            ),
            sent_messages=sent_messages,
        )

        self._assert_ekasa_sales_protocol_and_tools(seen_turn1["system_prompt"], seen_turn1["tool_names"])
        self.assertTrue(any(e.get("type") == "done" for e in events1))
        self.assertEqual(turn1_list_res.get("status"), "ok")
        self.assertGreaterEqual(turn1_list_res.get("count", 0), 1)
        found_draft = next((d for d in turn1_list_res.get("drafts", []) if d["draft_id"] == draft.name), None)
        self.assertIsNotNone(found_draft)
        self.assertEqual(found_draft["customer"], cust_name)
        self.assertFalse(found_draft["expired"])
        self.assertIn(draft.name, reply1)
        # Verifikasi bahwa data Sales Order belum dibuat dan status draf masih PENDING_APPROVAL
        self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")
        self.assertFalse(frappe.get_all("Sales Order", filters={"customer": cust_name}))

        # Turn 2: Karyawan memilih draf untuk disetujui -> AI panggil approve_draft tanpa confirmed=True (tantangan konfirmasi)
        def _t2_reply(res: dict) -> str:
            s = res["summary"]
            return f"Konfirmasi setujui draf {s['draft_id']} untuk {s['customer']} total {s['formatted_total']}. Balas ya atau tidak."

        events2, reply2 = self._run_ekasa_stream(
            f"setujui draf {draft.name}",
            conv_id,
            self.receiver,
            self._make_tool_turn_llm(
                "approve_draft",
                lambda: {"draft_id": draft.name},
                turn2_approve_res,
                _t2_reply,
            ),
            sent_messages=sent_messages,
        )

        self.assertTrue(any(e.get("type") == "done" for e in events2))
        self.assertEqual(turn2_approve_res.get("status"), "CONFIRMATION_REQUIRED")
        self.assertTrue(turn2_approve_res.get("confirmation_token"))
        cache_key = f"aios_tg_confirm:{self.receiver}:approve:{draft.name}"
        self.assertIsNotNone(frappe.cache().get_value(cache_key))
        self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")
        self.assertFalse(frappe.get_all("Sales Order", filters={"customer": cust_name}))
        self.assertIn(draft.name, reply2)

        # Turn 3: Karyawan konfirmasi "ya" -> AI panggil approve_draft dengan confirmed=True
        events3, reply3 = self._run_ekasa_stream(
            "ya setuju, lanjutkan",
            conv_id,
            self.receiver,
            self._make_tool_turn_llm(
                "approve_draft",
                lambda: {
                    "draft_id": draft.name,
                    "confirmed": True,
                    "confirmation_token": turn2_approve_res["confirmation_token"],
                },
                turn3_exec_res,
                lambda res: f"Draf {draft.name} berhasil disetujui. Nomor Sales Order: {res['sales_order']}.",
            ),
            sent_messages=sent_messages,
        )

        self.assertTrue(any(e.get("type") == "done" for e in events3))
        self.assertTrue(turn3_exec_res.get("executed"))
        so_name = turn3_exec_res.get("sales_order")
        self.assertTrue(so_name and frappe.db.exists("Sales Order", so_name))
        self.assertIsNone(frappe.cache().get_value(cache_key))

        draft_doc = frappe.get_doc("Pending Action Draft", draft.name)
        so_doc = frappe.get_doc("Sales Order", so_name)
        self.assertEqual(draft_doc.status, "EXECUTED")
        self.assertEqual(draft_doc.modified_by, self.receiver)
        self.assertEqual(so_doc.docstatus, 1)
        self.assertEqual(so_doc.owner, self.receiver)
        self.assertEqual(so_doc.modified_by, self.receiver)
        self.assertIn(so_name, reply3)

    def test_ekasa_desk_confirm_cash_payment_two_turns_sets_payment_entry_audit_and_notifies_customer(self):
        cust_name = "_Test Ekasa Cash Pay Two Turns"
        draft = self._create_guest_order_draft(cust_name, qty=1)
        frappe.set_user(self.receiver)
        try:
            with patch.object(telegram_client, "send_message", return_value=True):
                exec_res = approve_and_execute_draft(draft.name)
        finally:
            frappe.set_user("Administrator")
        so_name = exec_res["name"]

        conv_id = self._create_ekasa_conversation(self.receiver, "sales")
        sent_messages: list[tuple[str, str]] = []
        turn1_res: dict = {}
        turn2_res: dict = {}

        _, reply1 = self._run_ekasa_stream(
            f"sudah bayar cash draf {draft.name}",
            conv_id,
            self.receiver,
            self._make_tool_turn_llm(
                "confirm_cash_payment",
                lambda: {"draft_id": draft.name},
                turn1_res,
                lambda res: (
                    f"Konfirmasi bayar Cash draf {res['summary']['draft_id']} ({res['summary']['sales_order']}) "
                    f"untuk {res['summary']['customer']} total {res['summary']['formatted_total']}. Ya/tidak?"
                ),
            ),
            sent_messages=sent_messages,
        )

        self.assertEqual(turn1_res.get("status"), "CONFIRMATION_REQUIRED")
        self.assertEqual(turn1_res["summary"]["sales_order"], so_name)
        self.assertEqual(turn1_res["summary"]["customer"], cust_name)
        self.assertIn(so_name, reply1)
        self.assertEqual(
            frappe.get_all("Payment Entry Reference", filters={"reference_name": so_name, "docstatus": 1}),
            [],
        )
        self.assertEqual(sent_messages, [])

        _, reply2 = self._run_ekasa_stream(
            "uang cash sudah diterima, konfirmasi",
            conv_id,
            self.receiver,
            self._make_tool_turn_llm(
                "confirm_cash_payment",
                lambda: {
                    "draft_id": draft.name,
                    "confirmed": True,
                    "confirmation_token": turn1_res["confirmation_token"],
                },
                turn2_res,
                lambda res: f"Pembayaran Cash tercatat: {res['payment_entry']} untuk {res['sales_order']} (status: lunas).",
            ),
            sent_messages=sent_messages,
        )

        self.assertTrue(turn2_res.get("payment_confirmed"))
        pe_name = turn2_res.get("payment_entry")
        self.assertTrue(pe_name and frappe.db.exists("Payment Entry", pe_name))
        self.assertIsNone(frappe.cache().get_value(f"aios_tg_confirm:{self.receiver}:confirm_cash_payment:{draft.name}"))

        pe_doc = frappe.get_doc("Payment Entry", pe_name)
        so_doc = frappe.get_doc("Sales Order", so_name)
        draft_doc = frappe.get_doc("Pending Action Draft", draft.name)
        self.assertEqual(pe_doc.docstatus, 1)
        self.assertEqual(pe_doc.mode_of_payment, "Cash")
        self.assertGreater(float(pe_doc.paid_amount or 0), 0)
        self.assertEqual(float(so_doc.advance_paid or 0), float(pe_doc.paid_amount))
        self.assertEqual(pe_doc.owner, self.receiver)
        self.assertEqual(pe_doc.modified_by, self.receiver)
        self.assertEqual(so_doc.owner, self.receiver)
        self.assertEqual(so_doc.modified_by, self.receiver)
        self.assertEqual(draft_doc.modified_by, self.receiver)
        self.assertIn(pe_name, reply2)
        self.assertIn(so_name, reply2)

        customer_msgs = [txt for cid, txt in sent_messages if cid == CHAT_CUSTOMER]
        self.assertEqual(len(customer_msgs), 1)
        self.assertIn("pembayaran cash anda sebesar", customer_msgs[0].lower())
        for internal_ref in (pe_name, so_name, draft.name, "PE-", "SO-", "DRF-"):
            self.assertNotIn(internal_ref, customer_msgs[0])
        self.assertEqual([txt for cid, txt in sent_messages if cid == CHAT_RECEIVER], [])

    def test_ekasa_desk_reject_draft_two_turns_sets_modified_by_and_notifies_customer(self):
        cust_name = "_Test Ekasa Reject Two Turns"
        draft = self._create_guest_order_draft(cust_name, qty=1)
        conv_id = self._create_ekasa_conversation(self.receiver, "sales")
        sent_messages: list[tuple[str, str]] = []
        turn1_res: dict = {}
        turn2_res: dict = {}

        _, reply1 = self._run_ekasa_stream(
            f"tolak draf {draft.name} karena stok kosong",
            conv_id,
            self.receiver,
            self._make_tool_turn_llm(
                "reject_draft",
                lambda: {"draft_id": draft.name, "reason": "Stok kosong"},
                turn1_res,
                lambda res: f"Konfirmasi tolak draf {draft.name} ({res['summary']['customer']}) alasan Stok kosong. Ya/tidak?",
            ),
            sent_messages=sent_messages,
        )

        self.assertEqual(turn1_res.get("status"), "CONFIRMATION_REQUIRED")
        self.assertEqual(turn1_res["summary"]["reason"], "Stok kosong")
        self.assertIn(cust_name, reply1)
        self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")
        self.assertFalse(frappe.get_all("Sales Order", filters={"customer": cust_name}))
        self.assertEqual(sent_messages, [])

        _, reply2 = self._run_ekasa_stream(
            "ya tolak karena stok kosong",
            conv_id,
            self.receiver,
            self._make_tool_turn_llm(
                "reject_draft",
                lambda: {
                    "draft_id": draft.name,
                    "confirmed": True,
                    "confirmation_token": turn1_res["confirmation_token"],
                },
                turn2_res,
                lambda res: f"Draf {draft.name} telah ditolak (status: {res['draft_status']}).",
            ),
            sent_messages=sent_messages,
        )

        self.assertEqual(turn2_res.get("draft_status"), "REJECTED")
        self.assertIsNone(frappe.cache().get_value(f"aios_tg_confirm:{self.receiver}:reject:{draft.name}"))
        draft_doc = frappe.get_doc("Pending Action Draft", draft.name)
        self.assertEqual(draft_doc.status, "REJECTED")
        self.assertEqual(draft_doc.rejection_reason, "Stok kosong")
        self.assertEqual(draft_doc.modified_by, self.receiver)
        self.assertFalse(frappe.get_all("Sales Order", filters={"customer": cust_name}))
        self.assertIn("REJECTED", reply2)
        self.assertIn(draft.name, reply2)

        customer_msgs = [txt for cid, txt in sent_messages if cid == CHAT_CUSTOMER]
        self.assertEqual(len(customer_msgs), 1)
        self.assertIn("Stok kosong", customer_msgs[0])
        self.assertIn("belum dapat disetujui", customer_msgs[0].lower())
        for internal_ref in (draft.name, "DRF-", "SO-"):
            self.assertNotIn(internal_ref, customer_msgs[0])
        self.assertEqual([txt for cid, txt in sent_messages if cid == CHAT_RECEIVER], [])

    def test_ekasa_desk_guards_same_turn_bypass_decline_and_unauthorized_staff(self):
        cust_name = "_Test Ekasa Guard Cust"
        draft = self._create_guest_order_draft(cust_name, qty=1)
        conv_id = self._create_ekasa_conversation(self.receiver, "sales")
        sent_messages: list[tuple[str, str]] = []
        round_results: list[dict] = []
        turn_state = {"calls": 0}

        # 1. Bypass se-turn (confirmed=True pada giliran yang sama meski membawa token) ditolak CONFIRMATION_PENDING_USER_REPLY
        def same_turn_bypass_llm(messages, usage=None, tools=None, tool_calls=None):
            turn_state["calls"] += 1
            if turn_state["calls"] == 1:
                tool_calls.append(
                    {
                        "id": "ek_bypass_1",
                        "function": {"name": "approve_draft", "arguments": json.dumps({"draft_id": draft.name})},
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
                        "id": "ek_bypass_2",
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
            round_results.append(json.loads(messages[-1]["content"]))
            yield f"Mohon konfirmasi setujui {draft.name} (ya/tidak)."

        self._run_ekasa_stream(
            f"setujui draf {draft.name}",
            conv_id,
            self.receiver,
            same_turn_bypass_llm,
            sent_messages=sent_messages,
        )

        self.assertEqual(round_results[0].get("status"), "CONFIRMATION_REQUIRED")
        self.assertEqual(round_results[1].get("code"), "CONFIRMATION_PENDING_USER_REPLY")
        self.assertEqual(round_results[1].get("status"), "CONFIRMATION_PENDING_USER_REPLY")
        self.assertFalse(round_results[1].get("executed"))
        self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")
        self.assertFalse(frappe.get_all("Sales Order", filters={"customer": cust_name}))
        self.assertEqual(sent_messages, [])

        # 2. Token salah pada giliran berikutnya juga ditolak dan tidak mengeksekusi draf
        wrong_tok_res: dict = {}
        self._run_ekasa_stream(
            "ya teruskan",
            conv_id,
            self.receiver,
            self._make_tool_turn_llm(
                "approve_draft",
                lambda: {"draft_id": draft.name, "confirmed": True, "confirmation_token": "invalid-token"},
                wrong_tok_res,
                lambda _res: f"Token tidak cocok, konfirmasi ulang {draft.name}.",
            ),
            sent_messages=sent_messages,
        )
        self.assertEqual(wrong_tok_res.get("status"), "CONFIRMATION_REQUIRED")
        self.assertFalse(wrong_tok_res.get("executed"))
        self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")

        # 3. Pertanyaan netral & penolakan tidak mengeksekusi draf
        def neutral_llm(messages, usage=None, tools=None, tool_calls=None):
            yield f"Ongkir sesuai tarif ekspedisi. Apakah draf {draft.name} tetap ingin disetujui?"

        def decline_llm(messages, usage=None, tools=None, tool_calls=None):
            yield f"Baik, draf {draft.name} ditunda dan tidak diproses."

        self._run_ekasa_stream(
            "Ongkir ke Surabaya kira-kira berapa?",
            conv_id,
            self.receiver,
            neutral_llm,
            sent_messages=sent_messages,
        )
        self._run_ekasa_stream(
            "tidak jadi dulu, batalkan saja prosesnya",
            conv_id,
            self.receiver,
            decline_llm,
            sent_messages=sent_messages,
        )
        self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")
        self.assertFalse(frappe.get_all("Sales Order", filters={"customer": cust_name}))
        self.assertEqual(sent_messages, [])

        # 4. Staf non-berwenang di Ekasa Desk ditolak NOT_AUTHORIZED pada draf kanal & non-kanal
        non_channel_draft = create_draft(
            task_id=f"TEST-EKASA-NONCH-{frappe.generate_hash(length=6)}",
            action_type="CREATE",
            payload={
                "doctype": "Sales Order",
                "data": {
                    "customer": cust_name,
                    "company": self.company,
                    "selling_price_list": self.price_list,
                    "transaction_date": nowdate(),
                    "delivery_date": nowdate(),
                    "items": [
                        {
                            "item_code": self.item_code,
                            "qty": 1,
                            "rate": self.item_rate,
                            "delivery_date": nowdate(),
                        }
                    ],
                },
            },
            branch="sales",
            created_by_agent="manager",
            user=self.receiver,
        )
        self.created_drafts.append(non_channel_draft.name)

        self._clear_channel_context()
        frappe.set_user(self.staff)
        try:
            for tool_name in ("approve_draft", "reject_draft", "confirm_cash_payment"):
                staff_res = json.loads(
                    execute_tool(
                        tool_name,
                        json.dumps({"draft_id": draft.name}),
                        context={"user": self.staff, "branch": "sales", "worker_key": "manager"},
                    )
                )
                self.assertEqual(staff_res.get("code"), "NOT_AUTHORIZED")

            non_ch_res = json.loads(
                execute_tool(
                    "approve_draft",
                    json.dumps({"draft_id": non_channel_draft.name}),
                    context={"user": self.staff, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(non_ch_res.get("code"), "NOT_AUTHORIZED")

            # 5. Tamu (Guest) di Ekasa Desk ditolak GUEST_TOOL_FORBIDDEN dan tidak melihat DRAFT_TOOLS
            frappe.set_user("Guest")
            guest_tools = {
                s["function"]["name"]
                for s in get_tools_schema_for_worker("sales", "manager", user="Guest")
            }
            self.assertTrue(guest_tools.isdisjoint(DRAFT_TOOLS))
            for tool_name in ("list_pending_drafts", "approve_draft", "reject_draft", "confirm_cash_payment"):
                guest_res = json.loads(
                    execute_tool(
                        tool_name,
                        json.dumps({"draft_id": draft.name, "confirmed": True}),
                        context={"user": "Guest", "branch": "sales", "worker_key": "manager"},
                    )
                )
                self.assertEqual(guest_res.get("code"), "GUEST_TOOL_FORBIDDEN")
        finally:
            frappe.set_user("Administrator")

        self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "PENDING_APPROVAL")
        self.assertEqual(frappe.db.get_value("Pending Action Draft", non_channel_draft.name, "status"), "PENDING_APPROVAL")
        self.assertFalse(frappe.get_all("Sales Order", filters={"customer": cust_name}))

    def test_so_to_draft_resolution_for_cash_payment_approve_not_found_and_auth(self):
        cust_name = "_Test SO Resolve Cash Pay"
        draft = self._create_guest_order_draft(cust_name, qty=1)
        frappe.set_user(self.receiver)
        try:
            with patch.object(telegram_client, "send_message", return_value=True):
                exec_res = approve_and_execute_draft(draft.name)
        finally:
            frappe.set_user("Administrator")
        so_name = exec_res["name"]

        try:
            # (a) confirm_cash_payment dengan nomor SO menyelesaikan pembayaran 2 langkah draf yang benar
            frappe.set_user(self.receiver)
            step1 = json.loads(
                execute_tool(
                    "confirm_cash_payment",
                    json.dumps({"draft_id": so_name}),
                    context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(step1.get("status"), "CONFIRMATION_REQUIRED")
            self.assertEqual(step1.get("draft_id"), draft.name)
            self.assertEqual(step1["summary"]["sales_order"], so_name)

            with patch.object(telegram_client, "send_message", return_value=True):
                step2 = json.loads(
                    execute_tool(
                        "confirm_cash_payment",
                        json.dumps(
                            {
                                "draft_id": so_name,
                                "confirmed": True,
                                "confirmation_token": step1["confirmation_token"],
                            }
                        ),
                        context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                    )
                )
            self.assertEqual(step2.get("status"), "success")
            self.assertTrue(step2.get("payment_confirmed"))
            self.assertEqual(step2.get("draft_id"), draft.name)
            self.assertEqual(step2.get("sales_order"), so_name)
            pe_name = step2.get("payment_entry")
            self.assertTrue(pe_name and frappe.db.exists("Payment Entry", pe_name))

            # (b) approve_draft dengan nomor SO yang sudah dieksekusi mengembalikan sudah EXECUTED + nomor SO
            already_res = json.loads(
                execute_tool(
                    "approve_draft",
                    json.dumps({"draft_id": so_name}),
                    context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(already_res.get("status"), "success")
            self.assertEqual(already_res.get("draft_id"), draft.name)
            self.assertEqual(already_res.get("draft_status"), "EXECUTED")
            self.assertTrue(already_res.get("already_executed"))
            self.assertEqual(already_res.get("sales_order"), so_name)
            self.assertIn("EXECUTED", already_res.get("message", ""))
            self.assertIn(so_name, already_res.get("message", ""))

            # (c1) Nomor SO yang tidak ada mengembalikan DRAFT_NOT_FOUND
            for tool_name in ("approve_draft", "reject_draft", "confirm_cash_payment"):
                missing_res = json.loads(
                    execute_tool(
                        tool_name,
                        json.dumps({"draft_id": "SAL-ORD-2099-99999"}),
                        context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                    )
                )
                self.assertEqual(missing_res.get("code"), "DRAFT_NOT_FOUND")

            # (d) Wewenang tetap ditegakkan pada draf hasil resolusi
            frappe.set_user(self.staff)
            for tool_name in ("approve_draft", "reject_draft", "confirm_cash_payment"):
                unauth_res = json.loads(
                    execute_tool(
                        tool_name,
                        json.dumps({"draft_id": so_name}),
                        context={"user": self.staff, "branch": "sales", "worker_key": "manager"},
                    )
                )
                self.assertEqual(unauth_res.get("code"), "NOT_AUTHORIZED")

            # (c2) Jika >1 draf EXECUTED merujuk nomor SO yang sama (ambigu), kembalikan DRAFT_NOT_FOUND
            frappe.set_user("Administrator")
            dup_draft = frappe.get_doc(
                {
                    "doctype": "Pending Action Draft",
                    "task_id": f"TEST-SO-DUP-{frappe.generate_hash(length=6)}",
                    "action_type": "CREATE",
                    "type": "CREATE",
                    "branch": "sales",
                    "created_by_agent": "manager",
                    "user": self.receiver,
                    "status": "EXECUTED",
                    "payload": json.dumps({"doctype": "Sales Order", "result": {"name": so_name, "document": so_name}}),
                }
            )
            dup_draft.flags.ignore_mandatory = True
            dup_draft.insert(ignore_permissions=True)
            self.created_drafts.append(dup_draft.name)

            frappe.set_user(self.receiver)
            ambig_res = json.loads(
                execute_tool(
                    "approve_draft",
                    json.dumps({"draft_id": so_name}),
                    context={"user": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(ambig_res.get("code"), "DRAFT_NOT_FOUND")
        finally:
            frappe.set_user("Administrator")


class TestListPendingDrafts(TestConnectorDraftActions):
    def _create_custom_draft(
        self,
        customer_name: str,
        user: str | None = None,
        status: str = "PENDING_APPROVAL",
        expires_at=None,
        is_channel: bool = True,
        raw_payload: str | None = None,
    ):
        self.created_customers.append(customer_name)
        if raw_payload is not None:
            payload_str = raw_payload
        else:
            payload = {
                "doctype": "Sales Order",
                "data": {
                    "customer": customer_name,
                    "company": self.company,
                    "selling_price_list": self.price_list,
                    "transaction_date": nowdate(),
                    "delivery_date": nowdate(),
                    "items": [
                        {
                            "item_code": self.item_code,
                            "qty": 2,
                            "rate": self.item_rate,
                            "delivery_date": nowdate(),
                        }
                    ],
                },
                "customer_info": {
                    "customer_type": "Individual",
                    "customer_name": customer_name,
                    "payment_method": "Cash",
                },
                "reason": "Draft test",
            }
            if is_channel:
                payload["source_telegram_chat_id"] = CHAT_CUSTOMER
            payload_str = json.dumps(payload)

        exp_val = add_to_date(now_datetime(), hours=24) if expires_at is None else (None if expires_at == "NONE" else expires_at)
        draft = frappe.get_doc(
            {
                "doctype": "Pending Action Draft",
                "task_id": f"TEST-LIST-{frappe.generate_hash(length=8)}",
                "action_type": "CREATE",
                "type": "Sales Order",
                "branch": "sales",
                "created_by_agent": "manager",
                "user": user or self.receiver,
                "status": status,
                "payload": payload_str,
                "expires_at": exp_val,
            }
        )
        draft.flags.ignore_mandatory = True
        draft.insert(ignore_permissions=True)
        self.created_drafts.append(draft.name)
        if is_channel:
            nlog = frappe.get_doc(
                {
                    "doctype": "Notification Log",
                    "subject": f"AIOS Channel Alert: {draft.name}",
                    "type": "AIOS Channel Alert",
                    "document_type": "Pending Action Draft",
                    "document_name": draft.name,
                    "for_user": self.receiver,
                }
            )
            nlog.insert(ignore_permissions=True)
        return draft

    def test_list_returns_only_pending_approval_ordered_with_summary(self):
        d_pending1 = self._create_custom_draft("Cust Pending 1", status="PENDING_APPROVAL", is_channel=True)
        d_pending2 = self._create_custom_draft("Cust Pending 2", status="PENDING_APPROVAL", is_channel=True)
        d_approved = self._create_custom_draft("Cust Approved", status="APPROVED", is_channel=True)
        d_executed = self._create_custom_draft("Cust Executed", status="EXECUTED", is_channel=True)
        d_rejected = self._create_custom_draft("Cust Rejected", status="REJECTED", is_channel=True)
        d_expired = self._create_custom_draft("Cust Expired", status="EXPIRED", is_channel=True)

        raw = execute_tool(
            "list_pending_drafts",
            "{}",
            context={"user_id": self.receiver, "branch": "sales", "worker_key": "manager"},
        )
        res = json.loads(raw)
        self.assertEqual(res.get("status"), "ok")
        drafts = res.get("drafts", [])
        draft_ids = [d["draft_id"] for d in drafts]

        self.assertIn(d_pending1.name, draft_ids)
        self.assertIn(d_pending2.name, draft_ids)
        self.assertNotIn(d_approved.name, draft_ids)
        self.assertNotIn(d_executed.name, draft_ids)
        self.assertNotIn(d_rejected.name, draft_ids)
        self.assertNotIn(d_expired.name, draft_ids)

        idx1 = draft_ids.index(d_pending1.name)
        idx2 = draft_ids.index(d_pending2.name)
        self.assertLess(idx2, idx1)

        item = next(d for d in drafts if d["draft_id"] == d_pending2.name)
        required_keys = {
            "draft_id", "doctype", "customer", "currency", "total", "formatted_total",
            "items", "type", "branch", "status", "creation", "expires_at", "expired"
        }
        self.assertTrue(required_keys.issubset(set(item.keys())), f"Missing keys: {required_keys - set(item.keys())}")
        self.assertEqual(item["status"], "PENDING_APPROVAL")
        self.assertEqual(item["customer"], "Cust Pending 2")
        self.assertEqual(item["doctype"], "Sales Order")
        self.assertEqual(item["branch"], "sales")
        self.assertIsInstance(item["items"], list)
        self.assertIsInstance(item["expired"], bool)

    def test_limit_handling_defaults_caps_and_rejects_invalid(self):
        res_default = json.loads(
            execute_tool(
                "list_pending_drafts",
                "{}",
                context={"user_id": self.receiver, "branch": "sales", "worker_key": "manager"},
            )
        )
        self.assertEqual(res_default.get("status"), "ok")
        self.assertEqual(res_default.get("limit"), DEFAULT_LIST_LIMIT)

        res_none = json.loads(
            execute_tool(
                "list_pending_drafts",
                json.dumps({"limit": None}),
                context={"user_id": self.receiver, "branch": "sales", "worker_key": "manager"},
            )
        )
        self.assertEqual(res_none.get("status"), "ok")
        self.assertEqual(res_none.get("limit"), DEFAULT_LIST_LIMIT)

        res_custom = json.loads(
            execute_tool(
                "list_pending_drafts",
                json.dumps({"limit": 2}),
                context={"user_id": self.receiver, "branch": "sales", "worker_key": "manager"},
            )
        )
        self.assertEqual(res_custom.get("status"), "ok")
        self.assertEqual(res_custom.get("limit"), 2)

        res_capped = json.loads(
            execute_tool(
                "list_pending_drafts",
                json.dumps({"limit": 150}),
                context={"user_id": self.receiver, "branch": "sales", "worker_key": "manager"},
            )
        )
        self.assertEqual(res_capped.get("status"), "ok")
        self.assertEqual(res_capped.get("limit"), MAX_LIST_LIMIT)

        for invalid_val in (0, -1, True, False, "abc", [10], {"limit": 10}):
            res_invalid = json.loads(
                execute_tool(
                    "list_pending_drafts",
                    json.dumps({"limit": invalid_val}),
                    context={"user_id": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertFalse(res_invalid.get("success", True), f"limit={invalid_val!r} should fail")
            self.assertTrue(res_invalid.get("error"), f"limit={invalid_val!r} should have error message")
            self.assertEqual(res_invalid.get("code"), "INVALID_LIMIT", f"limit={invalid_val!r} should be INVALID_LIMIT")

    def test_cross_user_visibility_no_starvation_and_has_more_accurate(self):
        init_res = json.loads(
            execute_tool(
                "list_pending_drafts",
                json.dumps({"limit": 100}),
                context={"user_id": self.receiver, "branch": "sales", "worker_key": "manager"},
            )
        )
        base_count = init_res.get("count", 0)

        d_c1 = self._create_custom_draft("Cust Starv C1", user=self.receiver, is_channel=True)
        self._create_custom_draft("Cust Starv S1", user=self.staff, is_channel=False)
        d_c2 = self._create_custom_draft("Cust Starv C2", user=self.receiver, is_channel=True)
        self._create_custom_draft("Cust Starv S2", user=self.staff, is_channel=False)
        d_c3 = self._create_custom_draft("Cust Starv C3", user=self.receiver, is_channel=True)

        res_lim2 = json.loads(
            execute_tool(
                "list_pending_drafts",
                json.dumps({"limit": 2}),
                context={"user_id": self.receiver, "branch": "sales", "worker_key": "manager"},
            )
        )
        self.assertEqual(res_lim2.get("status"), "ok")
        self.assertEqual(len(res_lim2.get("drafts", [])), 2)
        rec_ids2 = [d["draft_id"] for d in res_lim2.get("drafts", [])]
        self.assertEqual(rec_ids2, [d_c3.name, d_c2.name])
        self.assertTrue(res_lim2.get("has_more"))

        total_expected = 3 + base_count
        res_all = json.loads(
            execute_tool(
                "list_pending_drafts",
                json.dumps({"limit": total_expected}),
                context={"user_id": self.receiver, "branch": "sales", "worker_key": "manager"},
            )
        )
        self.assertEqual(res_all.get("status"), "ok")
        self.assertEqual(len(res_all.get("drafts", [])), total_expected)
        rec_ids_all = [d["draft_id"] for d in res_all.get("drafts", [])]
        self.assertEqual(rec_ids_all[:3], [d_c3.name, d_c2.name, d_c1.name])
        self.assertFalse(res_all.get("has_more"))

    def test_expired_flag_reflects_expires_at_relative_to_now(self):
        past_dt = add_to_date(now_datetime(), hours=-2)
        future_dt = add_to_date(now_datetime(), hours=2)

        d_past = self._create_custom_draft("Cust Exp Past", expires_at=past_dt, is_channel=True)
        d_future = self._create_custom_draft("Cust Exp Future", expires_at=future_dt, is_channel=True)
        d_none = self._create_custom_draft("Cust Exp None", expires_at="NONE", is_channel=True)

        raw = execute_tool(
            "list_pending_drafts",
            "{}",
            context={"user_id": self.receiver, "branch": "sales", "worker_key": "manager"},
        )
        res = json.loads(raw)
        self.assertEqual(res.get("status"), "ok")
        drafts_by_id = {d["draft_id"]: d for d in res.get("drafts", [])}

        self.assertIn(d_past.name, drafts_by_id)
        self.assertTrue(drafts_by_id[d_past.name]["expired"])

        self.assertIn(d_future.name, drafts_by_id)
        self.assertFalse(drafts_by_id[d_future.name]["expired"])

        self.assertIn(d_none.name, drafts_by_id)
        self.assertFalse(drafts_by_id[d_none.name]["expired"])
        self.assertEqual(drafts_by_id[d_none.name]["expires_at"], "")

    def test_empty_list_returns_clean_response(self):
        res = json.loads(
            execute_tool(
                "list_pending_drafts",
                "{}",
                context={"user_id": self.staff, "branch": "sales", "worker_key": "manager"},
            )
        )
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("drafts"), [])
        self.assertEqual(res.get("count"), 0)
        self.assertFalse(res.get("has_more"))
        self.assertTrue(res.get("message"))
        self.assertIn("tidak ada", res.get("message").lower())

    def test_authorization_and_visibility_scenarios(self):
        res_guest = json.loads(
            execute_tool(
                "list_pending_drafts",
                "{}",
                context={"user_id": "Guest", "branch": "sales", "worker_key": "manager"},
            )
        )
        self.assertEqual(res_guest.get("code"), "GUEST_TOOL_FORBIDDEN")

        res_unauth = json.loads(
            execute_tool(
                "list_pending_drafts",
                "{}",
                context={"user_id": "_unknown_user@example.com", "branch": "sales", "worker_key": "manager"},
            )
        )
        self.assertEqual(res_unauth.get("code"), "NOT_AUTHORIZED")

        disabled_email = "_test.tg.draft.disabled@example.com"
        _ensure_user(disabled_email, "_Test Disabled User")
        frappe.db.set_value("User", disabled_email, "enabled", 0)
        try:
            res_disabled = json.loads(
                execute_tool(
                    "list_pending_drafts",
                    "{}",
                    context={"user_id": disabled_email, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(res_disabled.get("code"), "NOT_AUTHORIZED")
        finally:
            if frappe.db.exists("User", disabled_email):
                frappe.delete_doc("User", disabled_email, ignore_permissions=True, force=True, delete_permanently=True)

        no_client_email = "_test.tg.draft.noclient@example.com"
        _ensure_user(no_client_email, "_Test No Client User")
        frappe.db.delete("Has Role", {"parent": no_client_email, "parenttype": "User", "role": "AIOS Client"})
        frappe.clear_cache(user=no_client_email)
        try:
            res_no_client = json.loads(
                execute_tool(
                    "list_pending_drafts",
                    "{}",
                    context={"user_id": no_client_email, "branch": "sales", "worker_key": "manager"},
                )
            )
            self.assertEqual(res_no_client.get("code"), "NOT_AUTHORIZED")
        finally:
            if frappe.db.exists("User", no_client_email):
                frappe.delete_doc("User", no_client_email, ignore_permissions=True, force=True, delete_permanently=True)

        d_ch = self._create_custom_draft("Cust Owner Chan", user=self.owner, is_channel=True)
        res_receiver = json.loads(
            execute_tool(
                "list_pending_drafts",
                "{}",
                context={"user_id": self.receiver, "branch": "sales", "worker_key": "manager"},
            )
        )
        receiver_ids = [d["draft_id"] for d in res_receiver.get("drafts", [])]
        self.assertIn(d_ch.name, receiver_ids)

        res_staff = json.loads(
            execute_tool(
                "list_pending_drafts",
                "{}",
                context={"user_id": self.staff, "branch": "sales", "worker_key": "manager"},
            )
        )
        staff_ids = [d["draft_id"] for d in res_staff.get("drafts", [])]
        self.assertNotIn(d_ch.name, staff_ids)

        d_staff = self._create_custom_draft("Cust Staff NonChan", user=self.staff, is_channel=False)
        res_staff_own = json.loads(
            execute_tool(
                "list_pending_drafts",
                "{}",
                context={"user_id": self.staff, "branch": "sales", "worker_key": "manager"},
            )
        )
        staff_own_ids = [d["draft_id"] for d in res_staff_own.get("drafts", [])]
        self.assertIn(d_staff.name, staff_own_ids)

        res_rec_staff = json.loads(
            execute_tool(
                "list_pending_drafts",
                "{}",
                context={"user_id": self.receiver, "branch": "sales", "worker_key": "manager"},
            )
        )
        rec_ids = [d["draft_id"] for d in res_rec_staff.get("drafts", [])]
        self.assertNotIn(d_staff.name, rec_ids)

        frappe.db.delete("Has Role", {"parent": self.receiver, "parenttype": "User", "role": "AIOS Channel Receiver"})
        frappe.clear_cache(user=self.receiver)

        res_owner = json.loads(
            execute_tool(
                "list_pending_drafts",
                "{}",
                context={"user_id": self.owner, "branch": "sales", "worker_key": "manager"},
            )
        )
        owner_ids = [d["draft_id"] for d in res_owner.get("drafts", [])]
        self.assertIn(d_ch.name, owner_ids)

        res_ex_receiver = json.loads(
            execute_tool(
                "list_pending_drafts",
                "{}",
                context={"user_id": self.receiver, "branch": "sales", "worker_key": "manager"},
            )
        )
        ex_rec_ids = [d["draft_id"] for d in res_ex_receiver.get("drafts", [])]
        self.assertNotIn(d_ch.name, ex_rec_ids)

    def test_corrupt_payload_handled_safely_and_logged(self):
        d_corrupt = self._create_custom_draft("Cust Corrupt", raw_payload="not a valid json{", is_channel=True)
        d_valid = self._create_custom_draft("Cust Valid", is_channel=True)

        with patch("aios_v1.lib.erpnext_action_drafts.log_exception") as mock_log:
            res = json.loads(
                execute_tool(
                    "list_pending_drafts",
                    "{}",
                    context={"user_id": self.receiver, "branch": "sales", "worker_key": "manager"},
                )
            )
        self.assertEqual(res.get("status"), "ok")
        drafts = res.get("drafts", [])
        draft_ids = [d["draft_id"] for d in drafts]
        self.assertIn(d_valid.name, draft_ids)
        self.assertIn(d_corrupt.name, draft_ids)
        corrupt_item = next(d for d in drafts if d["draft_id"] == d_corrupt.name)
        self.assertEqual(corrupt_item["draft_id"], d_corrupt.name)
        self.assertTrue(mock_log.called)

    def test_limit_one_includes_has_more_suffix_when_more_drafts_exist(self):
        self._create_custom_draft("Cust Lim1 A", user=self.receiver, is_channel=True)
        self._create_custom_draft("Cust Lim1 B", user=self.receiver, is_channel=True)

        res_more = json.loads(
            execute_tool(
                "list_pending_drafts",
                json.dumps({"limit": 1}),
                context={"user_id": self.receiver, "branch": "sales", "worker_key": "manager"},
            )
        )
        self.assertEqual(res_more.get("status"), "ok")
        self.assertEqual(res_more.get("count"), 1)
        self.assertTrue(res_more.get("has_more"))
        self.assertEqual(
            res_more.get("message"),
            "Ditemukan 1 draf yang menunggu persetujuan (masih ada draf lainnya, tentukan limit lebih besar bila perlu).",
        )

        self._create_custom_draft("Cust Lim1 Single Staff", user=self.staff, is_channel=False)
        res_exact = json.loads(
            execute_tool(
                "list_pending_drafts",
                json.dumps({"limit": 1}),
                context={"user_id": self.staff, "branch": "sales", "worker_key": "manager"},
            )
        )
        self.assertEqual(res_exact.get("status"), "ok")
        self.assertEqual(res_exact.get("count"), 1)
        self.assertFalse(res_exact.get("has_more"))
        self.assertEqual(res_exact.get("message"), "Ditemukan 1 draf yang menunggu persetujuan.")
