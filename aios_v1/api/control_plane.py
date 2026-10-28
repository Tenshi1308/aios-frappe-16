"""Dashboard API for the AIOS Admin on the developer site.

Semua endpoint di sini dipakai dashboard Vue (`/aios-admin`, folder `admin/`)
lewat sesi login Frappe — bukan token `AIOS Control` (itu jalur Control API di
site klien, `aios_v1.api.control`). Guard: Guest ditolak, `Administrator` boleh
(root Frappe, dipakai operator saat setup), selain itu wajib role `AIOS Admin`.

Setiap `except` tercatat lewat `log_exception` lalu kembalikan pesan aman;
`AuthenticationError`/`PermissionError` di-re-raise. Tidak ada `except: pass`.
"""

from __future__ import annotations

import frappe

from aios_v1.lib import control_client
from aios_v1.lib.error_utils import log_exception, safe_error, sanitize_text

_EXCLUDED_USERS = ("Administrator", "Guest")
_ADMIN_ROLE = "AIOS Admin"
# Field registry yang boleh tampil di dashboard; api_credential tidak pernah masuk.
_SITE_FIELDS = (
	"site_name",
	"base_url",
	"company_name",
	"contact_name",
	"contact_email",
	"status",
	"last_seen",
	"last_error",
)
_USER_FIELDS = ("name", "full_name", "aios_status", "aios_persona", "enabled", "last_login")
_METRIC_FIELDS = (
	"site_tokens_used",
	"site_token_limit",
	"active_users",
	"total_users",
	"tokens_today",
)


def _require_aios_admin() -> None:
	"""Require a logged-in AIOS Admin (Administrator is the Frappe root)."""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw("Sesi tidak ditemukan. Silakan login.", frappe.AuthenticationError)
	if user == "Administrator":
		return
	if _ADMIN_ROLE not in frappe.get_roles(user):
		frappe.throw("Akses ditolak.", frappe.PermissionError)


def _safe_error() -> dict:
	return safe_error("Terjadi kesalahan internal.", "CONTROL_PLANE_ERROR")


def _metric_int(metric: dict, field: str) -> int:
	try:
		return int(metric.get(field) or 0)
	except (TypeError, ValueError):
		# Nilai non-numerik dihitung 0 agar totals site lain tetap terisi.
		log_exception("AIOS Dashboard: metrics", context=f"Nilai {field} tidak numerik; dihitung 0.")
		return 0


@frappe.whitelist()
def dashboard():
	"""List every managed site with its users and metrics, plus totals."""
	_require_aios_admin()
	try:
		registry = frappe.get_all(
			"AIOS Managed Site",
			fields=list(_SITE_FIELDS),
			order_by="site_name asc",
			limit=0,
		)
		sites = []
		totals = {
			"sites": 0,
			"active_users": 0,
			"total_users": 0,
			"site_tokens_used": 0,
			"site_token_limit": 0,
			"tokens_today": 0,
		}
		for row in registry:
			site_name = row.site_name
			try:
				users_payload = control_client.users(site_name)
				metrics_payload = control_client.metrics(site_name)
			except Exception as exc:
				# Kegagalan satu site tidak boleh menjatuhkan site lain.
				log_exception("AIOS Dashboard: panggilan site gagal", exc=exc, context=f"site={site_name}")
				sites.append({**dict(row), "users": [], "metrics": None, "error": "Site klien tidak dapat dihubungi."})
				totals["sites"] += 1
				continue
			users = []
			metrics = None
			error = None
			if users_payload.get("success") is False:
				error = sanitize_text(users_payload.get("error"))
				log_exception(
					"AIOS Dashboard: users gagal",
					context=f"site={site_name} code={users_payload.get('code')}",
				)
			else:
				users = [
					{field: user.get(field) for field in _USER_FIELDS}
					for user in users_payload.get("users") or []
					if isinstance(user, dict)
				]
			if metrics_payload.get("success") is False:
				error = error or sanitize_text(metrics_payload.get("error"))
				log_exception(
					"AIOS Dashboard: metrics gagal",
					context=f"site={site_name} code={metrics_payload.get('code')}",
				)
			else:
				metrics = {field: _metric_int(metrics_payload, field) for field in _METRIC_FIELDS}
				totals["active_users"] += metrics["active_users"]
				totals["total_users"] += metrics["total_users"]
				totals["site_tokens_used"] += metrics["site_tokens_used"]
				totals["site_token_limit"] += metrics["site_token_limit"]
				totals["tokens_today"] += metrics["tokens_today"]
			sites.append({**dict(row), "users": users, "metrics": metrics, "error": error})
			totals["sites"] += 1
		return {"sites": sites, "totals": totals}
	except (frappe.AuthenticationError, frappe.PermissionError):
		raise
	except Exception as exc:
		log_exception("AIOS Dashboard: dashboard", exc=exc, context="dashboard")
		return _safe_error()


@frappe.whitelist(methods=["POST"])
def health_check(site: str):
	"""Run a manual health check and record the outcome in the registry."""
	_require_aios_admin()
	try:
		site_name = sanitize_text(site)[:140]
		if not frappe.db.exists("AIOS Managed Site", site_name):
			frappe.throw("Site klien tidak ditemukan di registry.", frappe.DoesNotExistError)
		payload = control_client.health(site_name)
		if payload.get("success") is False:
			error = sanitize_text(payload.get("error"))[:500]
			frappe.db.set_value("AIOS Managed Site", site_name, "last_error", error, update_modified=False)
			last_seen = frappe.db.get_value("AIOS Managed Site", site_name, "last_seen")
			return {"ok": False, "site": site_name, "last_seen": last_seen, "last_error": error}
		frappe.db.set_value(
			"AIOS Managed Site",
			site_name,
			{"last_seen": frappe.utils.now(), "last_error": None},
			update_modified=False,
		)
		return {"ok": True, "site": site_name, "last_seen": frappe.db.get_value("AIOS Managed Site", site_name, "last_seen"), "last_error": None}
	except (frappe.AuthenticationError, frappe.PermissionError, frappe.DoesNotExistError):
		raise
	except Exception as exc:
		log_exception("AIOS Dashboard: health_check", exc=exc, context=f"site={site}")
		return _safe_error()


@frappe.whitelist(methods=["POST"])
def set_user_status(site: str, user: str, status: str):
	"""Activate or suspend one user on a client site via the Control API."""
	_require_aios_admin()
	if status not in ("Active", "Suspended"):
		frappe.throw("Status harus Active atau Suspended.", frappe.ValidationError)
	try:
		site_name = sanitize_text(site)[:140]
		user_name = sanitize_text(user)[:140]
		if not frappe.db.exists("AIOS Managed Site", site_name):
			frappe.throw("Site klien tidak ditemukan di registry.", frappe.DoesNotExistError)
		payload = control_client.activate_user(site_name, user_name, status)
		return {"ok": bool(payload.get("ok")), "site": site_name, "user": user_name, "aios_status": payload.get("aios_status")}
	except (frappe.AuthenticationError, frappe.PermissionError, frappe.ValidationError, frappe.DoesNotExistError):
		raise
	except Exception as exc:
		log_exception("AIOS Dashboard: set_user_status", exc=exc, context=f"site={site}")
		return _safe_error()
