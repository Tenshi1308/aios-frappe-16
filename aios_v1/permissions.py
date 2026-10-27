"""Isolasi baris per `User` (docs/03 §2.1, docs/05.1 §3 Tahap C).

`permission_query_conditions` memfilter daftar; `has_permission` menutup
`frappe.get_doc`. `Administrator` tidak pernah dibatasi — bypass native Frappe.
"""

import frappe

# DocType dengan field kepemilikan langsung `user -> Link(User)`.
OWNED_DOCTYPES = (
	"AIOS Conversation",
	"AIOS Agent State",
	"Pending Action Draft",
	"AIOS Token Usage",
)

# DocPerm dasar per role. `has_permission` hanya bisa MENOLAK, jadi izin dasar
# harus tetap ada (docs/03 §2.1).
CLIENT_PERMS = {
	"AIOS Conversation": ("read", "write", "create", "delete"),
	"AIOS Agent State": ("read", "write", "create", "delete"),
	"Pending Action Draft": ("read", "write", "create", "delete"),
	"AIOS Message": ("read",),
	"AIOS Token Usage": ("read",),
}

# Role layanan control plane: hanya baca User dan log token.
CONTROL_PERMS = {
	"User": ("read",),
	"AIOS Token Usage": ("read",),
}

# Developer control-plane registry permissions. This is deliberately separate
# from the client/control loops: the role only exists on the developer site.
MANAGED_SITE_ADMIN_PERMS = {
	"AIOS Managed Site": ("read", "write", "create", "delete"),
}

# DocType ERPNext target untuk plugin baca/laporan. `AIOS Client` hanya
# read + report; tulis tetap lewat Pending Action Draft.
ERP_CLIENT_DOCTYPES = (
	"Sales Order",
	"Sales Invoice",
	"Purchase Invoice",
	"Delivery Note",
	"Payment Entry",
	"Journal Entry",
	"GL Entry",
	"Customer",
	"Supplier",
	"Item",
	"Company",
	"Account",
)
ERP_CLIENT_PERMS = ("read", "report")


def _roles(user: str) -> set:
	if not user or user == "Guest":
		return set()
	return set(frappe.get_roles(user))


def _is_admin(user: str) -> bool:
	if user == "Administrator":
		return True
	return "AIOS Admin" in _roles(user)


def _is_client(user: str) -> bool:
	if not user or user in ("Guest", "Administrator"):
		return False
	return "AIOS Client" in _roles(user)


def _owned_condition(user: str, doctype: str) -> str:
    """Filter baris milik user; `NULL` otomatis tidak cocok."""
    if not user or user == "Guest":
        return "1=0"
    if _is_admin(user) or not _is_client(user):
        return ""
    return f"`tab{doctype}`.user = {frappe.db.escape(user)}"


def _active_company() -> str:
    """Company aktif dari `AIOS Setting.default_company` (fallback `Global Defaults`)."""
    from aios_v1.lib.tool_registry import _resolve_allowed_company

    return _resolve_allowed_company()


def erp_company_query_conditions(user=None, doctype=None) -> str:
    """Hook `permission_query_conditions` untuk DocType ERPNext (docs/03 §2.2 Lapis 3).

    Hanya menyempitkan `AIOS Client` ke company aktif; Administrator/AIOS Admin
    dan role lain tidak terpengaruh. DocType tanpa field `company` tidak di-scope.
    """
    if not user or user == "Guest":
        return ""
    if _is_admin(user) or not _is_client(user):
        return ""
    company = _active_company()
    if not company:
        # Fail-closed: tanpa company aktif, client tidak melihat data ERP apa pun.
        return "1=0"
    escaped = frappe.db.escape(company)
    if doctype == "Company":
        return f"`tabCompany`.name = {escaped}"
    if doctype and frappe.get_meta(doctype).has_field("company"):
        return f"`tab{doctype}`.company = {escaped}"
    return ""


def erp_company_has_permission(doc, ptype=None, user=None, debug=False) -> bool:
    """Hook `has_permission` untuk DocType ERPNext.

    Frappe menolak bila hook mengembalikan falsy, jadi jalur bypass/non-tercakup
    wajib mengembalikan `True` secara eksplisit — bukan `None`.
    """
    user = user or frappe.session.user
    if not user or user == "Guest":
        return False
    if _is_admin(user) or not _is_client(user):
        return True
    if ptype not in ("read", "report"):
        return True
    company = _active_company()
    if not company:
        return False
    if doc.doctype == "Company":
        return doc.name == company
    if frappe.get_meta(doc.doctype).has_field("company"):
        return (doc.get("company") or "") == company
    return True


def conversation_query_conditions(user=None, doctype=None) -> str:
	return _owned_condition(user, "AIOS Conversation")


def agent_state_query_conditions(user=None, doctype=None) -> str:
	return _owned_condition(user, "AIOS Agent State")


def draft_query_conditions(user=None, doctype=None) -> str:
	return _owned_condition(user, "Pending Action Draft")


def token_usage_query_conditions(user=None, doctype=None) -> str:
	return _owned_condition(user, "AIOS Token Usage")


def message_query_conditions(user=None, doctype=None) -> str:
	"""`AIOS Message` tidak punya `user`; scope lewat 1-hop ke Conversation."""
	if not user or user == "Guest":
		return "1=0"
	if _is_admin(user) or not _is_client(user):
		return ""
	return (
		"`tabAIOS Message`.conversation in ("
		"select `name` from `tabAIOS Conversation` "
		f"where `user` = {frappe.db.escape(user)})"
	)


def has_permission(doc, ptype=None, user=None, debug=False) -> bool:
	"""Hook `has_permission`: tolak akses lintas-user pada `get_doc`/`save`."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	if _is_admin(user):
		return True
	if not _is_client(user):
		return True
	if ptype == "create" and not doc.get("user"):
		return True
	if doc.doctype in OWNED_DOCTYPES:
		return doc.get("user") == user
	if doc.doctype == "AIOS Message":
		conversation_user = frappe.db.get_value(
			"AIOS Conversation", doc.get("conversation"), "user"
		)
		return conversation_user == user
	return True


def set_draft_user(doc, method=None) -> None:
	"""Semua jalur pembuatan draft mewarisi pemilik dari sesi (bukan argumen LLM)."""
	if doc.get("user"):
		return
	user = frappe.session.user
	if user and user != "Guest":
		doc.user = user


def _ensure_role_perm(doctype: str, role: str, ptypes) -> None:
	from frappe.permissions import add_permission, update_permission_property

	exists = frappe.db.exists(
		"Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
	)
	if not exists:
		add_permission(doctype, role, 0, ptypes[0])
	for ptype in ptypes:
		update_permission_property(doctype, role, 0, ptype, 1, validate=False)


def _remove_role_perm(doctype: str, role: str) -> None:
	"""Hapus sisa DocPerm role dari site klien (idempoten)."""
	if not frappe.db.exists("DocType", doctype):
		return
	if not frappe.db.exists(
		"Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
	):
		return
	frappe.db.delete(
		"Custom DocPerm",
		{"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
	)
	frappe.clear_cache(doctype=doctype)


def ensure_aios_permissions() -> None:
	"""Pasang matriks DocPerm dasar `AIOS Client`/`AIOS Control` (idempoten)."""
	for doctype, ptypes in CLIENT_PERMS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		_ensure_role_perm(doctype, "AIOS Client", ptypes)

	for doctype in ERP_CLIENT_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		_ensure_role_perm(doctype, "AIOS Client", ERP_CLIENT_PERMS)

	for doctype, ptypes in CONTROL_PERMS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		_ensure_role_perm(doctype, "AIOS Control", ptypes)

	for doctype, ptypes in MANAGED_SITE_ADMIN_PERMS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		if frappe.db.exists("Role", "AIOS Admin"):
			_ensure_role_perm(doctype, "AIOS Admin", ptypes)
		else:
			_remove_role_perm(doctype, "AIOS Admin")

	_remove_role_perm("AIOS Plugin", "AIOS Admin")
	_remove_role_perm("AIOS Plugin Scope", "AIOS Admin")

	# AIOS Admin tidak dipasang di site klien. Bersihkan sisa baris lama.
	for doctype in set(CLIENT_PERMS) | set(ERP_CLIENT_DOCTYPES):
		_remove_role_perm(doctype, "AIOS Admin")

	ensure_report_roles()

	frappe.clear_cache()


def ensure_report_roles() -> None:
	"""Rebuild `Custom Role` untuk report di `ALLOWED_REPORTS` (docs/03 §2.1).

	Role hasil rebuild = `Has Role` milik Report + `AIOS Client`; role stale yang
	sudah tidak ada di Report tidak dipertahankan (owner: rebuild, bukan append).
	Report tanpa `Has Role` tidak disentuh sama sekali — Custom Role existing
	tetap utuh dan tidak ada yang dibuat — agar report yang terbuka tidak
	tersempit dan role lama tidak terhapus saat sumber Has Role kosong. Report
	tanpa `Has Role` dan tanpa `Custom Role` pun dibiarkan terbuka. Dipanggil
	dari `ensure_aios_permissions()` (install + migrate), jadi edit manual
	`Custom Role` lewat UI bisa tertimpa. Tidak membuat `Role` baru dan tidak
	menyentuh `Has Role` standard Report.
	"""
	from aios_v1.lib.erpnext_financial_reports import ALLOWED_REPORTS

	for report_name in sorted(ALLOWED_REPORTS):
		report = frappe.db.get_value(
			"Report", report_name, ["name", "ref_doctype", "disabled"], as_dict=True
		)
		if not report or report.disabled:
			continue
		has_role = [
			d.role
			for d in frappe.get_all(
				"Has Role",
				fields=["role"],
				filters={"parent": report_name, "parenttype": "Report"},
			)
		]
		if not has_role:
			continue
		custom = frappe.db.get_value("Custom Role", {"report": report_name}, "name")
		desired = list(dict.fromkeys([*has_role, "AIOS Client"]))
		if custom:
			doc = frappe.get_doc("Custom Role", custom)
			current = [d.role for d in doc.get("roles") or []]
			if current == desired and doc.ref_doctype == report.ref_doctype:
				continue
			doc.ref_doctype = report.ref_doctype
			doc.set("roles", [])
			for role in desired:
				doc.append("roles", {"role": role})
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc(
				{
					"doctype": "Custom Role",
					"report": report_name,
					"ref_doctype": report.ref_doctype,
					"roles": [{"role": role} for role in desired],
				}
			).insert(ignore_permissions=True)
