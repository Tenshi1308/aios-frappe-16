"""Manajemen `Pending Action Draft` (Alur 5, docs/04).

- `create_draft()`: satu-satunya jalur pembuatan draft; pemilik selalu dari sesi.
- `approve_and_execute_draft()`: approve -> buat dokumen ERPNext -> `EXECUTED`.
  Bila eksekusi gagal, draft tetap `APPROVED` dan kegagalan dicatat di Error Log.
- `reject_draft()`: `REJECTED` + catatan penolakan untuk AI Manager.
"""

import json

import frappe
from frappe.utils import add_to_date, now_datetime

DRAFT_DOCTYPE = "Pending Action Draft"
ACTION_TYPES = frozenset({"CREATE", "UPDATE_DRAFT", "CANCEL_AND_AMEND"})

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
    branch: str = None,
    created_by_agent: str = None,
    reason: str = "",
    expires_in_hours: int = 24,
):
    """Simpan draft baru; `user` tidak pernah diambil dari argumen pemanggil."""
    if not task_id or not action_type:
        frappe.throw("task_id dan action_type wajib diisi.")
    if action_type not in ACTION_TYPES:
        frappe.throw("Jenis aksi draft tidak dikenal.")
    if not isinstance(payload, dict):
        frappe.throw("Payload draft harus berupa object JSON.")

    try:
        payload_json = json.dumps(payload)
    except (TypeError, ValueError):
        frappe.log_error(frappe.get_traceback(), "AIOS Draft Payload")
        frappe.throw("Payload draft tidak bisa diserialisasi ke JSON.")

    doc = frappe.get_doc(
        {
            "doctype": DRAFT_DOCTYPE,
            "user": frappe.session.user,
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


def execute_draft(doc) -> dict:
    """Buat + submit dokumen ERPNext dari payload draft; company dipaksa site-level."""
    if doc.type not in ACTION_TYPES:
        frappe.throw("Jenis aksi draft tidak dikenal.")
    if doc.type != "CREATE":
        frappe.throw("Jenis aksi draft ini belum didukung pada PoC.")
    try:
        payload = json.loads(doc.payload or "{}")
    except (TypeError, ValueError):
        frappe.log_error(frappe.get_traceback(), "AIOS Draft Execution")
        frappe.throw("Payload draft bukan JSON valid.")

    doctype = payload.get("doctype") if isinstance(payload, dict) else None
    data = payload.get("data") if isinstance(payload, dict) else None
    if doctype not in ALLOWED_DRAFT_DOCTYPES:
        frappe.throw(f"Tipe dokumen draft tidak didukung: {doctype}")
    if not isinstance(data, dict):
        frappe.throw("Field 'data' pada payload draft harus berupa object.")

    company = (
        frappe.db.get_single_value("AIOS Setting", "default_company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    )
    if not company:
        frappe.log_error(
            "default_company kosong: AIOS Setting/Global Defaults",
            "AIOS Draft Executor",
        )
        frappe.throw("Company default belum dikonfigurasi")

    target = frappe.get_doc({"doctype": doctype, **data, "company": company})
    target.insert(ignore_permissions=True)
    target.submit()
    return {"doctype": doctype, "name": target.name}


def _notify_rejection(doc, reason: str) -> None:
    """Catat penolakan di percakapan terakhir user agar AI Manager tahu konteksnya."""
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
    """Ambil detail draf; hanya pemilik (atau AIOS Admin/Administrator)."""
    doc = frappe.get_doc("Pending Action Draft", draft_id, check_permission="read")
    return doc.as_dict()


@frappe.whitelist()
def approve_and_execute_draft(draft_id: str) -> dict:
    """Approve draf lalu eksekusi ke ERPNext; kepemilikan diperiksa `has_permission`."""
    doc = frappe.get_doc(DRAFT_DOCTYPE, draft_id, check_permission="write")
    if doc.status != "PENDING_APPROVAL":
        frappe.throw(f"Draft tidak bisa di-approve karena berstatus {doc.status}.")
    if doc.expires_at and doc.expires_at < now_datetime():
        doc.status = "EXPIRED"
        doc.save()
        frappe.db.commit()
        frappe.throw("Draft sudah kedaluwarsa.")

    doc.status = "APPROVED"
    doc.save()

    frappe.db.savepoint("aios_draft_execution")
    try:
        executed = execute_draft(doc)
    except Exception:
        # Batalkan dokumen ERPNext setengah jadi; status APPROVED tetap tersimpan.
        frappe.db.rollback(save_point="aios_draft_execution")
        frappe.db.commit()
        frappe.log_error(frappe.get_traceback(), "AIOS Draft Execution")
        return {
            "status": "APPROVED",
            "draft_status": "APPROVED",
            "executed": False,
            "message": "Draft disetujui, tetapi eksekusi ERPNext gagal. Detail ada di Error Log.",
        }

    doc.status = "EXECUTED"
    doc.save()
    frappe.db.commit()
    return {
        "status": "success",
        "draft_status": "EXECUTED",
        "executed": True,
        "doctype": executed["doctype"],
        "document": executed["name"],
        "message": f"Draft {draft_id} dieksekusi: {executed['doctype']} {executed['name']}.",
    }


@frappe.whitelist()
def reject_draft(draft_id: str, reason: str = "") -> dict:
    """Reject draf; kepemilikan diperiksa lewat `has_permission`."""
    doc = frappe.get_doc(DRAFT_DOCTYPE, draft_id, check_permission="write")
    if doc.status != "PENDING_APPROVAL":
        frappe.throw(f"Draft tidak bisa di-reject karena berstatus {doc.status}.")

    doc.status = "REJECTED"
    doc.rejection_reason = reason
    doc.save()
    _notify_rejection(doc, reason)
    frappe.db.commit()

    return {"status": "success", "message": f"Draft {draft_id} telah di-reject."}


# Alias lama; frontend `DraftCard` masih memanggil nama ini sampai `#12`.
approve_draft = approve_and_execute_draft
