"""Test keamanan isolasi antar-User (IDOR N2/S3) — docs/05 §6c.

Baseline #1: sengaja MERAH sebelum #1. Butuh site + DB → jalan via
`bench --site aios-v16.localhost run-tests --app aios_v1`, auto-skip di CI.
"""

import unittest

import frappe

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _make_test_user(email, first_name):
    """Buat User dummy prefiks _Test dengan role AIOS Client (wajib _Test prefix)."""
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
            "roles": [{"role": "AIOS Client"}],
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


@unittest.skip("baseline #1: sengaja MERAH sebelum #1 (docs/05 §6c); jalan via bench")
class TestUserIsolation(IntegrationTestCase):
    """Alpha akses resource Beta → 403/404; tanpa cookie → 401."""

    ALPHA = "_Test User Alpha@example.com"
    BETA = "_Test User Beta@example.com"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Penangkal 87 db.commit() manual di kode AIOS lama (docs/05 §6b.3)
        cls._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        _make_test_user(cls.ALPHA, "_Test User Alpha")
        _make_test_user(cls.BETA, "_Test User Beta")

    @classmethod
    def tearDownClass(cls):
        frappe.db.commit = cls._orig_commit
        super().tearDownClass()

    def tearDown(self):
        frappe.db.rollback()

    def _beta_resources(self):
        """Kembalikan (doctype, name) milik Beta untuk tiap resource."""
        from frappe.utils import now_datetime

        resources = []
        conv = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": self.BETA,
                "title": "_Test Beta conversation",
                "datetime": str(now_datetime()),
            }
        ).insert(ignore_permissions=True)
        resources.append(("AIOS Conversation", conv.name))
        msg = frappe.get_doc(
            {
                "doctype": "AIOS Message",
                "conversation": conv.name,
                "user": self.BETA,
                "role": "user",
                "content": "beta-only",
            }
        ).insert(ignore_permissions=True)
        resources.append(("AIOS Message", msg.name))
        conn = frappe.get_doc(
            {
                "doctype": "AIOS DB Connection",
                "connection_name": "_Test Beta Connection",
                "user": self.BETA,
            }
        ).insert(ignore_permissions=True)
        resources.append(("AIOS DB Connection", conn.name))
        draft = frappe.get_doc(
            {
                "doctype": "Pending Action Draft",
                "task_id": "TEST-BETA-001",
                "user": self.BETA,
                "status": "PENDING_APPROVAL",
            }
        ).insert(ignore_permissions=True)
        resources.append(("Pending Action Draft", draft.name))
        return resources

    def test_alpha_cannot_access_beta_resources(self):
        frappe.set_user(self.ALPHA)
        for doctype, name in self._beta_resources():
            with self.subTest(doctype=doctype, name=name):
                with self.assertRaises((frappe.PermissionError, frappe.DoesNotExistError)):
                    frappe.get_doc(doctype, name)

    def test_alpha_cannot_list_beta_resources(self):
        frappe.set_user(self.ALPHA)
        for doctype in ("AIOS Conversation", "AIOS Message", "AIOS DB Connection"):
            names = frappe.get_list(doctype, filters={"user": self.BETA}, ignore_permissions=False)
            self.assertEqual(names, [], f"{doctype} Beta bocor ke Alpha")

    def test_no_cookie_returns_401(self):
        """Endpoint AIOS tanpa sesi → 401 (perilaku diperbaiki #1; sekarang merah)."""
        from aios_v1.api.dispatcher import handle_api_request

        frappe.set_user("Guest")
        with self.assertRaises(frappe.AuthenticationError):
            handle_api_request()
