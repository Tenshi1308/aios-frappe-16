"""Token-guarded API for the developer control plane."""

from __future__ import annotations

import frappe

from aios_v1.lib.error_utils import log_exception, safe_error, sanitize_text

_EXCLUDED_USERS = ("Administrator", "Guest")
_USER_FIELDS = ("name", "full_name", "aios_status", "aios_persona", "enabled", "last_login")
_CLIENT_ROLE = "AIOS Client"


def _require_control_token() -> None:
	"""Require a Frappe token-authenticated AIOS Control user."""
	authorization = frappe.get_request_header("Authorization") or ""
	if not authorization.lower().startswith("token "):
		frappe.throw("Endpoint ini hanya untuk akses token.", frappe.PermissionError)

	user = frappe.session.user
	if not user or user in _EXCLUDED_USERS:
		frappe.throw("Akses ditolak.", frappe.PermissionError)
	if "AIOS Control" not in frappe.get_roles(user):
		frappe.throw("Akses ditolak.", frappe.PermissionError)


def _audit(action: str, **fields) -> None:
	"""Write a sanitized audit entry through Frappe's site logger."""
	values = [("action", action), ("user", frappe.session.user), *fields.items()]
	message = " ".join(f"{sanitize_text(key)}={sanitize_text(value)}" for key, value in values)
	frappe.logger("aios_control", allow_site=True).info(message)


def _safe_error() -> dict:
	return safe_error("Terjadi kesalahan internal.", "CONTROL_API_ERROR")


def _bounded_int(value, default: int, minimum: int, maximum: int | None = None) -> int:
	try:
		parsed = int(value)
	except (TypeError, ValueError):
		log_exception("AIOS Control API: pagination", context="Invalid integer; default value used.")
		parsed = default
	parsed = max(minimum, parsed)
	if maximum is not None:
		parsed = min(maximum, parsed)
	return parsed


def _client_role_names() -> list[str]:
	"""Return users carrying the client role; the filter is fixed, not a parameter."""
	return frappe.get_all(
		"Has Role",
		filters={"parenttype": "User", "role": _CLIENT_ROLE},
		pluck="parent",
		limit=0,
	)


def _client_user_filters(status=None) -> list:
	filters = [
		["User", "name", "not in", list(_EXCLUDED_USERS)],
		["User", "name", "in", _client_role_names()],
	]
	if status is not None:
		filters.append(["User", "aios_status", "=", status])
	return filters


@frappe.whitelist(methods=["GET"])
def health():
	_require_control_token()
	try:
		payload = {
			"status": "ok",
			"site": frappe.local.site,
			"time": frappe.utils.now(),
			"version": frappe.get_attr("aios_v1.__version__"),
		}
		_audit("health")
		return payload
	except Exception as exc:
		log_exception("AIOS Control API: health", exc=exc, context="health")
		return _safe_error()


@frappe.whitelist(methods=["GET"])
def users(status=None, page=1, page_size=50):
	_require_control_token()
	try:
		page = _bounded_int(page, default=1, minimum=1)
		page_size = _bounded_int(page_size, default=50, minimum=1, maximum=100)
		filters = _client_user_filters(status)
		rows = frappe.get_list(
			"User",
			filters=filters,
			fields=list(_USER_FIELDS),
			order_by="name asc",
			limit_start=(page - 1) * page_size,
			limit=page_size,
		)
		payload = {
			"users": [dict(row) for row in rows],
			"total": frappe.db.count("User", filters=filters),
			"page": page,
			"page_size": page_size,
		}
		_audit("users", page=page, page_size=page_size)
		return payload
	except Exception as exc:
		log_exception("AIOS Control API: users", exc=exc, context="users")
		return _safe_error()


@frappe.whitelist(methods=["POST"])
def activate_user(user: str, status: str):
	_require_control_token()
	if status not in ("Active", "Suspended"):
		frappe.throw("Status harus Active atau Suspended.", frappe.ValidationError)

	try:
		if user in _EXCLUDED_USERS:
			_audit("activate_user_rejected", target=user, reason="excluded_user")
			frappe.throw("User tidak ditemukan atau tidak dapat diubah.", frappe.ValidationError)
		if not frappe.db.exists("User", user):
			_audit("activate_user_rejected", target=user, reason="user_not_found")
			frappe.throw("User tidak ditemukan atau tidak dapat diubah.", frappe.ValidationError)
		if _CLIENT_ROLE not in frappe.get_roles(user):
			_audit("activate_user_rejected", target=user, reason="not_aios_client")
			frappe.throw("User tidak ditemukan atau tidak dapat diubah.", frappe.ValidationError)

		frappe.db.set_value(
			"User",
			user,
			{"aios_status": status, "enabled": 1 if status == "Active" else 0},
		)
		_audit("activate_user", target=user, status=status)
		return {"ok": True, "user": user, "aios_status": status}
	except (frappe.PermissionError, frappe.ValidationError):
		raise
	except Exception as exc:
		log_exception("AIOS Control API: activate_user", exc=exc, context="activate_user")
		return _safe_error()


@frappe.whitelist(methods=["GET"])
def metrics():
	_require_control_token()
	try:
		today = frappe.utils.today()
		tomorrow = frappe.utils.add_days(today, 1)
		token_totals = frappe.get_list(
			"AIOS Token Usage",
			filters=[
				["AIOS Token Usage", "creation", ">=", f"{today} 00:00:00"],
				["AIOS Token Usage", "creation", "<", f"{tomorrow} 00:00:00"],
			],
			fields=[{"SUM": "total_tokens", "as": "tokens_today"}],
			limit=1,
		)
		payload = {
			"site_tokens_used": int(frappe.db.get_single_value("AIOS Setting", "site_tokens_used") or 0),
			"site_token_limit": int(frappe.db.get_single_value("AIOS Setting", "site_token_limit") or 0),
			"active_users": frappe.db.count("User", filters=_client_user_filters("Active")),
			"total_users": frappe.db.count("User", filters=_client_user_filters()),
			"tokens_today": int((token_totals[0].get("tokens_today") if token_totals else 0) or 0),
		}
		_audit("metrics")
		return payload
	except Exception as exc:
		log_exception("AIOS Control API: metrics", exc=exc, context="metrics")
		return _safe_error()
