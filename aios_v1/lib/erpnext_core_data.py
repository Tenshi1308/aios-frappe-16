"""Read-only ERPNext document tools, scoped to the configured site company."""

import frappe

from aios_v1.lib.error_utils import log_exception, safe_error
from aios_v1.lib.tool_registry import ai_tool, get_tool_context
from aios_v1.permissions import ERP_CLIENT_DOCTYPES

DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100

# Satu sumber teks daftar DocType untuk deskripsi tool dan pesan error —
# jangan pernah menuliskan daftarnya secara manual di tempat lain.
_ALLOWED_DOCTYPE_TEXT = ", ".join(ERP_CLIENT_DOCTYPES)


def _spend_hint() -> str:
    """Hint belanja untuk deskripsi tool; kondisional terhadap sumber allowlist.

    Hint hanya muncul bila `Purchase Invoice` ada di `ERP_CLIENT_DOCTYPES` dan
    `Accounts Payable` ada di `ALLOWED_REPORTS`; kegagalan import report module
    hanya melewatkan hint report (dicatat), tidak menggagalkan import tool.
    """
    hint = ""
    if "Purchase Invoice" in ERP_CLIENT_DOCTYPES:
        hint = " Untuk realisasi pengeluaran/pembelian gunakan Purchase Invoice."
    try:
        from aios_v1.lib.erpnext_financial_reports import ALLOWED_REPORTS

        if "Accounts Payable" in ALLOWED_REPORTS:
            hint += " Report Accounts Payable juga tersedia."
    except ImportError as exc:
        log_exception("AIOS ERPNext Core Data Hint", exc=exc)
    return hint


_DOC_LIST_DESCRIPTION = (
    f"Membaca daftar dokumen ERPNext untuk company aktif. "
    f"DocType yang diizinkan: {_ALLOWED_DOCTYPE_TEXT}.{_spend_hint()}"
)
_DOC_GET_DESCRIPTION = (
    f"Membaca detail satu dokumen ERPNext yang diizinkan. "
    f"DocType yang diizinkan: {_ALLOWED_DOCTYPE_TEXT}.{_spend_hint()}"
)
_DOC_SCHEMA_DESCRIPTION = (
    f"Membaca field yang tersedia pada DocType ERPNext yang diizinkan. "
    f"DocType yang diizinkan: {_ALLOWED_DOCTYPE_TEXT}.{_spend_hint()}"
)


def _validate_doctype(doctype: str):
    """Kembalikan `safe_error` bila DocType di luar allowlist; None bila diizinkan."""
    if doctype not in ERP_CLIENT_DOCTYPES:
        return safe_error(
            f"DocType '{doctype}' tidak diizinkan. DocType yang tersedia: "
            f"{_ALLOWED_DOCTYPE_TEXT}. Gunakan salah satu DocType tersebut; jangan menebak.",
            "DOCTYPE_NOT_ALLOWED",
        )
    return None


def _company() -> str:
    company = str(get_tool_context().get("allowed_company") or "").strip()
    if not company:
        frappe.throw("Company default belum dikonfigurasi.")
    return company


def _validate_fields(doctype: str, values, label: str, allow_empty: bool = True):
    if values is None and allow_empty:
        return None
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        frappe.throw(f"{label} harus berupa daftar nama field.")
    valid = set(frappe.get_meta(doctype).get_valid_columns())
    if any(value not in valid for value in values):
        frappe.throw(f"{label} memuat field yang tidak dikenal.")
    return values


@ai_tool(
    name="erpnext_doc_list",
    description=_DOC_LIST_DESCRIPTION,
    branch=["finance", "sales"],
    plugin_key="erpnext-core-data",
    parameters={
        "doctype": {"type": "string", "description": "DocType ERPNext yang diizinkan"},
        "fields": {"type": "array", "items": {"type": "string"}, "description": "Field yang dikembalikan", "required": False},
        "filters": {"type": "object", "description": "Filter field-value", "required": False},
        "limit": {"type": "integer", "description": "Jumlah maksimum baris (default 20, maksimum 100)", "required": False},
        "offset": {"type": "integer", "description": "Baris awal, minimal 0", "required": False},
        "order_by": {"type": "string", "description": "Field dan arah urut, mis. modified desc", "required": False},
    },
)
def erpnext_doc_list(doctype, fields=None, filters=None, limit=None, offset=0, order_by=None):
    error = _validate_doctype(doctype)
    if error:
        return error
    meta = frappe.get_meta(doctype)
    fields = _validate_fields(doctype, fields, "fields")
    if filters is not None and not isinstance(filters, dict):
        frappe.throw("filters harus berupa object.")
    filters = dict(filters or {})
    valid = set(meta.get_valid_columns())
    if any(key not in valid for key in filters):
        frappe.throw("filters memuat field yang tidak dikenal.")
    if doctype == "Company":
        filters["name"] = _company()
    elif meta.has_field("company"):
        filters["company"] = _company()

    try:
        limit = DEFAULT_LIST_LIMIT if limit is None else int(limit)
        offset = int(offset or 0)
    except (TypeError, ValueError) as exc:
        log_exception("AIOS ERPNext List Parameters", exc=exc)
        frappe.throw("limit dan offset harus berupa bilangan bulat.")
    if limit <= 0:
        frappe.throw("limit harus lebih besar dari 0.")
    if offset < 0:
        frappe.throw("offset tidak boleh negatif.")
    limit = min(limit, MAX_LIST_LIMIT)

    if order_by:
        parts = order_by.split()
        if len(parts) not in (1, 2) or parts[0] not in valid or (len(parts) == 2 and parts[1].lower() not in {"asc", "desc"}):
            frappe.throw("order_by tidak valid.")

    rows = frappe.get_list(
        doctype,
        fields=fields or ["name"],
        filters=filters,
        limit_page_length=limit,
        limit_start=offset,
        order_by=order_by or "modified desc",
    )
    return {"doctype": doctype, "company": _company(), "data": [dict(row) for row in rows]}


@ai_tool(
    name="erpnext_doc_get",
    description=_DOC_GET_DESCRIPTION,
    branch=["finance", "sales"],
    plugin_key="erpnext-core-data",
    parameters={
        "doctype": {"type": "string", "description": "DocType ERPNext yang diizinkan"},
        "name": {"type": "string", "description": "ID dokumen"},
    },
)
def erpnext_doc_get(doctype, name):
    error = _validate_doctype(doctype)
    if error:
        return error
    doc = frappe.get_doc(doctype, name, check_permission="read")
    if doctype == "Company" and name != _company():
        frappe.throw("Dokumen tidak ditemukan untuk company aktif.")
    if frappe.get_meta(doctype).has_field("company") and doc.get("company") != _company():
        frappe.throw("Dokumen tidak ditemukan untuk company aktif.")
    return doc.as_dict()


@ai_tool(
    name="erpnext_doctype_schema",
    description=_DOC_SCHEMA_DESCRIPTION,
    branch=["finance", "sales"],
    plugin_key="erpnext-core-data",
    parameters={"doctype": {"type": "string", "description": "DocType ERPNext yang diizinkan"}},
)
def erpnext_doctype_schema(doctype):
    error = _validate_doctype(doctype)
    if error:
        return error
    meta = frappe.get_meta(doctype)
    return {
        "doctype": doctype,
        "fields": [
            {
                "fieldname": field.fieldname,
                "label": field.label,
                "fieldtype": field.fieldtype,
                "options": field.options,
                "reqd": bool(field.reqd),
            }
            for field in meta.fields
            if field.fieldname and not field.fieldname.startswith("_")
        ],
    }
