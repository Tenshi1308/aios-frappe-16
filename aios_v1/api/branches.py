"""Whitelisted API resmi Frappe untuk katalog cabang publik Ekasa Desk.

Migrasi Fase 1 dari `GET /api/branches` (dispatcher kustom) ke
`GET /api/method/aios_v1.api.branches.list_branches`.

Sesi login, CSRF, dan penolakan tamu ditangani seragam oleh Frappe:
- `@frappe.whitelist(methods=["GET"])` tanpa `allow_guest` -> tamu ditolak
  403 (`frappe/__init__.py::is_whitelisted`).
- `frappe.session.user` diisi dari cookie `sid` oleh `HTTPRequest`.
"""

import frappe

from aios_v1.plugin_manager.registry import get_public_branches


@frappe.whitelist(methods=["GET"])
def list_branches() -> dict:
    """Katalog cabang publik, sudah diproyeksikan ke field tampilan saja.

    `get_public_branches()` (registry) sudah membuang `manager_persona` dan
    materi prompt internal worker; proyeksi itu dipertahankan apa adanya.
    """
    return {"branches": get_public_branches()}
