"""Server-owned, read-only catalog for Ekasa Desk ERP domains (active and planned)."""

from copy import deepcopy

from aios_v1.lib.desktop_modules import get_module_keys
from aios_v1.permissions import ERP_CLIENT_DOCTYPES

_DOMAINS = (
    {
        "key": "sales",
        "label": "Sales",
        "icon": "tag",
        "color_token": "domain-sales",
        "status": "active",
        "modules": ("sales_invoice", "sales_order", "customer", "item"),
        "cards": (
            {
                "key": "revenue_month",
                "label": "Invoice bulan ini",
                "aggregate": "sum",
                "doctype": "Sales Invoice",
                "field": "base_grand_total",
                "format": "currency",
                "filters": {"docstatus": 1},
            },
            {
                "key": "open_orders",
                "label": "Order terbuka",
                "aggregate": "count",
                "doctype": "Sales Order",
                "field": "name",
                "format": "number",
                "filters": {
                    "docstatus": 1,
                    "status": ["not in", ["Closed", "Completed"]],
                },
            },
            {
                "key": "receivable",
                "label": "Piutang outstanding",
                "aggregate": "sum",
                "doctype": "Sales Invoice",
                "field": "outstanding_amount",
                "format": "currency",
                "filters": {"docstatus": 1, "outstanding_amount": [">", 0]},
            },
            {
                "key": "customers",
                "label": "Customer aktif",
                "aggregate": "count",
                "doctype": "Customer",
                "field": "name",
                "format": "number",
                "filters": {"disabled": 0},
            },
        ),
    },
    {
        "key": "finance",
        "label": "Finance",
        "icon": "calc",
        "color_token": "domain-finance",
        "status": "active",
        "modules": ("purchase_invoice", "payment_entry", "supplier"),
        "cards": (
            {
                "key": "payable",
                "label": "Hutang outstanding",
                "aggregate": "sum",
                "doctype": "Purchase Invoice",
                "field": "outstanding_amount",
                "format": "currency",
                "filters": {"docstatus": 1, "outstanding_amount": [">", 0]},
            },
            {
                "key": "payments",
                "label": "Total pembayaran",
                "aggregate": "sum",
                "doctype": "Payment Entry",
                "field": "base_paid_amount",
                "format": "currency",
                "filters": {"docstatus": 1, "payment_type": ["in", ["Receive", "Pay"]]},
            },
            {
                "key": "journals",
                "label": "Jurnal tercatat",
                "aggregate": "count",
                "doctype": "Journal Entry",
                "field": "name",
                "format": "number",
                "filters": {"docstatus": 1},
            },
            {
                "key": "suppliers",
                "label": "Supplier aktif",
                "aggregate": "count",
                "doctype": "Supplier",
                "field": "name",
                "format": "number",
                "filters": {"disabled": 0},
            },
        ),
    },
    {
        "key": "purchasing",
        "label": "Purchasing",
        "icon": "cart",
        "color_token": "domain-purchasing",
        "status": "planned",
        "modules": (),
        "cards": (),
    },
    {
        "key": "inventory",
        "label": "Inventory",
        "icon": "box",
        "color_token": "domain-inventory",
        "status": "planned",
        "modules": (),
        "cards": (),
    },
    {
        "key": "manufacturing",
        "label": "Manufacturing",
        "icon": "factory",
        "color_token": "domain-manufacturing",
        "status": "planned",
        "modules": (),
        "cards": (),
    },
    {
        "key": "projects",
        "label": "Projects",
        "icon": "kanban",
        "color_token": "domain-projects",
        "status": "planned",
        "modules": (),
        "cards": (),
    },
    {
        "key": "crm",
        "label": "CRM",
        "icon": "target",
        "color_token": "domain-crm",
        "status": "planned",
        "modules": (),
        "cards": (),
    },
    {
        "key": "assets",
        "label": "Assets",
        "icon": "building",
        "color_token": "domain-assets",
        "status": "planned",
        "modules": (),
        "cards": (),
    },
    {
        "key": "support",
        "label": "Support",
        "icon": "headset",
        "color_token": "domain-support",
        "status": "planned",
        "modules": (),
        "cards": (),
    },
    {
        "key": "quality",
        "label": "Quality",
        "icon": "shield",
        "color_token": "domain-quality",
        "status": "planned",
        "modules": (),
        "cards": (),
    },
    {
        "key": "accounting",
        "label": "Accounting",
        "icon": "wallet",
        "color_token": "domain-accounting",
        "status": "planned",
        "modules": (),
        "cards": (),
    },
)


def _validate_domain_catalog(domains: tuple[dict, ...]) -> dict[str, dict]:
    known_modules = set(get_module_keys())
    seen_keys: set[str] = set()
    seen_tokens: set[str] = set()
    by_key: dict[str, dict] = {}

    for domain in domains:
        key = domain.get("key")
        color_token = domain.get("color_token")
        status = domain.get("status")
        if not key or key in seen_keys:
            raise RuntimeError(f"Desktop domain catalog has duplicate or empty key: {key!r}")
        if not color_token or color_token in seen_tokens:
            raise RuntimeError(f"Desktop domain catalog has duplicate or empty color_token: {color_token!r}")
        if status not in {"active", "planned"}:
            raise RuntimeError(f"Desktop domain {key!r} has invalid status: {status!r}")
        for module_key in domain.get("modules", ()):
            if module_key not in known_modules:
                raise RuntimeError(
                    f"Desktop domain {key!r} references unknown module {module_key!r}"
                )
        for card in domain.get("cards", ()):
            doctype = card.get("doctype")
            if doctype not in ERP_CLIENT_DOCTYPES:
                raise RuntimeError(
                    f"Desktop domain {key!r} card {card.get('key')!r} uses DocType "
                    f"{doctype!r} outside ERP_CLIENT_DOCTYPES"
                )
        seen_keys.add(key)
        seen_tokens.add(color_token)
        by_key[key] = domain

    return by_key


_DOMAINS_BY_KEY = _validate_domain_catalog(_DOMAINS)


def get_domain_keys() -> list[str]:
    """Return active domain keys used to validate API and agent requests."""
    return [domain["key"] for domain in _DOMAINS if domain["status"] == "active"]


def get_domain_definition(domain_key: str) -> dict | None:
    """Return a copy of one server-owned domain definition (active or planned)."""
    if not isinstance(domain_key, str):
        return None
    domain = _DOMAINS_BY_KEY.get(domain_key)
    return deepcopy(domain) if domain else None


def get_domain_catalog() -> list[dict]:
    """Return metadata for active domains only; omit KPI query internals and planned domains."""
    return [
        {
            "key": domain["key"],
            "label": domain["label"],
            "icon": domain["icon"],
            "color_token": domain["color_token"],
            "module_count": len(domain["modules"]),
        }
        for domain in _DOMAINS
        if domain["status"] == "active"
    ]


def get_planned_domain_count() -> int:
    """Return the number of planned domains in the server catalog."""
    return sum(1 for domain in _DOMAINS if domain["status"] == "planned")
