"""SSRF and output-boundary tests for web market research tools."""

import ipaddress
import json
import socket
import unittest
from unittest.mock import MagicMock, patch

import frappe
from urllib3.exceptions import ConnectTimeoutError, ReadTimeoutError

from aios_v1.lib import web_market_research as web
from aios_v1.lib.tool_registry import _TOOL_REGISTRY, execute_tool, get_tools_schema_for_worker

try:
	from frappe.tests import IntegrationTestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _dns_answer(address):
	return (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))


def _response(status=200, headers=None, chunks=(b"body",)):
	response = MagicMock()
	response.status = status
	response.headers = headers or {"Content-Type": "text/plain; charset=utf-8"}
	response.stream.return_value = iter(chunks)
	return response


class TestWebFetch(unittest.TestCase):
	def setUp(self):
		self.error_logger = patch.object(web, "log_exception")
		self.error_logger.start()
		self.addCleanup(self.error_logger.stop)

	def _run_fetch(self, url="https://example.com/path?secret=query#fragment", response=None):
		response = response or _response()
		pool = MagicMock()
		pool.request.return_value = response
		with (
			patch.object(web.socket, "getaddrinfo", return_value=[_dns_answer("93.184.216.34")]) as dns,
			patch.object(web, "HTTPSConnectionPool", return_value=pool) as pool_type,
		):
			result = web.web_fetch(url)
		return result, dns, pool_type, pool, response

	def test_dns_rebinding_cannot_change_pinned_connection(self):
		response = _response(chunks=(b"pinned",))
		pool = MagicMock()
		pool.request.return_value = response
		with (
			patch.object(
				web.socket,
				"getaddrinfo",
				side_effect=[[_dns_answer("93.184.216.34")], [_dns_answer("10.0.0.8")]],
			) as dns,
			patch.object(web, "HTTPSConnectionPool", return_value=pool) as pool_type,
		):
			result = web.web_fetch("https://example.com/")
		self.assertEqual(result["text"], "pinned")
		self.assertEqual(dns.call_count, 1)
		self.assertEqual(pool_type.call_args.kwargs["host"], "93.184.216.34")
		self.assertEqual(pool_type.call_args.kwargs["server_hostname"], "example.com")
		self.assertEqual(pool_type.call_args.kwargs["assert_hostname"], "example.com")
		pool.request.assert_called_once()

	def test_private_redirect_is_rejected_before_second_request(self):
		response = _response(status=302, headers={"Location": "http://127.0.0.1/private"})
		result, dns, pool_type, pool, _ = self._run_fetch(response=response)
		self.assertEqual(result["code"], "PRIVATE_ADDRESS_DENIED")
		self.assertEqual(dns.call_count, 1)
		pool.request.assert_called_once()
		pool_type.assert_called_once()

	def test_rejects_loopback_private_metadata_and_non_global_ip_literals(self):
		for url in (
			"http://127.0.0.1/",
			"http://10.1.2.3/",
			"http://169.254.169.254/latest/meta-data/",
			"http://[::1]/",
		):
			with (
				self.subTest(url=url),
				patch.object(web, "HTTPConnectionPool") as http_pool,
				patch.object(web, "HTTPSConnectionPool") as https_pool,
			):
				result = web.web_fetch(url)
				self.assertIn(result["code"], {"PRIVATE_ADDRESS_DENIED"})
				http_pool.assert_not_called()
				https_pool.assert_not_called()

	def test_rejects_scheme_userinfo_and_port(self):
		cases = (
			("file:///etc/passwd", "URL_SCHEME_DENIED"),
			("https://user:secret@example.com/", "URL_USERINFO_DENIED"),
			("https://example.com:8443/", "URL_PORT_DENIED"),
		)
		for url, code in cases:
			with self.subTest(url=url):
				self.assertEqual(web.web_fetch(url)["code"], code)

	def test_tls_uses_certificate_validation_and_ca_bundle(self):
		_, _, pool_type, _, _ = self._run_fetch()
		kwargs = pool_type.call_args.kwargs
		self.assertEqual(kwargs["cert_reqs"], web.ssl.CERT_REQUIRED)
		self.assertTrue(kwargs["ca_certs"])
		self.assertFalse(kwargs["retries"])
		self.assertEqual(kwargs["timeout"].connect_timeout, web.CONNECT_TIMEOUT_SECONDS)
		self.assertEqual(kwargs["timeout"].read_timeout, web.READ_TIMEOUT_SECONDS)

	def test_query_fragment_are_not_exposed_in_result(self):
		result, _, _, pool, _ = self._run_fetch()
		self.assertEqual(result["url"], "https://example.com/path")
		self.assertNotIn("secret", json.dumps(result))
		self.assertEqual(pool.request.call_args.args[1], "/path?secret=query")

	def test_redirect_loop_and_redirect_limit_are_rejected(self):
		loop = _response(status=302, headers={"Location": "https://example.com/"})
		pool = MagicMock()
		pool.request.return_value = loop
		with (
			patch.object(web.socket, "getaddrinfo", return_value=[_dns_answer("93.184.216.34")]),
			patch.object(web, "HTTPSConnectionPool", return_value=pool),
		):
			self.assertEqual(web.web_fetch("https://example.com/")["code"], "REDIRECT_DENIED")
			self.assertEqual(pool.request.call_count, 1)

		responses = [
			_response(status=302, headers={"Location": f"https://example.com/{index + 1}"})
			for index in range(4)
		]
		pool = MagicMock()
		pool.request.side_effect = responses
		with (
			patch.object(web.socket, "getaddrinfo", return_value=[_dns_answer("93.184.216.34")]),
			patch.object(web, "HTTPSConnectionPool", return_value=pool),
		):
			self.assertEqual(web.web_fetch("https://example.com/0")["code"], "REDIRECT_LIMIT")
			self.assertEqual(pool.request.call_count, web.MAX_REDIRECTS + 1)

	def test_timeout_and_body_size_have_distinct_safe_errors(self):
		for timeout_error in (
			ReadTimeoutError(None, "/", "read timed out"),
			ConnectTimeoutError(None, "/", "connect timed out"),
		):
			pool = MagicMock()
			pool.request.side_effect = timeout_error
			with (
				self.subTest(error=type(timeout_error).__name__),
				patch.object(web.socket, "getaddrinfo", return_value=[_dns_answer("93.184.216.34")]),
				patch.object(web, "HTTPSConnectionPool", return_value=pool),
			):
				self.assertEqual(web.web_fetch("https://example.com/")["code"], "FETCH_TIMEOUT")

		response = _response(chunks=(b"12345",))
		pool.request.side_effect = None
		pool.request.return_value = response
		with (
			patch.object(web.socket, "getaddrinfo", return_value=[_dns_answer("93.184.216.34")]),
			patch.object(web, "HTTPSConnectionPool", return_value=pool),
			patch.object(web, "MAX_BODY_BYTES", 4),
		):
			self.assertEqual(web.web_fetch("https://example.com/")["code"], "RESPONSE_TOO_LARGE")

	def test_unsupported_content_type_is_rejected(self):
		result, _, _, _, _ = self._run_fetch(response=_response(headers={"Content-Type": "application/pdf"}))
		self.assertEqual(result["code"], "CONTENT_TYPE_UNSUPPORTED")

	def test_html_extraction_ignores_script_style_and_bounds_text(self):
		response = _response(
			headers={"Content-Type": "text/html; charset=utf-8"},
			chunks=(b"<title>  Page  Title </title><script>SECRET</script><style>CSS</style><p>Hello</p>",),
		)
		result, _, _, _, _ = self._run_fetch(response=response)
		self.assertEqual(result["title"], "Page Title")
		self.assertEqual(result["text"], "Page Title Hello")
		self.assertNotIn("SECRET", result["text"])

		response = _response(headers={"Content-Type": "text/plain"}, chunks=(b"x" * 20_001,))
		with (
			patch.object(web.socket, "getaddrinfo", return_value=[_dns_answer("93.184.216.34")]),
			patch.object(
				web, "HTTPSConnectionPool", return_value=MagicMock(request=MagicMock(return_value=response))
			),
			patch.object(web, "MAX_TEXT_CHARS", 100),
		):
			result = web.web_fetch("https://example.com/")
		self.assertEqual(len(result["text"]), 100)
		self.assertTrue(result["truncated"])

	def test_web_search_fails_explicitly_without_provider(self):
		result = web.web_search("_Test query", limit=2)
		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "SEARCH_PROVIDER_NOT_CONFIGURED")


class TestWebMarketResearchPlugin(IntegrationTestCase):
	USER = "_test.web.market@example.com"
	PLUGIN_KEY = "web-market-research"

	def setUp(self):
		super().setUp()
		self.original_commit = frappe.db.commit
		frappe.db.commit = lambda *args, **kwargs: None
		if not frappe.db.exists("User", self.USER):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": self.USER,
					"first_name": "_Test Web Market",
					"enabled": 1,
					"send_welcome_email": 0,
					"user_type": "Website User",
					"roles": [{"role": "AIOS Client"}],
				}
			).insert(ignore_permissions=True)
		frappe.set_user(self.USER)

	def tearDown(self):
		frappe.db.commit = self.original_commit
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_plugin_disabled_and_scope_are_enforced_for_web_tools(self):
		from unittest.mock import Mock, patch

		from aios_v1.setup import ensure_builtin_plugins

		ensure_builtin_plugins()
		plugin_name = frappe.db.get_value("AIOS Plugin", {"plugin_key": self.PLUGIN_KEY}, "name")
		plugin = frappe.get_doc("AIOS Plugin", plugin_name)
		context = {
			"user": self.USER,
			"allowed_company": "_Test Company",
			"branch": "finance",
			"worker_key": "manager",
		}
		for tool_name in ("web_fetch", "web_search"):
			with (
				self.subTest(tool=tool_name),
				patch.dict(_TOOL_REGISTRY, {tool_name: {**_TOOL_REGISTRY[tool_name], "func": Mock()}}),
			):
				probe = _TOOL_REGISTRY[tool_name]["func"]
				plugin.enabled = 0
				plugin.save(ignore_permissions=True)
				self.assertNotIn(
					tool_name,
					{schema["function"]["name"] for schema in get_tools_schema_for_worker("finance")},
				)
				self.assertEqual(
					json.loads(execute_tool(tool_name, "{}", context=context))["code"],
					"PLUGIN_DISABLED",
				)
				plugin.enabled = 1
				plugin.set("scopes", [{"scope_type": "branch", "scope_key": "sales", "enabled": 1}])
				plugin.save(ignore_permissions=True)
				self.assertNotIn(
					tool_name,
					{schema["function"]["name"] for schema in get_tools_schema_for_worker("finance")},
				)
				self.assertEqual(
					json.loads(execute_tool(tool_name, "{}", context=context))["code"],
					"PLUGIN_SCOPE_DENIED",
				)
				probe.assert_not_called()
