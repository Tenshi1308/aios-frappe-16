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
                "user": self.EMAIL,
                "type": "CREATE",
                "payload": '{"doctype": "Sales Order", "data": {}}',
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


class TestListPendingDrafts(IntegrationTestCase):
    """C3 fase 2a: daftar draft pending owner-scoped + hanya PENDING_APPROVAL."""

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        self.alpha = _make_test_user("_test.draft.list.a@example.com", "_Test List A")
        self.beta = _make_test_user("_test.draft.list.b@example.com", "_Test List B")

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _draft(self, user, task_id):
        return frappe.get_doc(
            {
                "doctype": "Pending Action Draft",
                "task_id": task_id,
                "user": user,
                "type": "CREATE",
                "payload": '{"doctype": "Sales Order", "data": {}}',
                "status": "PENDING_APPROVAL",
                "expires_at": add_to_date(now_datetime(), hours=2),
            }
        ).insert(ignore_permissions=True)

    def test_list_is_owner_scoped_and_pending_only(self):
        from aios_v1.lib.draft_manager import list_pending_drafts, reject_draft

        a1 = self._draft(self.alpha.name, "TEST-LIST-A1")
        a2 = self._draft(self.alpha.name, "TEST-LIST-A2")
        b1 = self._draft(self.beta.name, "TEST-LIST-B1")

        frappe.set_user(self.alpha.name)
        rows = list_pending_drafts()
        names = {row["name"] for row in rows}
        self.assertEqual(names, {a1.name, a2.name})
        self.assertTrue(all(row["status"] == "PENDING_APPROVAL" for row in rows))
        self.assertTrue(all({"name", "type", "branch", "status", "expires_at", "creation"} <= set(row) for row in rows))

        frappe.set_user(self.beta.name)
        rows_beta = list_pending_drafts()
        self.assertEqual({row["name"] for row in rows_beta}, {b1.name})

        frappe.set_user(self.alpha.name)
        reject_draft(a1.name, "tidak sesuai")
        rows_after = list_pending_drafts()
        self.assertEqual({row["name"] for row in rows_after}, {a2.name})

    def test_list_limit_is_clamped(self):
        from aios_v1.lib.draft_manager import list_pending_drafts

        self._draft(self.alpha.name, "TEST-LIST-C1")
        frappe.set_user(self.alpha.name)
        rows = list_pending_drafts(limit=500)
        self.assertIsInstance(rows, list)
        rows_default = list_pending_drafts()
        self.assertEqual(len(rows_default), 1)
