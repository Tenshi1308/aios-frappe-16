"""Integration tests for the Control API HTTP client."""

import json
from unittest.mock import patch
from uuid import uuid4

import frappe
import requests
from frappe.tests import IntegrationTestCase

from aios_v1.lib.control_client import (
	MAX_BODY_BYTES,
	activate_user,
	health,
)

API_CREDENTIAL = "test-secret-abc123"
SITE_SECRET_SENTINEL = "test-secret-abc123"


class _Response:
	def __init__(self, status_code=200, payload=None, *, chunks=None, headers=None):
		self.status_code = status_code
		self.headers = headers or {}
		self._chunks = (
			chunks if chunks is not None else [json.dumps(payload if payload is not None else {}).encode()]
		)
		self.closed = False

	def iter_content(self, chunk_size):
		yield from self._chunks

	def close(self):
		self.closed = True


def _error_log_names():
	return set(frappe.get_all("Error Log", pluck="name", limit=0))


def _new_error_log_texts(before):
	names = list(_error_log_names() - before)
	return [
		f"{row.method or ''}\n{row.error or ''}"
		for row in frappe.get_all(
			"Error Log",
			filters={"name": ["in", names]},
			fields=["method", "error"],
			limit=0,
		)
	]


class TestControlClient(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.site_name = f"test.control-client.{uuid4().hex}.localhost"
		self.site = frappe.get_doc(
			{
				"doctype": "AIOS Managed Site",
				"site_name": self.site_name,
				"base_url": "http://127.0.0.1:8002",
				"api_credential": API_CREDENTIAL,
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		if frappe.db.exists("AIOS Managed Site", self.site_name):
			frappe.delete_doc("AIOS Managed Site", self.site_name, ignore_permissions=True)
		frappe.db.rollback()
		super().tearDown()

	def test_health_returns_unwrapped_payload_and_uses_registry_url(self):
		payload = {
			"message": {
				"status": "ok",
				"site": self.site_name,
				"time": "2026-10-28 10:00:00",
				"version": "1.0.0",
			}
		}
		with patch(
			"aios_v1.lib.control_client.requests.request",
			return_value=_Response(200, payload),
		) as request:
			result = health(self.site_name)

		self.assertEqual(set(result), {"status", "site", "time", "version"})
		self.assertEqual(result["status"], "ok")
		self.assertEqual(result["site"], self.site_name)

		args, kwargs = request.call_args
		self.assertEqual(args[0], "GET")
		self.assertEqual(
			args[1],
			"http://127.0.0.1:8002/api/method/aios_v1.api.control.health",
		)
		self.assertEqual(kwargs["headers"]["Authorization"], f"token {API_CREDENTIAL}")
		self.assertFalse(kwargs["allow_redirects"])
		self.assertEqual(kwargs["timeout"], (5, 10))

	def test_activate_user_sends_post_with_expected_body(self):
		payload = {"message": {"ok": True, "user": "user@example.test", "aios_status": "Active"}}
		with patch(
			"aios_v1.lib.control_client.requests.request",
			return_value=_Response(200, payload),
		) as request:
			result = activate_user(self.site_name, "user@example.test", "Active")

		self.assertEqual(
			result,
			{"ok": True, "user": "user@example.test", "aios_status": "Active"},
		)
		args, kwargs = request.call_args
		self.assertEqual(args[0], "POST")
		self.assertEqual(
			args[1],
			"http://127.0.0.1:8002/api/method/aios_v1.api.control.activate_user",
		)
		self.assertEqual(kwargs["data"], {"user": "user@example.test", "status": "Active"})
		self.assertEqual(kwargs["headers"]["Authorization"], f"token {API_CREDENTIAL}")

	def test_timeout_returns_safe_error_and_logs_once(self):
		before = _error_log_names()
		with patch(
			"aios_v1.lib.control_client.requests.request",
			side_effect=requests.Timeout("read timed out"),
		):
			result = health(self.site_name)
		logs = _new_error_log_texts(before)

		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "CONTROL_TIMEOUT")
		self.assertEqual(len(logs), 1)
		self.assertIn("CONTROL_TIMEOUT", logs[0])

	def test_remote_error_statuses_return_safe_error_and_log(self):
		for status_code in (401, 403, 500):
			with self.subTest(status_code=status_code):
				before = _error_log_names()
				with patch(
					"aios_v1.lib.control_client.requests.request",
					return_value=_Response(status_code, {"exc": "denied"}),
				):
					result = health(self.site_name)
				logs = _new_error_log_texts(before)

				self.assertFalse(result["success"])
				self.assertEqual(result["code"], "REMOTE_HTTP_ERROR")
				self.assertEqual(len(logs), 1)
				self.assertNotIn("127.0.0.1", result["error"])
				self.assertNotIn("http", result["error"])

	def test_oversized_body_is_rejected(self):
		before = _error_log_names()
		with patch(
			"aios_v1.lib.control_client.requests.request",
			return_value=_Response(200, chunks=[b"x" * (MAX_BODY_BYTES + 1)]),
		):
			result = health(self.site_name)
		logs = _new_error_log_texts(before)

		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "RESPONSE_TOO_LARGE")
		self.assertEqual(len(logs), 1)

	def test_credential_never_appears_in_payload_logs_or_error_messages(self):
		success_payload = {
			"message": {
				"status": "ok",
				"site": self.site_name,
				"time": "2026-10-28 10:00:00",
				"version": "1.0.0",
				"echo": f"token {SITE_SECRET_SENTINEL}",
			}
		}
		with patch(
			"aios_v1.lib.control_client.requests.request",
			return_value=_Response(200, success_payload),
		):
			success = health(self.site_name)
		self.assertNotIn(SITE_SECRET_SENTINEL, json.dumps(success))

		before = _error_log_names()
		with patch(
			"aios_v1.lib.control_client.requests.request",
			return_value=_Response(500, {"exc": f"token {SITE_SECRET_SENTINEL}"}),
		):
			failure = health(self.site_name)
		logs = _new_error_log_texts(before)

		self.assertFalse(failure["success"])
		self.assertNotIn(SITE_SECRET_SENTINEL, failure["error"])
		self.assertNotIn(SITE_SECRET_SENTINEL, json.dumps(failure))
		for log in logs:
			self.assertNotIn(SITE_SECRET_SENTINEL, log)

	def test_missing_registry_site_returns_safe_error_not_traceback(self):
		before = _error_log_names()
		result = health(f"test.missing.{uuid4().hex}.localhost")
		logs = _new_error_log_texts(before)

		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "SITE_NOT_FOUND")
		self.assertNotIn("Traceback", result["error"])
		self.assertEqual(len(logs), 1)
