"""#4a-1: matriks izin `AIOS Client` / `AIOS Control` / `System Manager`.

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

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
