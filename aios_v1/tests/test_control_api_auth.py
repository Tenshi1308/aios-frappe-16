"""Contract tests for the token-only developer Control API."""

import importlib
from unittest.mock import patch
from uuid import uuid4

import frappe

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _control_api():
	return importlib.import_module("aios_v1.api.control")


class TestControlApiAuth(IntegrationTestCase):
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
		email = f"_test.control-api.{uuid4().hex}@example.test"
		self.created_users.append(email)
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "_Test Control API",
				"enabled": enabled,
				"send_welcome_email": 0,
				"user_type": "Website User",
				"aios_status": status,
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)
		return email

	def _invoke(
		self,
		function,
		*,
		session_user=None,
		authorization="token test-api-key:test-api-secret",
		**kwargs,
	):
		frappe.set_user(session_user or self.control_user)
		with patch("aios_v1.api.control.frappe.get_request_header", return_value=authorization):
			return function(**kwargs)

	def test_t1_missing_authorization_header_is_rejected(self):
		control_api = _control_api()
		with self.assertRaises(frappe.PermissionError):
			self._invoke(control_api.health, authorization=None)
		with patch("aios_v1.api.control.frappe.logger"):
			payload = self._invoke(control_api.health, authorization="Token test-api-key:test-api-secret")
		self.assertEqual(set(payload), {"status", "site", "time", "version"})
		self.assertEqual(payload["status"], "ok")

	def test_t2_bearer_authorization_is_rejected(self):
		control_api = _control_api()
		with self.assertRaises(frappe.PermissionError):
			self._invoke(control_api.health, authorization="Bearer test-token")

	def test_t3_user_without_control_role_is_rejected(self):
		control_api = _control_api()
		client = self._make_user("AIOS Client")
		with self.assertRaises(frappe.PermissionError):
			self._invoke(control_api.health, session_user=client)

	def test_t4_guest_is_rejected(self):
		control_api = _control_api()
		with self.assertRaises(frappe.PermissionError):
			self._invoke(control_api.health, session_user="Guest")

	def test_t5_administrator_is_rejected(self):
		control_api = _control_api()
		with self.assertRaises(frappe.PermissionError):
			self._invoke(control_api.health, session_user="Administrator")

	def test_t6_invalid_status_does_not_change_user(self):
		control_api = _control_api()
		target = self._make_user("AIOS Client", status="Active", enabled=1)
		with self.assertRaises(frappe.ValidationError):
			self._invoke(control_api.activate_user, user=target, status="Disabled")
		self.assertEqual(frappe.db.get_value("User", target, "aios_status"), "Active")
		self.assertEqual(frappe.db.get_value("User", target, "enabled"), 1)

	def test_t7_suspending_user_updates_status_and_enabled_together(self):
		control_api = _control_api()
		target = self._make_user("AIOS Client", status="Active", enabled=1)
		result = self._invoke(control_api.activate_user, user=target, status="Suspended")
		self.assertEqual(result, {"ok": True, "user": target, "aios_status": "Suspended"})
		self.assertEqual(
			frappe.db.get_value("User", target, ["aios_status", "enabled"], as_dict=True),
			{"aios_status": "Suspended", "enabled": 0},
		)

	def test_t8_activating_user_updates_status_and_enabled_together(self):
		control_api = _control_api()
		target = self._make_user("AIOS Client", status="Suspended", enabled=0)
		result = self._invoke(control_api.activate_user, user=target, status="Active")
		self.assertEqual(result, {"ok": True, "user": target, "aios_status": "Active"})
		self.assertEqual(
			frappe.db.get_value("User", target, ["aios_status", "enabled"], as_dict=True),
			{"aios_status": "Active", "enabled": 1},
		)

	def test_t9_users_excludes_privileged_users_and_returns_only_allowed_fields(self):
		control_api = _control_api()
		result = self._invoke(control_api.users)
		self.assertEqual(set(result), {"users", "total", "page", "page_size"})
		self.assertNotIn("Administrator", {user["name"] for user in result["users"]})
		self.assertNotIn("Guest", {user["name"] for user in result["users"]})
		allowed = {"name", "full_name", "aios_status", "aios_persona", "enabled", "last_login"}
		for user in result["users"]:
			self.assertEqual(set(user), allowed)

	def test_t10_metrics_returns_only_aggregate_fields(self):
		control_api = _control_api()
		result = self._invoke(control_api.metrics)
		self.assertEqual(
			set(result),
			{"site_tokens_used", "site_token_limit", "active_users", "total_users", "pending_users", "tokens_today"},
		)

	def test_t11_audit_uses_logger_without_authorization_secrets(self):
		control_api = _control_api()
		target = self._make_user("AIOS Client", status="Active", enabled=1)
		api_key = "CONTROL_TEST_KEY_SENTINEL"
		api_secret = "CONTROL_TEST_SECRET_SENTINEL"
		with patch("aios_v1.api.control.frappe.logger") as logger_factory:
			self._invoke(
				control_api.activate_user,
				user=target,
				status="Suspended",
				authorization=f"token {api_key}:{api_secret}",
			)
		logger_factory.assert_called_once_with("aios_control", allow_site=True)
		logger = logger_factory.return_value
		logger.info.assert_called_once()
		logged = logger.info.call_args.args[0]
		self.assertIn("action=activate_user", logged)
		self.assertIn(f"target={target}", logged)
		self.assertNotIn(api_key, logged)
		self.assertNotIn(api_secret, logged)
