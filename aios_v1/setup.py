"""Setup identitas Frappe AIOS.

Custom Field `User`, Role, dan Role Profile didaftarkan lewat hook
`after_install` / `after_migrate` di hooks.py memakai `create_custom_fields`
(API resmi Frappe; dipakai ERPNext sendiri di setup/install.py).
Tidak memakai fixtures dan tidak memutasi `tabDocField`.
"""

from urllib.parse import urlsplit, urlunsplit

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
            "fieldname": "aios_tokens_used",
            "fieldtype": "Int",
            "label": "AIOS Tokens Used",
            "read_only": 1,
            "insert_after": "aios_company_name",
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
    ensure_sales_tax_template()


def after_migrate():
    setup_aios_identity()
    migrate_owner_user_to_channel_roles()
    ensure_builtin_plugins()
    ensure_signup_utm_source()
    ensure_connector_defaults()
    ensure_sales_tax_template()


def ensure_sales_tax_template():
    """Pastikan Sales Taxes and Charges Template PPN 11% aktif & default untuk company site."""
    if not frappe.db.exists("DocType", "Sales Taxes and Charges Template"):
        return

    from aios_v1.lib.draft_manager import _resolve_sales_tax_template
    from aios_v1.lib.error_utils import log_exception

    companies: list[str] = []
    for dt in ("AIOS Setting", "Global Defaults"):
        if frappe.db.exists("DocType", dt):
            comp = frappe.db.get_single_value(dt, "default_company")
            if comp and comp not in companies:
                companies.append(str(comp))
    for comp in frappe.get_all("Company", filters={"country": "Indonesia"}, pluck="name"):
        if comp and comp not in companies:
            companies.append(str(comp))

    for company in companies:
        if not frappe.db.exists("Company", company):
            continue
        try:
            _resolve_sales_tax_template(company)
        except Exception as exc:
            log_exception("AIOS Ensure Sales Tax Template", exc=exc, context=f"company={company}")


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

_BASE_PLUGIN_BRANCHES = ("finance", "sales")
_READONLY_ACCOUNTING_PLUGINS = frozenset(
    {
        "erpnext-core-data",
        "erpnext-financial-reports",
        "quant-calculator",
        "document-intelligence",
        "web-market-research",
        "workspace-artifact-builder",
    }
)
_LEGACY_UNTOUCHED_SCOPES = frozenset({("branch", "finance", 1), ("branch", "sales", 1)})


def _default_branches_for_plugin(plugin_key: str) -> tuple[str, ...]:
    if plugin_key in _READONLY_ACCOUNTING_PLUGINS:
        return (*_BASE_PLUGIN_BRANCHES, "accounting")
    return _BASE_PLUGIN_BRANCHES


def ensure_builtin_plugins():
    """Upsert built-in plugin records without replacing operator state."""
    for plugin_key, plugin_name in BUILTIN_PLUGIN_SEEDS:
        default_branches = _default_branches_for_plugin(plugin_key)
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
            existing_scopes = plugin.get("scopes") or []
            if not existing_scopes:
                for branch_key in default_branches:
                    plugin.append("scopes", {"scope_type": "branch", "scope_key": branch_key, "enabled": 1})
                changed = True
            elif (
                "accounting" in default_branches
                and int(plugin.enabled or 0) == 1
                and len(existing_scopes) == len(_LEGACY_UNTOUCHED_SCOPES)
                and {
                    (s.scope_type, (s.scope_key or "").strip(), int(s.enabled or 0))
                    for s in existing_scopes
                }
                == _LEGACY_UNTOUCHED_SCOPES
            ):
                # Upgrade site eksisting yang masih memakai seed bawaan lama [finance, sales]
                # tanpa menimpa state operator yang sudah diubah atau dinonaktifkan.
                plugin.append("scopes", {"scope_type": "branch", "scope_key": "accounting", "enabled": 1})
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
            for branch_key in default_branches:
                plugin.append("scopes", {"scope_type": "branch", "scope_key": branch_key, "enabled": 1})
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


def strip_wizard_channel_roles(doc) -> bool:
    """Cabut Role/Role Profile channel dari user yang sedang dibuat setup wizard.

    Frappe `create_or_update_user` (`frappe/desk/page/setup_wizard/setup_wizard.py:338`)
    menempelkan SEMUA Role ke user PERTAMA wizard lewat `_get_default_roles()`
    (baris 390-398), termasuk `AIOS Channel Receiver` dan `AIOS Client Owner` yang
    dibuat `after_install`. Keduanya menempel SEBELUM hook `setup_wizard_complete`
    sempat berjalan, sehingga `validate_aios_channel_and_owner_roles` (Keputusan #7)
    menolak user yang belum `Active` dan seluruh wizard gagal.

    Intervensi memakai primitif resmi `frappe.flags.in_setup_wizard` (dinyalakan
    Frappe di `process_setup_stages` baris 103, dipakai pula di `document.py:524`),
    dan hanya melepas role channel dari user BARU milik wizard — bukan melonggarkan
    validasi Keputusan #7 untuk jalur non-wizard. Role channel tetap dipasang di
    langkah 4 (`control.activate_user`) atau langkah 6 (menu Penerima Kanal).
    """
    if not frappe.flags.get("in_setup_wizard") or not doc.is_new():
        return False
    if doc.name in ("Administrator", "Guest"):
        return False

    changed = False
    channel_roles = [r for r in (doc.get("roles") or []) if r.role in CHANNEL_DEPENDENT_ROLES]
    if channel_roles:
        for row in channel_roles:
            doc.get("roles").remove(row)
        changed = True

    channel_profiles = [
        rp
        for rp in (doc.get("role_profiles") or [])
        if rp.role_profile in CHANNEL_DEPENDENT_PROFILES
    ]
    if channel_profiles:
        for row in channel_profiles:
            doc.get("role_profiles").remove(row)
        changed = True

    return changed


def validate_aios_channel_and_owner_roles(doc, method=None):
    """User.validate: Keputusan #7 — Role penerima dan Role pengatur wajib AIOS Client aktif."""
    # Langkah 3 Flow Utama: Frappe menempelkan semua Role ke user pertama wizard.
    # Cabut dulu role channel yang bukan hak user Pending Provisioning, agar wizard
    # tidak gagal; validasi #7 di bawah tetap berlaku penuh untuk jalur non-wizard.
    strip_wizard_channel_roles(doc)

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


def _normalize_invitation_url(raw_url: str | None) -> str | None:
    """Normalisasi tautan undangan agar memuat port webserver bila bukan mode produksi.

    Menghindari kegagalan koneksi ketika site klien diakses pada port non-standar (mis. port webserver lokal)
    karena Frappe get_url(..., allow_header_override=False) mengabaikan webserver_port
    bila developer_mode tidak aktif.
    """
    if not raw_url:
        return raw_url

    parsed = urlsplit(raw_url)
    if parsed.port is not None or not parsed.hostname:
        return raw_url

    is_production = bool(
        frappe.conf.get("restart_supervisor_on_update")
        or frappe.conf.get("restart_systemd_on_update")
    )
    if is_production:
        return raw_url

    port = frappe.conf.get("http_port") or frappe.conf.get("webserver_port")
    if not port:
        return raw_url

    return urlunsplit((parsed.scheme, f"{parsed.hostname}:{port}", parsed.path, parsed.query, ""))


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

    # Cabut Role/Role Profile channel bila ada (lapis kedua, idempoten). Frappe
    # `create_or_update_user` menempelkan semua Role ke user pertama wizard; pada
    # jalur normal sudah dilepas `strip_wizard_channel_roles` saat User.validate,
    # tetapi hook ini juga harus aman bila dipanggil terpisah (mis. lewat kontrak).
    # Keputusan #7: role channel baru dipasang di langkah 4/6, bukan saat wizard.
    user.roles = [r for r in user.roles if r.role not in CHANNEL_DEPENDENT_ROLES]
    if hasattr(user, "role_profiles"):
        user.role_profiles = [
            rp
            for rp in user.role_profiles
            if rp.role_profile not in CHANNEL_DEPENDENT_PROFILES
        ]

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

