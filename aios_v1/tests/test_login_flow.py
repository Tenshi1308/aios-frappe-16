"""P3: guard 3 lapis `aios_status` (enabled, on_login, auth_hooks).

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import unittest
from types import SimpleNamespace

import frappe

from aios_v1.setup import (
    on_login,
    sync_aios_status_enabled,
    validate_aios_status,
)

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _make_test_user(email, first_name, status):
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    doc = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "enabled": 1 if status == "Active" else 0,
            "send_welcome_email": 0,
            "user_type": "Website User",
            "aios_status": status,
            "roles": [{"role": "AIOS Client"}],
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


class TestLoginFlow(IntegrationTestCase):
    ACTIVE = "_test.login.active@example.com"
    PENDING = "_test.login.pending@example.com"
    SUSPENDED = "_test.login.suspended@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        _make_test_user(self.ACTIVE, "_Test Login Active", "Active")
        _make_test_user(self.PENDING, "_Test Login Pending", "Pending Provisioning")
        _make_test_user(self.SUSPENDED, "_Test Login Suspended", "Suspended")

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def test_on_login_allows_active(self):
        on_login(SimpleNamespace(user=self.ACTIVE))

    def test_on_login_blocks_pending(self):
        with self.assertRaises(frappe.AuthenticationError):
            on_login(SimpleNamespace(user=self.PENDING))

    def test_on_login_blocks_suspended(self):
        with self.assertRaises(frappe.AuthenticationError):
            on_login(SimpleNamespace(user=self.SUSPENDED))

    def test_on_login_ignores_administrator(self):
        on_login(SimpleNamespace(user="Administrator"))

    def test_auth_hook_blocks_pending_session(self):
        frappe.set_user(self.PENDING)
        with self.assertRaises(frappe.AuthenticationError):
            validate_aios_status()

    def test_auth_hook_allows_active_session(self):
        frappe.set_user(self.ACTIVE)
        validate_aios_status()

    def test_auth_hook_ignores_administrator(self):
        frappe.set_user("Administrator")
        validate_aios_status()

    def test_sync_enabled_follows_status(self):
        doc = frappe._dict(
            name="_Test Sync",
            aios_status="Active",
            roles=[frappe._dict(role="AIOS Client")],
            enabled=0,
        )
        sync_aios_status_enabled(doc)
        self.assertEqual(doc.enabled, 1)

        doc.aios_status = "Suspended"
        sync_aios_status_enabled(doc)
        self.assertEqual(doc.enabled, 0)

    def test_sync_skips_administrator(self):
        doc = frappe._dict(
            name="Administrator",
            aios_status="Suspended",
            roles=[frappe._dict(role="AIOS Client")],
            enabled=1,
        )
        sync_aios_status_enabled(doc)
        self.assertEqual(doc.enabled, 1)

    def test_sync_skips_non_aios_user(self):
        doc = frappe._dict(
            name="_Test Non AIOS",
            aios_status="Suspended",
            roles=[frappe._dict(role="System Manager")],
            enabled=1,
        )
        sync_aios_status_enabled(doc)
        self.assertEqual(doc.enabled, 1)
