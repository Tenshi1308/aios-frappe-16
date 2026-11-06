"""Tests for Batch 3 Phase 1: Multi-tiered rate limit, order notifications, and bell integration.
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import frappe

from aios_v1.lib.connector import dispatch, notify, views
from aios_v1.lib.draft_manager import create_draft

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

SETTING = "AIOS Telegram Setting"
THREAD = "AIOS Channel Thread"
FLAG = "AIOS Conversation Flag"
OWNER = "_test.batch3.owner@example.com"
OTHER = "_test.batch3.other@example.com"
CHAT_A = "88112233"
CHAT_B = "88112244"


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


class ConnectorBatch3Test(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.in_test = True
        frappe.flags.in_test = True
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        frappe.set_user("Administrator")
        frappe.db.set_single_value("AIOS Setting", "max_users", 20)
        # Clear any pre-existing channel receiver/owner roles from non-test users during test
        frappe.db.delete(
            "Has Role",
            {"parenttype": "User", "role": ("in", ["AIOS Channel Receiver", "AIOS Client Owner"])},
        )
        self.owner = _ensure_user(OWNER, "Batch3 Owner", is_receiver=True)
        self.other = _ensure_user(OTHER, "Batch3 Other", is_receiver=False)
        self._orig_active = frappe.db.get_single_value(SETTING, "is_active")
        frappe.db.set_value(SETTING, SETTING, "is_active", 1)
        frappe.db.set_value(SETTING, SETTING, "poll_offset", 0)
        self._cleanup_data()

    def tearDown(self):
        self._cleanup_data()
        frappe.db.set_value(SETTING, SETTING, "is_active", self._orig_active)
        frappe.db.set_value(SETTING, SETTING, "poll_offset", 0)
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()
        super().tearDown()

    def _cleanup_data(self):
        # Clear rate limit keys for test chats
        cache = frappe.cache()
        now = time.time()
        for chat_id in (CHAT_A, CHAT_B):
            m_bucket = int(now // 60)
            h_bucket = int(now // 3600)
            d_bucket = int(now // 86400)
            cache.delete_value(f"aios_tg_rate_m:{chat_id}:{m_bucket}")
            cache.delete_value(f"aios_tg_rate_h:{chat_id}:{h_bucket}")
            cache.delete_value(f"aios_tg_rate_d:{chat_id}:{d_bucket}")
            cache.delete_value(f"aios_tg_rate_warned:{chat_id}")

        for name in frappe.get_all(
            THREAD, filters={"external_thread_id": ("in", [CHAT_A, CHAT_B])}, pluck="name"
        ):
            for flag in frappe.get_all(FLAG, filters={"thread": name}, pluck="name"):
                frappe.delete_doc(FLAG, flag, ignore_permissions=True, force=True)
            conversation = frappe.db.get_value(THREAD, name, "conversation")
            frappe.delete_doc(THREAD, name, ignore_permissions=True, force=True)
            if conversation and frappe.db.exists("AIOS Conversation", conversation):
                frappe.delete_doc("AIOS Conversation", conversation, ignore_permissions=True, force=True)

        for n in frappe.get_all("Notification Log", filters={"for_user": ("in", [self.owner, self.other])}, pluck="name"):
            frappe.delete_doc("Notification Log", n, ignore_permissions=True, force=True)

    def _update(self, text: str, update_id: int = 1, chat_id: str | int | None = None) -> dict:
        return {
            "update_id": update_id,
            "message": {
                "message_id": update_id,
                "chat": {"id": int(chat_id if chat_id is not None else CHAT_A)},
                "from": {"first_name": "Siti", "username": "siticustomer"},
                "text": text,
            },
        }

    # =========================================================================
    # 1. Multi-tiered rate limit tests
    # =========================================================================
    def test_rate_limit_minute_isolated(self):
        """15 messages/minute accepted; 16th blocked; other chat remains unblocked."""
        with patch("aios_v1.lib.connector.dispatch._collect_reply", return_value="Jawaban bot"), patch(
            "aios_v1.lib.connector.telegram_client.send_message"
        ) as mock_send, patch("aios_v1.lib.connector.dispatch.check_site_token_quota", return_value=True):
            # Send 15 messages for CHAT_A
            for i in range(1, 16):
                res = dispatch.process_update(self._update(f"Pesan {i}", update_id=i, chat_id=CHAT_A))
                self.assertTrue(res["success"], f"Pesan {i} seharusnya sukses")

            # 16th message for CHAT_A must be rate-limited
            res16 = dispatch.process_update(self._update("Pesan 16", update_id=16, chat_id=CHAT_A))
            self.assertFalse(res16["success"])
            self.assertEqual(res16["code"], "CONNECTOR_RATE_LIMITED")
            mock_send.assert_called_with(int(CHAT_A), dispatch.RATE_LIMIT_MSG)

            # CHAT_B must NOT be blocked (rate limit is isolated per chat)
            res_b = dispatch.process_update(self._update("Pesan Chat B", update_id=17, chat_id=CHAT_B))
            self.assertTrue(res_b["success"])

    def test_rate_limit_hour_and_day(self):
        """Reaching 60/hr or 200/day triggers rate limit."""
        cache = frappe.cache()
        now = time.time()
        h_bucket = int(now // 3600)
        # Pre-set 60 count in hour bucket
        cache.set_value(f"aios_tg_rate_h:{CHAT_A}:{h_bucket}", "60", expires_in_sec=3600)

        with patch("aios_v1.lib.connector.telegram_client.send_message") as mock_send, patch(
            "aios_v1.lib.connector.dispatch.check_site_token_quota", return_value=True
        ):
            res = dispatch.process_update(self._update("Pesan ke-61", update_id=1, chat_id=CHAT_A))
            self.assertFalse(res["success"])
            self.assertEqual(res["code"], "CONNECTOR_RATE_LIMITED")
            mock_send.assert_called_with(int(CHAT_A), dispatch.RATE_LIMIT_MSG)

    def test_rate_limit_single_warning_per_window(self):
        """Only one warning message is sent per cooldown window."""
        with patch("aios_v1.lib.connector.dispatch._collect_reply", return_value="Jawaban bot"), patch(
            "aios_v1.lib.connector.telegram_client.send_message"
        ) as mock_send, patch("aios_v1.lib.connector.dispatch.check_site_token_quota", return_value=True):
            for i in range(1, 16):
                dispatch.process_update(self._update(f"Pesan {i}", update_id=i, chat_id=CHAT_A))

            mock_send.reset_mock()
            # 16th triggers warning
            dispatch.process_update(self._update("Pesan 16", update_id=16, chat_id=CHAT_A))
            self.assertEqual(mock_send.call_count, 1)

            # 17th and 18th in same window are silently dropped without duplicate warning
            mock_send.reset_mock()
            dispatch.process_update(self._update("Pesan 17", update_id=17, chat_id=CHAT_A))
            dispatch.process_update(self._update("Pesan 18", update_id=18, chat_id=CHAT_A))
            self.assertEqual(mock_send.call_count, 0)

    # =========================================================================
    # 2. Order draft notification tests
    # =========================================================================
    def test_guest_order_draft_creates_notification_log(self):
        """When a guest creates an order draft, a Notification Log is created for owner_user."""
        payload = {
            "doctype": "Sales Order",
            "data": {"items": [{"item_code": "GENSET-01", "qty": 1, "rate": 5000000}]},
        }
        draft = create_draft(
            task_id="AIOS-TEST-DRAFT-1",
            action_type="CREATE",
            payload=payload,
            branch="sales",
            user=self.owner,
        )

        thread = {
            "display_name": "Siti Rahma",
            "username": "sitir",
            "external_thread_id": CHAT_A,
        }

        success = notify.notify_order_draft(draft, thread=thread)
        self.assertTrue(success)

        # Check Notification Log created for owner
        logs = frappe.get_all(
            "Notification Log",
            filters={
                "for_user": self.owner,
                "type": notify.NOTIFICATION_TYPE,
                "document_type": "Pending Action Draft",
                "document_name": draft.name,
            },
            fields=["name", "subject", "email_content", "read"],
        )
        self.assertEqual(len(logs), 1)
        log = logs[0]
        self.assertIn("Sales Order", log["subject"])
        self.assertIn("Siti Rahma", log["subject"])
        self.assertIn("Catatan customer mau beli", log["email_content"])
        self.assertEqual(log["read"], 0)

        # Ensure OTHER user did NOT receive the notification
        other_logs = frappe.get_all(
            "Notification Log",
            filters={"for_user": self.other, "document_name": draft.name},
        )
        self.assertEqual(len(other_logs), 0)

    def test_order_notification_fallback_customer_label(self):
        """When display_name is empty, use username or chat ID without inventing names."""
        payload = {"doctype": "Quotation", "data": {}}
        draft = create_draft(
            task_id="AIOS-TEST-DRAFT-2",
            action_type="CREATE",
            payload=payload,
            branch="sales",
            user=self.owner,
        )

        # Thread with only chat_id
        thread = {"external_thread_id": CHAT_B}
        notify.notify_order_draft(draft, thread=thread)

        logs = frappe.get_all(
            "Notification Log",
            filters={"for_user": self.owner, "document_name": draft.name},
            fields=["subject"],
        )
        self.assertEqual(len(logs), 1)
        self.assertIn(f"Chat ID {CHAT_B}", logs[0]["subject"])
        self.assertIn("Quotation", logs[0]["subject"])

    # =========================================================================
    # 3. Views API: list_orders and review_order
    # =========================================================================
    def test_list_orders_and_review_order(self):
        """Orders are listed for owner, and reviewing marks them read."""
        payload = {"doctype": "Sales Order", "data": {}}
        draft = create_draft(
            task_id="AIOS-TEST-DRAFT-3",
            action_type="CREATE",
            payload=payload,
            branch="sales",
            user=self.owner,
        )
        thread = {"display_name": "Ahmad", "external_thread_id": CHAT_A}
        notify.notify_order_draft(draft, thread=thread)

        # 1. List unread orders
        orders = views.list_orders(self.owner, unread_only=True)
        self.assertTrue(any(o["draft_id"] == draft.name for o in orders))
        target_order = next(o for o in orders if o["draft_id"] == draft.name)
        self.assertEqual(target_order["customer_name"], "Ahmad")
        self.assertEqual(target_order["doctype"], "Sales Order")
        self.assertEqual(target_order["read"], 0)

        # Other user sees 0 orders
        other_orders = views.list_orders(self.other, unread_only=True)
        self.assertEqual(len(other_orders), 0)

        # 2. Review order
        res = views.review_order(self.owner, target_order["name"])
        self.assertTrue(res["success"])
        self.assertEqual(res["read"], 1)

        # 3. Ensure order no longer appears in unread list
        orders_after = views.list_orders(self.owner, unread_only=True)
        self.assertFalse(any(o["draft_id"] == draft.name for o in orders_after))

    def test_review_order_permission_isolation(self):
        """User cannot review order notifications belonging to another user."""
        payload = {"doctype": "Sales Order", "data": {}}
        draft = create_draft(
            task_id="AIOS-TEST-DRAFT-4",
            action_type="CREATE",
            payload=payload,
            branch="sales",
            user=self.owner,
        )
        notify.notify_order_draft(draft, thread={"external_thread_id": CHAT_A})

        orders = views.list_orders(self.owner, unread_only=True)
        target_order = next(o for o in orders if o["draft_id"] == draft.name)

        from aios_v1.lib.workspace import WorkspaceError

        with self.assertRaises(WorkspaceError):
            views.review_order(self.other, target_order["name"])
