"""
Notifikasi in-app SPI berbasis Notification Log Frappe (lonceng di TopBar).
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.permissions import get_user_permissions
from frappe.utils import cint

DEFAULT_RECIPIENT_PROFILES = ("Finance", "CSO", "Marketing")


def branch_users(company: str, profiles=DEFAULT_RECIPIENT_PROFILES) -> list[str]:
	"""User aktif dengan role profile tertentu yang memiliki akses ke cabang (tanpa batasan cabang = semua cabang)."""
	users = frappe.get_all("User", filters={"enabled": 1, "role_profile_name": ["in", list(profiles)]}, pluck="name")
	result = []
	for user in users:
		perms = get_user_permissions(user).get("Company", [])
		if not perms or company in {p.get("doc") for p in perms}:
			result.append(user)
	return result


def notify_branch(
	company: str,
	subject: str,
	message: str = "",
	document_type: str | None = None,
	document_name: str | None = None,
	profiles=DEFAULT_RECIPIENT_PROFILES,
) -> list[str]:
	"""Membuat Notification Log untuk Finance & CSO cabang. Mengembalikan daftar penerima."""
	recipients = branch_users(company, profiles)
	for user in recipients:
		create_notification(user, subject, message, document_type, document_name)
	return recipients


def create_notification(
	user: str,
	subject: str,
	message: str = "",
	document_type: str | None = None,
	document_name: str | None = None,
	notification_type: str = "Alert",
) -> None:
	"""Satu Notification Log (lonceng TopBar). ``document_type`` dipakai SPA untuk menentukan halaman tujuan."""
	frappe.get_doc(
		{
			"doctype": "Notification Log",
			"for_user": user,
			"from_user": frappe.session.user,
			"type": notification_type,
			"subject": subject,
			"email_content": message,
			"document_type": document_type,
			"document_name": document_name,
		}
	).insert(ignore_permissions=True)


@frappe.whitelist(methods=["GET"])
def get_my_notifications(limit: int = 20) -> dict[str, Any]:
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Anda harus login."), frappe.PermissionError)
	items = frappe.get_all(
		"Notification Log",
		filters={"for_user": user},
		fields=["name", "subject", "email_content", "document_type", "document_name", "read", "creation"],
		order_by="creation desc",
		limit_page_length=min(cint(limit) or 20, 100),
	)
	return {"items": items, "unread": frappe.db.count("Notification Log", {"for_user": user, "read": 0})}


@frappe.whitelist(methods=["POST"])
def mark_notifications_read(names=None) -> dict[str, Any]:
	"""Tandai dibaca: daftar nama tertentu, atau semua bila kosong. Hanya notifikasi milik user sendiri."""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Anda harus login."), frappe.PermissionError)
	names = frappe.parse_json(names) if isinstance(names, str) else names
	filters: dict[str, Any] = {"for_user": user, "read": 0}
	if names:
		filters["name"] = ["in", names]
	for name in frappe.get_all("Notification Log", filters=filters, pluck="name"):
		frappe.db.set_value("Notification Log", name, "read", 1, update_modified=False)
	return {"unread": frappe.db.count("Notification Log", {"for_user": user, "read": 0})}
