"""Registrasi klien AIOS di atas `User` Frappe.

Alur sesuai docs/04 Alur 1: user baru masuk `Pending Provisioning`, `enabled = 0`,
tanpa email reset password, dan tanpa auto-login.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import validate_email_address

from aios_v1.lib.error_utils import log_exception


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=5, seconds=60)
def register_account(full_name: str, email: str, password: str, company_name: str):
    """Daftarkan calon klien sebagai `User` berstatus `Pending Provisioning`."""
    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()
    company_name = (company_name or "").strip()

    if not full_name or not email or not password or not company_name:
        frappe.throw(
            _("Nama lengkap, email, password, dan nama perusahaan wajib diisi"),
            frappe.ValidationError,
        )

    validate_email_address(email, throw=True)

    if len(password) < 8:
        frappe.throw(_("Password minimal 8 karakter"), frappe.ValidationError)

    generic = {"status": "PENDING_PROVISIONING"}

    # Anti-enumerasi: email yang sudah terdaftar memberi respons yang sama.
    if frappe.db.exists("User", email):
        return generic

    user = frappe.new_doc("User")
    user.email = email
    user.first_name = full_name
    user.new_password = password
    user.user_type = "Website User"
    user.send_welcome_email = 0
    user.flags.no_welcome_mail = True
    user.enabled = 0
    user.append("role_profiles", {"role_profile": "AIOS Client Profile"})
    user.aios_status = "Pending Provisioning"
    user.aios_persona = "executive"
    user.aios_company_name = company_name
    user.aios_tokens_used = 0

    if frappe.get_meta("AIOS Setting").has_field("default_user_token_limit"):
        token_limit = frappe.db.get_single_value("AIOS Setting", "default_user_token_limit")
        if token_limit:
            user.aios_token_limit = token_limit

    try:
        user.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError as exc:
        # Balapan dua request dengan email sama: tetap respons seragam.
        log_exception("AIOS Auth: email duplikat saat registrasi", exc=exc)
        return generic

    return generic
