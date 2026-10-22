"""Alur approval draft: expire, approve, reject, status guard (S2/L9).

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import frappe
from frappe.utils import add_to_date, now_datetime

from aios_v1.lib.draft_manager import approve_draft, expire_old_drafts, reject_draft

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


class TestDraftManager(IntegrationTestCase):
    EMAIL = "_test.draft.manager@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        _make_test_user(self.EMAIL, "_Test Draft Manager")
        frappe.set_user(self.EMAIL)

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _draft(self, expires_hours=2):
        return frappe.get_doc(
            {
                "doctype": "Pending Action Draft",
                "task_id": "TEST-DRAFTMGR-001",
                "type": "create_po",
                "payload": '{"item": "Baut"}',
                "status": "PENDING_APPROVAL",
                "expires_at": add_to_date(now_datetime(), hours=expires_hours),
            }
        ).insert(ignore_permissions=True)

    def test_expire_old_drafts(self):
        draft = self._draft(expires_hours=-2)
        self.assertEqual(
            frappe.db.get_value("Pending Action Draft", draft.name, "status"),
            "PENDING_APPROVAL",
        )
        expire_old_drafts()
        self.assertEqual(
            frappe.db.get_value("Pending Action Draft", draft.name, "status"),
            "EXPIRED",
        )

    def test_approve_draft(self):
        draft = self._draft()
        result = approve_draft(draft.name)
        # Payload contoh bukan dokumen ERPNext valid -> approval sukses, eksekusi gagal.
        self.assertEqual(result["status"], "APPROVED")
        self.assertFalse(result["executed"])
        self.assertEqual(
            frappe.db.get_value("Pending Action Draft", draft.name, "status"),
            "APPROVED",
        )

    def test_reject_draft(self):
        draft = self._draft()
        result = reject_draft(draft.name, reason="tidak sesuai kebutuhan")
        self.assertEqual(result["status"], "success")
        self.assertEqual(
            frappe.db.get_value("Pending Action Draft", draft.name, "status"),
            "REJECTED",
        )
        self.assertEqual(
            frappe.db.get_value(
                "Pending Action Draft", draft.name, "rejection_reason"
            ),
            "tidak sesuai kebutuhan",
        )

    def test_cannot_approve_non_pending(self):
        draft = self._draft()
        draft.status = "EXPIRED"
        draft.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            approve_draft(draft.name)
