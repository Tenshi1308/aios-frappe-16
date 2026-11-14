"""Create and confirm approval drafts without bypassing human authorization."""

import hashlib
import hmac
import json
import uuid

import frappe
from frappe.utils import get_datetime, now_datetime

from aios_v1.lib.draft_manager import (
    ALLOWED_DRAFT_DOCTYPES,
    DraftExecutionError,
    _format_currency_amount,
    _is_channel_draft,
    _site_company,
    approve_and_execute_draft,
    confirm_draft_cash_payment,
    create_draft,
    validate_data_fields,
)
from aios_v1.lib.draft_manager import (
    reject_draft as reject_draft_doc,
)
from aios_v1.lib.erpnext_core_data import DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT
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
                "customer_name, contact_person (opsional), mobile_no, address, "
                "serta payment_method ('Cash', wajib untuk Sales Order)."
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

            if validated_customer_info is not None:
                raw_pm = str((customer_info or {}).get("payment_method") or "").strip()
                if not raw_pm:
                    if is_guest:
                        return safe_error(
                            "Metode pembayaran (payment_method) wajib diisi 'Cash' pada customer_info untuk draf Sales Order.",
                            "PAYMENT_METHOD_REQUIRED",
                        )
                    frappe.throw("Metode pembayaran (payment_method) wajib diisi 'Cash' pada customer_info untuk draf Sales Order.")
                if raw_pm.lower() != "cash":
                    if is_guest:
                        return safe_error(
                            "Metode pembayaran saat ini hanya mendukung 'Cash' (Tunai).",
                            "UNSUPPORTED_PAYMENT_METHOD",
                        )
                    frappe.throw("Metode pembayaran saat ini hanya mendukung 'Cash' (Tunai).")
                validated_customer_info["payment_method"] = "Cash"
                payload["customer_info"] = validated_customer_info

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


_CONFIRM_TTL_SECONDS = 300
_CONFIRM_CACHE_PREFIX = "aios_tg_confirm"
_ACTION_LABELS = {
    "approve": "menyetujui draf menjadi Sales Order",
    "reject": "menolak/membatalkan draf",
    "confirm_cash_payment": "mengonfirmasi pembayaran Cash",
}


def _confirm_cache_key(user: str, action: str, draft_id: str) -> str:
    return f"{_CONFIRM_CACHE_PREFIX}:{user}:{action}:{draft_id}"


def _parse_bool_flag(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "ya"}
    return bool(value)


def _latest_conversation_user_msg(conversation_id: str | None) -> str | None:
    if not conversation_id:
        return None
    rows = frappe.get_all(
        "AIOS Message",
        filters={"conversation": str(conversation_id), "role": "user"},
        fields=["name"],
        order_by="name desc",
        limit=1,
    )
    if not rows:
        return None
    return str(rows[0]["name"])


def _is_newer_message(latest_name: str | None, issued_name: str | None) -> bool:
    if not latest_name or not issued_name:
        return False
    s_latest = str(latest_name)
    s_issued = str(issued_name)
    if s_latest == s_issued:
        return False
    if s_latest.isdigit() and s_issued.isdigit():
        return int(s_latest) > int(s_issued)
    return s_latest > s_issued


def _resolve_authorized_draft_caller(action: str = "", draft_id: str = "") -> tuple[str | None, dict | None]:
    """Validate linked user, active AIOS Client authority; return (user, err)."""
    user = get_tool_context().get("user_id") or getattr(getattr(frappe, "session", None), "user", None)
    clean_id = str(draft_id or "").strip()
    ctx_suffix = f"; draft={clean_id}" if clean_id else ""
    if not user or user == "Guest":
        log_exception("AIOS Draft Tool Guest Denied", context=f"action={action}{ctx_suffix}")
        return None, safe_error(
            "Maaf, hanya karyawan yang tertaut dan berwenang yang dapat memproses draf ini.",
            "GUEST_TOOL_FORBIDDEN",
        )

    if user != "Administrator":
        user_row = frappe.db.get_value("User", user, ["enabled", "aios_status"], as_dict=True)
        roles = set(frappe.get_roles(user))
        if (
            not user_row
            or int(user_row.enabled or 0) != 1
            or user_row.aios_status != "Active"
            or "AIOS Client" not in roles
        ):
            log_exception("AIOS Draft Tool Inactive Denied", context=f"user={user}; action={action}")
            return None, safe_error(
                "Maaf, akun Anda sedang tidak aktif atau tidak memiliki akses AIOS Client.",
                "NOT_AUTHORIZED",
            )

    return user, None


def _is_channel_draft_record(draft_name: str, payload: dict) -> bool:
    """Return True if draft is originated from channel or alerted via notification."""
    return _is_channel_draft(draft_name) or bool(payload.get("source_telegram_chat_id"))


def _resolve_executed_draft_by_result_doc(clean_id: str) -> str | None:
    """Resolve an executed draft name from a Sales Order/document number in payload.result."""
    rows = frappe.get_all(
        "Pending Action Draft",
        filters={"status": "EXECUTED", "payload": ["like", f"%{clean_id}%"]},
        fields=["name", "payload"],
        limit_page_length=0,
    )
    matched_names: list[str] = []
    for row in rows:
        try:
            parsed = json.loads(row.payload or "{}")
        except (TypeError, ValueError) as exc:
            log_exception("AIOS Draft Tool Parse Candidate Payload", exc=exc, context=f"draft={row.name}")
            continue
        result_obj = parsed.get("result") if isinstance(parsed, dict) and isinstance(parsed.get("result"), dict) else {}
        if result_obj.get("name") == clean_id or result_obj.get("document") == clean_id:
            matched_names.append(row.name)
    if len(matched_names) == 1:
        return matched_names[0]
    return None


def _require_authorized_draft(draft_id: str, action: str) -> tuple[str | None, object | None, dict | None, dict | None]:
    """Validate linked user, Ekasa Desk authority, and return (user, draft_doc, payload, err)."""
    clean_id = str(draft_id or "").strip()
    user, auth_err = _resolve_authorized_draft_caller(action=action, draft_id=clean_id)
    if auth_err:
        return None, None, None, auth_err

    if not clean_id:
        return None, None, None, safe_error("Nomor draf (draft_id) wajib disebutkan.", "DRAFT_ID_REQUIRED")

    resolved_id = (
        clean_id
        if frappe.db.exists("Pending Action Draft", clean_id)
        else _resolve_executed_draft_by_result_doc(clean_id)
    )
    if not resolved_id:
        return None, None, None, safe_error(f"Draf {clean_id} tidak ditemukan.", "DRAFT_NOT_FOUND")

    doc = frappe.get_doc("Pending Action Draft", resolved_id)
    try:
        payload = json.loads(doc.payload or "{}")
        if not isinstance(payload, dict):
            raise ValueError("Payload draf bukan JSON object.")
    except (TypeError, ValueError) as exc:
        log_exception("AIOS Draft Tool Parse Payload", exc=exc, context=f"draft={doc.name}")
        return None, None, None, safe_error("Data draf tidak valid.", "INVALID_DRAFT_PAYLOAD")

    is_channel = _is_channel_draft_record(doc.name, payload)
    if user != "Administrator":
        if is_channel:
            from aios_v1.lib.connector.notify import get_channel_recipients

            if user not in set(get_channel_recipients()):
                log_exception(
                    "AIOS Draft Tool Unauthorized",
                    context=f"user={user}; draft={doc.name}; action={action}; channel=1",
                )
                return None, None, None, safe_error(
                    "Maaf, Anda tidak memiliki wewenang untuk memproses draf ini. "
                    "Hanya penerima kanal aktif atau pemilik klien berwenang yang dapat menyetujui, "
                    "menolak, atau mengonfirmasi pembayaran draf.",
                    "NOT_AUTHORIZED",
                )
        elif doc.user != user or not frappe.has_permission("Pending Action Draft", ptype="write", doc=doc):
            log_exception(
                "AIOS Draft Tool Unauthorized",
                context=f"user={user}; draft={doc.name}; action={action}; owner={doc.user}",
            )
            return None, None, None, safe_error(
                "Maaf, Anda tidak memiliki wewenang untuk memproses draf ini.",
                "NOT_AUTHORIZED",
            )

    return user, doc, payload, None


def _validate_draft_state(doc, payload: dict, action: str) -> tuple[dict | None, dict | None]:
    """Check draft lifecycle before asking confirmation; return (early_success, err)."""
    if action == "approve":
        if doc.status == "EXECUTED":
            result_obj = payload.get("result") if isinstance(payload.get("result"), dict) else {}
            so_name = result_obj.get("name") or result_obj.get("document")
            return {
                "status": "success",
                "draft_id": doc.name,
                "draft_status": "EXECUTED",
                "executed": True,
                "already_executed": True,
                "sales_order": so_name,
                "document": so_name,
                "message": f"Draf {doc.name} sudah berstatus EXECUTED ({so_name}).",
            }, None
        if doc.status == "PENDING_APPROVAL" and doc.expires_at and doc.expires_at < now_datetime():
            return None, safe_error(f"Draf {doc.name} sudah kedaluwarsa sehingga tidak bisa disetujui.", "DRAFT_EXPIRED")
        if doc.status not in {"PENDING_APPROVAL", "APPROVED"}:
            return None, safe_error(
                f"Draf {doc.name} tidak bisa disetujui karena berstatus {doc.status}.",
                "DRAFT_STATUS_INVALID",
            )
        return None, None

    if action == "reject":
        if doc.status not in {"PENDING_APPROVAL", "APPROVED"}:
            return None, safe_error(
                f"Draf {doc.name} tidak bisa ditolak karena berstatus {doc.status}.",
                "DRAFT_STATUS_INVALID",
            )
        return None, None

    # confirm_cash_payment
    if doc.status != "EXECUTED":
        return None, safe_error(
            f"Konfirmasi pembayaran Cash hanya berlaku untuk draf berstatus EXECUTED (status saat ini: {doc.status}).",
            "DRAFT_NOT_EXECUTED",
        )
    if doc.type != "CREATE" or payload.get("doctype") != "Sales Order":
        return None, safe_error(
            "Konfirmasi pembayaran Cash hanya berlaku untuk draf pembuatan Sales Order.",
            "DRAFT_TYPE_UNSUPPORTED",
        )
    result_obj = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    so_name = result_obj.get("name") or result_obj.get("document")
    if not so_name or not frappe.db.exists("Sales Order", so_name):
        return None, safe_error(
            f"Dokumen Sales Order untuk draf {doc.name} tidak ditemukan.",
            "SALES_ORDER_NOT_FOUND",
        )
    existing_pe = result_obj.get("payment_entry")
    if not existing_pe:
        refs = frappe.get_all(
            "Payment Entry Reference",
            filters={"reference_doctype": "Sales Order", "reference_name": so_name, "docstatus": 1},
            pluck="parent",
            limit=1,
        )
        existing_pe = refs[0] if refs else None
    if existing_pe and frappe.db.exists("Payment Entry", existing_pe):
        return {
            "status": "success",
            "draft_id": doc.name,
            "sales_order": so_name,
            "payment_entry": existing_pe,
            "payment_confirmed": True,
            "already_paid": True,
            "message": f"Pembayaran Cash untuk {so_name} sudah tercatat pada {existing_pe} (status: lunas).",
        }, None
    return None, None


def _build_draft_summary(doc, payload: dict, action: str, reason: str = "") -> dict:
    """Build dynamic draft summary (number, customer, total, items) without hardcoding."""
    company = _site_company()
    default_currency = frappe.db.get_value("Company", company, "default_currency") if company else None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    currency = str(data.get("currency") or default_currency or "IDR")

    if action == "confirm_cash_payment":
        result_obj = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        so_name = str(result_obj.get("name") or result_obj.get("document") or "")
        so = frappe.get_doc("Sales Order", so_name)
        so_currency = str(so.currency or currency)
        total_val = float(so.rounded_total or so.grand_total or 0)
        items = [
            {
                "item_code": str(it.item_code or ""),
                "item_name": str(it.item_name or it.item_code or "-"),
                "qty": float(it.qty or 0),
                "uom": str(it.uom or ""),
                "rate": float(it.rate or 0),
                "amount": float(it.amount or 0),
                "formatted_amount": _format_currency_amount(it.amount or 0, so_currency),
            }
            for it in (so.items or [])
        ]
        return {
            "draft_id": doc.name,
            "sales_order": so.name,
            "doctype": "Sales Order",
            "customer": str(so.customer_name or so.customer or "-"),
            "currency": so_currency,
            "total": total_val,
            "formatted_total": _format_currency_amount(total_val, so_currency),
            "items": items,
        }

    customer_info = payload.get("customer_info") if isinstance(payload.get("customer_info"), dict) else {}
    customer = str(
        customer_info.get("customer_name")
        or data.get("customer")
        or data.get("party_name")
        or payload.get("name")
        or "-"
    )
    price_list = data.get("selling_price_list")
    if not price_list:
        pl_rows = frappe.get_all("Price List", filters={"selling": 1, "enabled": 1}, pluck="name", limit=1)
        price_list = pl_rows[0] if pl_rows else None

    items = []
    total_val = 0.0
    all_priced = True
    for raw_item in (data.get("items") if isinstance(data.get("items"), list) else []):
        if not isinstance(raw_item, dict):
            continue
        item_code = str(raw_item.get("item_code") or raw_item.get("item_name") or "-")
        item_meta = (
            frappe.db.get_value(
                "Item", item_code, ["item_name", "stock_uom", "standard_rate"], as_dict=True
            )
            if frappe.db.exists("Item", item_code)
            else None
        )
        item_name = str(raw_item.get("item_name") or (item_meta or {}).get("item_name") or item_code)
        uom = str(raw_item.get("uom") or (item_meta or {}).get("stock_uom") or "")
        qty = float(raw_item.get("qty") or 0)
        rate = raw_item.get("rate")
        if rate is None and price_list and frappe.db.exists("Item", item_code):
            rate = frappe.db.get_value(
                "Item Price",
                {"item_code": item_code, "price_list": price_list, "selling": 1},
                "price_list_rate",
            )
        if rate is None and item_meta and item_meta.get("standard_rate"):
            rate = item_meta.get("standard_rate")
        if rate is not None:
            rate_f = float(rate)
            amount_f = qty * rate_f
            total_val += amount_f
            formatted_amt = _format_currency_amount(amount_f, currency)
        else:
            rate_f = None
            amount_f = None
            all_priced = False
            formatted_amt = "-"
        items.append(
            {
                "item_code": item_code,
                "item_name": item_name,
                "qty": qty,
                "uom": uom,
                "rate": rate_f,
                "amount": amount_f,
                "formatted_amount": formatted_amt,
            }
        )

    if items and all_priced:
        formatted_total = _format_currency_amount(total_val, currency)
        summary_total: float | None = total_val
    elif data.get("grand_total") is not None:
        summary_total = float(data["grand_total"])
        formatted_total = _format_currency_amount(summary_total, currency)
    else:
        summary_total = None
        formatted_total = "Menunggu perhitungan ERPNext"

    summary = {
        "draft_id": doc.name,
        "doctype": str(payload.get("doctype") or doc.type or "Sales Order"),
        "customer": customer,
        "currency": currency,
        "total": summary_total,
        "formatted_total": formatted_total,
        "items": items,
    }
    if reason:
        summary["reason"] = reason
    return summary


def _format_confirmation_message(action: str, summary: dict) -> str:
    action_label = _ACTION_LABELS.get(action, action)
    item_lines = []
    for it in summary.get("items") or []:
        qty_val = it["qty"]
        qty_str = str(int(qty_val)) if float(qty_val).is_integer() else str(qty_val)
        uom_part = f" {it['uom']}" if it.get("uom") else ""
        amt_part = f" ({it['formatted_amount']})" if it.get("formatted_amount") and it["formatted_amount"] != "-" else ""
        item_lines.append(f"- {it['item_name']} x {qty_str}{uom_part}{amt_part}")
    items_block = "\n".join(item_lines) if item_lines else "- (Tidak ada rincian item pada draf)"
    so_line = f"\nSales Order: {summary['sales_order']}" if summary.get("sales_order") else ""
    reason_line = f"\nAlasan penolakan: {summary['reason']}" if summary.get("reason") else ""
    return (
        f"Konfirmasi sebelum {action_label}:\n"
        f"Nomor Draf: {summary['draft_id']}{so_line}\n"
        f"Customer: {summary['customer']}\n"
        f"Total: {summary['formatted_total']}\n"
        f"Item:\n{items_block}{reason_line}\n\n"
        f"Apakah Anda yakin ingin {action_label}? Jawab ya untuk melanjutkan atau tidak untuk membatalkan."
    )


def _load_challenge(cache_key: str) -> dict | None:
    raw = frappe.cache().get_value(cache_key)
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, ValueError) as exc:
        log_exception("AIOS Draft Confirm Challenge Parse", exc=exc, context=cache_key)
        frappe.cache().delete_value(cache_key)
        return None


def _issue_confirmation(
    cache_key: str,
    user: str,
    action: str,
    draft_id: str,
    summary: dict,
    conversation_id: str | None,
    latest_msg_name: str | None,
    reason: str = "",
) -> dict:
    raw_token = frappe.generate_hash(length=12)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    challenge = {
        "token_hash": token_hash,
        "user": user,
        "action": action,
        "draft_id": draft_id,
        "conversation_id": str(conversation_id) if conversation_id else "",
        "issued_user_msg": latest_msg_name or "",
        "reason": reason,
    }
    frappe.cache().set_value(
        cache_key,
        json.dumps(challenge),
        expires_in_sec=_CONFIRM_TTL_SECONDS,
    )
    return {
        "status": "CONFIRMATION_REQUIRED",
        "code": "CONFIRMATION_REQUIRED",
        "requires_confirmation": True,
        "executed": False,
        "confirmation_token": raw_token,
        "action": action,
        "draft_id": draft_id,
        "summary": summary,
        "message": _format_confirmation_message(action, summary),
    }


def _verify_or_issue_confirmation(
    user: str,
    action: str,
    draft_id: str,
    summary: dict,
    confirmed: bool,
    confirmation_token: str = "",
    reason: str = "",
) -> tuple[dict | None, str]:
    """Enforce 2-step confirmation across user turns; return (halt_response_or_None, stored_reason)."""
    cache_key = _confirm_cache_key(user, action, draft_id)
    conversation_id = get_tool_context().get("conversation_id")
    latest_msg_name = _latest_conversation_user_msg(conversation_id)
    confirmed_flag = _parse_bool_flag(confirmed)
    tok = str(confirmation_token or "").strip()

    if not confirmed_flag:
        return _issue_confirmation(
            cache_key, user, action, draft_id, summary, conversation_id, latest_msg_name, reason=reason
        ), reason

    challenge = _load_challenge(cache_key)
    if (
        not challenge
        or challenge.get("user") != user
        or challenge.get("action") != action
        or challenge.get("draft_id") != draft_id
    ):
        return _issue_confirmation(
            cache_key, user, action, draft_id, summary, conversation_id, latest_msg_name, reason=reason
        ), reason

    if tok:
        supplied_hash = hashlib.sha256(tok.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(supplied_hash, str(challenge.get("token_hash") or "")):
            return _issue_confirmation(
                cache_key, user, action, draft_id, summary, conversation_id, latest_msg_name, reason=reason
            ), reason

    in_same_conversation = bool(
        conversation_id and challenge.get("conversation_id") == str(conversation_id)
    )
    if in_same_conversation:
        issued_msg = challenge.get("issued_user_msg") or ""
        if not issued_msg or not _is_newer_message(latest_msg_name, issued_msg):
            return {
                "status": "CONFIRMATION_PENDING_USER_REPLY",
                "code": "CONFIRMATION_PENDING_USER_REPLY",
                "requires_confirmation": True,
                "executed": False,
                "action": action,
                "draft_id": draft_id,
                "summary": summary,
                "message": (
                    "Tampilkan ringkasan draf ini ke karyawan dan tunggu balasan konfirmasi "
                    "pada pesan berikutnya sebelum mengeksekusi."
                ),
            }, reason
    elif not tok:
        # Di luar konteks AIOS Conversation, token tantangan wajib dicocokkan persis.
        return _issue_confirmation(
            cache_key, user, action, draft_id, summary, conversation_id, latest_msg_name, reason=reason
        ), reason

    effective_reason = str(reason or challenge.get("reason") or "").strip()
    # Hapus tantangan sekali-pakai sebelum mengeksekusi mutasi agar tidak bisa di-replay.
    frappe.cache().delete_value(cache_key)
    return None, effective_reason


def _run_confirmed_draft_action(
    draft_id: str,
    action: str,
    confirmed: bool,
    confirmation_token: str,
    reason: str,
    executor,
) -> dict:
    user, doc, payload, auth_err = _require_authorized_draft(draft_id, action)
    if auth_err:
        return auth_err

    early_resp, state_err = _validate_draft_state(doc, payload, action)
    if state_err:
        return state_err
    if early_resp:
        return early_resp

    summary = _build_draft_summary(doc, payload, action, reason=reason)
    halt_resp, effective_reason = _verify_or_issue_confirmation(
        user=user,
        action=action,
        draft_id=doc.name,
        summary=summary,
        confirmed=confirmed,
        confirmation_token=confirmation_token,
        reason=reason,
    )
    if halt_resp:
        return halt_resp

    try:
        return executor(doc, payload, effective_reason)
    except frappe.PermissionError as exc:
        log_exception("AIOS Draft Tool Permission Denied", exc=exc, context=f"user={user}; draft={doc.name}; action={action}")
        return safe_error("Maaf, Anda tidak memiliki wewenang untuk memproses draf ini.", "NOT_AUTHORIZED")
    except (DraftExecutionError, frappe.ValidationError) as exc:
        log_exception("AIOS Draft Tool Validation Failed", exc=exc, context=f"draft={doc.name}; action={action}")
        return safe_error(str(exc) or "Validasi dokumen ERPNext gagal saat memproses draf.", "DRAFT_VALIDATION_FAILED")
    except Exception as exc:
        log_exception("AIOS Draft Tool Failed", exc=exc, context=f"draft={doc.name}; action={action}")
        return safe_error("Terjadi kendala saat memproses draf di sistem.", "DRAFT_ACTION_FAILED")


def _execute_approve_draft(doc, _payload: dict, _reason: str) -> dict:
    res = approve_and_execute_draft(doc.name)
    if not res.get("executed"):
        return safe_error(
            res.get("message") or "Eksekusi draf gagal pada validasi ERPNext.",
            res.get("code") or "DRAFT_EXECUTION_FAILED",
        )
    so_name = res.get("name") or res.get("document")
    draft_status = res.get("draft_status") or "EXECUTED"
    return {
        "status": "success",
        "draft_id": doc.name,
        "draft_status": draft_status,
        "executed": True,
        "doctype": res.get("doctype") or "Sales Order",
        "sales_order": so_name,
        "document": so_name,
        "customer_notified": True,
        "message": (
            f"Draf {doc.name} berhasil disetujui. Sales Order {so_name} telah dibuat dan disubmit "
            f"(status: {draft_status})."
        ),
    }


def _execute_reject_draft(doc, _payload: dict, reason: str) -> dict:
    res = reject_draft_doc(doc.name, reason=reason)
    draft_status = res.get("draft_status") or "REJECTED"
    effective_reason = res.get("reason") or reason
    return {
        "status": "success",
        "draft_id": doc.name,
        "draft_status": draft_status,
        "executed": False,
        "reason": effective_reason,
        "customer_notified": True,
        "message": f"Draf {doc.name} telah ditolak (status: {draft_status}).",
    }


def _execute_confirm_cash_payment(doc, _payload: dict, _reason: str) -> dict:
    res = confirm_draft_cash_payment(doc.name)
    so_name = res.get("sales_order")
    pe_name = res.get("payment_entry")
    return {
        "status": "success",
        "draft_id": doc.name,
        "sales_order": so_name,
        "payment_entry": pe_name,
        "payment_confirmed": bool(res.get("payment_confirmed", True)),
        "already_paid": bool(res.get("already_paid")),
        "customer_notified": True,
        "message": (
            f"Pembayaran Cash berhasil dikonfirmasi. Payment Entry {pe_name} untuk Sales Order {so_name} "
            f"(status: lunas)."
        ),
    }


@ai_tool(
    name="list_pending_drafts",
    description=(
        "Melihat daftar Pending Action Draft yang menunggu persetujuan (status PENDING_APPROVAL). "
        "Mengembalikan ringkasan tiap draf (nomor draf, doctype, customer, currency, total, "
        "formatted_total, items, type, branch, status, creation, expires_at, expired). "
        "Gunakan tool ini untuk mengetahui draf mana saja yang perlu disetujui atau ditolak."
    ),
    branch="sales",
    roles=["manager", "sales_manager", "ai_manager"],
    plugin_key="erpnext-action-drafts",
    parameters={
        "limit": {
            "type": "integer",
            "description": "Jumlah maksimal draf yang diambil (opsional, default 20, maksimal 100).",
            "required": False,
        }
    },
)
def list_pending_drafts(limit: int | None = None) -> dict:
    """List pending action drafts visible to the authorized caller."""
    if limit is None:
        resolved_limit = DEFAULT_LIST_LIMIT
    elif isinstance(limit, bool):
        return safe_error("Parameter limit harus berupa integer positif (minimal 1).", "INVALID_LIMIT")
    else:
        try:
            if isinstance(limit, float) and not limit.is_integer():
                return safe_error("Parameter limit harus berupa integer positif (minimal 1).", "INVALID_LIMIT")
            parsed_limit = int(limit)
            if parsed_limit < 1:
                return safe_error("Parameter limit harus berupa integer positif (minimal 1).", "INVALID_LIMIT")
        except (TypeError, ValueError) as exc:
            log_exception("list_pending_drafts.invalid_limit", exc=exc, context=f"limit={limit!r}")
            return safe_error("Parameter limit harus berupa integer positif (minimal 1).", "INVALID_LIMIT")
        resolved_limit = min(parsed_limit, MAX_LIST_LIMIT)

    user, auth_err = _resolve_authorized_draft_caller(action="list_pending_drafts")
    if auth_err:
        return auth_err

    limit_start = 0
    batch_size = max(resolved_limit * 2, 50)
    visible_drafts = []
    channel_recipients: set[str] | None = None
    now_dt = now_datetime()

    while len(visible_drafts) < resolved_limit + 1:
        rows = frappe.get_all(
            "Pending Action Draft",
            filters={"status": "PENDING_APPROVAL"},
            fields=["name", "user", "type", "branch", "status", "payload", "creation", "expires_at"],
            order_by="creation desc, name desc",
            limit_start=limit_start,
            limit=batch_size,
        )
        if not rows:
            break

        limit_start += len(rows)

        for row in rows:
            payload = {}
            if row.payload:
                try:
                    parsed = json.loads(row.payload)
                    if isinstance(parsed, dict):
                        payload = parsed
                    else:
                        raise ValueError("Payload draf bukan JSON object.")
                except (TypeError, ValueError) as exc:
                    log_exception("list_pending_drafts.invalid_payload", exc=exc, context=f"draft={row.name}")
                    payload = {}

            if user != "Administrator":
                is_ch = _is_channel_draft_record(row.name, payload)
                if is_ch:
                    if channel_recipients is None:
                        from aios_v1.lib.connector.notify import get_channel_recipients

                        channel_recipients = set(get_channel_recipients())
                    if user not in channel_recipients:
                        continue
                else:
                    if row.user != user:
                        continue
                    if not frappe.has_permission("Pending Action Draft", ptype="read", doc=row.name, user=user):
                        continue

            summary = _build_draft_summary(row, payload, action="approve")

            expires_dt = get_datetime(row.expires_at) if row.expires_at else None
            expired = bool(expires_dt and expires_dt < now_dt)

            summary.update({
                "type": str(row.type or payload.get("doctype") or "Sales Order"),
                "branch": str(row.branch or "sales"),
                "status": str(row.status or "PENDING_APPROVAL"),
                "creation": str(row.creation or ""),
                "expires_at": str(row.expires_at or ""),
                "expired": expired,
            })
            visible_drafts.append(summary)
            if len(visible_drafts) >= resolved_limit + 1:
                break

    has_more = len(visible_drafts) > resolved_limit
    drafts_page = visible_drafts[:resolved_limit]
    count = len(drafts_page)

    if count == 0:
        message = "Tidak ada draf yang menunggu persetujuan (status PENDING_APPROVAL)."
    else:
        more_suffix = " (masih ada draf lainnya, tentukan limit lebih besar bila perlu)" if has_more else ""
        message = f"Ditemukan {count} draf yang menunggu persetujuan{more_suffix}."

    return {
        "status": "ok",
        "drafts": drafts_page,
        "count": count,
        "limit": resolved_limit,
        "has_more": has_more,
        "message": message,
    }


@ai_tool(
    name="approve_draft",
    description=(
        "Menyetujui Pending Action Draft menjadi Sales Order atas nama karyawan yang berwenang. "
        "Karyawan dapat menyebutkan nomor Pending Action Draft (DRF-...) maupun nomor Sales Order (SAL-ORD-...). "
        "Alur 2 langkah: Langkah 1, panggil dengan confirmed=false terlebih dahulu untuk mengambil "
        "ringkasan draf (nomor, customer, total, item) dan meminta konfirmasi karyawan. "
        "Langkah 2, setelah karyawan menjawab ya/setuju pada pesan berikutnya, panggil tool ini lagi "
        "dengan confirmed=true untuk mengeksekusi persetujuan (jangan memanggil ulang confirmed=false "
        "setelah ringkasan ditampilkan dan karyawan sudah mengonfirmasi). "
        "Parameter confirmation_token bersifat opsional bila konfirmasi diberikan di dalam percakapan "
        "chat (AIOS Conversation) yang sama (panggil confirmed=true tanpa confirmation_token bila token "
        "tidak tersedia), dan wajib hanya bila eksekusi dilakukan di luar percakapan tanpa riwayat."
    ),
    branch="sales",
    roles=["manager", "sales_manager", "ai_manager"],
    plugin_key="erpnext-action-drafts",
    parameters={
        "draft_id": {
            "type": "string",
            "description": "Nomor Pending Action Draft (contoh: DRF-2026-11-00001) atau nomor Sales Order (contoh: SAL-ORD-2026-00001)",
        },
        "confirmed": {
            "type": "boolean",
            "description": (
                "Isi false pada langkah 1 untuk mengambil ringkasan konfirmasi awal; isi true pada "
                "langkah 2 untuk mengeksekusi setelah karyawan menjawab setuju pada pesan berikutnya "
                "(jangan mengulang false setelah karyawan mengonfirmasi)."
            ),
            "required": False,
        },
        "confirmation_token": {
            "type": "string",
            "description": (
                "Token tantangan dari hasil pemanggilan langkah 1 bila masih tersedia (wajib hanya "
                "bila eksekusi di luar percakapan tanpa riwayat). Jika tidak tersedia saat percakapan "
                "berlanjut ke pesan berikutnya, panggil confirmed=true tanpa confirmation_token — "
                "jangan mengambil ringkasan ulang untuk mendapatkan token baru dan jangan mengarang nilai token."
            ),
            "required": False,
        },
    },
)
def approve_draft(draft_id: str, confirmed: bool = False, confirmation_token: str = "") -> dict:
    """Approve a Pending Action Draft into a submitted Sales Order with mandatory 2-step confirmation."""
    return _run_confirmed_draft_action(
        draft_id=draft_id,
        action="approve",
        confirmed=confirmed,
        confirmation_token=confirmation_token,
        reason="",
        executor=_execute_approve_draft,
    )


@ai_tool(
    name="reject_draft",
    description=(
        "Menolak/membatalkan Pending Action Draft atas nama karyawan yang berwenang. "
        "Karyawan dapat menyebutkan nomor Pending Action Draft (DRF-...) maupun nomor Sales Order (SAL-ORD-...). "
        "Alur 2 langkah: Langkah 1, panggil dengan confirmed=false terlebih dahulu untuk menampilkan "
        "ringkasan draf dan meminta konfirmasi dari karyawan. "
        "Langkah 2, setelah karyawan menjawab ya/setuju pada pesan berikutnya, panggil tool ini lagi "
        "dengan confirmed=true untuk mengeksekusi penolakan (jangan memanggil ulang confirmed=false "
        "setelah ringkasan ditampilkan dan karyawan sudah mengonfirmasi). "
        "Parameter confirmation_token bersifat opsional bila konfirmasi diberikan di dalam percakapan "
        "chat (AIOS Conversation) yang sama (panggil confirmed=true tanpa confirmation_token bila token "
        "tidak tersedia), dan wajib hanya bila eksekusi dilakukan di luar percakapan tanpa riwayat."
    ),
    branch="sales",
    roles=["manager", "sales_manager", "ai_manager"],
    plugin_key="erpnext-action-drafts",
    parameters={
        "draft_id": {
            "type": "string",
            "description": "Nomor Pending Action Draft (contoh: DRF-2026-11-00001) atau nomor Sales Order (contoh: SAL-ORD-2026-00001)",
        },
        "reason": {"type": "string", "description": "Alasan penolakan atau pembatalan draf", "required": False},
        "confirmed": {
            "type": "boolean",
            "description": (
                "Isi false pada langkah 1 untuk mengambil ringkasan konfirmasi awal; isi true pada "
                "langkah 2 untuk mengeksekusi setelah karyawan mengonfirmasi penolakan tersebut "
                "(jangan mengulang false setelah karyawan mengonfirmasi)."
            ),
            "required": False,
        },
        "confirmation_token": {
            "type": "string",
            "description": (
                "Token tantangan dari hasil pemanggilan langkah 1 bila masih tersedia (wajib hanya "
                "bila eksekusi di luar percakapan tanpa riwayat). Jika tidak tersedia saat percakapan "
                "berlanjut ke pesan berikutnya, panggil confirmed=true tanpa confirmation_token — "
                "jangan mengambil ringkasan ulang untuk mendapatkan token baru dan jangan mengarang nilai token."
            ),
            "required": False,
        },
    },
)
def reject_draft(
    draft_id: str, reason: str = "", confirmed: bool = False, confirmation_token: str = ""
) -> dict:
    """Reject a Pending Action Draft with mandatory 2-step confirmation."""
    return _run_confirmed_draft_action(
        draft_id=draft_id,
        action="reject",
        confirmed=confirmed,
        confirmation_token=confirmation_token,
        reason=str(reason or "").strip(),
        executor=_execute_reject_draft,
    )


@ai_tool(
    name="confirm_cash_payment",
    description=(
        "Mengonfirmasi pembayaran Cash (membuat & submit Payment Entry Cash) untuk draf Sales Order berstatus EXECUTED "
        "atas nama karyawan yang berwenang. Karyawan dapat menyebutkan nomor Pending Action Draft (DRF-...) maupun "
        "nomor Sales Order (SAL-ORD-...). "
        "Alur 2 langkah: Langkah 1, panggil dengan confirmed=false terlebih dahulu untuk menampilkan ringkasan "
        "(draf, SO, customer, total, item) dan menunggu konfirmasi karyawan. "
        "Langkah 2, setelah karyawan menjawab ya/setuju pada pesan berikutnya, panggil tool ini lagi "
        "dengan confirmed=true untuk mengeksekusi konfirmasi pembayaran Cash (jangan memanggil ulang "
        "confirmed=false setelah ringkasan ditampilkan dan karyawan sudah mengonfirmasi). "
        "Parameter confirmation_token bersifat opsional bila konfirmasi diberikan di dalam percakapan "
        "chat (AIOS Conversation) yang sama (panggil confirmed=true tanpa confirmation_token bila token "
        "tidak tersedia), dan wajib hanya bila eksekusi dilakukan di luar percakapan tanpa riwayat."
    ),
    branch="sales",
    roles=["manager", "sales_manager", "ai_manager"],
    plugin_key="erpnext-action-drafts",
    parameters={
        "draft_id": {
            "type": "string",
            "description": "Nomor Pending Action Draft (contoh: DRF-2026-11-00001) atau nomor Sales Order (contoh: SAL-ORD-2026-00001)",
        },
        "confirmed": {
            "type": "boolean",
            "description": (
                "Isi false pada langkah 1 untuk mengambil ringkasan konfirmasi awal; isi true pada "
                "langkah 2 untuk mengeksekusi setelah karyawan mengonfirmasi pembayaran Cash tersebut "
                "(jangan mengulang false setelah karyawan mengonfirmasi)."
            ),
            "required": False,
        },
        "confirmation_token": {
            "type": "string",
            "description": (
                "Token tantangan dari hasil pemanggilan langkah 1 bila masih tersedia (wajib hanya "
                "bila eksekusi di luar percakapan tanpa riwayat). Jika tidak tersedia saat percakapan "
                "berlanjut ke pesan berikutnya, panggil confirmed=true tanpa confirmation_token — "
                "jangan mengambil ringkasan ulang untuk mendapatkan token baru dan jangan mengarang nilai token."
            ),
            "required": False,
        },
    },
)
def confirm_cash_payment(draft_id: str, confirmed: bool = False, confirmation_token: str = "") -> dict:
    """Confirm Cash payment (Payment Entry) for an executed Sales Order draft with 2-step confirmation."""
    return _run_confirmed_draft_action(
        draft_id=draft_id,
        action="confirm_cash_payment",
        confirmed=confirmed,
        confirmation_token=confirmation_token,
        reason="",
        executor=_execute_confirm_cash_payment,
    )
