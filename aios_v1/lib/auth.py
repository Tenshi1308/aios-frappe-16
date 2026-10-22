import hashlib
import hmac
import os
import json
import base64
import time
import frappe

from aios_v1.lib.error_utils import log_exception

SESSION_COOKIE = "aios_session"

def get_session_secret() -> str:
    """
    Mengambil kunci rahasia untuk menandatangani token sesi dari site_config.json.
    Sesuai Prinsip Zero Hardcoding: Dilarang keras menaruh fallback default.
    Jika encryption_key tidak tersedia, sistem melempar error.
    """
    secret = frappe.conf.get("encryption_key")
    if not secret:
        raise RuntimeError("Kunci 'encryption_key' tidak ditemukan di site_config.json site aktif!")
    return str(secret)

def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    dk = hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt), n=16384, r=8, p=1, maxmem=0, dklen=32)
    return f"{salt}:{dk.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        if not stored:
            return False
        parts = stored.split(":")
        if len(parts) != 2:
            return False
        salt, hash_hex = parts
        dk = hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt), n=16384, r=8, p=1, maxmem=0, dklen=32)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception as exc:
        log_exception(
            "AIOS Auth: verifikasi password gagal",
            context=f"jenis={type(exc).__name__}",
        )
        return False

def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')

def base64url_decode(data: str) -> bytes:
    pad = '=' * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode((data + pad).encode('utf-8'))

def sign(data: str) -> str:
    secret = get_session_secret()
    h = hmac.new(secret.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).digest()
    return base64url_encode(h)

def create_session_token(payload: dict) -> str:
    full = dict(payload)
    full['exp'] = int(time.time() * 1000) + 1000 * 60 * 60 * 12
    body = base64url_encode(json.dumps(full, separators=(',', ':')).encode('utf-8'))
    sig = sign(body)
    return f"{body}.{sig}"

def verify_session_token(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        body, sig = parts
        expected = sign(body)
        if not hmac.compare_digest(sig, expected):
            return None
        raw = base64url_decode(body).decode('utf-8')
        payload = json.loads(raw)
        if payload.get('exp', 0) < int(time.time() * 1000):
            return None
        return payload
    except Exception as exc:
        log_exception(
            "AIOS Auth: verifikasi sesi gagal",
            context=f"jenis={type(exc).__name__}",
        )
        return None

def portal_from_request(req, body=None):
    if body and isinstance(body, dict) and body.get("portal"):
        return str(body["portal"]).lower()
    host = req.headers.get("host", "") or getattr(req, "host", "") or ""
    origin = req.headers.get("origin", "") or ""
    referer = req.headers.get("referer", "") or ""
    x_portal = req.headers.get("x-portal-host", "") or req.headers.get("x-portal", "") or ""
    source = f"{x_portal} {origin} {host} {referer}".lower()
    if "8085" in source or "developer" in source:
        return "developer"
    return "client"
