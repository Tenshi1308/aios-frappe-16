"""Read-only cross-branch consultation handlers (deterministic + LLM fallback)."""

import json

import frappe

from aios_v1.lib.tool_registry import get_tool_context


def _company() -> str:
    company = str(get_tool_context().get("allowed_company") or "").strip()
    if not company:
        frappe.throw("Company default belum dikonfigurasi.")
    return company


def _customer(payload: dict):
    customer = payload.get("customer")
    if not isinstance(customer, str) or not customer.strip():
        frappe.throw("Konsultasi cabang memerlukan customer yang valid.")
    return frappe.get_doc("Customer", customer.strip(), check_permission="read")


def finance_consultation(*, user_id: str, task_id: str, from_branch: str,
                         message_type: str, payload: dict) -> dict:
    """Return customer credit and receivable facts scoped to the site company."""
    if message_type != "consultation":
        frappe.throw("Finance hanya menerima consultation read-only.")
    customer = _customer(payload)
    company = _company()
    if not frappe.has_permission("Sales Invoice", "read", user=user_id):
        frappe.throw("Izin baca piutang tidak tersedia.")

    from erpnext.selling.doctype.customer.customer import (
        get_credit_limit,
        get_customer_outstanding,
        get_customer_overdue_amount,
    )

    return {
        "customer": customer.name,
        "company": company,
        "credit_limit": get_credit_limit(customer.name, company),
        "outstanding": get_customer_outstanding(customer.name, company),
        "overdue": get_customer_overdue_amount(customer.name, company),
        "currency": frappe.get_cached_value("Company", company, "default_currency"),
    }


def sales_consultation(*, user_id: str, task_id: str, from_branch: str,
                       message_type: str, payload: dict) -> dict:
    """Return customer, recent Sales Order, and Quotation status without writing ERPNext."""
    if message_type != "consultation":
        frappe.throw("Sales hanya menerima consultation read-only.")
    customer = _customer(payload)
    company = _company()
    orders = frappe.get_list(
        "Sales Order",
        filters={"customer": customer.name, "company": company},
        fields=["name", "status", "docstatus", "transaction_date", "grand_total"],
        order_by="modified desc",
        limit_page_length=10,
    )
    quotations = frappe.get_list(
        "Quotation",
        filters={"quotation_to": "Customer", "party_name": customer.name, "company": company},
        fields=["name", "status", "docstatus", "transaction_date", "valid_till", "grand_total"],
        order_by="modified desc",
        limit_page_length=10,
    )
    return {
        "customer": customer.name,
        "company": company,
        "customer_status": (customer.get("disabled", 0) and "disabled") or "active",
        "sales_orders": [dict(order) for order in orders],
        "quotations": [dict(quotation) for quotation in quotations],
    }


def llm_branch_consultation(
    *,
    user_id: str,
    task_id: str,
    from_branch: str,
    to_branch: str,
    message_type: str,
    payload: dict,
) -> dict:
    """Run read-only LLM manager consultation for general questions across any active branch."""
    if message_type != "consultation":
        frappe.throw("Konsultasi lintas cabang hanya menerima message_type consultation read-only.")
    if not isinstance(payload, dict) or not payload:
        frappe.throw("Pertanyaan konsultasi lintas cabang wajib diisi.")

    question = str(
        payload.get("question") or payload.get("query") or payload.get("prompt") or ""
    ).strip()
    extra_context = {
        key: value
        for key, value in payload.items()
        if key not in {"question", "query", "prompt"}
    }
    if not question:
        question = (
            "Jawab pertanyaan konsultasi baca-saja berikut berdasarkan data yang tersedia: "
            + json.dumps(payload, ensure_ascii=False)
        )
        extra_context = {}

    from aios_v1.managers import get_manager

    tool_ctx = get_tool_context()
    usage_records = tool_ctx.get("_usage_records") if isinstance(tool_ctx.get("_usage_records"), list) else None
    target_manager = get_manager(to_branch)
    return target_manager.consult_readonly(
        question=question,
        from_branch=from_branch,
        user=user_id,
        context_data=extra_context or None,
        usage_records=usage_records,
    )
