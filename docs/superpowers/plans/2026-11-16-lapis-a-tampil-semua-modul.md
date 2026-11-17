# Lapis A — Tampilkan 6 Modul di Ekasa Desk: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menampilkan 6 DocType yang sudah diizinkan (Delivery Note, Item Price, Journal Entry, GL Entry, Account, Company) sebagai modul read-only di Ekasa Desk, sehingga bidang menjadi 3 (Sales, Finance, Accounting) — jawaban tercepat untuk "kok baru ada sales finance".

**Architecture:** Ikuti preseden Quotation (commit `d8ab5aa`): tiap modul = satu entri di katalog server `desktop_modules.py` + penempatan di bidang `desktop_domains.py` + update tes daftar-eksak + sinkron mock frontend. Tanpa ubah izin, tanpa migrate, tanpa ubah frontend. Satu modul = satu task = satu commit; task berjalan berurutan 1 → 6 (jangan diparalelkan — update daftar-eksak tiap task dibangun di atas task sebelumnya).

**Tech Stack:** Frappe/ERPNext 16.34.2, Python (backend `aios_v1`), Vue (frontend Ekasa Desk, generik — tanpa ubah komponen), `bench run-tests`.

**Spec:** `docs/10-peta-tampil-semua-modul.md` (peta + §9 Keputusan Ten, 16 Nov 2026). Plan ini berargumen dari spec itu; executor membaca keduanya. Lokasi plan ini: `docs/superpowers/plans/2026-11-16-lapis-a-tampil-semua-modul.md`.

## Global Constraints

Setiap task secara implisit mencakup bagian ini.

- Modul baru read-only (list + kartu hitung + filter + search). Aksi tetap hanya Sales + Finance (alur draf SO/Quotation tidak disentuh; tidak ada alur draf baru).
- Agen ikut terbuka otomatis via allowlist global `ERP_CLIENT_DOCTYPES` (tidak bisa dipisah). Cabang agen tetap Sales + Finance: tidak ada perubahan `_PRIORITY_BRANCHES` di `registry.py`, tidak ada handler baru di `branch_handlers.py`.
- Tanpa ubah `aios_v1/permissions.py`; tanpa migrate. Keenam DocType sudah ada di `ERP_CLIENT_DOCTYPES` (`permissions.py:49-64`) dan Custom DocPerm sudah terpasang.
- Tanpa HRIS/Payroll; tanpa pasang aplikasi baru.
- Laporan keuangan sebagai modul Desk BUKAN bagian plan ini (scope terpisah, direncanakan belakangan).
- Branding Finto OS/Fino dikerjakan paralel, BUKAN bagian plan ini (tidak ada perubahan tema/warna/logo di plan ini).
- Frontend generik: tanpa ubah komponen Vue; hanya sinkron mock `frontend/src/api/mock/modules.ts` (dev parity — tidak ada tes bench yang menjaga parity mock, verifikasi dengan membaca file mock).
- Label modul memakai nama DocType Inggris (konsisten dengan 8 modul yang ada). Label kolom/filter UI memakai Bahasa Indonesia ("Nomor", "Tanggal", "Customer", "Status", "Total", "Dari tanggal", "Sampai tanggal", "Pihak"). Label kartu hitung memakai "terbit" HANYA untuk DocType submittable (docstatus 1).
- Satu modul = satu task = satu commit, pesan commit pola `feat(desk): ...` (contoh preseden: `feat(desk): tambah modul Quotation read-only di Ekasa Desk dan akses baca agen`). Tidak push — push keputusan Ten.
- Cara resmi tes: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.<module>`. Verifikasi live dilakukan Gemini lewat browser built-in Antigravity biasa (bukan `/browser` di sesi CLI, bukan oleh Ten) di bench PC (`aios-client1.localhost:5173`); bila kode baru belum ter-load, restart bench dulu. Deploy ke server testing BUKAN bagian plan ini (keputusan Ten sesudah commit, seperti preseden Quotation).
- YAGNI: jangan tambah filter/kolom/kartu di luar yang dipin di tiap task. Jangan perbaiki gap pra-ada: `"Quotation"` hilang dari `CATALOG_DOCTYPES` di `test_frontend_no_hardcode.py`, dan `MOCK_MODULES` di mock hanya berisi `sales_invoice` — keduanya dicatat sebagai follow-up, bukan langkah di plan ini *(catatan: sinkron Quotation di Task 1 adalah keputusan Ten saat eksekusi, bukan bagian plan awal)*.
- Rencana Fase 2 (bidang planned) dibuat SETELAH Fase 1 selesai (aturan Ten 20:24) — bukan bagian plan ini.

## Review Focus

Lima mode kegagalan yang paling mungkin menggigit pengguna, yang tidak ditangkap tes-tes yang sudah ada. Tiap baris sudah ditambah tesnya di task yang bersangkutan.

1. **GL Entry tanpa docstatus — list kosong padahal data ada.** GL Entry tidak pernah disubmit (docstatus selalu 0); `base_filters {"docstatus": 1}` lolos validasi field (docstatus adalah kolom standar) tapi mengembalikan 0 baris, sehingga pengguna membuka modul GL Entry yang kosong. Tes penambat: Task 4 (`test_gl_entry_list_returns_rows_without_docstatus_filter` + assert `base_filters == {"is_cancelled": 0}`).
2. **Item Price tanpa field company — endpoint melempar error.** `_server_filters` (`aios_v1/api/desktop.py:221-230`) melempar `ValidationError` "Cakupan company tidak dapat dipastikan" untuk DocType tanpa field `company` bila `group` modul adalah Sales/Finance dan doctype tidak masuk daftar pengecualian `{Customer, Supplier, Item}`. Tanpa pengecualian, endpoint list/modul/kartu DAN ringkasan modul bidang Sales semuanya gagal untuk Item Price. Tes penambat: Task 2 (`test_item_price_module_is_site_scoped_without_company_field` — endpoint modul mengembalikan baris tanpa throw).
3. **Company tanpa field company — list menampilkan SEMUA company di site.** Company adalah record company itu sendiri, jadi tidak bisa di-scope ke company aktif. Diterima untuk Fase 1 (Company adalah master data; site normalnya punya 1 company); bila pemisahan multi-company menjadi kebutuhan, itu mekanisme baru di luar scope. Tes penambat: Task 6 (`test_company_module_is_site_wide_without_company_field` — endpoint bekerja, kartu scope `site`).
4. **Search memakai nama tampilan pihak tidak menemukan apa-apa.** Bila `search_fields` hanya berisi field ID (mis. `customer`) dan bukan field nama tampilan (`customer_name`), pencarian "Tenshi" tidak menemukan dokumen padahal namanya tampil di list. Tes penambat: Task 1 (Delivery Note — assert search `customer_name` menemukan baris) dan Task 2 (Item Price — assert search `item_name` menemukan baris).
5. **Harga kedaluwarsa tetap tampil tanpa penanda.** Baris Item Price dengan `valid_upto` yang sudah lewat tetap masuk list Fase 1 (tidak ada filter validitas) — pengguna bisa menjual dengan harga yang sudah tidak berlaku. Diterima untuk Fase 1; filter validitas adalah keputusan produk bila Ten memintanya. Tes penambat: Task 2 (pola tes: patch `frappe.get_list`, bukan sisip dokumen ke DB — kembalikan 1 baris Item Price dengan `valid_upto` kemarin, assert list tetap mengembalikannya — perilaku ini didokumentasikan, bukan kejutan).

## Scope Check

Spec (peta) mencakup beberapa subsistem independen: Lapis A (6 modul), Lapis B (9 bidang planned), Lapis C (HRIS/Payroll), laporan keuangan sebagai modul Desk, dan branding. Plan ini hanya mencakup SATU subsistem — Lapis A — dan menghasilkan perangkat lunak yang bekerja dan bisa dites sendiri (14 modul, 3 bidang aktif). Lapis B, Lapis C, laporan, dan branding masing-masing mendapat plan sendiri belakangan.

## File Structure

File yang diubah plan ini (dan tanggung jawabnya):

- `aios_v1/lib/desktop_modules.py` — `_MODULES`: satu entri per modul (key/label/group/icon/doctype + kolom + filter + `filter_fields` + `search_fields` + `order_field` + `base_filters` + kartu hitung). Penjaga `RuntimeError` di akhir file menolak DocType di luar allowlist.
- `aios_v1/lib/desktop_domains.py` — `_DOMAINS`: penempatan key modul per bidang; aktivasi bidang `accounting` (`planned` → `active`) + kartu KPI bidang. Penjaga `_validate_domain_catalog` menolak key modul tak dikenal dan kartu dengan DocType di luar allowlist.
- `aios_v1/api/desktop.py` — HANYA Task 2: tambah `"Item Price"` ke daftar pengecualian di `_server_filters` (:221-230). Tidak ada perubahan API lain.
- `aios_v1/tests/test_desktop_modules.py` — daftar-eksak katalog + tes per modul.
- `aios_v1/tests/test_desktop_domains.py` — hitung planned, bidang aktif, bentuk domain + KPI, `open_domain`.
- `aios_v1/tests/test_frontend_no_hardcode.py` — konstanta `CATALOG_DOCTYPES` (+6 doctype) dan `ACTIVE_DOMAINS` (+`"Accounting"`).
- `frontend/src/api/mock/modules.ts` — `MOCK_DOMAINS` (hitung modul) + daftar modul di `fetchDomain` (dev parity).

File yang TIDAK disentuh: `aios_v1/permissions.py`, `aios_v1/lib/branch_handlers.py`, `aios_v1/plugin_manager/registry.py`, `aios_v1/lib/erpnext_action_drafts.py`, `draft_manager.py`, `aios_v1/tests/test_client_seeder_contract.py`, komponen Vue apa pun.

## Task Right-Sizing

Tiap task adalah satu modul: unit terkecil yang punya siklus tes sendiri, deliverable yang bisa dites sendiri (modul tampil + list + search + kartu), dan bisa ditolak/disetujui sendiri oleh reviewer. Aktivasi bidang Accounting dilipat ke Task 3 (task yang butuh deliverable-nya), bukan task sendiri. Pengecualian scope-site Item Price dilipat ke Task 2. Tiap step adalah satu aksi dengan hasil yang bisa dicek (tulis tes gagal → jalanin → implementasi minimal → jalanin tes → verifikasi live → commit).

---

## Batch 1 — Sales

### Task 1: Delivery Note → Sales

**Files:**
- Modify: `aios_v1/lib/desktop_modules.py` (tambah entri `delivery_note` ke `_MODULES`)
- Modify: `aios_v1/lib/desktop_domains.py` (tambah `"delivery_note"` ke modul bidang `sales`, setelah `"quotation"`)
- Modify: `aios_v1/tests/test_desktop_modules.py` (daftar-eksak + tes list/search Delivery Note)
- Modify: `aios_v1/tests/test_frontend_no_hardcode.py` (tambah `"Delivery Note"` ke `CATALOG_DOCTYPES`)
- Modify: `frontend/src/api/mock/modules.ts` (`MOCK_DOMAINS` sales `module_count` 4 → 6; cabang sales di `fetchDomain` tambah entri `delivery_note`, `row_count` 0)

**Interfaces:**
- Consumes: pola entri Sales Order (`desktop_modules.py` — kolom `customer_name`, `filter_fields` pihak → field `customer` operator `like`, `search_fields ("name", "customer", "customer_name")`, `order_field "posting_date"`, `base_filters {"docstatus": 1}`); validasi field `_definition` (`aios_v1/api/desktop.py:126-153` — semua field yang dideklarasikan harus ada di `meta.get_valid_columns()`).
- Produces: key modul `"delivery_note"` terdaftar di `_MODULES_BY_KEY`; bidang `sales` berisi `("sales_invoice", "sales_order", "quotation", "delivery_note", "customer", "item")`.

**Riset field (terverifikasi dari `delivery_note.json`, ERPNext 16.34.2):** submittable (`is_submittable` 1); `company` [Link] ADA; `customer` [Link] + `customer_name` [Data] ADA (pola sama dengan Sales Order/Quotation); `posting_date` [Date]; `status` [Select: Draft, To Bill, Partially Billed, Completed, Return, Return Issued, Cancelled, Closed]; `base_grand_total` [Currency]; `title_field` = `customer_name`.

**Entri katalog yang dipin (ikuti persis pola Sales Order):**
- `key "delivery_note"`, `label "Delivery Note"`, `group "Sales"`, `icon "file"`, `doctype "Delivery Note"`
- `columns`: `name` "Nomor" text; `posting_date` "Tanggal" date; `customer_name` "Customer" text (kolom pihak); `status` "Status" text; `base_grand_total` "Total" currency
- `filters`: `date_from` "Dari tanggal" date; `date_to` "Sampai tanggal" date; `status` "Status" text; `party` "Customer" text
- `filter_fields`: `date_from {posting_date, >=}`, `date_to {posting_date, <=}`, `status {status, =}`, `party {customer, like}`
- `search_fields`: `("name", "customer", "customer_name")`
- `order_field`: `"posting_date"`
- `base_filters`: `{"docstatus": 1}`
- `cards`: `count` "Surat jalan terbit" (count, `name`, number, scope `company`, `{"docstatus": 1}`); `total` "Total surat jalan" (sum, `base_grand_total`, currency, scope `company`, `{"docstatus": 1}`)

- [ ] **Step 1: Tulis tes yang gagal.** Di `test_desktop_modules.py`, update `test_catalog_only_contains_approved_modules_and_doctypes` (:189): set key menjadi 9 key (8 lama + `"delivery_note"`); grup Sales menjadi `{"sales_invoice", "sales_order", "quotation", "customer", "item", "delivery_note"}`; grup Finance tetap; `assertNotIn("Purchase Order", ...)` tetap. Tambah tes baru `test_delivery_note_list_and_search_return_submitted_company_scoped_rows`, mengikuti pola `test_quotation_list_and_search_return_submitted_company_scoped_rows` (:540-624): pola tes = patch `frappe.get_list` (bukan sisip dokumen ke DB), assert list mengembalikan baris submitted + company aktif, dan assert search dengan `customer_name` menemukan nomornya. Tambah `"delivery_note"` ke tuple di `test_transaction_cards_use_base_currency_and_exclude_internal_transfers` (:527) — kartu sum-nya `base_grand_total` dengan `docstatus` 1, sama seperti 4 modul transaksi lainnya. Tambah `"Delivery Note"` ke `_snapshot_counts` di `test_desktop_domains.py` (daftar doctype yang di-snapshot sebelum/sesudah panggil domain).

```python
# Pola mengikuti test_quotation_list_and_search_return_submitted_company_scoped_rows (:540-624):
# pola tes: patch frappe.get_list (bukan sisip dokumen ke DB);
# assert list mengembalikan nomor yang submitted + company aktif,
# dan assert search dengan customer_name menemukan nomornya.
result = frappe.call(desktop_api.list, module="delivery_note", doctype="Delivery Note", page_size=10)
names = [row["name"] for row in result["rows"]]
self.assertIn("<nomor DN submitted>", names)
self.assertNotIn("<nomor DN draft>", names)
```

- [ ] **Step 2: Jalankan tes untuk memastikan gagal.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules`
Expected: FAIL — `test_catalog_only_contains_approved_modules_and_doctypes` (set key belum berisi `delivery_note`) dan `test_delivery_note_list_and_search_return_submitted_company_scoped_rows` (modul belum ada).

- [ ] **Step 3: Implementasi entri katalog `delivery_note` di `aios_v1/lib/desktop_modules.py`.** Tulis entri dengan nilai yang dipin di atas, mengikuti persis bentuk entri Sales Order (tuple `_MODULES`, urutan field sama).

- [ ] **Step 4: Penempatan bidang.** Di `aios_v1/lib/desktop_domains.py`, tambah `"delivery_note"` ke modul bidang `sales` setelah `"quotation"`. Kartu KPI bidang Sales TIDAK diubah.

- [ ] **Step 5: Sinkron mock + konstanta tes anti-hardcode.** Di `frontend/src/api/mock/modules.ts`: `MOCK_DOMAINS` sales `module_count` 4 → 6; cabang sales di `fetchDomain` tambah `{ key: 'delivery_note', label: 'Delivery Note', icon: 'file', row_count: 0 }` (row_count 0 = dummy dev-only, bukan nilai yang diverifikasi). Di `test_frontend_no_hardcode.py`: tambah `"Delivery Note"` ke `CATALOG_DOCTYPES`.

- [ ] **Step 6: Jalankan tes untuk memastikan lolos.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_domains` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_frontend_no_hardcode`
Expected: PASS — ketiga modul hijau, termasuk `test_catalog_fields_are_valid_for_every_doctype` (semua field entri baru valid di meta Delivery Note) dan `test_module_endpoints_run_read_only_queries_for_catalog` (endpoint modul mengembalikan kartu).

- [ ] **Step 7: Verifikasi live oleh Gemini lewat browser built-in Antigravity biasa (bukan `/browser` di sesi CLI, bukan oleh Ten).** Buka Ekasa Desk di bench PC (`aios-client1.localhost:5173`, restart bench dulu bila kode baru belum ter-load): bootstrap memuat `delivery_note`; bidang Sales menampilkan Delivery Note; buka modul — list menampilkan Delivery Note yang submitted di company aktif; search dengan nama customer menemukan nomornya; nilai kartu "Surat jalan terbit" dan "Total surat jalan" cocok dengan hitung langsung (`frappe.get_list` count/sum `base_grand_total`, `docstatus` 1, company aktif).

- [ ] **Step 8: Commit.**

```bash
git add aios_v1/lib/desktop_modules.py aios_v1/lib/desktop_domains.py aios_v1/tests/test_desktop_modules.py aios_v1/tests/test_desktop_domains.py aios_v1/tests/test_frontend_no_hardcode.py frontend/src/api/mock/modules.ts
git commit -m "feat(desk): tambah modul Delivery Note read-only di Ekasa Desk"
```

---

### Task 2: Item Price → Sales

**Files:**
- Modify: `aios_v1/lib/desktop_modules.py` (tambah entri `item_price` ke `_MODULES`)
- Modify: `aios_v1/api/desktop.py` (tambah `"Item Price"` ke daftar pengecualian di `_server_filters`, :221-230)
- Modify: `aios_v1/lib/desktop_domains.py` (tambah `"item_price"` ke modul bidang `sales`, setelah `"item"`)
- Modify: `aios_v1/tests/test_desktop_modules.py` (daftar-eksak + tes scope-site + tes perilaku harga kedaluwarsa)
- Modify: `aios_v1/tests/test_frontend_no_hardcode.py` (tambah `"Item Price"` ke `CATALOG_DOCTYPES`)
- Modify: `frontend/src/api/mock/modules.ts` (`MOCK_DOMAINS` sales `module_count` 6 → 7; cabang sales di `fetchDomain` tambah entri `item_price`, `row_count` 0)

**Interfaces:**
- Consumes: pola entri master Item/Customer (`desktop_modules.py` — `filters ()`, `filter_fields {}`, kartu count scope `site`, `order_field` nama); `_server_filters` (`aios_v1/api/desktop.py:221-230`); fakta bahwa Item Price sudah bisa dibaca tamu (`aios_v1/permissions.py:300-302` — Guest `read` pada Item + Item Price).
- Produces: key modul `"item_price"` terdaftar di `_MODULES_BY_KEY`; `"Item Price"` masuk daftar pengecualian scope-site di `_server_filters`; bidang `sales` berisi `("sales_invoice", "sales_order", "quotation", "delivery_note", "customer", "item", "item_price")`.

**Riset field (terverifikasi dari `item_price.json`, ERPNext 16.34.2):** TIDAK submittable; field `company` TIDAK ADA (satu-satunya pengecualian di Lapis A selain Company); `item_code` [Link → Item]; `item_name` [Data] (`title_field`); `price_list` [Link → Price List]; `price_list_rate` [Currency]; `currency` [Link]; `customer` [Link] + `supplier` [Link] (harga khusus pihak); `buying` [Check]; `selling` [Check]; `valid_from`/`valid_upto` [Date]; `uom` [Link]; `brand` [Link]; `autoname` hash (field `name` adalah hash, bukan kode yang bisa dibaca).

**Keputusan yang dipin (tidak bisa ditebak implementer):**
- **Pengecualian `_server_filters` adalah SATU-SATUNYA perubahan API di plan ini.** Tanpa pengecualian, endpoint list/modul/kartu DAN ringkasan modul bidang Sales melempar `ValidationError` untuk Item Price, karena grup modul adalah Sales dan doctype tidak ada di `{Customer, Supplier, Item}`. Pengecualian ini aman: Item Price sudah bisa dibaca tamu sekalipun (`GUEST_ALLOWED_DOCTYPES`), jadi menampilkan site-wide untuk karyawan tidak membuka apa pun yang baru; Item Price adalah master site-wide seperti Item. JANGAN tambah `"Item Price"` ke daftar pengecualian `_domain_card_value` (:335-343) — tidak ada kartu bidang yang memakai Item Price (YAGNI).
- **`base_filters` = `{"selling": 1}`.** Hanya harga jual (keputusan Ten 20:44, mengikuti rekomendasi Muse: modul Sales, harga beli adalah info biaya/margin; konsisten dengan Standard Selling). Harga beli tetap bisa dilihat di ERPNext Desk oleh yang berhak.

**Entri katalog yang dipin:**
- `key "item_price"`, `label "Item Price"`, `group "Sales"`, `icon "folder"` (keluarga master Item), `doctype "Item Price"`
- `columns`: `name` "ID" text; `item_name` "Nama item" text (kolom pihak); `price_list` "Price list" text; `price_list_rate` "Harga" currency; `valid_from` "Berlaku dari" date
- `filters`: `()`; `filter_fields`: `{}`
- `search_fields`: `("name", "item_code", "item_name", "price_list")`
- `order_field`: `"item_name"`
- `base_filters`: `{"selling": 1}`
- `cards`: `count` "Harga item di site" (count, `name`, number, scope `site`, `{"selling": 1}`) — SATU kartu saja; tidak ada kartu sum (menjumlahkan `price_list_rate` lintas item/mata uang tidak bermakna)

- [ ] **Step 1: Tulis tes yang gagal.** Di `test_desktop_modules.py`, update `test_catalog_only_contains_approved_modules_and_doctypes`: set key menjadi 10 key (9 + `"item_price"`); grup Sales menjadi 7 key (6 + `"item_price"`). Tambah tes baru `test_item_price_module_is_site_scoped_without_company_field`: assert `frappe.get_meta("Item Price").has_field("company") is False`; assert `frappe.call(desktop_api.module, module="item_price", page=1, page_size=1)` mengembalikan baris tanpa throw (ini menguji pengecualian `_server_filters` end-to-end, termasuk jalur kartu); assert kartu modul = 1 kartu, scope `site`, dan satu kolom berformat currency (`price_list_rate`). Tambah tes perilaku harga kedaluwarsa (Review Focus #5): pola tes = patch `frappe.get_list` (bukan sisip dokumen ke DB) dengan 1 baris Item Price (`item_code` dari Item yang ada di site tes, `price_list` "Standard Selling", `selling` 1, `valid_upto` kemarin), assert list modul tetap mengembalikannya (Fase 1: tanpa filter validitas). Tambah `"Item Price"` ke `_snapshot_counts` di `test_desktop_domains.py`. JANGAN tambah `item_price` ke `test_master_cards_are_site_counts_without_nominal_fields` (:485) — tes itu meng-assert tidak ada kolom currency, sedangkan Item Price punya kolom `price_list_rate` currency.

```python
def test_item_price_module_is_site_scoped_without_company_field(self):
    self.assertFalse(frappe.get_meta("Item Price").has_field("company"))
    # Pola tes = patch frappe.get_list (bukan sisip dokumen ke DB):
    # kembalikan 1 baris Item Price (item_code dari Item, price_list "Standard Selling",
    # selling 1, price_list_rate 100000) — ikuti pola patch get_list di tes Quotation (:540-624).
    result = frappe.call(desktop_api.module, module="item_price", page=1, page_size=1)
    self.assertEqual(result["module"]["key"], "item_price")
    self.assertTrue(result["rows"])
    self.assertEqual(len(result["cards"]), 1)
    self.assertEqual(result["cards"][0]["scope"], "site")
```

- [ ] **Step 2: Jalankan tes untuk memastikan gagal.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules`
Expected: FAIL — daftar-eksak (set key belum berisi `item_price`) dan tes scope-site baru (modul belum ada; tanpa pengecualian, endpoint akan throw).

- [ ] **Step 3: Implementasi entri katalog `item_price` di `aios_v1/lib/desktop_modules.py`.** Tulis entri dengan nilai yang dipin di atas.

- [ ] **Step 4: Pengecualian scope-site + penempatan bidang.** Di `aios_v1/api/desktop.py`, ubah kondisi `elif` di `_server_filters` (:224-226) dari `module["doctype"] not in {"Customer", "Supplier", "Item"}` menjadi `module["doctype"] not in {"Customer", "Supplier", "Item", "Item Price"}`. Di `aios_v1/lib/desktop_domains.py`, tambah `"item_price"` ke modul bidang `sales` setelah `"item"`. Kartu KPI bidang Sales TIDAK diubah.

- [ ] **Step 5: Sinkron mock + konstanta tes anti-hardcode.** Di `frontend/src/api/mock/modules.ts`: `MOCK_DOMAINS` sales `module_count` 6 → 7; cabang sales di `fetchDomain` tambah `{ key: 'item_price', label: 'Item Price', icon: 'folder', row_count: 0 }`. Di `test_frontend_no_hardcode.py`: tambah `"Item Price"` ke `CATALOG_DOCTYPES`.

- [ ] **Step 6: Jalankan tes untuk memastikan lolos.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_domains` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_frontend_no_hardcode`
Expected: PASS — ketiga modul hijau, termasuk `test_module_endpoints_run_read_only_queries_for_catalog` (endpoint modul `item_price` mengembalikan kartu tanpa throw — bukti pengecualian bekerja).

- [ ] **Step 7: Verifikasi live oleh Gemini lewat browser built-in Antigravity biasa (bukan `/browser` di sesi CLI, bukan oleh Ten).** Buka Ekasa Desk di bench PC (`aios-client1.localhost:5173`, restart bench dulu bila kode baru belum ter-load): bootstrap memuat `item_price`; bidang Sales menampilkan Item Price (membuka bidang Sales tidak error — ini membuktikan ringkasan modul `_domain_module_summaries` lolos pengecualian); list menampilkan harga (termasuk satu harga Standard Selling yang dikenal); search dengan nama item menemukan barisnya; nilai kartu "Harga item di site" cocok dengan hitung langsung (count Item Price, tanpa filter company).

- [ ] **Step 8: Commit.**

```bash
git add aios_v1/lib/desktop_modules.py aios_v1/api/desktop.py aios_v1/lib/desktop_domains.py aios_v1/tests/test_desktop_modules.py aios_v1/tests/test_desktop_domains.py aios_v1/tests/test_frontend_no_hardcode.py frontend/src/api/mock/modules.ts
git commit -m "feat(desk): tambah modul Item Price read-only di Ekasa Desk"
```

---

## Batch 2 — Accounting (aktifkan bidang)

### Task 3: Journal Entry → Accounting (AKTIVASI bidang Accounting dilipat ke task ini)

**Files:**
- Modify: `aios_v1/lib/desktop_modules.py` (tambah entri `journal_entry` ke `_MODULES`)
- Modify: `aios_v1/lib/desktop_domains.py` (bidang `accounting`: status `planned` → `active`, modul `("journal_entry",)`, kartu `journal_debit`)
- Modify: `aios_v1/tests/test_desktop_modules.py` (daftar-eksak + grup Accounting baru)
- Modify: `aios_v1/tests/test_desktop_domains.py` (hitung planned 9 → 8, bidang aktif +`accounting`, hapus `"accounting"` dari daftar bidang invalid, bentuk domain + KPI, `open_domain("accounting")`, `_snapshot_counts`)
- Modify: `aios_v1/tests/test_frontend_no_hardcode.py` (tambah `"Journal Entry"` ke `CATALOG_DOCTYPES`; tambah `"Accounting"` ke `ACTIVE_DOMAINS`)
- Modify: `frontend/src/api/mock/modules.ts` (`MOCK_DOMAINS` tambah entri accounting `module_count` 1; `fetchDomain` tambah cabang accounting)

**Interfaces:**
- Consumes: entri bidang `accounting` yang sudah ada sebagai `planned` (`desktop_domains.py` — key `accounting`, label `Accounting`, icon `wallet`, color_token `domain-accounting`, modul `()`, kartu `()`); aturan `_validate_domain_catalog` (modul harus dikenal, kartu harus memakai DocType di allowlist); kartu bidang Finance `journals` ("Jurnal tercatat", count Journal Entry) — kartu Accounting TIDAK boleh menduplikasi label/hitungan ini.
- Produces: bidang `accounting` berstatus `active` dengan modul `("journal_entry",)` dan 1 kartu KPI; key modul `"journal_entry"` terdaftar di `_MODULES_BY_KEY`; `get_domain_keys()` mengembalikan `["sales", "finance", "accounting"]`; `get_planned_domain_count()` mengembalikan 8.

**Riset field (terverifikasi dari `journal_entry.json`, ERPNext 16.34.2):** submittable (`is_submittable` 1); `company` [Link] ADA; `posting_date` [Date]; `voucher_type` [Select — 18 nilai: Journal Entry, Bank Entry, Cash Entry, Credit/Debit Note, Contra Entry, Write Off Entry, Opening Entry, Depreciation Entry, dst.]; `title` [Data] (`title_field`); `cheque_no` [Data] ("Reference Number"); `pay_to_recd_from` [Data] ("Pay To / Recd From" — SATU-SATUNYA field pihak di header; sering kosong untuk jurnal umum; pihak per baris ada di child table `accounts`, bukan di header); `total_debit`/`total_credit`/`difference` [Currency]; `mode_of_payment` [Link]; `is_opening` [Select No/Yes]; `is_system_generated` [Check]. Field `status` TIDAK ADA; field `customer`/`party` TIDAK ADA; `base_grand_total` TIDAK ADA.

**Entri katalog yang dipin:**
- `key "journal_entry"`, `label "Journal Entry"`, `group "Accounting"`, `icon "file"`, `doctype "Journal Entry"`
- `columns`: `name` "Nomor" text; `posting_date` "Tanggal" date; `pay_to_recd_from` "Pihak" text (kolom pihak — dengan catatan di atas); `voucher_type` "Jenis" text; `total_debit` "Total debit" currency
- `filters`: `date_from` "Dari tanggal" date; `date_to` "Sampai tanggal" date; `voucher_type` "Jenis" text; `party` "Pihak" text. (TIDAK ada filter `status` — Journal Entry tidak punya field status; filter jenis menggantikannya.)
- `filter_fields`: `date_from {posting_date, >=}`, `date_to {posting_date, <=}`, `voucher_type {voucher_type, =}`, `party {pay_to_recd_from, like}`
- `search_fields`: `("name", "title", "voucher_type", "cheque_no", "pay_to_recd_from")`
- `order_field`: `"posting_date"`
- `base_filters`: `{"docstatus": 1}`
- `cards`: `count` "Jurnal terbit" (count, `name`, number, scope `company`, `{"docstatus": 1}`); `total` "Total debit jurnal" (sum, `total_debit`, currency, scope `company`, `{"docstatus": 1}`)

**Kartu KPI bidang Accounting yang dipin (task ini — 1 kartu):**
- `journal_debit` "Total debit jurnal" (sum, Journal Entry, `total_debit`, currency, `{"docstatus": 1}`). Kartu ini sengaja memakai agregat sum (bukan count) supaya tidak menduplikasi kartu Finance `journals` ("Jurnal tercatat", count). Kartu ini sama nilainya dengan kartu modul `total` di atas — itu konsisten dengan preseden (kartu bidang Sales "Invoice bulan ini" sama nilainya dengan kartu modul SI "Total invoice").

- [ ] **Step 1: Tulis tes yang gagal.** Di `test_desktop_modules.py`, update `test_catalog_only_contains_approved_modules_and_doctypes`: set key menjadi 11 key (10 + `"journal_entry"`); tambah grup Accounting `{"journal_entry"}`; grup Sales dan Finance tetap. Di `test_desktop_domains.py`: update `test_catalog_contains_active_only_and_tracks_planned_count` (:158-163) — katalog bidang menjadi `["sales", "finance", "accounting"]`, `get_domain_keys()` menjadi `["sales", "finance", "accounting"]`, `get_planned_domain_count()` menjadi 8, `len(_DOMAINS)` tetap 11. Hapus `"accounting"` dari tuple bidang invalid di `test_domain_rejects_planned_unknown_and_unauthorized_users` (:231-232). Update `test_domain_sales_and_finance_shape_kpi_and_no_mutation` (:254): ubah loop menjadi `for domain_key, expected_cards in (("sales", 4), ("finance", 4), ("accounting", 1))` dan assert `len(result["cards"]) == expected_cards` (bukan lagi `== 4` mentah). Di `test_http_get_domain_endpoint` (:322): tambah assert `domain=accounting` mengembalikan 200 (sambil `domain=purchasing` tetap non-200). Di `test_open_module_and_open_domain_full_path_and_separation` (:333): tambah assert `open_domain("accounting") == {"ok": True, "domain": "accounting"}`. Tambah `"Journal Entry"` ke `_snapshot_counts` di `test_desktop_domains.py` (sudah ada — Journal Entry sudah di daftar snapshot; TIDAK perlu diubah — verifikasi saja). Tambah `"Journal Entry"` ke `CATALOG_DOCTYPES` dan `"Accounting"` ke `ACTIVE_DOMAINS` di `test_frontend_no_hardcode.py`.

```python
def test_accounting_domain_is_active_with_journal_entry(self):
    self.assertEqual(get_domain_keys(), ["sales", "finance", "accounting"])
    self.assertEqual(get_planned_domain_count(), 8)
    definition = get_domain_definition("accounting")
    self.assertEqual(definition["status"], "active")
    self.assertEqual(definition["modules"], ("journal_entry",))
    self.assertEqual(len(definition["cards"]), 1)
```

- [ ] **Step 2: Jalankan tes untuk memastikan gagal.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_domains`
Expected: FAIL — daftar-eksak (set key belum berisi `journal_entry`), hitung planned (masih 9), dan tes bidang Accounting baru (bidang masih `planned`, endpoint domain melempar "Bidang tidak tersedia").

- [ ] **Step 3: Implementasi entri katalog `journal_entry` di `aios_v1/lib/desktop_modules.py`.** Tulis entri dengan nilai yang dipin di atas.

- [ ] **Step 4: Aktivasi bidang Accounting.** Di `aios_v1/lib/desktop_domains.py`, ubah entri `accounting`: status `planned` → `active`, modul `("journal_entry",)`, kartu `journal_debit` seperti dipin di atas. Bidang Sales dan Finance TIDAK diubah (termasuk kartu Finance `journals` yang tetap ada).

- [ ] **Step 5: Sinkron mock + konstanta tes anti-hardcode.** Di `frontend/src/api/mock/modules.ts`: `MOCK_DOMAINS` tambah `{ key: 'accounting', label: 'Accounting', icon: 'wallet', color_token: 'domain-accounting', module_count: 1 }`; ubah logika `isFinance` di `fetchDomain` menjadi percabangan 3 bidang (sales/finance/accounting) — cabang accounting mengembalikan daftar modulnya (`{ key: 'journal_entry', label: 'Journal Entry', icon: 'file', row_count: 0 }`) dan kartu domainnya. Di `test_frontend_no_hardcode.py`: tambah `"Journal Entry"` ke `CATALOG_DOCTYPES` dan `"Accounting"` ke `ACTIVE_DOMAINS`.

- [ ] **Step 6: Jalankan tes untuk memastikan lolos.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_domains` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_frontend_no_hardcode`
Expected: PASS — ketiga modul hijau, termasuk `test_domain_sales_and_finance_shape_kpi_and_no_mutation` yang kini juga memeriksa bidang accounting (1 kartu, nilai cocok dengan hitung langsung).

- [ ] **Step 7: Verifikasi live oleh Gemini lewat browser built-in Antigravity biasa (bukan `/browser` di sesi CLI, bukan oleh Ten).** Buka Ekasa Desk di bench PC (`aios-client1.localhost:5173`, restart bench dulu bila kode baru belum ter-load): bootstrap memuat 3 bidang aktif (sales, finance, accounting) dan `journal_entry`; bidang Accounting bisa dibuka (tidak lagi "Bidang tidak tersedia"); kartu "Total debit jurnal" tampil dengan nilai yang cocok dengan hitung langsung; buka modul Journal Entry — list menampilkan jurnal submitted di company aktif; search dengan `title`/`cheque_no` menemukan nomornya; filter Jenis "Bank Entry" mengembalikan hanya jurnal jenis itu.

- [ ] **Step 8: Commit.**

```bash
git add aios_v1/lib/desktop_modules.py aios_v1/lib/desktop_domains.py aios_v1/tests/test_desktop_modules.py aios_v1/tests/test_desktop_domains.py aios_v1/tests/test_frontend_no_hardcode.py frontend/src/api/mock/modules.ts
git commit -m "feat(desk): aktifkan bidang Accounting + tambah modul Journal Entry read-only"
```

---

### Task 4: GL Entry → Accounting

**Files:**
- Modify: `aios_v1/lib/desktop_modules.py` (tambah entri `gl_entry` ke `_MODULES`)
- Modify: `aios_v1/lib/desktop_domains.py` (bidang `accounting`: modul tambah `"gl_entry"`, kartu tambah 3 kartu GL)
- Modify: `aios_v1/tests/test_desktop_modules.py` (daftar-eksak + tes GL tanpa docstatus)
- Modify: `aios_v1/tests/test_frontend_no_hardcode.py` (tambah `"GL Entry"` ke `CATALOG_DOCTYPES`)
- Modify: `frontend/src/api/mock/modules.ts` (`MOCK_DOMAINS` accounting `module_count` 1 → 2; cabang accounting di `fetchDomain` tambah entri `gl_entry`, `row_count` 0)

**Interfaces:**
- Consumes: bidang `accounting` aktif (Task 3); `_domain_definition` (`aios_v1/api/desktop.py:315-334` — field kartu bidang harus ada di `meta.get_valid_columns()`); `_domain_card_value` (:335-343 — GL Entry punya field `company`, jadi kartu bidang di-scope ke company aktif tanpa pengecualian).
- Produces: key modul `"gl_entry"` terdaftar di `_MODULES_BY_KEY`; bidang `accounting` berisi `("journal_entry", "gl_entry")` dengan 4 kartu KPI (1 JE + 3 GL).

**Riset field (terverifikasi dari `gl_entry.json`, ERPNext 16.34.2):** TIDAK submittable (`is_submittable` kosong — GL Entry dibuat oleh posting, bukan disubmit); `company` [Link] ADA; `posting_date` [Date]; `transaction_date` [Date]; `account` [Link → Account]; `party_type` [Link → DocType] + `party` [Dynamic Link]; `debit`/`credit` [Currency]; `voucher_type` [Link → DocType] + `voucher_no` [Dynamic Link]; `against` [Text]; `remarks` [Text]; `is_opening` [Select]; `is_cancelled` [Check]; `fiscal_year` [Link]; `autoname` `ACC-GLE-.YYYY.-.#####`. Field `status` TIDAK ADA; `docstatus` ADA sebagai kolom standar tapi SELALU 0 untuk GL Entry (tidak pernah disubmit).

**Keputusan yang dipin (tidak bisa ditebak implementer):**
- **`base_filters` = `{"is_cancelled": 0}` — BUKAN `{"docstatus": 1}`.** `docstatus` lolos validasi field tapi selalu 0 untuk GL Entry, sehingga filter `docstatus` 1 mengembalikan 0 baris (Review Focus #1). Tulis komentar satu baris di kode di atas entri: `# GL Entry tidak pernah disubmit (docstatus selalu 0) — jangan ganti ke docstatus 1.`
- **Label kartu TIDAK memakai "terbit"** (GL Entry tidak disubmit): "Entri GL tercatat", "Total debit", "Total kredit".
- **Volume baris:** setiap posting menghasilkan banyak baris GL — list GL Entry adalah list terbesar di Desk. `order_field` `posting_date` + paginasi (cap 100 baris/halaman, pola yang sudah ada) yang berlaku; tidak ada langkah khusus di task ini selain verifikasi live bahwa halaman 2 termuat.

**Entri katalog yang dipin:**
- `key "gl_entry"`, `label "GL Entry"`, `group "Accounting"`, `icon "file"`, `doctype "GL Entry"`
- `columns`: `name` "Nomor" text; `posting_date` "Tanggal" date; `account` "Akun" text; `party` "Pihak" text; `voucher_no` "Voucher" text; `debit` "Debit" currency; `credit` "Kredit" currency
- `filters`: `date_from` "Dari tanggal" date; `date_to` "Sampai tanggal" date; `account` "Akun" text; `party` "Pihak" text
- `filter_fields`: `date_from {posting_date, >=}`, `date_to {posting_date, <=}`, `account {account, like}`, `party {party, like}`
- `search_fields`: `("name", "account", "party", "voucher_no", "remarks")`
- `order_field`: `"posting_date"`
- `base_filters`: `{"is_cancelled": 0}`
- `cards`: `count` "Entri GL tercatat" (count, `name`, number, scope `company`, `{"is_cancelled": 0}`); `debit` "Total debit" (sum, `debit`, currency, scope `company`, `{"is_cancelled": 0}`); `credit` "Total kredit" (sum, `credit`, currency, scope `company`, `{"is_cancelled": 0}`)

**Kartu KPI bidang Accounting yang dipin (task ini — 3 kartu, total bidang menjadi 4):**
- `gl_count` "Entri GL tercatat" (count, GL Entry, `name`, number, `{"is_cancelled": 0}`)
- `gl_debit` "Total debit" (sum, GL Entry, `debit`, currency, `{"is_cancelled": 0}`)
- `gl_credit` "Total kredit" (sum, GL Entry, `credit`, currency, `{"is_cancelled": 0}`)

- [ ] **Step 1: Tulis tes yang gagal.** Di `test_desktop_modules.py`, update `test_catalog_only_contains_approved_modules_and_doctypes`: set key menjadi 12 key (11 + `"gl_entry"`); grup Accounting menjadi `{"journal_entry", "gl_entry"}`. Tambah tes baru `test_gl_entry_list_returns_rows_without_docstatus_filter`: pola tes = patch `frappe.get_list` (bukan sisip dokumen ke DB) untuk mengembalikan baris GL (`is_cancelled` 0), lalu assert endpoint modul `gl_entry` mengembalikan baris-baris GL-nya dan assert `get_module_definition("gl_entry")["base_filters"] == {"is_cancelled": 0}`; assert 3 kartu modul dengan label yang dipin. JANGAN tambah `"gl_entry"` ke tuple di `test_transaction_cards_use_base_currency_and_exclude_internal_transfers` (:527) — kartu sum GL memakai field `debit`/`credit`, bukan `base_grand_total`. Tambah `"GL Entry"` ke `_snapshot_counts` di `test_desktop_domains.py`. Di `test_desktop_domains.py`, update `test_domain_sales_and_finance_shape_kpi_and_no_mutation`: ubah ekspektasi kartu accounting dari 1 menjadi 4.

```python
def test_gl_entry_list_returns_rows_without_docstatus_filter(self):
    self.assertEqual(get_module_definition("gl_entry")["base_filters"], {"is_cancelled": 0})
    result = frappe.call(desktop_api.module, module="gl_entry", page=1, page_size=1)
    self.assertEqual(result["module"]["key"], "gl_entry")
    self.assertTrue(result["rows"])
    self.assertEqual(len(result["cards"]), 3)
```

- [ ] **Step 2: Jalankan tes untuk memastikan gagal.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_domains`
Expected: FAIL — daftar-eksak (set key belum berisi `gl_entry`), tes GL baru (modul belum ada), dan bentuk domain (kartu accounting masih 1, bukan 4).

- [ ] **Step 3: Implementasi entri katalog `gl_entry` di `aios_v1/lib/desktop_modules.py`.** Tulis entri dengan nilai yang dipin di atas, termasuk komentar satu baris soal `docstatus` di atas `base_filters`.

- [ ] **Step 4: Penempatan bidang + kartu KPI.** Di `aios_v1/lib/desktop_domains.py`, tambah `"gl_entry"` ke modul bidang `accounting` (setelah `"journal_entry"`) dan tambah 3 kartu GL seperti dipin di atas.

- [ ] **Step 5: Sinkron mock + konstanta tes anti-hardcode.** Di `frontend/src/api/mock/modules.ts`: `MOCK_DOMAINS` accounting `module_count` 1 → 2; cabang accounting di `fetchDomain` tambah `{ key: 'gl_entry', label: 'GL Entry', icon: 'file', row_count: 0 }`. Di `test_frontend_no_hardcode.py`: tambah `"GL Entry"` ke `CATALOG_DOCTYPES`.

- [ ] **Step 6: Jalankan tes untuk memastikan lolos.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_domains` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_frontend_no_hardcode`
Expected: PASS — ketiga modul hijau, termasuk `test_gl_entry_list_returns_rows_without_docstatus_filter` (list GL mengembalikan baris) dan bentuk domain accounting (4 kartu, nilai cocok dengan hitung langsung).

- [ ] **Step 7: Verifikasi live oleh Gemini lewat browser built-in Antigravity biasa (bukan `/browser` di sesi CLI, bukan oleh Ten).** Buka Ekasa Desk di bench PC (`aios-client1.localhost:5173`, restart bench dulu bila kode baru belum ter-load): bidang Accounting menampilkan 4 kartu KPI (1 JE + 3 GL) dengan nilai yang cocok dengan hitung langsung; buka modul GL Entry — list menampilkan baris GL terbaru dulu (`posting_date` desc); buka halaman 2 — termuat tanpa error (list GL adalah yang terbesar); search dengan `voucher_no` menemukan barisnya; filter Akun mempersempit list ke akun itu.

- [ ] **Step 8: Commit.**

```bash
git add aios_v1/lib/desktop_modules.py aios_v1/lib/desktop_domains.py aios_v1/tests/test_desktop_modules.py aios_v1/tests/test_desktop_domains.py aios_v1/tests/test_frontend_no_hardcode.py frontend/src/api/mock/modules.ts
git commit -m "feat(desk): tambah modul GL Entry read-only di Ekasa Desk"
```

---

### Task 5: Account → Accounting

**Files:**
- Modify: `aios_v1/lib/desktop_modules.py` (tambah entri `account` ke `_MODULES`)
- Modify: `aios_v1/lib/desktop_domains.py` (bidang `accounting`: modul tambah `"account"`)
- Modify: `aios_v1/tests/test_desktop_modules.py` (daftar-eksak + perluas tes kartu master)
- Modify: `aios_v1/tests/test_frontend_no_hardcode.py` (tambah `"Account"` ke `CATALOG_DOCTYPES`)
- Modify: `frontend/src/api/mock/modules.ts` (`MOCK_DOMAINS` accounting `module_count` 2 → 3; cabang accounting di `fetchDomain` tambah entri `account`, `row_count` 0)

**Interfaces:**
- Consumes: bidang `accounting` aktif (Task 3); pola entri master Customer/Supplier/Item (`desktop_modules.py` — `filters ()`, `filter_fields {}`, kartu count scope `site`, `order_field` nama); `_server_filters` (`aios_v1/api/desktop.py:221-230` — Account PUNYA field `company`, jadi list di-scope ke company aktif tanpa pengecualian).
- Produces: key modul `"account"` terdaftar di `_MODULES_BY_KEY`; bidang `accounting` berisi `("journal_entry", "gl_entry", "account")`.

**Riset field (terverifikasi dari `account.json`, ERPNext 16.34.2):** TIDAK submittable; `company` [Link] ADA; `account_name` [Data]; `account_number` [Data]; `is_group` [Check] (akun grup tidak punya saldo — tampil sama seperti akun biasa di list, diterima untuk Fase 1); `root_type` [Select: Asset, Liability, Income, Expense, Equity]; `report_type` [Select: Balance Sheet, Profit and Loss]; `account_type` [Select: Bank, Cash, Receivable, Payable, Tax, Stock, dst.]; `parent_account` [Link → Account]; `account_currency` [Link → Currency]; `disabled` [Check]; `name` adalah path tree akun (mis. `1110 - Kas - EKASA`). Field `status` TIDAK ADA; field tanggal TIDAK ADA.

**Keputusan yang dipin (tidak bisa ditebak implementer):**
- **Label kartu "Akun aktif" — TANPA "di site".** Kartu memakai scope `site` (pola master), TETAPI `_server_filters` tetap menambahkan filter company karena Account punya field `company` — jadi nilai kartu sebenarnya ter-scope ke company aktif, bukan site-wide. Scope `site` di sini hanya memengaruhi penggabungan `client_filters` di `_card_value`, bukan filternya. Label tanpa "di site" supaya tidak menyesatkan.

**Entri katalog yang dipin:**
- `key "account"`, `label "Account"`, `group "Accounting"`, `icon "folder"` (keluarga master), `doctype "Account"`
- `columns`: `name` "ID" text; `account_name` "Nama akun" text (kolom pihak); `root_type` "Tipe" text; `account_type` "Jenis akun" text; `disabled` "Nonaktif" boolean
- `filters`: `()`; `filter_fields`: `{}`
- `search_fields`: `("name", "account_name", "account_number")`
- `order_field`: `"account_name"`
- `base_filters`: `{"disabled": 0}`
- `cards`: `count` "Akun aktif" (count, `name`, number, scope `site`, `{"disabled": 0}`) — SATU kartu saja

- [ ] **Step 1: Tulis tes yang gagal.** Di `test_desktop_modules.py`, update `test_catalog_only_contains_approved_modules_and_doctypes`: set key menjadi 13 key (12 + `"account"`); grup Accounting menjadi `{"journal_entry", "gl_entry", "account"}`. Perluas `test_master_cards_are_site_counts_without_nominal_fields` (:485) dari satu modul (`customer`) menjadi loop atas `(("customer", "Customer"), ("account", "Account"))` dengan `subTest` — assert yang sama berlaku untuk keduanya (1 kartu, scope `site`, tanpa currency, tanpa kolom berformat currency, doctype cocok). Tambah `"Account"` ke `_snapshot_counts` di `test_desktop_domains.py`.

```python
def test_master_cards_are_site_counts_without_nominal_fields(self):
    for module_key, doctype in (("customer", "Customer"), ("account", "Account")):
        with self.subTest(module=module_key):
            # ... assert yang sama seperti sebelumnya, memakai module_key/doctype ...
```

- [ ] **Step 2: Jalankan tes untuk memastikan gagal.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules`
Expected: FAIL — daftar-eksak (set key belum berisi `account`) dan tes kartu master (loop belum mencakup `account`).

- [ ] **Step 3: Implementasi entri katalog `account` di `aios_v1/lib/desktop_modules.py`.** Tulis entri dengan nilai yang dipin di atas.

- [ ] **Step 4: Penempatan bidang.** Di `aios_v1/lib/desktop_domains.py`, tambah `"account"` ke modul bidang `accounting` (setelah `"gl_entry"`). Kartu KPI bidang Accounting TIDAK diubah (tetap 4 kartu dari Task 3 + Task 4).

- [ ] **Step 5: Sinkron mock + konstanta tes anti-hardcode.** Di `frontend/src/api/mock/modules.ts`: `MOCK_DOMAINS` accounting `module_count` 2 → 3; cabang accounting di `fetchDomain` tambah `{ key: 'account', label: 'Account', icon: 'folder', row_count: 0 }`. Di `test_frontend_no_hardcode.py`: tambah `"Account"` ke `CATALOG_DOCTYPES`.

- [ ] **Step 6: Jalankan tes untuk memastikan lolos.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_domains` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_frontend_no_hardcode`
Expected: PASS — ketiga modul hijau, termasuk `test_catalog_fields_are_valid_for_every_doctype` (semua field entri Account valid di meta) dan `test_module_endpoints_run_read_only_queries_for_catalog` (endpoint modul `account` mengembalikan kartu).

- [ ] **Step 7: Verifikasi live oleh Gemini lewat browser built-in Antigravity biasa (bukan `/browser` di sesi CLI, bukan oleh Ten).** Buka Ekasa Desk di bench PC (`aios-client1.localhost:5173`, restart bench dulu bila kode baru belum ter-load): bidang Accounting menampilkan Account; buka modul — list menampilkan chart of accounts company aktif (bukan semua company); search dengan nama akun menemukan barisnya; nilai kartu "Akun aktif" cocok dengan hitung langsung (count Account, `disabled` 0, company aktif).

- [ ] **Step 8: Commit.**

```bash
git add aios_v1/lib/desktop_modules.py aios_v1/lib/desktop_domains.py aios_v1/tests/test_desktop_modules.py aios_v1/tests/test_desktop_domains.py aios_v1/tests/test_frontend_no_hardcode.py frontend/src/api/mock/modules.ts
git commit -m "feat(desk): tambah modul Account read-only di Ekasa Desk"
```

---

### Task 6: Company → Accounting

**Files:**
- Modify: `aios_v1/lib/desktop_modules.py` (tambah entri `company` ke `_MODULES`)
- Modify: `aios_v1/lib/desktop_domains.py` (bidang `accounting`: modul tambah `"company"`)
- Modify: `aios_v1/tests/test_desktop_modules.py` (daftar-eksak final + perluas tes kartu master + tes site-wide)
- Modify: `aios_v1/tests/test_frontend_no_hardcode.py` (tambah `"Company"` ke `CATALOG_DOCTYPES`)
- Modify: `frontend/src/api/mock/modules.ts` (`MOCK_DOMAINS` accounting `module_count` 3 → 4; cabang accounting di `fetchDomain` tambah entri `company`, `row_count` 0)

**Interfaces:**
- Consumes: bidang `accounting` aktif (Task 3); pola entri master Customer/Supplier/Item; `_server_filters` (`aios_v1/api/desktop.py:221-230` — grup modul `Accounting` TIDAK ada di `{"Sales", "Finance"}`, jadi DocType tanpa field `company` TIDAK melempar; list memakai `base_filters` saja).
- Produces: key modul `"company"` terdaftar di `_MODULES_BY_KEY`; bidang `accounting` berisi `("journal_entry", "gl_entry", "account", "company")` — KEADAAN AKHIR Fase 1: 14 modul, 3 bidang aktif (sales, finance, accounting), 8 bidang planned.

**Riset field (terverifikasi dari `company.json`, ERPNext 16.34.2):** TIDAK submittable; field `company` TIDAK ADA (record Company ADALAH company itu sendiri); `company_name` [Data] (sumber `autoname` — field `name` = nama company); `abbr` [Data]; `default_currency` [Link → Currency]; `country` [Link]; `tax_id` [Data]; `is_group` [Check]; `parent_company` [Link → Company]. Field `disabled` TIDAK ADA; field `status` TIDAK ADA; field tanggal TIDAK ADA.

**Keputusan yang dipin (tidak bisa ditebak implementer):**
- **List menampilkan SEMUA company di site (site-wide, tanpa filter company).** Tidak ada cara memfilter Company ke company aktif — record-nya sendiri adalah company. Diterima untuk Fase 1 (Review Focus #3): Company adalah master data dan site normalnya punya 1 company. Label kartu memakai "di site" karena di sini benar-benar site-wide.

**Entri katalog yang dipin:**
- `key "company"`, `label "Company"`, `group "Accounting"`, `icon "building"` (ada di kosakata ikon — dipakai bidang assets; bila set ikon modul ternyata tidak menyediakan `building`, fallback ke `"users"` pola master pihak), `doctype "Company"`
- `columns`: `name` "ID" text; `company_name` "Nama company" text (kolom pihak); `abbr` "Singkatan" text; `default_currency` "Mata uang" text; `country` "Negara" text
- `filters`: `()`; `filter_fields`: `{}`
- `search_fields`: `("name", "company_name", "abbr")`
- `order_field`: `"company_name"`
- `base_filters`: `{}`
- `cards`: `count` "Company di site" (count, `name`, number, scope `site`, `{}`) — SATU kartu saja

- [ ] **Step 1: Tulis tes yang gagal.** Di `test_desktop_modules.py`, update `test_catalog_only_contains_approved_modules_and_doctypes` KE KEADAAN AKHIR: set key menjadi 14 key (`sales_invoice`, `sales_order`, `quotation`, `purchase_invoice`, `payment_entry`, `customer`, `supplier`, `item`, `delivery_note`, `item_price`, `journal_entry`, `gl_entry`, `account`, `company`); grup Sales menjadi 7 key; grup Finance tetap 3 key; grup Accounting menjadi `{"journal_entry", "gl_entry", "account", "company"}`; `assertNotIn("Purchase Order", ...)` tetap. Perluas loop di `test_master_cards_are_site_counts_without_nominal_fields` menjadi `(("customer", "Customer"), ("account", "Account"), ("company", "Company"))`. Tambah tes baru `test_company_module_is_site_wide_without_company_field`: assert `frappe.get_meta("Company").has_field("company") is False`; assert endpoint modul `company` mengembalikan company tes tanpa throw; assert kartu scope `site`. Tambah `"Company"` ke `_snapshot_counts` di `test_desktop_domains.py`.

```python
def test_company_module_is_site_wide_without_company_field(self):
    self.assertFalse(frappe.get_meta("Company").has_field("company"))
    result = frappe.call(desktop_api.module, module="company", page=1, page_size=1)
    self.assertEqual(result["module"]["key"], "company")
    self.assertTrue(result["rows"])
    self.assertEqual(len(result["cards"]), 1)
    self.assertEqual(result["cards"][0]["scope"], "site")
```

- [ ] **Step 2: Jalankan tes untuk memastikan gagal.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules`
Expected: FAIL — daftar-eksak (set key belum berisi `company`) dan tes site-wide baru (modul belum ada).

- [ ] **Step 3: Implementasi entri katalog `company` di `aios_v1/lib/desktop_modules.py`.** Tulis entri dengan nilai yang dipin di atas.

- [ ] **Step 4: Penempatan bidang.** Di `aios_v1/lib/desktop_domains.py`, tambah `"company"` ke modul bidang `accounting` (setelah `"account"`). Kartu KPI bidang Accounting TIDAK diubah (tetap 4 kartu dari Task 3 + Task 4).

- [ ] **Step 5: Sinkron mock + konstanta tes anti-hardcode.** Di `frontend/src/api/mock/modules.ts`: `MOCK_DOMAINS` accounting `module_count` 3 → 4; cabang accounting di `fetchDomain` tambah `{ key: 'company', label: 'Company', icon: 'building', row_count: 0 }`. Di `test_frontend_no_hardcode.py`: tambah `"Company"` ke `CATALOG_DOCTYPES`.

- [ ] **Step 6: Jalankan tes untuk memastikan lolos — SEKALIGUS verifikasi akhir Fase 1.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_domains` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_frontend_no_hardcode`
Expected: PASS — ketiga modul hijau. Verifikasi akhir keadaan Fase 1 (assert di tes yang sudah ada): `get_module_keys()` = 14 key; `get_domain_keys()` = `["sales", "finance", "accounting"]`; `get_planned_domain_count()` = 8; `len(_DOMAINS)` = 11.

- [ ] **Step 7: Verifikasi live oleh Gemini lewat browser built-in Antigravity biasa (verifikasi akhir Fase 1; bukan `/browser` di sesi CLI, bukan oleh Ten).** Buka Ekasa Desk di bench PC (`aios-client1.localhost:5173`, restart bench dulu bila kode baru belum ter-load): bootstrap memuat 14 modul dan 3 bidang aktif; bidang Accounting menampilkan 4 modul (Journal Entry, GL Entry, Account, Company) dan 4 kartu KPI; buka modul Company — list menampilkan company; search dengan nama company menemukan barisnya; nilai kartu "Company di site" cocok dengan jumlah company di site. Cek silang global search: cari satu dokumen dari tiap modul baru (Delivery Note, Item Price, Journal Entry, GL Entry, Account, Company) — semuanya ditemukan. Cek silang agen: `open_module` menerima keenam key baru (enum dinamis dari `get_module_keys()`).

- [ ] **Step 8: Commit.**

```bash
git add aios_v1/lib/desktop_modules.py aios_v1/lib/desktop_domains.py aios_v1/tests/test_desktop_modules.py aios_v1/tests/test_desktop_domains.py aios_v1/tests/test_frontend_no_hardcode.py frontend/src/api/mock/modules.ts
git commit -m "feat(desk): tambah modul Company read-only di Ekasa Desk"
```

---

## Self-Review

(Dijalankan sendiri atas plan ini, sesuai skill — temuan diperbaiki inline, tidak perlu re-review.)

1. **Spec coverage:** Tiap kebutuhan Lapis A di peta (§0.2a, §2 Lapis A, §3 tabel per-modul, §7 urutan 1, §9 keputusan 1-3 + 6-7) dipetakan ke task: 6 modul → Task 1-6; aktivasi Accounting → Task 3; read-only → Global Constraints + tiap entri tanpa alur draf; agen ikut terbuka → Global Constraints (tanpa perubahan cabang); branding bersamaan → dicatat sebagai paralel di luar plan (bukan task). Satu gap yang ditemukan dan diperbaiki: kartu KPI bidang Accounting belum diputuskan di peta — plan ini memutuskannya (1 kartu JE di Task 3 + 3 kartu GL di Task 4 = 4 kartu, sejajar Sales/Finance) dan mencatatnya sebagai poin review Ten. Laporan keuangan sebagai modul Desk dan HRIS/Payroll sengaja TIDAK masuk plan (scope terpisah, sesuai §9.4-5).
2. **Step scan:** Setiap step menghasilkan tepat satu hal yang bisa ditulis/dicek (satu edit tes, satu perintah bench dengan Expected, satu entri katalog, satu commit). Perbaikan yang dilakukan: Step 1 Task 3 awalnya mencampur update 3 file tes tanpa menyebut baris — dipecah per file dengan nomor baris/tes yang tepat. Tidak ada baris "TBD"/"tangani edge case".
3. **Type consistency:** Key modul (`delivery_note`, `item_price`, `journal_entry`, `gl_entry`, `account`, `company`), label, grup, dan field dipakai konsisten di semua task (contoh: `journal_entry` selalu grup `Accounting`; `total_debit` selalu field kartu JE di Task 3 dan Task 4 tidak menyentuhnya; `is_cancelled` hanya muncul di Task 4). Nama tes baru konsisten pola `test_<modul>_list_and_search...` / `test_<modul>_module_is_site_scoped...`.
4. **Review Focus:** Kelima baris masing-masing punya tes di task pemiliknya (GL docstatus → Task 4; Item Price throw → Task 2; Company site-wide → Task 6; search nama pihak → Task 1 + Task 2; harga kedaluwarsa → Task 2). Tidak ada bagian yang kosong.
5. **Proportion:** Plan ini lebih panjang dari bagian Lapis A di spec — wajar karena tiap modul butuh nilai eksak (field, label, filter, kartu) yang tidak ada di spec; tetapi plan TIDAK menulis badan kode (hanya nilai eksak + nama tes + assert singkat + perintah). Entri katalog ditulis sebagai daftar nilai ringkas, bukan literal dict Python penuh — implementer menulis badannya mengikuti pola entri yang sudah ada.

## Execution Handoff

Plan selesai dan disimpan di `docs/superpowers/plans/2026-11-16-lapis-a-tampil-semua-modul.md`.

Metode eksekusi sudah ditetapkan Ten: builder Gemini (Hydrogen) via Ten sebagai jembatan — satu draf implementasi per task, Muse crosscheck per task sebelum lanjut (workflow AGENTS.md; bukan subagent-driven, bukan native inline). Ten, mohon review plan ini dulu. Bila cocok, Muse buatkan draf implementasi Task 1 (Delivery Note) untuk dikirim ke builder.

Review keamanan selama implementasi (keputusan Ten 20:43): builder juga menjalankan Cloudflare Security Audit Skill (MIT, model-agnostic, publik di GitHub) — review keamanan + perkuat security sambil jalan. Cara pakai skill-nya (install via `npx skills add` atau baca langsung dari GitHub) ditentukan di draf implementasi / saat setup builder; bukan bagian dari plan ini.

**Keputusan Ten saat review (20:43):**
1. Item Price `base_filters` — **DISETUJUI Ten 20:44: `{"selling": 1}` (hanya harga jual)**, mengikuti rekomendasi Muse (modul Sales; harga beli adalah info biaya/margin; konsisten dengan Standard Selling). Task 2 sudah di-update: `base_filters {"selling": 1}`, kartu count menghitung harga jual saja.
2. Item Price: pengecualian `"Item Price"` di `_server_filters` (tetap di grup Sales) — **DISETUJUI Ten ("Boleh sih")**. Alternatif pindah ke Accounting tetap ditolak.
3. Kartu KPI bidang Accounting: 1 kartu JE ("Total debit jurnal") + 3 kartu GL ("Entri GL tercatat", "Total debit", "Total kredit") — total 4 kartu, sejajar Sales/Finance — **DISETUJUI Ten ("Okehh")**.
4. Ikon modul Company: `"building"` (fallback `"users"` bila set ikon modul tidak menyediakannya) — **DISETUJUI Ten ("Bolehh")**.

**Yang TIDAK ada di plan ini (sengaja):** laporan keuangan sebagai modul Desk, Lapis B (bidang planned), HRIS/Payroll, branding Finto OS/Fino, halaman detail dokumen, harga di kartu approval, deploy server testing, push. Masing-masing diputuskan/dijadwalkan terpisah.
