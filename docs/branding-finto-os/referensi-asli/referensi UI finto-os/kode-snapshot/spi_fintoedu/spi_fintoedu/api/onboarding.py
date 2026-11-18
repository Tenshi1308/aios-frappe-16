"""
Status wizard panduan (onboarding) per user.

SPA menampilkan wizard selamat datang saat user pertama kali login dan wizard
panduan halaman saat user pertama kali membuka sebuah menu. Kunci panduan yang
sudah dilihat disimpan sebagai user default ``spi_seen_guides`` (JSON list),
jadi status ikut berpindah perangkat/browser.
"""

from __future__ import annotations

import json
import re
from typing import Any

import frappe
from frappe import _

DEFAULT_KEY = "spi_seen_guides"
WELCOME_GUIDE = "welcome"
GUIDE_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,79}$")
MAX_KEYS = 200


def _require_login() -> str:
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Anda harus login."), frappe.PermissionError)
	return user


def _load(user: str) -> list[str]:
	raw = frappe.defaults.get_user_default(DEFAULT_KEY, user=user)
	if not raw:
		return []
	try:
		keys = json.loads(raw)
	except (TypeError, ValueError):
		return []
	return [k for k in keys if isinstance(k, str)] if isinstance(keys, list) else []


def _save(user: str, keys: list[str]) -> None:
	frappe.defaults.set_user_default(DEFAULT_KEY, json.dumps(keys[-MAX_KEYS:]), user=user)


@frappe.whitelist(methods=["GET"])
def get_onboarding_state() -> dict[str, Any]:
	user = _require_login()
	seen = _load(user)
	return {"seen": seen, "welcome_done": WELCOME_GUIDE in seen}


@frappe.whitelist(methods=["POST"])
def mark_guide_seen(key: str) -> dict[str, Any]:
	user = _require_login()
	key = (key or "").strip()
	if not GUIDE_KEY_PATTERN.match(key):
		frappe.throw(_("Kunci panduan tidak valid."), frappe.ValidationError)
	seen = _load(user)
	if key not in seen:
		seen.append(key)
		_save(user, seen)
	return {"seen": seen, "welcome_done": WELCOME_GUIDE in seen}


@frappe.whitelist(methods=["POST"])
def reset_guides() -> dict[str, Any]:
	"""Tampilkan ulang semua wizard panduan untuk user ini."""
	user = _require_login()
	_save(user, [])
	return {"seen": [], "welcome_done": False}
