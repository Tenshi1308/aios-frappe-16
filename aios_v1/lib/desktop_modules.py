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
                "label": "Invoice terbit",
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
                "label": "Order terbit",
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
        "key": "quotation",
        "label": "Quotation",
        "group": "Sales",
        "icon": "file",
        "doctype": "Quotation",
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
            "party": {"field": "customer_name", "operator": "like"},
        },
        "search_fields": ("name", "party_name", "customer_name"),
        "order_field": "transaction_date",
        "base_filters": {"docstatus": 1},
        "cards": (
            {
                "key": "count",
                "label": "Quotation terbit",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
            {
                "key": "total",
                "label": "Total quotation",
                "aggregate": "sum",
                "field": "base_grand_total",
                "format": "currency",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
        ),
    },
    {
        "key": "delivery_note",
        "label": "Delivery Note",
        "group": "Sales",
        "icon": "file",
        "doctype": "Delivery Note",
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
                "label": "Surat jalan terbit",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
            {
                "key": "total",
                "label": "Total surat jalan",
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
                "label": "Invoice pembelian terbit",
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
    {
        "key": "item_price",
        "label": "Item Price",
        "group": "Sales",
        "icon": "folder",
        "doctype": "Item Price",
        "columns": (
            {"key": "name", "label": "ID", "field": "name", "format": "text"},
            {"key": "party", "label": "Nama item", "field": "item_name", "format": "text"},
            {"key": "price_list", "label": "Price list", "field": "price_list", "format": "text"},
            {"key": "amount", "label": "Harga", "field": "price_list_rate", "format": "currency"},
            {"key": "valid_from", "label": "Berlaku dari", "field": "valid_from", "format": "date"},
        ),
        "filters": (),
        "filter_fields": {},
        "search_fields": ("name", "item_code", "item_name", "price_list"),
        "order_field": "item_name",
        "base_filters": {"selling": 1},
        "cards": (
            {
                "key": "count",
                "label": "Harga item di site",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "site",
                "filters": {"selling": 1},
            },
        ),
    },
    {
        "key": "journal_entry",
        "label": "Journal Entry",
        "group": "Accounting",
        "icon": "file",
        "doctype": "Journal Entry",
        "columns": (
            {"key": "name", "label": "Nomor", "field": "name", "format": "text"},
            {"key": "date", "label": "Tanggal", "field": "posting_date", "format": "date"},
            {"key": "party", "label": "Pihak", "field": "pay_to_recd_from", "format": "text"},
            {"key": "voucher_type", "label": "Jenis", "field": "voucher_type", "format": "text"},
            {"key": "amount", "label": "Total debit", "field": "total_debit", "format": "currency"},
        ),
        "filters": (
            {"key": "date_from", "label": "Dari tanggal", "type": "date"},
            {"key": "date_to", "label": "Sampai tanggal", "type": "date"},
            {"key": "voucher_type", "label": "Jenis", "type": "text"},
            {"key": "party", "label": "Pihak", "type": "text"},
        ),
        "filter_fields": {
            "date_from": {"field": "posting_date", "operator": ">="},
            "date_to": {"field": "posting_date", "operator": "<="},
            "voucher_type": {"field": "voucher_type", "operator": "="},
            "party": {"field": "pay_to_recd_from", "operator": "like"},
        },
        "search_fields": ("name", "title", "voucher_type", "cheque_no", "pay_to_recd_from"),
        "order_field": "posting_date",
        "base_filters": {"docstatus": 1},
        "cards": (
            {
                "key": "count",
                "label": "Jurnal terbit",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
            {
                "key": "total",
                "label": "Total debit jurnal",
                "aggregate": "sum",
                "field": "total_debit",
                "format": "currency",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
        ),
    },
    {
        "key": "gl_entry",
        "label": "GL Entry",
        "group": "Accounting",
        "icon": "file",
        "doctype": "GL Entry",
        "columns": (
            {"key": "name", "label": "Nomor", "field": "name", "format": "text"},
            {"key": "posting_date", "label": "Tanggal", "field": "posting_date", "format": "date"},
            {"key": "account", "label": "Akun", "field": "account", "format": "text"},
            {"key": "party", "label": "Pihak", "field": "party", "format": "text"},
            {"key": "voucher_no", "label": "No. voucher", "field": "voucher_no", "format": "text"},
            {"key": "debit", "label": "Debit", "field": "debit", "format": "currency"},
            {"key": "credit", "label": "Kredit", "field": "credit", "format": "currency"},
        ),
        "filters": (
            {"key": "date_from", "label": "Dari tanggal", "type": "date"},
            {"key": "date_to", "label": "Sampai tanggal", "type": "date"},
            {"key": "account", "label": "Akun", "type": "text"},
            {"key": "party", "label": "Pihak", "type": "text"},
        ),
        "filter_fields": {
            "date_from": {"field": "posting_date", "operator": ">="},
            "date_to": {"field": "posting_date", "operator": "<="},
            "account": {"field": "account", "operator": "like"},
            "party": {"field": "party", "operator": "like"},
        },
        "search_fields": ("name", "account", "party", "voucher_no", "remarks"),
        "order_field": "posting_date",
        # GL Entry dibuat oleh posting dan selalu ber-docstatus 1 — pakai is_cancelled 0 untuk mengecualikan entri batal, jangan pakai docstatus 1.
        "base_filters": {"is_cancelled": 0},
        "cards": (
            {
                "key": "count",
                "label": "Entri GL tercatat",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "company",
                "filters": {"is_cancelled": 0},
            },
            {
                "key": "debit",
                "label": "Total debit",
                "aggregate": "sum",
                "field": "debit",
                "format": "currency",
                "scope": "company",
                "filters": {"is_cancelled": 0},
            },
            {
                "key": "credit",
                "label": "Total kredit",
                "aggregate": "sum",
                "field": "credit",
                "format": "currency",
                "scope": "company",
                "filters": {"is_cancelled": 0},
            },
        ),
    },
    {
        "key": "account",
        "label": "Account",
        "group": "Accounting",
        "icon": "folder",
        "doctype": "Account",
        "columns": (
            {"key": "name", "label": "ID", "field": "name", "format": "text"},
            {"key": "account_name", "label": "Nama akun", "field": "account_name", "format": "text"},
            {"key": "root_type", "label": "Tipe", "field": "root_type", "format": "text"},
            {"key": "account_type", "label": "Jenis akun", "field": "account_type", "format": "text"},
            {"key": "disabled", "label": "Nonaktif", "field": "disabled", "format": "boolean"},
        ),
        "filters": (),
        "filter_fields": {},
        "search_fields": ("name", "account_name", "account_number"),
        "order_field": "account_name",
        "base_filters": {"disabled": 0},
        "cards": (
            {
                "key": "count",
                "label": "Akun aktif",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "site",
                "filters": {"disabled": 0},
            },
        ),
    },
    {
        "key": "company",
        "label": "Company",
        "group": "Accounting",
        "icon": "building",
        "doctype": "Company",
        "columns": (
            {"key": "name", "label": "ID", "field": "name", "format": "text"},
            {"key": "company_name", "label": "Nama company", "field": "company_name", "format": "text"},
            {"key": "abbr", "label": "Singkatan", "field": "abbr", "format": "text"},
            {"key": "default_currency", "label": "Mata uang", "field": "default_currency", "format": "text"},
            {"key": "country", "label": "Negara", "field": "country", "format": "text"},
        ),
        "filters": (),
        "filter_fields": {},
        "search_fields": ("name", "company_name", "abbr"),
        "order_field": "company_name",
        "base_filters": {},
        "cards": (
            {
                "key": "count",
                "label": "Company di site",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "site",
                "filters": {},
            },
        ),
    },
    {
        "key": "purchase_order",
        "label": "Purchase Order",
        "group": "Purchasing",
        "icon": "file",
        "doctype": "Purchase Order",
        "columns": (
            {"key": "name", "label": "Nomor", "field": "name", "format": "text"},
            {"key": "date", "label": "Tanggal", "field": "transaction_date", "format": "date"},
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
            "date_from": {"field": "transaction_date", "operator": ">="},
            "date_to": {"field": "transaction_date", "operator": "<="},
            "status": {"field": "status", "operator": "="},
            "party": {"field": "supplier", "operator": "like"},
        },
        "search_fields": ("name", "supplier", "supplier_name"),
        "order_field": "transaction_date",
        "base_filters": {"docstatus": 1},
        "cards": (
            {
                "key": "count",
                "label": "Order pembelian terbit",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
            {
                "key": "total",
                "label": "Total order pembelian",
                "aggregate": "sum",
                "field": "base_grand_total",
                "format": "currency",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
        ),
    },
    {
        "key": "purchase_receipt",
        "label": "Purchase Receipt",
        "group": "Purchasing",
        "icon": "file",
        "doctype": "Purchase Receipt",
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
                "label": "Tanda terima terbit",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
            {
                "key": "total",
                "label": "Total tanda terima",
                "aggregate": "sum",
                "field": "base_grand_total",
                "format": "currency",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
        ),
    },
    {
        "key": "supplier_quotation",
        "label": "Supplier Quotation",
        "group": "Purchasing",
        "icon": "file",
        "doctype": "Supplier Quotation",
        "columns": (
            {"key": "name", "label": "Nomor", "field": "name", "format": "text"},
            {"key": "date", "label": "Tanggal", "field": "transaction_date", "format": "date"},
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
            "date_from": {"field": "transaction_date", "operator": ">="},
            "date_to": {"field": "transaction_date", "operator": "<="},
            "status": {"field": "status", "operator": "="},
            "party": {"field": "supplier", "operator": "like"},
        },
        "search_fields": ("name", "supplier", "supplier_name"),
        "order_field": "transaction_date",
        "base_filters": {"docstatus": 1},
        "cards": (
            {
                "key": "count",
                "label": "Penawaran supplier terbit",
                "aggregate": "count",
                "field": "name",
                "format": "number",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
            {
                "key": "total",
                "label": "Total penawaran supplier",
                "aggregate": "sum",
                "field": "base_grand_total",
                "format": "currency",
                "scope": "company",
                "filters": {"docstatus": 1},
            },
        ),
    },
)

_MODULES_BY_KEY = {module["key"]: module for module in _MODULES}

if any(module["doctype"] not in ERP_CLIENT_DOCTYPES for module in _MODULES):
    raise RuntimeError("Desktop module catalog contains a DocType outside ERP_CLIENT_DOCTYPES")

# D8 (Batch B): pemetaan eksplisit modul -> cabang, 1:1 dengan domain yang
# memuatnya di `desktop_domains.DOMAIN_BRANCH_MAP`. Katalog modul statis tidak
# menyimpan cabang, jadi peta ini satu-satunya sumber gerbang aktivasi: modul
# hanya tampil di katalog/pencarian dan bisa dibuka bila cabangnya aktif untuk
# site ini. Konsistensi peta dengan domain divalidasi saat import di
# `_validate_domain_catalog` agar tidak ada dua sumber yang berbeda.
MODULE_BRANCH_MAP = {
    "sales_invoice": "sales",
    "sales_order": "sales",
    "quotation": "sales",
    "delivery_note": "sales",
    "customer": "sales",
    "item": "sales",
    "item_price": "sales",
    "purchase_invoice": "finance",
    "payment_entry": "finance",
    "supplier": "finance",
    "journal_entry": "accounting",
    "gl_entry": "accounting",
    "account": "accounting",
    "company": "accounting",
    "purchase_order": "purchasing",
    "purchase_receipt": "purchasing",
    "supplier_quotation": "purchasing",
}

if any(module["key"] not in MODULE_BRANCH_MAP for module in _MODULES):
    raise RuntimeError("Desktop module catalog contains a module without a branch mapping")


def get_module_branch(module_key: str) -> str | None:
    """Return the branch that owns one module, or None for unknown keys."""
    if not isinstance(module_key, str):
        return None
    return MODULE_BRANCH_MAP.get(module_key)


def _active_branch_keys() -> frozenset[str]:
    """Cabang aktif untuk site ini; lazy import agar bebas circular import.

    `desktop_domains` sudah mengimpor modul ini di level modul, jadi impor balik
    ke `branch_activation` (yang tanpa dependensi katalog) dilakukan di sini
    saat pemanggilan, mengikuti pola `desktop_domains._branch_active`.
    """
    from aios_v1.lib.branch_activation import get_active_branches

    return get_active_branches()


def get_module_keys() -> list[str]:
    """Return the catalog keys used to validate API and agent requests (D9: statis)."""
    return list(_MODULES_BY_KEY)


def get_module_definition(module_key: str) -> dict | None:
    """Return a copy of one server-owned module definition (cabang aktif saja).

    Modul yang cabangnya tidak aktif diperlakukan tidak ada (Gap 2), sehingga
    semua konsumen definisi ikut tergerbang tanpa cek terpisah. Key yang tidak
    dikenal dan key yang cabangnya mati sama-sama mengembalikan None; pembeda
    pesannya tersedia lewat `get_module_branch`.
    """
    module = _MODULES_BY_KEY.get(module_key)
    if not module or MODULE_BRANCH_MAP.get(module_key) not in _active_branch_keys():
        return None
    return deepcopy(module)


def get_module_catalog() -> list[dict]:
    """Return metadata for branch-active modules only; omit query internals."""
    active = _active_branch_keys()
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
        if MODULE_BRANCH_MAP.get(module["key"]) in active
    ]
