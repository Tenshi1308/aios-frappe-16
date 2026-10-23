"""Public web fetch with explicit DNS validation and IP-pinned connections."""

import html.parser
import ipaddress
import re
import socket
import ssl
from urllib.parse import urljoin, urlsplit, urlunsplit

import certifi
from urllib3 import HTTPConnectionPool, HTTPSConnectionPool, Timeout
from urllib3.exceptions import HTTPError
from urllib3.exceptions import TimeoutError as Urllib3Timeout

from aios_v1.lib.error_utils import log_exception, safe_error
from aios_v1.lib.tool_registry import ai_tool

MAX_REDIRECTS = 3
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 20_000
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 10
READ_CHUNK_BYTES = 64 * 1024
ALLOWED_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml", "application/json", "text/plain"})
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_METADATA_IPS = frozenset({ipaddress.ip_address("169.254.169.254")})


class _FetchFailure(Exception):
	def __init__(self, code, message):
		super().__init__(message)
		self.code = code
		self.message = message


class _TextExtractor(html.parser.HTMLParser):
	"""Collect visible text and title without executing or interpreting markup."""

	_IGNORED = frozenset({"script", "style", "noscript"})

	def __init__(self):
		super().__init__(convert_charrefs=True)
		self._ignored = []
		self._in_title = False
		self.title_parts = []
		self.text_parts = []

	def handle_starttag(self, tag, attrs):
		if tag in self._IGNORED:
			self._ignored.append(tag)
		elif tag == "title":
			self._in_title = True

	def handle_endtag(self, tag):
		if tag in self._IGNORED:
			for index in range(len(self._ignored) - 1, -1, -1):
				if self._ignored[index] == tag:
					del self._ignored[index:]
					break
		elif tag == "title":
			self._in_title = False

	def handle_data(self, data):
		if self._ignored:
			return
		if self._in_title:
			self.title_parts.append(data)
		self.text_parts.append(data)


def _public_ip(value):
	try:
		address = ipaddress.ip_address(value)
	except ValueError as exc:
		raise _FetchFailure("DNS_RESOLUTION_FAILED", "Host tujuan tidak valid.") from exc
	if (
		address in _METADATA_IPS
		or not address.is_global
		or address.is_loopback
		or address.is_private
		or address.is_link_local
		or address.is_multicast
		or address.is_unspecified
		or address.is_reserved
	):
		raise _FetchFailure("PRIVATE_ADDRESS_DENIED", "Alamat tujuan tidak diizinkan.")
	return address


def _parse_url(url):
	if not isinstance(url, str) or not url or any(ord(char) < 32 for char in url):
		raise _FetchFailure("URL_INVALID", "URL tidak valid.")
	try:
		parts = urlsplit(url)
		port = parts.port
	except ValueError as exc:
		raise _FetchFailure("URL_INVALID", "URL tidak valid.") from exc
	if parts.scheme.lower() not in {"http", "https"}:
		raise _FetchFailure("URL_SCHEME_DENIED", "Skema URL tidak diizinkan.")
	if parts.username is not None or parts.password is not None or "@" in parts.netloc:
		raise _FetchFailure("URL_USERINFO_DENIED", "URL dengan userinfo tidak diizinkan.")
	if not parts.hostname:
		raise _FetchFailure("URL_INVALID", "URL tidak valid.")
	if port is not None and port not in {80, 443}:
		raise _FetchFailure("URL_PORT_DENIED", "Port URL tidak diizinkan.")
	hostname = parts.hostname.rstrip(".").lower()
	if not hostname or hostname == "localhost" or hostname.endswith(".localhost"):
		raise _FetchFailure("PRIVATE_ADDRESS_DENIED", "Alamat tujuan tidak diizinkan.")
	try:
		ascii_hostname = hostname.encode("idna").decode("ascii")
	except UnicodeError as exc:
		raise _FetchFailure("URL_INVALID", "URL tidak valid.") from exc
	if not parts.path:
		parts = parts._replace(path="/")
	return (
		parts._replace(scheme=parts.scheme.lower(), netloc=_netloc(ascii_hostname, port, parts.scheme)),
		ascii_hostname,
		port,
	)


def _netloc(hostname, port, scheme):
	default_port = 443 if scheme.lower() == "https" else 80
	formatted_host = f"[{hostname}]" if ":" in hostname else hostname
	return formatted_host if port is None or port == default_port else f"{formatted_host}:{port}"


def _resolve_public_addresses(hostname, port):
	if ":" in hostname or re.fullmatch(r"[0-9.]+", hostname):
		return [_public_ip(hostname)]
	try:
		answers = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
	except (OSError, socket.gaierror) as exc:
		raise _FetchFailure("DNS_RESOLUTION_FAILED", "Host tujuan tidak dapat diresolusi.") from exc
	addresses = []
	for answer in answers:
		try:
			address = _public_ip(answer[4][0])
		except _FetchFailure:
			# Mixed public/private DNS answers are denied as a whole.
			raise
		if address not in addresses:
			addresses.append(address)
	if not addresses:
		raise _FetchFailure("DNS_RESOLUTION_FAILED", "Host tujuan tidak memiliki alamat yang valid.")
	return addresses


def _request_once(url_parts, hostname, port, address):
	scheme = url_parts.scheme
	port_number = port or (443 if scheme == "https" else 80)
	path = url_parts.path or "/"
	if url_parts.query:
		path = f"{path}?{url_parts.query}"
	headers = {
		"Host": _netloc(hostname, port, scheme),
		"User-Agent": "AIOS-Web-Market-Research/1.0",
		"Accept": "text/html, application/xhtml+xml, application/json, text/plain",
		"Accept-Encoding": "gzip, deflate",
		"Connection": "close",
	}
	pool_options = {
		"host": address.compressed,
		"port": port_number,
		"timeout": Timeout(connect=CONNECT_TIMEOUT_SECONDS, read=READ_TIMEOUT_SECONDS),
		"retries": False,
		"headers": headers,
		"maxsize": 1,
		"block": True,
	}
	if scheme == "https":
		pool = HTTPSConnectionPool(
			**pool_options,
			server_hostname=hostname,
			assert_hostname=hostname,
			cert_reqs=ssl.CERT_REQUIRED,
			ca_certs=certifi.where(),
		)
	else:
		pool = HTTPConnectionPool(**pool_options)
	try:
		response = pool.request("GET", path, redirect=False, preload_content=False, decode_content=False)
		return pool, response
	except Exception:
		pool.close()
		raise


def _read_body(response):
	length = response.headers.get("Content-Length")
	if length:
		try:
			if int(length) > MAX_BODY_BYTES:
				raise _FetchFailure("RESPONSE_TOO_LARGE", "Respons melewati batas ukuran.")
		except ValueError as exc:
			raise _FetchFailure("FETCH_FAILED", "Server memberi ukuran respons yang tidak valid.") from exc
	body = bytearray()
	for chunk in response.stream(amt=READ_CHUNK_BYTES, decode_content=True):
		if not chunk:
			continue
		body.extend(chunk)
		if len(body) > MAX_BODY_BYTES:
			raise _FetchFailure("RESPONSE_TOO_LARGE", "Respons melewati batas ukuran.")
	return bytes(body)


def _decode_body(body, content_type):
	match = re.search(r"(?:^|;)\s*charset\s*=\s*[\"']?([^;\"'\s]+)", content_type, flags=re.I)
	encoding = match.group(1) if match else "utf-8"
	try:
		return body.decode(encoding, errors="replace")
	except LookupError:
		log_exception("AIOS Web Fetch Encoding", context="UNKNOWN_CHARSET")
		return body.decode("utf-8", errors="replace")


def _extract_text(body, content_type):
	text = _decode_body(body, content_type)
	title = ""
	if content_type.split(";", 1)[0].strip().lower() in {"text/html", "application/xhtml+xml"}:
		parser = _TextExtractor()
		parser.feed(text)
		parser.close()
		title = " ".join("".join(parser.title_parts).split())
		text = " ".join(" ".join(parser.text_parts).split())
	else:
		text = " ".join(text.split())
	truncated = len(text) > MAX_TEXT_CHARS
	return title, text[:MAX_TEXT_CHARS], truncated


def _fetch(url):
	current_url = url
	visited = set()
	redirects = 0
	while True:
		parts, hostname, port = _parse_url(current_url)
		canonical = urlunsplit(parts)
		if canonical in visited:
			raise _FetchFailure("REDIRECT_DENIED", "Redirect berulang ditolak.")
		visited.add(canonical)
		addresses = _resolve_public_addresses(hostname, port or (443 if parts.scheme == "https" else 80))
		pool = None
		response = None
		try:
			pool, response = _request_once(parts, hostname, port, addresses[0])
			if response.status in _REDIRECT_CODES:
				location = response.headers.get("Location")
				if not location:
					raise _FetchFailure("REDIRECT_DENIED", "Redirect tanpa tujuan ditolak.")
				if redirects >= MAX_REDIRECTS:
					raise _FetchFailure("REDIRECT_LIMIT", "Jumlah redirect melewati batas.")
				redirects += 1
				current_url = urljoin(canonical, location)
				continue
			content_type = response.headers.get("Content-Type", "").strip()
			media_type = content_type.split(";", 1)[0].strip().lower()
			if media_type not in ALLOWED_CONTENT_TYPES:
				raise _FetchFailure("CONTENT_TYPE_UNSUPPORTED", "Jenis konten tidak didukung.")
			if response.status < 200 or response.status >= 300:
				raise _FetchFailure("FETCH_FAILED", "Server tidak dapat memenuhi permintaan.")
			body = _read_body(response)
			title, text, truncated = _extract_text(body, content_type)
			return {
				"url": _redact_url(url),
				"final_url": _redact_url(canonical),
				"status_code": response.status,
				"content_type": media_type,
				"title": title,
				"text": text,
				"truncated": truncated,
			}
		except _FetchFailure:
			raise
		except (Urllib3Timeout, TimeoutError) as exc:
			raise _FetchFailure("FETCH_TIMEOUT", "Permintaan web melewati batas waktu.") from exc
		except (HTTPError, OSError, ssl.SSLError) as exc:
			raise _FetchFailure("FETCH_FAILED", "Konten web tidak dapat diambil.") from exc
		finally:
			if response is not None:
				response.close()
			if pool is not None:
				pool.close()


def _redact_url(url):
	parts = urlsplit(url)
	return urlunsplit(parts._replace(query="", fragment=""))


@ai_tool(
	name="web_fetch",
	description="Mengambil teks dari URL publik yang aman dan menampilkan ringkasan kontennya.",
	parameters={"url": {"type": "string", "description": "URL halaman publik HTTP atau HTTPS"}},
	branch=["finance", "sales"],
	roles=[],
	plugin_key="web-market-research",
)
def web_fetch(url):
	try:
		return _fetch(url)
	except _FetchFailure as exc:
		log_exception("AIOS Web Fetch", context=exc.code)
		return safe_error(exc.message, exc.code)
	except Exception:
		log_exception("AIOS Web Fetch", context="FETCH_FAILED")
		return safe_error("Konten web tidak dapat diambil.", "FETCH_FAILED")


@ai_tool(
	name="web_search",
	description="Mencari informasi web; provider pencarian belum dikonfigurasi.",
	parameters={
		"query": {"type": "string", "description": "Kata kunci pencarian"},
		"limit": {"type": "integer", "description": "Jumlah hasil yang diminta", "required": False},
	},
	branch=["finance", "sales"],
	roles=[],
	plugin_key="web-market-research",
)
def web_search(query, limit=None):
	log_exception("AIOS Web Search", context="SEARCH_PROVIDER_NOT_CONFIGURED")
	return safe_error("Provider pencarian belum dikonfigurasi.", "SEARCH_PROVIDER_NOT_CONFIGURED")
