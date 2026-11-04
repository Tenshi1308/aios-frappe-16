"""Thread resolution and inbound message dispatch for the Telegram channel.

One job: turn an inbound update into (a) an `AIOS Channel Thread` bound to an
existing workspace user, and (b) a reply produced by the existing Sales manager
stream. No ERPNext writes happen here — the manager's tool loop only creates
`Pending Action Draft` documents, which a human approves in Ekasa Desk.

Identity: the whole block runs as the configured `owner_user` because the chat
path (`handle_stream`, `create_draft`, `save_private_file`) reads
`frappe.session.user`. In a background worker `frappe.connect()` leaves the
session as `Administrator`, which would bypass every permission — so the user is
set explicitly and restored in `finally`.
"""

from __future__ import annotations

import json
import time

import frappe
from frappe.utils import now_datetime

from aios_v1.lib.connector import BRANCH, CHANNEL, audit, rules, telegram_client
from aios_v1.lib.connector.explain import explain_flag
from aios_v1.lib.connector.notify import notify_flag
from aios_v1.lib.error_utils import log_exception, safe_error
from aios_v1.managers import get_manager
from aios_v1.services.usage import check_site_token_quota

SETTING_DOCTYPE = "AIOS Telegram Setting"
THREAD_DOCTYPE = "AIOS Channel Thread"
FLAG_DOCTYPE = "AIOS Conversation Flag"
MESSAGE_DOCTYPE = "AIOS Message"
CONVERSATION_DOCTYPE = "AIOS Conversation"

NO_OWNER_REPLY = "Maaf, layanan ini belum siap. Silakan hubungi admin."
BUSY_REPLY = "Maaf, sedang ada kendala di sistem kami. Boleh coba lagi sebentar lagi?"
QUOTA_REPLY = "Maaf, layanan sedang tidak tersedia. Silakan hubungi admin."
RATE_LIMIT_MSG = "Maaf, Anda telah mencapai batas pengiriman pesan sementara. Mohon tunggu beberapa saat sebelum mengirim pesan kembali."

RATE_LIMIT_MINUTE = 15
RATE_LIMIT_HOUR = 60
RATE_LIMIT_DAY = 200


def check_and_increment_rate_limit(chat_id: str | int) -> tuple[bool, str | None]:
    """Enforce multi-tiered rate limits per chat: 15/min, 60/hr, 200/day.

    Counts are isolated per chat_id in frappe.cache() using time-bucket keys.
    Returns (allowed: bool, warning_message: str | None).
    """
    chat_str = str(chat_id)
    now = time.time()
    m_bucket = int(now // 60)
    h_bucket = int(now // 3600)
    d_bucket = int(now // 86400)

    cache = frappe.cache()
    key_m = f"aios_tg_rate_m:{chat_str}:{m_bucket}"
    key_h = f"aios_tg_rate_h:{chat_str}:{h_bucket}"
    key_d = f"aios_tg_rate_d:{chat_str}:{d_bucket}"

    def _get_count(k: str) -> int:
        val = cache.get_value(k)
        try:
            return int(val) if val is not None else 0
        except (TypeError, ValueError) as exc:
            frappe.log_error(title="AIOS Rate Limit Count Error", message=str(exc))
            return 0

    c_m = _get_count(key_m)
    c_h = _get_count(key_h)
    c_d = _get_count(key_d)

    if c_m >= RATE_LIMIT_MINUTE or c_h >= RATE_LIMIT_HOUR or c_d >= RATE_LIMIT_DAY:
        warn_key = f"aios_tg_rate_warned:{chat_str}"
        already_warned = cache.get_value(warn_key)
        if not already_warned:
            cache.set_value(warn_key, "1", expires_in_sec=60)
            return False, RATE_LIMIT_MSG
        return False, None

    cache.set_value(key_m, str(c_m + 1), expires_in_sec=120)
    cache.set_value(key_h, str(c_h + 1), expires_in_sec=7200)
    cache.set_value(key_d, str(c_d + 1), expires_in_sec=172800)
    return True, None


def clear_rate_limit(chat_id: str | int) -> None:
    """Clear rate limit counters for chat_id (e.g. for testing or reset)."""
    chat_str = str(chat_id)
    now = time.time()
    cache = frappe.cache()
    m_bucket = int(now // 60)
    h_bucket = int(now // 3600)
    d_bucket = int(now // 86400)
    cache.delete_value(f"aios_tg_rate_m:{chat_str}:{m_bucket}")
    cache.delete_value(f"aios_tg_rate_h:{chat_str}:{h_bucket}")
    cache.delete_value(f"aios_tg_rate_d:{chat_str}:{d_bucket}")
    cache.delete_value(f"aios_tg_rate_warned:{chat_str}")


class ConnectorConfigError(Exception):
    """Connector is not usable; the message is safe to log, never to send."""


def _owner_user() -> str:
    owner = frappe.db.get_single_value(SETTING_DOCTYPE, "owner_user")
    if not owner:
        raise ConnectorConfigError("AIOS Telegram Setting.owner_user belum diisi.")
    if not frappe.db.exists("User", owner):
        raise ConnectorConfigError("owner_user menunjuk User yang tidak ada.")
    return owner


def get_or_create_thread(chat_id, user_info: dict | None = None) -> dict:
    """Return the thread for this chat, creating conversation + thread once.

    Field separation:
    - `thread.owner_user`: set to Setting.owner_user for workspace audit & flags.
    - `conversation`: created with effective_user 'Guest' for new unlinked threads.
    """
    external_id = str(chat_id)
    name = frappe.db.get_value(
        THREAD_DOCTYPE,
        {"channel": CHANNEL, "external_thread_id": external_id},
        "name",
    )
    if name:
        return frappe.get_doc(THREAD_DOCTYPE, name).as_dict()

    owner = _owner_user()
    # Satu conversation per thread: `ensure_conversation` tanpa `force_new` akan
    # mengembalikan conversation terakhir user+branch, sehingga dua chat_id
    # berbeda berbagi transkrip. Hanya thread baru yang sampai ke baris ini.
    # Thread baru dimulai sebagai tamu (Guest).
    conversation = str(get_manager(BRANCH).ensure_conversation("Guest", force_new=True))
    info = user_info or {}
    doc = frappe.new_doc(THREAD_DOCTYPE)
    doc.channel = CHANNEL
    doc.external_thread_id = external_id
    doc.conversation = conversation
    doc.owner_user = owner
    doc.linked_user = None
    doc.linked_at = None
    doc.display_name = " ".join(
        part for part in (info.get("first_name"), info.get("last_name")) if part
    ).strip()
    doc.username = info.get("username") or ""
    doc.status = "Open"
    doc.insert(ignore_permissions=True)
    return doc.as_dict()


def _collect_reply(manager, conversation: str, user: str, text: str) -> str:
    """Drain the manager stream and keep only the answer text.

    SSE framing is stripped: the connector is a text channel, so trace and
    artifact events are not forwarded. The manager persists both messages and
    records token usage itself, so nothing is written twice here.
    """
    chunks: list[str] = []
    for raw in manager.handle_stream(
        user_message=text,
        conversation_id=conversation,
        user=user,
    ):
        line = (raw or "").strip()
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[5:].strip())
        except (TypeError, ValueError) as exc:
            log_exception("AIOS Connector Stream Parse", exc=exc, context=line[:120])
            continue
        if event.get("type") == "delta":
            chunks.append(event.get("text") or "")
    return "".join(chunks).strip()


def _last_user_message(conversation: str) -> dict | None:
    rows = frappe.get_all(
        MESSAGE_DOCTYPE,
        filters={"conversation": conversation, "role": "user"},
        fields=["name", "content"],
        order_by="creation desc",
        limit_page_length=1,
    )
    return rows[0] if rows else None


def _ensure_inbound_recorded(conversation: str, text: str) -> str | None:
    """Guarantee the inbound text exists in the transcript and return its name.

    `handle_stream` persists the user message itself, so normally this finds it
    and does nothing. If the manager failed before writing (provider down, or a
    caller that does not persist), the channel keeps the message itself —
    otherwise the audit and the flag evidence would point at nothing.
    """
    last = _last_user_message(conversation)
    if last and (last.get("content") or "").strip() == text.strip():
        return last["name"]

    doc = frappe.new_doc(MESSAGE_DOCTYPE)
    doc.conversation = conversation
    doc.role = "user"
    doc.worker_key = "manager"
    doc.content = text
    doc.insert(ignore_permissions=True)
    return doc.name


def _transcript(conversation: str) -> list[dict]:
    return frappe.get_all(
        MESSAGE_DOCTYPE,
        filters={"conversation": conversation},
        fields=["role", "content", "creation"],
        order_by="creation asc",
        limit_page_length=0,
    )


def _raise_flags(thread: dict, text: str, message_name: str | None) -> list[str]:
    """Create flags for deterministic hits; the LLM only explains them."""
    hits = rules.evaluate(text, rules.load_config())
    if not hits:
        return []

    transcript = _transcript(thread["conversation"])
    created: list[str] = []
    for hit in hits:
        flag = frappe.new_doc(FLAG_DOCTYPE)
        flag.thread = thread["name"]
        flag.conversation = thread["conversation"]
        flag.owner_user = thread["owner_user"]
        flag.rule_key = hit["rule_key"]
        flag.severity = hit["severity"]
        flag.status = "Open"
        flag.label = hit["label"]
        flag.excerpt = hit["excerpt"]
        flag.message_ids = message_name or ""
        flag.insert(ignore_permissions=True)
        # Explanation is best-effort and never blocks the flag.
        reason = explain_flag(hit["label"], hit["excerpt"], transcript)
        if reason:
            frappe.db.set_value(FLAG_DOCTYPE, flag.name, "reason_text", reason, update_modified=False)
        created.append(flag.name)
        notify_flag(flag)
    return created


def process_message(update: dict) -> dict:
    """Handle one Telegram `message` update end to end."""
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id")
    from_user = message.get("from") or {}

    if not text or chat_id is None:
        return {"success": False, "code": "CONNECTOR_IGNORED"}

    allowed, rate_limit_warning = check_and_increment_rate_limit(chat_id)
    if not allowed:
        if rate_limit_warning:
            telegram_client.send_message(chat_id, rate_limit_warning)
        return {"success": False, "code": "CONNECTOR_RATE_LIMITED"}

    try:
        owner = _owner_user()
    except ConnectorConfigError as exc:
        log_exception("AIOS Connector Config", context=str(exc))
        telegram_client.send_message(chat_id, NO_OWNER_REPLY)
        return {"success": False, "code": "CONNECTOR_NOT_CONFIGURED"}

    if not check_site_token_quota():
        log_exception("AIOS Connector Quota", context=f"chat={chat_id}")
        telegram_client.send_message(chat_id, QUOTA_REPLY)
        return {"success": False, "code": "CONNECTOR_QUOTA_EXHAUSTED"}

    clean_text = text.strip()

    # 1. Deep link linking handler: /start LINK_<token>
    if clean_text.startswith("/start LINK_"):
        raw_token = clean_text[len("/start LINK_"):].strip()
        from aios_v1.lib.connector.linking import link_thread_to_user, verify_and_consume_token

        success, msg, target_user = verify_and_consume_token(chat_id, raw_token)
        thread = get_or_create_thread(chat_id, from_user)
        if success and target_user:
            link_thread_to_user(chat_id, target_user, thread["name"])
            thread["linked_user"] = target_user
            reply = (
                f"Akun Telegram Anda berhasil ditautkan ke akun AIOS '{target_user}'. "
                "Sekarang Anda dapat menggunakan layanan karyawan."
            )
        else:
            reply = msg

        telegram_client.send_message(chat_id, reply)
        return {
            "success": success,
            "thread": thread["name"],
            "conversation": thread["conversation"],
            "action": "link",
            "reply": reply,
        }

    # 2. Greeting /start without token
    if clean_text == "/start":
        thread = get_or_create_thread(chat_id, from_user)
        if thread.get("linked_user"):
            reply = f"Halo {thread['linked_user']}! Anda terhubung sebagai karyawan. Ada yang bisa dibantu untuk urusan penjualan hari ini?"
        else:
            reply = "Halo! Selamat datang di layanan kami. Ada informasi barang atau katalog produk yang ingin Anda tanyakan?"
        telegram_client.send_message(chat_id, reply)
        return {
            "success": True,
            "thread": thread["name"],
            "conversation": thread["conversation"],
            "action": "start",
            "reply": reply,
        }

    # 3. Unlink command: /unlink
    if clean_text == "/unlink":
        from aios_v1.lib.connector.linking import unlink_thread

        thread = get_or_create_thread(chat_id, from_user)
        if thread.get("linked_user"):
            unlink_thread(chat_id)
            thread["linked_user"] = None
            reply = "Tautan akun Telegram telah diputuskan. Anda kini dilayani sebagai tamu."
        else:
            reply = "Chat Telegram ini belum tertaut ke akun karyawan mana pun."

        telegram_client.send_message(chat_id, reply)
        return {
            "success": True,
            "thread": thread["name"],
            "conversation": thread["conversation"],
            "action": "unlink",
            "reply": reply,
        }

    # 4. Standard message processing
    thread = get_or_create_thread(chat_id, from_user)
    conversation = thread["conversation"]
    effective_user = thread.get("linked_user") or "Guest"

    previous_user = frappe.session.user
    previous_channel = getattr(frappe.local, "aios_channel", None)
    previous_thread = getattr(frappe.local, "aios_channel_thread", None)
    frappe.set_user(effective_user)
    frappe.local.aios_channel = CHANNEL
    frappe.local.aios_channel_thread = thread
    try:
        telegram_client.send_chat_action(chat_id, "typing")

        try:
            reply = _collect_reply(get_manager(BRANCH), conversation, effective_user, text)
        except Exception as exc:
            log_exception("AIOS Connector Reply", exc=exc, context=f"thread={thread['name']}")
            reply = ""

        if not reply:
            reply = BUSY_REPLY
            doc = frappe.new_doc(MESSAGE_DOCTYPE)
            doc.conversation = conversation
            doc.role = "manager"
            doc.worker_key = "manager"
            doc.content = reply
            doc.insert(ignore_permissions=True)
            frappe.db.commit()

        telegram_client.send_message(chat_id, reply)

        message_name = _ensure_inbound_recorded(conversation, text)
        flags = _raise_flags(thread, text, message_name)

        frappe.db.set_value(
            THREAD_DOCTYPE,
            thread["name"],
            {"last_inbound_at": now_datetime(), "last_outbound_at": now_datetime()},
            update_modified=False,
        )
        frappe.db.commit()

        return {
            "success": True,
            "thread": thread["name"],
            "conversation": conversation,
            "flags": flags,
        }
    finally:
        frappe.set_user(previous_user)
        if previous_channel is None:
            if hasattr(frappe.local, "aios_channel"):
                delattr(frappe.local, "aios_channel")
        else:
            frappe.local.aios_channel = previous_channel
        if previous_thread is None:
            if hasattr(frappe.local, "aios_channel_thread"):
                delattr(frappe.local, "aios_channel_thread")
        else:
            frappe.local.aios_channel_thread = previous_thread


def process_update(update: dict) -> dict:
    """Route one update. Callback queries are intentionally ignored in v1."""
    if update.get("callback_query"):
        # Inline-keyboard checkout is out of scope for v1 (docs/02 §2.4).
        log_exception("AIOS Connector Callback Ignored", context=str(update.get("update_id")))
        return {"success": False, "code": "CONNECTOR_CALLBACK_IGNORED"}
    if update.get("message"):
        return process_message(update)
    return {"success": False, "code": "CONNECTOR_IGNORED"}


def health() -> dict:
    """Cheap read-only status for the poller and for tests."""
    try:
        config = telegram_client.get_config()
    except Exception as exc:
        log_exception("AIOS Connector Health", exc=exc)
        return safe_error("Konfigurasi kanal tidak terbaca.", "CONNECTOR_UNHEALTHY")
    return {
        "success": True,
        "channel": CHANNEL,
        "branch": BRANCH,
        "is_active": config["is_active"],
        "has_token": bool(config["bot_token"]),
        "owner_user": frappe.db.get_single_value(SETTING_DOCTYPE, "owner_user"),
        "offset": frappe.db.get_single_value(SETTING_DOCTYPE, "poll_offset") or 0,
    }


def audit_snapshot(thread_name: str) -> dict:
    """Deterministic audit numbers for one thread (read-only)."""
    thread = frappe.get_doc(THREAD_DOCTYPE, thread_name)
    return audit.summarize(thread.conversation)
