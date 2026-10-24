"""Allowlisted ERPNext financial and sales report tool."""

import frappe

from aios_v1.lib.error_utils import safe_error
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

# Filter wajib per report, dibaca dari source ERPNext v16 (bukan tebakan):
# - Trial Balance: fiscal_year wajib (accounts/report/trial_balance/trial_balance.py).
# - P&L, Balance Sheet, Cash Flow: periodicity wajib dan salah satu pasangan periode;
#   jalur fiscal year juga butuh filter_based_on (erpnext/accounts/report/financial_statements.py).
# - General Ledger: from_date dan to_date (general_ledger.py::validate_filters).
# - Sales Analytics: from_date dan to_date dipakai di semua query periodenya.
# - Accounts Receivable/Payable: report_date default hari ini di source; tanpa wajib tambahan.
REPORT_FILTER_GUIDE = {
    "Accounts Payable": {"required": (), "any_of": ()},
    "Accounts Receivable": {"required": (), "any_of": ()},
    "Balance Sheet": {
        "required": ("periodicity",),
        "any_of": (
            ("filter_based_on", "from_fiscal_year", "to_fiscal_year"),
            ("period_start_date", "period_end_date"),
        ),
    },
    "Cash Flow": {
        "required": ("periodicity",),
        "any_of": (
            ("filter_based_on", "from_fiscal_year", "to_fiscal_year"),
            ("period_start_date", "period_end_date"),
        ),
    },
    "General Ledger": {"required": ("from_date", "to_date"), "any_of": ()},
    "Profit and Loss Statement": {
        "required": ("periodicity",),
        "any_of": (
            ("filter_based_on", "from_fiscal_year", "to_fiscal_year"),
            ("period_start_date", "period_end_date"),
        ),
    },
    "Sales Analytics": {"required": ("from_date", "to_date"), "any_of": ()},
    "Trial Balance": {"required": ("fiscal_year",), "any_of": ()},
}

_REPORT_FILTER_DESCRIPTION = (
    "Menjalankan laporan keuangan atau penjualan ERPNext yang diizinkan. Filter wajib per laporan: "
    "Trial Balance: fiscal_year. Profit and Loss Statement, Balance Sheet, Cash Flow: periodicity "
    "dan satu pasangan periode — filter_based_on='Fiscal Year' dengan from_fiscal_year+to_fiscal_year, "
    "atau period_start_date+period_end_date. General Ledger dan Sales Analytics: from_date+to_date. "
    "Accounts Receivable dan Accounts Payable: report_date opsional (default hari ini)."
)


def _missing_report_filters(report_name, filters):
    """Kembalikan daftar filter wajib yang belum diisi; kosong bila lengkap."""
    guide = REPORT_FILTER_GUIDE.get(report_name)
    if not guide:
        return []
    missing = [key for key in guide["required"] if not filters.get(key)]
    for option in guide["any_of"]:
        if all(filters.get(key) for key in option):
            break
    else:
        if guide["any_of"]:
            missing.append(" atau ".join("+".join(option) for option in guide["any_of"]))
    return missing


@ai_tool(
    name="erpnext_report_run",
    description=_REPORT_FILTER_DESCRIPTION,
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
    missing = _missing_report_filters(report_name, report_filters)
    if missing:
        return safe_error(
            f"Report {report_name} butuh filter yang belum diisi: {', '.join(missing)}. "
            "Lengkapi filter tersebut lalu panggil ulang tool ini.",
            "REPORT_FILTER_REQUIRED",
        )
    from frappe.desk.query_report import run

    return run(report_name=report_name, filters=report_filters)
