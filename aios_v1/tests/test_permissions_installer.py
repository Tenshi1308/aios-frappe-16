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
