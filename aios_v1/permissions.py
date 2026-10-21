"""Isolasi baris per `User` (docs/03 §2.1, docs/05.1 §3 Tahap C).

`permission_query_conditions` memfilter daftar; `has_permission` menutup
`frappe.get_doc`. `Administrator` tidak pernah dibatasi — bypass native Frappe.
"""

import frappe

# DocType dengan field kepemilikan langsung `user -> Link(User)`.
OWNED_DOCTYPES = (
	"AIOS Conversation",
	"AIOS DB Connection",
	"AIOS Agent State",
	"Pending Action Draft",
)

# DocPerm dasar per role. `has_permission` hanya bisa MENOLAK, jadi izin dasar
# harus tetap ada (docs/03 §2.1). Matriks penuh menyusul di #4b.
CLIENT_PERMS = {
	"AIOS Conversation": ("read", "write", "create", "delete"),
	"AIOS DB Connection": ("read", "write", "create", "delete"),
	"AIOS Agent State": ("read", "write", "create", "delete"),
	"Pending Action Draft": ("read", "write", "create", "delete"),
	"AIOS Message": ("read",),
}
ADMIN_PERMS = ("read", "write", "create", "delete")


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


def conversation_query_conditions(user=None, doctype=None) -> str:
	return _owned_condition(user, "AIOS Conversation")


def db_connection_query_conditions(user=None, doctype=None) -> str:
	return _owned_condition(user, "AIOS DB Connection")


def agent_state_query_conditions(user=None, doctype=None) -> str:
	return _owned_condition(user, "AIOS Agent State")


def draft_query_conditions(user=None, doctype=None) -> str:
	return _owned_condition(user, "Pending Action Draft")


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


def ensure_aios_permissions() -> None:
	"""Pasang DocPerm dasar `AIOS Client`/`AIOS Admin` (idempoten)."""
	for doctype, ptypes in CLIENT_PERMS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		_ensure_role_perm(doctype, "AIOS Client", ptypes)
		_ensure_role_perm(doctype, "AIOS Admin", ADMIN_PERMS)
