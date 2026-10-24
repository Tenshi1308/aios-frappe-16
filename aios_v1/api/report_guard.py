"""Guard satu titik entry `frappe.desk.query_report.run` untuk `AIOS Client`.

Report standar ERPNext memakai raw SQL yang hanya menghormati `filters.company`
apa pun yang dipanggil (AR bahkan fallback ke `Global Defaults.default_company`),
sementara layer permission (hook/User Permission) tidak menyentuh raw SQL. Untuk
`AIOS Client`: report dibatasi `ALLOWED_REPORTS`, `filters["company"]` dipaksa ke
company aktif, dan prepared report dimatikan karena hasil cache tidak dijamin
company-scope. User lain (Administrator, AIOS Admin, System User) pass-through.
"""

import json

import frappe

from aios_v1.lib.error_utils import log_exception


def run_query_report(
    report_name,
    filters=None,
    user=None,
    ignore_prepared_report=False,
    custom_columns=None,
    is_tree=False,
    parent_field=None,
    are_default_filters=True,
    js_filters=None,
):
    from frappe.desk.query_report import run as original_run

    from aios_v1.lib.erpnext_financial_reports import ALLOWED_REPORTS
    from aios_v1.lib.tool_registry import _resolve_allowed_company
    from aios_v1.permissions import _is_admin, _is_client

    user = user or frappe.session.user
    if _is_admin(user) or not _is_client(user):
        return original_run(
            report_name=report_name,
            filters=filters,
            user=user,
            ignore_prepared_report=ignore_prepared_report,
            custom_columns=custom_columns,
            is_tree=is_tree,
            parent_field=parent_field,
            are_default_filters=are_default_filters,
            js_filters=js_filters,
        )

    if report_name not in ALLOWED_REPORTS:
        frappe.throw(
            "Report ini tidak diizinkan untuk AIOS.",
            frappe.PermissionError,
        )

    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except (TypeError, ValueError) as exc:
            log_exception("AIOS Report Guard Filters", exc=exc, context=f"report={report_name}")
            frappe.throw("Filter report tidak valid.")
    if filters is not None and not isinstance(filters, dict):
        log_exception(
            "AIOS Report Guard Filters",
            context=f"report={report_name}; tipe filters tidak didukung",
        )
        frappe.throw("Filter report tidak valid.")

    company = _resolve_allowed_company()
    if not company:
        frappe.throw("Company default belum dikonfigurasi.")
    filters = dict(filters or {})
    filters["company"] = company

    return original_run(
        report_name=report_name,
        filters=filters,
        ignore_prepared_report=True,
        custom_columns=custom_columns,
        is_tree=is_tree,
        parent_field=parent_field,
        are_default_filters=are_default_filters,
        js_filters=js_filters,
    )
