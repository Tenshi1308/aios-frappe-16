"""P1: `ensure_aios_permissions` idempoten + matriks DocPerm dasar.

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import frappe

from aios_v1.permissions import ERP_CLIENT_DOCTYPES, ensure_aios_permissions

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


class TestPermissionInstaller(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _perm(self, doctype, role, table="Custom DocPerm"):
        return frappe.db.get_value(
            table,
            {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
            ["read", "write", "create", "delete", "report"],
            as_dict=True,
        )

    def test_idempotent(self):
        ensure_aios_permissions()
        ensure_aios_permissions()
        count = frappe.db.count(
            "Custom DocPerm",
            {
                "parent": "AIOS Conversation",
                "role": "AIOS Client",
                "permlevel": 0,
                "if_owner": 0,
            },
        )
        self.assertEqual(count, 1)

    def test_creates_perms_from_scratch(self):
        """Jalur pembuatan (`add_permission`) benar-benar dieksekusi, bukan cuma idempoten."""
        frappe.db.delete(
            "Custom DocPerm",
            {
                "parent": "AIOS Conversation",
                "role": ["in", ["AIOS Client", "AIOS Admin"]],
            },
        )
        self.assertIsNone(self._perm("AIOS Conversation", "AIOS Client"))

        ensure_aios_permissions()

        perm = self._perm("AIOS Conversation", "AIOS Client")
        self.assertTrue(perm)
        self.assertEqual(perm["read"], 1)
        self.assertIsNone(self._perm("AIOS Conversation", "AIOS Admin"))

    def test_client_full_on_owned_doctype(self):
        perm = self._perm("AIOS Conversation", "AIOS Client")
        self.assertTrue(perm)
        for ptype in ("read", "write", "create", "delete"):
            self.assertEqual(perm[ptype], 1, ptype)

    def test_client_read_only_on_message(self):
        perm = self._perm("AIOS Message", "AIOS Client")
        self.assertTrue(perm)
        self.assertEqual(perm["read"], 1)
        self.assertEqual(perm["write"], 0)
        self.assertEqual(perm["create"], 0)
        self.assertEqual(perm["delete"], 0)

    def test_client_read_only_on_token_usage(self):
        perm = self._perm("AIOS Token Usage", "AIOS Client")
        self.assertTrue(perm)
        self.assertEqual(perm["read"], 1)
        self.assertEqual(perm["write"], 0)
        self.assertEqual(perm["create"], 0)
        self.assertEqual(perm["delete"], 0)

    def test_control_reads_user_and_token_usage(self):
        user_perm = self._perm("User", "AIOS Control")
        self.assertTrue(user_perm)
        self.assertEqual(user_perm["read"], 1)
        self.assertEqual(user_perm["write"], 0)

        token_perm = self._perm("AIOS Token Usage", "AIOS Control")
        self.assertTrue(token_perm)
        self.assertEqual(token_perm["read"], 1)
        self.assertEqual(token_perm["write"], 0)

    def test_control_has_no_setting_or_erpnext(self):
        self.assertIsNone(self._perm("AIOS Setting", "AIOS Control"))
        self.assertIsNone(self._perm("Sales Order", "AIOS Control"))

    def test_no_admin_perms(self):
        ensure_aios_permissions()
        for doctype in ("AIOS Conversation", "Pending Action Draft", "AIOS Token Usage"):
            self.assertIsNone(self._perm(doctype, "AIOS Admin"), doctype)
        self.assertIsNone(self._perm("Sales Order", "AIOS Admin"))

    def test_client_erpnext_read_report(self):
        ensure_aios_permissions()
        for doctype in ERP_CLIENT_DOCTYPES:
            perm = self._perm(doctype, "AIOS Client")
            self.assertTrue(perm, doctype)
            self.assertEqual(perm["read"], 1, doctype)
            self.assertEqual(perm["report"], 1, doctype)
            self.assertEqual(perm["write"], 0, doctype)
            self.assertEqual(perm["create"], 0, doctype)
            self.assertEqual(perm["delete"], 0, doctype)

    def test_system_manager_setting_read_only(self):
        perm = self._perm("AIOS Setting", "System Manager", table="DocPerm")
        self.assertTrue(perm)
        self.assertEqual(perm["read"], 1)
        self.assertEqual(perm["write"], 0)
        self.assertEqual(perm["create"], 0)
        self.assertEqual(perm["delete"], 0)


CLIENT = "_test.report.roles@example.com"


def _make_client_user():
    if frappe.db.exists("User", CLIENT):
        return frappe.get_doc("User", CLIENT)
    doc = frappe.get_doc(
        {
            "doctype": "User",
            "email": CLIENT,
            "first_name": "_Test Report Roles",
            "enabled": 1,
            "send_welcome_email": 0,
            "user_type": "Website User",
            "aios_status": "Active",
            "roles": [{"role": "AIOS Client"}],
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


class TestReportRolesInstaller(IntegrationTestCase):
    """B/C: `Custom Role` rebuild untuk report `ALLOWED_REPORTS` + Purchase Invoice.

    Regresi: sebelum B/C, `Report.is_permitted()` = False untuk `AIOS Client`
    pada semua 8 report (Has Role Report tidak memuat role client) dan
    `Purchase Invoice` tanpa Custom DocPerm read/report.
    """

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.client_user = _make_client_user()
        from aios_v1.lib.erpnext_financial_reports import ALLOWED_REPORTS

        self.reports = sorted(ALLOWED_REPORTS)
        for report_name in self.reports:
            if not frappe.db.exists("Report", report_name):
                self.skipTest(f"Report {report_name} tidak ada di site.")

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _custom_roles(self, report_name):
        doc = frappe.get_doc("Custom Role", {"report": report_name})
        return [d.role for d in doc.get("roles") or []]

    def _has_role_report(self, report_name):
        return [d.role for d in frappe.get_all("Has Role", fields=["role"], filters={"parent": report_name})]

    def test_rebuild_creates_custom_role_with_union(self):
        ensure_aios_permissions()
        for report_name in self.reports:
            self.assertEqual(
                frappe.db.count("Custom Role", {"report": report_name}), 1, report_name
            )
            roles = self._custom_roles(report_name)
            self.assertIn("AIOS Client", roles, report_name)
            for role in self._has_role_report(report_name):
                self.assertIn(role, roles, f"{report_name}: role {role} hilang")

    def test_rebuild_is_idempotent_and_single_client_role(self):
        ensure_aios_permissions()
        ensure_aios_permissions()
        for report_name in self.reports:
            self.assertEqual(
                frappe.db.count("Custom Role", {"report": report_name}), 1, report_name
            )
            self.assertEqual(self._custom_roles(report_name).count("AIOS Client"), 1, report_name)

    def test_rebuild_replaces_stale_roles(self):
        ensure_aios_permissions()
        doc = frappe.get_doc("Custom Role", {"report": "Trial Balance"})
        doc.append("roles", {"role": "System Manager"})
        doc.save(ignore_permissions=True)
        ensure_aios_permissions()
        roles = self._custom_roles("Trial Balance")
        self.assertNotIn("System Manager", roles)
        self.assertIn("AIOS Client", roles)
        for role in self._has_role_report("Trial Balance"):
            self.assertIn(role, roles)

    def test_rebuild_picks_up_new_has_role(self):
        ensure_aios_permissions()
        report_doc = frappe.get_doc("Report", "Trial Balance")
        report_doc.append("roles", {"role": "Sales Manager"})
        report_doc.save(ignore_permissions=True)
        ensure_aios_permissions()
        roles = self._custom_roles("Trial Balance")
        self.assertIn("Sales Manager", roles)
        self.assertIn("AIOS Client", roles)

    def test_report_without_roles_not_tightened(self):
        report_doc = frappe.get_doc(
            {
                "doctype": "Report",
                "report_name": "_Test Open Report",
                "ref_doctype": "Sales Order",
                "module": "Accounts",
                "is_standard": "No",
                "report_type": "Query Report",
            }
        ).insert(ignore_permissions=True)
        ensure_aios_permissions()
        self.assertIsNone(
            frappe.db.get_value("Custom Role", {"report": report_doc.name})
        )
        self.assertIsNone(frappe.db.get_value("Custom Role", {"page": report_doc.name}))

    def test_client_is_permitted_for_all_allowlisted_reports(self):
        ensure_aios_permissions()
        frappe.set_user(self.client_user.name)
        permitted = {
            report_name: frappe.get_doc("Report", report_name).is_permitted()
            for report_name in self.reports
        }
        self.assertTrue(all(permitted.values()), permitted)

    def test_report_outside_allowlist_still_denied_for_client(self):
        ensure_aios_permissions()
        outside = "Accounts Receivable Summary"
        if not frappe.db.exists("Report", outside):
            self.skipTest(f"Report {outside} tidak ada di site.")
        frappe.set_user(self.client_user.name)
        self.assertFalse(frappe.get_doc("Report", outside).is_permitted())

    def test_purchase_invoice_read_report_only(self):
        ensure_aios_permissions()
        perm = frappe.db.get_value(
            "Custom DocPerm",
            {"parent": "Purchase Invoice", "role": "AIOS Client", "permlevel": 0, "if_owner": 0},
            ["read", "report", "write", "create", "delete"],
            as_dict=True,
        )
        self.assertTrue(perm)
        self.assertEqual(perm["read"], 1)
        self.assertEqual(perm["report"], 1)
        self.assertEqual(perm["write"], 0)
        self.assertEqual(perm["create"], 0)
        self.assertEqual(perm["delete"], 0)
        frappe.set_user(self.client_user.name)
        self.assertTrue(frappe.has_permission("Purchase Invoice", "read"))
        self.assertTrue(frappe.has_permission("Purchase Invoice", "report"))
        self.assertFalse(frappe.has_permission("Purchase Invoice", "write"))
        self.assertFalse(frappe.has_permission("Purchase Invoice", "create"))
        self.assertFalse(frappe.has_permission("Purchase Invoice", "delete"))

    def test_purchase_invoice_company_scoped_for_client(self):
        ensure_aios_permissions()
        from aios_v1.lib.tool_registry import _resolve_allowed_company

        active = _resolve_allowed_company()
        non_test = [
            row.name
            for row in frappe.get_all("Company", fields=["name"])
            if not row.name.startswith("_Test")
        ]
        other = next((name for name in non_test if name != active), None)
        if not other:
            self.skipTest("Butuh dua company non-test.")
        frappe.set_user(self.client_user.name)
        self.assertEqual(
            frappe.get_list("Purchase Invoice", filters={"company": other}, limit_page_length=1),
            [],
        )
        self.assertTrue(
            frappe.get_list("Purchase Invoice", filters={"company": active}, limit_page_length=1)
        )

    def test_administrator_bypasses_report_roles(self):
        ensure_aios_permissions()
        outside = "Accounts Receivable Summary"
        if not frappe.db.exists("Report", outside):
            self.skipTest(f"Report {outside} tidak ada di site.")
        frappe.set_user("Administrator")
        self.assertTrue(frappe.get_doc("Report", outside).is_permitted())

    def test_report_without_has_role_keeps_existing_custom_role(self):
        """Report allowlisted yang Has Role-nya kosong tidak boleh disentuh:
        Custom Role existing tetap utuh (tidak dibangun ulang jadi ["AIOS Client"])."""
        ensure_aios_permissions()
        frappe.db.delete("Has Role", {"parent": "Trial Balance", "parenttype": "Report"})
        frappe.db.delete("Custom Role", {"report": "Trial Balance"})
        frappe.get_doc(
            {
                "doctype": "Custom Role",
                "report": "Trial Balance",
                "ref_doctype": "GL Entry",
                "roles": [{"role": "System Manager"}],
            }
        ).insert(ignore_permissions=True)
        ensure_aios_permissions()
        doc = frappe.get_doc("Custom Role", {"report": "Trial Balance"})
        roles = [d.role for d in doc.get("roles") or []]
        self.assertEqual(
            roles, ["System Manager"], "Custom Role report tanpa Has Role tidak boleh diubah"
        )
