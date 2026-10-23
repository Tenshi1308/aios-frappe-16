"""Allowlisted ERPNext financial and sales report tool."""

import frappe

from aios_v1.lib.tool_registry import ai_tool, get_tool_context

ALLOWED_REPORTS = frozenset(
    {
        "General Ledger",
        "Accounts Receivable",
        "Accounts Payable",
        "Trial Balance",
        "Profit and Loss Statement",
        "Balance Sheet",
        "Cash Flow",
        "Sales Analytics",
    }
)


@ai_tool(
    name="erpnext_report_run",
    description="Menjalankan laporan keuangan atau penjualan ERPNext yang diizinkan.",
    branch=["finance", "sales"],
    plugin_key="erpnext-financial-reports",
    parameters={
        "report_name": {"type": "string", "description": "Nama laporan ERPNext yang diizinkan"},
        "filters": {"type": "object", "description": "Filter laporan", "required": False},
    },
)
def erpnext_report_run(report_name, filters=None):
    if report_name not in ALLOWED_REPORTS:
        frappe.throw("Laporan ini tidak diizinkan untuk AIOS.")
    if filters is not None and not isinstance(filters, dict):
        frappe.throw("filters harus berupa object.")
    report_filters = dict(filters or {})
    company = str(get_tool_context().get("allowed_company") or "").strip()
    if not company:
        frappe.throw("Company default belum dikonfigurasi.")
    report_filters["company"] = company
    from frappe.desk.query_report import run

    return run(report_name=report_name, filters=report_filters)
