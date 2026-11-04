"""In-app notification for channel flags (docs/02 §2.4).

Reuses Frappe's own notification pipeline instead of inventing one:
`enqueue_create_notification` writes a `Notification Log` row (scoped to
`for_user` by Frappe's permission hooks) and `NotificationLog.after_insert`
publishes the realtime event and sends the email when the type allows it.

The bell is the contract; email is opportunistic (a client site may have no
outgoing Email Account, and `send_notification_email` then only logs).
"""

from __future__ import annotations

import json

import frappe

from aios_v1.lib.error_utils import log_exception

# A dedicated type keeps channel alerts separable from Desk mentions and lets
# users mute them through Notification Settings.
NOTIFICATION_TYPE = "AIOS Channel Alert"


def ensure_notification_type() -> str | None:
    """Create the notification type and seed per-user preferences (idempotent)."""
    if not frappe.db.exists("DocType", "Notification Type"):
        log_exception("AIOS Connector Notification", context="DocType Notification Type tidak ada")
        return None
    try:
        if not frappe.db.exists("Notification Type", NOTIFICATION_TYPE):
            doc = frappe.new_doc("Notification Type")
            doc.type_name = NOTIFICATION_TYPE
            doc.enabled = 1
            doc.insert(ignore_permissions=True)
        elif not frappe.db.get_value("Notification Type", NOTIFICATION_TYPE, "enabled"):
            frappe.db.set_value("Notification Type", NOTIFICATION_TYPE, "enabled", 1)
    except Exception as exc:
        log_exception("AIOS Connector Notification Type", exc=exc)
        return None

    # Email is opt-in per type through the user's `email_notification_types`
    # table; without a row the type never emails. Seed it for every user.
    try:
        from frappe.desk.doctype.notification_type.notification_type import (
            seed_type_into_settings,
        )

        seed_type_into_settings(NOTIFICATION_TYPE)
    except Exception as exc:
        log_exception("AIOS Connector Notification Seed", exc=exc)
    return NOTIFICATION_TYPE


def notify_flag(flag) -> bool:
    """Send one in-app notification to the flag owner. Never raises."""
    try:
        from frappe.desk.doctype.notification_log.notification_log import (
            enqueue_create_notification,
        )

        enqueue_create_notification(
            [flag.owner_user],
            {
                "type": NOTIFICATION_TYPE,
                "title": f"Percakapan perlu dicek: {flag.label or flag.rule_key}",
                "description": (
                    f"<p>{frappe.utils.escape_html(flag.excerpt or '')}</p>"
                    f"<p>Tingkat: {flag.severity}. Buka jendela percakapan untuk meninjau.</p>"
                ),
                "document_type": "AIOS Conversation Flag",
                "document_name": flag.name,
                "link": f"/flags/{flag.name}",
            },
            dedupe_on=["document_name"],
        )
        return True
    except Exception as exc:
        log_exception("AIOS Connector Notification", exc=exc, context=f"flag={flag.name}")
        return False


def notify_order_draft(draft, thread: dict | None = None) -> bool:
    """Send one in-app notification to the channel owner for an order draft. Never raises."""
    try:
        from frappe.desk.doctype.notification_log.notification_log import (
            enqueue_create_notification,
        )

        owner = frappe.db.get_single_value("AIOS Telegram Setting", "owner_user")
        if not owner:
            log_exception("AIOS Connector Order Notification", context="owner_user belum diisi")
            return False

        target_doctype = "Pesanan"
        if hasattr(draft, "payload") and draft.payload:
            try:
                parsed_payload = json.loads(draft.payload) if isinstance(draft.payload, str) else draft.payload
                target_doctype = parsed_payload.get("doctype") or "Pesanan"
            except (TypeError, ValueError) as exc:
                log_exception("AIOS Order Draft Payload Parse", exc=exc, context=str(getattr(draft, "name", "")))

        customer_label = ""
        if thread:
            customer_label = (thread.get("display_name") or "").strip()
            if not customer_label and thread.get("username"):
                customer_label = f"@{thread.get('username')}"
            if not customer_label and thread.get("external_thread_id"):
                customer_label = f"Chat ID {thread.get('external_thread_id')}"
        if not customer_label:
            customer_label = "Customer Telegram"

        creation_dt = getattr(draft, "creation", None) or frappe.utils.now_datetime()
        creation_str = frappe.utils.format_datetime(creation_dt)

        title = f"Draf Pesanan Baru: {target_doctype} - {customer_label}"
        description = (
            f"<p>Draf <b>{target_doctype}</b> baru dibuat oleh customer <b>{frappe.utils.escape_html(customer_label)}</b>.</p>"
            f"<p>Waktu dibuat: {creation_str}</p>"
            f"<p>Catatan customer mau beli yang menunggu tindak lanjut staf.</p>"
        )

        enqueue_create_notification(
            [owner],
            {
                "type": NOTIFICATION_TYPE,
                "title": title,
                "description": description,
                "document_type": "Pending Action Draft",
                "document_name": draft.name,
                "link": f"/desk#Form/Pending Action Draft/{draft.name}",
            },
            dedupe_on=["document_name"],
        )
        return True
    except Exception as exc:
        log_exception("AIOS Connector Order Notification", exc=exc, context=f"draft={getattr(draft, 'name', None)}")
        return False
