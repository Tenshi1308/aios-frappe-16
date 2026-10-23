"""Create approval drafts without writing an ERPNext business document."""

import uuid

import frappe

from aios_v1.lib.draft_manager import create_draft
from aios_v1.lib.error_utils import safe_error
from aios_v1.lib.tool_registry import ai_tool, get_tool_context
from aios_v1.permissions import ERP_CLIENT_DOCTYPES


@ai_tool(
    name="erpnext_action_draft_create",
    description="Membuat Pending Action Draft untuk ditinjau manusia; tidak menulis ke ERPNext.",
    branch=["finance", "sales"],
    parameters={
        "action_type": {"type": "string", "description": "Jenis aksi; saat ini hanya CREATE"},
        "doctype": {"type": "string", "description": "DocType ERPNext yang diizinkan"},
        "data": {"type": "object", "description": "Nilai dokumen yang diusulkan"},
        "reason": {"type": "string", "description": "Alasan pembuatan draf", "required": False},
    },
)
def erpnext_action_draft_create(action_type, doctype, data, reason=""):
    if action_type != "CREATE":
        return safe_error("Pada PoC ini action_type yang didukung hanya CREATE.", "ACTION_TYPE_UNSUPPORTED")
    if doctype not in ERP_CLIENT_DOCTYPES:
        frappe.throw("DocType ini tidak diizinkan untuk draf AIOS.")
    if not isinstance(data, dict):
        frappe.throw("data harus berupa object.")

    company = str(get_tool_context().get("allowed_company") or "").strip()
    if not company:
        frappe.throw("Company default belum dikonfigurasi.")
    draft_data = dict(data)
    if frappe.get_meta(doctype).has_field("company"):
        draft_data["company"] = company
    payload = {"doctype": doctype, "data": draft_data}
    if reason:
        payload["reason"] = reason
    tool_context = get_tool_context()
    draft = create_draft(
        task_id=f"AIOS-{uuid.uuid4()}",
        action_type=action_type,
        payload=payload,
        branch=tool_context.get("branch"),
        created_by_agent=tool_context.get("worker_key"),
        reason=reason,
    )
    return {
        "status": "PENDING_APPROVAL",
        "draft_id": draft.name,
        "action_type": action_type,
        "doctype": doctype,
        "message": "Draf tersimpan untuk ditinjau; dokumen ERPNext belum dibuat.",
    }
