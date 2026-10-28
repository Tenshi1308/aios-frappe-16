"""Halaman shell dashboard AIOS Admin di /aios-admin (site developer).

Aset Vue di-build terpisah di folder `admin/` lalu dilayani dari
`aios_v1/public/admin/` lewat manifest Vite. Tanpa build, halaman tetap
menampilkan pesan aman — bukan traceback.
"""

from __future__ import annotations

import json

import frappe

from aios_v1.lib.error_utils import log_exception, sanitize_text

_ADMIN_ROLE = "AIOS Admin"
_APP_PUBLIC = "aios_v1/public/admin"
_ASSET_BASE = "/assets/aios_v1/admin"


def _admin_assets() -> tuple[str | None, str | None, str | None]:
	"""Read the Vite manifest and return (js_url, css_url, error_message)."""
	try:
		import os

		manifest_path = os.path.join(frappe.get_app_path("aios_v1"), "..", _APP_PUBLIC, "manifest.json")
		with open(manifest_path, encoding="utf-8") as file:
			manifest = json.load(file)
	except Exception as exc:
		log_exception("AIOS Admin: manifest tidak tersedia", exc=exc, context="aios-admin")
		return None, None, "Dashboard belum di-build. Jalankan build admin/ terlebih dahulu."

	entry = manifest.get("index.html") or {}
	js_file = entry.get("file")
	css_files = entry.get("css") or []
	js_url = f"{_ASSET_BASE}/{js_file}" if js_file else None
	css_url = f"{_ASSET_BASE}/{css_files[0]}" if css_files else None
	if not js_url:
		log_exception("AIOS Admin: manifest tanpa entry JS", context="aios-admin")
		return None, None, "Dashboard belum di-build. Jalankan build admin/ terlebih dahulu."
	return js_url, css_url, None


def get_context(context):
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/aios-admin"
		raise frappe.Redirect
	if user != "Administrator" and _ADMIN_ROLE not in frappe.get_roles(user):
		frappe.throw("Akses ditolak.", frappe.PermissionError)

	js_url, css_url, error = _admin_assets()
	context.admin_js = js_url
	context.admin_css = css_url
	context.admin_error = sanitize_text(error) if error else None
	context.no_cache = True
