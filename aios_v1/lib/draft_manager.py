import frappe
from frappe.utils import now_datetime

def expire_old_drafts():
    """Cron job: Ubah status draft yang melewati batas expires_at jadi EXPIRED."""
    now = now_datetime()
    drafts = frappe.get_all(
        "Pending Action Draft", 
        filters={"status": "PENDING_APPROVAL", "expires_at": ["<", now]}
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
def approve_draft(draft_id: str) -> dict:
    """Approve draf; kepemilikan diperiksa lewat `has_permission`."""
    doc = frappe.get_doc("Pending Action Draft", draft_id, check_permission="write")
    if doc.status != "PENDING_APPROVAL":
        frappe.throw(f"Draft tidak bisa di-approve karena berstatus {doc.status}.")
    
    # Ubah status
    doc.status = "APPROVED"
    doc.save()
    frappe.db.commit()
    
    # TODO: Panggil fungsi eksekusi sebenarnya (di tahap 4/6)
    
    return {"status": "success", "message": f"Draft {draft_id} telah di-approve."}

@frappe.whitelist()
def reject_draft(draft_id: str, reason: str = "") -> dict:
    """Reject draf; kepemilikan diperiksa lewat `has_permission`."""
    doc = frappe.get_doc("Pending Action Draft", draft_id, check_permission="write")
    if doc.status != "PENDING_APPROVAL":
        frappe.throw(f"Draft tidak bisa di-reject karena berstatus {doc.status}.")
    
    doc.status = "REJECTED"
    doc.rejection_reason = reason
    doc.save()
    frappe.db.commit()
    
    # TODO: Beritahu AI Manager terkait penolakan ini agar AI mencari alternatif
    
    return {"status": "success", "message": f"Draft {draft_id} telah di-reject."}
