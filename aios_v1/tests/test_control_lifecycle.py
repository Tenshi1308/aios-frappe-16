"""Lifecycle target authorization and aggregate consistency tests."""

import importlib
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase


def _control_api():
	return importlib.import_module("aios_v1.api.control")


class TestControlLifecycle(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.created_users = []
		self.control_user = self._make_user("AIOS Control")

	def tearDown(self):
		frappe.set_user("Administrator")
		for user in reversed(self.created_users):
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, ignore_permissions=True)
		frappe.db.rollback()
		super().tearDown()

	def _make_user(self, role, *, status="Active", enabled=1):
		email = f"_test.control-lifecycle.{uuid4().hex}@example.test"
		self.created_users.append(email)
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "_Test Control Lifecycle",
				"enabled": enabled,
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
			return_value="token test-lifecycle-key:test-lifecycle-secret",
		):
			return function(**kwargs)

	def test_activate_user_rejects_user_without_client_role(self):
		control_api = _control_api()
		target = self._make_user("System Manager", status="Active", enabled=1)
		with self.assertRaises(frappe.ValidationError):
			self._invoke(control_api.activate_user, user=target, status="Suspended")
		self.assertEqual(
			frappe.db.get_value("User", target, ["aios_status", "enabled"], as_dict=True),
			{"aios_status": "Active", "enabled": 1},
		)

	def test_activate_user_rejects_administrator(self):
		control_api = _control_api()
		with self.assertRaises(frappe.ValidationError):
			self._invoke(control_api.activate_user, user="Administrator", status="Suspended")
		self.assertEqual(frappe.db.get_value("User", "Administrator", "enabled"), 1)

	def test_activate_user_rejects_guest(self):
		control_api = _control_api()
		with self.assertRaises(frappe.ValidationError):
			self._invoke(control_api.activate_user, user="Guest", status="Suspended")

	def test_activate_user_accepts_client_role(self):
		control_api = _control_api()
		target = self._make_user("AIOS Client", status="Active", enabled=1)
		for status, enabled in (("Suspended", 0), ("Active", 1)):
			result = self._invoke(control_api.activate_user, user=target, status=status)
			self.assertEqual(result, {"ok": True, "user": target, "aios_status": status})
			self.assertEqual(
				frappe.db.get_value("User", target, ["aios_status", "enabled"], as_dict=True),
				{"aios_status": status, "enabled": enabled},
			)

	def test_metrics_counts_only_client_role_users(self):
		control_api = _control_api()
		self._make_user("AIOS Client")
		before = self._invoke(control_api.metrics)
		system_manager = self._make_user("System Manager")

		metrics = self._invoke(control_api.metrics)
		users = self._invoke(control_api.users)
		self.assertEqual(metrics["total_users"], before["total_users"])
		self.assertEqual(metrics["total_users"], users["total"])
		self.assertNotIn(system_manager, {user["name"] for user in users["users"]})

	def test_metrics_response_contract_is_unchanged(self):
		control_api = _control_api()
		result = self._invoke(control_api.metrics)
		self.assertEqual(
			set(result),
			{"site_tokens_used", "site_token_limit", "active_users", "total_users", "tokens_today"},
		)
