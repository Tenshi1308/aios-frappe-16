"""Read-only Finance and Sales handlers for cross-branch consultation."""

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
    """Return customer and recent Sales Order status without writing ERPNext."""
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
    return {
        "customer": customer.name,
        "company": company,
        "customer_status": (customer.get("disabled", 0) and "disabled") or "active",
        "sales_orders": [dict(order) for order in orders],
    }
