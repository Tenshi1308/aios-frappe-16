"""P3: `AIOS Client` adalah Website User (desk_access=0) dan bisa panggil whitelist.

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import unittest

import frappe

from aios_v1.setup import get_session_context

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


class TestWebsiteUserAccess(IntegrationTestCase):
    EMAIL = "_test.website.user@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        _make_test_user(self.EMAIL, "_Test Website User")

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def test_client_role_has_no_desk_access(self):
        self.assertEqual(
            frappe.db.get_value("Role", "AIOS Client", "desk_access"), 0
        )

    def test_client_is_website_user(self):
        self.assertEqual(
            frappe.db.get_value("User", self.EMAIL, "user_type"), "Website User"
        )

    def test_client_can_call_whitelisted_method(self):
        frappe.set_user(self.EMAIL)
        context = get_session_context()
        self.assertEqual(context["user"], self.EMAIL)
        self.assertIn("AIOS Client", context["roles"])
        self.assertTrue(context["csrf_token"])

    def test_client_has_read_permission(self):
        frappe.set_user(self.EMAIL)
        self.assertTrue(frappe.has_permission("AIOS Conversation", "read"))
