import re
from urllib.parse import urlsplit

import frappe
from frappe.model.document import Document

SITE_NAME_PATTERN = re.compile(
	r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$"
)
LOCAL_HOST_PATTERN = re.compile(
	r"^(?:localhost|(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+localhost|127\.0\.0\.1)$",
	re.IGNORECASE,
)


class AIOSManagedSite(Document):
	"""Enforce provisionable hostnames and reserve plain HTTP for loopback development endpoints."""

	def validate(self):
		if not self.site_name or not SITE_NAME_PATTERN.fullmatch(self.site_name):
			frappe.throw("Site name must be a lowercase hostname with at least one dot.")

		try:
			parsed_url = urlsplit(self.base_url or "")
			hostname = parsed_url.hostname
			parsed_url.port
		except ValueError as exc:
			from aios_v1.lib.error_utils import log_exception

			log_exception(title="AIOS Managed Site", exc=exc, context="validate base_url")
			frappe.throw("Base URL must be a valid HTTP or HTTPS URL.")

		if parsed_url.scheme not in ("http", "https") or not hostname:
			frappe.throw("Base URL must be a valid HTTP or HTTPS URL.")

		if parsed_url.scheme != "https" and not LOCAL_HOST_PATTERN.fullmatch(hostname):
			frappe.throw("Base URL must use HTTPS except for local hosts.")
