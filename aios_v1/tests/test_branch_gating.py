"""Branch gating and channel connector gating tests."""

from unittest.mock import patch

import frappe

from aios_v1.lib.connector import telegram_client
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


class TestConnectorGating(IntegrationTestCase):
    """The connector must not open a network connection without a token."""

    def test_unconfigured_connector_opens_no_network(self):
        with patch.object(telegram_client, "get_config", return_value={
            "bot_token": "", "bot_username": "", "is_active": False,
            "persona_tone": "", "custom_instructions": "",
        }), patch.object(telegram_client.requests, "post") as post:
            self.assertFalse(telegram_client.is_configured())
            self.assertFalse(telegram_client.send_message("1", "hello"))
            self.assertFalse(telegram_client.send_chat_action("1"))
            with self.assertRaises(telegram_client.ConnectorError) as raised:
                telegram_client.get_updates(0)
            self.assertEqual(raised.exception.code, "CONNECTOR_NO_TOKEN")
        post.assert_not_called()

    def test_connector_health_is_read_only(self):
        from aios_v1.lib.connector.dispatch import health

        with patch.object(telegram_client, "get_config", return_value={
            "bot_token": "", "bot_username": "", "is_active": False,
            "persona_tone": "", "custom_instructions": "",
        }), patch.object(telegram_client.requests, "post") as post:
            result = health()
        post.assert_not_called()
        self.assertTrue(result["success"])
        self.assertFalse(result["has_token"])
        self.assertEqual(result["channel"], "telegram")
        self.assertEqual(result["branch"], "sales")

    def test_poller_skips_when_not_configured(self):
        from aios_v1.lib.connector import poller

        with patch.object(telegram_client, "is_configured", return_value=False), \
             patch.object(telegram_client, "get_updates") as get_updates:
            self.assertEqual(poller.poll_once(), 0)
        get_updates.assert_not_called()
