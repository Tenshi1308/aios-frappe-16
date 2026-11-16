"""Whitelisted API resmi Frappe untuk Peringatan Kanal / channel connector.

Migrasi Fase 1 dari dispatcher kustom `/api/connector/*` ke
`/api/method/aios_v1.api.connector.*` (keputusan Ten, Opsi A). Menjadi jalan
masuk Tunggal untuk jendela Peringatan Kanal yang sebelumnya 401 setelah
refresh akibat sesi `sid` rusak.

Nama method dikunci Ten: `list_threads`, `list_flags`, `close_flag`,
`list_orders`, `review_order`, `create_link_token`, `get_link_status`,
`unlink_telegram`.

Ketentuan:
- `@frappe.whitelist(methods=[...])` TANPA `allow_guest`; tamu ditolak 403
  oleh `frappe/__init__.py::is_whitelisted` (kontrak 401 -> 403).
- `frappe.session.user` dibaca langsung (cookie `sid` + CSRF bawaan Frappe).
- Isolasi data tetap memakai `_require_user` / `_can_access_channel_doc`
  (`views.py:27-38`) lewat fungsi `views.py` yang sama seperti sebelumnya.
- `WorkspaceError` (status kustom lama) dipetakan ke exception resmi Frappe
  sehingga tidak ada lagi 401 kustom; pesan tetap aman tanpa detail internal.
"""

import math

import frappe

from aios_v1.lib.connector import views
from aios_v1.lib.connector.linking import LinkError, unlink_by_user
from aios_v1.lib.connector.linking import create_link_token as _create_link_token
from aios_v1.lib.connector.linking import get_link_status as _get_link_status
from aios_v1.lib.error_utils import log_exception
from aios_v1.lib.workspace import WorkspaceError


def _current_user() -> str:
    """User aktif dari sesi Frappe; tamu ditolak 403 (bukan 401 kustom)."""
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw("Belum login.", frappe.PermissionError)
    return str(user)


def _body() -> dict:
    """Body JSON POST (frontend `use_json_request_body = True`).

    Aman dipanggil di luar konteks HTTP (mis. pemanggilan langsung dari tes):
    tanpa `frappe.request`, kembalikan dict kosong dan biarkan parameter
    method yang menentukan nilai.
    """
    request = getattr(frappe.local, "request", None)
    if request is None:
        return {}
    data = request.get_json(force=True, silent=True) or {}
    return data if isinstance(data, dict) else {}


def _map_workspace_error(exc: WorkspaceError, context: str) -> None:
    """Petakan `WorkspaceError` ke exception resmi + catat ke Error Log."""
    log_exception(context, exc=exc, context=exc.code)
    if exc.status in (401, 403):
        frappe.throw(exc.message, frappe.PermissionError)
    if exc.status == 404:
        frappe.throw(exc.message, frappe.DoesNotExistError)
    frappe.throw(exc.message, frappe.ValidationError)


# ---------------------------------------------------------------------------
# GET /api/method/aios_v1.api.connector.list_threads
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def list_threads() -> list:
    """Daftar thread kanal yang boleh dilihat user (read-only)."""
    user = _current_user()
    return views.list_threads(user)


# ---------------------------------------------------------------------------
# GET /api/method/aios_v1.api.connector.list_flags
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def list_flags(status: str | None = None) -> dict:
    """Daftar flag kanal + total, difilter `Open`/`Closed` bila valid."""
    user = _current_user()
    clean_status = status if status in ("Open", "Closed") else None
    flags = views.list_flags(user, status=clean_status)
    total = views.count_flags(user, status=clean_status)
    return {"flags": flags, "total": total}


# ---------------------------------------------------------------------------
# POST /api/method/aios_v1.api.connector.close_flag
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def close_flag(flag: str = "", note: str = "") -> dict:
    """Tandai flag sudah ditinjau (write, idempotent)."""
    user = _current_user()
    body = _body()
    flag = str(flag or body.get("flag") or "")
    note = str(note or body.get("note") or "")
    try:
        return views.close_flag(user, flag, note)
    except WorkspaceError as exc:
        _map_workspace_error(exc, "AIOS Connector Flag Close")
        raise  # `_map_workspace_error` selalu melempar; eksplisit untuk audit


# ---------------------------------------------------------------------------
# GET /api/method/aios_v1.api.connector.list_orders
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def list_orders(page: str | int = 1, unread: str | int | None = None) -> dict:
    """Daftar notifikasi draf pesanan dengan paginasi (read-only)."""
    user = _current_user()
    raw_page = page
    clean_page = str(raw_page).strip() if raw_page is not None else ""
    digits = clean_page[1:] if clean_page.startswith(("+", "-")) else clean_page
    page_num = max(1, int(clean_page)) if digits.isascii() and digits.isdigit() else 1

    unread_only = True
    if unread is not None:
        unread_only = str(unread).lower() in ("1", "true")

    page_length = 20
    total = views.count_orders(user, unread_only=unread_only)
    total_pages = max(1, math.ceil(total / page_length)) if total > 0 else 1
    orders = views.list_orders(
        user, unread_only=unread_only, page=page_num, page_length=page_length
    )
    return {
        "orders": orders,
        "total": total,
        "page": page_num,
        "page_length": page_length,
        "total_pages": total_pages,
    }


# ---------------------------------------------------------------------------
# POST /api/method/aios_v1.api.connector.review_order
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def review_order(notification_id: str = "") -> dict:
    """Tandai notifikasi pesanan sudah ditinjau (write)."""
    user = _current_user()
    body = _body()
    notification_id = str(notification_id or body.get("notification_id") or "")
    try:
        return views.review_order(user, notification_id)
    except WorkspaceError as exc:
        _map_workspace_error(exc, "AIOS Connector Order Review")
        raise  # `_map_workspace_error` selalu melempar; eksplisit untuk audit


# ---------------------------------------------------------------------------
# POST /api/method/aios_v1.api.connector.create_link_token
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def create_link_token() -> dict:
    """Buat deep-link token sekali pakai untuk akun sendiri."""
    user = _current_user()
    body = _body()
    requested_user = body.get("user")
    if requested_user and requested_user != user:
        frappe.throw(
            "Akses ditolak: hanya dapat membuat tautan untuk akun sendiri.",
            frappe.PermissionError,
        )
    try:
        return _create_link_token(user)
    except LinkError as exc:
        log_exception("AIOS Connector Link Token", exc=exc, context=exc.code)
        frappe.throw(exc.message, frappe.ValidationError)
    except frappe.PermissionError:
        raise


# ---------------------------------------------------------------------------
# GET /api/method/aios_v1.api.connector.get_link_status
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def get_link_status() -> dict:
    """Status tautan Telegram akun sendiri (read-only)."""
    user = _current_user()
    return _get_link_status(user)


# ---------------------------------------------------------------------------
# POST /api/method/aios_v1.api.connector.unlink_telegram
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def unlink_telegram() -> dict:
    """Putuskan tautan Telegram akun sendiri (write) lalu sinkronkan daftar perintah tamu."""
    user = _current_user()
    success = unlink_by_user(user)
    return {"success": success}
