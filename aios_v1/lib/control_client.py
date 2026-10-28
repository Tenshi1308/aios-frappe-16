"""HTTP client for the token-guarded Control API on a managed client site.

Security policy is deliberately different from ``web_market_research``:

- The only allowed destinations are registry records (``AIOS Managed Site``).
  Loopback and RFC1918 are valid because the operator registered them.
- Metadata, link-local, unspecified, multicast, and reserved addresses are
  always denied, even when a registry record points at them.
- Redirects are never followed; a 3xx response is a failure.

``log_exception`` di modul ini adalah satu pintu pencatatan: setiap except
handler memanggilnya (atau me-raise), tidak ada except yang diam.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from urllib.parse import urlsplit

import frappe
import requests

from aios_v1.lib import error_utils
from aios_v1.lib.error_utils import REDACTED, safe_error, sanitize_text

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 10
MAX_BODY_BYTES = 2 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
MAX_LOG_DETAIL = 500

_CONTROL_PATH = "/api/method/aios_v1.api.control."
_METHOD_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_HTTP_METHODS = frozenset({"GET", "POST"})
_METADATA_ADDRESSES = frozenset(
	{
		ipaddress.ip_address("169.254.169.254"),
		ipaddress.ip_address("fd00:ec2::254"),
	}
)


class ControlClientError(Exception):
	"""A safe, coded failure raised by URL/host validation."""

	def __init__(self, code: str, message: str, detail: str | None = None):
		super().__init__(message)
		self.code = code
		self.message = message
		self.detail = detail


def _is_forbidden(address) -> bool:
	if address in _METADATA_ADDRESSES:
		return True
	# Python menandai sebagian alamat loopback IPv6 sebagai reserved; kebijakan
	# control plane tetap mengizinkan loopback karena site klien lokal sah.
	if address.is_loopback:
		return False
	if address.is_link_local or address.is_unspecified or address.is_multicast or address.is_reserved:
		return True
	mapped = getattr(address, "ipv4_mapped", None)
	if mapped is not None:
		return _is_forbidden(mapped)
	return False


def is_forbidden_address(ip) -> bool:
	"""Return ``True`` when *ip* is an address the control plane must never call.

	Input yang tidak dapat diparse dianggap terlarang (fail closed) dan
	dicatat, karena pemanggil yang benar selalu mengirim IP literal atau
	alamat yang sudah diparse.
	"""
	if isinstance(ip, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
		return _is_forbidden(ip)
	try:
		address = ipaddress.ip_address(str(ip).strip())
	except ValueError as exc:
		log_exception("ADDRESS_PARSE_FAILED", "Input alamat tidak dapat diparse.", exc=exc)
		return True
	return _is_forbidden(address)


def is_forbidden_literal(hostname: str) -> bool:
	"""Return ``True`` hanya bila *hostname* berbentuk IP literal dan terlarang.

	Hanya string berbentuk IP (ada ``:`` atau semua digit/titik) yang diparse,
	seperti pola di ``web_market_research._resolve_public_addresses``; hostname
	DNS tidak disentuh di sini dan diperiksa saat panggilan klien. String
	berbentuk IP yang tidak valid gagal tertutup dan dicatat.
	"""
	if ":" not in hostname and not re.fullmatch(r"[0-9.]+", hostname):
		return False
	try:
		address = ipaddress.ip_address(hostname)
	except ValueError as exc:
		log_exception("LITERAL_PARSE_FAILED", "Host berbentuk IP tetapi tidak valid.", exc=exc)
		return True
	return is_forbidden_address(address)


def validate_base_url(base_url: str) -> str:
	"""Validate a registry ``base_url`` without DNS or network access.

	Returns the normalized base URL (no trailing slash). Raises
	``ControlClientError`` for schemes other than HTTP(S), userinfo, query or
	fragment components, and literal forbidden addresses.
	"""
	if not isinstance(base_url, str) or not base_url.strip():
		raise ControlClientError("SITE_URL_INVALID", "Base URL registry tidak valid.")
	candidate = base_url.strip()
	if any(ord(char) < 32 for char in candidate):
		raise ControlClientError("SITE_URL_INVALID", "Base URL registry tidak valid.")

	try:
		parts = urlsplit(candidate)
		parts.port
		hostname = parts.hostname
	except ValueError as exc:
		raise ControlClientError("SITE_URL_INVALID", "Base URL registry tidak valid.") from exc

	scheme = parts.scheme.lower()
	if scheme not in ("http", "https") or not hostname:
		raise ControlClientError("SITE_URL_INVALID", "Base URL registry tidak valid.")
	if parts.username is not None or parts.password is not None or "@" in parts.netloc:
		raise ControlClientError("SITE_URL_USERINFO_DENIED", "Base URL tidak boleh memuat userinfo.")
	if parts.query or "?" in candidate:
		raise ControlClientError("SITE_URL_QUERY_DENIED", "Base URL tidak boleh memuat query.")
	if parts.fragment or "#" in candidate:
		raise ControlClientError("SITE_URL_FRAGMENT_DENIED", "Base URL tidak boleh memuat fragment.")

	literal = None
	if ":" in hostname or re.fullmatch(r"[0-9.]+", hostname):
		try:
			literal = ipaddress.ip_address(hostname)
		except ValueError as exc:
			raise ControlClientError("SITE_URL_INVALID", "Base URL registry tidak valid.") from exc
	if literal is not None and is_forbidden_address(literal):
		raise ControlClientError("ADDRESS_FORBIDDEN", "Base URL menunjuk ke alamat yang tidak diizinkan.")

	# Normalisasi hanya membuang garis miring akhir; path (bila ada) dipertahankan
	# sebagai prefix yang sah untuk site di balik reverse proxy.
	normalized = parts._replace(scheme=scheme, path=parts.path.rstrip("/")).geturl()
	return normalized.rstrip("/")


def _build_url(base_url: str, method: str) -> str:
	if not isinstance(method, str) or not _METHOD_PATTERN.fullmatch(method):
		raise ControlClientError("METHOD_INVALID", "Method Control API tidak valid.")
	return f"{base_url}{_CONTROL_PATH}{method}"


def _request_timeout(timeout):
	if timeout is None:
		return (CONNECT_TIMEOUT, READ_TIMEOUT)
	try:
		read_timeout = float(timeout)
	except (TypeError, ValueError) as exc:
		raise ControlClientError("TIMEOUT_INVALID", "Nilai timeout tidak valid.") from exc
	if read_timeout <= 0:
		raise ControlClientError("TIMEOUT_INVALID", "Nilai timeout tidak valid.")
	return (CONNECT_TIMEOUT, min(read_timeout, READ_TIMEOUT))


def _resolve_allowed_addresses(hostname: str, port: int) -> list:
	"""Resolve *hostname* and deny the whole host when any answer is forbidden."""
	literal = None
	if ":" in hostname or re.fullmatch(r"[0-9.]+", hostname):
		try:
			literal = ipaddress.ip_address(hostname)
		except ValueError as exc:
			raise ControlClientError("SITE_URL_INVALID", "Host site klien tidak valid.") from exc
	if literal is not None:
		if is_forbidden_address(literal):
			raise ControlClientError(
				"ADDRESS_FORBIDDEN", "Host site klien menunjuk ke alamat yang tidak diizinkan."
			)
		return [literal]

	try:
		answers = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
	except OSError as exc:
		raise ControlClientError("DNS_RESOLUTION_FAILED", "Host site klien tidak dapat diresolusi.") from exc

	addresses = []
	for answer in answers:
		try:
			address = ipaddress.ip_address(answer[4][0])
		except (IndexError, TypeError, ValueError) as exc:
			raise ControlClientError(
				"DNS_RESOLUTION_FAILED", "Host site klien tidak dapat diresolusi."
			) from exc
		if is_forbidden_address(address):
			# Fail closed: satu jawaban DNS terlarang menolak seluruh host.
			raise ControlClientError(
				"ADDRESS_FORBIDDEN", "Host site klien menunjuk ke alamat yang tidak diizinkan."
			)
		if address not in addresses:
			addresses.append(address)
	if not addresses:
		raise ControlClientError("DNS_RESOLUTION_FAILED", "Host site klien tidak dapat diresolusi.")
	return addresses


def _read_body(response) -> bytes:
	"""Read at most ``MAX_BODY_BYTES`` from a streamed response."""
	headers = getattr(response, "headers", None) or {}
	length = headers.get("Content-Length")
	if length:
		try:
			if int(length) > MAX_BODY_BYTES:
				raise ControlClientError("RESPONSE_TOO_LARGE", "Respons site klien melewati batas ukuran.")
		except (TypeError, ValueError) as exc:
			raise ControlClientError(
				"INVALID_RESPONSE", "Header Content-Length site klien tidak valid."
			) from exc

	body = bytearray()
	for chunk in response.iter_content(chunk_size=READ_CHUNK_BYTES):
		if not chunk:
			continue
		body.extend(chunk)
		if len(body) > MAX_BODY_BYTES:
			raise ControlClientError("RESPONSE_TOO_LARGE", "Respons site klien melewati batas ukuran.")
	return bytes(body)


def _redact(value: str, credential: str | None) -> str:
	text = str(value or "")
	if credential:
		text = text.replace(credential, REDACTED)
	return sanitize_text(text)[:MAX_LOG_DETAIL]


def log_exception(
	code: str,
	message: str,
	*,
	exc: BaseException | None = None,
	detail: str | None = None,
	credential: str | None = None,
) -> dict:
	"""Catat tepat satu Error Log tersanitasi, lalu kembalikan payload error aman.

	Semua except handler di modul ini memanggil fungsi ini; tidak ada kegagalan
	yang diam. Nama sengaja sama dengan pintu pencatatan baku agar pemanggil
	tidak perlu tahu detail redaksi kredensial.
	"""
	error_utils.log_exception(
		f"AIOS Control Client: {code}",
		exc=exc,
		context=code,
		detail=_redact(detail, credential) if detail else None,
	)
	return safe_error(message, code)


def call(site_name, method, *, http_method="GET", params=None, timeout=None) -> dict:
	"""Call one Control API method on a registered client site."""
	try:
		site = frappe.get_doc("AIOS Managed Site", site_name)
	except frappe.DoesNotExistError:
		return log_exception("SITE_NOT_FOUND", "Site klien tidak ditemukan di registry.")
	except Exception as exc:
		return log_exception("SITE_LOOKUP_FAILED", "Site klien tidak dapat dibaca dari registry.", exc=exc)

	try:
		credential = site.get_password("api_credential", raise_exception=False) or ""
	except Exception as exc:
		return log_exception("CREDENTIAL_UNREADABLE", "Kredensial site klien tidak dapat dibaca.", exc=exc)
	if not credential:
		return log_exception("CREDENTIAL_MISSING", "Kredensial site klien tidak tersedia.")

	response = None
	try:
		method_name = str(http_method or "").upper()
		if method_name not in _HTTP_METHODS:
			raise ControlClientError("HTTP_METHOD_INVALID", "HTTP method tidak diizinkan.")

		base_url = validate_base_url(site.base_url)
		url = _build_url(base_url, method)
		parts = urlsplit(base_url)
		hostname = parts.hostname
		port = parts.port or (443 if parts.scheme.lower() == "https" else 80)

		# ponytail: koneksi tidak di-pin ke IP hasil resolusi. Risiko DNS rebinding
		# rendah karena base_url berasal dari record operator, bukan input user;
		# redirect juga tidak diikuti sehingga tidak bisa dipakai mengganti tujuan.
		_resolve_allowed_addresses(hostname, port)

		request_kwargs = {
			"headers": {
				"Authorization": f"token {credential}",
				"Accept": "application/json",
			},
			"allow_redirects": False,
			"timeout": _request_timeout(timeout),
			"stream": True,
		}
		if method_name == "GET":
			request_kwargs["params"] = params
		else:
			request_kwargs["data"] = params or {}

		response = requests.request(method_name, url, **request_kwargs)
		status_code = response.status_code

		if 300 <= status_code < 400:
			return log_exception(
				"REDIRECT_DENIED", "Redirect dari site klien ditolak.", credential=credential
			)

		body = _read_body(response)
		body_text = body.decode("utf-8", errors="replace").replace(credential, REDACTED)

		if not 200 <= status_code < 300:
			return log_exception(
				"REMOTE_HTTP_ERROR",
				"Site klien mengembalikan kesalahan.",
				detail=body_text,
				credential=credential,
			)

		try:
			payload = json.loads(body_text)
		except (TypeError, ValueError) as exc:
			return log_exception(
				"INVALID_RESPONSE",
				"Respons site klien tidak valid.",
				exc=exc,
				detail=body_text,
				credential=credential,
			)

		# Frappe membungkus hasil whitelisted method pada key "message".
		if isinstance(payload, dict) and set(payload) == {"message"}:
			payload = payload["message"]
		if not isinstance(payload, dict):
			return log_exception(
				"INVALID_RESPONSE",
				"Respons site klien tidak valid.",
				detail="payload is not a JSON object",
				credential=credential,
			)
		if payload.get("success") is False:
			return log_exception(
				"REMOTE_ERROR",
				"Site klien melaporkan kegagalan internal.",
				detail=body_text,
				credential=credential,
			)
		return payload
	except ControlClientError as exc:
		return log_exception(exc.code, exc.message, detail=exc.detail, credential=credential)
	except requests.Timeout as exc:
		return log_exception(
			"CONTROL_TIMEOUT",
			"Site klien tidak merespons tepat waktu.",
			exc=exc,
			credential=credential,
		)
	except requests.RequestException as exc:
		return log_exception(
			"CONTROL_UNAVAILABLE",
			"Site klien tidak dapat dihubungi.",
			exc=exc,
			credential=credential,
		)
	except Exception as exc:
		return log_exception("CLIENT_ERROR", "Panggilan ke site klien gagal.", exc=exc, credential=credential)
	finally:
		if response is not None:
			try:
				response.close()
			except Exception as exc:
				# Kegagalan menutup respons juga kegagalan; payload baliknya tidak dipakai.
				log_exception("RESPONSE_CLOSE_FAILED", "Respons site klien tidak dapat ditutup.", exc=exc)


def health(site_name) -> dict:
	return call(site_name, "health")


def users(site_name, status=None, page=1, page_size=50) -> dict:
	params = {"page": page, "page_size": page_size}
	if status is not None:
		params["status"] = status
	return call(site_name, "users", params=params)


def activate_user(site_name, user, status) -> dict:
	return call(
		site_name,
		"activate_user",
		http_method="POST",
		params={"user": user, "status": status},
	)


def metrics(site_name) -> dict:
	return call(site_name, "metrics")
