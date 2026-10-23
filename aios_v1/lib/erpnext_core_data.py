"""Read-only ERPNext document tools, scoped to the configured site company."""

from aios_v1.permissions import ERP_CLIENT_DOCTYPES
from aios_v1.lib.error_utils import log_exception
from aios_v1.lib.tool_registry import ai_tool, get_tool_context
import frappe

DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100


def _validate_doctype(doctype: str) -> None:
    if doctype not in ERP_CLIENT_DOCTYPES:
        frappe.throw("DocType ini tidak diizinkan untuk pembacaan AIOS.")


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
    description="Membaca daftar dokumen ERPNext untuk company aktif.",
    branch=["finance", "sales"],
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
    _validate_doctype(doctype)
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
    description="Membaca detail satu dokumen ERPNext yang diizinkan.",
    branch=["finance", "sales"],
    parameters={
        "doctype": {"type": "string", "description": "DocType ERPNext yang diizinkan"},
        "name": {"type": "string", "description": "ID dokumen"},
    },
)
def erpnext_doc_get(doctype, name):
    _validate_doctype(doctype)
    doc = frappe.get_doc(doctype, name, check_permission="read")
    if doctype == "Company" and name != _company():
        frappe.throw("Dokumen tidak ditemukan untuk company aktif.")
    if frappe.get_meta(doctype).has_field("company") and doc.get("company") != _company():
        frappe.throw("Dokumen tidak ditemukan untuk company aktif.")
    return doc.as_dict()


@ai_tool(
    name="erpnext_doctype_schema",
    description="Membaca field yang tersedia pada DocType ERPNext yang diizinkan.",
    branch=["finance", "sales"],
    parameters={"doctype": {"type": "string", "description": "DocType ERPNext yang diizinkan"}},
)
def erpnext_doctype_schema(doctype):
    _validate_doctype(doctype)
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
