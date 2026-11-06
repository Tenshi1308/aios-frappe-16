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
    "AIOS Channel Receiver": 0,
    "AIOS Client Owner": 0,
}

AIOS_ROLE_PROFILES = {
    "AIOS Client Profile": ["AIOS Client"],
    "AIOS Channel Receiver Profile": ["AIOS Channel Receiver"],
    "AIOS Client Owner Profile": ["AIOS Client Owner"],
}


def after_install():
    setup_aios_identity()
    ensure_builtin_plugins()
    ensure_signup_utm_source()
    ensure_connector_defaults()


def after_migrate():
    setup_aios_identity()
    migrate_owner_user_to_channel_roles()
    ensure_builtin_plugins()
    ensure_signup_utm_source()
    ensure_connector_defaults()


def migrate_owner_user_to_channel_roles():
    """Migrasi idempoten transisi owner_user ke Role baru + drop kolom owner_user."""
    old_owner = frappe.db.get_value(
        "Singles",
        {"doctype": "AIOS Telegram Setting", "field": "owner_user"},
        "value",
        order_by=None,
    )

    if old_owner and frappe.db.exists("User", old_owner):
        user_doc = frappe.get_doc("User", old_owner)
        roles = {r.role for r in (user_doc.get("roles") or [])}
        if (
            "AIOS Client" in roles
            and user_doc.get("aios_status") == "Active"
            and int(user_doc.get("enabled") or 0) == 1
        ):
            profiles = {r.role_profile for r in (user_doc.get("role_profiles") or [])}
            changed = False
            if "AIOS Client Profile" not in profiles:
                user_doc.append("role_profiles", {"role_profile": "AIOS Client Profile"})
                changed = True
            if "AIOS Client Owner Profile" not in profiles:
                user_doc.append("role_profiles", {"role_profile": "AIOS Client Owner Profile"})
                changed = True
            if "AIOS Channel Receiver Profile" not in profiles:
                user_doc.append("role_profiles", {"role_profile": "AIOS Channel Receiver Profile"})
                changed = True
            if changed:
                user_doc.flags.ignore_permissions = True
                user_doc.flags.ignore_password_policy = True
                user_doc.save(ignore_permissions=True)

    for dt in ("AIOS Channel Thread", "AIOS Conversation Flag"):
        cols = [r[0] for r in frappe.db.sql(f"SHOW COLUMNS FROM `tab{dt}`")]
        if "owner_user" in cols:
            frappe.db.sql(
                f"""
                UPDATE `tab{dt}`
                SET `owner` = `owner_user`
                WHERE `owner_user` IS NOT NULL
                  AND `owner_user` != ''
                  AND `owner` != `owner_user`
                """
            )
            frappe.db.sql_ddl(f"ALTER TABLE `tab{dt}` DROP COLUMN `owner_user`")
            frappe.cache.delete_value("table_columns")

    frappe.db.delete(
        "Singles",
        {"doctype": "AIOS Telegram Setting", "field": "owner_user"},
    )


def ensure_connector_defaults():
    """Siapkan prasyarat kanal Telegram: tipe notifikasi + kebijakan audit.

    Idempoten dan tidak menimpa isian operator. Tidak mengisi `owner_user` dan
    tidak menyentuh token: keduanya keputusan manusia (docs/02 §2.4).
    """
    from aios_v1.lib.connector.notify import ensure_notification_type

    ensure_notification_type()
    if not frappe.db.get_single_value("AIOS Telegram Setting", "connector_config_json"):
        import json

        from aios_v1.lib.connector.rules import DEFAULT_CONFIG

        frappe.db.set_single_value(
            "AIOS Telegram Setting",
            "connector_config_json",
            json.dumps(DEFAULT_CONFIG, indent=2),
        )


UTM_SOURCE_SIGNUP = "AIOS Signup"


def ensure_signup_utm_source():
    """Pastikan record UTM Source untuk pendaftar AIOS tersedia di site."""
    if frappe.db.exists("DocType", "UTM Source") and not frappe.db.exists("UTM Source", UTM_SOURCE_SIGNUP):
        doc = frappe.get_doc(
            {
                "doctype": "UTM Source",
                "__newname": UTM_SOURCE_SIGNUP,
                "description": "Pendaftaran mandiri calon klien AIOS",
            }
        )
        doc.insert(ignore_permissions=True)


BUILTIN_PLUGIN_SEEDS = (
    ("erpnext-core-data", "ERPNext Core Data"),
    ("erpnext-financial-reports", "ERPNext Financial Reports"),
    ("erpnext-action-drafts", "ERPNext Action Drafts"),
    ("quant-calculator", "Quant Calculator"),
    ("document-intelligence", "Document Intelligence"),
    ("web-market-research", "Web Market Research"),
    ("workspace-artifact-builder", "Workspace Artifact Builder"),
)


def ensure_builtin_plugins():
    """Upsert built-in plugin records without replacing operator state."""
    for plugin_key, plugin_name in BUILTIN_PLUGIN_SEEDS:
        name = frappe.db.get_value("AIOS Plugin", {"plugin_key": plugin_key}, "name")
        if name:
            plugin = frappe.get_doc("AIOS Plugin", name)
            changed = False
            if plugin.plugin_name != plugin_name:
                plugin.plugin_name = plugin_name
                changed = True
            if plugin.plugin_type != "BUILT_IN":
                plugin.plugin_type = "BUILT_IN"
                changed = True
            if not plugin.get("scopes"):
                plugin.append("scopes", {"scope_type": "branch", "scope_key": "finance", "enabled": 1})
                plugin.append("scopes", {"scope_type": "branch", "scope_key": "sales", "enabled": 1})
                changed = True
            if changed:
                plugin.save(ignore_permissions=True)
        else:
            plugin = frappe.get_doc(
                {
                    "doctype": "AIOS Plugin",
                    "plugin_key": plugin_key,
                    "plugin_name": plugin_name,
                    "plugin_type": "BUILT_IN",
                    "enabled": 1,
                }
            )
            plugin.append("scopes", {"scope_type": "branch", "scope_key": "finance", "enabled": 1})
            plugin.append("scopes", {"scope_type": "branch", "scope_key": "sales", "enabled": 1})
            plugin.insert(ignore_permissions=True)


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


def ensure_roles_and_profiles():
    _ensure_roles()
    _ensure_role_profiles()


def _ensure_roles():
    for role_name, desk_access in AIOS_ROLES.items():
        if frappe.db.exists("Role", role_name):
            role = frappe.get_doc("Role", role_name)
            if int(role.desk_access or 0) == int(desk_access):
                continue
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
    orig_in_install = getattr(frappe.flags, "in_install", False)
    try:
        frappe.flags.in_install = True
        for profile_name, roles in AIOS_ROLE_PROFILES.items():
            if frappe.db.exists("Role Profile", profile_name):
                profile = frappe.get_doc("Role Profile", profile_name)
                existing_roles = [r.role for r in (profile.get("roles") or [])]
                if existing_roles == list(roles):
                    continue
            else:
                profile = frappe.new_doc("Role Profile")
                profile.role_profile = profile_name
                profile.name = profile_name
            profile.unlock()
            profile.set("roles", [])
            for role_name in roles:
                profile.append("roles", {"role": role_name})
            profile.save(ignore_permissions=True)
    finally:
        frappe.flags.in_install = orig_in_install


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


CHANNEL_DEPENDENT_ROLES = {"AIOS Channel Receiver", "AIOS Client Owner"}
CHANNEL_DEPENDENT_PROFILES = {"AIOS Channel Receiver Profile", "AIOS Client Owner Profile"}


def validate_aios_channel_and_owner_roles(doc, method=None):
    """User.validate: Keputusan #7 — Role penerima dan Role pengatur wajib AIOS Client aktif."""
    if doc.name in ("Administrator", "Guest"):
        return

    roles = {row.role for row in (doc.get("roles") or [])}
    profiles = {row.role_profile for row in (doc.get("role_profiles") or [])}

    has_dependent_role = bool(roles & CHANNEL_DEPENDENT_ROLES)
    has_dependent_profile = bool(profiles & CHANNEL_DEPENDENT_PROFILES)

    if not has_dependent_role and not has_dependent_profile:
        return

    if "AIOS Client" not in roles or (profiles and "AIOS Client Profile" not in profiles):
        frappe.throw(
            "Role AIOS Channel Receiver dan AIOS Client Owner hanya dapat diberikan kepada "
            "pengguna yang sudah memiliki Role AIOS Client.",
            frappe.ValidationError,
        )

    if doc.get("aios_status") != "Active" or int(doc.get("enabled") or 0) != 1:
        frappe.throw(
            "Role AIOS Channel Receiver dan AIOS Client Owner hanya dapat diberikan kepada "
            "pengguna AIOS Client yang berstatus Active.",
            frappe.ValidationError,
        )


def count_active_client_users(exclude_user: str | None = None) -> int:
    """Hitung jumlah User AIOS Client aktif di site saat ini."""
    params: dict = {}
    exclude_clause = ""
    if exclude_user:
        exclude_clause = "AND u.name != %(exclude_user)s"
        params["exclude_user"] = exclude_user

    rows = frappe.db.sql(
        f"""
        SELECT COUNT(DISTINCT u.name)
        FROM `tabUser` u
        INNER JOIN `tabHas Role` r
            ON r.parent = u.name AND r.parenttype = 'User' AND r.role = 'AIOS Client'
        WHERE u.enabled = 1
          AND u.aios_status = 'Active'
          AND u.name NOT IN ('Administrator', 'Guest')
          {exclude_clause}
        """,
        params,
    )
    return int(rows[0][0]) if rows else 0


def assert_within_max_users(exclude_user: str | None = None) -> tuple[int, int]:
    """Pastikan penambahan 1 user AIOS Client aktif tidak melampaui AIOS Setting.max_users.

    Mengembalikan (current_active, max_users) sebelum penambahan 1 user baru.
    """
    max_users = int(frappe.db.get_single_value("AIOS Setting", "max_users") or 0)
    if max_users <= 0:
        frappe.throw(
            "Batas maksimum pengguna (max_users) belum dikonfigurasi pada AIOS Setting.",
            frappe.ValidationError,
        )
    current_active = count_active_client_users(exclude_user=exclude_user)
    if current_active >= max_users:
        frappe.throw(
            f"Batas maksimum pengguna aktif site ini ({max_users} pengguna) telah tercapai. "
            "Tidak dapat menambah atau mengaktifkan pengguna baru.",
            frappe.ValidationError,
        )
    return current_active, max_users


def validate_max_users(doc, method=None):
    """Hook User.before_insert & User.validate: tegakkan plafon AIOS Setting.max_users."""
    if doc.name in ("Administrator", "Guest"):
        return
    roles = {row.role for row in (doc.get("roles") or [])}
    profiles = {row.role_profile for row in (doc.get("role_profiles") or [])}
    is_client = ("AIOS Client" in roles) or ("AIOS Client Profile" in profiles)
    if not is_client:
        return
    # Plafon hanya menghitung user AIOS Client yang aktif (enabled=1 dan aios_status='Active').
    # Pendaftaran baru via normalize_wizard_user berstatus 'Pending Provisioning' (enabled=0),
    # sehingga tidak dihitung sampai diaktifkan via activate_user.
    is_active = doc.get("aios_status") == "Active" and int(doc.get("enabled") or 0) == 1
    if not is_active:
        return
    assert_within_max_users(exclude_user=doc.name if not doc.is_new() else None)


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


def normalize_wizard_user(args=None):
    """Hook setup_wizard_complete: menormalkan user klien hasil setup wizard Frappe.

    1. Cabut role System Manager agar user tidak memiliki akses Frappe Desk.
    2. Pasang role AIOS Client dan AIOS Client Profile.
    3. Set user_type = 'Website User'.
    4. Set aios_status = 'Pending Provisioning' dan enabled = 0.
    5. Idempotent dan hanya menargetkan email pendaftar, bukan Administrator.
    """
    if not args:
        return

    email = getattr(args, "email", None) if not isinstance(args, dict) else args.get("email")
    if not email:
        return

    email = str(email).strip()
    if email == "Administrator" or not frappe.db.exists("User", email):
        return

    user = frappe.get_doc("User", email)

    # Cabut System Manager
    user.roles = [r for r in user.roles if r.role != "System Manager"]

    # Pasang role AIOS Client
    if not any(r.role == "AIOS Client" for r in user.roles):
        user.append("roles", {"role": "AIOS Client"})

    # Pasang role profile AIOS Client Profile
    if hasattr(user, "role_profiles") and not any(
        r.role_profile == "AIOS Client Profile" for r in user.role_profiles
    ):
        user.append("role_profiles", {"role_profile": "AIOS Client Profile"})

    if hasattr(user, "role_profile_name"):
        user.role_profile_name = "AIOS Client Profile"

    user.user_type = "Website User"
    user.aios_status = "Pending Provisioning"
    user.enabled = 0

    user.flags.ignore_permissions = True
    user.flags.ignore_password_policy = True
    user.save(ignore_permissions=True)

