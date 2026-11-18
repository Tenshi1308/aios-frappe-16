"""Branch gating and channel connector gating tests."""

from unittest.mock import MagicMock, patch

import frappe
import requests

from aios_v1.lib.connector import telegram_client
from aios_v1.lib.tool_registry import execute_tool, get_tools_schema_for_worker
from aios_v1.managers import get_manager
from aios_v1.plugin_manager.registry import get_branches, is_branch_enabled

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase


class TestBranchGating(IntegrationTestCase):
    def test_only_priority_branches_are_listed(self):
        self.assertEqual({branch["key"] for branch in get_branches()}, {"finance", "sales", "accounting"})
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

    def test_disabled_chat_stream_method_returns_branch_disabled(self):
        """Fase 1: method whitelisted `stream_chat` menolak cabang nonaktif.

        Dulu diuji lewat dispatcher kustom `/api/chat/hr/stream`; kini
        langsung memanggil `aios_v1.api.chat.stream_chat`.
        """
        from aios_v1.api import chat

        with patch.object(chat, "check_site_token_quota", return_value=True):
            with self.assertRaises(frappe.DoesNotExistError) as raised:
                chat.stream_chat(branch="hr", message="halo")

        self.assertIn("Cabang ini belum tersedia", str(raised.exception))


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
            self.assertFalse(
                telegram_client.set_my_commands("1", [{"command": "start", "description": "Mulai percakapan baru"}])
            )
            with self.assertRaises(telegram_client.ConnectorError) as raised:
                telegram_client.get_updates(0)
            self.assertEqual(raised.exception.code, "CONNECTOR_NO_TOKEN")
        post.assert_not_called()

    def test_set_my_commands_sends_chat_scoped_payload(self):
        fake_resp = MagicMock()
        fake_resp.json.return_value = {"ok": True, "result": True}
        commands = [
            {"command": "start", "description": "Mulai percakapan baru"},
            {"command": "clear", "description": "Bersihkan riwayat percakapan"},
        ]
        token = "123456:TEST_TOKEN_SECRET_VALUE_987654"
        with patch.object(
            telegram_client,
            "get_config",
            return_value={
                "bot_token": token,
                "bot_username": "test_bot",
                "is_active": True,
                "persona_tone": "Ramah & Kasual",
                "custom_instructions": "",
            },
        ), patch.object(telegram_client.requests, "post", return_value=fake_resp) as post:
            ok = telegram_client.set_my_commands(99001122, commands)

        self.assertTrue(ok)
        post.assert_called_once()
        call_args, call_kwargs = post.call_args
        self.assertEqual(call_args[0], f"{telegram_client.API_BASE}/bot{token}/setMyCommands")
        self.assertEqual(
            call_kwargs["json"],
            {
                "commands": commands,
                "scope": {"type": "chat", "chat_id": 99001122},
            },
        )

    def test_set_my_commands_failure_modes_are_logged_without_token_and_return_false(self):
        token = "123456:TEST_TOKEN_SECRET_VALUE_987654"
        commands = [{"command": "start", "description": "Mulai percakapan baru"}]
        bad_resp = MagicMock()
        bad_resp.json.return_value = {
            "ok": False,
            "description": f"Bad Request: chat not found (bot{token})",
        }
        cases = [
            requests.exceptions.Timeout(f"timeout for bot{token}"),
            requests.exceptions.RequestException(f"network error on bot{token}"),
            bad_resp,
        ]

        for outcome in cases:
            with self.subTest(outcome=type(outcome).__name__):
                post_kwargs = (
                    {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
                )
                with patch.object(
                    telegram_client,
                    "get_config",
                    return_value={
                        "bot_token": token,
                        "bot_username": "test_bot",
                        "is_active": True,
                        "persona_tone": "Ramah & Kasual",
                        "custom_instructions": "",
                    },
                ), patch.object(telegram_client.requests, "post", **post_kwargs), patch(
                    "aios_v1.lib.error_utils.frappe.log_error"
                ) as log_error_mock:
                    ok = telegram_client.set_my_commands(99001122, commands)

                self.assertFalse(ok)
                self.assertTrue(log_error_mock.called)
                for call in log_error_mock.call_args_list:
                    combined = f"{call.args} {call.kwargs}"
                    self.assertNotIn(token, combined)

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
