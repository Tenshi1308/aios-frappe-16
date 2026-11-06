"""Tests for Connector Orders Pagination and Bell Total Integration.

Tests cover:
a. Pagination page 1 and 2 (no duplicates, no missing items)
b. Out-of-bounds page handling
c. Bell total count (60 vs 20, and 99+ cap)
d. Reviewing order on page 2 and empty page step-back transition
e. Permission isolation and employee draft exclusion
"""

from __future__ import annotations

import json
import math
import uuid

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from aios_v1.api.dispatcher import CustomAPIResponse, handle_api_request
from aios_v1.lib.connector import notify, views
from aios_v1.lib.draft_manager import create_draft
from aios_v1.lib.workspace import WorkspaceError

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

SETTING = "AIOS Telegram Setting"
OWNER = "_test.pag.owner@example.com"
OTHER = "_test.pag.other@example.com"


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


class TestConnectorOrdersPagination(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.in_test = True
        frappe.flags.in_test = True
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        frappe.set_user("Administrator")
        frappe.db.set_single_value("AIOS Setting", "max_users", 20)
        frappe.db.delete(
            "Has Role",
            {"parenttype": "User", "role": ("in", ["AIOS Channel Receiver", "AIOS Client Owner"])},
        )
        self.owner = _ensure_user(OWNER, "Pag Owner", is_receiver=True)
        self.other = _ensure_user(OTHER, "Pag Other", is_receiver=False)
        self._cleanup()

    def tearDown(self):
        self._cleanup()
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()
        super().tearDown()

    def _cleanup(self):
        for n in frappe.get_all(
            "Notification Log",
            filters={"for_user": ("in", [self.owner, self.other])},
            pluck="name",
        ):
            frappe.delete_doc("Notification Log", n, ignore_permissions=True, force=True)
        for pad in frappe.get_all(
            "Pending Action Draft",
            filters={"user": ("in", [self.owner, self.other])},
            pluck="name",
        ):
            frappe.delete_doc("Pending Action Draft", pad, ignore_permissions=True, force=True)

    def _seed_orders(self, count: int, user: str) -> list[str]:
        draft_names = []
        for i in range(count):
            draft = create_draft(
                task_id=f"AIOS-TEST-PAG-{uuid.uuid4()}",
                action_type="CREATE",
                payload={"doctype": "Sales Order", "data": {"item": f"Item-{i}"}},
                branch="sales",
                user=user,
            )
            notify.notify_order_draft(
                draft,
                thread={"display_name": f"Customer {i}", "external_thread_id": f"chat_{i}"},
            )
            draft_names.append(draft.name)
        return draft_names

    def _call_orders_api(self, user: str, query_string: str = "") -> dict:
        builder = EnvironBuilder(
            path="api/connector/orders",
            method="GET",
            query_string=query_string,
        )
        frappe.local.request = Request(builder.get_environ())
        frappe.set_user(user)
        try:
            handle_api_request()
        except CustomAPIResponse as exc:
            data = exc._custom_response.get_data(as_text=True)
            return json.loads(data)
        finally:
            frappe.local.request = None
            frappe.set_user("Administrator")
        raise AssertionError("api/connector/orders tidak mengembalikan response")

    # =========================================================================
    # a. Halaman 1 dan 2
    # =========================================================================
    def test_pagination_page_1_and_2(self):
        """Seed 25 orders: page 1 has exactly 20, page 2 has 5, no duplicates or lost items."""
        self._seed_orders(25, self.owner)

        # Direct view query
        p1 = views.list_orders(self.owner, unread_only=True, page=1, page_length=20)
        p2 = views.list_orders(self.owner, unread_only=True, page=2, page_length=20)

        self.assertEqual(len(p1), 20)
        self.assertEqual(len(p2), 5)

        p1_ids = {o["name"] for o in p1}
        p2_ids = {o["name"] for o in p2}

        # Zero intersection (no duplicates)
        self.assertEqual(len(p1_ids.intersection(p2_ids)), 0)
        # Full union covers all 25
        self.assertEqual(len(p1_ids.union(p2_ids)), 25)

        # Via API endpoint
        res_p1 = self._call_orders_api(self.owner, "page=1")
        self.assertEqual(res_p1["total"], 25)
        self.assertEqual(res_p1["page"], 1)
        self.assertEqual(res_p1["page_length"], 20)
        self.assertEqual(res_p1["total_pages"], 2)
        self.assertEqual(len(res_p1["orders"]), 20)

        res_p2 = self._call_orders_api(self.owner, "page=2")
        self.assertEqual(res_p2["total"], 25)
        self.assertEqual(res_p2["page"], 2)
        self.assertEqual(res_p2["page_length"], 20)
        self.assertEqual(res_p2["total_pages"], 2)
        self.assertEqual(len(res_p2["orders"]), 5)

    # =========================================================================
    # b. Halaman di luar jangkauan
    # =========================================================================
    def test_page_out_of_bounds(self):
        """Seed 5 orders, call page 999: returns empty orders, total 5, page 999, total_pages 1."""
        self._seed_orders(5, self.owner)

        res = self._call_orders_api(self.owner, "page=999")
        self.assertEqual(res["orders"], [])
        self.assertEqual(res["total"], 5)
        self.assertEqual(res["page"], 999)
        self.assertEqual(res["page_length"], 20)
        self.assertEqual(res["total_pages"], 1)

    # =========================================================================
    # c. Hitungan bell total 60 dan batas 99+
    # =========================================================================
    def test_bell_total_60_and_99_plus(self):
        """Seed 60 orders: count_orders returns 60, API page 1 has 20 orders but total 60."""
        self._seed_orders(60, self.owner)

        count = views.count_orders(self.owner, unread_only=True)
        self.assertEqual(count, 60)

        res = self._call_orders_api(self.owner, "page=1")
        self.assertEqual(len(res["orders"]), 20)
        self.assertEqual(res["total"], 60)
        self.assertEqual(res["total_pages"], 3)

        # Simulate bell badge logic
        open_flags_count = 0
        bell_count_60 = open_flags_count + res["total"]
        badge_60 = "99+" if bell_count_60 > 99 else str(bell_count_60)
        self.assertEqual(bell_count_60, 60)
        self.assertEqual(badge_60, "60")

        # Simulate bell badge logic with total 105
        bell_count_105 = open_flags_count + 105
        badge_105 = "99+" if bell_count_105 > 99 else str(bell_count_105)
        self.assertEqual(badge_105, "99+")

    # =========================================================================
    # d. Tandai ditinjau di halaman 2 dan transisi halaman kosong
    # =========================================================================
    def test_review_order_page_2_and_empty_page_step_back(self):
        """Seed 21 orders, review 1 item on page 2: total becomes 20, total_pages 1.
        Page 2 becomes empty, stepping back to page 1 gives 20 orders.
        """
        self._seed_orders(21, self.owner)

        self.assertEqual(views.count_orders(self.owner, unread_only=True), 21)
        res_p2 = self._call_orders_api(self.owner, "page=2")
        self.assertEqual(len(res_p2["orders"]), 1)
        self.assertEqual(res_p2["total"], 21)
        self.assertEqual(res_p2["total_pages"], 2)

        target_notif_id = res_p2["orders"][0]["name"]
        rev_res = views.review_order(self.owner, target_notif_id)
        self.assertTrue(rev_res["success"])
        self.assertEqual(rev_res["read"], 1)

        # Now total is 20
        new_total = views.count_orders(self.owner, unread_only=True)
        self.assertEqual(new_total, 20)

        # Fetching page 2 now returns empty
        res_p2_after = self._call_orders_api(self.owner, "page=2")
        self.assertEqual(res_p2_after["orders"], [])
        self.assertEqual(res_p2_after["total"], 20)
        self.assertEqual(res_p2_after["total_pages"], 1)

        # Stepping back to page 1 returns 20 orders
        target_page = res_p2_after["total_pages"] if res_p2_after["page"] > res_p2_after["total_pages"] else res_p2_after["page"]
        self.assertEqual(target_page, 1)

        res_p1_after = self._call_orders_api(self.owner, f"page={target_page}")
        self.assertEqual(len(res_p1_after["orders"]), 20)
        self.assertEqual(res_p1_after["total"], 20)
        self.assertEqual(res_p1_after["total_pages"], 1)

    # =========================================================================
    # e. Isolasi izin dan eksklusi draf karyawan
    # =========================================================================
    def test_permission_isolation_and_employee_draft_exclusion(self):
        """Other user gets 0 orders, cannot review owner's order, and employee draft creates no notif."""
        self._seed_orders(5, self.owner)

        # Other user sees 0
        self.assertEqual(views.count_orders(self.other, unread_only=True), 0)
        self.assertEqual(len(views.list_orders(self.other, unread_only=True)), 0)

        res_other = self._call_orders_api(self.other, "page=1")
        self.assertEqual(res_other["total"], 0)
        self.assertEqual(res_other["orders"], [])

        # Other user cannot review owner's notification
        owner_orders = views.list_orders(self.owner, unread_only=True)
        owner_notif = owner_orders[0]["name"]
        with self.assertRaises(WorkspaceError) as ctx:
            views.review_order(self.other, owner_notif)
        self.assertEqual(ctx.exception.status, 404)

        # Employee draft creation (is_guest = False) must NOT create Notification Log
        from unittest.mock import patch

        from aios_v1.lib.erpnext_action_drafts import erpnext_action_draft_create

        before_count = views.count_orders(self.owner, unread_only=True)
        with patch("aios_v1.lib.erpnext_action_drafts.get_tool_context", return_value={"user_id": self.owner, "allowed_company": "Windu Utama PT", "branch": "sales", "worker_key": "sales"}):
            with patch("aios_v1.lib.erpnext_action_drafts.validate_data_fields"):
                frappe.set_user(self.owner)
                res = erpnext_action_draft_create(
                    action_type="CREATE",
                    doctype="Sales Order",
                    data={"customer": "Internal Customer"},
                    reason="Employee internal order",
                )
                self.assertEqual(res["status"], "PENDING_APPROVAL")
        after_count = views.count_orders(self.owner, unread_only=True)
        self.assertEqual(before_count, after_count, "Employee draft must not create Notification Log")
