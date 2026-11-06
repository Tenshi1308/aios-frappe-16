"""Create approval drafts without writing an ERPNext business document."""

import uuid

import frappe

from aios_v1.lib.draft_manager import ALLOWED_DRAFT_DOCTYPES, create_draft, validate_data_fields
from aios_v1.lib.error_utils import safe_error
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
    },
)
def erpnext_action_draft_create(action_type, doctype, data, reason="", name=None):
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

    company = str(get_tool_context().get("allowed_company") or "").strip()
    if not company:
        frappe.throw("Company default belum dikonfigurasi.")
    payload = {"doctype": doctype, "data": dict(data), "reason": reason or ""}
    if action_type == "CREATE":
        draft_data = dict(data)
        draft_data.pop("company", None)
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
