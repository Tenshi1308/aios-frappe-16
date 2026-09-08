# Copyright (c) 2026, Tenshi and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_days, nowdate


def get_active_catalog_prompt() -> str:
    """
    Mengambil daftar item aktif dari tabItem bawaan ERPNext
    beserta harga jual resminya dari Item Price (Standard Selling).
    Disusun menjadi teks ringkas dan terstruktur sebagai panduan konteks LLM.
    """
    try:
        items = frappe.get_all(
            "Item",
            filters={"disabled": 0, "is_sales_item": 1},
            fields=["item_code", "item_name", "stock_uom", "standard_rate"],
            order_by="item_code asc"
        )

        if not items:
            return "Saat ini belum ada produk aktif di katalog sistem."

        # Ambil harga jual resmi dari Item Price (Standard Selling)
        prices = frappe.get_all(
            "Item Price",
            filters={"price_list": "Standard Selling", "selling": 1},
            fields=["item_code", "price_list_rate"]
        )
        price_map = {p["item_code"]: p["price_list_rate"] for p in prices}

        lines = ["KATALOG PRODUK TERSEDIA:"]
        for item in items:
            code = item["item_code"]
            name = item["item_name"]
            uom = item.get("stock_uom") or "Pcs"
            rate = price_map.get(code) or item.get("standard_rate") or 0.0

            formatted_rate = f"Rp {rate:,.0f}".replace(",", ".")
            lines.append(f"- {code}: {name} (Harga: {formatted_rate} / {uom})")

        return "\n".join(lines)

    except Exception as e:
        frappe.log_error(f"Gagal mengambil katalog produk: {str(e)}", "Order Service")
        return "Gagal memuat katalog produk dari sistem."


def ensure_erpnext_customer(lead_name: str | None = None, full_name: str = "") -> str:
    """
    Memastikan ketersediaan entitas Customer resmi di ERPNext.
    Jika sudah ada Customer yang tertaut ke Lead atau memiliki nama yang sama, kembalikan namanya.
    Jika belum ada, buatkan dokumen Customer baru bertipe Individual.
    """
    cleaned_name = (full_name or "Telegram Customer").strip()

    # 1. Cek apakah sudah ada Customer yang tertaut ke Lead ini
    if lead_name:
        existing_by_lead = frappe.db.get_value("Customer", {"lead_name": lead_name}, "name")
        if existing_by_lead:
            return existing_by_lead

    # 2. Cek apakah sudah ada Customer dengan nama yang sama
    existing_by_name = frappe.db.get_value("Customer", {"customer_name": cleaned_name}, "name")
    if existing_by_name:
        # Jika ada dan belum tertaut ke lead, tautkan
        if lead_name and not frappe.db.get_value("Customer", existing_by_name, "lead_name"):
            frappe.db.set_value("Customer", existing_by_name, "lead_name", lead_name, update_modified=False)
        return existing_by_name

    # 3. Buat dokumen Customer baru
    customer_group = (
        frappe.db.get_single_value("Selling Settings", "customer_group")
        or "Individual"
        or "All Customer Groups"
    )
    territory = (
        frappe.db.get_single_value("Selling Settings", "territory")
        or "All Territories"
    )

    doc = frappe.new_doc("Customer")
    doc.customer_name = cleaned_name
    doc.customer_type = "Individual"
    doc.customer_group = customer_group
    doc.territory = territory
    if lead_name:
        doc.lead_name = lead_name

    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return doc.name


def create_erpnext_sales_order(session_name: str | int, order_items: list) -> dict:
    """
    Membuat draf dokumen Sales Order resmi di ERPNext (status 'Draft', docstatus 0)
    berdasarkan item pesanan yang dikonfirmasi oleh customer.
    Mengembalikan ringkasan data transaksi.
    """
    if not order_items:
        return {"error": "Daftar item pesanan kosong", "sales_order": None}

    try:
        # 1. Ambil data sesi Telegram
        lead_name = None
        full_name = "Telegram Customer"

        if frappe.db.exists("AIOS Telegram Session", session_name):
            session_doc = frappe.get_doc("AIOS Telegram Session", session_name)
            first_name = (session_doc.first_name or "").strip()
            last_name = (session_doc.last_name or "").strip()
            username = (session_doc.username or "").strip()

            if first_name or last_name:
                full_name = f"{first_name} {last_name}".strip()
            elif username:
                full_name = username

            lead_name = session_doc.lead

        # 2. Pastikan entitas Customer tersedia di ERPNext
        customer_id = ensure_erpnext_customer(lead_name=lead_name, full_name=full_name)

        # 3. Tentukan Company default yang aktif
        company = (
            frappe.defaults.get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
            or "Demo Client ERP (Demo)"
        )

        # 4. Validasi dan siapkan item pesanan
        delivery_date = add_days(nowdate(), 3)
        valid_items = []

        for item in order_items:
            item_code = (item.get("item_code") or item.get("sku") or "").strip()
            qty = float(item.get("qty") or 1)

            if not item_code:
                continue

            if not frappe.db.exists("Item", item_code):
                continue

            valid_items.append({
                "item_code": item_code,
                "qty": qty,
                "delivery_date": delivery_date
            })

        if not valid_items:
            return {
                "error": "Tidak ada item valid dalam katalog yang dapat diproses",
                "sales_order": None
            }

        # 5. Buat dokumen Sales Order baru (status Draft secara default)
        so = frappe.new_doc("Sales Order")
        so.company = company
        so.customer = customer_id
        so.order_type = "Sales"
        so.delivery_date = delivery_date

        for item_data in valid_items:
            so.append("items", item_data)

        # Biarkan controller ERPNext mengisi detail harga resmi, pajak, dan kalkulasi total
        so.run_method("set_missing_values")
        so.run_method("calculate_taxes_and_totals")

        so.insert(ignore_permissions=True)
        frappe.db.commit()

        # 6. Tautkan Sales Order ke Sesi Telegram jika field sudah tersedia
        if frappe.db.exists("AIOS Telegram Session", session_name):
            session_doc = frappe.get_doc("AIOS Telegram Session", session_name)
            if hasattr(session_doc, "sales_order") or "sales_order" in session_doc.as_dict():
                session_doc.sales_order = so.name
                session_doc.save(ignore_permissions=True)
                frappe.db.commit()

        # 7. Susun ringkasan item untuk dikembalikan
        items_summary = [
            {
                "item_code": itm.item_code,
                "item_name": itm.item_name,
                "qty": itm.qty,
                "rate": itm.rate,
                "amount": itm.amount
            }
            for itm in so.items
        ]

        return {
            "success": True,
            "sales_order": so.name,
            "customer": so.customer,
            "grand_total": so.grand_total,
            "currency": so.currency or "IDR",
            "delivery_date": str(so.delivery_date),
            "items": items_summary
        }

    except Exception as e:
        frappe.log_error(f"Gagal membuat Sales Order ERPNext: {str(e)}", "Order Service")
        return {
            "success": False,
            "error": str(e),
            "sales_order": None
        }
