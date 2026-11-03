"""Thin Telegram Bot API client for the AIOS channel connector.

Only transport: no business logic, no ERPNext access, no persistence. The bot
token is read from `AIOS Telegram Setting.bot_token` (Frappe `Password` field)
and never appears in messages, logs, or error payloads.

Reference: https://core.telegram.org/bots/api
"""

from __future__ import annotations

import frappe
import requests

from aios_v1.lib.error_utils import log_exception, sanitize_text

SETTING_DOCTYPE = "AIOS Telegram Setting"
API_BASE = "https://api.telegram.org"
DEFAULT_TIMEOUT = 15
# Long-poll window must stay below the HTTP timeout used for the same request.
POLL_TIMEOUT = 25
REQUEST_TIMEOUT = POLL_TIMEOUT + 10


class ConnectorError(Exception):
    """Transport/config failure carrying a stable code for callers and logs."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def get_config() -> dict:
    """Read connector settings. Never returns a token to any response payload."""
    doc = frappe.get_single(SETTING_DOCTYPE)
    token = doc.get_password("bot_token", raise_exception=False) or ""
    return {
        "bot_token": token,
        "bot_username": doc.get("bot_username") or "",
        "is_active": bool(doc.get("is_active")),
        "persona_tone": doc.get("persona_tone") or "Ramah & Kasual",
        "custom_instructions": doc.get("custom_instructions") or "",
    }


def is_configured() -> bool:
    """True only when the connector is switched on and a token is stored."""
    config = get_config()
    return bool(config["is_active"] and config["bot_token"])


def _require_token() -> str:
    token = get_config()["bot_token"]
    if not token:
        raise ConnectorError("CONNECTOR_NO_TOKEN", "Token bot belum diatur di AIOS Telegram Setting.")
    return token


def _api(method: str, payload: dict | None = None, *, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Call one Bot API method and return its `result`.

    Failures are logged without the token and re-raised as `ConnectorError`;
    callers decide whether to retry or to skip the update.
    """
    token = _require_token()
    url = f"{API_BASE}/bot{token}/{method}"
    try:
        response = requests.post(url, json=payload or {}, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        # A long-poll timeout is a normal idle period, not a failure.
        if method == "getUpdates":
            return []
        log_exception("AIOS Connector Transport", exc=exc, context=f"telegram:{method}")
        raise ConnectorError("CONNECTOR_TIMEOUT", "Server Telegram tidak merespons.") from exc
    except Exception as exc:
        log_exception("AIOS Connector Transport", exc=exc, context=f"telegram:{method}")
        raise ConnectorError("CONNECTOR_UNREACHABLE", "Gagal menghubungi server Telegram.") from exc

    try:
        data = response.json()
    except ValueError as exc:
        log_exception("AIOS Connector Response", exc=exc, context=f"telegram:{method}")
        raise ConnectorError("CONNECTOR_BAD_RESPONSE", "Respons Telegram tidak valid.") from exc

    if not data.get("ok"):
        # Telegram's own `description` never contains the token; sanitize anyway.
        # Logging is left to the caller so one failure produces one log entry.
        description = sanitize_text(data.get("description") or "Unknown error")
        raise ConnectorError("CONNECTOR_API_ERROR", description)

    return data.get("result")


def get_me() -> dict:
    """Validate the token; returns bot metadata."""
    return _api("getMe") or {}


def delete_webhook() -> bool:
    """Drop any webhook so `getUpdates` is allowed (the two are exclusive)."""
    return bool(_api("deleteWebhook", {"drop_pending_updates": False}))


def get_updates(offset: int = 0, *, timeout: int = POLL_TIMEOUT, limit: int = 20) -> list:
    """Long-poll for new updates starting at `offset`."""
    payload = {"timeout": timeout, "limit": limit, "allowed_updates": ["message", "callback_query"]}
    if offset:
        payload["offset"] = offset
    result = _api("getUpdates", payload, timeout=REQUEST_TIMEOUT)
    return result or []


def send_message(chat_id, text: str) -> bool:
    """Send plain text; returns False instead of raising so callers keep the transcript."""
    try:
        _api("sendMessage", {"chat_id": chat_id, "text": text})
        return True
    except ConnectorError as exc:
        log_exception("AIOS Connector Send", context=f"sendMessage; code={exc.code}; {exc.message}")
        return False


def send_chat_action(chat_id, action: str = "typing") -> bool:
    try:
        _api("sendChatAction", {"chat_id": chat_id, "action": action})
        return True
    except ConnectorError as exc:
        log_exception("AIOS Connector Action", context=f"sendChatAction; code={exc.code}")
        return False
