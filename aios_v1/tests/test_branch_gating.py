"""Branch gating and dormant Telegram behavior tests."""

from unittest.mock import patch

import frappe

from aios_v1.lib import telegram_service
from aios_v1.lib.tool_registry import execute_tool, get_tools_schema_for_worker
from aios_v1.managers import get_manager
from aios_v1.plugin_manager.registry import get_branches, is_branch_enabled

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase


class TestBranchGating(IntegrationTestCase):
    def test_only_finance_and_sales_are_listed(self):
        self.assertEqual({branch["key"] for branch in get_branches()}, {"finance", "sales"})
        self.assertFalse(is_branch_enabled("hr"))

    def test_disabled_branch_schema_and_tool_execution_are_denied(self):
        self.assertEqual(get_tools_schema_for_worker("hr", "manager"), [])
        with patch("aios_v1.lib.tool_registry.log_exception"):
            result = execute_tool("get_current_time", "{}", context={
                "user": "Administrator", "allowed_company": "_Test", "branch": "hr", "worker_key": "manager",
            })
        self.assertIn("BRANCH_DISABLED", result)
        with self.assertRaises(frappe.ValidationError):
            get_manager("hr")

    def test_disabled_chat_stream_route_returns_branch_disabled(self):
        from aios_v1.api import dispatcher

        previous_request = frappe.request
        frappe.request = type("Request", (), {
            "path": "/api/chat/hr/stream", "method": "POST", "headers": {},
        })()
        try:
            with patch.object(dispatcher, "require_session", return_value={"user": "Administrator"}), \
                 patch.object(dispatcher, "_current_request", return_value=None):
                with self.assertRaises(dispatcher.CustomAPIResponse) as raised:
                    dispatcher._handle_api_request()
            self.assertIn("BRANCH_DISABLED", raised.exception.get_response().get_data(as_text=True))
        finally:
            frappe.request = previous_request

    def test_telegram_endpoint_returns_safe_disabled_error(self):
        from aios_v1.api import dispatcher

        previous_request = frappe.request
        frappe.request = type("Request", (), {
            "path": "/api/chatbot/settings", "method": "GET", "headers": {},
        })()
        try:
            with patch.object(dispatcher, "require_session", return_value={"role": "DEVELOPER"}):
                with self.assertRaises(dispatcher.CustomAPIResponse) as raised:
                    dispatcher._handle_api_request()
            body = raised.exception.get_response().get_data(as_text=True)
            self.assertIn("TELEGRAM_DISABLED", body)
        finally:
            frappe.request = previous_request

    def test_telegram_polling_and_send_do_not_open_network(self):
        with patch.object(telegram_service.requests, "get") as get, \
             patch.object(telegram_service.requests, "post") as post, \
             patch.object(telegram_service.requests, "Session") as session:
            self.assertEqual(telegram_service.poll_telegram_updates()["code"], "TELEGRAM_DISABLED")
            self.assertEqual(telegram_service.send_telegram_message("1", "hello")["code"], "TELEGRAM_DISABLED")
            self.assertFalse(telegram_service.test_telegram_connection()["success"])
        get.assert_not_called()
        post.assert_not_called()
        session.assert_not_called()
