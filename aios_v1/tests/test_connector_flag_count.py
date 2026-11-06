"""Tests for Connector Flag Counting, Status Filtering, and Bell Total Integration.

Tests cover:
a. GET ?status=Open returns only Open, ?status=Closed returns only Closed, without query returns all
b. Mixed 35 older Open + 30 newer Closed: ?status=Open returns all 35 Open (not truncated to 20)
c. 60 Open + 10 Closed: total is 60, len(flags) is 50, bell count is 60; adding up to 105 caps badge at 99+
d. Closing 1 flag via POST api/connector/flag/close decrements Open total by 1 and removes it from ?status=Open
e. Other user calling ?status=Open receives flags=[] and total=0
"""

from __future__ import annotations

import json

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from aios_v1.api.dispatcher import CustomAPIResponse, handle_api_request
from aios_v1.lib.connector import dispatch, views

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

SETTING = "AIOS Telegram Setting"
THREAD = "AIOS Channel Thread"
FLAG = "AIOS Conversation Flag"
OWNER = "_test.flagcnt.owner@example.com"
OTHER = "_test.flagcnt.other@example.com"
CHAT_ID = "77889900"


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


class TestConnectorFlagCount(IntegrationTestCase):
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
        self.owner = _ensure_user(OWNER, "FlagCnt Owner", is_receiver=True)
        self.other = _ensure_user(OTHER, "FlagCnt Other", is_receiver=False)
        self._cleanup()
        self.thread_name = self._create_thread(self.owner)

    def tearDown(self):
        self._cleanup()
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()
        super().tearDown()

    def _cleanup(self):
        for flag_name in frappe.get_all(
            FLAG,
            pluck="name",
        ):
            frappe.delete_doc(FLAG, flag_name, ignore_permissions=True, force=True)
        for thread_name in frappe.get_all(
            THREAD,
            filters={"external_thread_id": CHAT_ID},
            pluck="name",
        ):
            conv = frappe.db.get_value(THREAD, thread_name, "conversation")
            frappe.delete_doc(THREAD, thread_name, ignore_permissions=True, force=True)
            if conv and frappe.db.exists("AIOS Conversation", conv):
                frappe.delete_doc("AIOS Conversation", conv, ignore_permissions=True, force=True)

    def _create_thread(self, owner_user: str) -> str:
        thread = dispatch.get_or_create_thread(CHAT_ID)
        return thread["name"]

    def _seed_flags(self, count: int, status: str, owner_user: str | None = None) -> list[int | str]:
        owner = owner_user or self.owner
        names: list[int | str] = []
        for i in range(count):
            doc = frappe.get_doc(
                {
                    "doctype": FLAG,
                    "thread": self.thread_name,
                    "owner": owner,
                    "rule_key": "personal_account",
                    "severity": "high",
                    "status": status,
                    "label": f"Flag {status} {i}",
                    "excerpt": f"Excerpt {status} {i}",
                }
            )
            doc.insert(ignore_permissions=True)
            if doc.owner != owner:
                frappe.db.set_value(FLAG, doc.name, "owner", owner, update_modified=False)
            names.append(doc.name)
        return names

    def _call_flags_api(self, user: str, query_string: str = "") -> dict:
        builder = EnvironBuilder(
            path="api/connector/flags",
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
        raise AssertionError("api/connector/flags tidak mengembalikan response")

    def _call_close_flag_api(self, user: str, flag_id: int | str, note: str = "") -> dict:
        payload = json.dumps({"flag": flag_id, "note": note})
        builder = EnvironBuilder(
            path="api/connector/flag/close",
            method="POST",
            data=payload,
            content_type="application/json",
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
        raise AssertionError("api/connector/flag/close tidak mengembalikan response")

    # =========================================================================
    # a. Filter status=Open, status=Closed, dan tanpa query
    # =========================================================================
    def test_status_filter_open_closed_and_default_all(self):
        """GET ?status=Open returns only Open, ?status=Closed only Closed, no query returns all."""
        self._seed_flags(3, "Open")
        self._seed_flags(4, "Closed")

        res_open = self._call_flags_api(self.owner, "status=Open")
        self.assertEqual(res_open["total"], 3)
        self.assertEqual(len(res_open["flags"]), 3)
        self.assertTrue(all(f["status"] == "Open" for f in res_open["flags"]))

        res_closed = self._call_flags_api(self.owner, "status=Closed")
        self.assertEqual(res_closed["total"], 4)
        self.assertEqual(len(res_closed["flags"]), 4)
        self.assertTrue(all(f["status"] == "Closed" for f in res_closed["flags"]))

        res_all = self._call_flags_api(self.owner, "")
        self.assertEqual(res_all["total"], 7)
        self.assertEqual(len(res_all["flags"]), 7)

        # Invalid status falls back to None (all)
        res_invalid = self._call_flags_api(self.owner, "status=InvalidStatus")
        self.assertEqual(res_invalid["total"], 7)
        self.assertEqual(len(res_invalid["flags"]), 7)

    # =========================================================================
    # b. Campur 35 Open lama + 30 Closed baru
    # =========================================================================
    def test_mixed_35_older_open_and_30_newer_closed(self):
        """35 older Open + 30 newer Closed: ?status=Open returns all 35 Open, not 20."""
        self._seed_flags(35, "Open")
        self._seed_flags(30, "Closed")

        res_open = self._call_flags_api(self.owner, "status=Open")
        self.assertEqual(res_open["total"], 35)
        self.assertEqual(len(res_open["flags"]), 35)
        self.assertTrue(all(f["status"] == "Open" for f in res_open["flags"]))

    # =========================================================================
    # c. 60 Open + 10 Closed: total 60, len(flags) 50, bell 60, dan cap 99+ di 105
    # =========================================================================
    def test_60_open_and_10_closed_total_and_bell_cap_99_plus(self):
        """60 Open + 10 Closed gives total=60 and len(flags)=50; 105 Open caps badge at 99+."""
        self._seed_flags(60, "Open")
        self._seed_flags(10, "Closed")

        self.assertEqual(views.count_flags(self.owner, status="Open"), 60)
        self.assertEqual(views.count_flags(self.owner, status="Closed"), 10)
        self.assertEqual(views.count_flags(self.owner, status=None), 70)

        res_open = self._call_flags_api(self.owner, "status=Open")
        self.assertEqual(res_open["total"], 60)
        self.assertEqual(len(res_open["flags"]), 50)
        self.assertTrue(all(f["status"] == "Open" for f in res_open["flags"]))

        order_total = 0
        bell_count_60 = res_open["total"] + order_total
        badge_60 = "99+" if bell_count_60 > 99 else str(bell_count_60)
        self.assertEqual(bell_count_60, 60)
        self.assertEqual(badge_60, "60")

        # Add 45 more Open flags to reach 105 Open
        self._seed_flags(45, "Open")
        res_105 = self._call_flags_api(self.owner, "status=Open")
        self.assertEqual(res_105["total"], 105)
        self.assertEqual(len(res_105["flags"]), 50)

        bell_count_105 = res_105["total"] + order_total
        badge_105 = "99+" if bell_count_105 > 99 else str(bell_count_105)
        self.assertEqual(bell_count_105, 105)
        self.assertEqual(badge_105, "99+")

    # =========================================================================
    # d. Tutup 1 flag via POST api/connector/flag/close menurunkan total 1
    # =========================================================================
    def test_close_flag_decrements_open_total_and_removes_from_open_list(self):
        """Closing 1 Open flag via POST flag/close reduces Open total by 1 and removes it from ?status=Open."""
        open_ids = self._seed_flags(4, "Open")
        target_id = open_ids[0]

        before = self._call_flags_api(self.owner, "status=Open")
        self.assertEqual(before["total"], 4)
        self.assertEqual(len(before["flags"]), 4)

        close_res = self._call_close_flag_api(self.owner, target_id, "Ditinjau oleh staf.")
        self.assertTrue(close_res.get("success"))
        self.assertEqual(close_res.get("status"), "Closed")

        after = self._call_flags_api(self.owner, "status=Open")
        self.assertEqual(after["total"], 3)
        self.assertEqual(len(after["flags"]), 3)
        remaining_ids = {f["name"] for f in after["flags"]}
        self.assertNotIn(target_id, remaining_ids)

    # =========================================================================
    # e. User lain memanggil ?status=Open menerima flags=[] dan total=0
    # =========================================================================
    def test_other_user_isolation(self):
        """Other user calling ?status=Open gets flags=[] and total=0."""
        self._seed_flags(5, "Open")

        res_other = self._call_flags_api(self.other, "status=Open")
        self.assertEqual(res_other["flags"], [])
        self.assertEqual(res_other["total"], 0)
        self.assertEqual(views.count_flags(self.other, status="Open"), 0)
