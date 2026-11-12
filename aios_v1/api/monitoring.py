"""Whitelisted API resmi Frappe untuk monitoring penggunaan token (developer).

Migrasi Fase 1 dari dispatcher kustom `/api/monitoring/usage*` ke
`/api/method/aios_v1.api.monitoring.*` (keputusan Ten, Opsi A).

Nama method dikunci Ten: `usage_summary`, `usage_by_company`, `usage_by_branch`.

PERUBAHAN GATE (disetujui Ten): monitoring kini memakai helper `_is_admin`
(`aios_v1/permissions.py:73-76`) = `Administrator` + role `AIOS Admin`.
Peran `System Manager` (yang lolos lewat pengecekan `DEVELOPER` lama di
`dispatcher.py:137-139`) TIDAK lagi diizinkan. Ini memperketat gate, bukan
melemahkan. Non-admin ditolak `frappe.PermissionError` (403).
"""

from urllib.parse import unquote

import frappe

from aios_v1.permissions import _is_admin


def _require_admin() -> None:
    """Hanya Administrator / AIOS Admin; tamu & staf biasa ditolak 403."""
    user = frappe.session.user
    if not user or not _is_admin(user):
        frappe.throw("Akses ditolak.", frappe.PermissionError)


def _get_aios_client_users() -> list:
    names = frappe.get_all(
        "Has Role",
        filters={"role": "AIOS Client", "parenttype": "User"},
        pluck="parent",
        distinct=1,
        limit_page_length=0,
    )
    if not names:
        return []
    return frappe.get_all(
        "User",
        filters={"name": ["in", names]},
        fields=["name", "full_name", "aios_status", "aios_company_name"],
        limit_page_length=0,
    )


def _usage_totals(user: str) -> tuple[int, int, float]:
    rows = frappe.get_all(
        "AIOS Token Usage",
        filters={"user": user},
        fields=["input_tokens", "output_tokens", "cost"],
        limit_page_length=0,
    )
    return (
        sum(int(row.get("input_tokens") or 0) for row in rows),
        sum(int(row.get("output_tokens") or 0) for row in rows),
        sum(float(row.get("cost") or 0) for row in rows),
    )


# ---------------------------------------------------------------------------
# GET /api/method/aios_v1.api.monitoring.usage_summary
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def usage_summary() -> dict:
    """Ringkasan pemakaian token per user klien."""
    _require_admin()
    clients = _get_aios_client_users()
    companies = []
    for user in clients:
        total_in, total_out, total_cost = _usage_totals(user.name)
        companies.append(
            {
                "id": user.name,
                "name": user.aios_company_name or user.full_name or user.name,
                "status": (user.aios_status or "UNKNOWN").upper(),
                "conversations": frappe.db.count("AIOS Conversation", {"user": user.name}),
                "inputTokens": total_in,
                "outputTokens": total_out,
                "costIdr": round(total_cost),
            }
        )
    return {"companies": companies}


# ---------------------------------------------------------------------------
# GET /api/method/aios_v1.api.monitoring.usage_by_company
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def usage_by_company(company_id: str) -> dict:
    """Drill-down pemakaian token per cabang untuk satu user klien."""
    _require_admin()
    company_id = unquote(str(company_id))
    clients = _get_aios_client_users()
    user = frappe.db.get_value(
        "User",
        company_id,
        ["name", "full_name", "aios_status", "aios_company_name"],
        as_dict=True,
    )
    if not user and clients:
        user = clients[0]

    branches: dict = {}
    if user:
        rows = frappe.get_all(
            "AIOS Token Usage",
            filters={"user": user.name},
            fields=["branch", "input_tokens", "output_tokens", "cost"],
            limit_page_length=0,
        )
        for row in rows:
            key = row.branch or "GENERAL"
            bucket = branches.setdefault(
                key,
                {"inputTokens": 0, "outputTokens": 0, "calls": 0, "costIdr": 0.0},
            )
            bucket["inputTokens"] += int(row.get("input_tokens") or 0)
            bucket["outputTokens"] += int(row.get("output_tokens") or 0)
            bucket["calls"] += 1
            bucket["costIdr"] += float(row.get("cost") or 0)

    branches_list = [
        {
            "branch": key,
            "inputTokens": value["inputTokens"],
            "outputTokens": value["outputTokens"],
            "calls": value["calls"],
            "costIdr": round(value["costIdr"]),
        }
        for key, value in branches.items()
    ]
    branches_list.sort(key=lambda x: x["inputTokens"] + x["outputTokens"], reverse=True)

    return {
        "company": {
            "id": user.name if user else company_id,
            "name": (
                (user.aios_company_name or user.full_name or user.name) if user else "Client"
            ),
            "status": ((user.aios_status or "UNKNOWN").upper() if user else "UNKNOWN"),
        },
        "branches": branches_list,
    }


# ---------------------------------------------------------------------------
# GET /api/method/aios_v1.api.monitoring.usage_by_branch
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def usage_by_branch(company_id: str, branch: str) -> dict:
    """Drill-down pemakaian token per worker pada satu cabang."""
    _require_admin()
    company_id = unquote(str(company_id))
    branch = unquote(str(branch))
    clients = _get_aios_client_users()
    user = frappe.db.get_value(
        "User",
        company_id,
        ["name", "full_name", "aios_status", "aios_company_name"],
        as_dict=True,
    )
    if not user and clients:
        user = clients[0]

    workers: dict = {}
    if user:
        rows = frappe.get_all(
            "AIOS Token Usage",
            filters={"user": user.name, "branch": branch},
            fields=["agent", "input_tokens", "output_tokens", "cost"],
            limit_page_length=0,
        )
        for row in rows:
            key = row.agent or "manager"
            bucket = workers.setdefault(
                key,
                {"inputTokens": 0, "outputTokens": 0, "calls": 0, "costIdr": 0.0},
            )
            bucket["inputTokens"] += int(row.get("input_tokens") or 0)
            bucket["outputTokens"] += int(row.get("output_tokens") or 0)
            bucket["calls"] += 1
            bucket["costIdr"] += float(row.get("cost") or 0)

    workers_list = [
        {
            "workerKey": key,
            "inputTokens": value["inputTokens"],
            "outputTokens": value["outputTokens"],
            "calls": value["calls"],
            "costIdr": round(value["costIdr"]),
        }
        for key, value in workers.items()
    ]
    workers_list.sort(key=lambda x: x["inputTokens"] + x["outputTokens"], reverse=True)
    return {"branch": branch, "workers": workers_list}
