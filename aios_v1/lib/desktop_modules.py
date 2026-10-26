"""Server-owned, read-only catalog for Ekasa Desk Sales and Finance modules."""

from copy import deepcopy

from aios_v1.permissions import ERP_CLIENT_DOCTYPES

_MODULES = (
    {
        "key": "sales_invoice",
        "label": "Sales Invoice",
        "group": "Sales",
        "icon": "file",
        "doctype": "Sales Invoice",
        "columns": (
            {"key": "name", "label": "Nomor", "field": "name", "format": "text"},
            {"key": "date", "label": "Tanggal", "field": "posting_date", "format": "date"},
            {"key": "party", "label": "Customer", "field": "customer_name", "format": "text"},
            {"key": "status", "label": "Status", "field": "status", "format": "text"},
            {
                "key": "amount",
                "label": "Total",
                "field": "base_grand_total",
                "format": "currency",
            },
        ),
        "filters": (
            {"key": "date_from", "label": "Dari tanggal", "type": "date"},
            {"key": "date_to", "label": "Sampai tanggal", "type": "date"},
            {"key": "status", "label": "Status", "type": "text"},
            {"key": "party", "label": "Customer", "type": "text"},
        ),
        "filter_fields": {
            "date_from": {"field": "posting_date", "operator": ">="},
            "date_to": {"field": "posting_date", "operator": "<="},
            "status": {"field": "status", "operator": "="},
            "party": {"field": "customer", "operator": "like"},
        },
        "search_fields": ("name", "customer", "customer_name"),
        "order_field": "posting_date",
        "base_filters": {"docstatus": 1},
        "cards": (
            {
                "key": "count",
                "label": "Invoice disetujui",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
            {
                "key": "total",
                "label": "Total invoice",
                "aggregate": "sum",
                "field": "base_grand_total",
                "format": "currency",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
        ),
    },
    {
        "key": "sales_order",
        "label": "Sales Order",
        "group": "Sales",
        "icon": "file",
        "doctype": "Sales Order",
        "columns": (
            {"key": "name", "label": "Nomor", "field": "name", "format": "text"},
            {"key": "date", "label": "Tanggal", "field": "transaction_date", "format": "date"},
            {"key": "party", "label": "Customer", "field": "customer_name", "format": "text"},
            {"key": "status", "label": "Status", "field": "status", "format": "text"},
            {
                "key": "amount",
                "label": "Total",
                "field": "base_grand_total",
                "format": "currency",
            },
        ),
        "filters": (
            {"key": "date_from", "label": "Dari tanggal", "type": "date"},
            {"key": "date_to", "label": "Sampai tanggal", "type": "date"},
            {"key": "status", "label": "Status", "type": "text"},
            {"key": "party", "label": "Customer", "type": "text"},
        ),
        "filter_fields": {
            "date_from": {"field": "transaction_date", "operator": ">="},
            "date_to": {"field": "transaction_date", "operator": "<="},
            "status": {"field": "status", "operator": "="},
            "party": {"field": "customer", "operator": "like"},
        },
        "search_fields": ("name", "customer", "customer_name"),
        "order_field": "transaction_date",
        "base_filters": {"docstatus": 1},
        "cards": (
            {
                "key": "count",
                "label": "Order disetujui",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
            {
                "key": "total",
                "label": "Total order",
                "aggregate": "sum",
                "field": "base_grand_total",
                "format": "currency",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
        ),
    },
    {
        "key": "purchase_invoice",
        "label": "Purchase Invoice",
        "group": "Finance",
        "icon": "file",
        "doctype": "Purchase Invoice",
        "columns": (
            {"key": "name", "label": "Nomor", "field": "name", "format": "text"},
            {"key": "date", "label": "Tanggal", "field": "posting_date", "format": "date"},
            {"key": "party", "label": "Supplier", "field": "supplier_name", "format": "text"},
            {"key": "status", "label": "Status", "field": "status", "format": "text"},
            {
                "key": "amount",
                "label": "Total",
                "field": "base_grand_total",
                "format": "currency",
            },
        ),
        "filters": (
            {"key": "date_from", "label": "Dari tanggal", "type": "date"},
            {"key": "date_to", "label": "Sampai tanggal", "type": "date"},
            {"key": "status", "label": "Status", "type": "text"},
            {"key": "party", "label": "Supplier", "type": "text"},
        ),
        "filter_fields": {
            "date_from": {"field": "posting_date", "operator": ">="},
            "date_to": {"field": "posting_date", "operator": "<="},
            "status": {"field": "status", "operator": "="},
            "party": {"field": "supplier", "operator": "like"},
        },
        "search_fields": ("name", "supplier", "supplier_name"),
        "order_field": "posting_date",
        "base_filters": {"docstatus": 1},
        "cards": (
            {
                "key": "count",
                "label": "Invoice pembelian disetujui",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
            {
                "key": "total",
                "label": "Total pembelian",
                "aggregate": "sum",
                "field": "base_grand_total",
                "format": "currency",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
        ),
    },
    {
        "key": "payment_entry",
        "label": "Payment Entry",
        "group": "Finance",
        "icon": "file",
        "doctype": "Payment Entry",
        "columns": (
            {"key": "name", "label": "Nomor", "field": "name", "format": "text"},
            {"key": "date", "label": "Tanggal", "field": "posting_date", "format": "date"},
            {"key": "party", "label": "Pihak", "field": "party_name", "format": "text"},
            {"key": "payment_type", "label": "Jenis", "field": "payment_type", "format": "text"},
            {"key": "status", "label": "Status", "field": "status", "format": "text"},
            {
                "key": "paid_amount",
                "label": "Dibayar",
                "field": "base_paid_amount",
                "format": "currency",
            },
            {
                "key": "received_amount",
                "label": "Diterima",
                "field": "base_received_amount",
                "format": "currency",
            },
        ),
        "filters": (
            {"key": "date_from", "label": "Dari tanggal", "type": "date"},
            {"key": "date_to", "label": "Sampai tanggal", "type": "date"},
            {"key": "status", "label": "Status", "type": "text"},
            {"key": "party", "label": "Pihak", "type": "text"},
        ),
        "filter_fields": {
            "date_from": {"field": "posting_date", "operator": ">="},
            "date_to": {"field": "posting_date", "operator": "<="},
            "status": {"field": "status", "operator": "="},
            "party": {"field": "party", "operator": "like"},
        },
        "search_fields": ("name", "party", "party_name"),
        "order_field": "posting_date",
        "base_filters": {"docstatus": 1, "payment_type": ["in", ["Receive", "Pay"]]},
        "cards": (
            {
                "key": "count",
                "label": "Pembayaran dan penerimaan",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "company",
                "filters": {"docstatus": 1, "payment_type": ["in", ["Receive", "Pay"]]},
            },
            {
                "key": "received",
                "label": "Dana diterima",
                "aggregate": "sum",
                "field": "base_received_amount",
                "format": "currency",
                "scope": "company",
                "filters": {"docstatus": 1, "payment_type": "Receive"},
            },
            {
                "key": "paid",
                "label": "Dana dibayar",
                "aggregate": "sum",
                "field": "base_paid_amount",
                "format": "currency",
                "scope": "company",
                "filters": {"docstatus": 1, "payment_type": "Pay"},
            },
        ),
    },
    {
        "key": "customer",
        "label": "Customer",
        "group": "Sales",
        "icon": "users",
        "doctype": "Customer",
        "columns": (
            {"key": "name", "label": "ID", "field": "name", "format": "text"},
            {"key": "party", "label": "Nama customer", "field": "customer_name", "format": "text"},
            {"key": "status", "label": "Nonaktif", "field": "disabled", "format": "boolean"},
        ),
        "filters": (),
        "filter_fields": {},
        "search_fields": ("name", "customer_name"),
        "order_field": "customer_name",
        "base_filters": {"disabled": 0},
        "cards": (
            {
                "key": "count",
                "label": "Customer aktif di site",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "site",
                "filters": {"disabled": 0},
            },
        ),
    },
    {
        "key": "supplier",
        "label": "Supplier",
        "group": "Finance",
        "icon": "users",
        "doctype": "Supplier",
        "columns": (
            {"key": "name", "label": "ID", "field": "name", "format": "text"},
            {"key": "party", "label": "Nama supplier", "field": "supplier_name", "format": "text"},
            {"key": "status", "label": "Nonaktif", "field": "disabled", "format": "boolean"},
        ),
        "filters": (),
        "filter_fields": {},
        "search_fields": ("name", "supplier_name"),
        "order_field": "supplier_name",
        "base_filters": {"disabled": 0},
        "cards": (
            {
                "key": "count",
                "label": "Supplier aktif di site",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "site",
                "filters": {"disabled": 0},
            },
        ),
    },
    {
        "key": "item",
        "label": "Item",
        "group": "Sales",
        "icon": "folder",
        "doctype": "Item",
        "columns": (
            {"key": "name", "label": "ID", "field": "name", "format": "text"},
            {"key": "party", "label": "Nama item", "field": "item_name", "format": "text"},
            {"key": "group", "label": "Grup item", "field": "item_group", "format": "text"},
            {"key": "status", "label": "Nonaktif", "field": "disabled", "format": "boolean"},
        ),
        "filters": (),
        "filter_fields": {},
        "search_fields": ("name", "item_name", "item_group"),
        "order_field": "item_name",
        "base_filters": {"disabled": 0},
        "cards": (
            {
                "key": "count",
                "label": "Item aktif di site",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "site",
                "filters": {"disabled": 0},
            },
        ),
    },
)

_MODULES_BY_KEY = {module["key"]: module for module in _MODULES}

if any(module["doctype"] not in ERP_CLIENT_DOCTYPES for module in _MODULES):
    raise RuntimeError("Desktop module catalog contains a DocType outside ERP_CLIENT_DOCTYPES")


def get_module_keys() -> list[str]:
    """Return the catalog keys used to validate API and agent requests."""
    return list(_MODULES_BY_KEY)


def get_module_definition(module_key: str) -> dict | None:
    """Return a copy of one server-owned module definition."""
    module = _MODULES_BY_KEY.get(module_key)
    return deepcopy(module) if module else None


def get_module_catalog() -> list[dict]:
    """Return only metadata required by the desktop; omit query internals."""
    return [
        {
            "key": module["key"],
            "label": module["label"],
            "group": module["group"],
            "icon": module["icon"],
            "doctype": module["doctype"],
            "columns": [
                {key: column[key] for key in ("key", "label", "field", "format")}
                for column in module["columns"]
            ],
            "filters": deepcopy(module["filters"]),
            "cards": [
                {key: card[key] for key in ("key", "label", "format", "scope")}
                for card in module["cards"]
            ],
        }
        for module in _MODULES
    ]
