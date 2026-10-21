"""P1: `ensure_aios_permissions` idempoten + matriks DocPerm dasar.

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import unittest

import frappe

from aios_v1.permissions import ensure_aios_permissions

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

    def _perm(self, doctype, role):
        return frappe.db.get_value(
            "Custom DocPerm",
            {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
            ["read", "write", "create", "delete"],
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

    def test_admin_full_on_owned_doctype(self):
        perm = self._perm("Pending Action Draft", "AIOS Admin")
        self.assertTrue(perm)
        for ptype in ("read", "write", "create", "delete"):
            self.assertEqual(perm[ptype], 1, ptype)
