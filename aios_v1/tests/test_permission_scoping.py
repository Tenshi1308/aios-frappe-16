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
    frappe.db.set_value("AIOS Setting", "AIOS Setting", "max_users", 20, update_modified=False)
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

    def test_channel_and_owner_role_validation_requires_active_client(self):
        """Keputusan 7 (Lapis 1): AIOS Channel Receiver & AIOS Client Owner wajib punya AIOS Client aktif."""
        frappe.set_user("Administrator")
        # 1) User tanpa Role AIOS Client ditolak:
        non_client = frappe.get_doc(
            {
                "doctype": "User",
                "email": "_test.scope.nonclient.role@example.com",
                "first_name": "Non Client",
                "enabled": 1,
                "send_welcome_email": 0,
                "user_type": "Website User",
                "roles": [{"role": "AIOS Channel Receiver"}],
            }
        )
        with self.assertRaises(frappe.ValidationError):
            non_client.insert(ignore_permissions=True)

        # 2) User AIOS Client yang belum Active (Pending Provisioning) ditolak diberi AIOS Client Owner:
        pending_client = frappe.get_doc(
            {
                "doctype": "User",
                "email": "_test.scope.pending.role@example.com",
                "first_name": "Pending Client",
                "enabled": 0,
                "send_welcome_email": 0,
                "user_type": "Website User",
                "aios_status": "Pending Provisioning",
                "roles": [{"role": "AIOS Client"}, {"role": "AIOS Client Owner"}],
            }
        )
        with self.assertRaises(frappe.ValidationError):
            pending_client.insert(ignore_permissions=True)

        # 3) User AIOS Client aktif diizinkan menerima AIOS Channel Receiver Profile & AIOS Client Owner Profile:
        self.alpha.append("role_profiles", {"role_profile": "AIOS Client Profile"})
        self.alpha.append("role_profiles", {"role_profile": "AIOS Channel Receiver Profile"})
        self.alpha.append("role_profiles", {"role_profile": "AIOS Client Owner Profile"})
        self.alpha.save(ignore_permissions=True)
        alpha_roles = [r.role for r in self.alpha.roles]
        self.assertIn("AIOS Channel Receiver", alpha_roles)
        self.assertIn("AIOS Client Owner", alpha_roles)

    def test_max_users_validation_blocks_over_limit_and_allows_after_suspend(self):
        """Keputusan 19: plafon AIOS Setting.max_users ditegakkan di User.before_insert & User.validate."""
        from aios_v1.setup import count_active_client_users

        frappe.set_user("Administrator")
        current_active = count_active_client_users()
        frappe.db.set_value(
            "AIOS Setting", "AIOS Setting", "max_users", current_active, update_modified=False
        )

        # Penambahan user AIOS Client aktif baru ketika kursi penuh harus ditolak:
        over_user = frappe.get_doc(
            {
                "doctype": "User",
                "email": "_test.scope.overlimit@example.com",
                "first_name": "Over Limit",
                "enabled": 1,
                "send_welcome_email": 0,
                "user_type": "Website User",
                "aios_status": "Active",
                "roles": [{"role": "AIOS Client"}],
            }
        )
        with self.assertRaises(frappe.ValidationError):
            over_user.insert(ignore_permissions=True)

        # Setelah 1 user AIOS Client dinonaktifkan (Suspended), slot terbuka dan insert berhasil:
        self.beta.aios_status = "Suspended"
        self.beta.enabled = 0
        self.beta.save(ignore_permissions=True)
        over_user.insert(ignore_permissions=True)
        self.assertTrue(frappe.db.exists("User", over_user.name))

    def test_channel_doctype_scoping_for_receiver_vs_regular_client(self):
        """Penerima kanal aktif dapat mengakses AIOS Channel Thread & Flag; AIOS Client biasa ditolak."""
        frappe.set_user("Administrator")
        frappe.db.delete(
            "Has Role",
            {"parenttype": "User", "role": ("in", ["AIOS Channel Receiver", "AIOS Client Owner"])},
        )
        self.alpha.append("roles", {"role": "AIOS Channel Receiver"})
        self.alpha.save(ignore_permissions=True)
        frappe.clear_cache(user=self.alpha.name)
        frappe.clear_cache(user=self.beta.name)

        conv = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": "Guest",
                "branch": "sales",
                "title": "Test Channel Thread",
            }
        ).insert(ignore_permissions=True)
        thread = frappe.get_doc(
            {
                "doctype": "AIOS Channel Thread",
                "channel": "telegram",
                "external_thread_id": "scope-chat-1",
                "conversation": conv.name,
            }
        ).insert(ignore_permissions=True)

        frappe.set_user(self.alpha.name)
        self.assertIn(thread.name, frappe.get_list("AIOS Channel Thread", pluck="name"))
        self.assertTrue(frappe.has_permission("AIOS Channel Thread", "read", doc=thread))

        frappe.set_user(self.beta.name)
        self.assertNotIn(thread.name, frappe.get_list("AIOS Channel Thread", pluck="name"))
        self.assertFalse(frappe.has_permission("AIOS Channel Thread", "read", doc=thread))


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
