"""MCP client cache, schema, dispatch, and failure-boundary tests."""

import asyncio
import json
import unittest
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import MagicMock, patch

import frappe
from mcp.types import CallToolResult, Tool

from aios_v1.lib import mcp_client
from aios_v1.lib.tool_registry import execute_tool


class _FakeCache:
	def __init__(self):
		self.values = {}

	def get_value(self, key):
		return self.values.get(key)

	def set_value(self, key, value, expires_in_sec=None):
		self.values[key] = value


class _FakeTool:
	def __init__(self, name="lookup", description="_Test lookup"):
		self.name = name
		self.description = description
		self.inputSchema = {
			"type": "object",
			"properties": {"query": {"type": "string"}},
			"required": ["query"],
		}


class _FakeClient:
	tools: ClassVar[list] = [_FakeTool()]
	call_result: ClassVar[dict] = {"content": [{"type": "text", "text": "_Test result"}], "isError": False}

	def __init__(self, server, **kwargs):
		self.server = server
		self.kwargs = kwargs

	async def __aenter__(self):
		return self

	async def __aexit__(self, *args):
		return None

	async def list_tools(self, **kwargs):
		return SimpleNamespace(tools=self.tools)

	async def call_tool(self, name, arguments, **kwargs):
		self.last_call = (name, arguments)
		return SimpleNamespace(
			isError=self.call_result["isError"],
			model_dump=lambda **dump_kwargs: self.call_result,
		)


class TestMCPClient(unittest.TestCase):
	def setUp(self):
		self.cache = _FakeCache()
		self.old_site = getattr(frappe.local, "site", None)
		frappe.local.site = "_test-mcp.localhost"
		self.plugin = frappe._dict(
			{
				"plugin_key": "_Test external-mcp",
				"plugin_name": "_Test MCP",
				"plugin_type": "EXTERNAL_MCP_HTTP",
				"enabled": 1,
				"endpoint_url": "https://mcp.example.com/mcp",
				"config_json": "{}",
			}
		)
		self.error_logger = patch.object(mcp_client, "log_exception")
		self.error_logger.start()
		self.addCleanup(self.error_logger.stop)

	def tearDown(self):
		if self.old_site is None:
			if hasattr(frappe.local, "site"):
				delattr(frappe.local, "site")
		else:
			frappe.local.site = self.old_site

	def _patch_cache_and_plugin(self, plugin=None):
		return (
			patch.object(mcp_client, "_cache", return_value=self.cache),
			patch.object(mcp_client, "_get_plugin", return_value=plugin or self.plugin),
		)

	def test_endpoint_rejects_auth_private_and_non_https_production_urls(self):
		for endpoint in (
			"https://user:secret@mcp.example.com/mcp",
			"https://localhost/mcp",
			"https://10.0.0.7/mcp",
			"https://mcp.example.com:8443/mcp",
			"http://mcp.example.com/mcp",
		):
			with self.subTest(endpoint=endpoint), self.assertRaises(mcp_client.MCPClientFailure):
				mcp_client.validate_mcp_endpoint(endpoint, developer_mode=False)
		self.assertEqual(
			mcp_client.validate_mcp_endpoint("http://127.0.0.1:8765/mcp", developer_mode=True),
			"http://127.0.0.1:8765/mcp",
		)

	def test_config_rejects_auth_keys_unknown_keys_and_invalid_limits(self):
		for config in ('{"auth_token":"secret"}', '{"other":true}', '{"timeout_seconds":99}'):
			with self.subTest(config=config), self.assertRaises(mcp_client.MCPClientFailure):
				mcp_client.parse_plugin_config(config)
		self.assertEqual(
			mcp_client.parse_plugin_config("{}")["timeout_seconds"], mcp_client.DEFAULT_TIMEOUT_SECONDS
		)

	def test_aliases_are_safe_bounded_and_unique_for_long_colliding_slugs(self):
		first = mcp_client.make_tool_alias("plugin-" + "a" * 80, "tool-" + "b" * 80)
		second = mcp_client.make_tool_alias("plugin-" + "a" * 79 + "c", "tool-" + "b" * 79 + "d")
		self.assertLessEqual(len(first), 64)
		self.assertLessEqual(len(second), 64)
		self.assertRegex(first, r"^mcp__[a-z0-9_-]+__[a-z0-9_-]+__[a-f0-9]{8}$")
		self.assertNotEqual(first, second)

	def test_alias_index_drops_a_name_collision_instead_of_exposing_wrong_dispatch(self):
		first = {
			"alias": "mcp__same__tool__12345678",
			"original_name": "first",
			"description": "first",
			"input_schema": {},
		}
		second = {
			"alias": first["alias"],
			"original_name": "second",
			"description": "second",
			"input_schema": {},
		}
		with (
			patch.object(mcp_client, "_cache", return_value=self.cache),
			patch.object(mcp_client, "_log_failure") as log_failure,
		):
			mcp_client._save_discovery(self.plugin, [first, second])
			index = mcp_client._cache_get_json(mcp_client._alias_index_key())
			snapshot = mcp_client._cache_get_json(
				mcp_client._snapshot_key(
					self.plugin.plugin_key, self.plugin.endpoint_url, self.plugin.config_json
				)
			)
		self.assertEqual(index[first["alias"]]["original_name"], "first")
		self.assertEqual([item["original_name"] for item in snapshot["tools"]], ["first"])
		log_failure.assert_called_once_with("MCP_ALIAS_COLLISION", self.plugin.plugin_key)

	def test_discovery_caches_schema_and_alias_mapping_without_public_endpoint(self):
		with (
			patch.object(mcp_client, "_cache", return_value=self.cache),
			patch.object(mcp_client, "_get_plugin", return_value=self.plugin),
			patch.object(mcp_client, "_validate_endpoint_dns"),
			patch.object(mcp_client, "Client", _FakeClient),
		):
			result = mcp_client.discover_mcp_tools(self.plugin.plugin_key)
			self.assertEqual(result, {"ok": True, "tools_count": 1, "error_code": None})
			alias = mcp_client.make_tool_alias(self.plugin.plugin_key, "lookup")
			index = mcp_client._cache_get_json(mcp_client._alias_index_key())
			self.assertEqual(index[alias], {"plugin_key": self.plugin.plugin_key, "original_name": "lookup"})
			snapshot = mcp_client._cache_get_json(
				mcp_client._snapshot_key(
					self.plugin.plugin_key, self.plugin.endpoint_url, self.plugin.config_json
				)
			)
		self.assertEqual(snapshot["tools"][0]["alias"], alias)

	def test_tool_schema_reads_official_sdk_model_field(self):
		tool = Tool(
			name="lookup",
			description="_Test lookup",
			inputSchema={
				"type": "object",
				"properties": {"query": {"type": "string"}},
				"required": ["query"],
			},
		)

		result = mcp_client._tool_to_schema(self.plugin.plugin_key, tool)

		self.assertIsNotNone(result)
		self.assertEqual(result["input_schema"]["required"], ["query"])

	def test_schema_checks_enabled_scope_and_direct_call_rechecks_them(self):
		with patch.object(mcp_client, "_cache", return_value=self.cache):
			mcp_client._save_discovery(
				self.plugin, [mcp_client._tool_to_schema(self.plugin.plugin_key, _FakeTool())]
			)
		with (
			patch.object(mcp_client, "_cache", return_value=self.cache),
			patch.object(mcp_client, "_get_plugin", return_value=self.plugin),
			patch.object(mcp_client, "_get_external_plugins", return_value=[self.plugin]),
			patch("aios_v1.lib.tool_registry._plugin_enabled", return_value=True),
			patch(
				"aios_v1.lib.tool_registry._plugin_scope_allows",
				side_effect=lambda key, branch, worker: branch == "sales",
			),
		):
			self.assertEqual(mcp_client.get_mcp_tools_schema_for_worker("finance", "manager"), [])
			schema = mcp_client.get_mcp_tools_schema_for_worker("sales", "manager")
		self.assertEqual(len(schema), 1)
		alias = schema[0]["function"]["name"]
		with (
			patch.object(mcp_client, "_cache", return_value=self.cache),
			patch.object(mcp_client, "_get_plugin", return_value=self.plugin),
			patch("aios_v1.lib.tool_registry._plugin_enabled", return_value=True),
			patch("aios_v1.lib.tool_registry._plugin_scope_allows", return_value=False),
			patch.object(mcp_client, "Client", _FakeClient),
			patch.object(mcp_client, "_validate_endpoint_dns"),
		):
			denied = mcp_client.execute_mcp_tool(alias, {"query": "_Test"}, "finance", "manager")
		self.assertEqual(denied["code"], "PLUGIN_SCOPE_DENIED")

	def test_disabled_plugin_is_not_visible_or_callable(self):
		with patch.object(mcp_client, "_cache", return_value=self.cache):
			mcp_client._save_discovery(
				self.plugin, [mcp_client._tool_to_schema(self.plugin.plugin_key, _FakeTool())]
			)
		with (
			patch.object(mcp_client, "_cache", return_value=self.cache),
			patch.object(mcp_client, "_get_plugin", return_value=self.plugin),
			patch.object(mcp_client, "_get_external_plugins", return_value=[self.plugin]),
			patch("aios_v1.lib.tool_registry._plugin_enabled", return_value=False),
			patch("aios_v1.lib.tool_registry._plugin_scope_allows", return_value=True),
		):
			self.assertEqual(mcp_client.get_mcp_tools_schema_for_worker("finance", "manager"), [])
			alias = mcp_client.make_tool_alias(self.plugin.plugin_key, "lookup")
			result = mcp_client.execute_mcp_tool(alias, {}, "finance", "manager")
		self.assertEqual(result["code"], "PLUGIN_DISABLED")

	def test_stale_alias_and_sse_transport_fail_closed(self):
		with patch.object(mcp_client, "_cache", return_value=self.cache):
			stale = mcp_client.execute_mcp_tool("mcp__stale__tool__12345678", {}, "finance", "manager")
			self.assertEqual(stale["code"], "MCP_DISCOVERY_REQUIRED")
			sse = self.plugin.copy()
			sse.plugin_type = "EXTERNAL_MCP_SSE"
			with patch.object(mcp_client, "_get_plugin", return_value=sse):
				result = mcp_client.discover_mcp_tools(sse.plugin_key)
		self.assertEqual(result["error_code"], "MCP_TRANSPORT_UNSUPPORTED")
		with patch.object(mcp_client, "_cache", return_value=self.cache):
			mcp_client._save_discovery(
				self.plugin, [mcp_client._tool_to_schema(self.plugin.plugin_key, _FakeTool())]
			)
		self.plugin.plugin_type = "EXTERNAL_MCP_SSE"
		with (
			patch.object(mcp_client, "_cache", return_value=self.cache),
			patch.object(mcp_client, "_get_plugin", return_value=self.plugin),
		):
			unsupported = mcp_client.execute_mcp_tool(
				mcp_client.make_tool_alias(self.plugin.plugin_key, "lookup"), {}, "finance", "manager"
			)
		self.assertEqual(unsupported["code"], "MCP_TRANSPORT_UNSUPPORTED")

	def test_schema_without_snapshot_never_calls_mcp_client(self):
		with (
			patch.object(mcp_client, "_cache", return_value=self.cache),
			patch.object(mcp_client, "_get_external_plugins", return_value=[self.plugin]),
			patch("aios_v1.lib.tool_registry._plugin_enabled", return_value=True),
			patch("aios_v1.lib.tool_registry._plugin_scope_allows", return_value=True),
			patch.object(mcp_client, "Client") as client,
		):
			self.assertEqual(mcp_client.get_mcp_tools_schema_for_worker("finance", "manager"), [])
		client.assert_not_called()

	def test_mcp_call_uses_cached_original_name_and_returns_json_safe_result(self):
		with patch.object(mcp_client, "_cache", return_value=self.cache):
			mcp_client._save_discovery(
				self.plugin, [mcp_client._tool_to_schema(self.plugin.plugin_key, _FakeTool())]
			)
		alias = mcp_client.make_tool_alias(self.plugin.plugin_key, "lookup")
		with (
			patch.object(mcp_client, "_cache", return_value=self.cache),
			patch.object(mcp_client, "_get_plugin", return_value=self.plugin),
			patch("aios_v1.lib.tool_registry._plugin_enabled", return_value=True),
			patch("aios_v1.lib.tool_registry._plugin_scope_allows", return_value=True),
			patch.object(mcp_client, "_validate_endpoint_dns"),
			patch.object(mcp_client, "Client", _FakeClient),
		):
			result = mcp_client.execute_mcp_tool(alias, {"query": "_Test"}, "finance", "manager")
		self.assertFalse(result["isError"])
		self.assertEqual(result["content"][0]["text"], "_Test result")

	def test_official_sdk_tool_error_is_not_reported_as_success(self):
		with patch.object(mcp_client, "_cache", return_value=self.cache):
			mcp_client._save_discovery(
				self.plugin, [mcp_client._tool_to_schema(self.plugin.plugin_key, _FakeTool())]
			)
		alias = mcp_client.make_tool_alias(self.plugin.plugin_key, "lookup")
		with (
			patch.object(mcp_client, "_cache", return_value=self.cache),
			patch.object(mcp_client, "_get_plugin", return_value=self.plugin),
			patch("aios_v1.lib.tool_registry._plugin_enabled", return_value=True),
			patch("aios_v1.lib.tool_registry._plugin_scope_allows", return_value=True),
			patch.object(mcp_client, "_validate_endpoint_dns"),
			patch.object(
				mcp_client, "_run_async_in_thread", return_value=CallToolResult(content=[], isError=True)
			),
		):
			result = mcp_client.execute_mcp_tool(alias, {"query": "_Test"}, "finance", "manager")
		self.assertEqual(result["code"], "MCP_TOOL_FAILED")

	def test_tool_registry_dispatches_mcp_alias_with_worker_context(self):
		alias = mcp_client.make_tool_alias(self.plugin.plugin_key, "lookup")
		context = {
			"user": "_test.mcp@example.com",
			"allowed_company": "_Test Company",
			"branch": "finance",
			"worker_key": "manager",
		}
		with patch.object(mcp_client, "execute_mcp_tool", return_value={"content": "nonce _Test"}) as call:
			result = json.loads(execute_tool(alias, '{"query":"_Test"}', context=context))
		self.assertEqual(result, {"content": "nonce _Test"})
		call.assert_called_once_with(alias, {"query": "_Test"}, "finance", "manager")

	def test_auth_timeout_and_connection_errors_map_to_safe_codes(self):
		for status in (401, 403):
			failure = mcp_client._exception_failure(
				SimpleNamespace(response=SimpleNamespace(status_code=status))
			)
			self.assertEqual(failure.code, "MCP_AUTH_REQUIRED")
		self.assertEqual(mcp_client._exception_failure(TimeoutError()).code, "MCP_SERVER_UNAVAILABLE")
		self.assertEqual(mcp_client._exception_failure(ConnectionError()).code, "MCP_SERVER_UNAVAILABLE")
		self.assertEqual(mcp_client._exception_failure(ValueError("_Test")).code, "MCP_TOOL_FAILED")

	def test_discovery_server_failure_is_reported_without_raw_exception(self):
		class FailedClient:
			def __init__(self, *args, **kwargs):
				pass

			async def __aenter__(self):
				raise ConnectionError("_Test endpoint details")

			async def __aexit__(self, *args):
				return None

		with (
			patch.object(mcp_client, "_cache", return_value=self.cache),
			patch.object(mcp_client, "_get_plugin", return_value=self.plugin),
			patch.object(mcp_client, "_validate_endpoint_dns"),
			patch.object(mcp_client, "Client", FailedClient),
			patch.object(mcp_client, "log_exception") as logged,
		):
			result = mcp_client.discover_mcp_tools(self.plugin.plugin_key)
		self.assertEqual(result["error_code"], "MCP_SERVER_UNAVAILABLE")
		self.assertNotIn("endpoint", json.dumps(result))
		logged.assert_called()
		self.assertNotIn("_Test endpoint details", str(logged.call_args_list))

	def test_async_bridge_works_inside_running_loop_and_enforces_timeout(self):
		async def value():
			return "_Test complete"

		async def invoke_from_loop():
			return mcp_client._run_async_in_thread(value, 1)

		self.assertEqual(asyncio.run(invoke_from_loop()), "_Test complete")

		async def slow():
			await asyncio.sleep(0.2)

		with self.assertRaises(TimeoutError):
			mcp_client._run_async_in_thread(slow, 0.01)

	def test_async_bridge_preserves_original_error_when_thread_logging_is_unavailable(self):
		async def fail():
			raise ConnectionError("_Test connection failure")

		with (
			patch.object(mcp_client, "log_exception", side_effect=RuntimeError("object is not bound")),
			self.assertRaises(ConnectionError),
		):
			mcp_client._run_async_in_thread(fail, 1)
