"""Manajemen `Pending Action Draft` (Alur 5, docs/04).

- `create_draft()`: satu-satunya jalur pembuatan draft; pemilik selalu dari sesi.
- `approve_and_execute_draft()`: approve -> buat dokumen ERPNext -> `EXECUTED`.
  Bila eksekusi gagal, draft tetap `APPROVED` dan kegagalan dicatat di Error Log.
- `reject_draft()`: `REJECTED` + catatan penolakan untuk AI Manager.
"""

import json
import re

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from aios_v1.lib.error_utils import log_exception

DRAFT_DOCTYPE = "Pending Action Draft"
ACTION_TYPES = frozenset({"CREATE", "UPDATE_DRAFT", "CANCEL_AND_AMEND"})
_PROTECTED_FIELDS = frozenset({
    "name", "doctype", "docstatus", "amended_from", "owner", "creation",
    "modified", "modified_by", "parent", "parenttype", "parentfield", "idx",
})


class DraftExecutionError(frappe.ValidationError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)

# DocType ERPNext yang boleh dibuat lewat approval (docs/04 Alur 5, docs/02 §2.2).
ALLOWED_DRAFT_DOCTYPES = frozenset(
    {
        "Quotation",
        "Sales Order",
        "Sales Invoice",
        "Delivery Note",
        "Purchase Order",
        "Payment Entry",
        "Journal Entry",
    }
)


def create_draft(
    task_id: str,
    action_type: str,
    payload: dict,
    branch: str | None = None,
    created_by_agent: str | None = None,
    reason: str = "",
    expires_in_hours: int = 24,
    user: str | None = None,
):
    """Simpan draft baru; `user` diambil dari parameter eksplisit atau sesi aktif."""
    if not task_id or not action_type:
        frappe.throw("task_id dan action_type wajib diisi.")
    if action_type not in ACTION_TYPES:
        frappe.throw("Jenis aksi draft tidak dikenal.")
    if not isinstance(payload, dict):
        frappe.throw("Payload draft harus berupa object JSON.")

    # Rekam chat_id Telegram dari context thread bila belum ada di payload
    if "source_telegram_chat_id" not in payload:
        channel_thread = getattr(frappe.local, "aios_channel_thread", None)
        if channel_thread:
            chat_id = (
                getattr(channel_thread, "external_thread_id", None)
                or (channel_thread.get("external_thread_id") if isinstance(channel_thread, dict) else None)
            )
            if chat_id:
                payload["source_telegram_chat_id"] = str(chat_id)

    try:
        payload_json = json.dumps(payload, default=str)
    except (TypeError, ValueError):
        frappe.log_error(frappe.get_traceback(), "AIOS Draft Payload")
        frappe.throw("Payload draft tidak bisa diserialisasi ke JSON.")

    doc = frappe.get_doc(
        {
            "doctype": DRAFT_DOCTYPE,
            "user": user or frappe.session.user,
            "task_id": task_id,
            "type": action_type,
            "branch": branch,
            "created_by_agent": created_by_agent,
            "payload": payload_json,
            "status": "PENDING_APPROVAL",
            "expires_at": add_to_date(now_datetime(), hours=expires_in_hours),
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


def _json_copy(value):
    return json.loads(json.dumps(value, default=str))


def _snapshot_value(value):
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    if isinstance(value, dict):
        return {
            str(key): _snapshot_value(item)
            for key, item in value.items()
            if key not in _PROTECTED_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [_snapshot_value(item) for item in value]
    return _json_copy(value)


def validate_data_fields(meta, data: dict) -> None:
    for fieldname, value in data.items():
        if fieldname in _PROTECTED_FIELDS or fieldname == "company":
            frappe.throw(f"Field '{fieldname}' tidak dapat diubah melalui draft AIOS.")
        field = meta.get_field(fieldname)
        if not field:
            frappe.throw(
                f"Field '{fieldname}' tidak dikenal untuk DocType '{meta.name}'. "
                f"Gunakan tool 'erpnext_doctype_schema' untuk memeriksa nama field yang valid."
            )
        if field.fieldtype == "Table":
            if not isinstance(value, list):
                frappe.throw(f"Field tabel '{fieldname}' harus berupa daftar.")
            child_meta = frappe.get_meta(field.options)
            for row in value:
                if not isinstance(row, dict):
                    frappe.throw(f"Baris pada '{fieldname}' harus berupa object.")
                validate_data_fields(child_meta, row)


def snapshot_fields(target, data: dict) -> dict:
    """Capture only approved business fields from an ERPNext document."""
    if not isinstance(data, dict) or not data:
        frappe.throw("data untuk perubahan draft tidak boleh kosong.")
    for fieldname in data:
        if fieldname in _PROTECTED_FIELDS or fieldname == "company" or not target.meta.get_field(fieldname):
            frappe.throw("Snapshot memuat field yang tidak dapat diubah melalui draft AIOS.")
    return {field: _snapshot_value(target.get(field)) for field in data}


def _site_company() -> str:
    company = (
        frappe.db.get_single_value("AIOS Setting", "default_company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    )
    if not company:
        frappe.log_error(
            "default_company kosong: AIOS Setting/Global Defaults",
            "AIOS Draft Executor",
        )
        raise DraftExecutionError("COMPANY_NOT_CONFIGURED", "Company default belum dikonfigurasi.")
    return company


def _load_target(doctype: str, name: str, company: str):
    target = frappe.get_doc(doctype, name)
    if not target.has_permission("read"):
        raise DraftExecutionError("PERMISSION_DENIED", "Dokumen target tidak dapat dibaca.")
    if target.meta.has_field("company") and target.get("company") != company:
        raise DraftExecutionError("COMPANY_MISMATCH", "Dokumen tidak ditemukan untuk company aktif.")
    return target


def _assert_snapshot_current(target, before: dict) -> None:
    if not isinstance(before, dict) or not before:
        raise DraftExecutionError("DRAFT_INVALID", "Snapshot dokumen tidak valid.")
    current = snapshot_fields(target, before)
    if json.dumps(current, sort_keys=True, default=str) != json.dumps(before, sort_keys=True, default=str):
        raise DraftExecutionError("DRAFT_STALE", "Dokumen berubah setelah draft dibuat. Buat draft baru.")


def _period_is_closed(target, company: str) -> bool:
    """Fail closed if the original transaction date falls in a closed period."""
    if not frappe.db.exists("DocType", "Accounting Period") or not frappe.db.exists("DocType", "Closed Document"):
        raise DraftExecutionError("PERIOD_CHECK_FAILED", "Status periode akuntansi tidak dapat diverifikasi.")
    date_field = next(
        (field for field in ("posting_date", "transaction_date", "date", "completion_date", "period_end_date")
         if target.meta.has_field(field) and target.get(field)),
        None,
    )
    transaction_date = target.get(date_field) if date_field else None
    if not transaction_date:
        raise DraftExecutionError("PERIOD_CHECK_FAILED", "Tanggal dokumen tidak tersedia untuk pemeriksaan periode.")
    periods = frappe.get_all(
        "Accounting Period",
        filters={"company": company, "disabled": 0, "start_date": ["<=", transaction_date],
                 "end_date": [">=", transaction_date]},
        fields=["name"],
        limit_page_length=0,
    )
    for period in periods:
        if frappe.db.exists(
            "Closed Document",
            {"parent": period.name, "parenttype": "Accounting Period",
             "parentfield": "closed_documents", "document_type": target.doctype, "closed": 1},
        ):
            return True
    return False


def normalize_phone_number(raw_phone: str) -> str:
    """Normalisasi nomor HP: hapus karakter non-digit, samakan awalan +62/62/8 menjadi 08."""
    if not raw_phone:
        return ""
    digits = re.sub(r"\D", "", str(raw_phone))
    if not digits:
        return ""
    if digits.startswith("62") and len(digits) >= 10:
        digits = "0" + digits[2:]
    elif digits.startswith("8") and len(digits) >= 9:
        digits = "0" + digits
    return digits


def _find_customer_by_phone(phone: str) -> str | None:
    norm = normalize_phone_number(phone)
    if not norm:
        return None
    variants = [norm]
    if norm.startswith("0") and len(norm) > 1:
        variants.append("+62" + norm[1:])
        variants.append("62" + norm[1:])

    # 1. Cek di tabContact Phone & tabContact via Dynamic Link ke Customer
    contact_names = frappe.db.sql(
        """
        SELECT parent FROM `tabContact Phone`
        WHERE phone IN %(variants)s
        UNION
        SELECT name FROM `tabContact`
        WHERE mobile_no IN %(variants)s OR phone IN %(variants)s
        """,
        {"variants": variants},
        pluck=True,
    )
    if contact_names:
        customer_links = frappe.db.sql(
            """
            SELECT link_name FROM `tabDynamic Link`
            WHERE parenttype = 'Contact'
              AND parent IN %(contacts)s
              AND link_doctype = 'Customer'
            ORDER BY creation ASC
            LIMIT 1
            """,
            {"contacts": contact_names},
            pluck=True,
        )
        if customer_links:
            return customer_links[0]

    # 2. Cek di tabCustomer langsung bila ada
    cust = frappe.db.get_value("Customer", {"mobile_no": ["in", variants]}, "name")
    if cust:
        return cust
    return None


def _get_company_default_location(company: str) -> tuple[str, str]:
    """Cari kota dan negara default dari Company di site; fallback negara Indonesia."""
    country = "Indonesia"
    city = ""
    if company and frappe.db.exists("Company", company):
        comp_country = frappe.db.get_value("Company", company, "country")
        if comp_country:
            country = comp_country

        company_addr = frappe.db.sql(
            """
            SELECT a.city, a.country
            FROM `tabAddress` a
            JOIN `tabDynamic Link` dl ON dl.parent = a.name
            WHERE dl.link_doctype = 'Company' AND dl.link_name = %s
            ORDER BY a.is_primary_address DESC, a.creation ASC
            LIMIT 1
            """,
            (company,),
            as_dict=True,
        )
        if company_addr:
            if company_addr[0].get("city"):
                city = company_addr[0]["city"]
            if company_addr[0].get("country"):
                country = company_addr[0]["country"]

    return city, country


def _ensure_customer_for_draft(payload: dict, company: str) -> str | None:
    """Pastikan Customer ada sebelum Sales Order/Quotation dibuat otomatis dari draf."""
    info = payload.get("customer_info")
    data = payload.get("data") or {}

    # Jika customer_info tidak ada di payload, cek apakah data memuat customer placeholder yang belum ada di ERP
    if not info:
        target_customer = data.get("customer") or data.get("party_name")
        if target_customer and not frappe.db.exists("Customer", target_customer):
            info = {
                "customer_name": target_customer,
                "customer_type": "Individual",
                "mobile_no": data.get("contact_mobile") or "",
                "address": data.get("address_display") or "",
                "contact_person": data.get("contact_display") or "",
            }

    if not info:
        return data.get("customer") or data.get("party_name")

    customer_name = (info.get("customer_name") or "").strip()
    customer_type = info.get("customer_type") or "Individual"
    if customer_type not in {"Individual", "Company"}:
        customer_type = "Individual"
    mobile_no = (info.get("mobile_no") or "").strip()
    address_str = (info.get("address") or "").strip()
    contact_person = (info.get("contact_person") or "").strip()

    if not customer_name:
        return data.get("customer") or data.get("party_name")

    # Aturan anti-duplikat: nomor HP diperiksa lebih dulu
    matched_cust = _find_customer_by_phone(mobile_no) if mobile_no else None
    if matched_cust:
        existing_cust = frappe.get_doc("Customer", matched_cust)
        existing_name = (existing_cust.customer_name or "").strip()

        # Kasus 1: Nomor HP cocok dan nama sama
        if existing_name.lower() == customer_name.lower():
            return matched_cust

        # Kasus 2: Nomor HP cocok tapi nama beda
        if customer_type == "Individual" or existing_cust.customer_type == "Individual":
            # Untuk perorangan: pakai Customer lama, catat nama baru di contact_display
            if isinstance(data, dict):
                data["contact_display"] = customer_name
            return matched_cust
        else:
            # Untuk perusahaan: tambahkan Contact PIC baru ke perusahaan tersebut
            from erpnext.selling.doctype.customer.customer import make_contact

            contact_args = frappe._dict({
                "doctype": "Customer",
                "name": matched_cust,
                "customer_name": existing_name,
                "customer_type": "Company",
                "first_name": contact_person or customer_name,
                "mobile_no": mobile_no,
                "flags": {"ignore_permissions": True},
            })
            try:
                make_contact(contact_args, is_primary_contact=0)
            except Exception as exc:
                log_exception("AIOS Add Contact PIC to Existing Customer", exc=exc)
            return matched_cust

    # Kasus 3 & 4: Nomor HP baru (nama baru atau nama sama tapi HP baru)
    # Buat Customer baru lewat primitif resmi ERPNext
    cust_group = "Individual" if customer_type == "Individual" else "Commercial"
    if not frappe.db.exists("Customer Group", cust_group):
        cust_group = frappe.db.get_single_value("Selling Settings", "customer_group") or "All Customer Groups"

    comp_city, comp_country = _get_company_default_location(company)
    territory = "Indonesia"
    if not frappe.db.exists("Territory", territory):
        territory = frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"

    cust_doc = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": customer_name,
        "customer_type": customer_type,
        "customer_group": cust_group,
        "territory": territory,
    })
    cust_doc.flags.ignore_permissions = True
    cust_doc.insert(ignore_permissions=True)
    created_cust_name = cust_doc.name

    # Buat Contact primer
    from erpnext.selling.doctype.customer.customer import make_address, make_contact, parse_full_name

    contact_args = frappe._dict({
        "doctype": "Customer",
        "name": created_cust_name,
        "customer_name": customer_name,
        "customer_type": customer_type,
        "mobile_no": mobile_no,
        "phone": mobile_no,
        "flags": {"ignore_permissions": True},
    })
    if customer_type == "Company":
        contact_args["company_name"] = customer_name
        if contact_person:
            first, middle, last = parse_full_name(contact_person)
            contact_args["first_name"] = first
            if middle:
                contact_args["middle_name"] = middle
            if last:
                contact_args["last_name"] = last

    try:
        contact = make_contact(contact_args, is_primary_contact=1)
        if customer_type == "Company" and contact_person:
            first, middle, last = parse_full_name(contact_person)
            if middle:
                contact.db_set("middle_name", middle)
                contact.db_set("full_name", contact_person)
        cust_doc.db_set("customer_primary_contact", contact.name)
        if mobile_no:
            cust_doc.db_set("mobile_no", mobile_no)
    except Exception as exc:
        log_exception("AIOS Make Primary Contact", exc=exc)
        raise DraftExecutionError("CONTACT_CREATION_FAILED", f"Gagal membuat kontak primer customer: {exc}") from exc

    if not cust_doc.customer_primary_contact or not frappe.db.exists("Contact", cust_doc.customer_primary_contact):
        raise DraftExecutionError("CONTACT_CREATION_FAILED", "Kontak primer customer tidak terisi atau gagal disimpan.")

    # Buat Address primer
    if not address_str:
        raise DraftExecutionError("ADDRESS_REQUIRED", "Alamat pengiriman wajib diisi untuk membuat customer baru.")

    city = ""
    parts = [p.strip() for p in address_str.split(",") if p.strip()]
    if len(parts) >= 2:
        city = parts[-1]
    if not city and comp_city:
        city = comp_city

    country = comp_country or "Indonesia"
    if not city or city.lower() in {country.lower(), "indonesia"}:
        raise DraftExecutionError(
            "CITY_REQUIRED",
            "Kota pada alamat pengiriman tidak ditemukan. Mohon sertakan nama kota pada alamat pengiriman (contoh: Jalan Sukabumi No. 10, Bandung).",
        )

    addr_args = frappe._dict({
        "doctype": "Customer",
        "name": created_cust_name,
        "customer_name": customer_name,
        "address_line1": address_str,
        "city": city,
        "country": country,
        "flags": {"ignore_permissions": True},
    })
    try:
        address = make_address(addr_args, is_primary_address=1, is_shipping_address=1)
        cust_doc.db_set("customer_primary_address", address.name)
        cust_doc.db_set("primary_address", address_str)
    except Exception as exc:
        log_exception("AIOS Make Primary Address", exc=exc)
        raise DraftExecutionError("ADDRESS_CREATION_FAILED", f"Gagal membuat alamat primer customer: {exc}") from exc

    if not cust_doc.customer_primary_address or not frappe.db.exists("Address", cust_doc.customer_primary_address):
        raise DraftExecutionError("ADDRESS_CREATION_FAILED", "Alamat primer customer tidak terisi atau gagal disimpan.")

    return created_cust_name


_PPN_RATE = 11.0


def _pick_ppn_11_template(company: str) -> str | None:
    """Cari Sales Taxes and Charges Template aktif milik company dengan PPN 11% On Net Total."""
    candidates = frappe.get_all(
        "Sales Taxes and Charges Template",
        filters={"company": company, "disabled": 0},
        fields=["name", "title", "is_default"],
        order_by="is_default desc, name asc",
    )
    scored: list[tuple[tuple[int, int, int, str], str]] = []
    for row in candidates:
        tpl_doc = frappe.get_doc("Sales Taxes and Charges Template", row.name)
        matching_rows = [
            tax
            for tax in (tpl_doc.get("taxes") or [])
            if tax.charge_type == "On Net Total"
            and abs(float(tax.rate or 0) - _PPN_RATE) < 1e-6
            and int(tax.included_in_print_rate or 0) == 0
        ]
        if not matching_rows:
            continue
        title_lower = str(row.get("title") or "").strip().lower()
        is_sales_tax = int(
            title_lower == "sales tax"
            or any(
                "keluaran" in f"{tax.account_head or ''} {tax.description or ''}".lower()
                for tax in matching_rows
            )
        )
        not_purchase_tax = int(
            "purchase" not in title_lower
            and all(
                "masukan" not in f"{tax.account_head or ''} {tax.description or ''}".lower()
                for tax in matching_rows
            )
        )
        scored.append(((is_sales_tax, not_purchase_tax, int(row.get("is_default") or 0), str(row.name)), str(row.name)))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _resolve_sales_tax_template(company: str) -> str:
    """Resolve or create the official ERPNext PPN 11% Sales Taxes and Charges Template for `company`."""
    if not company:
        raise DraftExecutionError("COMPANY_NOT_CONFIGURED", "Company default belum dikonfigurasi.")

    template_name = _pick_ppn_11_template(company)
    if not template_name:
        from erpnext.setup.setup_wizard.operations.taxes_setup import (
            make_taxes_and_charges_template,
            setup_taxes_and_charges,
        )

        try:
            setup_taxes_and_charges(company, "Indonesia")
        except Exception as exc:
            log_exception("AIOS Setup Taxes And Charges", exc=exc, context=f"company={company}")

        template_name = _pick_ppn_11_template(company)
        if not template_name:
            try:
                make_taxes_and_charges_template(
                    company,
                    "Sales Taxes and Charges Template",
                    {
                        "title": "Sales Tax",
                        "is_default": 1,
                        "taxes": [{"account_head": {"account_name": "PPN Keluaran", "tax_rate": _PPN_RATE}}],
                    },
                )
            except Exception as exc:
                log_exception("AIOS Make Sales Tax Template", exc=exc, context=f"company={company}")
                raise DraftExecutionError(
                    "TAX_TEMPLATE_SETUP_FAILED",
                    f"Gagal menyiapkan template PPN 11% untuk company {company}.",
                ) from exc
            template_name = _pick_ppn_11_template(company)

    if not template_name:
        raise DraftExecutionError(
            "TAX_TEMPLATE_MISSING",
            f"Template pajak PPN 11% tidak ditemukan untuk company {company}.",
        )

    if not frappe.db.exists(
        "Sales Taxes and Charges Template",
        {"company": company, "disabled": 0, "is_default": 1},
    ):
        frappe.db.set_value(
            "Sales Taxes and Charges Template",
            template_name,
            "is_default",
            1,
            update_modified=False,
        )
    return template_name


def _calculate_sales_tax_breakdown(
    doctype: str,
    company: str,
    currency: str,
    price_list: str | None,
    items: list[dict],
    taxes_and_charges: str | None = None,
) -> dict:
    """Calculate base total, PPN 11% tax, and grand total using ERPNext's in-memory tax controller."""
    tax_template = str(taxes_and_charges or "").strip() or _resolve_sales_tax_template(company)
    temp_items = []
    for it in items:
        qty_val = float(it.get("qty") or 0)
        rate_val = float(it.get("rate") or 0)
        uom_val = str(it.get("uom") or "").strip() or "Nos"
        temp_items.append(
            {
                "item_code": it.get("item_code"),
                "item_name": it.get("item_name") or it.get("item_code"),
                "qty": qty_val,
                "uom": uom_val,
                "stock_uom": uom_val,
                "conversion_factor": 1.0,
                "rate": rate_val,
                "price_list_rate": rate_val,
            }
        )

    doc_dict = {
        "doctype": doctype,
        "company": company,
        "currency": currency,
        "conversion_rate": 1.0,
        "selling_price_list": price_list or "Standard Selling",
        "price_list_currency": currency,
        "plc_conversion_rate": 1.0,
        "taxes_and_charges": tax_template,
        "items": temp_items,
    }
    temp_doc = frappe.get_doc(doc_dict)
    if tax_template and hasattr(temp_doc, "append_taxes_from_master"):
        temp_doc.append_taxes_from_master()
    if hasattr(temp_doc, "calculate_taxes_and_totals"):
        temp_doc.calculate_taxes_and_totals()

    base_total = float(temp_doc.get("net_total") or temp_doc.get("total") or 0.0)
    tax_amount = float(temp_doc.get("total_taxes_and_charges") or 0.0)
    grand_total = float(
        temp_doc.get("rounded_total") or temp_doc.get("grand_total") or (base_total + tax_amount)
    )
    return {
        "base_total": base_total,
        "tax_amount": tax_amount,
        "grand_total": grand_total,
        "taxes_and_charges": tax_template,
    }


def _create_and_submit(doctype: str, data: dict, company: str) -> dict:
    business_data = dict(data)
    business_data.pop("company", None)
    if doctype == "Quotation":
        if "customer" in business_data and not business_data.get("party_name"):
            business_data["party_name"] = business_data.pop("customer")
        else:
            business_data.pop("customer", None)
        if frappe.get_meta("Quotation").has_field("quotation_to") and not business_data.get("quotation_to"):
            business_data["quotation_to"] = "Customer"
    if (
        doctype in {"Sales Order", "Quotation"}
        and frappe.get_meta(doctype).has_field("taxes_and_charges")
        and not business_data.get("taxes_and_charges")
    ):
        business_data["taxes_and_charges"] = _resolve_sales_tax_template(company)
    validate_data_fields(frappe.get_meta(doctype), business_data)
    if doctype == "Sales Order" and not frappe.db.exists("Mode of Payment", "Cash"):
        raise DraftExecutionError(
            "MODE_OF_PAYMENT_CASH_MISSING",
            "Master Mode of Payment 'Cash' belum tersedia di sistem.",
        )
    target_data = {"doctype": doctype, **business_data}
    if frappe.get_meta(doctype).has_field("company"):
        target_data["company"] = company
    target = frappe.get_doc(target_data)
    if (
        doctype in {"Sales Order", "Quotation"}
        and target.get("taxes_and_charges")
        and not target.get("taxes")
        and hasattr(target, "append_taxes_from_master")
    ):
        target.append_taxes_from_master()
    target.flags.ignore_permissions = True
    target.insert(ignore_permissions=True)
    if doctype == "Sales Order":
        for row in target.get("payment_schedule") or []:
            row.mode_of_payment = "Cash"
    target.flags.ignore_permissions = True
    target.submit()
    res = {"doctype": doctype, "name": target.name, "docstatus": 1}
    if doctype in {"Sales Order", "Quotation"}:
        base_total = float(target.get("net_total") or target.get("total") or 0)
        tax_amount = float(target.get("total_taxes_and_charges") or 0)
        grand_total = float(target.get("rounded_total") or target.get("grand_total") or 0)
        res["net_total"] = base_total
        res["base_total"] = base_total
        res["total_taxes_and_charges"] = tax_amount
        res["tax_amount"] = tax_amount
        res["grand_total"] = grand_total
        res["rounded_total"] = float(target.get("rounded_total") or grand_total)
        res["taxes_and_charges"] = str(target.get("taxes_and_charges") or "")
        res["currency"] = str(target.get("currency") or "IDR")
        if doctype == "Sales Order":
            res["delivery_date"] = str(target.get("delivery_date") or "")
        elif doctype == "Quotation":
            res["valid_till"] = str(target.get("valid_till") or "")
    return res


def execute_draft(doc) -> dict:
    """Execute an approved CREATE, UPDATE_DRAFT, or CANCEL_AND_AMEND."""
    if doc.type not in ACTION_TYPES:
        raise DraftExecutionError("ACTION_TYPE_UNSUPPORTED", "Jenis aksi draft tidak dikenal.")
    try:
        payload = json.loads(doc.payload or "{}")
    except (TypeError, ValueError) as exc:
        log_exception("AIOS Draft Execution", exc=exc)
        raise DraftExecutionError("DRAFT_INVALID", "Payload draft bukan JSON valid.")
    if not isinstance(payload, dict):
        raise DraftExecutionError("DRAFT_INVALID", "Payload draft bukan object JSON.")

    doctype = payload.get("doctype")
    data = payload.get("data")
    if doctype not in ALLOWED_DRAFT_DOCTYPES or not isinstance(data, dict):
        raise DraftExecutionError("DRAFT_INVALID", "Payload draft tidak valid.")
    company = _site_company()
    if doc.type == "CREATE":
        if doctype in {"Sales Order", "Quotation"}:
            resolved_customer = _ensure_customer_for_draft(payload, company)
            if doctype == "Quotation":
                data.pop("customer", None)
                if frappe.get_meta("Quotation").has_field("quotation_to") and not data.get("quotation_to"):
                    data["quotation_to"] = "Customer"
                if resolved_customer and frappe.get_meta("Quotation").has_field("party_name"):
                    data["party_name"] = resolved_customer
            elif resolved_customer:
                data["customer"] = resolved_customer
        return _create_and_submit(doctype, data, company)

    name = payload.get("name")
    if not isinstance(name, str) or not name:
        raise DraftExecutionError("DRAFT_INVALID", "Nama dokumen target tidak valid.")
    target = _load_target(doctype, name, company)
    expected_docstatus = 0 if doc.type == "UPDATE_DRAFT" else 1
    if int(target.docstatus or 0) != expected_docstatus:
        raise DraftExecutionError("DOCSTATUS_MISMATCH", "Status dokumen berubah sejak draft dibuat.")
    _assert_snapshot_current(target, payload.get("before"))
    validate_data_fields(target.meta, data)

    if doc.type == "UPDATE_DRAFT":
        target.update(data)
        target.flags.ignore_permissions = True
        target.save(ignore_permissions=True)
        return {"doctype": doctype, "name": target.name, "docstatus": 0}

    try:
        period_closed = _period_is_closed(target, company)
    except DraftExecutionError:
        raise
    except Exception as exc:
        log_exception("AIOS Draft Period Check", exc=exc)
        raise DraftExecutionError(
            "PERIOD_CHECK_FAILED", "Status periode akuntansi tidak dapat diverifikasi."
        )
    if period_closed:
        raise DraftExecutionError(
            "PERIOD_CLOSED",
            "Periode dokumen sudah ditutup. Jangan batalkan; ajukan jurnal koreksi periode berjalan.",
        )
    from frappe.model.document import copy_doc

    replacement = copy_doc(target)
    replacement.docstatus = 0
    replacement.amended_from = target.name
    replacement.update(data)
    if replacement.meta.has_field("company"):
        replacement.company = company
    target.flags.ignore_permissions = True
    target.cancel()
    replacement.flags.ignore_permissions = True
    replacement.insert(ignore_permissions=True)
    replacement.flags.ignore_permissions = True
    replacement.submit()
    return {"doctype": doctype, "old_name": target.name,
            "new_name": replacement.name, "docstatus": 1}


def _notify_rejection(doc, reason: str) -> None:
    """Catat penolakan di percakapan terakhir user agar AI Manager tahu konteksnya."""
    # Kirim kabar proaktif ke Telegram bila draf berasal dari Telegram
    guest_msg = (
        f"Mohon maaf, pengajuan pesanan Anda belum dapat disetujui oleh tim kami.\n"
        f"Catatan dari tim kami: {reason or 'Perlu penyesuaian data pesanan'}.\n\n"
        f"Anda tidak perlu mengulang seluruh pesanan Anda. Silakan sampaikan perbaikan data di atas "
        f"agar kami dapat langsung memperbarui pesanan Anda. Terima kasih!"
    )
    _send_proactive_guest_notification(doc, guest_msg)

    try:
        filters = {"user": doc.user}
        if doc.branch:
            filters["branch"] = doc.branch
        conversations = frappe.get_all(
            "AIOS Conversation",
            filters=filters,
            order_by="modified desc",
            limit=1,
            pluck="name",
        )
        if not conversations:
            frappe.log_error(
                f"Draft {doc.name} ditolak tanpa conversation untuk {doc.user}.",
                "AIOS Draft Manager",
            )
            return

        content = (
            f"[DRAFT DITOLAK] Draf {doc.type} ({doc.name}) ditolak. "
            f"Alasan: {reason or 'tidak disebutkan'}. "
            "Susun alternatif atau konfirmasi ulang ke pengguna sebelum mengusulkan aksi baru."
        )
        frappe.get_doc(
            {
                "doctype": "AIOS Message",
                "conversation": conversations[0],
                "role": "manager",
                "worker_key": "manager",
                "content": content,
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "AIOS Draft Notification")


def _send_proactive_guest_notification(doc, message: str) -> bool:
    """Kirim kabar proaktif ke customer Telegram bila draf berasal dari kanal Telegram."""
    if not doc:
        return False
    try:
        payload = json.loads(doc.payload or "{}") if isinstance(doc.payload, str) else (doc.payload or {})
    except Exception as exc:
        log_exception("AIOS Parse Draft Payload For Notification", exc=exc)
        payload = {}

    chat_id = payload.get("source_telegram_chat_id")
    if not chat_id:
        return False

    from aios_v1.lib.connector import telegram_client

    sent = telegram_client.send_message(chat_id, message)

    try:
        thread_conv = frappe.db.get_value(
            "AIOS Channel Thread",
            {"channel": "telegram", "external_thread_id": str(chat_id)},
            "conversation",
        )
        if thread_conv:
            frappe.get_doc(
                {
                    "doctype": "AIOS Message",
                    "conversation": thread_conv,
                    "role": "manager",
                    "worker_key": "manager",
                    "content": message,
                }
            ).insert(ignore_permissions=True)
            frappe.db.commit()
    except Exception as exc:
        log_exception("AIOS Draft Notification Conversation Log", exc=exc)

    return sent


def expire_old_drafts():
    """Cron job: Ubah status draft yang melewati batas expires_at jadi EXPIRED."""
    now = now_datetime()
    drafts = frappe.get_all(
        "Pending Action Draft",
        filters={"status": "PENDING_APPROVAL", "expires_at": ["<", now]},
        limit_page_length=0,
    )
    for d in drafts:
        frappe.db.set_value("Pending Action Draft", d.name, "status", "EXPIRED")

    if drafts:
        frappe.db.commit()
        frappe.log_error(f"{len(drafts)} drafts expired.", "AIOS Draft Manager")


@frappe.whitelist()
def get_draft(draft_id: str) -> dict:
    """Ambil detail draf; hanya pemilik atau Administrator."""
    doc = frappe.get_doc("Pending Action Draft", draft_id, check_permission="read")
    _assert_draft_owner(doc)
    return doc.as_dict()


@frappe.whitelist()
def list_pending_drafts(limit: int = 50, status: str | None = None) -> list:
    """Daftar draft milik pemanggil (owner-scoped), default status PENDING_APPROVAL, terbaru dulu.

    Detail isi draf diambil UI lewat `get_draft` — doctype/aksi ada di dalam
    `payload` dan tidak di-expose di sini. Untuk status EXECUTED / HISTORY, hanya
    `document_doctype` dan `document_name` hasil eksekusi yang diproyeksikan.
    """
    allowed_statuses = {
        "PENDING_APPROVAL",
        "EXPIRED",
        "APPROVED",
        "EXECUTED",
        "REJECTED",
        "HISTORY",
    }
    resolved_status = (status or "PENDING_APPROVAL").strip().upper()
    if resolved_status not in allowed_statuses:
        frappe.throw(
            "Status daftar draf hanya mendukung PENDING_APPROVAL, EXPIRED, APPROVED, EXECUTED, REJECTED, atau HISTORY."
        )

    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        log_exception("AIOS Draft List Limit", exc=exc)
        limit = 50
    limit = max(1, min(limit, 100))

    status_filter = (
        ["in", ["APPROVED", "EXECUTED", "REJECTED"]]
        if resolved_status == "HISTORY"
        else resolved_status
    )
    # D6: draf cabang yang dimatikan disembunyikan dari daftar (tidak dihapus).
    # Draf tanpa branch tidak terikat cabang mana pun, jadi tetap ditampilkan.
    from aios_v1.lib.branch_activation import get_active_branches

    active_branches = sorted(get_active_branches())
    rows = frappe.get_all(
        "Pending Action Draft",
        filters={
            "user": frappe.session.user,
            "status": status_filter,
            "branch": ["in", [*active_branches, ""]],
        },
        fields=["name", "type", "branch", "status", "expires_at", "creation", "modified", "payload"],
        order_by="creation desc",
        limit_page_length=limit,
    )
    now_dt = now_datetime()
    for row in rows:
        expires_dt = get_datetime(row.get("expires_at")) if row.get("expires_at") else None
        row["expired"] = bool(expires_dt and expires_dt < now_dt)
        raw_payload = row.pop("payload", None)
        if row.get("status") == "EXECUTED" and isinstance(raw_payload, str) and raw_payload.strip():
            try:
                parsed = json.loads(raw_payload)
            except (TypeError, ValueError) as exc:
                log_exception("AIOS Draft List Result Payload", exc=exc)
                parsed = None
            result_obj = parsed.get("result") if isinstance(parsed, dict) else None
            if isinstance(result_obj, dict):
                doc_doctype = result_obj.get("doctype")
                doc_name = result_obj.get("document") or result_obj.get("name") or result_obj.get("new_name")
                if isinstance(doc_doctype, str) and doc_doctype:
                    row["document_doctype"] = doc_doctype
                if isinstance(doc_name, str) and doc_name:
                    row["document_name"] = doc_name
    return rows


@frappe.whitelist()
def close_expired_draft(draft_id: str) -> dict:
    """Tutup draf PENDING_APPROVAL yang sudah kedaluwarsa menjadi EXPIRED tanpa notifikasi."""
    doc = frappe.get_doc(DRAFT_DOCTYPE, draft_id, check_permission="read")
    _assert_draft_owner(doc)
    if doc.status != "PENDING_APPROVAL":
        frappe.throw(f"Draft tidak bisa ditutup karena berstatus {doc.status}.")

    expires_dt = get_datetime(doc.expires_at) if doc.expires_at else None
    if not expires_dt or expires_dt >= now_datetime():
        frappe.throw("Draft belum kedaluwarsa sehingga tidak bisa ditutup.")

    frappe.db.set_value(DRAFT_DOCTYPE, doc.name, "status", "EXPIRED")
    frappe.db.commit()
    return {
        "status": "success",
        "draft_id": doc.name,
        "draft_status": "EXPIRED",
        "message": f"Draf kedaluwarsa {doc.name} telah ditutup (status: EXPIRED).",
    }


def _is_channel_draft(draft_name: str) -> bool:
    if not draft_name or not frappe.db.exists("DocType", "Notification Log"):
        return False
    return bool(
        frappe.db.exists(
            "Notification Log",
            {
                "type": "AIOS Channel Alert",
                "document_type": "Pending Action Draft",
                "document_name": draft_name,
            },
        )
    )


def _assert_draft_owner(doc) -> None:
    user = frappe.session.user
    if user != "Administrator" and doc.user != user:
        from aios_v1.lib.connector.notify import get_channel_recipients

        if user in set(get_channel_recipients()) and _is_channel_draft(doc.name):
            return
        frappe.throw("Draft tidak ditemukan.", frappe.PermissionError)


def _lock_draft(draft_id: str):
    """Serialize approval/retry requests for one draft within this transaction."""
    frappe.db.sql(
        "select name from `tabPending Action Draft` where name = %s for update",
        (draft_id,),
    )
    return frappe.get_doc(DRAFT_DOCTYPE, draft_id, check_permission="write")


@frappe.whitelist()
def approve_and_execute_draft(draft_id: str) -> dict:
    """Owner approves and executes a draft once; failed APPROVED drafts can retry."""
    doc = _lock_draft(draft_id)
    _assert_draft_owner(doc)
    if doc.status == "EXECUTED":
        try:
            payload = json.loads(doc.payload or "{}")
            result = payload.get("result") if isinstance(payload, dict) else None
        except (TypeError, ValueError) as exc:
            log_exception("AIOS Draft Idempotency", exc=exc)
            result = None
        if not isinstance(result, dict):
            frappe.log_error(f"Hasil eksekusi hilang pada draft {draft_id}.", "AIOS Draft Idempotency")
            frappe.throw("Hasil draft yang sudah dieksekusi tidak tersedia.")
        return result
    if doc.status not in {"PENDING_APPROVAL", "APPROVED"}:
        frappe.throw(f"Draft tidak bisa di-approve karena berstatus {doc.status}.")
    if doc.status == "PENDING_APPROVAL" and doc.expires_at and doc.expires_at < now_datetime():
        doc.status = "EXPIRED"
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.throw("Draft sudah kedaluwarsa.")

    doc.status = "APPROVED"
    doc.save(ignore_permissions=True)

    frappe.db.savepoint("aios_draft_execution")
    try:
        executed = execute_draft(doc)
    except Exception as exc:
        frappe.db.rollback(save_point="aios_draft_execution")
        frappe.db.commit()
        log_exception("AIOS Draft Execution", exc=exc)

        error_desc = str(exc) if isinstance(exc, DraftExecutionError) else "Kendala teknis pada validasi data pesanan"
        guest_msg = (
            f"Halo! Ada sedikit kendala saat kami memproses pesanan Anda: {error_desc}.\n\n"
            f"Anda tidak perlu mengulang pesanan dari awal. Cukup informasikan perbaikan data tersebut kepada kami di sini "
            f"agar kami dapat segera melanjutkan proses pesanan Anda. Terima kasih!"
        )
        _send_proactive_guest_notification(doc, guest_msg)

        return {
            "status": "APPROVED",
            "draft_status": "APPROVED",
            "executed": False,
            "code": getattr(exc, "code", "DRAFT_EXECUTION_FAILED"),
            "message": str(exc) if isinstance(exc, DraftExecutionError)
            else "Draft disetujui, tetapi eksekusi ERPNext gagal. Detail ada di Error Log.",
        }

    doc.status = "EXECUTED"
    payload = json.loads(doc.payload or "{}")
    result = {
        "status": "success",
        "draft_status": "EXECUTED",
        "executed": True,
        **executed,
        "document": executed.get("name") or executed.get("new_name"),
        "message": f"Draft {draft_id} berhasil dieksekusi.",
    }
    payload["result"] = result
    doc.payload = json.dumps(payload, default=str)
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    if doc.type == "CREATE" and payload.get("doctype") == "Sales Order":
        currency_code = result.get("currency") or "IDR"
        formatted_base = _format_currency_amount(
            result.get("base_total") or result.get("net_total") or 0,
            currency_code,
        )
        formatted_tax = _format_currency_amount(
            result.get("tax_amount") or result.get("total_taxes_and_charges") or 0,
            currency_code,
        )
        formatted_total = _format_currency_amount(
            result.get("grand_total") or 0,
            currency_code,
        )
        delivery_date_str = str(
            result.get("delivery_date")
            or (payload.get("data") or {}).get("delivery_date")
            or "-"
        )
        guest_approve_msg = (
            f"Halo! Pesanan Anda telah disetujui. "
            f"Harga Dasar: {formatted_base}. "
            f"PPN 11%: {formatted_tax}. "
            f"Total Pembayaran: {formatted_total}. "
            f"Rencana Tanggal Pengiriman: {delivery_date_str}. "
            f"Metode Pembayaran: Cash (Tunai). "
            f"Mohon melakukan pembayaran Cash dan konfirmasi pembayaran terlebih dahulu sebelum pesanan dikirim. "
            f"Apabila sampai tanggal pengiriman pembayaran belum dikonfirmasi, maka pengiriman pesanan akan ditahan. Terima kasih."
        )
        _send_proactive_guest_notification(doc, guest_approve_msg)
    elif doc.type == "CREATE" and payload.get("doctype") == "Quotation":
        currency_code = result.get("currency") or "IDR"
        formatted_base = _format_currency_amount(
            result.get("base_total") or result.get("net_total") or 0,
            currency_code,
        )
        formatted_tax = _format_currency_amount(
            result.get("tax_amount") or result.get("total_taxes_and_charges") or 0,
            currency_code,
        )
        formatted_total = _format_currency_amount(
            result.get("grand_total") or 0,
            currency_code,
        )
        valid_till_str = str(
            result.get("valid_till")
            or (payload.get("data") or {}).get("valid_till")
            or "-"
        )
        guest_quote_msg = (
            f"Halo! Penawaran harga Anda telah disetujui. "
            f"Harga Dasar: {formatted_base}. "
            f"PPN 11%: {formatted_tax}. "
            f"Total Penawaran: {formatted_total}. "
            f"Berlaku Hingga: {valid_till_str}. "
            f"Silakan hubungi kami apabila Anda ingin melanjutkan ke pemesanan. Terima kasih."
        )
        _send_proactive_guest_notification(doc, guest_quote_msg)

    return result


def _format_currency_amount(amount: float | int, currency: str = "IDR") -> str:
    val = round(float(amount or 0))
    formatted_num = f"{val:,}".replace(",", ".")
    prefix = "Rp" if str(currency or "IDR").upper() == "IDR" else str(currency).upper()
    return f"{prefix} {formatted_num}"


@frappe.whitelist()
def confirm_draft_cash_payment(draft_id: str) -> dict:
    """Konfirmasi pembayaran Cash oleh staf untuk draf Sales Order yang sudah EXECUTED (Jalan B)."""
    if frappe.session.user == "Guest":
        frappe.throw("Tamu tidak diizinkan mengonfirmasi pembayaran.", frappe.PermissionError)

    doc = _lock_draft(draft_id)
    _assert_draft_owner(doc)

    if doc.status != "EXECUTED":
        frappe.throw(
            f"Konfirmasi pembayaran hanya berlaku untuk draf berstatus EXECUTED (status saat ini: {doc.status})."
        )

    try:
        payload = json.loads(doc.payload or "{}")
    except (TypeError, ValueError) as exc:
        log_exception("AIOS Confirm Cash Payment Parse Payload", exc=exc)
        frappe.throw("Payload draf tidak valid.")

    if doc.type != "CREATE" or payload.get("doctype") != "Sales Order":
        frappe.throw("Konfirmasi pembayaran Cash hanya berlaku untuk draf pembuatan Sales Order.")

    result_obj = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    so_name = result_obj.get("name") or result_obj.get("document")
    if not so_name or not frappe.db.exists("Sales Order", so_name):
        frappe.throw("Dokumen Sales Order tidak ditemukan.")

    existing_pe = result_obj.get("payment_entry")
    if existing_pe and frappe.db.exists("Payment Entry", existing_pe):
        return {
            "status": "success",
            "payment_entry": existing_pe,
            "sales_order": so_name,
            "payment_confirmed": True,
            "already_paid": True,
            "message": f"Pembayaran Cash untuk {so_name} sudah tercatat pada {existing_pe}.",
        }

    existing_pe_refs = frappe.get_all(
        "Payment Entry Reference",
        filters={"reference_doctype": "Sales Order", "reference_name": so_name, "docstatus": 1},
        pluck="parent",
        limit=1,
    )
    if existing_pe_refs:
        pe_name = existing_pe_refs[0]
        result_obj["payment_entry"] = pe_name
        result_obj["payment_confirmed"] = True
        payload["result"] = result_obj
        doc.payload = json.dumps(payload, default=str)
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {
            "status": "success",
            "payment_entry": pe_name,
            "sales_order": so_name,
            "payment_confirmed": True,
            "already_paid": True,
            "message": f"Pembayaran Cash untuk {so_name} sudah tercatat pada {pe_name}.",
        }

    if not frappe.db.exists("Mode of Payment", "Cash"):
        frappe.throw("Master Mode of Payment 'Cash' belum tersedia di sistem.")

    from erpnext.accounts.doctype.journal_entry.journal_entry import get_default_bank_cash_account
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
    from frappe.utils import nowdate

    company = _site_company()
    prev_user = frappe.session.user
    # E1 (disetujui Ten 11 Nov 2026): `frappe.set_user` menimpa
    # `local.session.sid` dengan username dan mengosongkan `local.session.data`
    # (frappe/__init__.py:386-392). Karena `local.session` adalah objek yang
    # sama dengan `session_obj.data` (frappe/auth.py:239), kerusakan itu ikut
    # dipersist `Session.update` ke Redis setelah response (frappe/app.py:471-472,
    # frappe/sessions.py:445) -> request berikutnya tidak me-resume sesi staf.
    # Simpan & pulihkan state sesi di finally, sempit hanya di sekitar blok
    # elevasi hak. Tidak mengubah logika bisnis payment.
    session = frappe.local.session
    saved_session = session.copy()
    saved_session["data"] = (
        session.data.copy() if isinstance(getattr(session, "data", None), dict) else frappe._dict()
    )
    form_dict = frappe.local.form_dict
    frappe.db.savepoint("aios_confirm_cash_payment")
    try:
        try:
            frappe.set_user("Administrator")
            cash_acc_info = get_default_bank_cash_account(
                company,
                "Cash",
                mode_of_payment="Cash",
                fetch_balance=False,
            )
            cash_account = (cash_acc_info or {}).get("account")
            pe = get_payment_entry("Sales Order", so_name, bank_account=cash_account)
            pe.payment_type = "Receive"
            pe.mode_of_payment = "Cash"
            pe.reference_no = so_name
            pe.reference_date = nowdate()
        finally:
            # Pulihkan seluruh state sesi yang ditimpa `set_user` (user, sid,
            # data/form_dict/cache) sebelum `insert()` & `submit()` agar `owner`
            # dan `modified_by` tercatat sebagai karyawan pelaksana, bukan Administrator.
            frappe.set_user(prev_user)
            session.update(saved_session)
            frappe.local.session = session
            frappe.local.form_dict = form_dict
            frappe.local.cache = {}
            frappe.local.role_permissions = {}
            frappe.local.user_perms = None

        pe.flags.ignore_permissions = True
        pe.insert(ignore_permissions=True)
        pe.flags.ignore_permissions = True
        pe.submit()
    except Exception as exc:
        frappe.db.rollback(save_point="aios_confirm_cash_payment")
        log_exception("AIOS Confirm Draft Cash Payment", exc=exc)
        raise

    result_obj["payment_entry"] = pe.name
    result_obj["payment_confirmed"] = True
    payload["result"] = result_obj
    doc.payload = json.dumps(payload, default=str)
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    formatted_paid = _format_currency_amount(
        pe.paid_amount or result_obj.get("grand_total") or 0,
        result_obj.get("currency") or "IDR",
    )
    delivery_date_str = str(
        result_obj.get("delivery_date")
        or (payload.get("data") or {}).get("delivery_date")
        or "-"
    )
    guest_paid_msg = (
        f"Halo! Pembayaran Cash Anda sebesar {formatted_paid} telah kami terima. "
        f"Pesanan Anda siap diproses untuk pengiriman sesuai jadwal pada tanggal {delivery_date_str}. "
        f"Terima kasih."
    )
    _send_proactive_guest_notification(doc, guest_paid_msg)

    return {
        "status": "success",
        "payment_entry": pe.name,
        "sales_order": so_name,
        "payment_confirmed": True,
        "already_paid": False,
        "message": f"Pembayaran Cash berhasil dikonfirmasi ({pe.name}).",
    }


@frappe.whitelist()
def reject_draft(draft_id: str, reason: str = "") -> dict:
    """Reject draf hanya untuk pemilik atau Administrator."""
    doc = _lock_draft(draft_id)
    _assert_draft_owner(doc)
    if doc.status not in ("PENDING_APPROVAL", "APPROVED"):
        frappe.throw(f"Draft tidak bisa di-reject karena berstatus {doc.status}.")

    doc.status = "REJECTED"
    doc.rejection_reason = reason
    doc.save()
    _notify_rejection(doc, reason)
    frappe.db.commit()

    return {"status": "success", "message": f"Draft {draft_id} telah di-reject."}


# Alias lama; frontend `DraftCard` masih memanggil nama ini sampai `#12`.
approve_draft = approve_and_execute_draft
