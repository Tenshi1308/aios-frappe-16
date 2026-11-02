"""Kontrak error handling batch 1: tersanitasi, tercatat, tidak pura-pura sukses.

Jalankan:
    bench --site aios-v16.localhost run-tests --app aios_v1 \
        --module aios_v1.tests.test_error_handling
"""

import json
from unittest.mock import patch

import frappe

from aios_v1.api.dispatcher import CustomAPIResponse, json_error
from aios_v1.lib.error_utils import log_exception, safe_error, sanitize_text
from aios_v1.lib.tool_registry import _TOOL_REGISTRY, ai_tool, execute_tool

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


SECRET = "sk-live-ABC123456789"
BOT_TOKEN = "bot123456:ABCDEFGHIJKLMNOPQRSTUV"
PASSWORD = "hunter2"
HOME_PATH = "/home/" + "samue"


class TestErrorHandling(IntegrationTestCase):
	def test_sanitize_masks_secrets_and_infrastructure(self):
		db_name = frappe.conf.get("db_name") or "_f76bcd16c9507e06"
		raw = (
			f"{SECRET} {BOT_TOKEN} password={PASSWORD} api_key=secret123 "
			f"{db_name} {HOME_PATH}/mybench-v16/sites/aios-v16.localhost "
			"Authorization: Bearer abc.def"
		)

		clean = sanitize_text(raw)

		for secret in (SECRET, BOT_TOKEN, PASSWORD, "secret123", db_name, HOME_PATH):
			self.assertNotIn(secret, clean)
		self.assertIn("[REDACTED]", clean)

	def test_log_exception_calls_frappe_log_error(self):
		with patch("frappe.log_error") as log:
			log_exception("Test Error", exc=ValueError(f"{SECRET} /home/x"), context="unit")

		log.assert_called_once()
		message = log.call_args.kwargs["message"]
		self.assertNotIn(SECRET, message)
		self.assertNotIn("/home/x", message)

	def test_json_error_is_safe_and_logged(self):
		with patch("frappe.log_error") as log:
			with self.assertRaises(CustomAPIResponse) as ctx:
				json_error(
					500,
					"PDF_READ_FAILED",
					"Gagal membaca dokumen PDF.",
					exc=ValueError(f"{SECRET} /home/x"),
				)

		log.assert_called_once()
		response = ctx.exception.get_response()
		body = json.loads(response.get_data(as_text=True))

		self.assertFalse(body["success"])
		self.assertEqual(body["error"], "Gagal membaca dokumen PDF.")
		self.assertEqual(body["code"], "PDF_READ_FAILED")
		self.assertNotIn(SECRET, json.dumps(body))
		self.assertNotIn("/home/x", json.dumps(body))

	def test_execute_tool_failure_is_safe_and_logged(self):
		@ai_tool(name="_test_error_tool", description="test")
		def _boom():
			raise ValueError(f"{SECRET} /home/x")

		try:
			with patch("frappe.log_error") as log:
				result = json.loads(
					execute_tool(
						"_test_error_tool",
						"{}",
						context={"user": "Administrator", "allowed_company": "Test"},
					)
				)
		finally:
			_TOOL_REGISTRY.pop("_test_error_tool", None)

		log.assert_called_once()
		self.assertFalse(result["success"])
		# ValueError = input tak valid -> VALIDATION_FAILED agar agent bisa self-correct;
		# TOOL_FAILED hanya untuk crash tak terduga (lihat test_validation_feedback_and_smart_lookup).
		self.assertEqual(result["code"], "VALIDATION_FAILED")
		self.assertNotIn(SECRET, json.dumps(result))

	def test_dispatcher_wrapper_logs_and_returns_safe(self):
		from aios_v1.api import dispatcher

		with patch.object(
			dispatcher, "_handle_api_request", side_effect=ValueError(f"{SECRET} /home/x")
		):
			with patch("frappe.log_error") as log:
				with self.assertRaises(CustomAPIResponse) as ctx:
					dispatcher.handle_api_request()

		log.assert_called_once()
		body = json.loads(ctx.exception.get_response().get_data(as_text=True))
		self.assertFalse(body["success"])
		self.assertEqual(body["code"], "INTERNAL_ERROR")
		self.assertNotIn(SECRET, json.dumps(body))

	def test_safe_error_never_claims_success(self):
		payload = safe_error("Gagal.", "TEST_FAILED")
		self.assertFalse(payload["success"])
		self.assertEqual(payload["code"], "TEST_FAILED")

	def test_seed_failure_is_logged(self):
		from aios_v1.setup_poc.seed_erpnext_demo import _log_failures

		@_log_failures
		def _fail():
			raise RuntimeError(f"{SECRET} /home/x")

		with patch("frappe.log_error") as log:
			with self.assertRaises(RuntimeError):
				_fail()

		log.assert_called_once()
		self.assertNotIn(SECRET, log.call_args.kwargs["message"])
