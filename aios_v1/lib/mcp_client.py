"""External MCP Streamable HTTP client and cached tool catalog."""

import asyncio
import hashlib
import ipaddress
import json
import re
import socket
import threading
from urllib.parse import urlsplit, urlunsplit

import frappe
from mcp import Client

from aios_v1.lib.error_utils import log_exception, safe_error

DISCOVERY_TTL_SECONDS = 300
DEFAULT_TIMEOUT_SECONDS = 10
MAX_TIMEOUT_SECONDS = 30
DEFAULT_MAX_TOOLS = 20
MAX_TOOLS = 100
DEFAULT_MAX_RESULT_CHARS = 10_000
MAX_RESULT_CHARS = 20_000
MAX_TOOL_NAME_LENGTH = 64
MCP_TOOL_PREFIX = "mcp__"
_SLUG_PATTERN = re.compile(r"[^a-z0-9_-]+")
_SECRET_CONFIG_PATTERN = re.compile(r"(?i)(token|secret|password|credential|auth|api[_-]?key)")


class MCPClientFailure(Exception):
	def __init__(self, code, message):
		super().__init__(message)
		self.code = code
		self.message = message


def _log_failure(code, plugin_key=None):
	context = code if not plugin_key else f"{code}: {plugin_key}"
	log_exception("AIOS MCP Client", context=context)


def _cache():
	return frappe.cache()


def _site_key():
	return str(getattr(frappe.local, "site", None) or "unknown-site")


def _fingerprint(plugin_key, endpoint_url, config_json):
	material = "\0".join((str(endpoint_url or ""), str(config_json or "{}")))
	digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
	return hashlib.sha256(f"{_site_key()}\0{plugin_key}\0{digest}".encode()).hexdigest()


def _snapshot_key(plugin_key, endpoint_url, config_json):
	return f"aios:mcp:snapshot:{_fingerprint(plugin_key, endpoint_url, config_json)}"


def _alias_index_key():
	return f"aios:mcp:aliases:{hashlib.sha256(_site_key().encode()).hexdigest()}"


def _cache_get_json(key):
	value = _cache().get_value(key)
	if value is None:
		return None
	if isinstance(value, str):
		try:
			return json.loads(value)
		except json.JSONDecodeError:
			log_exception("AIOS MCP Cache", context="CACHE_INVALID")
			return None
	return value if isinstance(value, dict) else None


def _cache_set_json(key, value):
	_cache().set_value(key, json.dumps(value, separators=(",", ":")), expires_in_sec=DISCOVERY_TTL_SECONDS)


def _get_plugin(plugin_key):
	rows = frappe.get_all(
		"AIOS Plugin",
		filters={"plugin_key": plugin_key},
		fields=["name", "plugin_key", "plugin_name", "plugin_type", "enabled", "endpoint_url", "config_json"],
		limit_page_length=1,
	)
	return rows[0] if rows else None


def _get_external_plugins():
	return frappe.get_all(
		"AIOS Plugin",
		filters={"plugin_type": ["in", ["EXTERNAL_MCP_HTTP", "EXTERNAL_MCP_SSE"]]},
		fields=["plugin_key", "plugin_name", "plugin_type", "enabled", "endpoint_url", "config_json"],
		limit_page_length=500,
	)


def parse_plugin_config(config_json):
	if not config_json:
		config = {}
	else:
		try:
			config = json.loads(config_json) if isinstance(config_json, str) else config_json
		except (json.JSONDecodeError, TypeError) as exc:
			raise MCPClientFailure("MCP_CONFIG_INVALID", "Konfigurasi MCP tidak valid.") from exc
	if not isinstance(config, dict):
		raise MCPClientFailure("MCP_CONFIG_INVALID", "Konfigurasi MCP harus berupa object JSON.")
	allowed = {"timeout_seconds", "max_tools", "max_result_chars"}
	if any(
		not isinstance(key, str) or key not in allowed or _SECRET_CONFIG_PATTERN.search(key) for key in config
	):
		raise MCPClientFailure("MCP_CONFIG_INVALID", "Konfigurasi MCP memuat opsi yang tidak didukung.")
	values = {
		"timeout_seconds": config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
		"max_tools": config.get("max_tools", DEFAULT_MAX_TOOLS),
		"max_result_chars": config.get("max_result_chars", DEFAULT_MAX_RESULT_CHARS),
	}
	if isinstance(values["timeout_seconds"], bool) or not isinstance(values["timeout_seconds"], (int, float)):
		raise MCPClientFailure("MCP_CONFIG_INVALID", "timeout_seconds harus berupa angka.")
	if not 1 <= values["timeout_seconds"] <= MAX_TIMEOUT_SECONDS:
		raise MCPClientFailure("MCP_CONFIG_INVALID", "timeout_seconds di luar batas.")
	for key, lower, upper in (("max_tools", 1, MAX_TOOLS), ("max_result_chars", 100, MAX_RESULT_CHARS)):
		value = values[key]
		if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
			raise MCPClientFailure("MCP_CONFIG_INVALID", f"{key} di luar batas.")
	return values


def validate_mcp_endpoint(endpoint_url, developer_mode=None):
	if not isinstance(endpoint_url, str) or not endpoint_url.strip():
		raise MCPClientFailure("MCP_ENDPOINT_INVALID", "Endpoint MCP wajib diisi.")
	try:
		parts = urlsplit(endpoint_url.strip())
		port = parts.port
	except ValueError as exc:
		raise MCPClientFailure("MCP_ENDPOINT_INVALID", "Endpoint MCP tidak valid.") from exc
	if parts.username is not None or parts.password is not None or "@" in parts.netloc:
		raise MCPClientFailure("MCP_ENDPOINT_INVALID", "Endpoint MCP tidak boleh memuat userinfo.")
	if parts.query or parts.fragment:
		raise MCPClientFailure("MCP_ENDPOINT_INVALID", "Endpoint MCP tidak boleh memuat query atau fragment.")
	if not parts.hostname:
		raise MCPClientFailure("MCP_ENDPOINT_INVALID", "Endpoint MCP tidak memiliki host.")
	host = parts.hostname.rstrip(".").lower()
	dev = developer_mode
	if dev is None:
		conf = getattr(frappe, "conf", None) or {}
		dev = str(conf.get("developer_mode", "")).lower() in {"1", "true", "yes"}
	if parts.scheme.lower() == "http" and dev and host == "127.0.0.1" and port is not None:
		return urlunsplit(("http", f"127.0.0.1:{port}", parts.path or "/", "", ""))
	if parts.scheme.lower() != "https" or port not in (None, 443):
		raise MCPClientFailure("MCP_ENDPOINT_INVALID", "Endpoint MCP production harus HTTPS port 443.")
	if host == "localhost" or host.endswith(".localhost"):
		raise MCPClientFailure("MCP_ENDPOINT_INVALID", "Hostname lokal tidak diizinkan.")
	try:
		address = ipaddress.ip_address(host)
	except ValueError:
		try:
			ascii_host = host.encode("idna").decode("ascii")
		except UnicodeError as exc:
			raise MCPClientFailure("MCP_ENDPOINT_INVALID", "Hostname MCP tidak valid.") from exc
		if not ascii_host or "." not in ascii_host:
			raise MCPClientFailure("MCP_ENDPOINT_INVALID", "Hostname MCP tidak valid.")
		host = ascii_host
	else:
		if not address.is_global:
			raise MCPClientFailure("MCP_ENDPOINT_INVALID", "Alamat IP MCP harus publik.")
	formatted_host = f"[{host}]" if ":" in host else host
	return urlunsplit(("https", f"{formatted_host}:443", parts.path or "/", "", ""))


def validate_plugin_record(plugin):
	plugin_type = plugin.get("plugin_type")
	if plugin_type == "EXTERNAL_MCP_SSE":
		raise MCPClientFailure("MCP_TRANSPORT_UNSUPPORTED", "Transport MCP SSE belum didukung.")
	if plugin_type != "EXTERNAL_MCP_HTTP":
		return None
	validate_mcp_endpoint(plugin.get("endpoint_url"))
	parse_plugin_config(plugin.get("config_json"))
	return True


def _slug(value, max_length):
	slug = _SLUG_PATTERN.sub("_", str(value).lower()).strip("_-") or "tool"
	return slug[:max_length].rstrip("_-") or "tool"


def make_tool_alias(plugin_key, original_name):
	plugin_slug = _slug(plugin_key, 20)
	tool_slug = _slug(original_name, 24)
	digest = hashlib.sha256(f"{plugin_key}\0{original_name}".encode()).hexdigest()[:8]
	alias = f"{MCP_TOOL_PREFIX}{plugin_slug}__{tool_slug}__{digest}"
	if len(alias) > MAX_TOOL_NAME_LENGTH:
		raise MCPClientFailure("MCP_TOOL_NAME_INVALID", "Nama tool MCP tidak dapat dibuat dengan aman.")
	return alias


def _tool_to_schema(plugin_key, tool):
	name = getattr(tool, "name", None)
	input_schema = getattr(tool, "input_schema", None)
	if input_schema is None:
		input_schema = getattr(tool, "inputSchema", None)
	if not isinstance(name, str) or not name or not isinstance(input_schema, dict):
		return None
	if input_schema.get("type", "object") != "object" or not isinstance(
		input_schema.get("properties", {}), dict
	):
		return None
	schema = dict(input_schema)
	schema.pop("$schema", None)
	try:
		json.dumps(schema, allow_nan=False)
	except TypeError, ValueError:
		log_exception("AIOS MCP Schema", context="MCP_SCHEMA_INVALID")
		return None
	return {
		"alias": make_tool_alias(plugin_key, name),
		"original_name": name,
		"description": str(getattr(tool, "description", None) or "Tool MCP eksternal.")[:1000],
		"input_schema": schema,
	}


def _save_discovery(plugin, tool_schemas):
	key = _snapshot_key(plugin.plugin_key, plugin.endpoint_url, plugin.config_json)
	index_key = _alias_index_key()
	index = _cache_get_json(index_key) or {}
	index = {alias: value for alias, value in index.items() if value.get("plugin_key") != plugin.plugin_key}
	accepted = []
	for item in tool_schemas:
		alias = item["alias"]
		if alias in index:
			_log_failure("MCP_ALIAS_COLLISION", plugin.plugin_key)
			continue
		index[alias] = {"plugin_key": plugin.plugin_key, "original_name": item["original_name"]}
		accepted.append(item)
	snapshot = {"plugin_key": plugin.plugin_key, "tools": accepted}
	_cache_set_json(key, snapshot)
	_cache_set_json(index_key, index)


async def _async_discover(endpoint_url, timeout_seconds):
	async with Client(endpoint_url, read_timeout_seconds=timeout_seconds, cache=None) as client:
		return await client.list_tools(cache_mode="refresh")


async def _async_call(endpoint_url, timeout_seconds, original_name, arguments):
	async with Client(endpoint_url, read_timeout_seconds=timeout_seconds, cache=None) as client:
		return await client.call_tool(original_name, arguments, read_timeout_seconds=timeout_seconds)


def _validate_endpoint_dns(endpoint_url):
	parts = urlsplit(endpoint_url)
	host = parts.hostname
	conf = getattr(frappe, "conf", None) or {}
	literal = ipaddress.ip_address(host) if ":" in host or re.fullmatch(r"[0-9.]+", host) else None
	if literal is not None:
		addresses = [literal]
	else:
		try:
			answers = socket.getaddrinfo(host, parts.port or 443, type=socket.SOCK_STREAM)
		except (OSError, socket.gaierror) as exc:
			raise MCPClientFailure("MCP_SERVER_UNAVAILABLE", "Host MCP tidak dapat diresolusi.") from exc
		addresses = [ipaddress.ip_address(answer[4][0]) for answer in answers]
	if not addresses or any(not address.is_global for address in addresses):
		if (
			parts.scheme == "http"
			and host == "127.0.0.1"
			and str(conf.get("developer_mode", "")).lower() in {"1", "true", "yes"}
		):
			return
		raise MCPClientFailure("MCP_ENDPOINT_INVALID", "Endpoint MCP harus mengarah ke alamat publik.")


def _run_async_in_thread(coroutine_factory, timeout_seconds):
	result = {}

	def runner():
		try:
			result["value"] = asyncio.run(asyncio.wait_for(coroutine_factory(), timeout=timeout_seconds))
		except BaseException as exc:
			# The caller re-raises and logs this on the bound Frappe request thread.
			result["error"] = exc

	thread = threading.Thread(target=runner, name="aios-mcp-client", daemon=True)
	thread.start()
	thread.join(timeout_seconds + 1)
	if thread.is_alive():
		raise TimeoutError("MCP operation exceeded its time budget")
	if "error" in result:
		raise result["error"]
	return result.get("value")


def _status_code(exc):
	for candidate in (exc, getattr(exc, "response", None), getattr(exc, "__cause__", None)):
		status = getattr(candidate, "status_code", None)
		if status is not None:
			return status
	return None


def _exception_failure(exc):
	if _status_code(exc) in {401, 403}:
		return MCPClientFailure("MCP_AUTH_REQUIRED", "Server MCP memerlukan autentikasi yang belum didukung.")
	if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or "timeout" in type(exc).__name__.lower():
		return MCPClientFailure("MCP_SERVER_UNAVAILABLE", "Server MCP tidak merespons dalam batas waktu.")
	if any(
		token in type(exc).__name__.lower() for token in ("connecterror", "connectionerror", "networkerror")
	):
		return MCPClientFailure("MCP_SERVER_UNAVAILABLE", "Server MCP tidak dapat dijangkau.")
	return MCPClientFailure("MCP_TOOL_FAILED", "Operasi pada server MCP gagal.")


def discover_mcp_tools(plugin_key):
	"""Explicit bounded discovery; intentionally not exposed as a public endpoint."""
	plugin = _get_plugin(plugin_key)
	if not plugin:
		_log_failure("MCP_PLUGIN_NOT_FOUND", plugin_key)
		return {"ok": False, "tools_count": 0, "error_code": "MCP_PLUGIN_NOT_FOUND"}
	try:
		if not plugin.enabled:
			raise MCPClientFailure("PLUGIN_DISABLED", "Plugin MCP tidak aktif.")
		if plugin.plugin_type == "EXTERNAL_MCP_SSE":
			raise MCPClientFailure("MCP_TRANSPORT_UNSUPPORTED", "Transport MCP SSE belum didukung.")
		if plugin.plugin_type != "EXTERNAL_MCP_HTTP":
			raise MCPClientFailure("MCP_TRANSPORT_UNSUPPORTED", "Plugin bukan client MCP HTTP.")
		endpoint = validate_mcp_endpoint(plugin.endpoint_url)
		_validate_endpoint_dns(endpoint)
		config = parse_plugin_config(plugin.config_json)
		result = _run_async_in_thread(
			lambda: _async_discover(endpoint, config["timeout_seconds"]), config["timeout_seconds"]
		)
		tools = []
		for tool in result.tools:
			if len(tools) >= config["max_tools"]:
				break
			entry = _tool_to_schema(plugin_key, tool)
			if entry is not None:
				tools.append(entry)
		_save_discovery(plugin, tools)
		return {"ok": True, "tools_count": len(tools), "error_code": None}
	except MCPClientFailure as exc:
		log_exception("AIOS MCP Discovery", context=f"{exc.code}: {plugin_key}")
		return {"ok": False, "tools_count": 0, "error_code": exc.code}
	except Exception as exc:
		failure = _exception_failure(exc)
		log_exception("AIOS MCP Discovery", context=f"{failure.code}: {plugin_key}")
		return {"ok": False, "tools_count": 0, "error_code": failure.code}


def _worker_is_valid(branch, worker_key):
	from aios_v1.plugin_manager.registry import get_branch, get_worker

	if not get_branch(branch):
		return False
	manager_keys = {"manager", "ai_manager", f"{branch}_manager"}
	return worker_key in manager_keys or bool(get_worker(branch, worker_key))


def get_mcp_tools_schema_for_worker(branch, worker_key):
	if not _worker_is_valid(branch, worker_key):
		return []
	from aios_v1.lib.tool_registry import _plugin_enabled, _plugin_scope_allows

	schemas = []
	for plugin in _get_external_plugins():
		plugin_key = plugin.get("plugin_key")
		if not plugin.get("enabled") or plugin.get("plugin_type") != "EXTERNAL_MCP_HTTP":
			continue
		if not _plugin_enabled(plugin_key) or not _plugin_scope_allows(plugin_key, branch, worker_key):
			continue
		snapshot = _cache_get_json(
			_snapshot_key(plugin_key, plugin.get("endpoint_url"), plugin.get("config_json"))
		)
		if not snapshot:
			continue
		for item in snapshot.get("tools", []):
			if len(item.get("alias", "")) > MAX_TOOL_NAME_LENGTH:
				continue
			schemas.append(
				{
					"type": "function",
					"function": {
						"name": item["alias"],
						"description": item["description"],
						"parameters": item["input_schema"],
					},
				}
			)
	return schemas


def _find_cached_tool(alias):
	index = _cache_get_json(_alias_index_key()) or {}
	entry = index.get(alias)
	if not isinstance(entry, dict):
		return None
	plugin = _get_plugin(entry.get("plugin_key"))
	if not plugin:
		return None
	key = _snapshot_key(plugin.get("plugin_key"), plugin.get("endpoint_url"), plugin.get("config_json"))
	snapshot = _cache_get_json(key)
	if not snapshot:
		return None
	for item in snapshot.get("tools", []):
		if item.get("alias") == alias and item.get("original_name") == entry.get("original_name"):
			return plugin, item
	return None


def execute_mcp_tool(alias, arguments, branch, worker_key):
	from aios_v1.lib.tool_registry import _plugin_enabled, _plugin_scope_allows

	try:
		entry = _find_cached_tool(alias)
		if not entry:
			raise MCPClientFailure(
				"MCP_DISCOVERY_REQUIRED", "Tool MCP belum ditemukan atau snapshot sudah kedaluwarsa."
			)
		plugin, tool = entry
		plugin_key = plugin.get("plugin_key")
		if plugin.get("plugin_type") == "EXTERNAL_MCP_SSE":
			raise MCPClientFailure("MCP_TRANSPORT_UNSUPPORTED", "Transport MCP SSE belum didukung.")
		if plugin.get("plugin_type") != "EXTERNAL_MCP_HTTP":
			raise MCPClientFailure("MCP_TRANSPORT_UNSUPPORTED", "Transport MCP tidak didukung.")
		if not _plugin_enabled(plugin_key):
			raise MCPClientFailure("PLUGIN_DISABLED", "Plugin MCP tidak aktif.")
		if not _worker_is_valid(branch, worker_key) or not _plugin_scope_allows(
			plugin_key, branch, worker_key
		):
			raise MCPClientFailure("PLUGIN_SCOPE_DENIED", "Plugin MCP tidak diizinkan untuk worker ini.")
		if not isinstance(arguments, dict):
			raise MCPClientFailure("MCP_TOOL_FAILED", "Argumen tool MCP tidak valid.")
		endpoint = validate_mcp_endpoint(plugin.get("endpoint_url"))
		_validate_endpoint_dns(endpoint)
		config = parse_plugin_config(plugin.get("config_json"))
		response = _run_async_in_thread(
			lambda: _async_call(
				endpoint,
				config["timeout_seconds"],
				tool["original_name"],
				arguments,
			),
			config["timeout_seconds"],
		)
		if getattr(response, "is_error", getattr(response, "isError", False)):
			raise MCPClientFailure("MCP_TOOL_FAILED", "Tool pada server MCP gagal.")
		payload = response.model_dump(mode="json", by_alias=True)
		serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
		if len(serialized) > config["max_result_chars"]:
			return {"truncated": True, "content": serialized[: config["max_result_chars"]]}
		return payload
	except MCPClientFailure as exc:
		log_exception("AIOS MCP Tool", context=f"{exc.code}: {locals().get('plugin_key') or ''}")
		return safe_error(exc.message, exc.code)
	except Exception as exc:
		failure = _exception_failure(exc)
		log_exception("AIOS MCP Tool", context=f"{failure.code}: {locals().get('plugin_key') or ''}")
		return safe_error(failure.message, failure.code)
