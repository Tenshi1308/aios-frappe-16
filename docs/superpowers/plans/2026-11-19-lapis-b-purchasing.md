# Lapis B — Tampilkan Bidang Purchasing + Branding Finto OS/Fino di Ekasa Desk: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menampilkan 3 DocType Purchasing (Purchase Order, Purchase Receipt, Supplier Quotation) sebagai modul read-only di Ekasa Desk, sehingga bidang menjadi 4 (Sales, Finance, Accounting, Purchasing) — satu bidang planned sebagai pola, bersamaan dengan branding Finto OS/Fino.

**Architecture:** Ikuti preseden Lapis A (plan `2026-11-16-lapis-a-tampil-semua-modul.md`, 6 modul selesai penuh 18 Nov 2026, commit terakhir `5af2a28`): tiap modul = satu entri di katalog server `desktop_modules.py` + penempatan di bidang `desktop_domains.py` + update tes daftar-eksak + sinkron mock frontend. Beda dengan Lapis A: ketiga DocType BELUM ada di allowlist, jadi Task 1 menambahkannya ke `ERP_CLIENT_DOCTYPES` + migrate di site dev. Satu modul = satu task = satu commit; task berjalan berurutan 1 → 4 (jangan diparalelkan — update daftar-eksak tiap task dibangun di atas task sebelumnya). Branding dikerjakan sebagai Batch 2 terpisah, riset dulu (Task B1) baru implementasi sesudah Ten memilih pemetaannya (Task B2).

**Tech Stack:** Frappe/ERPNext 16.34.2, Python (backend `aios_v1`), Vue (frontend Ekasa Desk, generik — tanpa ubah komponen), `bench run-tests`.

**Spec:** `~/workspace/aios/peta-tampil-semua-modul.md` (peta + §9 Keputusan Ten, 16 Nov 2026) dan `~/workspace/aios/tugas-tampil-semua-modul.md` (daftar tugas, bagian Fase 2). Plan ini berargumen dari spec itu; executor membaca ketiganya. Lokasi draf plan ini: `~/workspace/aios/rencana-lapis-b-superpowers.md` (untuk review Ten; setelah disetujui, masuk ke `docs/superpowers/plans/2026-11-19-lapis-b-purchasing.md` di repo).

## Bukti riset (19 Nov 2026 — yang membedakan plan ini dari draf mentah 18 Nov)

Draf investigasi Lapis B 18 Nov ditulis hanya dari dokumen, tanpa membaca kode repo — semua nilainya belum terverifikasi. Plan ini ditulis SESUDAH riset mendalam berikut, semuanya dicek langsung ke sumbernya hari ini:

1. **Repo live via SSH read-only** (`~/mybench-v16/apps/aios_v1`, branch `feat/plugin-mcp-manager`, HEAD `5af2a28`, bersih). Semua nomor baris di plan ini dikutip dari HEAD itu. Bila `git log -1` sudah bukan `5af2a28` saat eksekusi, verifikasi ulang nomor baris dulu (Task 1 Step 0).
2. **Field DocType dari ERPNext yang TERPASANG di bench** (`apps/erpnext/erpnext/.../*.json`, bukan cermin web): keempat DocType Purchasing dibaca field demi field (lihat tabel riset di bawah). Ini sumber yang sama dengan yang dipakai builder — bukan tebakan.
3. **Master dibaca penuh:** peta, daftar tugas, dan plan Lapis A (bukan ringkasannya).

### Tabel riset field (dari JSON DocType ERPNext 16.34.2 terpasang)

| DocType | Submittable | `company` | Tanggal | Pihak | Total (base currency) | Status |
|---|---|---|---|---|---|---|
| Purchase Order | ya (1) | ADA (Link→Company) | `transaction_date` Date, `schedule_date` Date | `supplier` Link→Supplier + `supplier_name` Data | `base_grand_total` Currency | Select: Draft, On Hold, To Receive and Bill, To Bill, To Receive, Completed, Cancelled, Closed, Delivered |
| Purchase Receipt | ya (1) | ADA | `posting_date` Date, `posting_time` Time | `supplier` + `supplier_name` | `base_grand_total` Currency | Select: Draft, Partly Billed, To Bill, Completed, Return, Return Issued, Cancelled, Closed |
| Supplier Quotation | ya (1) | ADA | `transaction_date` Date, `valid_till` Date | `supplier` + `supplier_name` | `base_grand_total` Currency | Select: Draft, Submitted, Stopped, Cancelled, Expired |
| Request for Quotation | ya (1) | ADA | `transaction_date` Date, `schedule_date` Date | TIDAK ADA `supplier_name`; `vendor` Link→Supplier + tabel `suppliers` (multi-supplier) | TIDAK ADA total/currency | Select: Draft, Submitted, Cancelled |

Konsekuensi yang dipin dari tabel ini (bukan asumsi):
- Ketiga modul Fase 2 punya field `company` → `_server_filters` (`api/desktop.py:234-244`) memfilter ke company aktif secara normal. TIDAK ada pengecualian seperti Item Price di Lapis A.
- Ketiganya submittable → `base_filters {"docstatus": 1}` dan kartu boleh memakai kata "terbit".
- **Request for Quotation TIDAK masuk Fase 2** (keputusan dipin, mengikuti daftar tugas Fase 2 yang hanya berisi 3 modul): RFQ tidak punya `supplier_name`, tidak punya total/mata uang, dan pihaknya tabel multi-supplier — pola katalog (kolom pihak + kolom total + `search_fields` nama tampilan) tidak berlaku untuknya. Bila RFQ mau ditampilkan, itu plan tersendiri dengan pola katalog baru, bukan tambahan satu baris di plan ini.

### Jangkar kode yang terverifikasi (HEAD `5af2a28`)

- `_MODULES` 14 key, entri terakhir `company` (`desktop_modules.py:604-630`, file 672 baris). Pola entri transaksi yang diikuti: Sales Order (`:63-116`) dan Purchase Invoice (`:225-278`, analog supplier terdekat).
- Bidang `purchasing` sudah ada sebagai planned (`desktop_domains.py:105-112`): key `purchasing`, label `Purchasing`, icon `cart`, `color_token` `domain-purchasing`, status `planned`, modul `()`, kartu `()`.
- `ERP_CLIENT_DOCTYPES` 14 doctype (`permissions.py:49-64`) — ketiga DocType Purchasing BELUM ada. Berbeda dengan Lapis A: plan ini WAJIB ubah allowlist + migrate.
- Tes katalog eksak (`test_desktop_modules.py:191-226`): 14 key; `assertNotIn("Purchase Order", ...)` di `:210`; grup Sales 7 / Finance 3 / Accounting 4.
- `test_list_rejects_unknown_module_doctype_and_filter_fields` (`:344-346`): masih memanggil `module="purchase_order"` dan mengharapkan `ValidationError` — tes ini AKAN MERAH sesudah Task 1 bila tidak diubah (temuan riset, bukan tebakan).
- Tes kartu transaksi (`:538-552`): tuple `("sales_invoice", "sales_order", "quotation", "delivery_note", "purchase_invoice")` meng-assert kartu sum memakai `base_grand_total` + filter `docstatus` 1.
- Tes bidang (`test_desktop_domains.py:164-169`): keys `["sales", "finance", "accounting"]`, planned 8, `len(_DOMAINS)` 11; `:263` kartu per bidang `(sales 4, finance 4, accounting 4)`; `_snapshot_counts` (`:134-165`) berisi 14 doctype.
- `CATALOG_DOCTYPES` 14 doctype + `ACTIVE_DOMAINS ("Sales", "Finance", "Accounting")` (`test_frontend_no_hardcode.py:47-70`).
- Mock (`frontend/src/api/mock/modules.ts`, 409 baris): `MOCK_DOMAINS` hanya 3 bidang aktif (sales 7, finance 3, accounting 4); `fetchDomain` (`:107-138`) bercabang `isFinance` / `isAccounting`; `MOCK_MODULES` hanya berisi `sales_invoice` (gap pra-ada dari Lapis A, bukan langkah plan ini).
- `_domain_card_value` (`api/desktop.py:348-356`): kartu bidang memakai field `company` bila ada, bila tidak melempar — ketiga DocType punya `company`, jadi kartu bidang aman.
- Token warna bidang purchasing SUDAH ada (`frontend/src/styles/tokens.css:43,197,247`): `--domain-purchasing: #3d7bd9` (terang) / `#6ba3f5` (gelap). Tidak perlu token baru untuk bidang ini.
- `_PRIORITY_BRANCHES` (`plugin_manager/registry.py:1043`) = `{"finance", "sales", "accounting"}` — TIDAK diubah plan ini (lihat Global Constraints).
- Branding di repo (`docs/branding-finto-os/`): `README.md` (palet navy `#0B1F3B`, biru `#0E63FF`, cyan `#00D4C8`, lime `#A7F432`, violet `#8B5CF6`, terang `#F3F7FB`), `logo/` (9 file: `finto-logo.png`, `finto-icon-32.svg`, dll.), `mascot/` (Fino: `fino-celebrate.jpg`, `fino-welcome.jpg`, `finto-hero-front-transparent.png`, dll.), `demo-booting-finto-os.mp4` (CATATAN: boot produk SPI, bukan AIOS — jangan disalin mentah-mentah).

## Global Constraints

Setiap task secara implisit mencakup bagian ini.

- Modul baru read-only (list + kartu hitung + filter + search). Aksi tetap hanya Sales + Finance (alur draf SO/Quotation tidak disentuh; tidak ada alur draf baru).
- Agen ikut terbuka otomatis via allowlist global `ERP_CLIENT_DOCTYPES` (tidak bisa dipisah — keputusan Ten §9.3). Cabang agen tetap Sales + Finance + Accounting: tidak ada perubahan `_PRIORITY_BRANCHES` di `registry.py`, tidak ada handler baru di `branch_handlers.py`, tidak ada persona agent Purchasing (belum diputuskan Ten).
- Request for Quotation TIDAK masuk Fase 2 (lihat tabel riset). Laporan keuangan sebagai modul Desk BUKAN bagian plan ini (scope terpisah, direncanakan belakangan). Tanpa HRIS/Payroll; tanpa pasang aplikasi baru.
- Branding Finto OS/Fino dikerjakan sebagai Batch 2 plan ini, BUKAN di dalam task modul. Batch 1 tidak mengubah tampilan apa pun.
- Frontend generik: tanpa ubah komponen Vue; hanya sinkron mock `frontend/src/api/mock/modules.ts` (dev parity) + token warna bila sudah ada.
- Label modul memakai nama DocType Inggris (konsisten dengan 14 modul yang ada). Label kolom/filter UI memakai Bahasa Indonesia ("Nomor", "Tanggal", "Supplier", "Status", "Total", "Dari tanggal", "Sampai tanggal", "Pihak"). Label kartu hitung memakai "terbit" HANYA untuk DocType submittable (docstatus 1) — ketiganya submittable, jadi ketiganya boleh.
- Satu modul = satu task = satu commit, pesan commit pola `feat(desk): ...`. Tidak push — push keputusan Ten.
- Cara resmi tes: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.<module>`. Verifikasi live via browser (built-in Antigravity) di bench PC Ten (`aios-client1.localhost:5173`); bila kode baru belum ter-load, restart bench dulu. Deploy ke server testing BUKAN bagian plan ini (keputusan Ten sesudah commit, seperti preseden Quotation).
- Migrate site dev (`aios-v16.localhost`) dilakukan di Task 1. Migrate site client (`aios-client1.localhost`) HANYA atas izin eksplisit Ten saat verifikasi live (preseden Opsi A, 18 Nov 14:41) — tanpa izin itu, verifikasi live modul baru di client1 tidak bisa jalan dan task berhenti di situ.
- YAGNI: jangan tambah filter/kolom/kartu di luar yang dipin di tiap task. Jangan perbaiki gap pra-ada: `"Quotation"` hilang dari `CATALOG_DOCTYPES` di `test_frontend_no_hardcode.py`, dan `MOCK_MODULES` di mock hanya berisi `sales_invoice` — keduanya dicatat sebagai follow-up, bukan langkah di plan ini.
- Rencana Fase 3 (bidang planned lain: Inventory, Manufacturing, Projects, CRM, Assets, Support, Quality) dibuat SETELAH Fase 2 selesai — bukan bagian plan ini.

## Review Focus

Lima mode kegagalan yang paling mungkin menggigit pengguna, yang tidak ditangkap tes-tes yang sudah ada. Tiap baris sudah ditambah tesnya di task yang bersangkutan.

1. **Allowlist ditambah tapi migrate lupa — modul baru gagal di site dev.** `ERP_CLIENT_DOCTYPES` hanya dibaca saat migrate memasang Custom DocPerm (`ensure_aios_permissions`, `permissions.py:295-298`). Tanpa migrate, endpoint modul melempar atau list kosong padahal katalog sudah berisi modulnya. Tes penambat: Task 1 (tes endpoint modul `purchase_order` mengembalikan baris — hanya lolos bila migrate sudah jalan; langkah migrate ada sebagai step eksplisit sebelum implementasi katalog).
2. **Tes penolak modul tak dikenal masih menolak Purchase Order.** `test_list_rejects_unknown_module_doctype_and_filter_fields` (`:344-346`) mengharapkan `ValidationError` untuk `module="purchase_order"` — sesudah Task 1, panggilan itu VALID dan tes merah bila barisnya tidak diubah. Tes penambat: Task 1 (hapus panggilan PO dari tes itu, ganti dengan panggilan `module="request_for_quotation"` yang tetap harus melempar — RFQ memang tetap tak dikenal).
3. **Search memakai ID supplier saja tidak menemukan apa-apa.** Bila `search_fields` hanya berisi field ID (`supplier`) dan bukan field nama tampilan (`supplier_name`), pencarian "Tenshi" tidak menemukan dokumen padahal namanya tampil di list (pelajaran Review Focus #4 Lapis A). Tes penambat: Task 1–3 (tiap modul: assert search dengan `supplier_name` menemukan nomornya).
4. **Kartu sum memakai `grand_total`, bukan `base_grand_total`.** `grand_total` dalam mata uang dokumen — menjumlahkannya lintas supplier bermata uang beda menghasilkan angka campur yang salah. Tes penambat: Task 1–3 (perluas tuple tes kartu transaksi `:538` dengan tiap modul baru — assert kartu sum memakai `base_grand_total` + filter `docstatus` 1).
5. **Penawaran kedaluwarsa dan tanda terima retur tampil tanpa penanda.** Supplier Quotation dengan `valid_till` yang sudah lewat tetap masuk list (ERPNext tidak memfilternya otomatis); Purchase Receipt retur (`is_return` 1, seri `MAT-PR-RET`) tercampur dengan tanda terima biasa. Diterima untuk Fase 2 — perilaku ini didokumentasikan, bukan kejutan. Tes penambat: Task 2 (sisipkan 1 baris PR `is_return` 1, assert list tetap mengembalikannya) dan Task 3 (sisipkan 1 baris SQ `valid_till` kemarin, assert list tetap mengembalikannya).

## Scope Check

Spec (peta) mencakup beberapa subsistem independen: Lapis A (6 modul, selesai), Lapis B (9 bidang planned — plan ini hanya Purchasing), Lapis C (HRIS/Payroll), laporan keuangan sebagai modul Desk, dan branding. Plan ini hanya mencakup DUA subsistem — Purchasing (3 modul, Batch 1) dan branding (Batch 2) — dan tiap batch menghasilkan perangkat lunak yang bekerja dan bisa dites sendiri (17 modul, 4 bidang aktif; lalu shell ber-branding Finto OS/Fino). Lapis C, laporan keuangan, dan bidang planned lain masing-masing mendapat plan sendiri belakangan.

## File Structure

File yang diubah plan ini (dan tanggung jawabnya):

- `aios_v1/permissions.py` — `ERP_CLIENT_DOCTYPES`: tambah 3 doctype (Task 1 saja). Penjaga `ensure_aios_permissions()` memasang Custom DocPerm saat migrate.
- `aios_v1/lib/desktop_modules.py` — `_MODULES`: satu entri per modul (key/label/group/icon/doctype + kolom + filter + `filter_fields` + `search_fields` + `order_field` + `base_filters` + kartu hitung). Penjaga `RuntimeError` di akhir file menolak DocType di luar allowlist.
- `aios_v1/lib/desktop_domains.py` — `_DOMAINS`: aktivasi bidang `purchasing` (`planned` → `active`) + penempatan key modul + kartu KPI bidang. Penjaga `_validate_domain_catalog` menolak key modul tak dikenal dan kartu dengan DocType di luar allowlist.
- `aios_v1/api/desktop.py` — TIDAK diubah plan ini (ketiga DocType punya field `company`, jadi `_server_filters` dan `_domain_card_value` berlaku normal tanpa pengecualian).
- `aios_v1/tests/test_desktop_modules.py` — daftar-eksak katalog + tes per modul + tes penolak modul tak dikenal + tuple kartu transaksi.
- `aios_v1/tests/test_desktop_domains.py` — hitung planned, bidang aktif, bentuk domain + KPI, `open_domain`, `_snapshot_counts`.
- `aios_v1/tests/test_frontend_no_hardcode.py` — konstanta `CATALOG_DOCTYPES` (+3 doctype) dan `ACTIVE_DOMAINS` (+`"Purchasing"`).
- `frontend/src/api/mock/modules.ts` — `MOCK_DOMAINS` (tambah entri purchasing) + cabang purchasing di `fetchDomain` (dev parity).
- Branding (Batch 2, file ditentukan Task B1): aset di `docs/branding-finto-os/` sudah ada di repo; file tema/shell yang disentuh dipin di proposal B1 yang Ten pilih, bukan di plan ini.

File yang TIDAK disentuh: `aios_v1/lib/branch_handlers.py`, `aios_v1/plugin_manager/registry.py`, `aios_v1/lib/erpnext_action_drafts.py`, `draft_manager.py`, `aios_v1/tests/test_client_seeder_contract.py`, komponen Vue apa pun (Batch 1).

## Task Right-Sizing

Tiap task adalah satu modul: unit terkecil yang punya siklus tes sendiri, deliverable yang bisa dites sendiri (modul tampil + list + search + kartu), dan bisa ditolak/disetujui sendiri oleh reviewer. Aktivasi bidang Purchasing + allowlist + migrate dilipat ke Task 1 (task yang butuh deliverable-nya), bukan task sendiri. Tiap step adalah satu aksi dengan hasil yang bisa dicek (tulis tes gagal → jalanin → implementasi minimal → jalanin tes → verifikasi live → commit).

---

## Batch 1 — Purchasing

### Task 1: Purchase Order → Purchasing (AKTIVASI bidang Purchasing dilipat ke task ini)

**Files:**
- Modify: `aios_v1/permissions.py` (tambah 3 doctype ke `ERP_CLIENT_DOCTYPES`, `:49-64`)
- Modify: `aios_v1/lib/desktop_modules.py` (tambah entri `purchase_order` ke `_MODULES`, setelah entri `company` `:604-630`)
- Modify: `aios_v1/lib/desktop_domains.py` (bidang `purchasing` `:105-112`: status `planned` → `active`, modul `("purchase_order",)`, kartu `po_count` + `po_total`)
- Modify: `aios_v1/tests/test_desktop_modules.py` (daftar-eksak + tes list/search PO + ubah tes penolak modul tak dikenal + tuple kartu transaksi)
- Modify: `aios_v1/tests/test_desktop_domains.py` (hitung planned 8 → 7, bidang aktif +`purchasing`, bentuk domain + KPI, `open_domain("purchasing")`, `_snapshot_counts`)
- Modify: `aios_v1/tests/test_frontend_no_hardcode.py` (tambah `"Purchase Order"` ke `CATALOG_DOCTYPES` `:47-62`; tambah `"Purchasing"` ke `ACTIVE_DOMAINS` `:70`)
- Modify: `frontend/src/api/mock/modules.ts` (`MOCK_DOMAINS` tambah entri purchasing `module_count` 1; `fetchDomain` tambah cabang purchasing)

**Interfaces:**
- Consumes: pola entri Sales Order (`desktop_modules.py:63-116` — kolom `customer_name`, `filter_fields` pihak → field ID operator `like`, `search_fields` nama tampilan, `order_field` tanggal, `base_filters {"docstatus": 1}`); pola entri Purchase Invoice (`:225-278`, analog supplier terdekat); entri bidang `purchasing` yang sudah ada sebagai `planned`; aturan `_validate_domain_catalog`; kartu bidang Finance/Sales sebagai preseden label.
- Produces: key modul `"purchase_order"` terdaftar di `_MODULES_BY_KEY`; bidang `purchasing` berstatus `active` dengan modul `("purchase_order",)` dan 2 kartu KPI; `get_domain_keys()` mengembalikan `["sales", "finance", "accounting", "purchasing"]`; `get_planned_domain_count()` mengembalikan 7; `"Purchase Order"`, `"Purchase Receipt"`, `"Supplier Quotation"` masuk `ERP_CLIENT_DOCTYPES` (dipakai Task 2–3 tanpa ubah allowlist lagi).

**Riset field (terverifikasi dari `purchase_order.json`, ERPNext 16.34.2 terpasang):** submittable (`is_submittable` 1); `company` [Link] ADA; `supplier` [Link → Supplier] + `supplier_name` [Data] ADA (`title_field`); `transaction_date` [Date]; `schedule_date` [Date, "Required By"]; `status` [Select: Draft, On Hold, To Receive and Bill, To Bill, To Receive, Completed, Cancelled, Closed, Delivered]; `base_grand_total` [Currency]; `currency` [Link]; `ref_sq` [Link → Supplier Quotation]; `is_internal_supplier` [Check]; `per_received`/`per_billed` [Percent].

**Keputusan yang dipin (tidak bisa ditebak implementer):**
- **Allowlist + migrate adalah SATU-SATUNYA perubahan izin di plan ini.** Tanpa migrate di site dev, Custom DocPerm tidak terpasang dan endpoint modul gagal (Review Focus #1). Migrate site client HANYA atas izin eksplisit Ten saat verifikasi live.
- **`base_filters` = `{"docstatus": 1}`.** Purchase Order submittable; kartu boleh memakai "terbit".
- **PO internal (`is_internal_supplier` 1) tetap dihitung** seperti PO lain — PO antar-company tetap komitmen pembelian, bukan transfer internal yang harus dikecualikan (beda dengan pelajaran GL Entry Lapis A). Perilaku ini dipin lewat tes, bukan kejutan.

**Entri katalog yang dipin:**
- `key "purchase_order"`, `label "Purchase Order"`, `group "Purchasing"`, `icon "file"`, `doctype "Purchase Order"`
- `columns`: `name` "Nomor" text; `transaction_date` "Tanggal" date; `supplier_name` "Supplier" text (kolom pihak); `status` "Status" text; `base_grand_total` "Total" currency
- `filters`: `date_from` "Dari tanggal" date; `date_to` "Sampai tanggal" date; `status` "Status" text; `party` "Supplier" text
- `filter_fields`: `date_from {transaction_date, >=}`, `date_to {transaction_date, <=}`, `status {status, =}`, `party {supplier, like}`
- `search_fields`: `("name", "supplier", "supplier_name")`
- `order_field`: `"transaction_date"`
- `base_filters`: `{"docstatus": 1}`
- `cards`: `count` "Order pembelian terbit" (count, `name`, number, scope `company`, `{"docstatus": 1}`); `total` "Total order pembelian" (sum, `base_grand_total`, currency, scope `company`, `{"docstatus": 1}`)

**Kartu KPI bidang Purchasing yang dipin (task ini — 2 kartu):**
- `po_count` "Order pembelian terbit" (count, Purchase Order, `name`, number, `{"docstatus": 1}`)
- `po_total` "Total order pembelian" (sum, Purchase Order, `base_grand_total`, currency, `{"docstatus": 1}`)

- [ ] **Step 0: Verifikasi jangkar.** `git log -1` masih `5af2a28` dan `git status` bersih. Bila sudah ada commit sesudahnya, verifikasi ulang nomor baris yang dikutip plan ini (terutama `:191`, `:210`, `:344`, `:538`, `desktop_domains.py:105-112`, `:164-169`, `:263`) dan sesuaikan sebelum lanjut. Hitung langsung read-only di `aios-client1.localhost` (cara resmi bench, mengikuti preseden Task 6): total baris tiap DocType (Purchase Order, Purchase Receipt, Supplier Quotation) + contoh 1 baris tiap DocType (`ORDER BY creation ASC LIMIT 1`: nomor, tanggal, supplier, total, status/docstatus). Catatan riset 19 Nov: shell SSH non-interaktif tidak menemukan perintah `bench` di PATH — jalankan hitung langsung dari shell login / environment bench yang sama seperti preseden Task 6, jangan ganti cara hitung. Catat angkanya di laporan task — jangan mengarang angka, jangan pin angka ke plan.

- [ ] **Step 1: Tulis tes yang gagal.** Di `test_desktop_modules.py`, update `test_catalog_only_contains_approved_modules_and_doctypes` (`:191-226`): set key menjadi 15 key (14 + `"purchase_order"`); tambah grup Purchasing `{"purchase_order"}`; HAPUS `assertNotIn("Purchase Order", ...)` (`:210`); TAMBAH `assertNotIn("Request for Quotation", {module["doctype"] for module in modules})` (RFQ tetap di luar Fase 2). Di `test_list_rejects_unknown_module_doctype_and_filter_fields` (`:344-346`): HAPUS panggilan `module="purchase_order"`; TAMBAH panggilan `module="request_for_quotation", doctype="Request for Quotation"` yang tetap harus melempar `ValidationError`. Tambah `"purchase_order"` ke tuple di `test_transaction_cards_use_base_currency_and_exclude_internal_transfers` (`:548`). Tambah tes baru `test_purchase_order_list_and_search_return_submitted_company_scoped_rows`, mengikuti pola `test_quotation_list_and_search_return_submitted_company_scoped_rows` (`:554-624`): sisipkan 3 baris Purchase Order (satu `docstatus` 1 di company aktif; satu draft/`docstatus` 0; satu `docstatus` 1 di company lain — salah satunya `is_internal_supplier` 1), assert list hanya mengembalikan yang submitted + company aktif (termasuk yang internal — perilaku dipin), dan assert search dengan `supplier_name` menemukan nomornya. Tambah `"Purchase Order"` ke `_snapshot_counts` di `test_desktop_domains.py` (`:134-165`). Di `test_desktop_domains.py`: update `test_catalog_contains_active_only_and_tracks_planned_count` (`:164-169`) — katalog bidang menjadi `["sales", "finance", "accounting", "purchasing"]`, `get_planned_domain_count()` menjadi 7, `len(_DOMAINS)` tetap 11. Tambah `"Purchasing"` ke `ACTIVE_DOMAINS` dan `"Purchase Order"` ke `CATALOG_DOCTYPES` di `test_frontend_no_hardcode.py`.

- [ ] **Step 2: Jalankan tes untuk memastikan gagal.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_domains`
Expected: FAIL — daftar-eksak (set key belum berisi `purchase_order`), tes list/search PO baru (modul belum ada), dan hitung planned (masih 8).

- [ ] **Step 3: Tambah allowlist + migrate site dev.** Di `aios_v1/permissions.py`, tambah `"Purchase Order"`, `"Purchase Receipt"`, `"Supplier Quotation"` ke `ERP_CLIENT_DOCTYPES` (`:49-64`, setelah `"Purchase Invoice"`). Lalu `bench --site aios-v16.localhost migrate` agar Custom DocPerm terpasang. JANGAN migrate `aios-client1.localhost` di step ini (butuh izin Ten — lihat Global Constraints).

- [ ] **Step 4: Implementasi entri katalog `purchase_order` di `aios_v1/lib/desktop_modules.py`.** Tulis entri dengan nilai yang dipin di atas, mengikuti persis bentuk entri Sales Order.

- [ ] **Step 5: Aktivasi bidang Purchasing.** Di `aios_v1/lib/desktop_domains.py`, ubah entri `purchasing` (`:105-112`): status `planned` → `active`, modul `("purchase_order",)`, kartu `po_count` + `po_total` seperti dipin di atas. Bidang Sales, Finance, Accounting TIDAK diubah.

- [ ] **Step 6: Sinkron mock + konstanta tes anti-hardcode.** Di `frontend/src/api/mock/modules.ts`: `MOCK_DOMAINS` tambah `{ key: 'purchasing', label: 'Purchasing', icon: 'cart', color_token: 'domain-purchasing', module_count: 1 }`; `fetchDomain` (`:107-138`) tambah cabang purchasing mengikuti pola cabang accounting (`isAccounting`), mengembalikan daftar modulnya (`{ key: 'purchase_order', label: 'Purchase Order', icon: 'file', row_count: 0 }`) dan kartu domainnya. Di `test_frontend_no_hardcode.py`: tambah `"Purchase Order"` ke `CATALOG_DOCTYPES` dan `"Purchasing"` ke `ACTIVE_DOMAINS`.

- [ ] **Step 7: Jalankan tes untuk memastikan lolos.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_domains` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_frontend_no_hardcode`
Expected: PASS — ketiga modul hijau, termasuk `test_catalog_fields_are_valid_for_every_doctype` (semua field entri baru valid di meta Purchase Order) dan `test_module_endpoints_run_read_only_queries_for_catalog` (endpoint modul mengembalikan kartu — bukti migrate bekerja).

- [ ] **Step 8: Verifikasi live via browser.** Migrate `aios-client1.localhost` HANYA sesudah Ten mengizinkan eksplisit (lihat Global Constraints). Buka Ekasa Desk di bench PC (`aios-client1.localhost:5173`, restart bench dulu bila kode baru belum ter-load): bootstrap memuat 4 bidang aktif (sales, finance, accounting, purchasing) dan `purchase_order`; bidang Purchasing bisa dibuka (tidak lagi "Bidang tidak tersedia"); kartu "Order pembelian terbit" dan "Total order pembelian" tampil dengan nilai yang cocok dengan hitung langsung Step 0; buka modul Purchase Order — list menampilkan PO yang submitted di company aktif; search dengan nama supplier menemukan nomornya; filter Status mempersempit list.

- [ ] **Step 9: Commit.**

```bash
git add aios_v1/permissions.py aios_v1/lib/desktop_modules.py aios_v1/lib/desktop_domains.py aios_v1/tests/test_desktop_modules.py aios_v1/tests/test_desktop_domains.py aios_v1/tests/test_frontend_no_hardcode.py frontend/src/api/mock/modules.ts
git commit -m "feat(desk): aktifkan bidang Purchasing + tambah modul Purchase Order read-only"
```

---

### Task 2: Purchase Receipt → Purchasing

**Files:**
- Modify: `aios_v1/lib/desktop_modules.py` (tambah entri `purchase_receipt` ke `_MODULES`)
- Modify: `aios_v1/lib/desktop_domains.py` (bidang `purchasing`: modul tambah `"purchase_receipt"`, kartu tambah `pr_count` + `pr_total`)
- Modify: `aios_v1/tests/test_desktop_modules.py` (daftar-eksak + tes list/search PR + tes perilaku retur + tuple kartu transaksi)
- Modify: `aios_v1/tests/test_frontend_no_hardcode.py` (tambah `"Purchase Receipt"` ke `CATALOG_DOCTYPES`)
- Modify: `frontend/src/api/mock/modules.ts` (`MOCK_DOMAINS` purchasing `module_count` 1 → 2; cabang purchasing di `fetchDomain` tambah entri `purchase_receipt`, `row_count` 0)

**Interfaces:**
- Consumes: bidang `purchasing` aktif (Task 1); pola entri Delivery Note (`desktop_modules.py:171-224` — modul transaksi dengan `posting_date`, analog penerimaan barang terdekat); `_server_filters` (Purchase Receipt punya field `company`, tanpa pengecualian).
- Produces: key modul `"purchase_receipt"` terdaftar di `_MODULES_BY_KEY`; bidang `purchasing` berisi `("purchase_order", "purchase_receipt")` dengan 4 kartu KPI.

**Riset field (terverifikasi dari `purchase_receipt.json`, ERPNext 16.34.2 terpasang):** submittable (`is_submittable` 1); `company` [Link] ADA; `supplier` [Link → Supplier] + `supplier_name` [Data] ADA (`title_field`); `posting_date` [Date]; `posting_time` [Time]; `status` [Select: Draft, Partly Billed, To Bill, Completed, Return, Return Issued, Cancelled, Closed]; `base_grand_total` [Currency]; `currency` [Link]; `is_return` [Check]; `return_against` [Link → Purchase Receipt]; `supplier_delivery_note` [Data]; `per_billed` [Percent].

**Keputusan yang dipin (tidak bisa ditebak implementer):**
- **`base_filters` = `{"docstatus": 1}`.** Tanda terima retur (`is_return` 1) tetap masuk list — diterima Fase 2, perilaku didokumentasikan lewat tes (Review Focus #5), bukan difilter diam-diam.
- **Kolom tanggal memakai `posting_date`** (bukan `transaction_date` — PR tidak punya field itu; mengikuti pola Delivery Note).

**Entri katalog yang dipin:**
- `key "purchase_receipt"`, `label "Purchase Receipt"`, `group "Purchasing"`, `icon "file"`, `doctype "Purchase Receipt"`
- `columns`: `name` "Nomor" text; `posting_date` "Tanggal" date; `supplier_name` "Supplier" text (kolom pihak); `status` "Status" text; `base_grand_total` "Total" currency
- `filters`: `date_from` "Dari tanggal" date; `date_to` "Sampai tanggal" date; `status` "Status" text; `party` "Supplier" text
- `filter_fields`: `date_from {posting_date, >=}`, `date_to {posting_date, <=}`, `status {status, =}`, `party {supplier, like}`
- `search_fields`: `("name", "supplier", "supplier_name")`
- `order_field`: `"posting_date"`
- `base_filters`: `{"docstatus": 1}`
- `cards`: `count` "Tanda terima terbit" (count, `name`, number, scope `company`, `{"docstatus": 1}`); `total` "Total tanda terima" (sum, `base_grand_total`, currency, scope `company`, `{"docstatus": 1}`)

**Kartu KPI bidang Purchasing yang dipin (task ini — 2 kartu, total bidang menjadi 4):**
- `pr_count` "Tanda terima terbit" (count, Purchase Receipt, `name`, number, `{"docstatus": 1}`)
- `pr_total` "Total tanda terima" (sum, Purchase Receipt, `base_grand_total`, currency, `{"docstatus": 1}`)

- [ ] **Step 1: Tulis tes yang gagal.** Di `test_desktop_modules.py`, update `test_catalog_only_contains_approved_modules_and_doctypes`: set key menjadi 16 key (15 + `"purchase_receipt"`); grup Purchasing menjadi `{"purchase_order", "purchase_receipt"}`. Tambah `"purchase_receipt"` ke tuple di `test_transaction_cards_use_base_currency_and_exclude_internal_transfers` (`:538`). Tambah tes baru `test_purchase_receipt_list_and_search_return_submitted_company_scoped_rows`, mengikuti pola tes Quotation: sisipkan 3 baris Purchase Receipt (satu `docstatus` 1 di company aktif; satu draft/`docstatus` 0; satu `docstatus` 1 di company lain), assert list hanya mengembalikan yang submitted + company aktif, dan assert search dengan `supplier_name` menemukan nomornya. Tambah tes perilaku retur (Review Focus #5): sisipkan 1 baris Purchase Receipt (`is_return` 1, `docstatus` 1, company aktif), assert list modul tetap mengembalikannya (Fase 2: tanpa filter retur). Tambah `"Purchase Receipt"` ke `_snapshot_counts` di `test_desktop_domains.py`. Di `test_desktop_domains.py`, update ekspektasi kartu purchasing dari 2 menjadi 4.

- [ ] **Step 2: Jalankan tes untuk memastikan gagal.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_domains`
Expected: FAIL — daftar-eksak (set key belum berisi `purchase_receipt`), tes list/search PR baru (modul belum ada), dan bentuk domain (kartu purchasing masih 2, bukan 4).

- [ ] **Step 3: Implementasi entri katalog `purchase_receipt` di `aios_v1/lib/desktop_modules.py`.** Tulis entri dengan nilai yang dipin di atas, mengikuti persis bentuk entri Delivery Note untuk kolom tanggal.

- [ ] **Step 4: Penempatan bidang + kartu KPI.** Di `aios_v1/lib/desktop_domains.py`, tambah `"purchase_receipt"` ke modul bidang `purchasing` (setelah `"purchase_order"`) dan tambah 2 kartu PR seperti dipin di atas.

- [ ] **Step 5: Sinkron mock + konstanta tes anti-hardcode.** Di `frontend/src/api/mock/modules.ts`: `MOCK_DOMAINS` purchasing `module_count` 1 → 2; cabang purchasing di `fetchDomain` tambah `{ key: 'purchase_receipt', label: 'Purchase Receipt', icon: 'file', row_count: 0 }`. Di `test_frontend_no_hardcode.py`: tambah `"Purchase Receipt"` ke `CATALOG_DOCTYPES`.

- [ ] **Step 6: Jalankan tes untuk memastikan lolos.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_domains` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_frontend_no_hardcode`
Expected: PASS — ketiga modul hijau, termasuk `test_catalog_fields_are_valid_for_every_doctype` (semua field entri PR valid di meta) dan `test_module_endpoints_run_read_only_queries_for_catalog`.

- [ ] **Step 7: Verifikasi live via browser.** Buka Ekasa Desk di bench PC (`aios-client1.localhost:5173`, restart bench dulu bila kode baru belum ter-load; migrate client1 hanya bila Ten mengizinkan — bila belum, verifikasi di site dev dulu dan catat): bidang Purchasing menampilkan 4 kartu KPI dengan nilai yang cocok dengan hitung langsung Task 1 Step 0; buka modul Purchase Receipt — list menampilkan tanda terima submitted di company aktif; search dengan nama supplier menemukan nomornya; filter Status mempersempit list.

- [ ] **Step 8: Commit.**

```bash
git add aios_v1/lib/desktop_modules.py aios_v1/lib/desktop_domains.py aios_v1/tests/test_desktop_modules.py aios_v1/tests/test_desktop_domains.py aios_v1/tests/test_frontend_no_hardcode.py frontend/src/api/mock/modules.ts
git commit -m "feat(desk): tambah modul Purchase Receipt read-only di Ekasa Desk"
```

---

### Task 3: Supplier Quotation → Purchasing

**Files:**
- Modify: `aios_v1/lib/desktop_modules.py` (tambah entri `supplier_quotation` ke `_MODULES`)
- Modify: `aios_v1/lib/desktop_domains.py` (bidang `purchasing`: modul tambah `"supplier_quotation"`, kartu tambah `sq_count` + `sq_total`)
- Modify: `aios_v1/tests/test_desktop_modules.py` (daftar-eksak + tes list/search SQ + tes perilaku kedaluwarsa + tuple kartu transaksi)
- Modify: `aios_v1/tests/test_frontend_no_hardcode.py` (tambah `"Supplier Quotation"` ke `CATALOG_DOCTYPES`)
- Modify: `frontend/src/api/mock/modules.ts` (`MOCK_DOMAINS` purchasing `module_count` 2 → 3; cabang purchasing di `fetchDomain` tambah entri `supplier_quotation`, `row_count` 0)

**Interfaces:**
- Consumes: bidang `purchasing` aktif (Task 1); pola entri Quotation (`desktop_modules.py:117-170` — modul penawaran dengan `transaction_date`, analog terdekat); `_server_filters` (Supplier Quotation punya field `company`, tanpa pengecualian).
- Produces: key modul `"supplier_quotation"` terdaftar di `_MODULES_BY_KEY`; bidang `purchasing` berisi `("purchase_order", "purchase_receipt", "supplier_quotation")` dengan 6 kartu KPI — KEADAAN AKHIR Batch 1: 17 modul, 4 bidang aktif (sales, finance, accounting, purchasing), 7 bidang planned.

**Riset field (terverifikasi dari `supplier_quotation.json`, ERPNext 16.34.2 terpasang):** submittable (`is_submittable` 1); `company` [Link] ADA; `supplier` [Link → Supplier] + `supplier_name` [Data] ADA (`title_field`); `transaction_date` [Date]; `valid_till` [Date]; `status` [Select: Draft, Submitted, Stopped, Cancelled, Expired]; `base_grand_total` [Currency]; `currency` [Link]; `quotation_number` [Data] (nomor penawaran supplier); `opportunity` [Link → Opportunity].

**Keputusan yang dipin (tidak bisa ditebak implementer):**
- **`base_filters` = `{"docstatus": 1}`.** Penawaran dengan `valid_till` lewat tetap masuk list — diterima Fase 2, perilaku didokumentasikan lewat tes (Review Focus #5); filter validitas adalah keputusan produk bila Ten memintanya.
- **Kolom tanggal memakai `transaction_date`** (mengikuti pola Quotation; `valid_till` bukan tanggal dokumen).

**Entri katalog yang dipin:**
- `key "supplier_quotation"`, `label "Supplier Quotation"`, `group "Purchasing"`, `icon "file"`, `doctype "Supplier Quotation"`
- `columns`: `name` "Nomor" text; `transaction_date` "Tanggal" date; `supplier_name` "Supplier" text (kolom pihak); `status` "Status" text; `base_grand_total` "Total" currency
- `filters`: `date_from` "Dari tanggal" date; `date_to` "Sampai tanggal" date; `status` "Status" text; `party` "Supplier" text
- `filter_fields`: `date_from {transaction_date, >=}`, `date_to {transaction_date, <=}`, `status {status, =}`, `party {supplier, like}`
- `search_fields`: `("name", "supplier", "supplier_name")`
- `order_field`: `"transaction_date"`
- `base_filters`: `{"docstatus": 1}`
- `cards`: `count` "Penawaran supplier terbit" (count, `name`, number, scope `company`, `{"docstatus": 1}`); `total` "Total penawaran supplier" (sum, `base_grand_total`, currency, scope `company`, `{"docstatus": 1}`)

**Kartu KPI bidang Purchasing yang dipin (task ini — 2 kartu, total bidang menjadi 6):**
- `sq_count` "Penawaran supplier terbit" (count, Supplier Quotation, `name`, number, `{"docstatus": 1}`)
- `sq_total` "Total penawaran supplier" (sum, Supplier Quotation, `base_grand_total`, currency, `{"docstatus": 1}`)

- [ ] **Step 1: Tulis tes yang gagal.** Di `test_desktop_modules.py`, update `test_catalog_only_contains_approved_modules_and_doctypes` KE KEADAAN AKHIR Batch 1: set key menjadi 17 key (16 + `"supplier_quotation"`); grup Purchasing menjadi `{"purchase_order", "purchase_receipt", "supplier_quotation"}`; `assertNotIn("Request for Quotation", ...)` tetap. Tambah `"supplier_quotation"` ke tuple di `test_transaction_cards_use_base_currency_and_exclude_internal_transfers`. Tambah tes baru `test_supplier_quotation_list_and_search_return_submitted_company_scoped_rows`, mengikuti pola tes Quotation: sisipkan 3 baris Supplier Quotation (satu `docstatus` 1 di company aktif; satu draft/`docstatus` 0; satu `docstatus` 1 di company lain), assert list hanya mengembalikan yang submitted + company aktif, dan assert search dengan `supplier_name` menemukan nomornya. Tambah tes perilaku kedaluwarsa (Review Focus #5): sisipkan 1 baris Supplier Quotation (`valid_till` kemarin, `docstatus` 1, company aktif), assert list modul tetap mengembalikannya (Fase 2: tanpa filter validitas). Tambah `"Supplier Quotation"` ke `_snapshot_counts` di `test_desktop_domains.py`. Di `test_desktop_domains.py`, update ekspektasi kartu purchasing dari 4 menjadi 6.

- [ ] **Step 2: Jalankan tes untuk memastikan gagal.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_domains`
Expected: FAIL — daftar-eksak (set key belum berisi `supplier_quotation`), tes list/search SQ baru (modul belum ada), dan bentuk domain (kartu purchasing masih 4, bukan 6).

- [ ] **Step 3: Implementasi entri katalog `supplier_quotation` di `aios_v1/lib/desktop_modules.py`.** Tulis entri dengan nilai yang dipin di atas, mengikuti persis bentuk entri Quotation.

- [ ] **Step 4: Penempatan bidang + kartu KPI.** Di `aios_v1/lib/desktop_domains.py`, tambah `"supplier_quotation"` ke modul bidang `purchasing` (setelah `"purchase_receipt"`) dan tambah 2 kartu SQ seperti dipin di atas.

- [ ] **Step 5: Sinkron mock + konstanta tes anti-hardcode.** Di `frontend/src/api/mock/modules.ts`: `MOCK_DOMAINS` purchasing `module_count` 2 → 3; cabang purchasing di `fetchDomain` tambah `{ key: 'supplier_quotation', label: 'Supplier Quotation', icon: 'file', row_count: 0 }`. Di `test_frontend_no_hardcode.py`: tambah `"Supplier Quotation"` ke `CATALOG_DOCTYPES`.

- [ ] **Step 6: Jalankan tes untuk memastikan lolos.**

Run: `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_modules` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_desktop_domains` dan `bench --site aios-v16.localhost run-tests --module aios_v1.tests.test_frontend_no_hardcode`
Expected: PASS — ketiga modul hijau, termasuk `test_catalog_fields_are_valid_for_every_doctype` dan `test_module_endpoints_run_read_only_queries_for_catalog`.

- [ ] **Step 7: Verifikasi live via browser.** Buka Ekasa Desk di bench PC (`aios-client1.localhost:5173`, restart bench dulu bila kode baru belum ter-load): bidang Purchasing menampilkan 6 kartu KPI dengan nilai yang cocok dengan hitung langsung Task 1 Step 0; buka modul Supplier Quotation — list menampilkan penawaran submitted di company aktif; search dengan nama supplier menemukan nomornya; filter Status mempersempit list. Verifikasi AKHIR Batch 1: bootstrap 17 modul + 4 bidang aktif; Sales/Finance/Accounting tidak berubah.

- [ ] **Step 8: Commit.**

```bash
git add aios_v1/lib/desktop_modules.py aios_v1/lib/desktop_domains.py aios_v1/tests/test_desktop_modules.py aios_v1/tests/test_desktop_domains.py aios_v1/tests/test_frontend_no_hardcode.py frontend/src/api/mock/modules.ts
git commit -m "feat(desk): tambah modul Supplier Quotation read-only di Ekasa Desk"
```

---

### Task 4: Sinkronisasi dokumentasi Batch 1

**Files:**
- Modify: `docs/10-peta-tampil-semua-modul.md` (keadaan akhir Batch 1: 17 modul, 4 bidang aktif, 7 planned; RFQ tetap di luar)
- Modify: `docs/11-tugas-tampil-semua-modul.md` (centang Task 1–3 Fase 2 + angka hitung langsung Task 1 Step 0)
- Modify: `docs/superpowers/plans/2026-11-19-lapis-b-purchasing.md` (plan ini, sesudah disetujui Ten)
- Modify: salinan workspace Muse (`~/workspace/aios/peta-tampil-semua-modul.md`, `tugas-tampil-semua-modul.md`, `rencana-lapis-b-superpowers.md`) — ikut disinkronkan, dua arah, bukan repo saja (keputusan Ten 19 Nov 2026)
- Modify: `README.md` (bila ada dokumen baru yang perlu didaftar)

**Interfaces:**
- Consumes: laporan tiap task (commit, angka hitung langsung, temuan) + preseden sinkronisasi Task 6 (commit `387d214`, 3 file).
- Produces: dokumentasi repo + salinan workspace Muse yang sinkron dengan kode HEAD sesudah Task 3 (1 = 1).

- [ ] **Step 1: Tulis perubahan dokumentasi.** Perbarui file-file di atas (repo + salinan workspace Muse — dua arah, bukan repo saja) dengan keadaan akhir Batch 1 (angka modul/bidang, status RFQ, angka hitung langsung dari Task 1 Step 0). Jangan ubah isi keputusan Ten — hanya status dan angka.
- [ ] **Step 2: Verifikasi.** `git diff --stat` hanya menyentuh file dokumentasi; tidak ada file kode yang berubah di commit ini.
- [ ] **Step 3: Commit.**

```bash
git add docs/10-peta-tampil-semua-modul.md docs/11-tugas-tampil-semua-modul.md docs/superpowers/plans/2026-11-19-lapis-b-purchasing.md
git commit -m "docs: sinkronisasi dokumentasi Lapis B (Purchasing)"
```

---

## Batch 2 — Branding Finto OS / Fino

### Task B1: Riset + usulan pemetaan branding (investigasi saja — TANPA ubah tampilan)

**Files:**
- Read-only: `frontend/src/styles/tokens.css`, `frontend/src/utils/theme.ts`, `frontend/src/components/shell/StartMenu.vue`, `frontend/src/components/domain/DomainWindow.vue`, `frontend/src/views/DesktopView.vue`, `frontend/src/stores/session.ts`, `frontend/src/api/session.ts`, `docs/branding-finto-os/README.md` + `logo/` + `mascot/` + `referensi-asli/02_SPESIFIKASI_TAMPILAN_FINTO_OS.md`
- Create: usulan pemetaan (dokumen, di workspace Muse dulu — bukan di repo)

**Interfaces:**
- Consumes: palet Finto OS (navy `#0B1F3B`, biru `#0E63FF`, cyan `#00D4C8`, lime `#A7F432`, violet `#8B5CF6`, terang `#F3F7FB`); aset logo + maskot Fino yang SUDAH ada di `docs/branding-finto-os/`; fakta bahwa token `--domain-purchasing` sudah ada (tidak perlu dibuat).
- Produces: daftar file shell/tema yang akan disentuh + pemetaan permukaan → nilai Finto → file (untuk Ten pilih) — dipakai Task B2.

- [ ] **Step 1: Verifikasi titik sentuh tema/shell.** Di repo/frontend: di mana tema/warna didefinisikan (`tokens.css`, `utils/theme.ts` — `ALLOWED_THEMES` saat ini hanya Automatic/Light/Dark, belum ada tema Finto)? Di mana logo dirender (StartMenu, session, PendingView — verifikasi cara rendernya, bukan asumsi)? Di mana maskot bisa tampil (layar sambutan / empty state / boot — verifikasi komponennya ada atau tidak)? Apakah ada aset logo/maskot Fino di frontend (bila belum ada, laporkan kosong — jangan buat aset)?
- [ ] **Step 2: Tulis usulan pemetaan.** Tabel permukaan → nilai Finto → file yang disentuh, untuk: (a) palet shell (variabel CSS apa diganti/ditambah), (b) logo (di permukaan mana, aset file mana), (c) maskot Fino (di permukaan mana, aset file mana), (d) boot screen (dipakai/tidak — ingat video referensi adalah boot SPI, bukan AIOS). Bila satu permukaan punya 2–3 pemetaan yang masuk akal, sajikan ketiganya dengan tradeoff, jangan pilih diam-diam.
- [ ] **Step 3: Berhenti dan tunggu Ten.** Deliverable: dokumen usulan pemetaan. JANGAN lanjut ke Task B2 sebelum Ten memilih pemetaannya — pilihan Ten dicatat sebagai amendemen plan ini.

### Task B2: Implementasi branding sesuai pilihan Ten (TERKUNCI sampai B1 dipilih)

**Files:** Ditentukan pemetaan B1 yang Ten pilih (amendemen plan ini sesudah B1).

**Interfaces:**
- Consumes: pemetaan B1 yang Ten pilih + aset `docs/branding-finto-os/`.
- Produces: shell Ekasa Desk ber-branding Finto OS/Fino sesuai pemetaan yang dipilih.

- [ ] **Step 1: Tulis langkah implementasi dari pemetaan yang dipilih.** Satu permukaan = satu langkah dengan hasil yang bisa dicek (file + nilai persis dari pemetaan B1). Bila pemetaan butuh tes (mis. tema baru di `ALLOWED_THEMES`), tulis tes gagal dulu mengikuti pola TDD plan ini.
- [ ] **Step 2: Implementasi minimal per permukaan.** Hanya permukaan yang Ten pilih — jangan tambah permukaan lain.
- [ ] **Step 3: Verifikasi visual via browser.** Buka Ekasa Desk di bench PC: tiap permukaan yang diubah dicek tampilannya (logo, warna, maskot) + modul/bidang tidak berubah (bootstrap tetap 17 modul, 4 bidang aktif).
- [ ] **Step 4: Commit.**

```bash
git add <file-file dari pemetaan B1 yang Ten pilih>
git commit -m "feat(desk): terapkan branding Finto OS/Fino di Ekasa Desk"
```

---

## Self-Review (dilakukan penulis plan, 19 Nov 2026)

1. **Spec coverage:** Peta §2 (Lapis B Purchasing — 4 kandidat) → Task 1–3 + keputusan RFQ dipin dengan alasan + tes. Peta §3 (pekerjaan per modul 8 langkah) → tiap task memuatnya (allowlist+migrate, katalog, bidang, tes, mock, verifikasi, commit; handler cabang TIDAK — sesuai keputusan). Peta §7 urutan (Lapis A dulu, lalu 1 bidang Purchasing) → dipatuhi, Fase 2 dimulai sesudah Lapis A selesai. Peta §9 keputusan Ten → semua masuk Global Constraints (read-only, agen ikut dibuka tanpa cabang baru, laporan keuangan bukan bagian plan, HRMS tunda, branding bersamaan). Daftar tugas Fase 2 (3 modul + RFQ dicatat) → tercakup. Satu yang TIDAK dicakup plan ini dan dicatat sebagai non-scope: laporan keuangan sebagai modul Desk (keputusan Ten §9.4 "Ya") — itu scope terpisah, direncanakan belakangan, bukan diam-diam dimasukkan ke Fase 2.
2. **Step scan:** Tiap step satu aksi dengan hasil yang bisa dicek. Nilai yang dipin (field, filter, kartu, label) tertulis eksplisit per task; tidak ada "TBD" kecuali Task B2 — dan itu bukan kekosongan, melainkan gate yang didokumentasikan (langkah B2 ditulis dari pemetaan B1 sesudah Ten memilih; eksekutor dilarang mengarang pemetaan).
3. **Type consistency:** Nama key/kartu konsisten lintas task: `purchase_order`/`purchase_receipt`/`supplier_quotation`; kartu modul `count`/`total`; kartu bidang `po_count`/`po_total`, `pr_count`/`pr_total`, `sq_count`/`sq_total`; grup `"Purchasing"` di semua entri; `base_filters {"docstatus": 1}` di semua modul.
4. **Review Focus:** Kelima baris punya tes penambat di task pemiliknya (migrate → Task 1 Step 3+7; tes penolak PO → Task 1 Step 1; search nama tampilan → Task 1–3 Step 1; base_grand_total → Task 1–3 Step 1; retur/kedaluwarsa → Task 2–3 Step 1).
5. **Proportion:** Plan ini sebanding dengan plan Lapis A (3 modul + branding vs 6 modul). Blok kode hanya untuk perintah tes/commit dan satu pola tes — badan implementasi tidak dituliskan, hanya nilai yang dipin dan tes yang membuktikannya.
