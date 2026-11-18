"""
Mode tampilan SPA SPI (keputusan pemilik 6 Nov 2026):

- ``web``     : tampilan web (sidebar + halaman).
- ``desktop`` : tampilan seperti sistem operasi (desktop ber-ikon, taskbar, menu Start, halaman terbuka sebagai
  jendela). Sebelum login tampil animasi booting lalu layar login. Default (keputusan pemilik 6 Nov 2026).

Berlaku untuk seluruh pengguna; HANYA Super Administrator (user ``Administrator``) yang dapat mengubahnya.
Disimpan sebagai default global ``spi_ui_mode``.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

UI_MODE_KEY = "spi_ui_mode"
UI_MODES = ("web", "desktop")
DEFAULT_UI_MODE = "desktop"


def get_ui_mode() -> str:
	mode = frappe.db.get_default(UI_MODE_KEY)
	return mode if mode in UI_MODES else DEFAULT_UI_MODE


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_ui_settings() -> dict[str, Any]:
	"""Dibaca sebelum login (animasi booting mode desktop), jadi hanya berisi data non-rahasia."""
	return {"mode": get_ui_mode(), "modes": list(UI_MODES)}


@frappe.whitelist(methods=["POST"])
def set_ui_mode(mode: str) -> dict[str, Any]:
	if frappe.session.user != "Administrator":
		frappe.throw(_("Hanya admin yang dapat mengubah mode tampilan."), frappe.PermissionError)
	if mode not in UI_MODES:
		frappe.throw(_("Mode tampilan tidak dikenal: {0}").format(mode), frappe.ValidationError)
	frappe.db.set_default(UI_MODE_KEY, mode)
	return get_ui_settings()
