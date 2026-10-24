"""#4a-1: matriks izin `AIOS Client` / `AIOS Control` / `System Manager`.

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

from unittest.mock import patch

import frappe

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


ALPHA = "_test.scope.alpha@example.com"
BETA = "_test.scope.beta@example.com"
CONTROL = "_test.scope.control@example.com"
SYSTEM_MANAGER = "_test.scope.sysman@example.com"


def _make_user(email, role, user_type="Website User"):
    if frappe.db.exists("User", email):
        user = frappe.get_doc("User", email)
    else:
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": email.split("@")[0],
                "enabled": 1,
                "send_welcome_email": 0,
                "user_type": user_type,
                "roles": [{"role": role}],
            }
        )
        if role == "AIOS Client":
            user.aios_status = "Active"
        user.insert(ignore_permissions=True)
    return user


def _usage(user, model="test-model"):
    return frappe.get_doc(
        {
            "doctype": "AIOS Token Usage",
            "user": user,
            "provider": "test-provider",
            "model": model,
            "branch": "finance",
            "agent": "manager",
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "cost": 1.5,
        }
    ).insert(ignore_permissions=True)


class TestPermissionScoping(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.alpha = _make_user(ALPHA, "AIOS Client")
        self.beta = _make_user(BETA, "AIOS Client")
        self.control = _make_user(CONTROL, "AIOS Control", user_type="System User")
        self.system_manager = _make_user(
            SYSTEM_MANAGER, "System Manager", user_type="System User"
        )
        self.usage_alpha = _usage(self.alpha.name)
        self.usage_beta = _usage(self.beta.name)

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def test_client_sees_only_own_token_usage(self):
        frappe.set_user(self.alpha.name)
        names = frappe.get_list("AIOS Token Usage", pluck="name", limit=0)
        self.assertIn(self.usage_alpha.name, names)
        self.assertNotIn(self.usage_beta.name, names)

        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc(
                "AIOS Token Usage", self.usage_beta.name, check_permission="read"
            )

    def test_client_cannot_write_token_usage(self):
        frappe.set_user(self.alpha.name)
        self.assertFalse(frappe.has_permission("AIOS Token Usage", "write"))
        self.assertFalse(frappe.has_permission("AIOS Token Usage", "create"))

        doc = frappe.get_doc("AIOS Token Usage", self.usage_alpha.name)
        doc.cost = 99
        with self.assertRaises(frappe.PermissionError):
            doc.save()

    def test_control_can_read_user_and_token_usage(self):
        frappe.set_user(self.control.name)
        users = frappe.get_list("User", fields=["name"], limit=1)
        self.assertTrue(users)

        names = frappe.get_list("AIOS Token Usage", pluck="name", limit=0)
        self.assertIn(self.usage_alpha.name, names)
        self.assertIn(self.usage_beta.name, names)

    def test_control_cannot_read_setting_or_erpnext(self):
        frappe.set_user(self.control.name)
        self.assertFalse(frappe.has_permission("AIOS Setting", "read"))
        self.assertFalse(frappe.has_permission("Sales Order", "read"))

    def test_client_erpnext_read_report_only(self):
        frappe.set_user(self.alpha.name)
        self.assertTrue(frappe.has_permission("Sales Order", "read"))
        self.assertTrue(frappe.has_permission("Sales Order", "report"))
        self.assertFalse(frappe.has_permission("Sales Order", "write"))

    def test_system_manager_setting_read_only(self):
        frappe.set_user(self.system_manager.name)
        self.assertTrue(frappe.has_permission("AIOS Setting", "read"))
        self.assertFalse(frappe.has_permission("AIOS Setting", "write"))

    def test_aios_admin_has_no_client_docperm(self):
        for doctype in (
            "AIOS Conversation",
            "Pending Action Draft",
            "AIOS Token Usage",
            "Sales Order",
        ):
            self.assertFalse(
                frappe.db.exists(
                    "Custom DocPerm",
                    {"parent": doctype, "role": "AIOS Admin"},
                ),
                doctype,
            )


def _active_company():
    from aios_v1.lib.tool_registry import _resolve_allowed_company

    return _resolve_allowed_company()


class TestERPCompanyScope(IntegrationTestCase):
    """Company-scope `AIOS Client` di layer Frappe (hook permission).

    Regresi bug 2026-10-24: client melihat GL Entry/Account dua company lewat
    get_list dan has_permission doc company lain = True. Scope wajib mengikuti
    `AIOS Setting.default_company` (fallback `Global Defaults`), bukan hardcode.
    """

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.alpha = _make_user(ALPHA, "AIOS Client")
        self.allowed = _active_company()
        non_test = [
            row.name
            for row in frappe.get_all("Company", fields=["name"])
            if not row.name.startswith("_Test")
        ]
        self.other = next((name for name in non_test if name != self.allowed), None)
        if not self.other:
            self.skipTest("Butuh dua company non-test untuk membedakan scope.")

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def test_client_list_gl_entry_only_active_company(self):
        frappe.set_user(self.alpha.name)
        companies = {
            row.company
            for row in frappe.get_list("GL Entry", fields=["company"], limit_page_length=0)
        }
        self.assertEqual(companies, {self.allowed})

    def test_client_list_account_other_company_empty_active_nonempty(self):
        frappe.set_user(self.alpha.name)
        other_rows = frappe.get_list(
            "Account", filters={"company": self.other}, limit_page_length=1
        )
        active_rows = frappe.get_list(
            "Account", filters={"company": self.allowed}, limit_page_length=1
        )
        self.assertEqual(other_rows, [])
        self.assertTrue(active_rows)

    def test_client_list_company_only_active(self):
        frappe.set_user(self.alpha.name)
        names = frappe.get_list("Company", pluck="name", limit_page_length=0)
        self.assertEqual(names, [self.allowed])

    def test_client_doc_permission_company_pair(self):
        frappe.set_user(self.alpha.name)
        self.assertFalse(
            frappe.has_permission("Company", "read", doc=self.other),
            "doc company lain harus ditolak",
        )
        self.assertTrue(frappe.has_permission("Company", "read", doc=self.allowed))

    def test_client_get_doc_other_company_denied_active_allowed(self):
        frappe.set_user(self.alpha.name)
        other_account = frappe.db.get_value("Account", {"company": self.other}, "name")
        active_account = frappe.db.get_value("Account", {"company": self.allowed}, "name")
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc("Account", other_account, check_permission="read")
        self.assertEqual(
            frappe.get_doc("Account", active_account, check_permission="read").company,
            self.allowed,
        )

    def test_master_without_company_field_not_scoped(self):
        frappe.set_user(self.alpha.name)
        self.assertIsInstance(frappe.get_list("Customer", limit_page_length=5), list)
        self.assertIsInstance(frappe.get_list("Item", limit_page_length=5), list)

    def test_administrator_still_sees_both_companies(self):
        frappe.set_user("Administrator")
        companies = {
            row.company
            for row in frappe.get_list("GL Entry", fields=["company"], limit_page_length=0)
        }
        self.assertIn(self.allowed, companies)
        self.assertIn(self.other, companies)

    def test_scope_follows_dynamic_setting(self):
        frappe.set_user(self.alpha.name)
        with patch(
            "aios_v1.lib.tool_registry._resolve_allowed_company", return_value=self.other
        ):
            companies = {
                row.company
                for row in frappe.get_list("GL Entry", fields=["company"], limit_page_length=0)
            }
        self.assertEqual(companies, {self.other})
