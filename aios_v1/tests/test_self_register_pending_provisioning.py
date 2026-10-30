"""Registrasi mandiri calon klien -> Lead di site developer (docs/00-poc-target.md §1.1).

Butuh site + DB -> `bench --site aios-v16.localhost run-tests --app aios_v1 --module aios_v1.tests.test_self_register_pending_provisioning`.
"""

from uuid import uuid4

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
        self._had_role = "aios_site_role" in frappe.conf
        self._orig_role = frappe.conf.get("aios_site_role")
        frappe.conf["aios_site_role"] = "developer"

        self.created_leads = []
        frappe.cache.delete_keys("rl:")
        frappe.local.request = None
        frappe.set_user("Guest")

    def tearDown(self):
        frappe.set_user("Administrator")
        for lead_name in reversed(self.created_leads):
            if frappe.db.exists("Lead", lead_name):
                frappe.delete_doc("Lead", lead_name, ignore_permissions=True, force=True)

        if self._had_role:
            frappe.conf["aios_site_role"] = self._orig_role
        else:
            frappe.conf.pop("aios_site_role", None)

        frappe.db.commit = self._orig_commit
        frappe.local.request = None
        frappe.db.rollback()
        super().tearDown()

    def _email(self, label: str) -> str:
        return f"_test.reg.{label}.{uuid4().hex[:8]}@example.test"

    def test_creates_lead_without_user(self):
        email = self._email("alpha")
        result = register_account("Test Alpha", email, "PT Test Alpha")

        self.assertEqual(result, {"status": "PENDING_PROVISIONING"})
        lead = frappe.db.get_value(
            "Lead",
            {"email_id": email},
            ["name", "company_name", "country", "utm_source"],
            as_dict=True,
        )
        self.assertIsNotNone(lead, "Lead harus terbentuk.")
        self.created_leads.append(lead.name)
        self.assertEqual(lead.company_name, "PT Test Alpha")
        expected_country = frappe.get_system_settings("country")
        self.assertEqual(
            lead.country,
            expected_country,
            "Lead country harus diambil secara dinamis dari System Settings.",
        )
        self.assertEqual(lead.utm_source, "AIOS Signup")

        self.assertFalse(frappe.db.exists("User", email), "User tidak boleh dibuat pra-site.")

    def test_duplicate_email_returns_same_generic_response(self):
        email = self._email("beta")
        first = register_account("Test Beta", email, "PT Test Beta")
        lead_name = frappe.db.get_value("Lead", {"email_id": email}, "name")
        if lead_name:
            self.created_leads.append(lead_name)

        second = register_account("Test Beta", email, "PT Test Beta Lain")

        self.assertEqual(first, second, "Respons harus seragam untuk mencegah enumerasi email.")
        self.assertEqual(frappe.db.count("Lead", {"email_id": email}), 1)

    def test_invalid_email_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            register_account("Test Gamma", "bukan-email", "PT Gamma")

    def test_missing_fields_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            register_account("", self._email("delta"), "PT Delta")

        with self.assertRaises(frappe.ValidationError):
            register_account("Test Delta", "", "PT Delta")

        with self.assertRaises(frappe.ValidationError):
            register_account("Test Delta", self._email("delta"), "")

    def test_non_developer_site_rejected(self):
        frappe.conf["aios_site_role"] = "client"
        email = self._email("zeta")
        with self.assertRaises(frappe.PermissionError):
            register_account("Test Zeta", email, "PT Zeta")
        self.assertFalse(frappe.db.exists("Lead", {"email_id": email}))
