"""Isolasi baris antar-`User` (docs/05 §6c, Tahap C).

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
Di CI statis file ini dibuang dari collection oleh `conftest.py` (import frappe).
"""

import unittest

import frappe

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _make_test_user(email, first_name):
    """Buat User dummy prefiks _Test dengan role AIOS Client yang sudah Active."""
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


class TestUserIsolation(IntegrationTestCase):
    """Alpha akses resource Beta → 403/404; tanpa sesi → 401."""

    ALPHA = "_test.user.alpha@example.com"
    BETA = "_test.user.beta@example.com"

    def setUp(self):
        super().setUp()
        # Penangkal db.commit() manual di kode AIOS lama (docs/05 §6b.3)
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        _make_test_user(self.ALPHA, "_Test User Alpha")
        _make_test_user(self.BETA, "_Test User Beta")

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()

    def _beta_resources(self):
        """Kembalikan (doctype, name) milik Beta untuk tiap resource."""
        from frappe.utils import add_to_date, now_datetime

        tenant = frappe.get_doc(
            {
                "doctype": "AIOS Tenant",
                "tenant_name": "_Test Tenant",
                "email": "_test.tenant@example.com",
            }
        ).insert(ignore_permissions=True)

        resources = []
        conv = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": self.BETA,
                "branch": "sales",
                "title": "_Test Beta conversation",
            }
        ).insert(ignore_permissions=True)
        resources.append(("AIOS Conversation", conv.name))

        msg = frappe.get_doc(
            {
                "doctype": "AIOS Message",
                "conversation": conv.name,
                "role": "user",
                "content": "beta-only",
            }
        ).insert(ignore_permissions=True)
        resources.append(("AIOS Message", msg.name))

        conn = frappe.get_doc(
            {
                "doctype": "AIOS DB Connection",
                "tenant": tenant.name,
                "user": self.BETA,
                "engine": "sqlite",
            }
        ).insert(ignore_permissions=True)
        resources.append(("AIOS DB Connection", conn.name))

        draft = frappe.get_doc(
            {
                "doctype": "Pending Action Draft",
                "user": self.BETA,
                "task_id": "TEST-BETA-001",
                "type": "sales_order",
                "payload": "{}",
                "status": "PENDING_APPROVAL",
                "expires_at": add_to_date(now_datetime(), hours=1),
            }
        ).insert(ignore_permissions=True)
        resources.append(("Pending Action Draft", draft.name))
        return resources

    def test_alpha_cannot_access_beta_resources(self):
        resources = self._beta_resources()
        frappe.set_user(self.ALPHA)
        for doctype, name in resources:
            with self.subTest(doctype=doctype, name=name):
                with self.assertRaises((frappe.PermissionError, frappe.DoesNotExistError)):
                    frappe.get_doc(doctype, name, check_permission="read")

    def test_alpha_cannot_list_beta_resources(self):
        self._beta_resources()
        frappe.set_user(self.ALPHA)
        for doctype in (
            "AIOS Conversation",
            "AIOS Message",
            "AIOS DB Connection",
            "Pending Action Draft",
        ):
            names = frappe.get_list(doctype, pluck="name")
            self.assertEqual(names, [], f"{doctype} bocor ke Alpha")

    def test_alpha_can_access_own_resources(self):
        frappe.set_user(self.ALPHA)
        conv = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": self.ALPHA,
                "branch": "sales",
                "title": "_Test Alpha conversation",
            }
        ).insert(ignore_permissions=True)
        doc = frappe.get_doc("AIOS Conversation", conv.name, check_permission="read")
        self.assertEqual(doc.name, conv.name)
        self.assertIn(conv.name, frappe.get_list("AIOS Conversation", pluck="name"))

    def test_null_user_rows_are_not_visible(self):
        from aios_v1.permissions import conversation_query_conditions

        condition = conversation_query_conditions(self.ALPHA, "AIOS Conversation")
        self.assertIn("`tabAIOS Conversation`.user = ", condition)
        self.assertNotIn("IS NULL", condition)

    def test_administrator_is_not_restricted(self):
        resources = self._beta_resources()
        frappe.set_user("Administrator")
        for doctype, name in resources:
            doc = frappe.get_doc(doctype, name, check_permission="read")
            self.assertEqual(doc.name, name)

    def test_draft_created_by_session_owner(self):
        frappe.set_user(self.ALPHA)
        from frappe.utils import add_to_date, now_datetime

        draft = frappe.get_doc(
            {
                "doctype": "Pending Action Draft",
                "task_id": "TEST-ALPHA-001",
                "type": "sales_order",
                "payload": "{}",
                "expires_at": add_to_date(now_datetime(), hours=1),
            }
        ).insert(ignore_permissions=True)
        self.assertEqual(draft.user, self.ALPHA)

    def test_alpha_cannot_approve_beta_draft(self):
        from aios_v1.lib.draft_manager import approve_draft

        resources = self._beta_resources()
        draft_name = dict(resources)["Pending Action Draft"]
        frappe.set_user(self.ALPHA)
        with self.assertRaises(frappe.PermissionError):
            approve_draft(draft_name)

    def test_no_cookie_returns_401(self):
        from aios_v1.api.dispatcher import CustomAPIResponse, require_session

        frappe.set_user("Guest")
        with self.assertRaises(CustomAPIResponse) as caught:
            require_session()
        self.assertEqual(caught.exception._custom_response.status_code, 401)
