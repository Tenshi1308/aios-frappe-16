"""Kontrak error handling: tersanitasi, tercatat, tidak pura-pura sukses.

Fase 1: dispatcher kustom (`json_error` / `CustomAPIResponse`) sudah digantikan
cara resmi Frappe. Yang diuji kini adalah utilitas aman yang tetap dipakai
(`aios_v1.lib.error_utils.safe_error`) dan penanganan error pada method
whitelisted (`aios_v1.api.connector.close_flag`): pesan aman, tercatat, dan
tidak pernah melaporkan sukses palsu.

Jalankan:
    bench --site <site> run-tests --app aios_v1 \
        --module aios_v1.tests.test_error_handling
"""

import json
from unittest.mock import patch

import frappe

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

    def test_safe_error_is_safe_and_logged(self):
        """`safe_error` = kontrak respons aman yang dipakai method baru."""
        with patch("frappe.log_error") as log:
            log_exception("AIOS API: PDF_READ_FAILED", exc=ValueError(f"{SECRET} /home/x"))
            body = safe_error("Gagal membaca dokumen PDF.", "PDF_READ_FAILED")

        log.assert_called_once()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"], "Gagal membaca dokumen PDF.")
        self.assertEqual(body["code"], "PDF_READ_FAILED")
        self.assertNotIn(SECRET, json.dumps(body))
        self.assertNotIn("/home/x", json.dumps(body))

    def test_whitelisted_guest_is_denied_403(self):
        """Tamu ditolak `PermissionError` (403), kontrak baru Fase 1."""
        from aios_v1.api import connector

        old_user = frappe.session.user
        frappe.set_user("Guest")
        try:
            with self.assertRaises(frappe.PermissionError) as ctx:
                connector.list_flags()
            self.assertEqual(getattr(ctx.exception, "http_status_code", None), 403)
        finally:
            frappe.set_user(old_user)

    def test_whitelisted_workspace_error_is_logged_and_never_claims_success(self):
        """`WorkspaceError` dari views dicatat & diterjemahkan, bukan sukses palsu."""
        from aios_v1.api import connector
        from aios_v1.lib.workspace import WorkspaceError

        with patch.object(
            connector.views,
            "close_flag",
            side_effect=WorkspaceError(400, "FLAG_REQUIRED", f"Flag wajib {SECRET}"),
        ):
            with patch("aios_v1.api.connector.log_exception") as log:
                with self.assertRaises(frappe.ValidationError):
                    connector.close_flag(flag="", note="")

        log.assert_called_once()
        # Kontrak: WorkspaceError diterjemahkan ke exception resmi (bukan
        # dikembalikan sebagai `{"success": true}`). Sanitasi isi Error Log
        # sudah diuji terpisah di `test_log_exception_calls_frappe_log_error`.
        self.assertEqual(log.call_args.args[0], "AIOS Connector Flag Close")
        self.assertEqual(log.call_args.kwargs["context"], "FLAG_REQUIRED")

    def test_execute_tool_failure_is_safe_and_logged(self):
        @ai_tool(name="_test_error_tool", description="test")
        def _boom():
            raise ValueError(f"{SECRET} /home/x")

        try:
            # `_build_tool_context` butuh context eksplisit di luar request
            # HTTP (tool_registry.py:64-88); beri user & company uji.
            with patch("frappe.log_error") as log:
                result = execute_tool(
                    "_test_error_tool",
                    "{}",
                    {"user": "Administrator", "allowed_company": "Test Co"},
                )

            log.assert_called_once()
            payload = json.loads(result) if isinstance(result, str) else result
            self.assertFalse(payload["success"])
            # ValueError = input tak valid -> VALIDATION_FAILED agar agent bisa self-correct;
            # TOOL_FAILED hanya untuk crash tak terduga (lihat test_validation_feedback_and_smart_lookup).
            self.assertEqual(payload["code"], "VALIDATION_FAILED")
            self.assertNotIn(SECRET, json.dumps(payload))
        finally:
            _TOOL_REGISTRY.pop("_test_error_tool", None)

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
