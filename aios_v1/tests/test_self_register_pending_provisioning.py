"""P3: registrasi mandiri → `Pending Provisioning`, tanpa `AIOS Tenant` (Alur 3).

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import unittest

import frappe

from aios_v1.auth import register_account

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


class TestSelfRegisterPendingProvisioning(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        frappe.local.request = None
        frappe.set_user("Guest")

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.local.request = None
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def test_creates_pending_user_without_tenant(self):
        email = "_test.register.alpha@example.com"
        result = register_account("Test Alpha", email, "rahasia123", "PT Test Alpha")

        self.assertEqual(result, {"status": "PENDING_PROVISIONING"})
        row = frappe.db.get_value(
            "User",
            email,
            ["aios_status", "enabled", "send_welcome_email", "user_type"],
            as_dict=True,
        )
        self.assertEqual(row["aios_status"], "Pending Provisioning")
        self.assertEqual(row["enabled"], 0)
        self.assertEqual(row["send_welcome_email"], 0)
        self.assertEqual(row["user_type"], "Website User")
        self.assertIn("AIOS Client", frappe.get_roles(email))
        self.assertFalse(frappe.db.exists("AIOS Tenant", {"email": email}))

    def test_duplicate_email_returns_same_generic_response(self):
        email = "_test.register.beta@example.com"
        first = register_account("Test Beta", email, "rahasia123", "PT Test Beta")
        second = register_account("Test Beta", email, "rahasia123", "PT Test Beta")

        self.assertEqual(first, second)
        self.assertEqual(frappe.db.count("User", {"email": email}), 1)

    def test_invalid_email_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            register_account("Test Gamma", "bukan-email", "rahasia123", "PT Gamma")

    def test_short_password_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            register_account(
                "Test Delta",
                "_test.register.delta@example.com",
                "123",
                "PT Delta",
            )

    def test_missing_fields_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            register_account("", "_test.register.epsilon@example.com", "rahasia123", "PT Epsilon")
