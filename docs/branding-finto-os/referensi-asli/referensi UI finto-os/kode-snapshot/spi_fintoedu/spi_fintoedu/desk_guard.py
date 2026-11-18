"""Restrict the ERPNext/Frappe Desk (``/app`` and ``/desk``) to the Super Administrator.

Policy (owner decision, Nov 2026): only the ``Administrator`` user is the Super
Administrator and may open the Desk. Every other logged-in user — including
other System Managers — is sent to the SPI SPA instead. API calls (``/api/*``)
are not affected, so the SPA keeps working for every role.

The SPA URL comes from site config key ``spi_frontend_url`` (falls back to ``/``).
"""

import frappe
from werkzeug.routing import RequestRedirect

SUPER_ADMINISTRATOR = "Administrator"
DESK_PREFIXES = ("app", "desk")


class _DeskRedirect(RequestRedirect):
	code = 302


def is_desk_path(path: str | None) -> bool:
	first_segment = (path or "").strip("/").split("/", 1)[0]
	return first_segment in DESK_PREFIXES


def can_access_desk(user: str | None) -> bool:
	return user == SUPER_ADMINISTRATOR


def get_frontend_url() -> str:
	return (frappe.conf.get("spi_frontend_url") or "/").rstrip("/") or "/"


def block_desk_for_non_super_admin():
	"""``before_request`` hook."""
	request = getattr(frappe.local, "request", None)
	if not request or not is_desk_path(request.path):
		return

	user = frappe.session.user if getattr(frappe.local, "session", None) else None
	# Guests are handled by Frappe itself (redirect to /login).
	if not user or user == "Guest" or can_access_desk(user):
		return

	raise _DeskRedirect(get_frontend_url())
