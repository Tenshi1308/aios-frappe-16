"""Tests for the implicit ``AIOS Client`` role filter in the Control API."""

import importlib
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase

_EXPECTED_USER_FIELDS = {
	"name",
	"full_name",
	"aios_status",
	"aios_persona",
	"enabled",
	"last_login",
}


def _control_api():
	return importlib.import_module("aios_v1.api.control")


class TestControlPendingQueue(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.created_users = []
		self.control_user = self._make_user("AIOS Control", status="Active")
		self.client_pending = self._make_user("AIOS Client", status="Pending Provisioning")
		self.client_active = self._make_user("AIOS Client", status="Active")
		self.system_pending = self._make_user("System Manager", status="Pending Provisioning")

	def tearDown(self):
		frappe.set_user("Administrator")
		for user in reversed(self.created_users):
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, ignore_permissions=True)
		frappe.db.rollback()
		super().tearDown()

	def _make_user(self, role, *, status):
		email = f"_test.control-pending.{uuid4().hex}@example.test"
		self.created_users.append(email)
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "_Test Control Pending",
				"enabled": 1,
				"send_welcome_email": 0,
				"user_type": "Website User",
				"aios_status": status,
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)
		return email

	def _invoke(self, function, **kwargs):
		frappe.set_user(self.control_user)
		with patch(
			"aios_v1.api.control.frappe.get_request_header",
			return_value="token test-control-key:test-control-secret",
		):
			return function(**kwargs)

	def test_users_without_arguments_only_returns_aios_client_role(self):
		control_api = _control_api()
		result = self._invoke(control_api.users)
		names = {user["name"] for user in result["users"]}

		self.assertIn(self.client_pending, names)
		self.assertIn(self.client_active, names)
		self.assertNotIn(self.system_pending, names)
		self.assertNotIn("Administrator", names)
		self.assertNotIn("Guest", names)
		for user in result["users"]:
			self.assertIn("AIOS Client", frappe.get_roles(user["name"]), user["name"])

	def test_status_filter_is_applied_on_top_of_role_filter(self):
		control_api = _control_api()
		result = self._invoke(control_api.users, status="Pending Provisioning")
		names = {user["name"] for user in result["users"]}

		self.assertIn(self.client_pending, names)
		self.assertNotIn(self.client_active, names)
		self.assertNotIn(self.system_pending, names)
		self.assertNotIn("Administrator", names)
		self.assertNotIn("Guest", names)

	def test_response_contract_is_unchanged(self):
		control_api = _control_api()
		result = self._invoke(control_api.users)

		self.assertEqual(set(result), {"users", "total", "page", "page_size"})
		self.assertEqual(result["page"], 1)
		self.assertEqual(result["page_size"], 50)
		self.assertGreaterEqual(result["total"], len(result["users"]))
		self.assertNotIn("Administrator", {user["name"] for user in result["users"]})
		self.assertNotIn("Guest", {user["name"] for user in result["users"]})
		for user in result["users"]:
			self.assertEqual(set(user), _EXPECTED_USER_FIELDS, user["name"])
