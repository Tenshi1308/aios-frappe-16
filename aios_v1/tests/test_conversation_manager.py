"""P1: `BaseManager.ensure_conversation` terikat ke user sesi, bukan tenant.

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import unittest

import frappe

from aios_v1.managers import get_manager

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


class TestEnsureConversation(IntegrationTestCase):
    ALPHA = "_test.conv.alpha@example.com"
    BETA = "_test.conv.beta@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        _make_test_user(self.ALPHA, "_Test Conv Alpha")
        _make_test_user(self.BETA, "_Test Conv Beta")
        self.manager = get_manager("sales")

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def test_creates_conversation_with_session_user(self):
        frappe.set_user(self.ALPHA)
        conv_id = self.manager.ensure_conversation(self.ALPHA)
        self.assertEqual(
            frappe.db.get_value("AIOS Conversation", conv_id, "user"), self.ALPHA
        )

    def test_reuses_own_conversation(self):
        frappe.set_user(self.ALPHA)
        first = self.manager.ensure_conversation(self.ALPHA)
        second = self.manager.ensure_conversation(self.ALPHA)
        self.assertEqual(first, second)

    def test_does_not_reuse_other_user_conversation(self):
        beta_conv = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": self.BETA,
                "branch": "sales",
                "title": "_Test Beta conv",
            }
        ).insert(ignore_permissions=True)
        frappe.set_user(self.ALPHA)
        alpha_conv = self.manager.ensure_conversation(self.ALPHA)
        self.assertNotEqual(int(beta_conv.name), alpha_conv)
        self.assertEqual(
            frappe.db.get_value("AIOS Conversation", alpha_conv, "user"), self.ALPHA
        )
