# Peta: Tampilkan Semua Modul di Ekasa Desk

**Tanggal:** 16 Nov 2026 (malam)
**Instruksi atasan (Pak Oscar, WhatsApp 19:34):** "sam, ini kok baru ada sales finance? terakhir yang aq bilang km, ditampilin aja semua yang kita bisa. kan fiturnya sudah ada semua"
**Fokus seminggu ke depan (Ten, 19:58):** kerjakan yang dibilang Pak Oscar — branding Finto OS/Fino + tampilkan semua modul.
**Sifat dokumen ini:** investigasi saja. Tidak ada kode yang diubah, tidak ada tes yang dijalankan.
**Repo yang dibaca (read-only via SSH):** `~/mybench-v16/apps/aios_v1`, branch `feat/plugin-mcp-manager`, HEAD `30d9e5e`. ERPNext 16.34.2. App terpasang: frappe, erpnext, aios_v1, ekasa_logbook.

---

## 0. Ringkasan eksekutif

1. **Yang tampil hari ini:** 2 bidang aktif (Sales, Finance), 8 modul. Ini yang dilihat Pak Oscar di screenshot.
2. **"Semua" itu tiga lapis, bukan satu:** (a) 6 DocType yang SUDAH diizinkan tapi belum ditampilkan — ini yang paling murah; (b) 9 bidang "planned" yang sudah disiapkan kodenya tapi kosong — ini kerjaan menengah per modul; (c) HRIS + Penggajian — ini TIDAK BISA tanpa pasang aplikasi HRMS baru.
3. **Klaim "fiturnya sudah ada semua" tidak sepenuhnya benar.** Yang sudah ada: izin baca 14 DocType + 8 laporan keuangan (sisi agen) + 9 bidang planned kosong. Yang belum ada: halaman detail dokumen, draf/aksi untuk modul selain Sales Order/Quotation, dan seluruh DocType payroll (tidak ada di site).
4. **Menampilkan modul ≠ sekadar toggle tampil.** Per modul (preseden Quotation, commit `d8ab5aa`): entri katalog + daftar bidang + (bila DocType baru) izin + migrate + update tes + verifikasi live. Dan satu kopling penting: **DocType yang masuk `ERP_CLIENT_DOCTYPES` otomatis bisa dibaca agen** (Sales & Finance) — tampil di Desk dan bisa dibaca agen itu satu paket, tidak bisa dipisah.
5. **Koreksi penting soal referensi branding:** menu di `menu-catalog.ts` referensi itu menu produk SEKOLAH (PPDB, Murid, SPP, Honor) — bukan daftar modul AIOS, jangan disalin. Video booting itu boot produk SPI, bukan boot AIOS.

---

## 1. Yang ADA hari ini di Ekasa Desk

### 1a. Katalog modul — `aios_v1/lib/desktop_modules.py` (8 modul)

| # | key | Modul (DocType) | Grup |
|---|---|---|---|
| 1 | `sales_invoice` | Sales Invoice | Sales |
| 2 | `sales_order` | Sales Order | Sales |
| 3 | `quotation` | Quotation | Sales |
| 4 | `customer` | Customer | Sales |
| 5 | `item` | Item | Sales |
| 6 | `purchase_invoice` | Purchase Invoice | Finance |
| 7 | `payment_entry` | Payment Entry | Finance |
| 8 | `supplier` | Supplier | Finance |

Semua modul read-only (list + kartu hitung + filter + search). Tidak ada halaman detail dokumen (lihat §5).

### 1b. Bidang (domain) — `aios_v1/lib/desktop_domains.py` (11 bidang)

Aktif (2):

| Bidang | Modul | Kartu KPI |
|---|---|---|
| `sales` — Sales | 5 modul di atas | Invoice bulan ini, Order terbuka, Piutang outstanding, Customer aktif |
| `finance` — Finance | 3 modul di atas | Hutang outstanding, Total pembayaran, Jurnal tercatat, Supplier aktif |

Planned — sudah ada key, ikon, dan `color_token`, tapi modul dan kartu KOSONG (9):

| Bidang | Keterangan |
|---|---|
| `purchasing` — Purchasing | kosong |
| `inventory` — Inventory | kosong |
| `manufacturing` — Manufacturing | kosong |
| `projects` — Projects | kosong |
| `crm` — CRM | kosong |
| `assets` — Assets | kosong |
| `support` — Support | kosong |
| `quality` — Quality | kosong |
| `accounting` — Accounting | 3 modul (Journal Entry, GL Entry, Account) + 4 kartu |

Catatan: **tidak ada bidang HR** — bahkan sebagai "planned" pun tidak ada. "Akuntansi & HRIS" dari log booting tidak punya wadah di katalog bidang saat ini.

### 1c. Izin baca yang SUDAH ada — `aios_v1/permissions.py`, `ERP_CLIENT_DOCTYPES` (14 DocType)

Quotation, Sales Order, Sales Invoice, Purchase Invoice, Delivery Note, Payment Entry, Journal Entry, GL Entry, Customer, Supplier, Item, Item Price, Company, Account.

Peran `AIOS Client`: read + report saja (`ERP_CLIENT_PERMS`), di-scope ke company aktif lewat `permission_query_conditions` / `has_permission`. `ensure_aios_permissions()` memasang Custom DocPerm saat install/migrate.

**Dari 14 ini, 1 belum tampil sebagai modul (peluang termurah, §3a):** Company. (Delivery Note, Journal Entry, GL Entry, Item Price, Account sudah tampil di Lapis A — Task 1–5.)

### 1d. Sisi agen (yang ikut kebuka kalau modul ditambah)

- Agen di aplikasi (bootstrap `agents`): hanya 2 cabang aktif — Sales & Finance. Registry (`aios_v1/plugin_manager/registry.py`) mendefinisikan 9 cabang (planning, finance, hr, logistics, maintenance, sales, quality, material, manufacturing), tapi `_PRIORITY_BRANCHES = {"finance", "sales"}` mematikan 7 lainnya.
- Konsultasi antar-cabang (`aios_v1/lib/branch_handlers.py`): hanya `sales_consultation` + `finance_consultation`, read-only.
- Tool baca agen (`aios_v1/lib/erpnext_core_data.py`): `erpnext_doc_list` / `erpnext_doc_get` / `erpnext_doctype_schema` dijaga oleh **satu allowlist global** `ERP_CLIENT_DOCTYPES` — tidak ada pembatasan per cabang. Tamu terpisah: hanya Item + Item Price (`GUEST_ALLOWED_DOCTYPES`).
- Laporan keuangan yang sudah diizinkan untuk agen (`aios_v1/lib/erpnext_financial_reports.py`, `ALLOWED_REPORTS`, 8 laporan): General Ledger, Accounts Receivable, Accounts Payable, Trial Balance, Profit and Loss Statement, Balance Sheet, Cash Flow, Sales Analytics. Ini sisi agen saja, bukan modul Desk.
- Draf/aksi (`aios_v1/lib/erpnext_action_drafts.py:76,107`, `draft_manager.py`): CREATE draf **hanya** Sales Order + Quotation (hardcode). Modul baru tampil sebagai read-only kecuali alur draf baru dibangun per DocType.

### 1e. Frontend — generik, tanpa ubah kode per modul

- `frontend/src/views/DesktopView.vue:52` merender ikon bidang dari data bootstrap; `frontend/src/components/module/ModuleWindow.vue` merender modul dari katalog server. Menambah modul/bidang **tidak butuh ubah frontend** (preseden Quotation).
- `frontend/src/api/mock/modules.ts` berisi data mock yang mencerminkan katalog (untuk dev) — perlu disinkronkan labelnya bila katalog berubah (tes `test_frontend_no_hardcode` menjaganya).
- Endpoint Desk (`aios_v1/api/desktop.py`): `bootstrap`, `domain`, `module`, `list`, `search`. `_domain_definition` menolak bidang berstatus `planned` ("Bidang tidak tersedia") — bidang planned tidak bisa dibuka sampai diaktifkan.

---

## 2. Himpunan "semua" — tiga lapis

### Lapis A — Yang sudah diizinkan, tinggal tampilkan (6 DocType)

Delivery Note, Journal Entry, GL Entry, Item Price, Company, Account. Sudah ada di `ERP_CLIENT_DOCTYPES`, Custom DocPerm sudah terpasang, agen sudah bisa membacanya. Pekerjaan per modul: entri katalog + penempatan bidang + tes + verifikasi. **Tidak perlu ubah `permissions.py`, tidak perlu migrate.**

**Temuan riset plan (20:30, terverifikasi dari kode):** Item Price butuh pengecualian di `_server_filters` (`api/desktop.py`) — tanpa itu endpoint list/modul/kartu + ringkasan bidang Sales melempar `ValidationError` (DocType tanpa field `company` di grup Sales, tidak ada di `{Customer, Supplier, Item}`). Satu-satunya perubahan API di Lapis A; aman karena Item Price sudah bisa dibaca tamu. GL Entry dibuat oleh posting dan selalu ber-docstatus 1 — `base_filters` memakai `{"is_cancelled": 0}` (bukan `{"docstatus": 1}`, karena entri batal tetap ber-docstatus 1).

Kandidat penempatan bidang:
- Delivery Note → Sales (dokumen pengiriman penjualan; juga dipakai buying) atau Inventory bila bidang itu diaktifkan.
- Journal Entry + GL Entry + Account + Company → Accounting (bidang sudah aktif sejak Task 3; Journal Entry, GL Entry, Account sudah tampil — Task 3–5; Company berikutnya, Task 6) atau Finance.
- Item Price → Sales (katalog harga; juga sudah bisa dibaca tamu).

### Lapis B — Bidang planned (9 bidang) + DocType ERPNext baru

Setiap bidang planned diisi modul dari DocType ERPNext yang memang ada di site (ERPNext 16.34.2). Kolam kandidat per bidang (DocType utama; angka = jumlah DocType di modul ERPNext):

| Bidang planned | Kandidat modul (DocType ERPNext yang tersedia) | Catatan |
|---|---|---|
| purchasing | Purchase Order, Purchase Receipt, Supplier Quotation, Request for Quotation | Supplier sudah ada di Finance; Purchase Order secara eksplisit DITOLAK di tes katalog saat ini (`test_desktop_modules.py` — `assertNotIn("Purchase Order")`) — menambahkannya berarti membalik keputusan tes itu |
| inventory | Stock Entry, Warehouse, Material Request, Stock Reconciliation, Delivery Note, Item (sudah ada di Sales) | Stock punya 79 DocType; pilih yang transaksional utama saja |
| manufacturing | BOM, Work Order, Production Plan, Job Card | 50 DocType di modul manufacturing |
| projects | Project, Task, Timesheet | 17 DocType |
| crm | Lead, Opportunity, Contact, Address | 31 DocType; Customer sudah ada di Sales |
| assets | Asset, Asset Category, Asset Maintenance | 28 DocType |
| support | Issue, Service Level Agreement | 13 DocType |
| quality | Quality Inspection, Quality Goal | 18 DocType |
| accounting | Journal Entry, GL Entry, Account, Company, Cost Center, Bank Account | Journal Entry, GL Entry, Account sudah tampil di Lapis A (Task 3–5); bidang aktif; Company berikutnya (Task 6) |

Setiap DocType baru di lapis ini butuh: tambah ke `ERP_CLIENT_DOCTYPES` → migrate di bench PC + server testing (pasang Custom DocPerm) → katalog → bidang → tes → verifikasi. Dan otomatis membuka baca agen untuk DocType itu (lihat §4).

### Lapis C — HRIS + Penggajian — TIDAK BISA tanpa pasang aplikasi baru

- Master HR **ada** di ERPNext core v16: Employee, Department, Branch, Designation, Holiday List (`erpnext/erpnext/setup/doctype/`). Modul Employee read-only mungkin.
- **Payroll TIDAK ada:** Salary Slip, Payroll Entry, Salary Structure, Leave Application, Attendance, Shift — semuanya DocType aplikasi HRMS, dan **aplikasi HRMS tidak terpasang** (app terpasang: frappe, erpnext, aios_v1, ekasa_logbook). "Memuat modul Penggajian" di log booting tidak punya DocType pendukung di site ini.
- Bila atasan menghendaki HRIS/Penggajian tampil: pasang aplikasi HRMS (install + migrate + izin + seeder + pengujian) — itu proyek tersendiri, bukan penambahan modul biasa. Perlu keputusan eksplisit.

---

## 3. Pekerjaan per modul / per bidang (dari preseden Quotation `d8ab5aa`)

Per SATU modul baru:

| # | Pekerjaan | File | Keterangan |
|---|---|---|---|
| 1 | (Bila DocType belum diizinkan) tambah ke allowlist | `aios_v1/permissions.py` — `ERP_CLIENT_DOCTYPES` | Lapis A tidak perlu |
| 2 | Migrate agar Custom DocPerm terpasang (bench PC + server testing) | `bench --site <site> migrate` | Lapis A tidak perlu; `ensure_aios_permissions()` |
| 3 | Entri katalog modul: key/label/grup/ikon/doctype + kolom + filter + `filter_fields` + `search_fields` + `order_field` + `base_filters` + kartu hitung | `aios_v1/lib/desktop_modules.py` — `_MODULES` | Perlu riset field per DocType (contoh Quotation: filter pihak pakai `customer_name`/`party_name` karena tidak ada field `customer`) |
| 4 | Masukkan key modul ke bidang + (opsional) kartu KPI bidang | `aios_v1/lib/desktop_domains.py` — `_DOMAINS` | Kartu KPI: DocType kartu harus ada di allowlist; field kartu divalidasi ke meta DocType di `_domain_definition` |
| 5 | (Bila perlu konsultasi agen lintas cabang) handler cabang baru | `aios_v1/lib/branch_handlers.py` | Saat ini hanya Sales & Finance |
| 6 | Update tes: daftar key eksak + grup eksak; hitung planned berkurang bila bidang diaktifkan | `aios_v1/tests/test_desktop_modules.py` (~:189), `test_desktop_domains.py` (:158–163, :330) | Tes meng-assert daftar persis — setiap modul baru WAJIB update tes, kalau tidak tes merah |
| 7 | Sinkron mock frontend (dev parity) | `frontend/src/api/mock/modules.ts` | Bukan fungsional, tapi dijaga tes `test_frontend_no_hardcode` |
| 8 | Verifikasi: `bench run-tests` modul terkait + cek live via browser (bootstrap, list, search, kartu) | — | Cara resmi; verifikasi live dilakukan Ten sendiri lewat Chrome + screenshot (preseden Task 1–3) |

Per SATU bidang planned yang diaktifkan: status `planned` → `active` + minimal 1 modul + kartu KPI (bisa 0 kartu, tapi bidang tanpa kartu tampil kosong) + update tes hitung planned (saat ini `get_planned_domain_count() == 9`, `len(_DOMAINS) == 11`).

**Validasi penjaga (akan gagal bila salah):** `desktop_modules.py:383` (modul di luar allowlist → `RuntimeError`); `desktop_domains.py:211–214` (kartu bidang di luar allowlist → `RuntimeError`); `_validate_domain_catalog` (key/token duplikat, modul tak dikenal, status invalid).

**Estimasi kasar (berdasarkan Quotation: 1 modul ≈ 1 sesi implementasi + 1 sesi verifikasi):** Lapis A (6 modul) ≈ 6× pekerjaan modul, tanpa migrate. Lapis B: tiap bidang ≈ 2–4 modul × pekerjaan modul + keputusan izin. Lapis C: proyek pasang HRMS — belum bisa diestimasi dari peta ini.

---

## 4. Implikasi izin & scope

1. **Tampil di Desk = bisa dibaca agen.** Tidak ada pemisah: `erpnext_doc_list/get/schema` memakai allowlist global yang sama. Menambah Delivery Note ke Desk berarti agen Sales & Finance bisa membaca Delivery Note. Bila atasan hanya mau "tampil" tanpa "agen bisa baca", itu butuh pemisah izin baru (belum ada mekanismenya).
2. **Powers karyawan hari ini hanya Sales and Distribution** (keputusan Ten 13 Nov + `_PRIORITY_BRANCHES`). Menampilkan bidang Purchasing/Inventory/Manufacturing/HR berarti karyawan melihat area itu di Desk (read-only list). Aksi tulis tetap terkunci ke SO/Quotation — tapi ekspektasi pengguna akan naik ("kok cuma bisa lihat?"). Perlu diputuskan: tampil read-only dulu, atau langsung dengan aksi?
3. **Cabang agen tidak ikut membesar otomatis.** Mengaktifkan bidang Inventory di Desk TIDAK mengaktifkan cabang agen `material`/`logistics` — cabang agen diaktifkan lewat `_PRIORITY_BRANCHES` di `registry.py`, dan konsultasi lintas cabang lewat `branch_handlers.py`. Desk dan agen adalah dua permukaan yang harus diputuskan terpisah.
4. **Tamu tidak berubah.** Allowlist tamu terpisah (Item + Item Price). Menambah modul karyawan tidak membuka apa pun untuk tamu.
5. **Scope company:** `permission_query_conditions` membatasi `AIOS Client` ke company aktif untuk DocType berfield `company`. DocType tanpa field `company` (mis. Item Price — per price list; GL Entry punya company) perlu dicek satu per satu saat entri katalog dibuat; `_domain_card_value` menolak DocType kartu tanpa field company (kecuali Customer/Supplier/Item).
6. **Keputusan 13 Nov berubah.** "Stabilkan Sales dulu, jangan buka semua bidang ERP" digantikan instruksi atasan. Keputusan akhir di atasan (Ten berargumen dulu, lalu ikut) — peta ini bahan argumennya, bukan penolakan.

---

## 5. Yang BELUM benar-benar ada (vs "fiturnya sudah ada semua")

| Klaim / harapan | Kenyataan (terverifikasi dari kode) |
|---|---|
| Semua fitur sudah ada | Hanya 8 modul + 9 bidang planned kosong. 6 DocType sudah diizinkan tapi belum tampil. Payroll tidak ada DocType-nya. |
| Modul tampil = fitur lengkap | **Tidak ada halaman detail dokumen sama sekali** — backend tidak punya endpoint detail, frontend hanya `ModuleWindow` list. Setiap modul baru = list-only. Detail adalah scope terpisah (dicatat sebagai follow-up Quotation). |
| Approval bisa dipakai untuk semua modul | Kartu approval tidak menampilkan harga (Harga Satuan + Subtotal "—"); notifikasi approval ke tamu hanya untuk Sales Order (`draft_manager.py:991`); draf CREATE hanya SO/Quotation. |
| HRIS & Penggajian tinggal tampilkan | HRMS tidak terpasang; DocType payroll tidak ada di site. |
| Menu referensi = daftar modul AIOS | Menu referensi adalah produk sekolah (SPI): PPDB, Murid, Akademik, SPP, Honor — produk lain, bukan modul AIOS. |
| Finto OS sudah jadi platform | Finto OS masih rencana (`01_RENCANA_TEKNIS_FINTO_OS.md`, tahap 0–6, status "belum dikerjakan"). Yang ada: snapshot frontend SPI + rencana arsitektur. AIOS memakai shell frontend sendiri, bukan kit Finto OS. |
| Laporan keuangan tampil di Desk | 8 laporan (GL, AR, AP, Trial Balance, P&L, Balance Sheet, Cash Flow, Sales Analytics) hanya tersedia lewat agen, bukan modul Desk. |

---

## 6. Koreksi soal referensi branding (penting — jangan salah pakai)

- **Video demo booting (5,4 dtk, `demo-booting-finto-os.mp4`) adalah boot produk SPI, bukan AIOS.** Frame yang diperiksa: log "[ OK ] Memeriksa koneksi server sekolah / Memuat modul Admisi & Murid / Memuat modul Akademik & LMS / Memuat modul Keuangan SPP / Memuat modul Penggajian", lalu lock screen "19.50 Senin, 16 November". Bukan "AIOS / Akuntansi & HRIS / Keuangan SIP".
- **Baris log booting bersifat per-produk** (hook `finto_os_boot_log`, rencana 01 §5.1). AIOS akan memasok barisnya sendiri bila memakai shell Finto OS.
- **Animasi boot memang sengaja lama** (Ten, 19:56 — seperti boot Windows/OS sungguhan; spesifikasi 02: total 4,2 dtk, tanpa tombol Lewati). Itu keputusan desain, bukan bug.
- **Isi referensi yang relevan untuk AIOS:** palet Finto OS (navy `#0B1F3B`, blue `#0E63FF`, cyan `#00D4C8`, lime `#A7F432`, violet `#8B5CF6`, light `#F3F7FB`), logo Finto OS, gambar maskot Fino (`Logo Finto OS/logo baru/mascot/`), mekanisme menu registry (grup/hub/label per peran), dan rencana platform Finto OS tahap 0–6.
- **Isi referensi yang TIDAK relevan untuk AIOS:** seluruh menu/fitur pendidikan SPI (`menu-catalog.ts`: PPDB, Murid, Kelas, Penilaian, SPP, Honor, Laporan cabang, Master Data sekolah, Portal orang tua/murid) dan DocType `SPI *`.

---

## 7. Usulan urutan (bukan keputusan — untuk Ten/atasan)

1. **Lapis A dulu (6 modul, tanpa migrate):** Delivery Note → Sales; Journal Entry + GL Entry + Account + Company → aktifkan bidang Accounting; Item Price → Sales. Ini jawaban tercepat untuk "kok baru ada sales finance" — bidang menjadi 3 (Sales, Finance, Accounting).
2. **Lalu 1 bidang planned sebagai pola:** Purchasing (Purchase Order + Purchase Receipt + Supplier Quotation) — paling dekat dengan alur Sales yang sudah stabil. Membalik `assertNotIn("Purchase Order")` perlu dicatat sebagai keputusan.
3. **Baru bidang lain** sesuai prioritas atasan (Inventory / Manufacturing / Projects / CRM / Assets / Support / Quality).
4. **HRIS/Payroll diputuskan terpisah:** pasang HRMS atau tunda — jangan dicampur ke gelombang modul biasa.
5. **Detail dokumen + harga di kartu approval** tetap sebagai follow-up terpisah (sudah dicatat di daftar kekurangan Ekasa Desk — file follow-up, masih di workspace Muse).

---

## 8. Pertanyaan terbuka untuk Ten / Pak Oscar

1. **Daftar "semua" yang persis:** Lapis A saja, Lapis A + sebagian bidang planned, atau harfiah semua termasuk HR/Payroll? Bidang mana dulu?
2. **Read-only dulu atau langsung dengan aksi?** Modul baru tampil sebagai list read-only (seperti Quotation) atau atasan mengharapkan bisa buat/approve dari Desk juga (itu alur draf baru per DocType)?
3. **Apakah agen ikut dibuka?** Tampil di Desk otomatis membuka baca agen untuk DocType itu. Apakah cabang agen baru (mis. `material`, `hr`, `planning`) juga diaktifkan, atau agen tetap Sales + Finance?
4. **Apakah 8 laporan keuangan ikut tampil sebagai modul Desk**, atau tetap agen-saja?
5. **HRIS/Pengajian:** pasang aplikasi HRMS, atau tunda? (Tanpa HRMS, "Penggajian" tidak bisa tampil sebagai data nyata.)
6. **Scope company untuk DocType tanpa field company** (mis. Item Price): bagaimana pembatasannya?
7. **Branding (Fino/Finto OS shell) dikerjakan bersamaan atau sesudah modul?** Keduanya masuk fokus minggu ini; urutannya perlu diputuskan.

---

## 9. Keputusan Ten (16 Nov 20:11, saat baca peta)

1. **Scope "semua": harfiah semua modul bawaan ERPNext** (Lapis A + 9 bidang planned). HRIS/Payroll TIDAK dulu — tanpa HRMS memang tidak bisa tampil, jadi menunda itu satu-satunya opsi benar (Ten: "Aman kan?" → ya, aman).
2. **Aksi: read-only dulu; aksi hanya Sales + Finance (Ten, 20:14).** Modul baru tampil sebagai list read-only. Aksi (buat dokumen baru, setujui/tolak draf, tombol Sudah Bayar, submit/cancel, edit/hapus) tetap hanya di Sales + Finance — dua bidang ini yang "digaspol sampai pucuk tertinggi".
3. **Agen ikut dibuka: Ya.**
4. **Laporan keuangan tampil sebagai modul Desk: Ya** (Ten: "Sebaiknya iya").
5. **HRMS: Tunda dulu.**
6. **Scope company untuk DocType tanpa field company: Ten masih bingung (20:14).** Penjelasan sederhana: hampir semua dokumen punya kolom `company`, jadi gampang dibatasi ke company aktif. Yang tidak punya cuma Item Price — tapi Item Price itu sudah bisa dibaca tamu sekalipun (`GUEST_ALLOWED_DOCTYPES`), jadi untuk karyawan tidak perlu dibatasi lagi. Dicek per-DocType saat implementasi; bukan keputusan yang perlu dijawab sekarang.
7. **Branding bersamaan dengan modul: Ya** — supaya frontend tidak ditulis 2x (Ten: "daripada klo ntar setelah modul atau ngebuka semua bidang, ntar nulis frontend 2x dong").

---

## Lampiran — file yang dibaca

- `docs/branding-finto-os/referensi-asli/referensi UI finto-os/01_RENCANA_TEKNIS_FINTO_OS.md`
- `.../02_SPESIFIKASI_TAMPILAN_FINTO_OS.md`, `03_INVENTARIS_FILE.md`, `04_SELISIH_FRONTEND_FINTO_EDU_VS_SPI.md`
- `.../kode-snapshot/spi_fintoedu/frontend/src/assets/data/menu-catalog.ts` (34 fitur, 9 hub, 11 grup — produk sekolah)
- `.../kode-snapshot/spi_fintoedu/frontend/src/assets/data/menu-items.ts`
- `.../kode-snapshot/spi_fintoedu/frontend/src/features/desktop/pages/BootScreen.vue` (LOG 7 baris SPI, durasi 4,2 dtk)
- `docs/branding-finto-os/demo-booting-finto-os.mp4` (5,4 dtk; frame diperiksa: boot SPI + lock screen 19.50)
- Via SSH read-only, `~/mybench-v16/apps/aios_v1`: `aios_v1/permissions.py` (`ERP_CLIENT_DOCTYPES`, 14), `aios_v1/lib/desktop_modules.py` (8 modul), `aios_v1/lib/desktop_domains.py` (2 aktif + 9 planned), `aios_v1/lib/branch_handlers.py` (2 handler), `aios_v1/lib/erpnext_core_data.py` (allowlist agen), `aios_v1/lib/erpnext_financial_reports.py` (`ALLOWED_REPORTS`, 8), `aios_v1/lib/tool_registry.py` (`GUEST_ALLOWED_TOOLS` 5, `DRAFT_TOOLS` 4), `aios_v1/plugin_manager/registry.py` (9 cabang, 2 aktif), `aios_v1/api/desktop.py` (`bootstrap`/`domain`/`module`/`list`/`search`), `aios_v1/tests/test_desktop_modules.py` (~:189 daftar eksak), `aios_v1/tests/test_desktop_domains.py` (:158–163, :330), `aios_v1/tests/test_client_seeder_contract.py` (12 DocType — daftarnya tidak mencakup Quotation + Item Price).
- `~/mybench-v16/apps/erpnext/erpnext/`: modul selling/buying/stock/manufacturing/projects/crm/assets/support/quality_management + `setup/doctype/employee` (ada) vs DocType payroll (tidak ada).
