"""
Skrip penyiapan data demo ERPNext untuk PoC AIOS.

TUJUAN
------
Menyiapkan data ERPNext yang NYATA (hidup di database, bisa di-query) supaya PoC
AIOS bisa membuktikan "AIOS menganalisis data", bukan "AIOS mengarang angka".

Skrip ini TIDAK mengarang data sendiri. Ia memakai generator resmi ERPNext:
    erpnext.setup.demo.setup_demo_data(company_name)
yang mengeksekusi hook `demo_transaction_doctypes = ["purchase_order", "sales_order"]`
(erpnext/hooks.py:100-103) + `convert_order_to_invoices()` dan membuat dokumen nyata
(Item, Customer, Supplier, Sales Order, Purchase Order, Sales/Purchase Invoice,
Payment Entry, GL Entry, Stock Ledger Entry). Catatan: file `demo_data/journal_entry.json`
di ERPNext adalah dead file yang tidak dipanggil `setup_demo_data`, sehingga
`Journal Entry` memang 0.

CARA JALANKAN
-------------
    cd ~/mybench-v16
    bench --site aios-v16.localhost execute \\
        aios_v1.setup_poc.seed_erpnext_demo.run

Atau bertahap (lihat --help pada masing-masing fungsi):

    # 1. Cek status saja, tidak menulis apa pun
    bench --site aios-v16.localhost execute \\
        aios_v1.setup_poc.seed_erpnext_demo.status

    # 2. Jalankan (Company + Fiscal Year + demo data)
    bench --site aios-v16.localhost execute \\
        aios_v1.setup_poc.seed_erpnext_demo.run

    # 3. Bersihkan (kembalikan ke kondisi sebelum demo)
    bench --site aios-v16.localhost execute \\
        aios_v1.setup_poc.seed_erpnext_demo.clear

PENTING SEBELUM MENJALANKAN
---------------------------
1. BACKUP DULU. Perintah ini menulis & submit dokumen:
       bench --site aios-v16.localhost backup --with-files
2. Skrip ini IDEMPOTEN: kalau `<Company> (Demo)` sudah ada dan berisi transaksi,
   `run()` tidak memanggil ulang `setup_demo_data` (mencegah DuplicateEntryError).
3. `setup_demo_data` membuat Company SALINAN bernama "<Company> (Demo)".
   Jadi Company dasarmu tidak diubah — yang diisi data adalah yang "(Demo)".
4. `setup_demo_data` di ERPNext (demo.py:23-32) menangkap semua Exception dan
   melakukan silent rollback ke savepoint `demo_data` tanpa re-raise. Skrip ini
   memverifikasi `Sales Order > 0` dan `GL Entry > 0` pasca-eksekusi dan melempar
   error keras (beserta cuplikan `Error Log`) bila terjadi silent rollback.
"""

import frappe
from frappe.utils import getdate, now_datetime, nowdate

# =============================================================================
# FALLBACK DEFAULT — hanya dipakai bila argumen fungsi, site_config, dan
# System Settings / default site semuanya kosong.
# Currency & Chart of Accounts TIDAK di-hardcode: diambil dinamis dari doctype
# Country & get_charts_for_country(country) bawaan ERPNext.
# =============================================================================

DEFAULT_BASE_COMPANY = "PT Demo AIOS"
DEFAULT_COUNTRY = "Indonesia"

# Dokumen yang akan dihitung sebelum & sesudah, untuk bukti.
# Catatan: Journal Entry tidak dimasukkan karena erpnext/hooks.py:100-103 hanya
# menjalankan ["purchase_order", "sales_order"] (journal_entry.json = dead file).
VERIFY_DOCTYPES = [
    "Company",
    "Item",
    "Item Group",
    "Customer",
    "Supplier",
    "Sales Order",
    "Purchase Order",
    "Sales Invoice",
    "Purchase Invoice",
    "Payment Entry",
    "GL Entry",
    "Warehouse",
    "Stock Ledger Entry",
]


# =============================================================================
# HELPER
# =============================================================================

def _log(msg: str) -> None:
    """Cetak dengan prefix supaya mudah dibaca di output bench."""
    print(f"[AIOS PoC] {msg}")


def _resolve_company_name(company: str | None = None) -> str:
    """Resolusi nama Company dasar: argumen → frappe.conf → default site → fallback."""
    if company and company.strip():
        return company.strip()
    conf_company = frappe.conf.get("aios_poc_company")
    if conf_company and str(conf_company).strip():
        return str(conf_company).strip()
    default_comp = frappe.defaults.get_global_default("company")
    if default_comp and not str(default_comp).endswith("(Demo)"):
        return str(default_comp).strip()
    return DEFAULT_BASE_COMPANY


def _derive_abbr(company_name: str, abbr: str | None = None) -> str:
    """Bentuk singkatan unik dari inisial Company bila abbr tidak diberikan."""
    if abbr and abbr.strip():
        return abbr.strip().upper()
    words = [w for w in company_name.replace("(", " ").replace(")", " ").split() if w.isalnum()]
    candidate = "".join(w[0].upper() for w in words) or "AIOS"
    base_candidate = candidate
    suffix = 1
    while frappe.db.exists("Company", {"abbr": candidate}):
        suffix += 1
        candidate = f"{base_candidate}{suffix}"
    return candidate


def _resolve_country_and_currency(
    country: str | None = None, currency: str | None = None
) -> tuple[str, str]:
    """Resolusi Country & Currency dinamis dari System Settings dan doctype Country."""
    resolved_country = (
        (country or "").strip()
        or frappe.conf.get("aios_poc_country")
        or frappe.db.get_single_value("System Settings", "country")
        or frappe.defaults.get_global_default("country")
        or DEFAULT_COUNTRY
    )
    if not frappe.db.exists("Country", resolved_country):
        frappe.throw(
            f"Master data Country '{resolved_country}' tidak ditemukan di database. "
            f"Jalankan setup wizard ERPNext terlebih dahulu."
        )

    resolved_currency = (
        (currency or "").strip()
        or frappe.conf.get("aios_poc_currency")
        or frappe.db.get_value("Country", resolved_country, "default_currency")
    )
    if not resolved_currency or not frappe.db.exists("Currency", resolved_currency):
        frappe.throw(
            f"Master data Currency '{resolved_currency}' untuk Country '{resolved_country}' "
            f"tidak ditemukan di database."
        )
    return str(resolved_country), str(resolved_currency)


def _resolve_chart_template(country: str, chart_template: str | None = None) -> str:
    """Ambil template Chart of Accounts resmi ERPNext secara dinamis berdasarkan Country."""
    if chart_template and chart_template.strip():
        return chart_template.strip()
    conf_coa = frappe.conf.get("aios_poc_chart_template")
    if conf_coa and str(conf_coa).strip():
        return str(conf_coa).strip()

    from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import (
        get_charts_for_country,
    )

    charts = get_charts_for_country(country) or []
    if not charts:
        frappe.throw(
            f"Tidak ditemukan template Chart of Accounts di ERPNext untuk Country '{country}'."
        )
    # Prioritaskan template non-Standard Number bila ada lebih dari satu, atau elemen pertama
    return charts[0]


def _count(doctype: str, filters: dict | None = None) -> int:
    """Hitung dokumen; catat ke Error Log Frappe & lempar error bila gagal."""
    try:
        return frappe.db.count(doctype, filters=filters or {})
    except Exception:
        frappe.log_error(
            title=f"AIOS PoC Seed: gagal menghitung {doctype}",
            message=frappe.get_traceback(),
        )
        raise


def _snapshot() -> dict:
    """Ambil jumlah dokumen untuk semua VERIFY_DOCTYPES."""
    return {dt: _count(dt) for dt in VERIFY_DOCTYPES}


def _print_snapshot(title: str, snap: dict) -> None:
    _log(f"--- {title} ---")
    for dt, n in snap.items():
        _log(f"  {dt:<24} {n:>7}")


# =============================================================================
# 1. STATUS (read-only)
# =============================================================================

def status(company: str | None = None) -> dict:
    """
    Laporkan kondisi site sekarang. TIDAK menulis apa pun.

    Jalankan:
        bench --site aios-v16.localhost execute \
            aios_v1.setup_poc.seed_erpnext_demo.status
    """
    base_company = _resolve_company_name(company)
    demo_name = f"{base_company} (Demo)"

    _log("=== STATUS SITE ===")
    _log(f"site      : {frappe.local.site}")
    _log(f"company   : {frappe.defaults.get_default('company') or '(belum diset)'}")
    _log(f"fiscal yr : {_active_fiscal_years() or '(tidak ada yang aktif)'}")
    _log("")

    snap = _snapshot()
    _print_snapshot("Jumlah dokumen saat ini", snap)

    _log("")
    _log(f"Company dasar '{base_company}' ada? {bool(frappe.db.exists('Company', base_company))}")
    _log(f"Company demo  '{demo_name}' ada? {bool(frappe.db.exists('Company', demo_name))}")

    # Cek jebakan warehouse: setup_demo_data butuh >= 4 warehouse non-group
    if frappe.db.exists("Company", demo_name):
        wh = frappe.db.count("Warehouse", {"company": demo_name, "is_group": 0})
        _log(f"Warehouse non-group di company demo: {wh} (butuh >= 4)")
    elif frappe.db.exists("Company", base_company):
        wh = frappe.db.count("Warehouse", {"company": base_company, "is_group": 0})
        _log(f"Warehouse non-group di '{base_company}': {wh} (butuh >= 4)")

    _log("")
    _log("Langkah berikutnya:")
    if frappe.db.exists("Company", demo_name) and frappe.db.count("Sales Order", {"company": demo_name}) > 0:
        _log(f"  → Company demo '{demo_name}' sudah berisi data transaksi; siap untuk branch #8")
    elif not frappe.db.exists("Company", base_company):
        _log("  → jalankan run() untuk membuat Company + Fiscal Year + demo data")
    elif not _active_fiscal_years():
        _log("  → Company ada, jalankan run() untuk membuat Fiscal Year + demo data")
    else:
        _log("  → prasyarat siap; jalankan run() untuk mengisi demo data")

    return snap


# =============================================================================
# 2. PRASYARAT: FISCAL YEAR
# =============================================================================

def _active_fiscal_years() -> list:
    """Ambil daftar Fiscal Year aktif (tanpa silent except)."""
    return frappe.db.get_all(
        "Fiscal Year",
        filters={"disabled": 0},
        pluck="name",
        order_by="year_start_date desc",
    )


def ensure_fiscal_year(fiscal_year_label: str | None = None) -> str:
    """
    Pastikan ada Fiscal Year aktif yang mencakup hari ini.

    `setup_demo_data` melempar FiscalYearError kalau tidak ada
    (lihat erpnext/setup/demo.py:123-130). Karena itu langkah ini WAJIB.
    """
    today = getdate(nowdate())

    for fy in frappe.db.get_all(
        "Fiscal Year",
        filters={"disabled": 0},
        fields=["name", "year_start_date", "year_end_date"],
    ):
        if getdate(fy.year_start_date) <= today <= getdate(fy.year_end_date):
            _log(f"Fiscal Year aktif ditemukan: {fy.name}")
            return fy.name

    year = today.year
    start = getdate(f"{year}-01-01")
    end = getdate(f"{year}-12-31")

    if end < today:
        year += 1
        start = getdate(f"{year}-01-01")
        end = getdate(f"{year}-12-31")

    name = (fiscal_year_label or "").strip() or str(year)
    if frappe.db.exists("Fiscal Year", name):
        _log(f"Fiscal Year '{name}' sudah ada")
        return name

    if frappe.db.exists("Fiscal Year", {"year_start_date": start, "year_end_date": end}):
        existing = frappe.db.get_value(
            "Fiscal Year", {"year_start_date": start, "year_end_date": end}, "name"
        )
        _log(f"Fiscal Year untuk periode itu sudah ada: {existing}")
        return existing

    doc = frappe.new_doc("Fiscal Year")
    doc.year = name
    doc.year_start_date = start
    doc.year_end_date = end
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    _log(f"Fiscal Year dibuat: {doc.name} ({start} → {end})")
    return doc.name


# =============================================================================
# 3. PRASYARAT: COMPANY DASAR
# =============================================================================

def ensure_base_company(
    company: str | None = None,
    abbr: str | None = None,
    country: str | None = None,
    currency: str | None = None,
    chart_template: str | None = None,
) -> str:
    """
    Pastikan Company dasar ada. `setup_demo_data` membuat SALINAN dari Company
    ini (erpnext/setup/demo.py:82-95), jadi Company dasar hanya jadi cetakan.
    """
    company_name = _resolve_company_name(company)
    if frappe.db.exists("Company", company_name):
        _log(f"Company dasar sudah ada: {company_name}")
        return company_name

    resolved_country, resolved_currency = _resolve_country_and_currency(country, currency)
    resolved_coa = _resolve_chart_template(resolved_country, chart_template)
    resolved_abbr = _derive_abbr(company_name, abbr)

    # Catatan: create_default_warehouses() (erpnext/setup/doctype/company/company.py:390)
    # hanya membuat warehouse ke-4 ("Goods In Transit") bila Warehouse Type "Transit" ada.
    if not frappe.db.exists("Warehouse Type", "Transit"):
        frappe.throw(
            "Master data 'Warehouse Type' bernama 'Transit' tidak ditemukan. "
            "Jalankan setup wizard ERPNext terlebih dahulu."
        )

    doc = frappe.new_doc("Company")
    doc.company_name = company_name
    doc.abbr = resolved_abbr
    doc.default_currency = resolved_currency
    doc.country = resolved_country
    doc.valuation_method = "FIFO"
    doc.create_chart_of_accounts_based_on = "Standard Template"
    doc.chart_of_accounts = resolved_coa
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    _log(
        f"Company dasar dibuat: {doc.name} "
        f"(abbr={resolved_abbr}, country={resolved_country}, currency={resolved_currency}, coa={resolved_coa})"
    )

    wh = frappe.db.count("Warehouse", {"company": doc.name, "is_group": 0})
    _log(f"Warehouse non-group dibuat otomatis: {wh}")
    if wh < 4:
        _log("  PERINGATAN: kurang dari 4 warehouse. Demo data mungkin gagal.")
    return doc.name


# =============================================================================
# 4. JALANKAN
# =============================================================================

def run(
    company: str | None = None,
    abbr: str | None = None,
    country: str | None = None,
    currency: str | None = None,
    chart_template: str | None = None,
    fiscal_year: str | None = None,
) -> dict:
    """
    Jalankan seluruh penyiapan: Fiscal Year → Company → demo data → verifikasi.

    Jalankan:
        bench --site aios-v16.localhost execute \
            aios_v1.setup_poc.seed_erpnext_demo.run

    Atau dengan parameter kustom:
        bench --site aios-v16.localhost execute \
            aios_v1.setup_poc.seed_erpnext_demo.run \
            --kwargs '{"company": "PT Contoh", "country": "Indonesia"}'

    BACKUP DULU:
        bench --site aios-v16.localhost backup --with-files
    """
    before = _snapshot()
    _print_snapshot("SEBELUM", before)
    _log("")

    # --- Prasyarat 1: Fiscal Year (kalau tidak ada, demo.throw) ---
    fy = ensure_fiscal_year(fiscal_year)
    _log(f"Fiscal Year: {fy}")
    _log("")

    # --- Prasyarat 2: Company dasar ---
    base_company = ensure_base_company(
        company=company,
        abbr=abbr,
        country=country,
        currency=currency,
        chart_template=chart_template,
    )
    demo_company = f"{base_company} (Demo)"
    _log("")

    # --- Idempotensi Company Demo (mencegah DuplicateEntryError di demo.py:86) ---
    if frappe.db.exists("Company", demo_company):
        existing_so = frappe.db.count("Sales Order", {"company": demo_company})
        existing_gl = frappe.db.count("GL Entry", {"company": demo_company})
        if existing_so > 0 and existing_gl > 0:
            _log(
                f"Company demo '{demo_company}' sudah ada dan berisi transaksi "
                f"(Sales Order={existing_so}, GL Entry={existing_gl}). "
                f"Melewati setup_demo_data() agar idempoten."
            )
            return {
                "before": before,
                "after": before,
                "delta": {dt: 0 for dt in VERIFY_DOCTYPES},
                "company": demo_company,
            }
        frappe.throw(
            f"Company demo '{demo_company}' sudah ada tetapi tidak memiliki transaksi "
            f"lengkap (Sales Order={existing_so}, GL Entry={existing_gl}) — kemungkinan "
            f"sisa eksekusi gagal sebelumnya. Jalankan clear() terlebih dahulu."
        )

    # --- Prasyarat 3: warehouse cukup (jebakan randint(0,3)) ---
    wh_count = frappe.db.count("Warehouse", {"company": base_company, "is_group": 0})
    if wh_count < 4:
        frappe.throw(
            f"Butuh minimal 4 warehouse non-group untuk '{base_company}', hanya ada {wh_count}. "
            f"setup_demo_data memakai warehouses[randint(0,3)] "
            f"(erpnext/setup/demo.py:254) dan akan IndexError."
        )
    _log(f"Warehouse non-group: {wh_count} (cukup, butuh >= 4)")
    _log("")

    # --- Jalankan generator resmi ERPNext ---
    from erpnext.setup.demo import setup_demo_data

    run_started_at = now_datetime()
    _log("Menjalankan erpnext.setup.demo.setup_demo_data(...) — ini membuat dokumen & submit")
    setup_demo_data(base_company)
    _log("Eksekusi setup_demo_data() selesai. Memverifikasi hasil...")
    _log("")

    # --- Deteksi Silent Rollback (erpnext/setup/demo.py:23-32) ---
    # setup_demo_data membungkus seluruh proses dalam try...except Exception:
    # lalu melakukan rollback(save_point="demo_data") + log_error() TANPA re-raise.
    # Ambil semua Error Log yang tercatat sejak run_started_at (tanpa hardcode judul).
    so_after = frappe.db.count("Sales Order", {"company": demo_company})
    gl_after = frappe.db.count("GL Entry", {"company": demo_company})
    if not frappe.db.exists("Company", demo_company) or so_after <= 0 or gl_after <= 0:
        recent_errors = frappe.db.get_all(
            "Error Log",
            filters={"creation": [">=", run_started_at]},
            fields=["name", "method", "error"],
            order_by="creation desc",
            limit_page_length=3,
        )
        err_detail = (
            " | ".join(
                f"[{row.name} ({row.method})]: {(row.error or '')[-500:]}"
                for row in recent_errors
            )
            if recent_errors
            else "(tidak ditemukan entri Error Log baru sejak eksekusi dimulai)"
        )
        frappe.throw(
            f"setup_demo_data('{base_company}') mengalami silent rollback! "
            f"Status pasca-run: exists('{demo_company}')={bool(frappe.db.exists('Company', demo_company))}, "
            f"Sales Order={so_after}, GL Entry={gl_after}. "
            f"Error Log tercatat: {err_detail}"
        )

    # --- Verifikasi ---
    after = _snapshot()
    _print_snapshot("SESUDAH", after)

    _log("")
    _log("--- SELISIH (bukti data nyata bertambah) ---")
    delta = {}
    for dt in VERIFY_DOCTYPES:
        d = after.get(dt, 0) - before.get(dt, 0)
        delta[dt] = d
        if d:
            _log(f"  +{d:<6} {dt}")
    if not any(delta.values()):
        _log("  (tidak ada perubahan — mungkin demo data sudah ada sebelumnya)")

    _log("")
    _log("=== RINGKASAN ===")
    _log(f"Company demo : {demo_company}")
    _log(f"Company aktif: {frappe.defaults.get_default('company')}")

    item = frappe.db.count("Item")
    cust = frappe.db.count("Customer")
    _log(f"Sales Order : {so_after}")
    _log(f"GL Entry    : {gl_after}")
    _log(f"Item        : {item}")
    _log(f"Customer    : {cust}")

    _log("")
    _log("Langkah berikutnya:")
    _log("  1. bench --site aios-v16.localhost clear-cache")
    _log("  2. Buka Desk /app → pastikan Company & transaksi muncul")
    _log("  3. Uji tool ERPNext membaca data ini (branch #8)")
    _log("")
    _log("Untuk membatalkan: execute aios_v1.setup_poc.seed_erpnext_demo.clear")

    return {"before": before, "after": after, "delta": delta, "company": demo_company}


# =============================================================================
# 5. BERSIHKAN
# =============================================================================

def clear() -> None:
    """
    Hapus data demo kembali ke kondisi sebelum demo.

    Jalankan:
        bench --site aios-v16.localhost execute \
            aios_v1.setup_poc.seed_erpnext_demo.clear
    """
    from erpnext.setup.demo import clear_demo_data

    _log("Menghapus demo data...")
    try:
        clear_demo_data()
        _log("clear_demo_data() selesai.")
    except Exception as e:
        frappe.log_error(
            title="AIOS PoC Seed: clear_demo_data gagal",
            message=frappe.get_traceback(),
        )
        _log(f"clear_demo_data() gagal (tercatat di Error Log): {type(e).__name__}: {e}")
        _log("Kalau gagal, hapus Company '(Demo)' manual lewat Desk.")
        raise

    _log("")
    _print_snapshot("Setelah dibersihkan", _snapshot())
    _log("")
    _log("Catatan: Company dasar dan Fiscal Year TIDAK dihapus otomatis oleh clear_demo_data().")
    _log("Hapus manual lewat Desk kalau memang mau bersih total.")

    return None


# =============================================================================
# ENTRY POINT DEFAULT
# =============================================================================

def main(**kwargs) -> dict:
    """Alias `run()` supaya bisa dipanggil sebagai fungsi execute default."""
    return run(**kwargs)
