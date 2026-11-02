"""Lifecycle target authorization, audit trail, and aggregate consistency tests."""

import importlib
import logging
from contextlib import contextmanager
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase


def _control_api():
	return importlib.import_module("aios_v1.api.control")


class _AuditHandler(logging.Handler):
	def __init__(self):
		super().__init__()
		self.records = []

	def emit(self, record):
		self.records.append(record)


class TestControlLifecycle(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.created_users = []
		self.created_activity_logs = []
		self.created_error_logs = []
		self.control_user = self._make_user("AIOS Control")

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in reversed(self.created_activity_logs):
			if frappe.db.exists("Activity Log", name):
				frappe.delete_doc("Activity Log", name, force=True, ignore_permissions=True)
		for name in reversed(self.created_error_logs):
			if frappe.db.exists("Error Log", name):
				frappe.delete_doc("Error Log", name, force=True, ignore_permissions=True)
		for user in reversed(self.created_users):
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, ignore_permissions=True)
		frappe.db.rollback()
		super().tearDown()

	def _activity_log_names(self):
		return set(frappe.get_all("Activity Log", pluck="name", limit=0))

	def _error_log_names(self):
		return set(frappe.get_all("Error Log", pluck="name", limit=0))

	@contextmanager
	def _capture_audit_logs(self):
		logger = frappe.logger("aios_control", allow_site=True)
		handler = _AuditHandler()
		logger.addHandler(handler)
		try:
			yield handler.records
		finally:
			logger.removeHandler(handler)

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
			self.assertEqual(set(result), {"ok", "user", "aios_status", "invitation_url"})
			self.assertEqual(
				{key: result[key] for key in ("ok", "user", "aios_status")},
				{"ok": True, "user": target, "aios_status": status},
			)
			if status == "Active":
				# Tautan dinamis (host + key acak): yang diuji bentuknya, bukan URL eksak.
				parsed = urlparse(result["invitation_url"])
				self.assertEqual(parsed.path, "/update-password")
				self.assertTrue(parse_qs(parsed.query).get("key"), "Tautan tanpa parameter key")
			else:
				self.assertIsNone(result["invitation_url"], "Status Suspended tidak menerbitkan tautan.")
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
			{"site_tokens_used", "site_token_limit", "active_users", "total_users", "pending_users", "tokens_today"},
		)

	def test_audit_writes_to_logger_handler(self):
		control_api = _control_api()
		target = self._make_user("AIOS Client")
		before = self._activity_log_names()
		with self._capture_audit_logs() as records:
			self._invoke(control_api.activate_user, user=target, status="Suspended")

		self.assertTrue(records, "captured: 0 audit records")
		audit = next((record for record in records if "action=activate_user " in record.getMessage()), None)
		self.assertIsNotNone(audit, "No activate_user audit record captured")
		self.assertEqual(audit.levelno, logging.INFO)
		self.created_activity_logs.extend(self._activity_log_names() - before)

	def test_audit_rejection_is_written_to_logger(self):
		control_api = _control_api()
		target = self._make_user("System Manager")
		with self._capture_audit_logs() as records:
			with self.assertRaises(frappe.ValidationError):
				self._invoke(control_api.activate_user, user=target, status="Suspended")

		rejected = next(
			(record for record in records if "action=activate_user_rejected " in record.getMessage()), None
		)
		self.assertIsNotNone(rejected, "No rejection audit record captured")
		self.assertEqual(rejected.levelno, logging.INFO)
		self.assertIn("reason=not_aios_client", rejected.getMessage())

	def test_activate_user_creates_activity_log(self):
		control_api = _control_api()
		target = self._make_user("AIOS Client")
		before = self._activity_log_names()
		result = self._invoke(control_api.activate_user, user=target, status="Suspended")
		new_names = self._activity_log_names() - before
		self.created_activity_logs.extend(new_names)

		self.assertTrue(result["ok"])
		self.assertEqual(len(new_names), 1)
		activity = frappe.get_doc("Activity Log", next(iter(new_names)))
		self.assertEqual(activity.user, self.control_user)
		self.assertEqual(activity.status, "Success")
		self.assertIn(target, activity.subject)
		self.assertIn("Suspended", activity.subject)

	def test_activity_log_failure_does_not_block_activation(self):
		control_api = _control_api()
		target = self._make_user("AIOS Client")
		before_activity = self._activity_log_names()
		before_errors = self._error_log_names()
		original_get_doc = frappe.get_doc

		def fail_activity_log(*args, **kwargs):
			doctype = args[0] if args else kwargs.get("doctype")
			if isinstance(doctype, dict):
				doctype = doctype.get("doctype")
			if doctype == "Activity Log":
				raise frappe.ValidationError("simulated activity log failure")
			return original_get_doc(*args, **kwargs)

		with patch("aios_v1.api.control.frappe.get_doc", side_effect=fail_activity_log):
			result = self._invoke(control_api.activate_user, user=target, status="Suspended")
		new_errors = self._error_log_names() - before_errors
		self.created_error_logs.extend(new_errors)
		self.created_activity_logs.extend(self._activity_log_names() - before_activity)

		self.assertEqual(
			result,
			{"ok": True, "user": target, "aios_status": "Suspended", "invitation_url": None},
		)
		self.assertEqual(
			frappe.db.get_value("User", target, ["aios_status", "enabled"], as_dict=True),
			{"aios_status": "Suspended", "enabled": 0},
		)
		self.assertEqual(len(new_errors), 1)

	def test_read_only_endpoints_do_not_create_activity_log(self):
		control_api = _control_api()
		before = self._activity_log_names()
		self._invoke(control_api.health)
		self._invoke(control_api.users)
		self._invoke(control_api.metrics)
		self.assertEqual(self._activity_log_names(), before)

	def test_control_role_cannot_read_aios_setting_or_business_doctypes(self):
		control_api = _control_api()
		frappe.set_user(self.control_user)
		self.assertFalse(frappe.has_permission("AIOS Setting", "read"))
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list("Sales Invoice", limit=1)
		frappe.get_list("AIOS Token Usage", limit=1)
		self.assertTrue(frappe.has_permission("AIOS Token Usage", "read"))
		self.assertEqual(control_api._CLIENT_ROLE, "AIOS Client")
