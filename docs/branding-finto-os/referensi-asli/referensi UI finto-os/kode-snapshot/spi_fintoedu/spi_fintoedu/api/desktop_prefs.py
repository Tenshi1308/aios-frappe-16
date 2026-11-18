"""
Personalisasi mode desktop (Finto OS) PER PENGGUNA (keputusan pemilik 6 Nov 2026):
latar belakang desktop dipilih masing-masing user (preset bawaan atau gambar unggahan sendiri) dan tidak
terlihat/berpengaruh ke user lain.

Disimpan sebagai user default ``spi_desktop_wallpaper`` (JSON ``{"kind": "preset"|"image", "value": ...}``).
Gambar unggahan = File privat yang dilampirkan ke dokumen User miliknya (hanya pemilik yang dapat membuka).

Tata letak ikon (keputusan pemilik 12 Nov 2026): posisi ikon desktop dapat diatur (seret & lepas) per pengguna dan per
peran yang ditampilkan ("Lihat sebagai" punya ikon berbeda). User default ``spi_desktop_icon_layout`` (JSON
``{role: {app_key: [kolom, baris]}}``). Tanpa simpanan → urutan bawaan (Master Data dulu, jarak antar kategori; diatur
di frontend ``features/desktop/iconLayout.ts``).
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

WALLPAPER_KEY = "spi_desktop_wallpaper"
PRESETS = ("finto", "aurora", "sunset", "forest", "midnight", "ocean", "graphite", "sakura")
DEFAULT_WALLPAPER = {"kind": "preset", "value": "finto"}
ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
WALLPAPER_FIELD = "spi_desktop_wallpaper"  # penanda File wallpaper (attached_to_field)
ICON_LAYOUT_KEY = "spi_desktop_icon_layout"
MAX_LAYOUT_ICONS = 200
MAX_GRID_INDEX = 100


def _require_login() -> str:
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Anda harus login."), frappe.PermissionError)
	return user


def _load(user: str) -> dict[str, Any]:
	raw = frappe.defaults.get_user_default(WALLPAPER_KEY, user=user)
	try:
		data = json.loads(raw) if raw else None
	except (TypeError, ValueError):
		data = None
	if not isinstance(data, dict) or data.get("kind") not in ("preset", "image"):
		return dict(DEFAULT_WALLPAPER)
	if data["kind"] == "preset" and data.get("value") not in PRESETS:
		return dict(DEFAULT_WALLPAPER)
	if data["kind"] == "image":
		# file harus masih ada & milik user ini
		if not frappe.db.exists(
			"File", {"file_url": data.get("value"), "attached_to_doctype": "User", "attached_to_name": user}
		):
			return dict(DEFAULT_WALLPAPER)
	return {"kind": data["kind"], "value": data["value"]}


def _save(user: str, data: dict[str, Any]) -> None:
	frappe.defaults.set_user_default(WALLPAPER_KEY, json.dumps(data), user=user)


def _load_layouts(user: str) -> dict[str, dict[str, list[int]]]:
	raw = frappe.defaults.get_user_default(ICON_LAYOUT_KEY, user=user)
	try:
		data = json.loads(raw) if raw else {}
	except (TypeError, ValueError):
		data = {}
	return data if isinstance(data, dict) else {}


def _clean_layout(layout) -> dict[str, list[int]]:
	if isinstance(layout, str):
		layout = json.loads(layout or "{}")
	if not isinstance(layout, dict) or len(layout) > MAX_LAYOUT_ICONS:
		frappe.throw(_("Tata letak ikon tidak valid."), frappe.ValidationError)
	clean: dict[str, list[int]] = {}
	seen: set[tuple[int, int]] = set()
	for key, pos in layout.items():
		if not isinstance(key, str) or len(key) > 140 or not isinstance(pos, (list, tuple)) or len(pos) != 2:
			frappe.throw(_("Tata letak ikon tidak valid."), frappe.ValidationError)
		col, row = int(pos[0]), int(pos[1])
		if not (0 <= col <= MAX_GRID_INDEX and 0 <= row <= MAX_GRID_INDEX) or (col, row) in seen:
			frappe.throw(_("Posisi ikon tidak valid atau bertumpuk."), frappe.ValidationError)
		seen.add((col, row))
		clean[key] = [col, row]
	return clean


@frappe.whitelist(methods=["GET"])
def get_desktop_prefs() -> dict[str, Any]:
	user = _require_login()
	return {"wallpaper": _load(user), "presets": list(PRESETS), "icon_layouts": _load_layouts(user)}


@frappe.whitelist(methods=["POST"])
def set_icon_layout(role: str, layout) -> dict[str, Any]:
	"""Simpan posisi ikon desktop untuk peran ``role`` (kunci tampilan; bukan hak akses)."""
	user = _require_login()
	role = (role or "default")[:80]
	layouts = _load_layouts(user)
	layouts[role] = _clean_layout(layout)
	frappe.defaults.set_user_default(ICON_LAYOUT_KEY, json.dumps(layouts), user=user)
	return {"icon_layouts": layouts}


@frappe.whitelist(methods=["POST"])
def reset_icon_layout(role: str) -> dict[str, Any]:
	"""Kembali ke susunan bawaan (Master Data dulu, jarak antar kategori)."""
	user = _require_login()
	layouts = _load_layouts(user)
	layouts.pop((role or "default")[:80], None)
	frappe.defaults.set_user_default(ICON_LAYOUT_KEY, json.dumps(layouts), user=user)
	return {"icon_layouts": layouts}


@frappe.whitelist(methods=["POST"])
def set_wallpaper_preset(preset: str) -> dict[str, Any]:
	user = _require_login()
	if preset not in PRESETS:
		frappe.throw(_("Latar belakang tidak dikenal."), frappe.ValidationError)
	_save(user, {"kind": "preset", "value": preset})
	_delete_uploaded(user)
	return get_desktop_prefs()


@frappe.whitelist(methods=["POST"])
def upload_wallpaper() -> dict[str, Any]:
	"""Unggah gambar latar sendiri (multipart ``file``). JPG/PNG/WEBP maks. 5 MB; menggantikan unggahan sebelumnya."""
	user = _require_login()
	files = getattr(frappe.request, "files", None) or {}
	upload = files.get("file")
	if not upload:
		frappe.throw(_("Pilih berkas gambar."), frappe.ValidationError)
	filename = upload.filename or "wallpaper"
	ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
	if ext not in ALLOWED_IMAGE_EXT:
		frappe.throw(_("Format gambar harus JPG, PNG, atau WEBP."), frappe.ValidationError)
	content = upload.stream.read()
	if not content:
		frappe.throw(_("Berkas kosong."), frappe.ValidationError)
	if len(content) > MAX_IMAGE_BYTES:
		frappe.throw(_("Ukuran gambar maksimal 5 MB."), frappe.ValidationError)
	if not _looks_like_image(content, ext):
		frappe.throw(_("Isi berkas bukan gambar yang valid."), frappe.ValidationError)
	return _store_image(user, filename, content)


def _store_image(user: str, filename: str, content: bytes) -> dict[str, Any]:
	_delete_uploaded(user)
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"wallpaper-{frappe.generate_hash(length=6)}-{filename}",
			"attached_to_doctype": "User",
			"attached_to_name": user,
			"attached_to_field": WALLPAPER_FIELD,
			"is_private": 1,
			"content": content,
		}
	)
	file_doc.flags.ignore_permissions = True
	file_doc.insert()
	_save(user, {"kind": "image", "value": file_doc.file_url})
	return get_desktop_prefs()


@frappe.whitelist(methods=["POST"])
def reset_wallpaper() -> dict[str, Any]:
	user = _require_login()
	_delete_uploaded(user)
	_save(user, dict(DEFAULT_WALLPAPER))
	return get_desktop_prefs()


def _delete_uploaded(user: str) -> None:
	for name in frappe.get_all(
		"File",
		filters={"attached_to_doctype": "User", "attached_to_name": user, "attached_to_field": WALLPAPER_FIELD},
		pluck="name",
	):
		frappe.delete_doc("File", name, ignore_permissions=True, force=True)


def _looks_like_image(content: bytes, ext: str) -> bool:
	head = content[:16]
	if ext in ("jpg", "jpeg"):
		return head.startswith(b"\xff\xd8\xff")
	if ext == "png":
		return head.startswith(b"\x89PNG\r\n\x1a\n")
	if ext == "webp":
		return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
	return False
