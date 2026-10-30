"""Registrasi klien AIOS di atas `Lead` bawaan ERPNext (docs/00-poc-target.md §1.1).

Pendaftar dicatat sebagai `Lead` (`utm_source = "AIOS Signup"`) di site developer.
Akun `User` baru dibuat saat penyiapan site (langkah 3), dan password dibuat
oleh client sendiri saat aktivasi (langkah 4-5).
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import validate_email_address

from aios_v1.lib.error_utils import log_exception

SITE_ROLE_KEY = "aios_site_role"
DEVELOPER_ROLE_VALUE = "developer"
UTM_SOURCE_NAME = "AIOS Signup"
GENERIC_PENDING_RESPONSE = {"status": "PENDING_PROVISIONING"}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=30, seconds=60)
def list_countries() -> list[str]:
    """Daftar nama negara resmi Frappe untuk opsi dropdown form registrasi."""
    return frappe.get_all("Country", pluck="name", order_by="name asc")


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=5, seconds=60)
def register_account(full_name: str, email: str, company_name: str, country: str):
    """Daftarkan calon klien sebagai `Lead` di site developer."""
    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()
    company_name = (company_name or "").strip()
    country = (country or "").strip()

    if not full_name or not email or not company_name or not country:
        frappe.throw(
            _("Nama lengkap, email, nama perusahaan, dan negara wajib diisi"),
            frappe.ValidationError,
        )

    validate_email_address(email, throw=True)

    # Guard: registrasi hanya diizinkan di site developer
    site_role = frappe.conf.get(SITE_ROLE_KEY)
    if site_role != DEVELOPER_ROLE_VALUE:
        frappe.throw(
            _("Pendaftaran mandiri hanya dapat dilakukan melalui portal pengembang."),
            frappe.PermissionError,
        )

    if not frappe.db.exists("Country", country):
        frappe.throw(
            _("Negara '{0}' tidak ditemukan di sistem").format(country),
            frappe.ValidationError,
        )

    # Anti-enumerasi: email yang sudah terdaftar memberi respons yang sama
    if frappe.db.exists("Lead", {"email_id": email}):
        return GENERIC_PENDING_RESPONSE

    lead = frappe.new_doc("Lead")
    lead.first_name = full_name
    lead.lead_name = full_name
    lead.email_id = email
    lead.company_name = company_name
    lead.country = country
    lead.utm_source = UTM_SOURCE_NAME

    try:
        lead.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError as exc:
        log_exception("AIOS Auth: email duplikat saat registrasi Lead", exc=exc)
        return GENERIC_PENDING_RESPONSE
    except frappe.ValidationError as exc:
        msg = str(exc).lower()
        if "unique" in msg or "already used" in msg:
            log_exception("AIOS Auth: validasi duplikat email Lead", exc=exc)
            return GENERIC_PENDING_RESPONSE
        raise

    return GENERIC_PENDING_RESPONSE
