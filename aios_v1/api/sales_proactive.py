"""Whitelisted API endpoints for Stage 1 Sales proactive insights & Desk heartbeat."""

from __future__ import annotations

import frappe

from aios_v1.lib.error_utils import log_exception
from aios_v1.lib.sales_proactive import (
    DETECTOR_KEYS,
    INSIGHT_LOG_DOCTYPE,
    SALES_BRANCH,
    default_detector_settings,
    get_detector_settings,
    record_desk_heartbeat,
    run_daily_sales_proactive_scan,
    run_detector_scheduler_dispatch,
)


def _require_authenticated_user() -> str:
    user = getattr(frappe.session, "user", None)
    if not user or user == "Guest":
        frappe.throw("Autentikasi diperlukan.", frappe.PermissionError)
    return str(user)


def _assert_admin_or_owner(user: str) -> None:
    if user == "Administrator":
        return
    roles = set(frappe.get_roles(user))
    if not (roles & {"System Manager", "AIOS Admin", "AIOS Client Owner"}):
        frappe.throw("Hanya admin atau owner yang dapat memicu pemindaian proaktif manual.", frappe.PermissionError)


@frappe.whitelist()
def trigger_sales_proactive_scan() -> dict:
    """Manual trigger (Admin/Owner) equivalent to Get Alerts for Today for live verification."""
    user = _require_authenticated_user()
    _assert_admin_or_owner(user)
    try:
        return run_daily_sales_proactive_scan()
    except Exception as exc:
        log_exception("AIOS Sales Proactive Manual Trigger", exc=exc, context=f"user={user}")
        frappe.throw("Pemindaian proaktif Sales gagal dijalankan. Silakan periksa Error Log.")


@frappe.whitelist()
def heartbeat() -> dict:
    """Lightweight Desk presence ping (no LLM, no AI token cost)."""
    user = _require_authenticated_user()
    ts = record_desk_heartbeat(user)
    return {"status": "ok", "timestamp": ts}


@frappe.whitelist()
def get_unread_sales_insights() -> dict:
    """Return unread Desk proactive insight count and latest sales conversation id for current user."""
    user = _require_authenticated_user()
    unread_count = frappe.db.count(
        INSIGHT_LOG_DOCTYPE,
        {
            "recipient_user": user,
            "status": "SENT_DESK",
            "is_read": 0,
        },
    )
    latest_conv = frappe.db.get_value(
        "AIOS Conversation",
        {"user": user, "branch": SALES_BRANCH, "is_archived": 0},
        "name",
        order_by="modified desc",
    )
    return {
        "unread_count": int(unread_count or 0),
        "conversation_id": str(latest_conv) if latest_conv else None,
    }


@frappe.whitelist()
def mark_sales_insights_read() -> dict:
    """Clear unread badge after user opens the Sales branch conversation."""
    user = _require_authenticated_user()
    unread_names = frappe.get_all(
        INSIGHT_LOG_DOCTYPE,
        filters={"recipient_user": user, "status": "SENT_DESK", "is_read": 0},
        pluck="name",
    )
    for name in unread_names:
        frappe.db.set_value(INSIGHT_LOG_DOCTYPE, name, "is_read", 1)
    if unread_names and not frappe.flags.in_test:
        frappe.db.commit()
    return {"status": "ok", "marked": len(unread_names)}


@frappe.whitelist()
def get_detector_schedules() -> dict:
    """Return per-detector schedules for the Insight Proaktif settings tab (K9)."""
    _require_authenticated_user()
    rows = get_detector_settings()
    if not rows:
        rows = default_detector_settings()
    return {
        "detectors": [
            {
                "detector_key": str(row.get("detector_key") or ""),
                "label": str(row.get("label") or ""),
                "enabled": int(row.get("enabled") or 0),
                "frequency": str(row.get("frequency") or "daily"),
                "run_hour": int(row.get("run_hour") or 0),
                "day_of_week": str(row.get("day_of_week") or ""),
            }
            for row in rows
        ],
        "frequencies": ["daily", "weekly", "monthly"],
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    }


@frappe.whitelist(methods=["POST"])
def save_detector_schedules(detectors=None) -> dict:
    """Persist per-detector schedules so Desk can change them without deploy (K9)."""
    user = _require_authenticated_user()
    _assert_admin_or_owner(user)
    try:
        payload = frappe.parse_json(detectors) if isinstance(detectors, str) else detectors
        if not isinstance(payload, list) or not payload:
            frappe.throw("Daftar detektor wajib diisi.", frappe.ValidationError)

        doc = frappe.get_single("AIOS Proactive Detector Setting")
        doc.set("detectors", [])
        for row in payload:
            if not isinstance(row, dict):
                frappe.throw("Setiap baris detektor harus berupa object.", frappe.ValidationError)
            key = str(row.get("detector_key") or "").strip()
            if key not in DETECTOR_KEYS:
                frappe.throw(f"Detektor tidak dikenal: {key}", frappe.ValidationError)
            doc.append(
                "detectors",
                {
                    "detector_key": key,
                    "label": str(row.get("label") or key),
                    "enabled": 1 if int(row.get("enabled") or 0) else 0,
                    "frequency": str(row.get("frequency") or "daily"),
                    "run_hour": int(row.get("run_hour") or 0),
                    "day_of_week": str(row.get("day_of_week") or ""),
                },
            )
        doc.flags.ignore_permissions = True
        doc.save(ignore_permissions=True)
        return {"status": "ok", "saved": len(payload)}
    except (frappe.AuthenticationError, frappe.PermissionError, frappe.ValidationError):
        raise
    except Exception as exc:
        log_exception("AIOS Detector Schedule Save", exc=exc, context=f"user={user}")
        frappe.throw("Jadwal detektor gagal disimpan. Silakan periksa Error Log.")


@frappe.whitelist()
def run_detector_dispatch_now() -> dict:
    """Manual 'jalankan sekarang' for the scheduler dispatcher (admin/owner only)."""
    user = _require_authenticated_user()
    _assert_admin_or_owner(user)
    try:
        return run_detector_scheduler_dispatch()
    except Exception as exc:
        log_exception("AIOS Detector Dispatch Manual", exc=exc, context=f"user={user}")
        frappe.throw("Dispatcher detektor gagal dijalankan. Silakan periksa Error Log.")
