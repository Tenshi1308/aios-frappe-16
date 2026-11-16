"""Read-only ERPNext document tools, scoped to the configured site company."""

import frappe

from aios_v1.lib.draft_manager import (
    _calculate_sales_tax_breakdown,
    _format_currency_amount,
    _resolve_sales_tax_template,
)
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
    " Saat menggunakan hasil tool ini, sebutkan filter yang kamu pakai dan "
    "cakupannya; jangan menyebut hasil terfilter sebagai seluruh data."
)
_DOC_GET_DESCRIPTION = (
    f"Membaca detail satu dokumen ERPNext yang diizinkan. "
    f"DocType yang diizinkan: {_ALLOWED_DOCTYPE_TEXT}.{_spend_hint()}"
)
_DOC_SCHEMA_DESCRIPTION = (
    f"Membaca field yang tersedia pada DocType ERPNext yang diizinkan. "
    f"DocType yang diizinkan: {_ALLOWED_DOCTYPE_TEXT}.{_spend_hint()}"
)


GUEST_ALLOWED_DOCTYPES = frozenset({"Item", "Item Price"})
_GUEST_ALLOWED_DOCTYPE_TEXT = ", ".join(sorted(GUEST_ALLOWED_DOCTYPES))
STANDARD_SELLING_PRICE_LIST = "Standard Selling"

_GUEST_DOC_LIST_DESCRIPTION = (
    f"Membaca daftar dokumen katalog perusahaan. "
    f"DocType yang diizinkan: {_GUEST_ALLOWED_DOCTYPE_TEXT}."
    " Saat menggunakan hasil tool ini, sebutkan filter yang kamu pakai dan "
    "cakupannya; jangan menyebut hasil terfilter sebagai seluruh data."
    " Untuk Item Price, hasil otomatis menyertakan rincian PPN 11% resmi ERPNext "
    "(base_rate, ppn_11_per_unit, rate_with_ppn_11 beserta format Rupiahnya)."
)
_GUEST_DOC_GET_DESCRIPTION = (
    f"Membaca detail satu dokumen katalog perusahaan yang diizinkan. "
    f"DocType yang diizinkan: {_GUEST_ALLOWED_DOCTYPE_TEXT}."
    " Untuk Item Price, hasil otomatis menyertakan rincian PPN 11% resmi ERPNext "
    "(base_rate, ppn_11_per_unit, rate_with_ppn_11 beserta format Rupiahnya)."
)
_GUEST_DOC_SCHEMA_DESCRIPTION = (
    f"Membaca field yang tersedia pada DocType katalog perusahaan yang diizinkan. "
    f"DocType yang diizinkan: {_GUEST_ALLOWED_DOCTYPE_TEXT}."
)
_GUEST_DRAFT_CREATE_DESCRIPTION = (
    "Membuat Pending Action Draft pesanan pembelian (Sales Order) atau penawaran (Quotation) untuk pelanggan baru atau lama. "
    "Data pelanggan baru (customer_type, customer_name, contact_person, mobile_no, address, payment_method) dimasukkan ke parameter 'customer_info', "
    "bukan ke dalam 'data'. Parameter 'data' hanya berisi field resmi dokumen seperti 'customer', 'items', 'delivery_date' (format YYYY-MM-DD), dll. "
    "Untuk pesanan Sales Order, tanggal pengiriman ('delivery_date') wajib diisi di dalam 'data', dan 'payment_method' wajib diisi 'Cash' di dalam 'customer_info'. "
    "Nilai customer_type harus 'Individual' (perorangan) atau 'Company' (perusahaan/instansi)."
)
GUEST_TOOL_DESCRIPTIONS = {
    "erpnext_doc_list": _GUEST_DOC_LIST_DESCRIPTION,
    "erpnext_doc_get": _GUEST_DOC_GET_DESCRIPTION,
    "erpnext_doctype_schema": _GUEST_DOC_SCHEMA_DESCRIPTION,
    "erpnext_action_draft_create": _GUEST_DRAFT_CREATE_DESCRIPTION,
}


def _is_guest() -> bool:
    ctx_user = get_tool_context().get("user_id")
    sess_user = getattr(frappe.session, "user", None)
    return ctx_user == "Guest" or sess_user == "Guest"


def _validate_doctype(doctype: str):
    """Kembalikan `safe_error` bila DocType di luar allowlist; None bila diizinkan."""
    if _is_guest():
        if doctype not in GUEST_ALLOWED_DOCTYPES:
            return safe_error(
                f"DocType '{doctype}' tidak diizinkan untuk tamu. "
                f"DocType yang tersedia untuk tamu: {', '.join(sorted(GUEST_ALLOWED_DOCTYPES))}.",
                "DOCTYPE_NOT_ALLOWED",
            )
        return None

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


def _resolve_tax_preview_company(company: str) -> str:
    """Resolve active Company record for tax preview calculation."""
    if company and frappe.db.exists("Company", company):
        return company
    default_company = ""
    if frappe.get_meta("AIOS Setting").has_field("default_company"):
        default_company = frappe.db.get_single_value("AIOS Setting", "default_company") or ""
    if not default_company and frappe.db.exists("DocType", "Global Defaults"):
        default_company = frappe.db.get_single_value("Global Defaults", "default_company") or ""
    return str(default_company).strip() or company


def _enrich_guest_item_price_row(
    row_dict: dict,
    company: str,
    taxes_and_charges: str | None = None,
) -> dict:
    """Enrich one guest Item Price row with ERPNext official in-memory PPN 11% breakdown."""
    enriched = dict(row_dict)
    if (
        enriched.get("price_list_rate") is None
        and enriched.get("name")
        and frappe.db.exists("Item Price", enriched["name"])
    ):
        ip_fields = (
            frappe.db.get_value(
                "Item Price",
                enriched["name"],
                ["price_list_rate", "currency", "item_code", "item_name", "uom"],
                as_dict=True,
            )
            or {}
        )
        for key, val in ip_fields.items():
            if enriched.get(key) is None:
                enriched[key] = val

    rate_val = float(enriched.get("price_list_rate") or 0.0)
    eff_company = _resolve_tax_preview_company(company)
    currency = (
        str(
            enriched.get("currency")
            or (frappe.get_cached_value("Company", eff_company, "default_currency") if eff_company else None)
            or "IDR"
        ).strip()
        or "IDR"
    )
    uom = str(enriched.get("uom") or "").strip() or "Nos"
    breakdown = _calculate_sales_tax_breakdown(
        "Sales Order",
        eff_company,
        currency,
        STANDARD_SELLING_PRICE_LIST,
        [
            {
                "item_code": enriched.get("item_code"),
                "item_name": enriched.get("item_name") or enriched.get("item_code") or enriched.get("name"),
                "qty": 1,
                "rate": rate_val,
                "uom": uom,
            }
        ],
        taxes_and_charges=taxes_and_charges,
    )
    base_rate = float(breakdown["base_total"])
    ppn_11_per_unit = float(breakdown["tax_amount"])
    rate_with_ppn_11 = float(breakdown["grand_total"])
    enriched.update(
        {
            "base_rate": base_rate,
            "formatted_base_rate": _format_currency_amount(base_rate, currency),
            "ppn_11_per_unit": ppn_11_per_unit,
            "formatted_ppn_11_per_unit": _format_currency_amount(ppn_11_per_unit, currency),
            "rate_with_ppn_11": rate_with_ppn_11,
            "formatted_rate_with_ppn_11": _format_currency_amount(rate_with_ppn_11, currency),
            "taxes_and_charges": breakdown["taxes_and_charges"],
        }
    )
    return enriched


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

    guest_item_price = doctype == "Item Price" and _is_guest()
    query_fields = list(fields) if fields is not None else ["name"]
    if guest_item_price:
        filters["price_list"] = STANDARD_SELLING_PRICE_LIST
        filters["selling"] = 1
        if fields is not None:
            for req_field in ("price_list_rate", "currency", "item_code", "item_name", "uom"):
                if req_field not in query_fields and req_field in valid:
                    query_fields.append(req_field)
        else:
            query_fields = ["name", "item_code", "item_name", "price_list_rate", "currency", "uom"]

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
        fields=query_fields,
        filters=filters,
        limit_page_length=limit,
        limit_start=offset,
        order_by=order_by or "modified desc",
    )
    company_name = _company()
    data_rows = [dict(row) for row in rows]
    if guest_item_price and data_rows:
        tax_template = _resolve_sales_tax_template(_resolve_tax_preview_company(company_name))
        data_rows = [
            _enrich_guest_item_price_row(row, company_name, taxes_and_charges=tax_template)
            for row in data_rows
        ]
    return {"doctype": doctype, "company": company_name, "data": data_rows}


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
    if _is_guest():
        doc = frappe.get_doc(doctype, name)
    else:
        doc = frappe.get_doc(doctype, name, check_permission="read")
    if doctype == "Company" and name != _company():
        frappe.throw("Dokumen tidak ditemukan untuk company aktif.")
    if frappe.get_meta(doctype).has_field("company") and doc.get("company") != _company():
        frappe.throw("Dokumen tidak ditemukan untuk company aktif.")
    if doctype == "Item Price" and _is_guest():
        if doc.get("price_list") != STANDARD_SELLING_PRICE_LIST or not doc.get("selling"):
            return safe_error(
                "Dokumen harga tidak ditemukan atau bukan harga jual standar.",
                "PRICE_NOT_ALLOWED",
            )
        doc_dict = doc.as_dict() if hasattr(doc, "as_dict") else dict(doc)
        return _enrich_guest_item_price_row(doc_dict, _company())
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
