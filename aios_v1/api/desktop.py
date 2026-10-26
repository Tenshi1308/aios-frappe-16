"""Read-only whitelisted API for Ekasa Desk modules."""

import json
from datetime import date
from functools import wraps

import frappe
from frappe.sessions import get_csrf_token
from frappe.utils import format_datetime, now_datetime
from frappe.utils.scheduler import is_scheduler_inactive

from aios_v1.lib.desktop_modules import (
    get_module_catalog,
    get_module_definition,
)
from aios_v1.lib.error_utils import log_exception
from aios_v1.lib.tool_registry import _resolve_allowed_company
from aios_v1.permissions import ERP_CLIENT_DOCTYPES
from aios_v1.plugin_manager.registry import get_public_branches

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 100
RESET_JOB_METHOD = "aios_v1.services.usage.reset_daily_counters"
_ALLOWED_FILTER_KEYS = frozenset({"date_from", "date_to", "status", "party"})
_THEME_OPTIONS = ("Automatic", "Light", "Dark")
_ALLOWED_THEMES = frozenset(_THEME_OPTIONS)


def _safe_api_errors(method_name: str):
    """Whitelist the final wrapper and keep internal errors in Error Log."""

    def decorate(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except (frappe.AuthenticationError, frappe.PermissionError, frappe.ValidationError):
                raise
            except Exception as exc:
                log_exception(
                    "AIOS Desktop API",
                    exc=exc,
                    context=method_name,
                    defer_insert=True,
                )
                frappe.throw("Data modul tidak dapat dimuat. Coba lagi nanti.", frappe.ValidationError)

        # Frappe records callable objects in its whitelist registry. Register
        # the safe wrapper itself so the HTTP route cannot reference an
        # unregistered outer callable.
        return frappe.whitelist(methods=["GET"])(wrapped)

    return decorate


def _require_active_client() -> tuple[str, dict]:
    user = getattr(frappe.session, "user", None)
    if not user or user == "Guest":
        frappe.throw("Belum login.", frappe.AuthenticationError)
    try:
        session_obj = frappe.local.session_obj
    except AttributeError as exc:
        log_exception(
            "AIOS Desktop Session",
            exc=exc,
            context="desktop API memerlukan sesi HTTP Frappe",
            defer_insert=True,
        )
        frappe.throw("Sesi tidak valid. Silakan login kembali.", frappe.AuthenticationError)
    if session_obj is None:
        try:
            raise AttributeError("session_obj")
        except AttributeError as exc:
            log_exception(
                "AIOS Desktop Session",
                exc=exc,
                context="desktop API memerlukan sesi HTTP Frappe",
                defer_insert=True,
            )
        frappe.throw("Sesi tidak valid. Silakan login kembali.", frappe.AuthenticationError)
    if user == "Administrator":
        frappe.throw("Akses ditolak.", frappe.PermissionError)

    roles = set(frappe.get_roles(user))
    if "AIOS Client" not in roles:
        frappe.throw("Akses ditolak.", frappe.PermissionError)

    user_state = frappe.db.get_value("User", user, ["full_name", "aios_status", "enabled"], as_dict=True)
    if not user_state or user_state.aios_status != "Active" or not user_state.enabled:
        frappe.throw("Akun belum aktif.", frappe.AuthenticationError)
    return user, user_state


def _company_context() -> dict:
    company_id = _resolve_allowed_company()
    if not company_id:
        log_exception("AIOS Desktop Company", context="Company aktif tidak terkonfigurasi.")
        frappe.throw("Company aktif belum dikonfigurasi.", frappe.ValidationError)

    company = frappe.db.get_value(
        "Company", company_id, ["company_name", "default_currency"], as_dict=True
    )
    if not company:
        log_exception("AIOS Desktop Company", context="Company aktif tidak ditemukan.")
        frappe.throw("Company aktif belum dikonfigurasi.", frappe.ValidationError)
    if not company.default_currency:
        log_exception("AIOS Desktop Currency", context="Company aktif tidak memiliki default_currency.")
        frappe.throw("Mata uang company aktif belum dikonfigurasi.", frappe.ValidationError)

    return {
        "id": company_id,
        "name": company.company_name or company_id,
        "currency": company.default_currency,
    }


def _definition(module_key: str, doctype: str | None = None) -> dict:
    module = get_module_definition(module_key)
    if not module:
        frappe.throw("Modul tidak ditemukan.", frappe.ValidationError)
    if doctype is not None and doctype != module["doctype"]:
        frappe.throw("DocType tidak tersedia pada modul ini.", frappe.ValidationError)
    if module["doctype"] not in ERP_CLIENT_DOCTYPES:
        log_exception("AIOS Desktop Catalog", context="DocType modul di luar allowlist.")
        frappe.throw("Modul tidak dapat dimuat.", frappe.ValidationError)

    meta = frappe.get_meta(module["doctype"])
    allowed_fields = set(meta.get_valid_columns())
    declared_fields = {column["field"] for column in module["columns"]}
    declared_fields.update(module["search_fields"])
    declared_fields.add(module["order_field"])
    for filter_definition in module["filter_fields"].values():
        declared_fields.add(filter_definition["field"])
    for card in module["cards"]:
        declared_fields.add(card["field"])
        declared_fields.update(card["filters"])
    declared_fields.update(module["base_filters"])
    if not declared_fields.issubset(allowed_fields):
        log_exception(
            "AIOS Desktop Catalog",
            context=f"Field katalog tidak valid untuk {module['doctype']}.",
        )
        frappe.throw("Modul tidak dapat dimuat.", frappe.ValidationError)
    return module


def _read_filters(module: dict, value) -> dict:
    if value in (None, ""):
        supplied = {}
    elif isinstance(value, str):
        try:
            supplied = json.loads(value)
        except (TypeError, ValueError) as exc:
            log_exception("AIOS Desktop Filters", exc=exc)
            frappe.throw("Filter tidak valid.", frappe.ValidationError)
    else:
        supplied = value

    if not isinstance(supplied, dict):
        frappe.throw("Filter harus berupa object.", frappe.ValidationError)
    if any(key not in _ALLOWED_FILTER_KEYS for key in supplied):
        frappe.throw("Filter tidak diizinkan.", frappe.ValidationError)

    filters = {}
    allowed = module["filter_fields"]
    for key, raw in supplied.items():
        if key not in allowed:
            frappe.throw("Filter tidak tersedia pada modul ini.", frappe.ValidationError)
        if raw in (None, ""):
            continue
        if not isinstance(raw, str):
            frappe.throw("Nilai filter tidak valid.", frappe.ValidationError)

        definition = allowed[key]
        if key in {"date_from", "date_to"}:
            try:
                parsed = date.fromisoformat(raw)
            except ValueError as exc:
                log_exception("AIOS Desktop Date Filter", exc=exc)
                frappe.throw("Format tanggal filter tidak valid.", frappe.ValidationError)
            filters[definition["field"]] = [definition["operator"], parsed.isoformat()]
        elif definition["operator"] == "like":
            filters[definition["field"]] = ["like", f"%{raw}%"]
        else:
            filters[definition["field"]] = [definition["operator"], raw]
    return filters


def _server_filters(module: dict, company_id: str, client_filters: dict | None = None) -> dict:
    filters = dict(module["base_filters"])
    meta = frappe.get_meta(module["doctype"])
    if meta.has_field("company"):
        filters["company"] = company_id
    elif module["group"] in {"Sales", "Finance"} and module["doctype"] not in {"Customer", "Supplier", "Item"}:
        log_exception("AIOS Desktop Company", context=f"DocType {module['doctype']} tanpa field company.")
        frappe.throw("Cakupan company tidak dapat dipastikan.", frappe.ValidationError)
    if client_filters:
        filters.update(client_filters)
    return filters


def _page_values(page, page_size) -> tuple[int, int]:
    try:
        page_value = int(page)
        page_size_value = int(page_size)
    except (TypeError, ValueError) as exc:
        log_exception("AIOS Desktop Pagination", exc=exc)
        frappe.throw("Nomor halaman tidak valid.", frappe.ValidationError)
    return max(1, page_value), min(MAX_PAGE_SIZE, max(1, page_size_value))


def _pagination_total(doctype: str, filters: dict) -> int:
    result = frappe.get_list(
        doctype,
        fields=[{"COUNT": "*", "as": "total"}],
        filters=filters,
        limit_page_length=1,
    )
    return int((result[0].get("total") if result else 0) or 0)


def _list_rows(module: dict, company_id: str, page, page_size, filters_value=None) -> tuple[list[dict], dict]:
    page_value, page_size_value = _page_values(page, page_size)
    user_filters = _read_filters(module, filters_value)
    filters = _server_filters(module, company_id, user_filters)
    total = _pagination_total(module["doctype"], filters)
    rows = frappe.get_list(
        module["doctype"],
        fields=[column["field"] for column in module["columns"]],
        filters=filters,
        order_by=f"{module['order_field']} desc, name desc",
        limit_start=(page_value - 1) * page_size_value,
        limit_page_length=page_size_value,
    )
    pages = (total + page_size_value - 1) // page_size_value
    return [dict(row) for row in rows], {
        "page": page_value,
        "page_size": page_size_value,
        "total": total,
        "total_pages": pages,
    }


def _card_value(module: dict, card: dict, company_id: str):
    filters = _server_filters(module, company_id, card["filters"])
    aggregate = card["aggregate"].upper()
    field = card["field"]
    rows = frappe.get_list(
        module["doctype"],
        fields=[{aggregate: field, "as": "value"}],
        filters=filters,
        limit_page_length=1,
    )
    value = (rows[0].get("value") if rows else 0) or 0
    return {
        "key": card["key"],
        "label": card["label"],
        "value": value,
        "format": card["format"],
        "scope": card["scope"],
    }


def _cards(module: dict, company_id: str, currency: str) -> list[dict]:
    cards = []
    for definition in module["cards"]:
        card = _card_value(module, definition, company_id)
        if card["format"] == "currency":
            card["currency"] = currency
        cards.append(card)
    return cards


def _public_module(module: dict) -> dict:
    return next(item for item in get_module_catalog() if item["key"] == module["key"])


def _module_response(module: dict, company: dict, page, page_size, filters=None) -> dict:
    rows, pagination = _list_rows(module, company["id"], page, page_size, filters)
    doctype = {
        "doctype": module["doctype"],
        "label": module["label"],
        "columns": _public_module(module)["columns"],
    }
    return {
        "module": _public_module(module),
        "cards": _cards(module, company["id"], company["currency"]),
        "doctypes": [doctype],
        "rows": rows,
        "pagination": pagination,
    }


@_safe_api_errors("desktop.bootstrap")
def bootstrap():
    user, user_state = _require_active_client()
    company = _company_context()
    return {
        "user": {"id": user, "name": user_state.full_name or user},
        "company": company,
        "agents": get_public_branches(),
        "modules": get_module_catalog(),
        "csrf_token": get_csrf_token(),
    }


@_safe_api_errors("desktop.module")
def module(module: str, page=1, page_size=DEFAULT_PAGE_SIZE, filters=None):
    _require_active_client()
    definition = _definition(module)
    company = _company_context()
    return _module_response(definition, company, page, page_size, filters)


@_safe_api_errors("desktop.list")
def list(module: str, doctype: str, page=1, page_size=DEFAULT_PAGE_SIZE, filters=None):
    _require_active_client()
    definition = _definition(module, doctype)
    company = _company_context()
    rows, pagination = _list_rows(definition, company["id"], page, page_size, filters)
    return {
        "module": _public_module(definition),
        "doctype": definition["doctype"],
        "rows": rows,
        "pagination": pagination,
    }


@_safe_api_errors("desktop.search")
def search(q: str, limit=DEFAULT_SEARCH_LIMIT):
    _require_active_client()
    company = _company_context()
    if not isinstance(q, str):
        frappe.throw("Kata pencarian tidak valid.", frappe.ValidationError)
    query = q.strip()
    if not query:
        return {"results": []}
    try:
        result_limit = min(MAX_SEARCH_LIMIT, max(1, int(limit)))
    except (TypeError, ValueError) as exc:
        log_exception("AIOS Desktop Search", exc=exc)
        frappe.throw("Batas pencarian tidak valid.", frappe.ValidationError)

    catalog = get_module_catalog()
    results = [
        {"type": "module", "module": item}
        for item in catalog
        if query.casefold() in item["label"].casefold() or query.casefold() in item["group"].casefold()
    ][:result_limit]

    for module_definition in map(lambda item: get_module_definition(item["key"]), catalog):
        remaining = result_limit - len(results)
        if remaining <= 0:
            break
        base_filters = _server_filters(module_definition, company["id"])
        pattern = f"%{query}%"
        or_filters = [[field, "like", pattern] for field in module_definition["search_fields"]]
        rows = frappe.get_list(
            module_definition["doctype"],
            fields=[column["field"] for column in module_definition["columns"]],
            filters=base_filters,
            or_filters=or_filters,
            order_by=f"{module_definition['order_field']} desc, name desc",
            limit_page_length=remaining,
        )
        public_module = _public_module(module_definition)
        for row in rows:
            results.append(
                {
                    "type": "document",
                    "module": public_module,
                    "doctype": module_definition["doctype"],
                    "name": row.get("name"),
                    "row": dict(row),
                }
            )
    return {"results": results[:result_limit]}


def _site_quota() -> dict:
    raw_limit = frappe.db.get_single_value("AIOS Setting", "site_token_limit")
    raw_used = frappe.db.get_single_value("AIOS Setting", "site_tokens_used")
    limit = max(0, int(raw_limit or 0))
    used = max(0, int(raw_used or 0))
    if limit <= 0:
        return {
            "limit": limit,
            "used": used,
            "remaining": None,
            "percent_used": None,
        }
    return {
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
        "percent_used": round(used / limit * 100, 2),
    }


def _reset_status() -> dict:
    scheduler_active = not bool(is_scheduler_inactive(verbose=False))
    if not scheduler_active:
        return {
            "at": None,
            "at_label": None,
            "seconds_remaining": None,
            "source": "unknown",
            "scheduler_active": False,
        }

    job_name = frappe.db.get_value(
        "Scheduled Job Type",
        {"method": RESET_JOB_METHOD, "stopped": 0},
        "name",
    )
    if not job_name:
        return {
            "at": None,
            "at_label": None,
            "seconds_remaining": None,
            "source": "unknown",
            "scheduler_active": True,
        }

    job = frappe.get_doc("Scheduled Job Type", job_name)
    at = job.get_next_execution()
    if not at:
        return {
            "at": None,
            "at_label": None,
            "seconds_remaining": None,
            "source": "unknown",
            "scheduler_active": True,
        }

    seconds_remaining = max(0, int((at - now_datetime()).total_seconds()))
    return {
        "at": at.isoformat(),
        "at_label": format_datetime(at, "HH:mm"),
        "seconds_remaining": seconds_remaining,
        "source": "scheduled",
        "scheduler_active": True,
    }


@_safe_api_errors("desktop.settings")
def settings():
    user, user_state = _require_active_client()
    company = _company_context()
    persona = frappe.db.get_value("User", user, "aios_persona")
    raw_theme = frappe.db.get_value("User", user, "desk_theme")
    theme_value = raw_theme if raw_theme in _ALLOWED_THEMES else "Automatic"
    return {
        "profile": {
            "name": user_state.full_name or user,
            "persona": persona or None,
            "status": user_state.aios_status,
        },
        "company": company,
        "quota": _site_quota(),
        "reset": _reset_status(),
        "theme": {
            "value": theme_value,
            "options": [*_THEME_OPTIONS],
        },
    }
