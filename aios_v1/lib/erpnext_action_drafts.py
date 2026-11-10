"""Create approval drafts without writing an ERPNext business document."""

import json
import uuid

import frappe

from aios_v1.lib.draft_manager import ALLOWED_DRAFT_DOCTYPES, create_draft, validate_data_fields
from aios_v1.lib.error_utils import log_exception, safe_error
from aios_v1.lib.tool_registry import ai_tool, get_tool_context


@ai_tool(
    name="erpnext_action_draft_create",
    description=(
        "Membuat Pending Action Draft untuk ditinjau manusia; tidak menulis ke ERPNext. "
        "Pastikan seluruh nama field pada 'data' sesuai dengan skema DocType target. "
        "Jika belum yakin atau menerima error validasi field, panggil 'erpnext_doctype_schema' terlebih dahulu "
        "(misal: Quotation menggunakan 'party_name' dan 'quotation_to', bukan 'customer')."
    ),
    branch=["finance", "sales"],
    plugin_key="erpnext-action-drafts",
    parameters={
        "action_type": {
            "type": "string",
            "enum": ["CREATE", "UPDATE_DRAFT", "CANCEL_AND_AMEND"],
            "description": "Jenis aksi yang memerlukan persetujuan manusia",
        },
        "doctype": {
            "type": "string",
            "enum": sorted(ALLOWED_DRAFT_DOCTYPES),
            "description": "DocType ERPNext yang diizinkan",
        },
        "name": {"type": "string", "description": "Nama dokumen target untuk UPDATE_DRAFT/CANCEL_AND_AMEND", "required": False},
        "data": {"type": "object", "description": "Nilai dokumen yang diusulkan"},
        "reason": {"type": "string", "description": "Alasan bisnis aksi", "required": False},
        "customer_info": {
            "type": "object",
            "description": (
                "Data pelanggan baru (hanya untuk CREATE Sales Order atau Quotation). "
                "Jangan masukkan ke 'data'. Berisi: customer_type ('Individual' atau 'Company'), "
                "customer_name, contact_person (opsional), mobile_no, address."
            ),
            "required": False,
        },
    },
)
def erpnext_action_draft_create(action_type, doctype, data, reason="", name=None, customer_info=None):
    ctx_user = get_tool_context().get("user_id")
    sess_user = getattr(frappe.session, "user", None)
    is_guest = (ctx_user == "Guest" or sess_user == "Guest")

    if is_guest:
        if action_type != "CREATE":
            return safe_error("Tamu hanya diizinkan membuat draf baru (CREATE).", "ACTION_FORBIDDEN_FOR_GUEST")
        if doctype not in {"Sales Order", "Quotation"}:
            return safe_error("Tamu hanya diizinkan membuat draf pemesanan Sales Order atau Quotation.", "DOCTYPE_FORBIDDEN_FOR_GUEST")

    if action_type not in {"CREATE", "UPDATE_DRAFT", "CANCEL_AND_AMEND"}:
        return safe_error("Jenis aksi draft tidak didukung.", "ACTION_TYPE_UNSUPPORTED")
    if doctype not in ALLOWED_DRAFT_DOCTYPES:
        frappe.throw("DocType ini tidak diizinkan untuk draf AIOS.")
    if not isinstance(data, dict):
        frappe.throw("data harus berupa object.")
    if action_type != "CREATE" and (not isinstance(name, str) or not name.strip()):
        frappe.throw("name wajib untuk UPDATE_DRAFT dan CANCEL_AND_AMEND.")
    if action_type != "CREATE" and (not isinstance(reason, str) or not reason.strip()):
        frappe.throw("reason wajib untuk UPDATE_DRAFT dan CANCEL_AND_AMEND.")

    company = str(
        get_tool_context().get("allowed_company")
        or frappe.db.get_single_value("AIOS Setting", "default_company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
        or (data.get("company") if isinstance(data, dict) else "")
        or ""
    ).strip()
    if not company:
        frappe.throw("Company default belum dikonfigurasi.")

    validated_customer_info = None
    if customer_info is not None:
        if isinstance(customer_info, str) and customer_info.strip().startswith("{"):
            try:
                customer_info = json.loads(customer_info)
            except Exception as exc:
                log_exception("AIOS Parse customer_info JSON", exc=exc)
        if action_type != "CREATE" or doctype not in {"Sales Order", "Quotation"}:
            frappe.throw("customer_info hanya diizinkan untuk pembuatan draf (CREATE) Sales Order atau Quotation.")
        if not isinstance(customer_info, dict):
            frappe.throw("customer_info harus berupa object.")

        c_type = str(customer_info.get("customer_type") or "").strip()
        if c_type not in {"Individual", "Company"}:
            if is_guest:
                return safe_error("Tipe pelanggan untuk tamu harus 'Individual' atau 'Company'.", "INVALID_CUSTOMER_TYPE")
            frappe.throw("customer_type harus 'Individual' atau 'Company'.")

        c_name = str(customer_info.get("customer_name") or "").strip()
        if not c_name:
            frappe.throw("customer_name wajib ada pada customer_info.")

        c_mobile = str(customer_info.get("mobile_no") or "").strip()
        if not c_mobile:
            frappe.throw("mobile_no wajib ada pada customer_info.")

        c_address = str(customer_info.get("address") or "").strip()
        if not c_address:
            frappe.throw("address wajib ada pada customer_info.")

        validated_customer_info = {
            "customer_type": c_type,
            "customer_name": c_name,
            "mobile_no": c_mobile,
            "address": c_address,
            "contact_person": str(customer_info.get("contact_person") or "").strip(),
        }

    payload = {"doctype": doctype, "data": dict(data), "reason": reason or ""}
    if validated_customer_info:
        payload["customer_info"] = validated_customer_info

    channel_thread = getattr(frappe.local, "aios_channel_thread", None)
    if channel_thread:
        chat_id = (
            getattr(channel_thread, "external_thread_id", None)
            or (channel_thread.get("external_thread_id") if isinstance(channel_thread, dict) else None)
        )
        if chat_id:
            payload["source_telegram_chat_id"] = str(chat_id)

    if action_type == "CREATE":
        draft_data = dict(data)
        draft_data.pop("company", None)

        if doctype == "Sales Order":
            delivery_date = draft_data.get("delivery_date")
            if not delivery_date:
                if is_guest:
                    return safe_error(
                        "Tanggal pengiriman (delivery_date) wajib diisi untuk draf Sales Order.",
                        "DELIVERY_DATE_REQUIRED",
                    )
                frappe.throw("Tanggal pengiriman (delivery_date) wajib diisi untuk draf Sales Order.")

            from frappe.utils import getdate

            try:
                parsed_delivery_date = getdate(delivery_date)
                if not parsed_delivery_date:
                    raise ValueError()
                draft_data["delivery_date"] = str(parsed_delivery_date)
            except Exception as exc:
                log_exception("AIOS Parse Delivery Date", exc=exc)
                if is_guest:
                    return safe_error(
                        "Format tanggal pengiriman (delivery_date) tidak valid.",
                        "INVALID_DELIVERY_DATE",
                    )
                frappe.throw("Format tanggal pengiriman (delivery_date) tidak valid.")

            if draft_data.get("items") and isinstance(draft_data["items"], list):
                for itm in draft_data["items"]:
                    if isinstance(itm, dict) and not itm.get("delivery_date"):
                        itm["delivery_date"] = draft_data["delivery_date"]

        validate_data_fields(frappe.get_meta(doctype), draft_data)
        if frappe.get_meta(doctype).has_field("company"):
            draft_data["company"] = company
        payload["data"] = draft_data
    else:
        validate_data_fields(frappe.get_meta(doctype), data)
        target = frappe.get_doc(doctype, name, check_permission="read")
        if frappe.get_meta(doctype).has_field("company") and target.get("company") != company:
            frappe.throw("Dokumen tidak ditemukan untuk company aktif.")
        required_docstatus = 0 if action_type == "UPDATE_DRAFT" else 1
        if int(target.get("docstatus") or 0) != required_docstatus:
            frappe.throw("Status dokumen tidak sesuai untuk jenis aksi draft.")
        from aios_v1.lib.draft_manager import snapshot_fields

        payload.update({
            "name": name,
            "before": snapshot_fields(target, data),
        })
    tool_context = get_tool_context()
    draft_owner = None
    if is_guest:
        from aios_v1.lib.connector.notify import get_channel_recipients

        recipients = get_channel_recipients()
        draft_owner = recipients[0] if recipients else None

    draft = create_draft(
        task_id=f"AIOS-{uuid.uuid4()}",
        action_type=action_type,
        payload=payload,
        branch=tool_context.get("branch"),
        created_by_agent=tool_context.get("worker_key"),
        reason=reason,
        user=draft_owner,
    )
    if is_guest:
        from aios_v1.lib.connector.notify import notify_order_draft

        thread = getattr(frappe.local, "aios_channel_thread", None)
        notify_order_draft(draft, thread=thread)
    return {
        "status": "PENDING_APPROVAL",
        "draft_id": draft.name,
        "action_type": action_type,
        "doctype": doctype,
        "message": "Draf tersimpan untuk ditinjau; dokumen ERPNext belum dibuat.",
    }
