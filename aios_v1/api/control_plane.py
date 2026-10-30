"""Dashboard API for the AIOS Admin on the developer site.

Semua endpoint di sini dipakai dashboard Vue (`/aios-admin`, folder `admin/`)
lewat sesi login Frappe — bukan token `AIOS Control` (itu jalur Control API di
site klien, `aios_v1.api.control`). Guard: Guest ditolak, `Administrator` boleh
(root Frappe, dipakai operator saat setup), selain itu wajib role `AIOS Admin`.

Setiap `except` tercatat lewat `log_exception` lalu kembalikan pesan aman;
`AuthenticationError`/`PermissionError` di-re-raise. Tidak ada `except: pass`.
"""

from __future__ import annotations

from math import ceil
from urllib.parse import urlsplit, urlunsplit

import frappe

from aios_v1.lib import control_client
from aios_v1.lib.error_utils import log_exception, safe_error, sanitize_text

_EXCLUDED_USERS = ("Administrator", "Guest")
_ADMIN_ROLE = "AIOS Admin"
_THEME_OPTIONS = ("Automatic", "Light", "Dark")
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
	"pending_users",
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


def _bounded_int(value, default, minimum, maximum=None):
	"""Paginasi: nilai tidak valid → default, lalu di-clamp ke rentang."""
	if isinstance(value, int) and not isinstance(value, bool):
		parsed = value
	elif isinstance(value, float):
		parsed = int(value)
	elif isinstance(value, str):
		val = value.strip()
		if val.isdigit() or (val.startswith("-") and val[1:].isdigit()):
			parsed = int(val)
		else:
			parsed = default
	else:
		parsed = default
	parsed = max(minimum, parsed)
	if maximum is not None:
		parsed = min(maximum, parsed)
	return parsed


def _metric_int(metric: dict, field: str) -> int:
	try:
		return int(metric.get(field) or 0)
	except (TypeError, ValueError):
		# Nilai non-numerik dihitung 0 agar totals site lain tetap terisi.
		log_exception("AIOS Dashboard: metrics", context=f"Nilai {field} tidak numerik; dihitung 0.")
		return 0


def _theme_payload() -> dict:
	raw = frappe.db.get_value("User", frappe.session.user, "desk_theme")
	value = raw if raw in _THEME_OPTIONS else "Automatic"
	return {"value": value, "options": list(_THEME_OPTIONS)}


@frappe.whitelist()
def dashboard(page=1, page_size=20):
	"""List every managed site with its metrics, plus pagination."""
	_require_aios_admin()
	try:
		page = _bounded_int(page, default=1, minimum=1)
		page_size = _bounded_int(page_size, default=20, minimum=1, maximum=100)
		registry = frappe.get_all(
			"AIOS Managed Site",
			fields=list(_SITE_FIELDS),
			order_by="site_name asc",
			offset=(page - 1) * page_size,
			limit=page_size,
		)
		total = frappe.db.count("AIOS Managed Site")
		sites = []
		for row in registry:
			site_name = row.site_name
			try:
				metrics_payload = control_client.metrics(site_name)
			except Exception as exc:
				# Kegagalan satu site tidak boleh menjatuhkan site lain.
				log_exception("AIOS Dashboard: panggilan site gagal", exc=exc, context=f"site={site_name}")
				sites.append({**dict(row), "metrics": None, "error": "Site klien tidak dapat dihubungi."})
				continue
			metrics = None
			error = None
			if metrics_payload.get("success") is False:
				error = sanitize_text(metrics_payload.get("error"))
				log_exception(
					"AIOS Dashboard: metrics gagal",
					context=f"site={site_name} code={metrics_payload.get('code')}",
				)
			else:
				metrics = {field: _metric_int(metrics_payload, field) for field in _METRIC_FIELDS}
			sites.append({**dict(row), "metrics": metrics, "error": error})

		return {
			"sites": sites,
			"pagination": {
				"page": page,
				"page_size": page_size,
				"total": total,
				"total_pages": max(1, ceil(total / page_size)),
			},
			"theme": _theme_payload(),
		}
	except (frappe.AuthenticationError, frappe.PermissionError):
		raise
	except Exception as exc:
		log_exception("AIOS Dashboard: dashboard", exc=exc, context="dashboard")
		return _safe_error()


@frappe.whitelist()
def users_page(site: str, page=1, page_size=20, status=None):
	"""Return a paginated list of users for one managed site."""
	_require_aios_admin()
	site_name = sanitize_text(site)[:140]
	if not frappe.db.exists("AIOS Managed Site", site_name):
		frappe.throw("Site klien tidak ditemukan di registry.", frappe.DoesNotExistError)
	if status is not None and status != "":
		if status not in ("Pending Provisioning", "Active", "Suspended"):
			frappe.throw("Status tidak valid.", frappe.ValidationError)
	else:
		status = None
	page = _bounded_int(page, default=1, minimum=1)
	page_size = _bounded_int(page_size, default=20, minimum=1, maximum=100)
	try:
		payload = control_client.users(site_name, status=status, page=page, page_size=page_size)
		if payload.get("success") is False:
			error = sanitize_text(payload.get("error"))
			log_exception(
				"AIOS Dashboard: users_page gagal",
				context=f"site={site_name} code={payload.get('code')}",
			)
			return {
				"users": [],
				"total": 0,
				"page": page,
				"page_size": page_size,
				"total_pages": 1,
				"error": error,
			}
		total = int(payload.get("total") or 0)
		users = [
			{field: u.get(field) for field in _USER_FIELDS}
			for u in payload.get("users") or []
			if isinstance(u, dict)
		]
		return {
			"site": site_name,
			"users": users,
			"total": total,
			"page": page,
			"page_size": page_size,
			"total_pages": max(1, ceil(total / page_size)),
			"error": None,
		}
	except (frappe.AuthenticationError, frappe.PermissionError, frappe.DoesNotExistError, frappe.ValidationError):
		raise
	except Exception as exc:
		log_exception("AIOS Dashboard: users_page", exc=exc, context=f"site={site}")
		return _safe_error()


@frappe.whitelist()
def totals():
	"""Aggregate metrics across every managed site."""
	_require_aios_admin()
	try:
		registry = frappe.get_all(
			"AIOS Managed Site",
			fields=["site_name"],
			order_by="site_name asc",
			limit=0,
		)
		total = len(registry)
		totals_data = {
			"sites": 0,
			"active_users": 0,
			"total_users": 0,
			"pending_users": 0,
			"site_tokens_used": 0,
			"site_token_limit": 0,
			"tokens_today": 0,
			"sites_unreachable": 0,
		}
		# ponytail: totals() sweep sekuensial O(N) HTTP (timeout 10s/call).
		# Ceiling: ratusan site bikin request menit-an. Upgrade: simpan
		# snapshot metrics di registry saat health check, totals() jumlahkan
		# snapshot (1 query).
		for row in registry:
			site_name = row.site_name
			try:
				metrics_payload = control_client.metrics(site_name)
			except Exception as exc:
				log_exception("AIOS Dashboard: totals metrics gagal", exc=exc, context=f"site={site_name}")
				totals_data["sites_unreachable"] += 1
				continue
			if metrics_payload.get("success") is False:
				log_exception(
					"AIOS Dashboard: totals metrics gagal",
					context=f"site={site_name} code={metrics_payload.get('code')}",
				)
				totals_data["sites_unreachable"] += 1
				continue
			totals_data["sites"] += 1
			for field in (
				"active_users",
				"total_users",
				"pending_users",
				"site_tokens_used",
				"site_token_limit",
				"tokens_today",
			):
				totals_data[field] += _metric_int(metrics_payload, field)
		return {
			"totals": totals_data,
			"sites_total": total,
			"sites_scanned": total,
		}
	except (frappe.AuthenticationError, frappe.PermissionError):
		raise
	except Exception as exc:
		log_exception("AIOS Dashboard: totals", exc=exc, context="totals")
		return _safe_error()


@frappe.whitelist()
def pending_inbox(site_page=1, site_page_size=20):
	"""Collect pending users across client sites, paginated by site."""
	_require_aios_admin()
	try:
		site_page = _bounded_int(site_page, default=1, minimum=1)
		site_page_size = _bounded_int(site_page_size, default=20, minimum=1, maximum=100)
		registry = frappe.get_all(
			"AIOS Managed Site",
			fields=["site_name"],
			order_by="site_name asc",
			offset=(site_page - 1) * site_page_size,
			limit=site_page_size,
		)
		sites_total = frappe.db.count("AIOS Managed Site")
		sites_scanned = len(registry)
		total_pending = 0
		entries = []
		partial = False

		for row in registry:
			site_name = row.site_name
			site_users = []
			loop_page = 1
			max_loops = 10
			site_partial = False

			while loop_page <= max_loops:
				try:
					payload = control_client.users(
						site_name,
						status="Pending Provisioning",
						page=loop_page,
						page_size=100,
					)
				except Exception as exc:
					log_exception("AIOS Dashboard: pending_inbox users gagal", exc=exc, context=f"site={site_name}")
					break

				if payload.get("success") is False:
					log_exception(
						"AIOS Dashboard: pending_inbox users gagal",
						context=f"site={site_name} code={payload.get('code')}",
					)
					break

				users_raw = payload.get("users") or []
				site_users.extend(
					[
						{field: u.get(field) for field in _USER_FIELDS}
						for u in users_raw
						if isinstance(u, dict)
					]
				)
				client_total = int(payload.get("total") or 0)
				if len(site_users) >= client_total or len(users_raw) < 100:
					break

				loop_page += 1
				if loop_page > max_loops:
					site_partial = True

			if site_partial:
				partial = True

			pending_count = len(site_users)
			if pending_count > 0:
				total_pending += pending_count
				entries.append({
					"site": site_name,
					"pending_users": pending_count,
					"users": site_users,
				})

		return {
			"site_page": site_page,
			"site_page_size": site_page_size,
			"sites_total": sites_total,
			"sites_scanned": sites_scanned,
			"total_pending": total_pending,
			"entries": entries,
			"partial": partial,
			"error": None,
		}
	except (frappe.AuthenticationError, frappe.PermissionError):
		raise
	except Exception as exc:
		log_exception("AIOS Dashboard: pending_inbox", exc=exc, context="pending_inbox")
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
		raw_url = payload.get("invitation_url")
		invitation_url = raw_url
		if raw_url:
			base_url = frappe.db.get_value("AIOS Managed Site", site_name, "base_url") or ""
			if base_url:
				parsed = urlsplit(raw_url)
				base = urlsplit(base_url)
				invitation_url = urlunsplit((base.scheme, base.netloc, parsed.path, parsed.query, ""))
		return {
			"ok": bool(payload.get("ok")),
			"site": site_name,
			"user": user_name,
			"aios_status": payload.get("aios_status"),
			"invitation_url": invitation_url,
		}
	except (frappe.AuthenticationError, frappe.PermissionError, frappe.ValidationError, frappe.DoesNotExistError):
		raise
	except Exception as exc:
		log_exception("AIOS Dashboard: set_user_status", exc=exc, context=f"site={site}")
		return _safe_error()


@frappe.whitelist()
def signup_leads():
	"""Daftar pendaftar calon klien pra-site untuk AIOS Admin (Langkah 3 Flow Utama)."""
	frappe.only_for(_ADMIN_ROLE)
	from aios_v1.setup import UTM_SOURCE_SIGNUP

	leads = frappe.get_all(
		"Lead",
		filters={"utm_source": UTM_SOURCE_SIGNUP},
		fields=["name", "lead_name", "first_name", "email_id", "company_name", "country", "creation"],
		order_by="creation desc",
	)

	managed_sites = frappe.get_all(
		"AIOS Managed Site",
		fields=["site_name", "contact_email", "company_name", "status"],
	)

	sites_by_email = {}
	sites_by_company = {}
	for site in managed_sites:
		c_email = (site.get("contact_email") or "").strip().lower()
		c_company = (site.get("company_name") or "").strip().lower()
		if c_email and c_email not in sites_by_email:
			sites_by_email[c_email] = site
		if c_company and c_company not in sites_by_company:
			sites_by_company[c_company] = site

	enriched = []
	for lead in leads:
		email = (lead.get("email_id") or "").strip().lower()
		company = (lead.get("company_name") or "").strip().lower()
		matched = sites_by_email.get(email) or sites_by_company.get(company)

		status = "Menunggu Penyiapan Site"
		site_name = None
		if matched:
			site_name = matched.get("site_name")
			site_status = matched.get("status")
			if site_status == "Active":
				status = "Site Siap"
			elif site_status == "Provisioning":
				status = "Sedang Disiapkan"
			else:
				status = f"Site {site_status}"

		lead_dict = dict(lead)
		lead_dict["status"] = status
		lead_dict["site_name"] = site_name
		enriched.append(lead_dict)

	return enriched

