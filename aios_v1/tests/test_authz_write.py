"""P0/P1: isolasi tulis-hapus lintas user + bypass `AIOS Admin`.

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import unittest

import frappe

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _make_test_user(email, first_name, role):
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    doc = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "enabled": 1,
            "send_welcome_email": 0,
            "user_type": "System User" if role == "AIOS Admin" else "Website User",
            "aios_status": "Active",
            "roles": [{"role": role}],
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


class TestWriteIsolation(IntegrationTestCase):
    ALPHA = "_test.write.alpha@example.com"
    BETA = "_test.write.beta@example.com"
    ADMIN = "_test.write.admin@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        _make_test_user(self.ALPHA, "_Test Write Alpha", "AIOS Client")
        _make_test_user(self.BETA, "_Test Write Beta", "AIOS Client")
        _make_test_user(self.ADMIN, "_Test Write Admin", "AIOS Admin")
        self.beta_conv = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": self.BETA,
                "branch": "sales",
                "title": "_Test Beta write",
            }
        ).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def test_alpha_cannot_write_beta_conversation(self):
        frappe.set_user(self.ALPHA)
        doc = frappe.get_doc("AIOS Conversation", self.beta_conv.name)
        doc.title = "diubah Alpha"
        with self.assertRaises(frappe.PermissionError):
            doc.save()

    def test_alpha_cannot_delete_beta_conversation(self):
        frappe.set_user(self.ALPHA)
        with self.assertRaises(frappe.PermissionError):
            frappe.delete_doc("AIOS Conversation", self.beta_conv.name)

    def test_alpha_cannot_create_for_other_user(self):
        frappe.set_user(self.ALPHA)
        doc = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": self.BETA,
                "branch": "sales",
                "title": "_Test Alpha nakal",
            }
        )
        with self.assertRaises(frappe.PermissionError):
            doc.insert()

    def test_alpha_can_create_own_conversation(self):
        frappe.set_user(self.ALPHA)
        doc = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": self.ALPHA,
                "branch": "sales",
                "title": "_Test Alpha own",
            }
        ).insert()
        self.assertEqual(doc.user, self.ALPHA)

    def test_alpha_can_write_own_conversation(self):
        own = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": self.ALPHA,
                "branch": "sales",
                "title": "_Test Alpha write own",
            }
        ).insert(ignore_permissions=True)
        frappe.set_user(self.ALPHA)
        doc = frappe.get_doc("AIOS Conversation", own.name)
        doc.title = "judul baru"
        doc.save()
        self.assertEqual(
            frappe.db.get_value("AIOS Conversation", own.name, "title"),
            "judul baru",
        )

    def test_alpha_can_delete_own_conversation(self):
        own = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": self.ALPHA,
                "branch": "sales",
                "title": "_Test Alpha delete own",
            }
        ).insert(ignore_permissions=True)
        frappe.set_user(self.ALPHA)
        frappe.delete_doc("AIOS Conversation", own.name)
        self.assertFalse(frappe.db.exists("AIOS Conversation", own.name))

    def test_aios_admin_can_read_and_write_beta(self):
        frappe.set_user(self.ADMIN)
        doc = frappe.get_doc(
            "AIOS Conversation", self.beta_conv.name, check_permission="read"
        )
        doc.title = "diedit AIOS Admin"
        doc.save()
        self.assertEqual(
            frappe.db.get_value("AIOS Conversation", self.beta_conv.name, "title"),
            "diedit AIOS Admin",
        )

    def test_aios_admin_can_delete_beta(self):
        frappe.set_user(self.ADMIN)
        frappe.delete_doc("AIOS Conversation", self.beta_conv.name)
        self.assertFalse(
            frappe.db.exists("AIOS Conversation", self.beta_conv.name)
        )
