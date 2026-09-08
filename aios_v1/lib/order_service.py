# Copyright (c) 2026, Tenshi and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_days, getdate, nowdate


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


def get_active_draft_order_summary(session_name: str | int) -> dict | None:
    """
    Mengambil rincian draf Sales Order aktif (docstatus == 0) untuk sesi Telegram tertentu.
    Mengembalikan None jika tidak ada Sales Order atau pesanan sudah difinalkan (docstatus != 0).
    """
    try:
        if not session_name or not frappe.db.exists("AIOS Telegram Session", session_name):
            return None

        so_id = frappe.db.get_value("AIOS Telegram Session", session_name, "sales_order")
        if not so_id or not frappe.db.exists("Sales Order", so_id):
            return None

        docstatus = frappe.db.get_value("Sales Order", so_id, "docstatus")
        if docstatus != 0:  # Hanya dokumen yang masih Draft
            return None

        so = frappe.get_doc("Sales Order", so_id)
        items_detail = []
        for itm in so.items:
            items_detail.append({
                "item_code": itm.item_code,
                "item_name": itm.item_name,
                "qty": itm.qty,
                "rate": itm.rate,
                "amount": itm.amount
            })

        return {
            "sales_order": so.name,
            "grand_total": so.grand_total,
            "currency": so.currency or "IDR",
            "items": items_detail
        }
    except Exception as e:
        frappe.log_error(f"Gagal mengambil ringkasan draf pesanan sesi {session_name}: {str(e)}", "Order Service")
        return None


def get_active_draft_prompt(session_name: str | int) -> str:
    """
    Menyusun teks konteks pesanan aktif yang sedang berlangsung untuk diinjeksikan ke prompt LLM.
    Jika tidak ada draf aktif, mengembalikan string kosong.
    """
    summary = get_active_draft_order_summary(session_name)
    if not summary or not summary.get("items"):
        return ""

    lines = [
        "[INFORMASI PESANAN AKTIF PELANGGAN DARI SISTEM]:",
        f"Pelanggan ini sedang memiliki draf pesanan terbuka (Nomor Order: {summary['sales_order']}) dengan rincian:",
    ]
    for itm in summary["items"]:
        formatted_rate = f"Rp {itm['rate']:,.0f}".replace(",", ".")
        formatted_amt = f"Rp {itm['amount']:,.0f}".replace(",", ".")
        qty_str = f"{int(itm['qty'])}" if hasattr(itm['qty'], 'is_integer') and itm['qty'].is_integer() else f"{itm['qty']}"
        lines.append(f"- {qty_str}x {itm['item_name']} ({itm['item_code']}) @ {formatted_rate} = {formatted_amt}")

    formatted_total = f"Rp {summary['grand_total']:,.0f}".replace(",", ".")
    lines.append(f"Total Akumulasi Saat Ini: {formatted_total}")
    lines.append(
        "Pedoman Penggunaan: Gunakan data rincian resmi di atas jika pelanggan menanyakan total harga, rincian pesanan, atau konfirmasi akumulasi. Jangan mengira-ngira sendiri jika data resmi sudah tersedia."
    )

    return "\n".join(lines)


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


def create_or_update_erpnext_sales_order(session_name: str | int, order_items: list) -> dict:
    """
    Membuat draf dokumen Sales Order baru atau memperbarui (mengakumulasikan) item
    pada draf Sales Order yang sedang terbuka (docstatus == 0) untuk sesi terkait.
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
        default_delivery_date = getdate(add_days(nowdate(), 3))
        valid_items = []

        for item in order_items:
            item_code = (item.get("item_code") or item.get("sku") or "").strip()
            qty = float(item.get("qty") or 1)

            if not item_code:
                continue

            if not frappe.db.exists("Item", item_code):
                continue

            # Ambil harga jual resmi dari Item Price (Standard Selling) atau standard_rate
            price_rate = frappe.db.get_value(
                "Item Price",
                {"item_code": item_code, "price_list": "Standard Selling", "selling": 1},
                "price_list_rate"
            )
            if not price_rate:
                price_rate = frappe.db.get_value("Item", item_code, "standard_rate") or 0.0

            valid_items.append({
                "item_code": item_code,
                "qty": qty,
                "rate": float(price_rate)
            })

        if not valid_items:
            return {
                "error": "Tidak ada item valid dalam katalog yang dapat diproses",
                "sales_order": None
            }

        # 5. Cek apakah sesi ini sudah memiliki Sales Order aktif yang masih Draft (docstatus == 0)
        existing_so_id = None
        if frappe.db.exists("AIOS Telegram Session", session_name):
            existing_so_id = frappe.db.get_value("AIOS Telegram Session", session_name, "sales_order")

        is_update = False
        so = None

        if existing_so_id and frappe.db.exists("Sales Order", existing_so_id):
            status = frappe.db.get_value("Sales Order", existing_so_id, "docstatus")
            if status == 0:  # 0 = Draft
                so = frappe.get_doc("Sales Order", existing_so_id)
                is_update = True

        # 6. Update draf yang ada atau buat dokumen baru
        if is_update and so:
            target_delivery_date = so.delivery_date or default_delivery_date
            # Akumulasikan item ke dokumen draf yang sedang terbuka
            for item_data in valid_items:
                matched_row = None
                for row in so.items:
                    if row.item_code == item_data["item_code"]:
                        matched_row = row
                        break

                if matched_row:
                    matched_row.qty += item_data["qty"]
                    if not matched_row.rate and item_data["rate"]:
                        matched_row.rate = item_data["rate"]
                else:
                    so.append("items", {
                        "item_code": item_data["item_code"],
                        "qty": item_data["qty"],
                        "rate": item_data["rate"],
                        "delivery_date": target_delivery_date
                    })

            # Hitung ulang harga dan total
            so.run_method("set_missing_values")
            so.run_method("calculate_taxes_and_totals")
            so.save(ignore_permissions=True)
            frappe.db.commit()

        else:
            # Buat dokumen Sales Order draf baru
            so = frappe.new_doc("Sales Order")
            so.company = company
            so.customer = customer_id
            so.order_type = "Sales"
            so.delivery_date = default_delivery_date

            for item_data in valid_items:
                so.append("items", {
                    "item_code": item_data["item_code"],
                    "qty": item_data["qty"],
                    "rate": item_data["rate"],
                    "delivery_date": default_delivery_date
                })

            # Biarkan controller ERPNext mengisi detail harga resmi, pajak, dan kalkulasi total
            so.run_method("set_missing_values")
            so.run_method("calculate_taxes_and_totals")
            so.insert(ignore_permissions=True)
            frappe.db.commit()

            # Tautkan Sales Order baru ke Sesi Telegram jika field sudah tersedia
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
            "is_update": is_update,
            "customer": so.customer,
            "grand_total": so.grand_total,
            "currency": so.currency or "IDR",
            "delivery_date": str(so.delivery_date),
            "items": items_summary
        }

    except Exception as e:
        frappe.log_error(f"Gagal memproses Sales Order ERPNext: {str(e)}", "Order Service")
        return {
            "success": False,
            "error": str(e),
            "sales_order": None
        }


# Alias untuk backward compatibility
create_erpnext_sales_order = create_or_update_erpnext_sales_order


def finalize_sales_order(session_name: str | int, sales_order_id: str | None = None) -> dict:
    """
    Memfinalkan dokumen draf Sales Order di ERPNext (submit docstatus = 1)
    dan mengunci sesi transaksi agar transaksi berikutnya menerbitkan order baru.
    """
    try:
        so_id = sales_order_id
        if not so_id and frappe.db.exists("AIOS Telegram Session", session_name):
            so_id = frappe.db.get_value("AIOS Telegram Session", session_name, "sales_order")

        if not so_id or not frappe.db.exists("Sales Order", so_id):
            return {"success": False, "error": f"Sales Order {so_id} tidak ditemukan"}

        so = frappe.get_doc("Sales Order", so_id)
        if so.docstatus == 0:
            so.submit()
            frappe.db.commit()

        return {
            "success": True,
            "sales_order": so.name,
            "status": "Submitted",
            "docstatus": so.docstatus
        }
    except Exception as e:
        frappe.log_error(f"Gagal memfinalkan Sales Order {sales_order_id}: {str(e)}", "Order Service")
        return {"success": False, "error": str(e)}


def cancel_sales_order_draft(session_name: str | int, sales_order_id: str | None = None) -> dict:
    """
    Membatalkan / menghapus draf dokumen Sales Order yang dibatalkan oleh customer
    dan melepaskan kaitan draf dari sesi.
    """
    try:
        so_id = sales_order_id
        if not so_id and frappe.db.exists("AIOS Telegram Session", session_name):
            so_id = frappe.db.get_value("AIOS Telegram Session", session_name, "sales_order")

        if so_id:
            # Lepas relasi di AIOS Telegram Session dan Message terlebih dahulu
            # agar tidak melanggar integrity check Link DocType saat delete
            if frappe.db.exists("AIOS Telegram Session", session_name):
                frappe.db.set_value("AIOS Telegram Session", session_name, "sales_order", None, update_modified=False)

            frappe.db.sql("""
                UPDATE `tabAIOS Telegram Message`
                SET sales_order = NULL
                WHERE sales_order = %s
            """, (so_id,))
            frappe.db.commit()

            if frappe.db.exists("Sales Order", so_id):
                so = frappe.get_doc("Sales Order", so_id)
                if so.docstatus == 0:
                    so.delete(ignore_permissions=True)
                elif so.docstatus == 1:
                    so.cancel()
                frappe.db.commit()

        return {"success": True, "cancelled_order": so_id}
    except Exception as e:
        frappe.log_error(f"Gagal membatalkan Sales Order {sales_order_id}: {str(e)}", "Order Service")
        return {"success": False, "error": str(e)}

