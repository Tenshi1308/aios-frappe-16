"""Manajemen `Pending Action Draft` (Alur 5, docs/04).

- `create_draft()`: satu-satunya jalur pembuatan draft; pemilik selalu dari sesi.
- `approve_and_execute_draft()`: approve -> buat dokumen ERPNext -> `EXECUTED`.
  Bila eksekusi gagal, draft tetap `APPROVED` dan kegagalan dicatat di Error Log.
- `reject_draft()`: `REJECTED` + catatan penolakan untuk AI Manager.
"""

import json

import frappe
from frappe.utils import add_to_date, now_datetime

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
        payload_json = json.dumps(payload, default=str)
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
            frappe.throw("data memuat field yang tidak dikenal untuk DocType ini.")
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


def _create_and_submit(doctype: str, data: dict, company: str) -> dict:
    business_data = dict(data)
    business_data.pop("company", None)
    validate_data_fields(frappe.get_meta(doctype), business_data)
    target_data = {"doctype": doctype, **business_data}
    if frappe.get_meta(doctype).has_field("company"):
        target_data["company"] = company
    target = frappe.get_doc(target_data)
    target.flags.ignore_permissions = True
    target.insert(ignore_permissions=True)
    target.flags.ignore_permissions = True
    target.submit()
    return {"doctype": doctype, "name": target.name, "docstatus": 1}


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
    """Ambil detail draf; hanya pemilik atau Administrator."""
    doc = frappe.get_doc("Pending Action Draft", draft_id, check_permission="read")
    _assert_draft_owner(doc)
    return doc.as_dict()


@frappe.whitelist()
def list_pending_drafts(limit: int = 50) -> list:
    """Daftar draft pending milik pemanggil (owner-scoped), terbaru dulu.

    Detail isi draf diambil UI lewat `get_draft` — doctype/aksi ada di dalam
    `payload` dan tidak di-expose di sini.
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        log_exception("AIOS Draft List Limit", exc=exc)
        limit = 50
    limit = max(1, min(limit, 100))
    return frappe.get_all(
        "Pending Action Draft",
        filters={"user": frappe.session.user, "status": "PENDING_APPROVAL"},
        fields=["name", "type", "branch", "status", "expires_at", "creation"],
        order_by="creation desc",
        limit_page_length=limit,
    )


def _assert_draft_owner(doc) -> None:
    user = frappe.session.user
    if user != "Administrator" and doc.user != user:
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
    return result


@frappe.whitelist()
def reject_draft(draft_id: str, reason: str = "") -> dict:
    """Reject draf hanya untuk pemilik atau Administrator."""
    doc = _lock_draft(draft_id)
    _assert_draft_owner(doc)
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
