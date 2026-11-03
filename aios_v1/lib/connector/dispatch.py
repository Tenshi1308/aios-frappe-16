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
    """Return the thread for this chat, creating conversation + thread once."""
    external_id = str(chat_id)
    name = frappe.db.get_value(
        THREAD_DOCTYPE,
        {"channel": CHANNEL, "external_thread_id": external_id},
        "name",
    )
    if name:
        return frappe.get_doc(THREAD_DOCTYPE, name).as_dict()

    owner = _owner_user()
    conversation = str(get_manager(BRANCH).ensure_conversation(owner))
    info = user_info or {}
    doc = frappe.new_doc(THREAD_DOCTYPE)
    doc.channel = CHANNEL
    doc.external_thread_id = external_id
    doc.conversation = conversation
    doc.owner_user = owner
    doc.display_name = " ".join(
        part for part in (info.get("first_name"), info.get("last_name")) if part
    ).strip()
    doc.username = info.get("username") or ""
    doc.status = "Open"
    doc.insert(ignore_permissions=True)
    return doc.as_dict()


def _collect_reply(manager, conversation: str, owner: str, text: str) -> str:
    """Drain the manager stream and keep only the answer text.

    SSE framing is stripped: the connector is a text channel, so trace and
    artifact events are not forwarded. The manager persists both messages and
    records token usage itself, so nothing is written twice here.
    """
    chunks: list[str] = []
    for raw in manager.handle_stream(
        user_message=text,
        conversation_id=conversation,
        user=owner,
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

    previous_user = frappe.session.user
    frappe.set_user(owner)
    try:
        thread = get_or_create_thread(chat_id, from_user)
        conversation = thread["conversation"]

        telegram_client.send_chat_action(chat_id, "typing")

        try:
            reply = _collect_reply(get_manager(BRANCH), conversation, owner, text)
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
