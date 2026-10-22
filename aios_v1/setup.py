"""Setup identitas Frappe AIOS.

Custom Field `User`, Role, dan Role Profile didaftarkan lewat hook
`after_install` / `after_migrate` di hooks.py memakai `create_custom_fields`
(API resmi Frappe; dipakai ERPNext sendiri di setup/install.py).
Tidak memakai fixtures dan tidak memutasi `tabDocField`.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

USER_CUSTOM_FIELDS = {
    "User": [
        {
            "fieldname": "aios_persona",
            "fieldtype": "Select",
            "label": "AIOS Persona",
            "options": "\nexecutive\nfinance\nsales\noperations\nsystem",
            "default": "executive",
            "insert_after": "username",
        },
        {
            "fieldname": "aios_persona_context",
            "fieldtype": "Small Text",
            "label": "AIOS Persona Context",
            "insert_after": "aios_persona",
        },
        {
            "fieldname": "aios_status",
            "fieldtype": "Select",
            "label": "AIOS Status",
            "options": "\nPending Provisioning\nActive\nSuspended",
            "default": None,
            "insert_after": "aios_persona_context",
        },
        {
            "fieldname": "aios_company_name",
            "fieldtype": "Data",
            "label": "AIOS Company Name",
            "insert_after": "aios_status",
        },
        {
            "fieldname": "aios_token_limit",
            "fieldtype": "Int",
            "label": "AIOS Token Limit",
            "insert_after": "aios_company_name",
        },
        {
            "fieldname": "aios_tokens_used",
            "fieldtype": "Int",
            "label": "AIOS Tokens Used",
            "read_only": 1,
            "insert_after": "aios_token_limit",
        },
    ]
}

AIOS_ROLES = {
    "AIOS Control": 0,
    "AIOS Client": 0,
}

AIOS_ROLE_PROFILES = {
    "AIOS Client Profile": ["AIOS Client"],
}


def after_install():
    setup_aios_identity()


def after_migrate():
    setup_aios_identity()


def setup_aios_identity():
    create_custom_fields(USER_CUSTOM_FIELDS, update=True)
    frappe.clear_cache(doctype="User")
    frappe.db.updatedb("User")
    _ensure_roles()
    _ensure_role_profiles()
    _ensure_aios_permissions()
    frappe.clear_cache()


def _ensure_aios_permissions():
    from aios_v1.permissions import ensure_aios_permissions

    ensure_aios_permissions()


def _ensure_roles():
    for role_name, desk_access in AIOS_ROLES.items():
        if frappe.db.exists("Role", role_name):
            role = frappe.get_doc("Role", role_name)
        else:
            role = frappe.new_doc("Role")
            role.role_name = role_name
        role.desk_access = desk_access
        role.save(ignore_permissions=True)

    # Role lama dari site yang pernah memakai AIOS Admin: jangan biarkan
    # punya akses Desk. Role ini hanya untuk control plane di #11.
    if frappe.db.exists("Role", "AIOS Admin"):
        frappe.db.set_value("Role", "AIOS Admin", "desk_access", 0)


def _ensure_role_profiles():
    for profile_name, roles in AIOS_ROLE_PROFILES.items():
        if frappe.db.exists("Role Profile", profile_name):
            profile = frappe.get_doc("Role Profile", profile_name)
        else:
            profile = frappe.new_doc("Role Profile")
            profile.role_profile = profile_name
        profile.set("roles", [])
        for role_name in roles:
            profile.append("roles", {"role": role_name})
        profile.save(ignore_permissions=True)


def _is_aios_user(user: str) -> bool:
    # Administrator adalah puncak tertinggi dan tidak pernah dibatasi AIOS.
    if not user or user in ("Guest", "Administrator"):
        return False
    roles = set(frappe.get_roles(user))
    return bool({"AIOS Admin", "AIOS Client"} & roles)


def sync_aios_status_enabled(doc, method=None):
    """User.validate: `aios_status` adalah sumber kebenaran; `enabled` mengikuti.

    Hanya berlaku untuk user ber-role AIOS. Administrator dan user Frappe lain
    tidak boleh ikut di-disable.
    """
    if doc.name == "Administrator":
        return
    status = doc.get("aios_status")
    if not status:
        return
    roles = {row.role for row in (doc.get("roles") or [])}
    if not ({"AIOS Admin", "AIOS Client"} & roles):
        return
    doc.enabled = 1 if status == "Active" else 0


def on_login(login_manager):
    """Hook on_login: tolak user AIOS yang belum Active."""
    user = login_manager.user
    if not user or user == "Guest":
        return
    if not _is_aios_user(user):
        return
    status = frappe.db.get_value("User", user, "aios_status")
    if status and status != "Active":
        raise frappe.AuthenticationError("Akun belum aktif")


def validate_aios_status():
    """Hook auth_hooks: tolak sesi AIOS yang statusnya bukan Active."""
    user = frappe.session.user
    if not user or user == "Guest":
        return
    if not _is_aios_user(user):
        return
    status = frappe.db.get_value("User", user, "aios_status")
    if status and status != "Active":
        raise frappe.AuthenticationError("Akun belum aktif")


@frappe.whitelist()
def get_session_context():
    """Bootstrap sesi untuk frontend: user, role, persona, kuota, company, CSRF."""
    from frappe.sessions import get_csrf_token

    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw("Belum login", frappe.AuthenticationError)

    user_doc = frappe.db.get_value(
        "User",
        user,
        [
            "full_name",
            "aios_persona",
            "aios_status",
            "aios_token_limit",
            "aios_tokens_used",
            "aios_company_name",
        ],
        as_dict=True,
    ) or {}

    company = None
    if frappe.get_meta("AIOS Setting").has_field("default_company"):
        company = frappe.db.get_single_value("AIOS Setting", "default_company")
    if not company and frappe.db.exists("DocType", "Global Defaults"):
        company = frappe.db.get_single_value("Global Defaults", "default_company")

    return {
        "user": user,
        "full_name": user_doc.get("full_name"),
        "roles": frappe.get_roles(user),
        "aios_persona": user_doc.get("aios_persona"),
        "aios_status": user_doc.get("aios_status"),
        "aios_token_limit": user_doc.get("aios_token_limit"),
        "aios_tokens_used": user_doc.get("aios_tokens_used"),
        "aios_company_name": user_doc.get("aios_company_name"),
        "company": company,
        "csrf_token": get_csrf_token(),
    }
