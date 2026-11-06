"""Employee account linking for the AIOS Telegram connector.

Handles token creation, Redis caching, brute-force rate-limiting, and
account linking/unlinking. Guest customers do NOT use this module.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import frappe
from frappe.utils import now_datetime

SETTING_DOCTYPE = "AIOS Telegram Setting"
THREAD_DOCTYPE = "AIOS Channel Thread"

DEFAULT_EXPIRY_SECONDS = 300
MAX_BRUTE_FORCE_ATTEMPTS = 5
LOCKOUT_SECONDS = 900  # 15 minutes


class LinkError(Exception):
    """Business rule violation for linking operations."""

    def __init__(self, message: str, code: str = "LINK_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


def _get_setting() -> dict[str, Any]:
    """Return relevant fields from AIOS Telegram Setting."""
    row = frappe.db.get_value(
        SETTING_DOCTYPE,
        SETTING_DOCTYPE,
        ["bot_username", "link_code_expiry_seconds"],
        as_dict=True,
    )
    return row or {}


def get_expiry_seconds() -> int:
    setting = _get_setting()
    val = setting.get("link_code_expiry_seconds")
    try:
        val_int = int(val) if val is not None else DEFAULT_EXPIRY_SECONDS
        return val_int if val_int > 0 else DEFAULT_EXPIRY_SECONDS
    except (TypeError, ValueError) as exc:
        frappe.log_error(title="AIOS Connector Linking Expiry Parse", message=str(exc))
        return DEFAULT_EXPIRY_SECONDS


def get_bot_username() -> str:
    setting = _get_setting()
    username = (setting.get("bot_username") or "").strip()
    if not username:
        raise LinkError(
            "AIOS Telegram Setting.bot_username belum dikonfigurasi.",
            "BOT_USERNAME_MISSING",
        )
    return username


def create_link_token(user: str) -> dict[str, Any]:
    """Generate a single-use deep link token for the authenticated user.

    Enforces:
    - User must match current session user.
    - Previous active token for this user is invalidated.
    - Raw token has 56 characters (high entropy).
    - SHA-256 hash stored in Redis (never raw token in cache).
    - Cache key uses default shared=False to isolate per site database.
    """
    session_user = frappe.session.user
    if not session_user or session_user in ("", "Guest"):
        raise frappe.PermissionError("Sesi login diperlukan untuk membuat tautan.")
    if user != session_user:
        raise frappe.PermissionError("Hanya dapat membuat tautan untuk akun sendiri.")

    bot_username = get_bot_username()
    ttl = get_expiry_seconds()

    # Cancel previous token for this user if one exists
    old_hash = frappe.cache().get_value(f"aios_tg_user_token:{user}")
    if old_hash:
        frappe.cache().delete_value(f"aios_tg_link:{old_hash}")
        frappe.cache().delete_value(f"aios_tg_user_token:{user}")

    # Generate 56-char raw token
    raw_token = frappe.generate_hash()
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    # Store payload: only {"user": user}
    payload = json.dumps({"user": user})
    frappe.cache().set_value(f"aios_tg_link:{token_hash}", payload, expires_in_sec=ttl)
    frappe.cache().set_value(f"aios_tg_user_token:{user}", token_hash, expires_in_sec=ttl)

    deep_link = f"https://t.me/{bot_username}?start=LINK_{raw_token}"
    return {
        "deep_link": deep_link,
        "expires_in_seconds": ttl,
    }


def is_locked_out(chat_id: str | int) -> bool:
    """Check if chat_id has exceeded maximum failed attempts in the last 15 min."""
    key = f"aios_tg_link_attempts:{chat_id}"
    attempts = frappe.cache().get_value(key)
    try:
        return bool(attempts and int(attempts) >= MAX_BRUTE_FORCE_ATTEMPTS)
    except (TypeError, ValueError) as exc:
        frappe.log_error(title="AIOS Connector Linking Lockout Parse", message=str(exc))
        return False


def record_attempt_failure(chat_id: str | int) -> int:
    """Increment failed attempts for chat_id with 15-minute sliding TTL."""
    key = f"aios_tg_link_attempts:{chat_id}"
    attempts = frappe.cache().get_value(key)
    try:
        count = int(attempts) if attempts else 0
    except (TypeError, ValueError) as exc:
        frappe.log_error(title="AIOS Connector Linking Attempt Count Parse", message=str(exc))
        count = 0
    count += 1
    frappe.cache().set_value(key, str(count), expires_in_sec=LOCKOUT_SECONDS)
    return count


def clear_attempts(chat_id: str | int) -> None:
    frappe.cache().delete_value(f"aios_tg_link_attempts:{chat_id}")


def verify_and_consume_token(chat_id: str | int, raw_token: str) -> tuple[bool, str, str | None]:
    """Verify deep link token, enforce lockout, single-use, and return target user.

    Returns: (success: bool, user_facing_message: str, linked_user: str | None)
    """
    chat_str = str(chat_id)

    # 1. Check lockout BEFORE hash or token lookup
    if is_locked_out(chat_str):
        return (
            False,
            "Terlalu banyak percobaan gagal. Silakan tunggu 15 menit sebelum mencoba lagi.",
            None,
        )

    # 2. Check if chat is already linked to another employee
    existing_linked = frappe.db.get_value(
        THREAD_DOCTYPE,
        {"channel": "telegram", "external_thread_id": chat_str},
        "linked_user",
    )
    if existing_linked:
        return (
            False,
            f"Chat Telegram ini sudah tertaut ke akun karyawan '{existing_linked}'. "
            "Gunakan /unlink terlebih dahulu jika ingin mengganti akun.",
            None,
        )

    # 3. Hash raw token and lookup in Redis
    clean_token = (raw_token or "").strip()
    if not clean_token:
        record_attempt_failure(chat_str)
        return (False, "Tautan tidak valid atau sudah kedaluwarsa.", None)

    token_hash = hashlib.sha256(clean_token.encode("utf-8")).hexdigest()
    cached = frappe.cache().get_value(f"aios_tg_link:{token_hash}")
    if not cached:
        record_attempt_failure(chat_str)
        frappe.log_error(
            f"Percobaan tautan token tidak valid/kedaluwarsa dari chat {chat_str}",
            "AIOS Telegram Link",
        )
        return (
            False,
            "Tautan tidak valid atau sudah kedaluwarsa. Silakan buat tautan baru di aplikasi AIOS.",
            None,
        )

    try:
        data = json.loads(cached)
        target_user = data.get("user")
    except Exception as exc:
        record_attempt_failure(chat_str)
        frappe.log_error(f"Payload token korup: {exc}", "AIOS Telegram Link")
        return (False, "Tautan tidak dapat diproses.", None)

    if not target_user or not frappe.db.exists("User", target_user):
        record_attempt_failure(chat_str)
        return (False, "Akun user untuk tautan ini tidak ditemukan.", None)

    # 4. Check if target user is already linked to ANOTHER chat
    other_thread = frappe.db.get_value(
        THREAD_DOCTYPE,
        {"channel": "telegram", "linked_user": target_user},
        ["name", "external_thread_id"],
        as_dict=True,
    )
    if other_thread and str(other_thread["external_thread_id"]) != chat_str:
        record_attempt_failure(chat_str)
        return (
            False,
            f"Akun AIOS '{target_user}' sudah terhubung ke Telegram lain. "
            "Putuskan tautan lama terlebih dahulu di aplikasi AIOS.",
            None,
        )

    # 5. Consume token immediately (single-use)
    frappe.cache().delete_value(f"aios_tg_link:{token_hash}")
    frappe.cache().delete_value(f"aios_tg_user_token:{target_user}")
    clear_attempts(chat_str)

    return (True, "Tautan valid.", target_user)


def link_thread_to_user(chat_id: str | int, user: str, thread_name: str | None = None) -> None:
    """Persist linked_user and linked_at on AIOS Channel Thread."""
    chat_str = str(chat_id)
    if not thread_name:
        thread_name = frappe.db.get_value(
            THREAD_DOCTYPE,
            {"channel": "telegram", "external_thread_id": chat_str},
            "name",
        )

    now = now_datetime()
    if thread_name:
        frappe.db.set_value(
            THREAD_DOCTYPE,
            thread_name,
            {"linked_user": user, "linked_at": now},
            update_modified=False,
        )
        frappe.db.commit()

    logger = frappe.logger("aios_connector", allow_site=True)
    logger.setLevel(logging.INFO)
    logger.info(f"Telegram chat {chat_str} successfully linked to employee user {user}")


def unlink_thread(chat_id: str | int) -> bool:
    """Clear linked_user and linked_at for a given chat_id."""
    chat_str = str(chat_id)
    thread = frappe.db.get_value(
        THREAD_DOCTYPE,
        {"channel": "telegram", "external_thread_id": chat_str},
        ["name", "linked_user"],
        as_dict=True,
    )
    if not thread or not thread.get("linked_user"):
        return False

    old_user = thread["linked_user"]
    frappe.db.set_value(
        THREAD_DOCTYPE,
        thread["name"],
        {"linked_user": None, "linked_at": None},
        update_modified=False,
    )
    frappe.db.commit()

    logger = frappe.logger("aios_connector", allow_site=True)
    logger.setLevel(logging.INFO)
    logger.info(f"Telegram chat {chat_str} unlinked from user {old_user}")
    return True


def unlink_by_user(user: str) -> bool:
    """Clear linked_user and linked_at for the specified employee user."""
    threads = frappe.get_all(
        THREAD_DOCTYPE,
        filters={"channel": "telegram", "linked_user": user},
        fields=["name", "external_thread_id"],
    )
    if not threads:
        return False

    for row in threads:
        frappe.db.set_value(
            THREAD_DOCTYPE,
            row["name"],
            {"linked_user": None, "linked_at": None},
            update_modified=False,
        )
    frappe.db.commit()

    logger = frappe.logger("aios_connector", allow_site=True)
    logger.setLevel(logging.INFO)
    logger.info(f"User {user} unlinked from Telegram threads: {[r['external_thread_id'] for r in threads]}")
    return True


def get_link_status(user: str) -> dict[str, Any]:
    """Check if the given employee user has an active Telegram link."""
    threads = frappe.get_all(
        THREAD_DOCTYPE,
        filters={"channel": "telegram", "linked_user": user},
        fields=["name", "external_thread_id", "username", "display_name", "linked_at"],
        order_by="linked_at desc",
        limit_page_length=1,
    )
    if not threads:
        return {"linked": False}

    thread = threads[0]
    return {
        "linked": True,
        "external_thread_id": thread.get("external_thread_id"),
        "telegram_username": thread.get("username"),
        "display_name": thread.get("display_name"),
        "linked_at": str(thread.get("linked_at") or ""),
    }
