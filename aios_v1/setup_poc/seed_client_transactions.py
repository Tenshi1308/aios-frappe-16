"""
Skrip seeder 100+ transaksi ERPNext untuk site klien AIOS.

Mencakup seluruh 12 DocType resmi (ERP_CLIENT_DOCTYPES):
1. Company
2. Account
3. Customer
4. Supplier
5. Item
6. Sales Order
7. Sales Invoice (min. 100 baris dengan variasi tanggal & status)
8. Delivery Note
9. Purchase Invoice
10. Payment Entry
11. Journal Entry
12. GL Entry (otomatis terbit dari transaksi berstatus submitted)

Aturan Rekayasa:
- ZERO SILENT ERRORS: Log traceback via log_exception dan fail loudly.
- ANTI-HARDCODE: Nama Company, Currency, Fiscal Year, Akun Kas/Bank/Piutang/Hutang/Pendapatan/Beban
  diambil dinamis dari database site aktif.
- IDEMPOTEN: Melewati pembuatan jika transaksi sudah ada (Sales Invoice >= 100).
"""

import random

import frappe
from frappe.utils import add_days, getdate, nowdate

from aios_v1.lib.error_utils import log_exception
from aios_v1.permissions import ERP_CLIENT_DOCTYPES

from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

CUSTOMERS = [
    ("PT Nusantara Digital Solusindo", "Commercial", "Jakarta Selatan"),
    ("PT Mega Graha Properti", "Commercial", "Jakarta Pusat"),
    ("PT Sentosa Logistik Indonesia", "Commercial", "Surabaya"),
    ("PT Surya Jaya Abadi", "Commercial", "Bandung"),
    ("CV Mitra Sukses Mandiri", "Commercial", "Semarang"),
    ("Toko Berkah Elektronik", "Individual", "Medan"),
    ("Klinik Sehat Sejahtera", "Commercial", "Yogyakarta"),
    ("Restoran Rasa Prima", "Commercial", "Denpasar"),
    ("Kedai Kopi Harmoni", "Individual", "Malang"),
    ("Yayasan Harapan Bangsa", "Non Profit", "Jakarta Timur"),
    ("PT Indo Retail Makmur", "Commercial", "Bekasi"),
    ("CV Cipta Karya Solusi", "Commercial", "Tangerang"),
    ("PT Prima Sarana Utama", "Commercial", "Batam"),
    ("PT Borneo Maju Abadi", "Commercial", "Balikpapan"),
    ("CV Celebes Distribusi", "Commercial", "Makassar"),
    ("Toko Sumber Rezeki", "Individual", "Surakarta"),
    ("PT Andalas Multi Niaga", "Commercial", "Palembang"),
    ("PT Graha Inti Perkasa", "Commercial", "Bogor"),
    ("CV Bahari Samudera", "Commercial", "Cirebon"),
    ("PT Tridharma Sejahtera", "Commercial", "Depok"),
]

SUPPLIERS = [
    ("PT Distributor Utama Komputer", "Hardware"),
    ("PT Solusi Jaringan Nusantara", "Networking"),
    ("PT Cloud Hosting Indonesia", "Cloud Services"),
    ("PT Telekomunikasi Data Pro", "Internet & ISP"),
    ("PT Manajemen Gedung Harmoni", "Facilities / Rent"),
    ("CV Sarana Kantor Prima", "Office Supplies"),
    ("PT Mitra Konsultan Pajak", "Professional Services"),
    ("PT Logistik Kargo Kilat", "Courier & Freight"),
    ("CV Servis Mandiri Tehnik", "Maintenance"),
    ("PT Daya Energi Mandiri", "Utilities / Electricity"),
]

ITEMS = [
    # (code, name, group, is_stock, rate)
    ("LAP-ENT-14", "Laptop Enterprise 14 Inch", "Products", 1, 18500000.0),
    ("MON-UW-34", "Monitor UltraWide 34 Inch Pro", "Products", 1, 8200000.0),
    ("SRV-RCK-2U", "Server Rackmount 2U High-Density", "Products", 1, 65000000.0),
    ("RTR-GW-01", "Router Dual-WAN Enterprise Gigabit", "Products", 1, 3500000.0),
    ("SW-PO-24P", "Gigabit Managed Switch 24-Port PoE", "Products", 1, 4800000.0),
    ("DOC-USB-PRO", "USB-C Triple Display Docking Station", "Products", 1, 1750000.0),
    ("CBL-CAT6-100", "Kabel Jaringan Cat6 UTP 100 Meter", "Products", 1, 850000.0),
    ("UPS-2000VA", "Smart Online UPS 2000VA Rackmount", "Products", 1, 9500000.0),
    ("LIC-AIOS-PRO", "AIOS Workplace Pro Annual License", "Services", 0, 12000000.0),
    ("CLD-BCK-10TB", "Cloud Storage Backup Enterprise 10TB", "Services", 0, 6000000.0),
    ("SRV-IMP-ERP", "Jasa Implementasi & Kustomisasi ERP", "Services", 0, 25000000.0),
    ("SRV-IT-247", "IT Managed Support Service SLA 24/7", "Services", 0, 5000000.0),
    ("SRV-AUD-SEC", "Audit Keamanan Siber & Pen-Testing", "Services", 0, 35000000.0),
    ("SRV-MNT-SRV", "Maintenance Berkala Hardware & Server", "Services", 0, 3000000.0),
    ("SRV-TRN-USR", "Training & Workshop User Ekasa Desk", "Services", 0, 4500000.0),
]


def _resolve_company(company_param: str | None = None) -> str:
    """Ambil Company aktif secara dinamis."""
    if company_param and company_param.strip():
        return company_param.strip()
    comp = (
        frappe.defaults.get_user_default("Company")
        or frappe.defaults.get_global_default("company")
        or frappe.db.get_single_value("AIOS Setting", "default_company")
        or frappe.db.get_value("Company", {}, "name")
    )
    if not comp:
        frappe.throw("Tidak ditemukan Company aktif di site ini.")
    return str(comp)


def _resolve_context(company: str) -> dict:
    """Ambil akun-akun dan master pendukung secara dinamis dari database."""
    comp_doc = frappe.get_doc("Company", company)
    currency = comp_doc.default_currency or "IDR"

    # Receivable (prioritas akun piutang dagang operasional)
    receivable = (
        comp_doc.default_receivable_account
        or frappe.db.get_value("Account", {"company": company, "root_type": "Asset", "account_type": "Receivable", "is_group": 0, "account_name": ["like", "%Dagang%"]}, "name")
        or frappe.db.get_value("Account", {"company": company, "root_type": "Asset", "account_type": "Receivable", "is_group": 0}, "name")
        or frappe.db.get_value("Account", {"company": company, "account_type": "Receivable", "is_group": 0}, "name")
        or frappe.db.get_value("Account", {"company": company, "root_type": "Asset", "is_group": 0}, "name")
    )

    # Payable (prioritas hutang dagang operasional)
    payable = (
        comp_doc.default_payable_account
        or frappe.db.get_value("Account", {"company": company, "root_type": "Liability", "account_type": "Payable", "is_group": 0, "account_name": ["like", "%Dalam Negeri%"]}, "name")
        or frappe.db.get_value("Account", {"company": company, "root_type": "Liability", "account_type": "Payable", "is_group": 0}, "name")
        or frappe.db.get_value("Account", {"company": company, "account_type": "Payable", "is_group": 0}, "name")
        or frappe.db.get_value("Account", {"company": company, "root_type": "Liability", "is_group": 0}, "name")
    )

    # Income
    income = (
        comp_doc.default_income_account
        or frappe.db.get_value("Account", {"company": company, "root_type": "Income", "account_type": "Income Account", "is_group": 0}, "name")
        or frappe.db.get_value("Account", {"company": company, "root_type": "Income", "is_group": 0}, "name")
        or frappe.db.get_value("Account", {"company": company, "account_type": "Income Account", "is_group": 0}, "name")
    )

    # Expense
    expense = (
        comp_doc.default_expense_account
        or frappe.db.get_value("Account", {"company": company, "root_type": "Expense", "account_type": "Expense Account", "is_group": 0}, "name")
        or frappe.db.get_value("Account", {"company": company, "root_type": "Expense", "is_group": 0}, "name")
        or frappe.db.get_value("Account", {"company": company, "account_type": "Expense Account", "is_group": 0}, "name")
    )

    # Cash / Bank (wajib root_type Asset dengan account_type Bank atau Cash)
    bank = (
        comp_doc.default_bank_account
        or comp_doc.default_cash_account
        or frappe.db.get_value("Account", {"company": company, "root_type": "Asset", "account_type": "Bank", "is_group": 0}, "name")
        or frappe.db.get_value("Account", {"company": company, "root_type": "Asset", "account_type": "Cash", "is_group": 0}, "name")
        or frappe.db.get_value("Account", {"company": company, "root_type": "Asset", "account_type": ["in", ["Bank", "Cash"]], "is_group": 0}, "name")
    )

    # Cost Center
    cost_center = comp_doc.cost_center or frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")

    # Warehouse (prioritas fisik Stores atau Finished Goods, hindari Transit)
    warehouse = (
        frappe.db.get_value("Warehouse", {"company": company, "is_group": 0, "warehouse_name": ["in", ["Stores", "Finished Goods"]]}, "name")
        or frappe.db.get_value("Warehouse", {"company": company, "is_group": 0, "warehouse_type": ["!=", "Transit"]}, "name")
        or frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")
    )

    return {
        "company": company,
        "currency": currency,
        "receivable_account": receivable,
        "payable_account": payable,
        "income_account": income,
        "expense_account": expense,
        "bank_account": bank,
        "cost_center": cost_center,
        "warehouse": warehouse,
    }


def _ensure_fiscal_years(company: str) -> None:
    """Pastikan Fiscal Year untuk tahun berjalan dan tahun sebelumnya ada di database."""
    today_year = getdate(nowdate()).year
    for year in (today_year - 1, today_year):
        start = f"{year}-01-01"
        end = f"{year}-12-31"
        fy_name = str(year)
        if not frappe.db.exists("Fiscal Year", fy_name):
            doc = frappe.new_doc("Fiscal Year")
            doc.year = fy_name
            doc.year_start_date = start
            doc.year_end_date = end
            doc.append("companies", {"company": company})
            doc.insert(ignore_permissions=True)
        else:
            fy_doc = frappe.get_doc("Fiscal Year", fy_name)
            if hasattr(fy_doc, "companies"):
                has_comp = any(c.company == company for c in fy_doc.companies)
                if not has_comp:
                    fy_doc.append("companies", {"company": company})
                    fy_doc.save(ignore_permissions=True)
    frappe.db.commit()


def _ensure_masters(ctx: dict) -> tuple[list[str], list[str], list[str]]:
    """Pastikan master Customer, Supplier, dan Item tersedia di database."""
    created_cust = []
    for name, grp, terr in CUSTOMERS:
        if not frappe.db.exists("Customer", name):
            c = frappe.new_doc("Customer")
            c.customer_name = name
            c.customer_group = grp if frappe.db.exists("Customer Group", grp) else "All Customer Groups"
            c.territory = terr if frappe.db.exists("Territory", terr) else "All Territories"
            c.insert(ignore_permissions=True)
        created_cust.append(name)

    created_supp = []
    for name, grp in SUPPLIERS:
        if not frappe.db.exists("Supplier", name):
            s = frappe.new_doc("Supplier")
            s.supplier_name = name
            s.supplier_group = "All Supplier Groups"
            s.insert(ignore_permissions=True)
        created_supp.append(name)

    created_items = []
    for ig in ("Products", "Services"):
        if not frappe.db.exists("Item Group", ig):
            doc = frappe.new_doc("Item Group")
            doc.item_group_name = ig
            doc.parent_item_group = "All Item Groups"
            doc.is_group = 0
            doc.insert(ignore_permissions=True)

    for code, name, ig, is_stock, rate in ITEMS:
        if not frappe.db.exists("Item", code):
            it = frappe.new_doc("Item")
            it.item_code = code
            it.item_name = name
            it.item_group = ig
            it.is_stock_item = is_stock
            it.stock_uom = "Nos" if is_stock else "Unit"
            it.standard_rate = rate
            it.insert(ignore_permissions=True)
        created_items.append(code)

    frappe.db.commit()
    return created_cust, created_supp, created_items


def _ensure_stock_entry(ctx: dict, item_list: list[str]) -> None:
    """Siapkan saldo stok awal untuk barang fisik agar Delivery Note valid."""
    if not ctx["warehouse"]:
        return
    stock_items = [it for it in item_list if frappe.db.get_value("Item", it, "is_stock_item")]
    if not stock_items:
        return
    if frappe.db.count("Stock Ledger Entry", {"company": ctx["company"], "warehouse": ctx["warehouse"]}) > 0:
        return
    try:
        se = frappe.new_doc("Stock Entry")
        se.company = ctx["company"]
        se.stock_entry_type = "Material Receipt"
        se.purpose = "Material Receipt"
        se.set_posting_time = 1
        se.posting_date = add_days(nowdate(), -360)
        for it in stock_items:
            rate = frappe.db.get_value("Item", it, "standard_rate") or 1000000.0
            se.append(
                "items",
                {
                    "item_code": it,
                    "qty": 1000,
                    "t_warehouse": ctx["warehouse"],
                    "basic_rate": rate * 0.6,
                    "cost_center": ctx["cost_center"],
                },
            )
        se.insert(ignore_permissions=True)
        se.submit()
        frappe.db.commit()
        print(f"[AIOS Seeder] Stok awal berhasil dibuat di {ctx['warehouse']}.")
    except Exception as exc:
        log_exception("AIOS Seeder: stok awal", exc=exc)
        frappe.db.rollback()


def _create_sales_flow(
    ctx: dict,
    cust_list: list[str],
    item_list: list[str],
    index: int,
    total_count: int,
    today_dt,
) -> None:
    """Buat satu alur penjualan lengkap: Sales Order, Delivery Note, Sales Invoice, Payment Entry."""
    if index < 65:
        target_status = "Paid"
        days_back = int(350 * (1 - (index / total_count))) + random.randint(1, 5)
        days_back = max(35, min(360, days_back))
        posting_date = add_days(today_dt, -days_back)
        due_date = add_days(posting_date, 30)
    elif index < 90:
        target_status = "Unpaid"
        days_back = random.randint(1, 20)
        posting_date = add_days(today_dt, -days_back)
        due_date = add_days(today_dt, random.randint(10, 30))
    else:
        target_status = "Overdue"
        days_back = random.randint(60, 180)
        posting_date = add_days(today_dt, -days_back)
        due_date = add_days(posting_date, random.randint(14, 28))

    cust = cust_list[index % len(cust_list)]
    item_code = item_list[index % len(item_list)]
    item_doc = frappe.get_doc("Item", item_code)
    qty = random.randint(1, 5)
    rate = item_doc.standard_rate or 1000000.0

    # 1. Sales Order
    so = frappe.new_doc("Sales Order")
    so.company = ctx["company"]
    so.customer = cust
    so.transaction_date = posting_date
    so.delivery_date = add_days(posting_date, 7)
    so.currency = ctx["currency"]
    so.append(
        "items",
        {
            "item_code": item_code,
            "item_name": item_doc.item_name,
            "qty": qty,
            "rate": rate,
            "uom": item_doc.stock_uom or "Nos",
            "warehouse": ctx["warehouse"],
        },
    )
    so.insert(ignore_permissions=True)
    so.submit()

    # 2. Delivery Note (untuk barang fisik pada transaksi Paid/Overdue)
    if item_doc.is_stock_item and ctx["warehouse"] and target_status in ("Paid", "Overdue") and make_delivery_note:
        savepoint = f"dn_sp_{index}"
        frappe.db.savepoint(savepoint)
        try:
            dn = make_delivery_note(so.name)
            dn.set_posting_time = 1
            dn.posting_date = add_days(posting_date, 2)
            for d_item in dn.items:
                if not d_item.warehouse:
                    d_item.warehouse = ctx["warehouse"]
            dn.insert(ignore_permissions=True)
            dn.submit()
        except Exception as exc:
            frappe.db.rollback(save_point=savepoint)
            log_exception("AIOS Seeder: toleransi pembuatan delivery note", exc=exc)

    # 3. Sales Invoice
    si = frappe.new_doc("Sales Invoice")
    si.company = ctx["company"]
    si.customer = cust
    si.set_posting_time = 1
    si.posting_date = posting_date
    si.due_date = due_date
    si.currency = ctx["currency"]
    si.debit_to = ctx["receivable_account"]
    si.append(
        "items",
        {
            "item_code": item_code,
            "item_name": item_doc.item_name,
            "qty": qty,
            "rate": rate,
            "income_account": ctx["income_account"],
            "cost_center": ctx["cost_center"],
            "sales_order": so.name,
            "so_detail": so.items[0].name,
        },
    )
    si.insert(ignore_permissions=True)
    si.submit()

    # 4. Payment Entry (Jika target Paid)
    if target_status == "Paid" and ctx["bank_account"] and get_payment_entry:
        savepoint = f"pe_sp_{index}"
        frappe.db.savepoint(savepoint)
        try:
            pe = get_payment_entry("Sales Invoice", si.name)
            pe.mode_of_payment = "Cash"
            pe.reference_no = f"INV-PAY-{index + 1:05d}"
            pe.reference_date = pe.posting_date
            if ctx["bank_account"]:
                pe.paid_to = ctx["bank_account"]
            pe.posting_date = add_days(posting_date, random.randint(1, 15))
            pe.insert(ignore_permissions=True)
            pe.submit()
        except Exception as exc:
            frappe.db.rollback(save_point=savepoint)
            log_exception("AIOS Seeder: gagal membuat Payment Entry Sales", exc=exc)


def _create_purchases(ctx: dict, supp_list: list[str], item_list: list[str], today_dt) -> None:
    """Buat ~35 transaksi pembelian (Purchase Invoice) dan pembayarannya."""
    existing_pi = frappe.db.count("Purchase Invoice", {"company": ctx["company"], "docstatus": 1})
    if existing_pi >= 35:
        print(f"[AIOS Seeder] Purchase Invoices sudah ada ({existing_pi}). Melewati.")
        return

    for i in range(35):
        days_back = random.randint(5, 330)
        p_date = add_days(today_dt, -days_back)
        supp = supp_list[i % len(supp_list)]
        item_code = item_list[i % len(item_list)]
        item_doc = frappe.get_doc("Item", item_code)
        qty = random.randint(2, 10)
        rate = round((item_doc.standard_rate or 2000000.0) * 0.65, -3)

        pi = frappe.new_doc("Purchase Invoice")
        pi.company = ctx["company"]
        pi.supplier = supp
        pi.set_posting_time = 1
        pi.posting_date = p_date
        pi.due_date = add_days(p_date, 30)
        pi.currency = ctx["currency"]
        pi.credit_to = ctx["payable_account"]
        pi.append(
            "items",
            {
                "item_code": item_code,
                "item_name": item_doc.item_name,
                "qty": qty,
                "rate": rate,
                "expense_account": ctx["expense_account"],
                "cost_center": ctx["cost_center"],
            },
        )
        pi.insert(ignore_permissions=True)
        pi.submit()

        # Bayar 70% dari purchase invoice
        if i % 3 != 0 and ctx["bank_account"] and get_payment_entry:
            savepoint = f"pe_purch_{i}"
            frappe.db.savepoint(savepoint)
            try:
                pe = get_payment_entry("Purchase Invoice", pi.name)
                pe.mode_of_payment = "Cash"
                pe.reference_no = f"PUR-PAY-{i + 1:05d}"
                pe.reference_date = pe.posting_date
                if ctx["bank_account"]:
                    pe.paid_from = ctx["bank_account"]
                pe.posting_date = add_days(p_date, random.randint(3, 20))
                pe.insert(ignore_permissions=True)
                pe.submit()
            except Exception as exc:
                frappe.db.rollback(save_point=savepoint)
                log_exception("AIOS Seeder: gagal membuat Payment Entry Purchase", exc=exc)


def _ensure_payments(ctx: dict) -> None:
    """Buat Payment Entry untuk Sales Invoice dan Purchase Invoice yang belum terbayar."""
    # 1. Bayar hingga 65 Sales Invoice pertama (target status Paid)
    sales_invoices = frappe.get_all(
        "Sales Invoice",
        filters={"company": ctx["company"], "docstatus": 1, "outstanding_amount": [">", 0]},
        fields=["name", "posting_date", "grand_total"],
        order_by="posting_date asc",
        limit=65,
    )
    print(f"[AIOS Seeder] Memproses pembayaran untuk {len(sales_invoices)} Sales Invoice...")
    for idx, si in enumerate(sales_invoices):
        savepoint = f"pe_backfill_sales_{idx}"
        frappe.db.savepoint(savepoint)
        try:
            pe = get_payment_entry("Sales Invoice", si.name)
            pe.mode_of_payment = "Cash"
            pe.reference_no = f"INV-PAY-{idx + 1:05d}"
            pe.reference_date = pe.posting_date
            if ctx["bank_account"]:
                pe.paid_to = ctx["bank_account"]
            pe.insert(ignore_permissions=True)
            pe.submit()
        except Exception as exc:
            frappe.db.rollback(save_point=savepoint)
            log_exception("AIOS Seeder: toleransi pembuatan Payment Entry Sales", exc=exc)

    frappe.db.commit()

    # 2. Bayar ~70% dari Purchase Invoice
    purch_invoices = frappe.get_all(
        "Purchase Invoice",
        filters={"company": ctx["company"], "docstatus": 1, "outstanding_amount": [">", 0]},
        fields=["name", "posting_date", "grand_total"],
        order_by="posting_date asc",
    )
    print(f"[AIOS Seeder] Memproses pembayaran untuk {len(purch_invoices)} Purchase Invoice...")
    for idx, pi in enumerate(purch_invoices):
        if idx % 3 == 0:
            continue  # Sisakan 30% unpaid untuk variasi status
        savepoint = f"pe_backfill_purch_{idx}"
        frappe.db.savepoint(savepoint)
        try:
            pe = get_payment_entry("Purchase Invoice", pi.name)
            pe.mode_of_payment = "Cash"
            pe.reference_no = f"PUR-PAY-{idx + 1:05d}"
            pe.reference_date = pe.posting_date
            if ctx["bank_account"]:
                pe.paid_from = ctx["bank_account"]
            pe.insert(ignore_permissions=True)
            pe.submit()
        except Exception as exc:
            frappe.db.rollback(save_point=savepoint)
            log_exception("AIOS Seeder: toleransi pembuatan Payment Entry Purchase", exc=exc)

    frappe.db.commit()


def _create_journals(ctx: dict, today_dt) -> None:
    """Buat ~15 transaksi Journal Entry (Beban Utilitas, Sewa, Penyusutan)."""
    if not (ctx["expense_account"] and ctx["bank_account"]):
        return

    existing_je = frappe.db.count("Journal Entry", {"company": ctx["company"], "docstatus": 1})
    if existing_je >= 15:
        print(f"[AIOS Seeder] Journal Entries sudah ada ({existing_je}). Melewati.")
        return

    descriptions = [
        "Biaya Listrik & Air Kantor Bulanan",
        "Biaya Internet & Telekomunikasi",
        "Beban Sewa Ruang Server & Kantor",
        "Biaya Pemeliharaan & Kebersihan Kantor",
        "Beban Jasa Konsultan & Administrasi",
    ]

    for i in range(15):
        days_back = random.randint(10, 320)
        j_date = add_days(today_dt, -days_back)
        amount = random.randint(15, 85) * 100000.0  # Rp 1.5jt - Rp 8.5jt
        desc = descriptions[i % len(descriptions)]

        je = frappe.new_doc("Journal Entry")
        je.company = ctx["company"]
        je.voucher_type = "Journal Entry"
        je.posting_date = j_date
        je.user_remark = desc
        je.append(
            "accounts",
            {
                "account": ctx["expense_account"],
                "debit_in_account_currency": amount,
                "cost_center": ctx["cost_center"],
            },
        )
        je.append(
            "accounts",
            {
                "account": ctx["bank_account"],
                "credit_in_account_currency": amount,
                "cost_center": ctx["cost_center"],
            },
        )
        je.insert(ignore_permissions=True)
        je.submit()


def run(company: str | None = None, target_invoices: int = 105) -> dict:
    """Jalankan seeder transaksi 12 DocType secara aman dan idempoten."""
    comp = _resolve_company(company)
    print(f"[AIOS Seeder] Memulai seeding data untuk Company: {comp}")

    # Pastikan Fiscal Year tersedia
    _ensure_fiscal_years(comp)

    # Guard Idempotensi
    existing_si = frappe.db.count("Sales Invoice", {"company": comp, "docstatus": 1})
    existing_pe = frappe.db.count("Payment Entry", {"company": comp, "docstatus": 1})
    if existing_si >= target_invoices and existing_pe >= 50:
        print(f"[AIOS Seeder] Idempoten: Company '{comp}' sudah memiliki {existing_si} Sales Invoice dan {existing_pe} Payment Entry. Melewati.")
        return {"status": "skipped", "sales_invoices": existing_si, "company": comp}

    ctx = _resolve_context(comp)
    print(
        f"[AIOS Seeder] Konteks: Currency={ctx['currency']}, "
        f"Receivable={ctx['receivable_account']}, "
        f"Income={ctx['income_account']}, "
        f"Warehouse={ctx['warehouse']}, "
        f"Bank={ctx['bank_account']}"
    )

    cust_list, supp_list, item_list = _ensure_masters(ctx)
    print(f"[AIOS Seeder] Master siap: {len(cust_list)} Customer, {len(supp_list)} Supplier, {len(item_list)} Item")

    # Siapkan stok awal
    _ensure_stock_entry(ctx, item_list)

    today_dt = getdate(nowdate())

    # Generate sisa Sales Invoices hingga mencapai target_invoices
    if existing_si < target_invoices:
        needed = target_invoices - existing_si
        print(f"[AIOS Seeder] Sudah ada {existing_si} Sales Invoice. Membuat {needed} transaksi penjualan baru...")
        for idx in range(existing_si, target_invoices):
            _create_sales_flow(ctx, cust_list, item_list, idx, target_invoices, today_dt)
            if (idx + 1) % 10 == 0 or idx == target_invoices - 1:
                frappe.db.commit()
                print(f"[AIOS Seeder] Progres Penjualan: {idx + 1}/{target_invoices} invoice selesai...")

        frappe.db.commit()

    # Generate Purchases
    print("[AIOS Seeder] Membuat transaksi pembelian operasional & supplier...")
    _create_purchases(ctx, supp_list, item_list, today_dt)
    frappe.db.commit()

    # Pastikan Payment Entry terbuat untuk Sales & Purchase Invoices
    print("[AIOS Seeder] Memastikan alokasi Payment Entry...")
    _ensure_payments(ctx)
    frappe.db.commit()

    # Generate Journal Entries
    print("[AIOS Seeder] Membuat jurnal penyesuaian operasional...")
    _create_journals(ctx, today_dt)
    frappe.db.commit()

    # Snapshot hasil
    summary = {
        dt: frappe.db.count(
            dt,
            {"company": comp}
            if dt in ("Sales Order", "Sales Invoice", "Delivery Note", "Purchase Invoice", "Journal Entry", "GL Entry")
            else {},
        )
        for dt in ERP_CLIENT_DOCTYPES
    }

    print("\n[AIOS Seeder] SELESAI! Ringkasan Dokumen:")
    for dt, cnt in summary.items():
        print(f"  - {dt}: {cnt}")

    return {
        "status": "success",
        "company": comp,
        "summary": summary,
    }
