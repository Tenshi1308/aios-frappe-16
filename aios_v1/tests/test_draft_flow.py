"""P1: alur approval draft milik sendiri + Guest ditolak.

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import unittest

import frappe
from frappe.utils import add_to_date, now_datetime

from aios_v1.lib.draft_manager import approve_draft, reject_draft

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _make_test_user(email, first_name):
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    doc = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "enabled": 1,
            "send_welcome_email": 0,
            "user_type": "Website User",
            "aios_status": "Active",
            "roles": [{"role": "AIOS Client"}],
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


class TestDraftFlow(IntegrationTestCase):
    ALPHA = "_test.draft.alpha@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        _make_test_user(self.ALPHA, "_Test Draft Alpha")
        frappe.set_user(self.ALPHA)

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _create_draft(self, task_id="TEST-DRAFT-001"):
        return frappe.get_doc(
            {
                "doctype": "Pending Action Draft",
                "task_id": task_id,
                "type": "sales_order",
                "payload": "{}",
                "status": "PENDING_APPROVAL",
                "expires_at": add_to_date(now_datetime(), hours=1),
            }
        ).insert(ignore_permissions=True)

    def test_approve_own_draft(self):
        draft = self._create_draft()
        result = approve_draft(draft.name)
        self.assertEqual(result["status"], "success")
        self.assertEqual(
            frappe.db.get_value("Pending Action Draft", draft.name, "status"),
            "APPROVED",
        )

    def test_reject_own_draft_saves_reason(self):
        draft = self._create_draft("TEST-DRAFT-002")
        result = reject_draft(draft.name, reason="harga terlalu tinggi")
        self.assertEqual(result["status"], "success")
        self.assertEqual(
            frappe.db.get_value("Pending Action Draft", draft.name, "status"),
            "REJECTED",
        )
        self.assertEqual(
            frappe.db.get_value(
                "Pending Action Draft", draft.name, "rejection_reason"
            ),
            "harga terlalu tinggi",
        )

    def test_guest_cannot_approve(self):
        draft = self._create_draft("TEST-DRAFT-003")
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            approve_draft(draft.name)

    def test_draft_methods_are_not_guest_whitelisted(self):
        from aios_v1.lib.draft_manager import get_draft, reject_draft

        frappe.set_user("Guest")
        for method in (get_draft, approve_draft, reject_draft):
            with self.assertRaises(frappe.PermissionError):
                frappe.is_whitelisted(method)
