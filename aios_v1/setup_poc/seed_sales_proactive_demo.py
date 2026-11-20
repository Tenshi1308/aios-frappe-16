"""Separate scenario seed & cleanup for Stage 1 Sales proactive verification."""

from __future__ import annotations

import frappe
from frappe.utils import add_days, getdate, nowdate

from aios_v1.lib.error_utils import log_exception
from aios_v1.lib.sales_proactive import _resolve_company

DEMO_CUSTOMER_NAME = "DEMO - PT Skenario Proaktif Sales"
DEMO_TAG = "DEMO"


def _ensure_demo_customer(company: str) -> str:
    if frappe.db.exists("Customer", DEMO_CUSTOMER_NAME):
        return DEMO_CUSTOMER_NAME
    cust_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "All Customer Groups"
    territory = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "All Territories"
    doc = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": DEMO_CUSTOMER_NAME,
            "customer_type": "Company",
            "customer_group": cust_group,
            "territory": territory,
        }
    ).insert(ignore_permissions=True)
    return str(doc.name)


def _resolve_demo_item_and_warehouse(company: str) -> tuple[str, str]:
    warehouses = frappe.get_all(
        "Warehouse",
        filters={"company": company, "is_group": 0, "disabled": 0},
        pluck="name",
    )
    if warehouses:
        bins = frappe.get_all(
            "Bin",
            filters={"warehouse": ["in", warehouses], "actual_qty": [">=", 5]},
            fields=["item_code", "warehouse"],
            limit=1,
        )
        if bins and frappe.db.get_value("Item", bins[0].item_code, "disabled") == 0:
            return str(bins[0].item_code), str(bins[0].warehouse)

    warehouse = warehouses[0] if warehouses else None
    if not warehouse:
        frappe.throw(f"Tidak ada Warehouse aktif untuk company {company}.")

    non_stock_item = frappe.db.get_value("Item", {"is_stock_item": 0, "disabled": 0}, "name")
    if non_stock_item:
        return str(non_stock_item), str(warehouse)

    item_code = frappe.db.get_value("Item", {"disabled": 0}, "name")
    if not item_code:
        frappe.throw("Tidak ada Item aktif untuk membuat skenario DEMO.")
    return str(item_code), str(warehouse)


def seed_demo_scenarios(company: str | None = None) -> dict:
    """Create relative-dated DEMO documents for all 3 Stage 1 Sales detectors."""
    comp = _resolve_company(company)
    customer = _ensure_demo_customer(comp)
    item_code, warehouse = _resolve_demo_item_and_warehouse(comp)
    item_doc = frappe.get_doc("Item", item_code)
    currency = frappe.get_cached_value("Company", comp, "default_currency") or "IDR"
    price_list = (
        frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
        or "Standard Selling"
    )
    today_dt = getdate(nowdate())
    created = {"quotations": [], "sales_orders": [], "delivery_notes": []}

    # 1. Quotation Open: valid_till besok (H-1) dan lusa (H-2), tanpa Sales Order
    for offset in (1, 2):
        qtn = frappe.get_doc(
            {
                "doctype": "Quotation",
                "quotation_to": "Customer",
                "party_name": customer,
                "customer_name": DEMO_CUSTOMER_NAME,
                "company": comp,
                "transaction_date": str(add_days(today_dt, -5)),
                "valid_till": str(add_days(today_dt, offset)),
                "currency": currency,
                "selling_price_list": price_list,
                "price_list_currency": currency,
                "plc_conversion_rate": 1.0,
                "items": [
                    {
                        "item_code": item_code,
                        "item_name": f"{DEMO_TAG} {item_doc.item_name}",
                        "qty": 2,
                        "rate": float(item_doc.standard_rate or 1500000.0),
                    }
                ],
            }
        )
        qtn.insert(ignore_permissions=True)
        qtn.submit()
        created["quotations"].append(qtn.name)

    # 2a. Sales Order terlambat 3 hari, per_delivered = 0
    so_unshipped = frappe.get_doc(
        {
            "doctype": "Sales Order",
            "customer": customer,
            "customer_name": DEMO_CUSTOMER_NAME,
            "company": comp,
            "transaction_date": str(add_days(today_dt, -10)),
            "delivery_date": str(add_days(today_dt, -3)),
            "currency": currency,
            "selling_price_list": price_list,
            "price_list_currency": currency,
            "plc_conversion_rate": 1.0,
            "items": [
                {
                    "item_code": item_code,
                    "item_name": f"{DEMO_TAG} {item_doc.item_name}",
                    "qty": 3,
                    "rate": float(item_doc.standard_rate or 2000000.0),
                    "warehouse": warehouse,
                }
            ],
        }
    )
    so_unshipped.insert(ignore_permissions=True)
    so_unshipped.submit()
    created["sales_orders"].append(so_unshipped.name)

    # 2b. Sales Order terlambat 3 hari, terkirim sebagian (qty 4, kirim 2 -> per_delivered = 50%)
    so_partial = frappe.get_doc(
        {
            "doctype": "Sales Order",
            "customer": customer,
            "customer_name": DEMO_CUSTOMER_NAME,
            "company": comp,
            "transaction_date": str(add_days(today_dt, -10)),
            "delivery_date": str(add_days(today_dt, -3)),
            "currency": currency,
            "selling_price_list": price_list,
            "price_list_currency": currency,
            "plc_conversion_rate": 1.0,
            "items": [
                {
                    "item_code": item_code,
                    "item_name": f"{DEMO_TAG} {item_doc.item_name}",
                    "qty": 4,
                    "rate": float(item_doc.standard_rate or 2000000.0),
                    "warehouse": warehouse,
                }
            ],
        }
    )
    so_partial.insert(ignore_permissions=True)
    so_partial.submit()
    created["sales_orders"].append(so_partial.name)

    # 3. Delivery Note tanpa Sales Invoice (dari so_partial, 2 unit)
    # Buat berumur 3 hari agar memenuhi ambang >= 3 hari detektor Delivered-but-Unbilled
    from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

    dn = make_delivery_note(so_partial.name)
    dn.set_posting_time = 1
    dn.posting_date = str(add_days(today_dt, -3))
    for d_item in dn.items:
        d_item.qty = 2
        if not d_item.warehouse:
            d_item.warehouse = warehouse
    dn.insert(ignore_permissions=True)
    dn.submit()
    created["delivery_notes"].append(dn.name)

    frappe.db.commit()
    return {"status": "success", "company": comp, "customer": customer, "created": created}


def cleanup_demo_scenarios() -> dict:
    """Cancel and delete all DEMO scenario documents safely."""
    deleted = {"Delivery Note": 0, "Sales Order": 0, "Quotation": 0, "AIOS Proactive Insight Log": 0}

    for dt in ("Delivery Note", "Sales Order", "Quotation"):
        filter_field = "party_name" if dt == "Quotation" else "customer"
        names = frappe.get_all(dt, filters={filter_field: DEMO_CUSTOMER_NAME}, pluck="name")
        for name in names:
            try:
                doc = frappe.get_doc(dt, name)
                if doc.docstatus == 1:
                    doc.flags.ignore_permissions = True
                    doc.cancel()
                frappe.delete_doc(dt, name, ignore_permissions=True, force=True, delete_permanently=True)
                deleted[dt] += 1
            except Exception as exc:
                log_exception("AIOS Sales Proactive Demo Cleanup", exc=exc, context=f"{dt}/{name}")
                raise

    log_names = frappe.get_all(
        "AIOS Proactive Insight Log",
        filters={"reference_name": ["in", [n for dt_list in deleted for n in []]]},
        pluck="name",
    ) if False else []
    # Also clean any insight logs created for DEMO documents
    for row in frappe.get_all("AIOS Proactive Insight Log", fields=["name", "reference_doctype", "reference_name"]):
        if not frappe.db.exists(row.reference_doctype, row.reference_name):
            frappe.delete_doc("AIOS Proactive Insight Log", row.name, ignore_permissions=True, force=True, delete_permanently=True)
            deleted["AIOS Proactive Insight Log"] += 1

    if frappe.db.exists("Customer", DEMO_CUSTOMER_NAME):
        frappe.delete_doc("Customer", DEMO_CUSTOMER_NAME, ignore_permissions=True, force=True, delete_permanently=True)

    frappe.db.commit()
    return {"status": "success", "deleted": deleted}
