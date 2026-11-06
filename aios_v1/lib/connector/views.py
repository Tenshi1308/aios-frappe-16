"""Read/close endpoints for channel threads and flags.

Every function takes the caller's user explicitly and scopes by `owner_user`;
`AIOS Client` can only see their own workspace's channel traffic. Closing a flag
is the human review step — there is no API path that reopens it automatically.
"""

from __future__ import annotations

import json

import frappe
from frappe.utils import now_datetime

from aios_v1.lib.connector.audit import summarize
from aios_v1.lib.connector.notify import get_channel_recipients
from aios_v1.lib.error_utils import log_exception
from aios_v1.lib.workspace import WorkspaceError

THREAD_DOCTYPE = "AIOS Channel Thread"
FLAG_DOCTYPE = "AIOS Conversation Flag"
CONVERSATION_DOCTYPE = "AIOS Conversation"

MAX_LIMIT = 100


def _require_user(user: str) -> str:
    if not user or user == "Guest":
        raise WorkspaceError(401, "NOT_LOGGED_IN", "Belum login.")
    return user


def _can_access_channel_doc(user: str, doc_owner: str | None = None) -> bool:
    if user == "Administrator" or "AIOS Admin" in set(frappe.get_roles(user)):
        return True
    if doc_owner and doc_owner == user:
        return True
    return user in set(get_channel_recipients())


def list_threads(user: str, limit: int = 50) -> list[dict]:
    """Threads visible to channel recipient or owned by `user`, newest activity first."""
    user = _require_user(user)
    limit = max(1, min(int(limit or 50), MAX_LIMIT))
    filters: dict = {}
    if not _can_access_channel_doc(user):
        filters["owner"] = user
    rows = frappe.get_all(
        THREAD_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "channel",
            "external_thread_id",
            "conversation",
            "display_name",
            "username",
            "party_type",
            "party",
            "status",
            "last_inbound_at",
            "last_outbound_at",
        ],
        order_by="last_inbound_at desc",
        limit_page_length=limit,
    )
    return rows


def count_flags(user: str, status: str | None = None) -> int:
    """Count flags visible to channel recipient or owned by `user`; `status` narrows to Open/Closed."""
    user = _require_user(user)
    filters: dict = {}
    if not _can_access_channel_doc(user):
        filters["owner"] = user
    if status in ("Open", "Closed"):
        filters["status"] = status
    return int(frappe.db.count(FLAG_DOCTYPE, filters=filters) or 0)


def list_flags(user: str, status: str | None = None, limit: int = 50) -> list[dict]:
    """Flags visible to channel recipient or owned by `user`, newest first; `status` narrows to Open/Closed."""
    user = _require_user(user)
    limit = max(1, min(int(limit or 50), MAX_LIMIT))
    filters: dict = {}
    if not _can_access_channel_doc(user):
        filters["owner"] = user
    if status in ("Open", "Closed"):
        filters["status"] = status
    return frappe.get_all(
        FLAG_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "thread",
            "conversation",
            "rule_key",
            "severity",
            "status",
            "label",
            "excerpt",
            "message_ids",
            "reason_text",
            "creation",
            "closed_by",
            "closed_at",
            "closing_note",
        ],
        order_by="creation desc",
        limit_page_length=limit,
    )


def close_flag(user: str, flag_id: str | None, note: str = "") -> dict:
    """Mark a flag reviewed. Recipient/owner-only; idempotent for an already-closed flag."""
    user = _require_user(user)
    if not flag_id:
        raise WorkspaceError(400, "FLAG_REQUIRED", "Flag wajib dipilih.")
    if not frappe.db.exists(FLAG_DOCTYPE, flag_id):
        raise WorkspaceError(404, "FLAG_NOT_FOUND", "Flag tidak ditemukan.")

    doc = frappe.get_doc(FLAG_DOCTYPE, flag_id)
    if not _can_access_channel_doc(user, doc.owner):
        raise WorkspaceError(404, "FLAG_NOT_FOUND", "Flag tidak ditemukan.")
    if doc.status == "Closed":
        return {
            "success": True,
            "flag": doc.name,
            "status": doc.status,
            "closed_by": doc.closed_by,
            "closed_at": doc.closed_at,
        }

    try:
        doc.status = "Closed"
        doc.closing_note = (note or "").strip()[:500]
        doc.closed_by = user
        doc.closed_at = now_datetime()
        doc.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception as exc:
        frappe.db.rollback()
        log_exception("AIOS Connector Flag Close", exc=exc, context=flag_id)
        raise WorkspaceError(500, "FLAG_CLOSE_FAILED", "Gagal menutup flag.") from exc

    return {
        "success": True,
        "flag": doc.name,
        "status": doc.status,
        "closed_by": doc.closed_by,
        "closed_at": doc.closed_at,
    }


def thread_audit(user: str, thread_id: str) -> dict:
    """Deterministic audit snapshot for one visible thread."""
    user = _require_user(user)
    if not thread_id or not frappe.db.exists(THREAD_DOCTYPE, thread_id):
        raise WorkspaceError(404, "THREAD_NOT_FOUND", "Percakapan tidak ditemukan.")
    thread = frappe.get_doc(THREAD_DOCTYPE, thread_id)
    if not _can_access_channel_doc(user, thread.owner):
        raise WorkspaceError(404, "THREAD_NOT_FOUND", "Percakapan tidak ditemukan.")
    return {"thread": thread.name, "audit": summarize(thread.conversation)}


def count_orders(user: str, unread_only: bool = True) -> int:
    """Count order notifications for `user`."""
    user = _require_user(user)
    filters: dict = {
        "for_user": user,
        "type": "AIOS Channel Alert",
        "document_type": "Pending Action Draft",
    }
    if unread_only:
        filters["read"] = 0
    return int(frappe.db.count("Notification Log", filters=filters) or 0)


def list_orders(
    user: str,
    unread_only: bool = True,
    limit: int | None = None,
    page: int = 1,
    page_length: int = 20,
) -> list[dict]:
    """Order notifications for `user`, newest first."""
    user = _require_user(user)
    page = max(1, int(page or 1))
    page_length = 20
    limit_start = (page - 1) * page_length
    limit_page_length = page_length

    if limit is not None:
        limit_page_length = max(1, min(int(limit), MAX_LIMIT))
        limit_start = 0

    filters: dict = {
        "for_user": user,
        "type": "AIOS Channel Alert",
        "document_type": "Pending Action Draft",
    }
    if unread_only:
        filters["read"] = 0

    rows = frappe.get_all(
        "Notification Log",
        filters=filters,
        fields=["name", "document_name", "subject", "email_content", "read", "creation"],
        order_by="creation desc",
        limit_start=limit_start,
        limit_page_length=limit_page_length,
    )

    orders: list[dict] = []
    for r in rows:
        draft_id = r.get("document_name") or ""
        doctype = "Sales Order"
        customer_name = ""
        if draft_id and frappe.db.exists("Pending Action Draft", draft_id):
            raw_payload = frappe.db.get_value("Pending Action Draft", draft_id, "payload")
            if raw_payload:
                try:
                    p = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
                    doctype = p.get("doctype") or "Sales Order"
                except Exception as exc:
                    log_exception("AIOS Views list_orders: JSON parse error", exc=exc)

        subject = r.get("subject") or ""
        if " - " in subject:
            customer_name = subject.split(" - ", 1)[1].strip()
        elif not customer_name:
            customer_name = "Customer Telegram"

        orders.append({
            "name": r["name"],
            "draft_id": draft_id,
            "doctype": doctype,
            "customer_name": customer_name,
            "subject": subject,
            "creation": r["creation"],
            "read": r.get("read") or 0,
        })
    return orders


def review_order(user: str, notification_id: str | None) -> dict:
    """Mark an order notification as reviewed (read = 1)."""
    user = _require_user(user)
    if not notification_id:
        raise WorkspaceError(400, "NOTIFICATION_REQUIRED", "Notifikasi wajib dipilih.")
    if not frappe.db.exists("Notification Log", notification_id):
        raise WorkspaceError(404, "NOTIFICATION_NOT_FOUND", "Notifikasi tidak ditemukan.")

    doc = frappe.get_doc("Notification Log", notification_id)
    if doc.for_user != user:
        raise WorkspaceError(404, "NOTIFICATION_NOT_FOUND", "Notifikasi tidak ditemukan.")

    if doc.read:
        return {"success": True, "notification_id": doc.name, "read": 1}

    try:
        doc.read = 1
        doc.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception as exc:
        frappe.db.rollback()
        log_exception("AIOS Connector Order Review", exc=exc, context=notification_id)
        raise WorkspaceError(500, "ORDER_REVIEW_FAILED", "Gagal meninjau pesanan.") from exc

    return {"success": True, "notification_id": doc.name, "read": 1}
