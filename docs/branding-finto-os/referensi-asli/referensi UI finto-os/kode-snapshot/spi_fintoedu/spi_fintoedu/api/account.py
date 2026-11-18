"""
Akun pengguna: ganti password sendiri dari SPA.

User hasil migrasi memakai password awal yang sama (keputusan pemilik 8 Nov 2026) dan ditandai
`User.custom_must_change_password`; SPA menampilkan jendela "Ganti Password" yang wajib diisi sampai
password diganti. Validasi kekuatan password memakai kebijakan Frappe (System Settings).
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, today

MUST_CHANGE_FIELD = "custom_must_change_password"


@frappe.whitelist(methods=["GET"])
def get_password_status() -> dict[str, Any]:
	user = frappe.session.user
	if user == "Guest" or not frappe.get_meta("User").has_field(MUST_CHANGE_FIELD):
		return {"must_change": False}
	return {"must_change": bool(cint(frappe.db.get_value("User", user, MUST_CHANGE_FIELD)))}


@frappe.whitelist(methods=["POST"])
def change_my_password(old_password: str, new_password: str) -> dict[str, Any]:
	from frappe.core.doctype.user.user import _update_password, handle_password_test_fail, test_password_strength
	from frappe.utils.password import check_password

	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Silakan login terlebih dahulu."), frappe.PermissionError)
	if not old_password or not new_password:
		frappe.throw(_("Password lama dan password baru wajib diisi."))
	if old_password == new_password:
		frappe.throw(_("Password baru harus berbeda dari password lama."))
	try:
		check_password(user, old_password)
	except frappe.AuthenticationError:
		frappe.clear_messages()
		frappe.throw(_("Password lama salah."))
	result = test_password_strength(new_password)
	feedback = result.get("feedback") or {}
	if feedback and not feedback.get("password_policy_validation_passed", False):
		handle_password_test_fail(feedback)
	_update_password(user, new_password, logout_all_sessions=0)
	values = {"last_password_reset_date": today()}
	if frappe.get_meta("User").has_field(MUST_CHANGE_FIELD):
		values[MUST_CHANGE_FIELD] = 0
	frappe.db.set_value("User", user, values, update_modified=False)
	return {"ok": True}
