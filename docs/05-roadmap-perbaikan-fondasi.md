# Roadmap Perbaikan AIOS V1

**Status:** revisi 11 — **`#0` SELESAI**; **Tahap C SELESAI** (ownership per `User`, hook izin, `Pending Action Draft`; 8/8 test isolasi hijau). `#1` tahap A selesai di `fix/security-emergency`. Berikutnya: **#4a** (hapus `AIOS Tenant` + sisa relasi `tenant`). Dokumen telah diaudit lintas-dokumen dan diverifikasi terhadap source Frappe 16 / ERPNext 16.
**Basis:** `develop` @ `ac98ca1` (2026-09-11)
**Dibuat:** 2026-10-19 · **Direvisi:** 2026-10-21 (revisi 11 — Tahap C selesai; lihat §#4a)
**Repo:** `git@github.com:Tenshi1308/aios-frappe-16.git` (origin) — upstream = `/home/samue/mybench/apps/aios_v1`

> **Prinsip kerja:** setiap tahap dan setiap fitur **wajib punya script test**.
> Tidak ada branch yang dianggap selesai tanpa test yang membuktikan klaimnya.
> Lihat **§6 Strategi Test** untuk peta branch → file test → apa yang dibuktikan.
>
> Semua temuan di §4 adalah hasil pembacaan statis + verifikasi `file:line`.
> Test runtime penuh **belum** dijalankan (lihat §10 Batasan Lingkungan).

---

## 0. Apa Itu AIOS (konteks produk)

**AIOS adalah workspace AI untuk kerja bisnis** — wrapper SaaS, bukan alat coding.
Target pasar: perusahaan bisnis.

| Harness coding | AIOS |
|---|---|
| tool: read/write file, bash, grep | tool: baca Sales Order, cek stok, analisis GL |
| skill: cara refactor, konvensi repo | skill: SOP finance, prosedur HR (86 file `.md`) |
| sandbox: batasi filesystem & shell | sandbox: batasi akses data bisnis klien |
| harness CLI (single user) | SaaS multi-tenant (`1 Client = 1 Site`) |

**Konsekuensi framing ini (penting untuk prioritas):**

1. **Tool layer + skills adalah PRODUKNYA, bukan fitur tambahan.** Yang saya sebut
   "70% kode mati" di §1 sebenarnya adalah inti produk. Yang 30% hidup (chat, routing,
   auth) hanya wadahnya. Karena itu **#7 dan #8 naik prioritas** — itu membuat
   produknya ada, bukan hiasan.
2. **Yang dipertaruhkan data keuangan klien.** Kalau LLM menyimpang, dampaknya bukan
   "kode rusak" tapi "angka salah dilaporkan ke direktur". Sandbox LLM jadi kritis,
   bukan opsional.
3. **Multi-tenant di level site (`1 Client = 1 Site` / `dns_multitenant=True`), dan di dalam site berbasis `User` (tanpa `AIOS Tenant`).** Setiap perusahaan klien mendapatkan *instance site* dan database MariaDB terpisah. Bila ada pendaftaran mandiri (*self-registration*), akun berstatus **`Pending Provisioning`** karena pembuatan site baru tidak bisa instan dalam 1 HTTP request. Di dalam setiap site, seluruh atribut pengguna & kuota melekat langsung pada **`User`** (dan default tingkat site di **`AIOS Setting`**), sehingga DocType `AIOS Tenant` dihapus sepenuhnya (§5 #4a/#4b).

---

## 1. Ringkasan Angka

| Metrik | Nilai | Catatan |
|---|---|---|
| File Python | **161** (18.885 LOC) | 160 modul unik (`131` non-`__init__` + `29` `__init__.py`) — `api` muncul 2× (`api.py` + `api/`) |
| Modul LIVE | ~58 (5.713 LOC) | ⚠️ **perkiraan**, bergantung pilihan root BFS (§10) |
| Modul MATI | ~102 (13.210 LOC) | ⚠️ **perkiraan**, asumsi sama |
| — `lib/demo_tahap*` | 25 file, 2.546 LOC | |
| — `aios_v1/tests/` | **19** file, 2.936 LOC + **4 test baru** | ✅ **suite terpisah sejak `#0`** (§3k) — bukan lagi "tidak bisa jalan": CI statis `2 skipped/11 xfailed` exit 0, lokal `23 passed/340 skipped` exit 0 |
| — backend tak tersambung | 59 file, 7.728 LOC | |
| Modul gagal import | **11 dari 160** | semua `demo_tahap*`, `chat_completion` hilang |
| Build artifact ter-track | 396 file / 39 MB | 72 direktori build, 126 chunk |
| `frappe.session` dipakai | **0 kali** | mesin otorisasi Frappe tidak aktif |
| `ignore_permissions=True` | 103 kali | |
| `frappe.get_all` vs `get_list` | 30 vs 1 | |
| Doctype | **13 unik** di repo (12 awal + `Pending Action Draft` Tahap C) | 14 file JSON saat ini (2 duplikat luar-package), semuanya hanya permission `System Manager` |
| CI | **tidak ada** | |
| `ruff` di env | **tidak ada** (bisa di-install, terverifikasi) | |
| Temuan keamanan | **12 → 18** | +6 dari review eksternal (N1–N6) |
| Sandbox LLM | **4 aman, 6 belum/celah** | L1–L4 aman; **L5** (`aggregate.fn` tanpa whitelist) + **L6** (guard read-only lemah) + L7–L10 belum |
| Skrip seed PoC ERPNext | **560 baris, belum dijalankan** | `aios_v1/setup_poc/seed_erpnext_demo.py` syntax OK, nol silent error (`frappe.log_error` + `raise`), resolusi dinamis `Country`/`Currency`/COA (#4d / L10) |

**Kesimpulan:** hanya ~30% kode yang tersambung. 70% yang mati berisi aset mahal
(9 cabang tools ERP 5.235 LOC, 3 adapter DB 1.075 LOC, 86 file SOP 171 KB,
swarm/ledger 365 LOC).

---

## 2. Keputusan yang Sudah Dikunci

| Keputusan | Isi | Dampak |
|---|---|---|
| **Static export** | Sudah ditinggalkan; frontend jalan standalone | 396 file artifact = beban mati, aman dihapus |
| **Port server** | Frappe 8083, frontend 8084, **tidak ada 8085** | `8085` di `auth.py` = kode mati |
| **Port lokal** | Frappe 8001, frontend bebas | `8083` di `next.config.ts` salah sasaran di lokal |
| **Konsep Multi-Tenant** | **`1 Client = 1 Site` (`dns_multitenant`)** | Setiap perusahaan klien memiliki site & DB terpisah; tidak ada pencampuran data klien di 1 DB |
| **DocType `AIOS Tenant`** | **Dihapus / Tidak dipakai** | Karena 1 site = 1 klien, semua atribut user & kuota langsung ditaruh di **`User`** (+ default site di **`AIOS Setting`**) |
| **Self-Registration** | **Status `Pending Provisioning`** | Pendaftaran mandiri di `/aios/register` tidak bisa langsung masuk instance site siap pakai |
| **Batas user per site** | Ya, dibutuhkan (`AIOS Setting.max_users`) | Validasi di `User.before_insert` / `User.validate` |
| **Dua UI terpisah** | Ya (client + admin) | Pemisah = **Role**, bukan port/host |
| **Klien pakai desk ERPNext?** | **Tidak** — hanya UI AIOS | Klien = `Website User` (`desk_access = 0`) |
| **Persona & Kuota per-user** | Menempel langsung di `User` | Custom Field di `User` (`aios_persona`, `aios_status`, `aios_company_name`, `aios_token_limit`, `aios_tokens_used`) |
| **Role & izin** | Pakai bawaan Frappe | Buang session/auth custom |
| **Daftar cabang hardcoded** | Tidak masalah | `registry.py` biarkan |
| **Aturan bisnis di kode** | Harga token, threshold, limit | **Tetap di kode**, jadi konstanta bernama satu tempat |
| **`intelligence_chat` page** | Hapus | Tidak pernah dipakai |
| **`aios_portals` page** | Hapus | URL port hardcoded, usang |
| **Data tenant lama** | Testing saja | **Tidak perlu migrasi data** (namun **kode hidup** yang masih mereferensikan `AIOS Tenant` — yakni `dispatcher.py:208,255,258,708,749,751,802,932` & SQL mentah `FROM \`tabAIOS Tenant\`` di `lib/monitoring_service.py:281` — wajib diganti/dibersihkan di `#4a`/`#4b` bersamaan dengan penghapusan `AIOS Tenant`) |
| **Judul halaman per role** | `role_home_page` **tidak** dipakai Next.js | Hanya memengaruhi web Frappe; Next.js baca `home_page` dari response login |

### 2b. Keputusan dari revisi 3–5 (Termasuk Arahan Atasan)

| Keputusan | Isi | Dampak |
|---|---|---|
| **Backend PoC** | **ERPNext dulu**, bukan adapter DB klien | PoC jalan minggu ini; menghapus N5, A5, A6, S11 dari jalur kritis |
| **Adaptasi DB klien** | Tetap tujuan akhir (arahan atasan) — **ditunda**, bukan dibatalkan | Arsitektur tool disiapkan agar 2 driver berdampingan |
| **Peran ganda ERPNext** | (1) jalur cepat PoC; (2) **target uji adapter** — MariaDB ERPNext punya skema nyata | Adapter DB diuji ke data nyata tanpa DB klien terpisah |
| **Multi-tenant (`1 Client = 1 Site`)** | **Level Site (`dns_multitenant=True`)**, bukan `1 Client = 1 Company` di 1 site | Menghilangkan kebutuhan `AIOS Tenant` & `User Permission` lintas PT; di dalam site cukup isolasi per `User` |
| **Nama role** | `AIOS Admin` + `AIOS Client` (bukan `DEVELOPER`/`CLIENT`) | Prefiks `AIOS ` mencegah bentrok dengan role app lain |
| **Cara buat Custom Field & Role** | **Di-script di Python pada hook `after_install` & `after_migrate` di `hooks.py` (BUKAN `fixtures`)** | Memakai `create_custom_fields(custom_fields, update=True)` resmi Frappe; terverifikasi wajib karena `User` ada di `core_doctypes_list` (`frappe/model/__init__.py:103-122`) sehingga UI Customize Form menolak `User` (`custom_field.py:281-282`) |
| **Administrator** | **Tidak dibatasi, tidak disentuh** | Sudah punya segalanya; menambah permission row = tidak berguna |
| **Larangan mutasi `tabDocField`** | **Dilarang `frappe.get_doc("DocType", "User").append("fields", ...)`** | Wajib menulis ke `tabCustom Field` lewat `create_custom_fields` di `after_install` & `after_migrate` |
| **Data demo** | Generator resmi ERPNext, Company `PT Demo AIOS` | Bukan mock di kode — data hidup & bisa di-query |
| **5.235 LOC tool lama** | **Jangan dirombak sekarang** | Ditunda sampai PoC satu cabang terbukti |
| **Cabang PoC pertama** | **finance** (diikuti **sales**) | Data ERPNext `accounts` & `selling` paling kaya; mock lama paling banyak di situ |

### Prinsip pagar

1. **Jangan tulis apa yang Frappe sudah punya** — auth, session, role, permission,
   password, REST, lockout, rate limit, `Error Log`.
2. **Batas baris di `hooks.py` + `permission_query_conditions` + `check_permission`**,
   bukan cek manual per query.
3. **Konstanta bisnis di kode (satu tempat, bernama); kredensial & path environment
   di `frappe.conf`; relasi/konfigurasi domain di database.**
4. **Custom Field & Role wajib di-script di `after_install` dan `after_migrate` (bukan `fixtures` dan bukan mutasi `tabDocField`).**
   - Jangan menaruh Custom Field di `fixtures` JSON, dan **dilarang keras** memutasi DocType inti via `frappe.get_doc("DocType", "User").append("fields", ...)` (`seed_auth.py:5-14`, `fix_perms.py:10-27`, `migrate_schema.py:8-15`).
   - Gunakan primitif resmi `create_custom_fields(custom_fields, update=True)` (`frappe/custom/doctype/custom_field/custom_field.py:322-350`) yang dipanggil otomatis pada `after_install` dan `after_migrate` di `hooks.py`.
5. **Administrator tidak dibatasi; `AIOS Admin` bukan Administrator.** Jangan tambahkan
   `Administrator` ke permission role AIOS. Aturan ini mengikat, dan versi normatifnya
   ada di `docs/03` §2.1 — roadmap ini hanya merujuk, bukan asal aturannya.
6. **Zero Silent Error — wajib `frappe.log_error` + Fail Loudly.** Dilarang keras
   menulis `except Exception: pass` / `continue` / `return None` demi "asal tidak crash".
   Setiap blok `except` yang menangkap error untuk mengembalikan JSON terstruktur
   (`dispatcher.py`, `tool_registry.py`, `query_engine.py`, `adapters/*`, `llm_client.py`)
   **wajib** memanggil `frappe.log_error(title=..., message=frappe.get_traceback())`
   supaya tercatat di doctype **`Error Log`** bawaan Frappe untuk debugging. Dijaga
   otomatis di CI via rule `ruff` (`S110`, `BLE001`, `B904`) dan cek AST di `test_repo_hygiene.py`.
7. **Jangan Hardcode Data/Konfigurasi yang Bisa Di-resolve Dinamis (di seluruh file, bukan hanya test).**
   Gunakan primitif resmi Frappe/ERPNext & relasi DB: mis. mata uang dari
   `frappe.db.get_value("Country", country, "default_currency")`, template COA dari
   `get_charts_for_country(country)`, `Company` aktif di site dari `AIOS Setting.default_company` / `Global Defaults`, dan kuota token default dari `AIOS Setting.default_user_token_limit`.
   Bila konfigurasi belum di-set, **tolak eksplisit (`frappe.throw(...)`)**, jangan
   memberi fallback angka/string gaib (`else 2`, `"PT Demo AIOS (Demo)"`, dsb.).

---

## 3. Riwayat Koreksi

Semua koreksi yang terjadi selama audit. Dicatat supaya tidak diulang sebagai asumsi.
Kolom "Sumber" membedakan kesalahan penyusun (AI) vs temuan reviewer.

### 3a. Koreksi penyusun (audit awal)

| Klaim awal | Status | Bukti | Sumber |
|---|---|---|---|
| `pymysql`/`psycopg2` tidak ada → `data_access` fatal | ❌ **SALAH** | Semua ada, `Required-by: frappe`. Turun: fatal → **rapuh** | Penyusun |
| Dua salinan `intelligence_chat` divergen | ❌ **SALAH** | SHA256 identik (JS & CSS), diff JSON kosong. Artefak perintah sendiri | Penyusun |
| `portal_from_request` bisa dipaksa via `Host: x:8085` | ❌ **SALAH** | `8085` hanya di `auth.py`; ada `expected_role` → `403`. **Kode mati** | Penyusun |
| Kredensial terekspos | ✅ Belum, tapi rapuh | `Password` ter-mask; response login bersih; artifact bersih. **Tapi** `password_hash` = `Data` → ranjau | Penyusun |
| COA template `"Standard"` untuk Company demo | ❌ **SALAH** | Nilai `"Standard"` itu **karangan penyusun**. Nilai valid = field `name` di `erpnext/.../chart_of_accounts/verified/*.json`; untuk Indonesia: **`"Indonesia - Chart of Accounts"`** (`id_chart_of_accounts.json`) | Penyusun (revisi 3) |
| Penyusun membocorkan `db_password` ke output | ⚠️ **TERJADI** | Perintah verifikasi mencetak `db_password` site ke log sesi. Sudah dirotate pemilik. Pelajaran: field sensitif **wajib difilter** dari output, termasuk saat "sekadar cek" | Penyusun (revisi 3) |

### 3b. Koreksi dari review eksternal (Claude Sonnet 5.5)

| Klaim roadmap | Status | Bukti terverifikasi |
|---|---|---|
| CORS di `dispatcher.py:129-137` | ❌ **SALAH** | CORS sebenarnya di **`111-120`** (`def add_cors_headers`). `129-137` = `res.set_cookie` |
| `permission_query_conditions` dikomentari di `hooks.py:139-146` | ❌ **SALAH** | Sebenarnya **`166-171`**. Dan 139-146 = boilerplate blok **Build** bawaan Frappe, bukan hook yang sengaja dimatikan |
| Aksi #1 `password_hash` → fieldtype `Password` | ❌ **BERBAHAYA** | `_save_passwords` (`base_document.py:1349-1369`) menulis placeholder `"*****"` **sebelum** `db_insert`; `frappe.db.get_value` **tidak punya** penanganan Password (body `database.py:517-595` nol referensi). → `verify_password(pw, "*****")` selalu `False` → **semua login gagal**. **Aksi dihapus** |
| "Semuanya `Link(AIOS Tenant)` → User Permission bekerja" | ❌ **SALAH untuk Message** | `AIOS Message` hanya punya `conversation → Link(AIOS Conversation)`. **Tidak ada link ke Tenant** → butuh hook join |
| `User Permission` membatasi baris | ⚠️ **FAIL-OPEN** | `permissions.py:359-362`: `if not user_permissions: return True`. → **wajib** buat User Permission otomatis |
| `permission_query_conditions` cukup | ❌ **tidak cukup** | Tidak mencakup `get_doc`. `check_permission` default `None` (`document.py:178-186`) |
| "CSRF framework yang urus" (#4) | ⚠️ **menyesatkan** | `auth.py:81-97`: validasi **dilewati** kalau sesi tak punya `csrf_token`; token dibuat di `sessions.py:197-205` saat render desk, sesi login API tidak pernah membuatnya |
| `rate_limit` bisa dipasang di #1 | ❌ **tidak bisa** | `rate_limiter.py:104`: "**Decorator** to rate limit an endpoint" — butuh `@frappe.whitelist`, tidak jalan di `before_request` |
| `role_home_page` berguna | ⚠️ **tidak untuk Next.js** | Hanya memengaruhi halaman web Frappe |
| A9: "10 file 0 byte" (vs #2: "9") | ❌ **SALAH** | `find managers -name '*.py' -size 0` → **9** |
| §1: 160 modul / 18.923 LOC | ⚠️ **meleset** | **161** file / **18.885** LOC (160 modul unik) |

### 3c. Koreksi severity

| Temuan | Sebelum | Sesudah | Alasan |
|---|---|---|---|
| S3, S5 | Tinggi | **Kritis** | N2 (tulis+riwayat ke tenant lain) dan N3 (`else 1` jalur **baca**) |
| S6 (CORS) | Keamanan | **Rendah-menengah** | Frontend pakai proxy Next.js → same-origin; `SameSite=Lax` menahan |
| S7 (CSRF) | Keamanan | **Rendah-menengah** | `SameSite=Lax` mencegah CSRF klasik; hilang sendiri di #4b |
| A8 (dispatcher di semua request) | Arsitektur | **Rendah** | `:159-176` langsung `return` untuk request non-AIOS |

### 3d. Klaim yang tetap rapuh (belum terbukti bocor)

`portal_from_request` memakai `body.get("portal")` — nilai **dikontrol client**.
Aman hari ini karena ada `expected_role` check, tapi penentu otorisasi sebaiknya dari
**role user**, bukan input request.

### 3e. Koreksi karakterisasi (revisi 3)

| Klaim penyusun | Status | Bukti |
|---|---|---|
| "`query_engine` menyusun SQL dari input LLM" (kesan: bebas) | ⚠️ **TERLALU KASAR** | Verifikasi: **tidak ada tool** yang menerima SQL mentah (nol parameter `sql`); `fields`/`filters`/`order_by` divalidasi ke mapping kanonik; **value parameterized** (`query_engine.py:110-127`). Arsitekturnya **lebih baik** dari kesan itu — LLM menyebut konsep bisnis, kode menerjemahkan |
| Nol akses OS dari LLM | ✅ **BENAR** | Verifikasi: nol `eval`/`exec`/`__import__`/`importlib`/`os.system`/`subprocess` di `lib/tools/*`, `tool_registry.py`, `data_access_agent.py` |
| "70% kode mati" | ⚠️ **DIKOREKSI FRAMING** | Setelah framing produk (§0), 70% itu **bukan kode mati — itu produknya** (tool + skills). Yang mati hanya *sambungannya*. Karena itu #7/#8 naik prioritas |

### 3f. Koreksi dari review eksternal putaran 2 (revisi 4)

| Klaim revisi 3 / reviewer | Status | Bukti terverifikasi |
|---|---|---|
| `setup_demo_data` membuat `Journal Entry` dari `demo_data/journal_entry.json` (#4d) | ❌ **SALAH** | `erpnext/hooks.py:100-103` hanya mendefinisikan `demo_transaction_doctypes = ["purchase_order", "sales_order"]`. File `demo_data/journal_entry.json` adalah dead file di ERPNext (memakai customer `"ABC Enterprises"` yang tidak ada di `customer.json`). `Journal Entry` = 0; `Payment Entry` terbuat dari `convert_order_to_invoices()` |
| `setup_demo_data` melempar exception bila gagal (#4d) | ❌ **RAWAN GAGAL** | `erpnext/setup/demo.py:23-32` membungkus seluruh isi dalam `try ... except Exception:` yang melakukan `frappe.db.rollback(save_point="demo_data")` + `frappe.log_error()` **tanpa re-raise**. Ditambah re-run gagal di `create_demo_company()` (`demo.py:86` `DuplicateEntryError`), dan warehouse ke-4 butuh `Warehouse Type = "Transit"` (`company.py:390`). **Diperbaiki di `seed_erpnext_demo.py`** |
| Buat Role `AIOS Client` di Desk UI sudah otomatis `Website User` (#4b) | ⚠️ **RAWAN GAGAL** | `frappe/core/doctype/role/role.json:33-42` memiliki default `desk_access = 1`, dan `User.validate` (`user.py:415`) mengeset `user_type = "System User"` bila ada satu saja role dengan `desk_access == 1`. Role `AIOS Client` **wajib** eksplisit `desk_access = 0` |
| CSRF beres otomatis begitu pindah ke `/api/method/login` (#4b/#4c) | ⚠️ **BELUM LENGKAP** | `POST /api/method/login` tidak mengembalikan `csrf_token`, dan `validate_csrf_token` (`auth.py:87`) melewati validasi bila `frappe.session.data.csrf_token` kosong. Perlu endpoint bootstrap `@frappe.whitelist()` / `on_login` hook yang memanggil `frappe.sessions.get_csrf_token()` |
| `User Permission` + konversi 30× `get_all` → `get_list` cukup untuk scoping (#4a) | ⚠️ **RAWAN GAGAL** | (1) `User Permission` standar tanpa `apply_strict_user_permissions` menyisipkan `ifnull(tenant, '')=''` (`db_query.py:1124-1126`) → baris `tenant=NULL` bocor, sehingga `permission_query_conditions` eksplisit tetap wajib untuk semua doctype ber-tenant; (2) konversi buta `get_all` → `get_list` merusak job background tanpa sesi (`draft_manager.py:7`, `telegram_service.py:205,307,332`) dan memotong agregasi (`/api/monitoring/usage` `:708-830`, `query_engine.py:16,22`) ke 20 baris |
| Isolasi site vs `Company` ERPNext di #7 (L7) & #8 | ✅ **DISELESAIKAN (Revisi 5–6)** | Dokumen ERPNext (`Sales Order`, `GL Entry`, `Sales Invoice`) di-scope oleh field `company`. Karena arsitektur menggunakan **`1 Client = 1 Site`** (dan `AIOS Tenant` dihapus), resolusi `allowed_company` di `execute_tool` dan `permission_query_conditions` ERPNext dilakukan di tingkat site via `frappe.db.get_single_value("AIOS Setting", "default_company") or frappe.db.get_single_value("Global Defaults", "default_company")` (lihat #4a & #7 L7) |
| Jalur paralel `#0 → #4d → #7 → #8` tanpa `#1` (§7 & §11) | ❌ **BERBAHAYA** | Menyalakan `#8` sebelum `#1` mengekspos eksekusi tool ERPNext nyata ke `/stream` tanpa sesi (`S5` fallback `company_id = 2`) dan IDOR `conversationId` (`N2`). `#1` **wajib** mendahului `#8` (`#0 → #1 → #4d → #7 → #8`) |
| Klaim reviewer: `execute_read_query` di `mysql_adapter.py` ada di baris `124-127`, bukan `:96` | ❌ **REVIEWER SALAH** | `aios_v1/data_access/adapters/mysql_adapter.py` hanya terdiri dari **109 baris** total; guard `if not clean_sql.upper().startswith(...)` memang berada tepat di **baris 96** (`sqlite_adapter.py` yang di baris 127) |

---

### 3g. Koreksi revisi 7 (verifikasi bench env, 2026-10-20)

Diukur langsung di `~/.mybench-v16` dengan `python -B` (tanpa menulis bytecode) dan `pip index`:

| Klaim revisi 6 | Status | Bukti terverifikasi |
|---|---|---|
| `ruff-0.17.1` untuk #0 | ⚠️ **bentrok** → **DIREVISI 3h** | `.pre-commit-config.yaml:21` memakai `ruff-pre-commit rev: v0.14.10`. Dua versi = dua gate. **Dipin `0.14.10`** (keduanya ada di PyPI). **Revisi 3h membalik keputusan ini:** pakai `0.17.1` (stable latest), bump pre-commit di #3 |
| "CI → `ruff check`, `ruff format --check`, pytest" (#0) | ⚠️ **terlalu dini** | **97 file indent 4-spasi vs 25 file tab** sementara `[tool.ruff.format]` minta tab, dan `aios_v1/api/dispatcher.py` = CRLF. `format --check` **ditunda ke #3** agar baseline 11 gagal tetap terbaca |
| "Install `frappe`" (#0) tanpa menyebut sumbernya | ❌ **celah rencana** → **DIREVISI 3h** | `frappe` di PyPI hanya placeholder **`0.0.1`**; `erpnext` **tidak ada di PyPI**. Wajib dari Git tag + Python 3.14 + `libmariadb-dev`/`libpango`/`libcairo` — ~70 dependency dan 2 dipin ke commit git. **Revisi 3h: CI tidak install frappe sama sekali** (lihat 3h) |
| `erpnext` perlu di-install | ✅ **tidak** | **Nol file** di `aios_v1/` mengimpor `erpnext` (`grep`), jadi CI cukup `frappe` |
| Smoke import butuh DB/site | ✅ **tidak** | `import frappe` sukses tanpa `frappe.init()`; `hooks`, `dispatcher`, `base_manager`, `setup_poc/seed_erpnext_demo` semua `IMPORT OK` |
| 149 OK / 11 gagal dari 160 modul | ✅ **BENAR** | `TOTAL=163 OK=152 FAIL=11` termasuk `setup_poc/` untracked ⇒ **149 OK / 11 gagal** untuk state tracked |
| Tiga unit test murni "diselamatkan" + `test_llm_client` perlu disesuaikan | ⚠️ **kurang satu** | **Empat** test `IMPORT OK` (`test_tool_registry`, `test_canonical_mapping`, `test_skills_engine`, `test_llm_client`) — `test_llm_client` **tidak** gagal saat import |
| `29` `__init__.py` | ⚠️ **meleset 1** | Ter-track = **30** (`131 + 30 = 161` file); tetap **160 modul unik** karena kolisi `api.py` vs `api/__init__.py` |
| K7: arah perbaikan tidak disebut | ⚠️ **ambigu** | Arah benar = **naikkan** `requires-python` ke `>=3.14` (frappe v16.33.1 = `>=3.14,<3.15`), **bukan** turunkan `target-version` |
| `seed_erpnext_demo.py` "454 baris" (§5 #4d) vs "560 baris" (§1) | ⚠️ **inkonsisten internal** | Aktual = **560** baris |

---

### 3h. Koreksi revisi 7b — lokasi test & CI (2026-10-20)

Dua keputusan di `#0` dibalik setelah membandingkan dengan app yang **sudah berjalan** di mesin ini.

**Pemicu:** `apps/ekasa_logbook/` (30 test, 22.379 LOC) ternyata **nol** `conftest.py`, **nol**
`[tool.pytest.ini_options]`, **nol** CI, dan **nol** dependency pytest — tetapi test-nya jalan.
Dijalankan lewat `bench --site … run-tests`, dengan `frappe` menyediakan site, database, dan binding.

| Klaim revisi 6/7 | Status | Bukti terverifikasi |
|---|---|---|
| Test di `tests/` **root app** | ❌ **SALAH** | `bench run-tests` me-walk `frappe.get_app_path(app)` = **paket dalam** (`apps/aios_v1/aios_v1`). Test di root app **tidak akan pernah dieksekusi `bench`**. Pola nyata: `apps/ekasa_logbook/ekasa_logbook/tests/` |
| CI harus install `frappe` dari Git tag | ❌ **DIBALIK** | ~70 dependency, 2 dipin ke **commit git** (`PyPika`, `gunicorn`). Hanya `test_import_smoke.py` yang butuh `import frappe` — sisanya statis. CI cukup `ruff` + `pytest`, **tanpa apt-get** |
| `norecursedirs` untuk mengeluarkan `aios_v1/tests` | ⚠️ **tidak perlu lagi** | Karena `testpaths` sudah menunjuk paket, `pytest` otomatis tidak menyentuh 4 skrip K3 (`aios_v1/test_*.py`) maupun 9 test doctype |
| Pin `ruff==0.14.10` (konsisten dengan pre-commit) | ⚠️ **DIBALIK** | Pakai `0.17.1` + `pytest==9.1.1` (**stable latest**, terverifikasi resolvable di Python 3.14). 0.14.10 vs 0.17.1 = **746 error identik**, jadi baseline aman. Bump `.pre-commit-config.yaml` di **#3** agar #0 tetap 6 file |
| `test_authz_user_isolation.py` "butuh site/DB" | ⚠️ **menyesatkan** | Infrastruktur **ada** (site + DB sudah siap; `bench` binding otomatis). Alasan sebenarnya skip: test ini memang **sengaja MERAH sebelum #1** (§6c) — itu buktinya, bukan kekurangan env |

**Konsekuensi pada `#0`:** test hidup di `aios_v1/tests/`, `testpaths = ["aios_v1/tests"]`,
CI tanpa `frappe`, dan verifikasi butuh-site dilakukan lokal via
`bench --site aios-v16.localhost run-tests --app aios_v1`.

---

### 3i. Koreksi revisi 7c — `IMPORT OK` ≠ lulus, & bentuk skip CI (2026-10-20)

Diukur setelah Builder menjalankan `#0` (`branch chore/ci-baseline`), dengan `frappe` **hadir**:
`pytest -q` → **2 failed, 23 passed, 338 skipped, 11 xfailed** (exit 1).

| Klaim | Status | Bukti terverifikasi |
|---|---|---|
| Empat test murni "terverifikasi `IMPORT OK`" ⇒ aman | ⚠️ **menyesatkan** | `IMPORT OK` hanya berarti modul ter-import. `test_llm_client` ter-import **mulus** tetapi **gagal saat dieksekusi**. Kata "terverifikasi" di §3g/§5 terlalu kuat; yang terukur cuma import |
| `test_get_llm_config_fallback` masih valid | ❌ **usang** | Mengharap fallback `api_key == "ollama"` / `model == "llama3"`. Perilaku itu **dihapus sengaja** oleh commit `5016ad9` (anti-hardcode, §AGENTS.md 3). Test menuntut perilaku yang memang dilarang |
| `test_chat_stream_success` masih valid | ❌ **usang** | Mock `iter_lines` menghasilkan **bytes** (`b'data: ...'`) sementara runtime nyata `decode_unicode=True` ⇒ **str**. Kode memanggil `.startswith("data:")` → `TypeError`. Mock-nya salah, bukan kodenya |
| Keduanya diperbaiki di `#0` | ❌ **bukan urusan #0** | `#0` = CI baseline + pemisahan suite. Keduanya di-skip dengan **alasan eksplisit**, perbaikan nyatanya di **#7** (release) / **#8** |
| `@unittest.skip` cukup untuk melewati test butuh-frappe di CI | ❌ **SALAH** | 14 file `aios_v1/tests/*.py` `import frappe` di **module level**. Tanpa frappe, pytest berhenti di fase **collect** → `18 errors during collection`, **exit 2** (CI MERAH). `@unittest.skip` tidak pernah dievaluasi karena modul gagal di-import |
| Bentuk skip yang benar di CI | ✅ `collect_ignore` | `aios_v1/tests/conftest.py`: saat `importlib.util.find_spec("frappe") is None`, isi `collect_ignore` dengan nama file `test_*.py` **di luar** allowlist statis (`test_app_structure`, `test_repo_hygiene`, `test_import_smoke`). Mekanisme resmi pytest; nol nama baru dirawat saat file test bertambah. **Terbukti:** simulasi CI → `2 skipped, 11 xfailed, exit 0` |
| `aios_v1/api/dispatcher.handle` | ❌ **tidak ada** | Yang ada `handle_api_request` (`dispatcher.py:151`). `test_authz_user_isolation.py:118` mengimpor `handle`, jadi test itu akan **langsung gagal** begitu di-unskip di `#1` |

**Konsekuensi:** `#0` **tidak boleh** dinyatakan selesai sebelum CI **HIJAU** — dan CI hari itu merah
karena **dua** sebab independen: (a) 18 collect-error tanpa frappe, (b) 2 kegagalan eksekusi di
`test_llm_client`. Keduanya wajib ditutup di `#0`, karena `#0`-lah yang memasang gate-nya.

---

### 3j. Insiden kredensial DB `aios-v16.localhost` (2026-10-20, selesai)

Desk sempat error `AttributeError: is_ajax` saat dibuka. **Itu bukan penyebabnya — itu topengnya.**

| Fakta terverifikasi | Bukti |
|---|---|
| MariaDB sehat | `11.8.6-MariaDB` menjawab di `127.0.0.1:3306`; socket `/run/mysqld/mysqld.sock` ada |
| Data **utuh**, tidak hilang | `/var/lib/mariadb/_f76bcd16c9507e06/` ada; setelah perbaikan site berisi **762 tabel** |
| Penyebab sebenarnya | `MySQLdb.connect(...)` → `(1045, "Access denied for user '_f76bcd16c9507e06'@'localhost' (using password: YES)")`. Password di `sites/aios-v16.localhost/site_config.json` tidak sinkron dengan user MariaDB |
| Situs lain tidak terkena | `ekasa-logbook.localhost` connect **OK** (248 tabel) dengan skema yang sama |
| Mengapa `is_ajax` yang muncul | Bug Frappe: `apps/frappe/frappe/app.py:217` `frappe.init()` gagal → baris `:224` (`frappe.local.is_ajax = ...`) **tidak pernah jalan** → `handle_exception` di `:391` membaca atribut itu tanpa `getattr` → `AttributeError`. Error 1045 asli **tertelan**. Bandingkan `frappe/__init__.py:1345` yang benar memakai `getattr(local, "is_ajax", False)` |
| Mengapa "khusus aios-v16" | `common_site_config.json` → `"default_site": "aios-v16.localhost"`. Browser mendarat di situs yang rusak; ekasa tak pernah dibuka |
| Korelasi waktu | `site_config.json` aios-v16 terakhir diubah **2026-10-20 13:31** (kena `bench set-config` saat pasang `allow_tests`/`developer_mode`); ekasa terakhir **2026-09-14**. Itu sebabnya hanya aios yang pincang |
| Kelas risiko yang terungkap | `private/backups/` **kosong** — nol backup sebelum insiden. `(1045)` tidak membedakan *password salah* dari *user tidak ada*, jadi keberadaan datanya sempat tidak bisa dipastikan. Backup kemudian dibuat (lihat L10) |

**Pelajaran untuk `#4d`:** backup bukan formalitas. `bench --site aios-v16.localhost backup --with-files` di §5 `#4d` adalah **prasyarat keras**, bukan langkah opsional — dan insiden ini buktinya.

---

### 3k. Penutupan `#0` (`chore/ci-baseline`) — 2026-10-20

**Status:** ✅ **SELESAI**. Gate terpasang dan **hijau di dua sisi**. Diverifikasi **tiga lapis**:
Builder menjalankan, reviewer mengukur ulang sendiri, pemilik project menjalankan di terminal.

**Hasil terukur (diukur ulang oleh reviewer, bukan dari laporan Builder):**

| Perintah | Hasil | Exit |
|---|---|---|
| `python3 -m pytest -q` (python sistem, **tanpa** frappe = simulasi CI) | `2 skipped, 11 xfailed` | **0** |
| `/home/samue/mybench-v16/env/bin/python -m pytest -q` (**dengan** frappe) | `23 passed, 340 skipped, 11 xfailed` | **0** |
| `ruff check --statistics .` | **746** errors | 1 (advisory, disengaja) |

Sebelumnya CI mati: `Interrupted: 18 errors during collection`, exit 2. Sekarang nol.

**File `#0` (final):**
- Baru: `aios_v1/tests/conftest.py`, `test_import_smoke.py`, `test_app_structure.py`, `test_repo_hygiene.py`, `test_authz_user_isolation.py`, `.github/workflows/ci.yml`
- Diubah: `pyproject.toml` + **14** file K5 (`13` diberi `@unittest.skip` class-level, `test_llm_client.py` diberi **2 decorator skip**, isi test tidak disentuh)
- `docs/` & `AGENTS.md` tidak diubah Builder (dikelola reviewer/pemilik)

**Koreksi klaim Builder — hasil benar, model mental salah:**

Builder melaporkan `2 skipped = authz_user_isolation (file ter-collect tapi tidak meng-import frappe di level module)`. **Dua-duanya salah**, terukur:

```
$ python3 -m pytest --collect-only -q | grep -c authz
0                                    # authz TIDAK dikumpulkan di CI

$ python3 -m pytest -q -rs
SKIPPED [1] test_import_smoke.py:49: frappe tidak importable (CI tanpa frappe)
SKIPPED [1] test_import_smoke.py:72: frappe tidak importable (CI tanpa frappe)
```

- `test_authz_user_isolation.py` **tidak** ter-collect di CI — dibuang `conftest.py` (allowlist statis hanya 3 file).
- File itu **memang** `import frappe` di module level (`:9`) — itulah alasan file itu butuh `conftest.py`.
- `2 skipped` berasal dari **dua** `@unittest.skipUnless(HAVE_FRAPPE, ...)` di `test_import_smoke.py`.

Ini kelas kesalahan yang **berbahaya**: hasilnya lolos sehingga tidak ketahuan, tetapi model mentalnya
salah. Bila `conftest.py` diubah di masa depan dengan asumsi "authz aman karena tidak import frappe di
module level", koleksi akan jebol kembali tanpa ada yang tahu sebabnya. **Pelajaran:** angka yang cocok
tidak membuktikan alasan yang benar — alasan wajib diukur terpisah.

**Batasan `#0` (jangan salah ingat):** di CI, jumlah `passed` = **0**. Ke-13 test yang ter-collect
seluruhnya `skipped` (2) atau `xfailed` (11), jadi **nol assertion dieksekusi**. CI `#0` membuktikan
**mekanisme collection bekerja**, bukan bahwa kodenya benar. Itu **sesuai desain**
(`test_app_structure` & `test_repo_hygiene` di-xfail sampai #2/#3), tetapi baru menjadi bukti nyata di
**#4a** saat CI naik ke MariaDB + Redis + site dan menjalankan `bench --site test_site run-tests`.

**Sisa nit (bukan blocker, ikut #1):** docstring `test_authz_user_isolation.py:4` masih menulis
`"auto-skip di CI"` — sebenarnya **dibuang dari collection** oleh `conftest.py`, bukan di-skip.

---

## 4. Temuan Lengkap

### 🔴 Keamanan (18 temuan)

**Prioritas tertinggi — lubang yang bisa dieksploitasi sekarang:**

| # | Temuan | Lokasi | Severity |
|---|---|---|---|
| **N1** | `/api/chatbot/*` **tanpa autentikasi sama sekali**. `sessions`, `messages`, `settings` GET/POST tidak memanggil `get_current_session()`. Bocor data pelanggan Telegram **dan** siapa pun bisa mengubah `custom_instructions` bot (prompt injection) | `dispatcher.py:989-1050` | **Kritis** |
| **N2** | **IDOR di `/stream`**. `conversationId` dari body dipakai apa adanya; pesan ditulis ke percakapan orang lain, dan riwayat 6 pesan terakhir milik tenant lain dikirim ke LLM | `managers/base_manager.py:107-129` | **Kritis** |
| **S1** | Gerbang approval manusia `allow_guest=True` (3 fungsi) | `lib/draft_manager.py:18,27,46` | **Kritis** |
| **S2** | Doctype `Pending Action Draft` **tidak ada di repo** — definisinya tersembunyi di `setup_tahap2.py:15-23` (yang akan dihapus di #2) dan **tidak punya field kepemilikan `user` maupun `rejection_reason`**. *(Owner tunggal pembuatan DocType JSON: **Tahap C**, langsung memakai `user -> Link(User)` agar tidak perlu dibongkar ulang di #4a)* | `draft_manager.py:8`, `setup_tahap2.py:15-23`, `tools/logistic_tools.py:42`, `aios_manager_tools.py:133` | **Kritis** |
| **S3** | **IDOR + bug routing** — `get_doc` tanpa cek tenant; `msgs` difilter hanya `conv_id` → isi pesan ikut bocor. **Plus bug kode**: `:927` (`if action == "conversations"`) tidak cek `len(parts) == 4` sehingga blok `:940` unreachable, dan `:941` pakai `conv_id = parts[3]` (`"conversations"`) padahal `<id>` ada di **`parts[4]`** (`len(parts) == 5`). Juga di `/api/mapping/validate` (`:662-677`): update `AIOS Mapping Entry` via `entryId` dari body tanpa cek kepemilikan `mapping` milik tenant | `api/dispatcher.py:662-677, 927-950` | **Kritis** |
| **S4** | `/api/chat/parse-pdf` **tanpa autentikasi**, tanpa batas ukuran file | `api/dispatcher.py:846` | **Kritis** |
| **S5** | Fallback tenant salah di jalur **tulis** — request tanpa sesi menulis ke tenant 2 + bakar kuota LLM | `api/dispatcher.py:954` | **Kritis** |

**Tinggi:**

| # | Temuan | Lokasi | Severity |
|---|---|---|---|
| **N3** | Fallback tenant **1** di jalur **baca** (list conversations) tanpa sesi | `dispatcher.py:928` | Tinggi |
| **N4** | `/api/auth/register` terbuka, langsung `ACTIVE`, tanpa rate limit; respons 409 → **enumerasi email**. `/api/payment/status` mengembalikan `ACTIVE` **hardcoded** → gerbang `PENDING_PAYMENT` kosmetik | `:237-282`, `:288-296` | Tinggi |
| **N5** | Adapter DB menerima `host`, `port`, `file_path` **dari klien** → SSRF/port scan internal; SQLite bisa diarahkan ke file server mana pun. Tidak ada allowlist/blokir IP privat | `dispatcher.py:457-462`, `data_access/adapters/sqlite_adapter.py`, `data_access/adapters/mysql_adapter.py` | Tinggi |
| **S8** | Kredensial hardcoded + **selalu di-reset** tiap dijalankan | `seed_auth.py:18-55` | Tinggi |
| **S12** | Default adapter MySQL `user="root"` @ `127.0.0.1` *(owner: **#1** ikut N5 / ditunda bersama adapter DB klien)* | `data_access/adapters/mysql_adapter.py:10` | Tinggi |

**Menengah / rendah:**

| # | Temuan | Lokasi | Severity |
|---|---|---|---|
| **N6** | Token sesi ditandatangani dengan `encryption_key` Frappe — **kunci yang sama** dengan enkripsi field `Password` | `lib/auth.py:17` vs `password.py:193` | Menengah |
| **S10** | `password_hash` fieldtype `Data` → tidak ter-mask → bocor kalau ada `as_dict()`/`fields=["*"]` | `aios_tenant.json` | Menengah |
| **S11** | Path mesin developer di jalur produksi | `data_access/adapters/sqlite_adapter.py:37-38` | Menengah |
| **S6** | CORS mencerminkan Origin apa pun + `Allow-Credentials: true` | `api/dispatcher.py:111-120` | Rendah-menengah |
| **S7** | CSRF token dikirim frontend tapi tidak diverifikasi | `frontend/lib/api.ts:17` | Rendah-menengah |
| **S9** | Tidak ada rate limit / lockout di **auth custom AIOS**; password min 6 karakter. *(Frappe punya `LoginAttemptTracker` — `auth.py:530`, dipakai `:518` — jadi ini hilang sendiri di #4b)* | `api/dispatcher.py:194,256` | Rendah |

### 🟠 Arsitektur (13 temuan)

| # | Temuan | Lokasi |
|---|---|---|
| A1 | **Lapisan tool tidak tersambung** — `base_manager` tidak kirim `tools=`; `execute_tool` pemanggilnya hanya test + demo. 7.728 LOC mati | `managers/base_manager.py` |
| A2 | Sisa refactor → `ImportError`: `chat_completion` tidak ada (11 modul gagal) | `lib/demo_tahap1.py:3` dst |
| A3 | `aios_v1/api.py` ter-shadow paket `api/` → `ask_intelligence` = `AttributeError` | `api.py` vs `api/__init__.py` (0 byte) |
| A4 | Dua pohon aplikasi bersaing | `aios_v1/doctype/`, `aios_v1/page/` (salinan luar-package; tidak ada `aios_v1/aios_v1/aios_v1/` — klaim lama itu keliru) |
| A5 | Mismatch entitas kanonik — `Account`/`Transaction`/`Loan` ditanyakan tapi tidak ada di kamus | `query_engine.py` vs `canonical_models.py` |
| A6 | Keyword matching salah — `"beli"` (SalesOrder) menangkap `"pembelian"` (PurchaseOrder) | `data_access/query_engine.py` |
| A7 | `_ADAPT_JOBS` dict module-level → rusak di multi-worker; `time.sleep(0.8)` per tabel memblokir worker | `api/dispatcher.py:10,50` |
| A8 | Dispatcher 1.061 baris di `before_request` — **severity rendah** (`:159-176` early return) | `hooks.py:291` |
| A9 | `managers/*.py` **9** file 0 byte | `managers/` |
| A10 | Telegram polling manual tanpa supervisor *(owner: **#9** pindah ke `scheduler_events`/webhook atau dicatat ditunda di **#10**)* | `lib/telegram_service.py:769` |
| A11 | `www/aios_web_handler.html` = `{{ html_content \| safe }}`, `html_content` tidak di-set di mana pun (XSS sink mati tanpa controller `.py`) *(owner: **hapus di #2/#3**)* | `www/aios_web_handler.html:1` |
| A12 | Token accounting pakai estimasi `len/3.8`, bukan usage API — kuota biaya jadi **tidak akurat** *(owner: **#7 L8** — wajib dibereskan sebagai fondasi kuota biaya)* | `managers/base_manager.py:201,220`, `lib/llm_client.py:56-70` |
| A13 | `get_doc` **tidak lewat** `permission_query_conditions`; tanpa `has_permission` ia membaca lintas tenant. Dipakai sejak jalur baca S3 — jadi hidup, bukan laten | `api/dispatcher.py:942-947` |

### 🟡 Kebersihan & Packaging (11 temuan)

| # | Temuan | Lokasi |
|---|---|---|
| K1 | 396 file / 39 MB build artifact ter-track | `aios_v1/public/frontend/` |
| K2 | `build-to-frappe.mjs` baca `out/` yang tidak ada; path Windows/WSL hardcoded | `frontend/scripts/build-to-frappe.mjs` |
| K3 | **16** skrip debug/test di root package, ter-track (termasuk `test_login_direct.py:7-8,14` yang mencetak `password_hash` ke stdout & hardcode password `'client123'`) *(owner: **#2**)* | `check_db.py`, `fix_perms.py`, `migrate_schema.py`, `seed_auth.py`, `get_error.py`, `create_dummy_draft.py`, `test_stream.py`, `test_whitelist.py`, `test_dispatcher_direct.py`, `test_login_direct.py`, `add_page.py`, `add_shortcuts.py`, `setup_tahap2.py`, `check_draft.py`, `inspect_setting.py`, `read_setting.py` |
| K4 | 25 file `lib/demo_tahap*` — 2.546 LOC, 11 rusak *(owner: **#3**)* | `lib/` |
| K5 | ~~**18 file di `aios_v1/tests/`** tidak bisa jalan langsung~~ → ✅ **DIPISAH di `#0`** (§3k): 4 test diselamatkan (`tool_registry` 4, `canonical_mapping` 6, `skills_engine` 10, `llm_client` 1 = **21** lulus), **2** test usang `test_llm_client` di-skip beralasan (§3i), **13** test tool mock lama di-`@unittest.skip` sampai **#3/#8**, dan `conftest.py` memisahkan suite statis (CI) dari integrasi (bench). *(sisa: hapus 13 test mock lama di **#3/#8**)* | `aios_v1/tests/` |
| K6 | App tidak mendeklarasikan dependensi runtime (`requests`, `pypdf`, `pytesseract`, `pdf2image`) *(owner: **#0/#3**)* | `pyproject.toml:10-12` |
| K7 | `target-version = "py314"` vs `requires-python = ">=3.10"`; `license.txt` 3 byte; tanpa field `license` *(owner: **#0/#3**; arah perbaikan terverifikasi: **naikkan** `requires-python` ke `>=3.14`, **bukan** turunkan `target-version` — `frappe` v16.33.1 sendiri memakai `requires-python = ">=3.14,<3.15"`)* | `pyproject.toml:7,28`, `license.txt` |
| K8 | 776 × `print(`, 76 × `except Exception`, 2 TODO (`draft_manager.py:42,60`) *(owner: **#2/#3** hapus mayoritas di file mati + **#9** bersihkan di jalur hidup)* | seluruh app |
| K9 | `ruff` mematikan `F401`,`F403`,`F405`,`B904`,`B023` *(owner: **#0/#3** — aktifkan kembali setelah file sampah dihapus di #3)* | `pyproject.toml:40-59` |
| K10 | **Tidak ada CI apa pun** — tanpa runner, "hijau/merah" hanya klaim; setiap branch berikutnya menumpuk di atas dasar tak terverifikasi *(owner: **#0**)* | `.github/` (tidak ada) |
| K11 | Tanpa `[tool.pytest.ini_options]` + dev-dep pytest/ruff: pytest meng-import `aios_v1/` sebagai package, **bukan** app terpasang → `import frappe` gagal. Test butuh `bench --site … run-tests` atau rootdir+`pythonpath` yang eksplisit *(owner: **#0**)* | `pyproject.toml`, `.github/workflows/` |

### 🟣 Sandbox LLM (temuan revisi 3)

Konteks: LLM di AIOS akan menjalankan tool terhadap **data keuangan klien**.
Sandbox bukan opsional. Yang sudah ada harus diakui, yang kurang harus ditutup.

| # | Lapisan | Status | Lokasi |
|---|---|---|---|
| L1 | Tidak ada SQL mentah dari LLM — LLM sebut konsep bisnis, kode menerjemahkan | ✅ **sudah** | `lib/data_access_agent.py:29-37`, `data_access/query_engine.py:110-127` |
| L2 | `fields`/`filters`/`order_by` divalidasi ke mapping kanonik; **value parameterized** | ✅ **sudah** | `data_access/query_engine.py:110-127` |
| L3 | Whitelist tool per worker (least privilege) | ✅ **sudah** | `lib/tool_registry.py:44-90` |
| L4 | Tidak ada akses OS/filesystem — nol `eval`/`exec`/`importlib`/`subprocess` | ✅ **sudah** | `lib/tools/*`, `lib/tool_registry.py` |
| **L5** | **`aggregate.fn` TIDAK divalidasi ke whitelist** — masuk mentah ke SQL | ⚠️ **CELAH** | `data_access/query_engine.py:93-103` |
| **L6** | Guard read-only lemah — hanya `startswith(("SELECT","WITH","EXPLAIN","PRAGMA"))` | ⚠️ **lemah** | `data_access/adapters/sqlite_adapter.py:127`, `data_access/adapters/postgres_adapter.py:96`, `data_access/adapters/mysql_adapter.py:96` |
| **L7** | Tidak ada batas `User` & `Company` di lapisan tool (perlu resolusi `AIOS Setting.default_company` / `Global Defaults` via `get_single_value` di level site) | ❌ **belum** | `lib/tools/*`, `aios_setting.json` |
| **L8** | Tidak ada kuota biaya/token per `User` + estimasi masih `len/3.8` (A12) + belum ada modul akuntansi atomik `aios_v1/services/usage.py` | ❌ **belum** | `managers/base_manager.py:201,220`, `lib/llm_client.py:56-70` |
| **L9** | Operasi tulis butuh approval manusia — DocType JSON dibuat di **Tahap C** (S2), penyambungan approval & 2 TODO dikerjakan di **#7** | ⚠️ **setengah** | `lib/ai_manager_tools.py:99-150`, `lib/draft_manager.py:42,60` |
| **L10** | Seed PoC ERPNext: skrip **sudah ditulis & syntax OK (560 baris), BELUM PERNAH dijalankan**. Backup site **sudah dibuat 2026-10-20 16:18** (`20261020_161847-aios-v16_localhost-database.sql.gz`, 997 KB — dipicu oleh insiden kredensial DB §3j). Menyalakan #8 tidak boleh mendahului seed ini | ⚠️ **seed belum dieksekusi**; backup ✅ | `aios_v1/setup_poc/seed_erpnext_demo.py` (#4d) |

**L5 terverifikasi dapat dieksploitasi** (belum reachable):

```
input  fn = "1) UNION SELECT password_hash FROM users --"
SQL    → SELECT 1) UNION SELECT PASSWORD_HASH FROM USERS --("harga_satuan") AS value FROM "katalog_produk" LIMIT 10
guard startswith("SELECT")? → True   ← LOLOS
```

**Reachable?** Belum — **tidak ada satu pun** dari 10 file `lib/tools/*` yang
mengekspos parameter `aggregate` ke LLM. Jadi ini **celah laten**: begitu #8
menyambungkan tool layer, kalau ada tool yang meneruskan `aggregate` dari LLM,
celah ini **langsung hidup**. Karena itu #7 harus mendahului #8.

### 🔵 Akar Masalah

**Tidak ada isolasi tenant di level framework.** Semua doctype hanya `System Manager`,
jalur aplikasi `ignore_permissions=True`, tenant difilter **manual** di setiap query.
`frappe.session` **0 kali** dipakai → seluruh mesin otorisasi Frappe tidak aktif.
`permission_query_conditions`/`has_permission` masih dikomentari
(**`hooks.py:166-171`** — boilerplate bawaan, bukan dimatikan sengaja).

**Akar struktur folder:** file diletakkan relatif ke `apps/<app>/` padahal seharusnya
relatif ke package `aios_v1/aios_v1/`. Bukti: `aios_v1/doctype/` dan `aios_v1/page/`
tidak punya `__init__.py`, sedangkan di dalam package punya.

---

## 5. Rencana Branch

Semua dari `develop`. Setiap branch **wajib** menyertakan test (lihat §6).

### #0 — `chore/ci-baseline` · 1–2 hari · **WAJIB PERTAMA** · ✅ **SELESAI 2026-10-20** (lihat §3k)

Jaring pengaman (menutup **K10, K11** + memisahkan suite **K5**). Tanpa ini, semua
branch berikutnya tidak punya cara membuktikan tidak merusak apa pun.

**Deliverable:**
- `.github/workflows/ci.yml` → `ruff check` + pytest statis. **`ruff format --check` DITUNDA ke #3** (bukan dibatalkan): repo saat ini **97 file indent 4-spasi vs 25 file tab** padahal `[tool.ruff.format]` minta `indent-style = "tab"`, dan `aios_v1/api/dispatcher.py` masih CRLF — reformat massal di #0 akan menenggelamkan baseline "11 gagal `demo_tahap*`" di ratusan diff format.
- **CI TIDAK meng-install `frappe` / `erpnext` (keputusan revisi 7 — meniru pola `ekasa_logbook`):**
  - `frappe` tidak tersedia di PyPI (hanya placeholder `0.0.1`) dan `erpnext` tidak ada sama sekali, jadi install wajib dari Git tag — ~70 dependency dengan 2 di antaranya dipin ke **commit git** (`PyPika`, `gunicorn`). CI jadi rapuh: commit itu hilang dari GitHub ⇒ pipeline mati. Nol manfaat untuk #0.
  - Yang dikumpulkan di CI **hanya** 3 test statis (`test_app_structure`, `test_repo_hygiene`, `test_import_smoke`); 14 file lain — termasuk `test_authz_user_isolation.py` dan 13 test K5 lama — **tidak dikumpulkan** oleh `conftest.py` (§3i). Semuanya dijalankan lokal via `bench --site aios-v16.localhost run-tests --app aios_v1`.
  - Karena itu CI cukup `pip install "ruff==0.17.1" "pytest==9.1.1"`, **tanpa apt-get**. CI tetap kelas **statis** (§10).
  - Pola rujukan: `apps/ekasa_logbook/` (30 test, **nol** `conftest.py`, nol konfigurasi pytest, nol CI) berjalan lewat `bench run-tests`. Lokal: `frappe 16.33.1` + `erpnext 16.34.2` terpasang sejak 2026-09-10.
  - **Mekanisme skip (wajib, terverifikasi 2026-10-20):** **14** file `aios_v1/tests/*.py` meng-`import frappe` di **module level**. Tanpa frappe, pytest berhenti di fase **collect** → `18 errors during collection`, **exit 2** (CI MERAH); `@unittest.skip` tidak pernah dievaluasi. Yang bekerja: `aios_v1/tests/conftest.py` mengisi `collect_ignore` saat `importlib.util.find_spec("frappe") is None`, menyisakan allowlist statis (`test_app_structure`, `test_repo_hygiene`, `test_import_smoke`). **Terbukti:** simulasi CI → `2 skipped, 11 xfailed, exit 0`. *(Revisi 7b menyebut `pytest.importorskip`; itu benar untuk 1 file, tetapi tidak menyelamatkan 13 file lain yang sudah meng-import frappe — `collect_ignore` menyelesaikan keduanya sekaligus.)*
- **Tangga CI — mengapa #0 tanpa `frappe` (bukan pola permanen):** CI #0 sengaja tanpa `frappe`/DB karena keempat test-nya statis dan nol di antaranya butuh site. Begitu test integrasi nyata masuk — **#4a** (`test_permission_scoping`), **#4b** (`test_login_flow`), **#8** (`test_erpnext_finance_tools`) — CI **wajib** naik ke MariaDB + Redis + site dan menjalankan `bench --site test_site run-tests`, meniru `.github/workflows/_base-server-tests.yml` milik Frappe sendiri. Keputusan itu milik **#4a**, bukan #0. Yang menjaga CI #0 tetap tahan lama: nol install `frappe` (~70 dependency, 2 dipin ke commit git) dan nol `apt-get`.
- `aios_v1/tests/test_import_smoke.py` → import **seluruh modul apa adanya via `Path.rglob("*.py")`** (karena `aios_v1/lib/` belum punya `__init__.py`). **Wajib snapshot & restore `sys.path` per modul** karena `aios_v1/check_db.py:2` mengeksekusi `sys.path.insert(0, '/home/samue/mybench/apps/aios_v1')` saat import!
  - **Jangan hardcode `160` / `11`.** Denominator bergerak sendiri: `setup_poc/` (2 file) masih **untracked** ⇒ checkout bersih CI = **161 file / 160 modul unik**, lalu bertambah ketika #4d men-commit `setup_poc/` dan berkurang ketika #3 menghapus 25 `demo_tahap*`. Uji memakai **daftar modul `xfail` eksplisit** (11 modul: `aios_v1.lib.demo_tahap1`, `demo_tahap6m_2` … `demo_tahap6m_11`; penyebab seragam `ImportError: cannot import name 'chat_completion'`), **bukan** dengan mencocokkan jumlah kegagalan.
- `aios_v1/tests/test_app_structure.py` → kontrak struktur app (lihat #2)
- `pyproject.toml` → `[tool.pytest.ini_options]` dengan `testpaths = ["aios_v1/tests"]` (test hidup di **paket dalam**, pola `ekasa_logbook`) dan `norecursedirs = ["frontend", "node_modules", ".git"]`. Karena `testpaths` menunjuk paket, `pytest` otomatis tidak mengumpulkan 4 skrip `aios_v1/test_*.py` (**K3**) maupun 9 test `aios_v1/aios_v1/doctype/*/test_*.py`. Dev-dependency `pytest` + `ruff`, selaraskan metadata Python (**K7**: **naikkan** `requires-python` ke `>=3.14`)
- Penanganan **K5** (18 file di `aios_v1/tests/`): pisahkan konfigurasi runner statis vs integrasi (`bench --site … run-tests`); selamatkan **4** unit test murni (`test_tool_registry`, `test_canonical_mapping`, `test_skills_engine`, `test_llm_client` — **keempatnya terverifikasi `IMPORT OK`** dan nol akses `frappe.db` di module level), dan tandai skip/tunda 13 test DB/tool mock lama sampai Tahap C (S2) & #8. *(Koreksi: revisi 6 menyebut `test_llm_client` gagal import; terverifikasi **tidak** — kalau ia gagal, itu saat eksekusi, bukan saat import.)* ⚠️ **`IMPORT OK` ≠ lulus** — dua test di `test_llm_client` **usang**; lihat §3i.
- Install `ruff==0.17.1` + `pytest==9.1.1` di bench env (**stable latest**, terverifikasi resolvable di Python 3.14). 0.14.10 dan 0.17.1 menghasilkan **746 error identik** (sudah diuji), jadi baseline tak berubah. ⚠️ `.pre-commit-config.yaml` masih mem-pin `ruff` `v0.14.10` — **bump-nya di #3** (`chore/repo-hygiene`) agar #0 tetap 6 file.

**Test (script):** `aios_v1/tests/conftest.py`, `aios_v1/tests/test_import_smoke.py`, `aios_v1/tests/test_app_structure.py`, `aios_v1/tests/test_repo_hygiene.py`, `aios_v1/tests/test_authz_user_isolation.py`

**Verifikasi (baseline diukur ulang 2026-10-20, `python -B`, read-only):**
`TOTAL=163 OK=152 FAIL=11` bila `setup_poc/` ikut dihitung ⇒ untuk state **tracked**: **149 OK / 11 gagal dari 160 modul unik** — angka yang muncul saat `bench run-tests` lokal (checkout bersih).
`test_app_structure.py` & `test_repo_hygiene.py` **gagal** di #0 (kode masih serakan & kotor) — sengaja, supaya #2 dan #3 punya target terukur.

> Catatan: test ini harus di-*xfail* atau di-skip eksplisit dengan alasan, agar CI
> bisa hijau untuk branch lain sambil tetap mencatat utang #2 dan #3.

---

### #1 — `fix/security-emergency` 🔴 · beberapa hari

**Dipangkas.** Hanya lubang yang **bisa dieksploitasi sekarang** dan **tidak akan
hilang** di #4. Yang toh dihapus #4b dan tidak bisa dieksekusi benar sekarang
(CSRF, CORS, rate limit, seed creds) **ditunda**.

| Aksi | Lokasi | Test |
|---|---|---|
| Auth di `/api/chatbot/*` (N1) | `dispatcher.py:989-1050` | `test_endpoint_auth.py` |
| **Tahap C —** Cek kepemilikan `conversationId` di `/stream` (N2) | `base_manager.py:107-129` | `test_authz_user_isolation.py` |
| **S2 — pindah ke Tahap C:** Buat doctype `Pending Action Draft` jadi **file JSON di repo** (`aios_v1/aios_v1/doctype/pending_action_draft/`): 7 field dari `setup_tahap2.py:15-23` (`task_id`, `type`, `branch`, `created_by_agent`, `payload`, `status`, `expires_at`) **+ 2 field wajib yang hilang di skrip lama**: **`user` (`Link -> User`, `reqd=1`, `in_standard_filter=1`)** dan `rejection_reason` (`Small Text`). *(Dikerjakan di **Tahap C**, bukan #1. Langsung memakai `user -> Link(User)`, **bukan** `tenant -> Link(AIOS Tenant)`, agar skema tidak perlu dibongkar ulang di #4a karena `CustomField`/`DocField` menolak perubahan `Link` target)* | `draft_manager.py:8`, `setup_tahap2.py:15-23` | `test_doctype_exists.py` (Tahap C) |
| **Tahap C —** Cabut `allow_guest` (S1) | `draft_manager.py:18,27,46` | `test_draft_contract.py`, `test_draft_flow.py` |
| **Tahap C —** Cek kepemilikan percakapan & mapping terhadap sesi aktif + **betulkan bug routing** (`:927` wajib `len(parts) == 4`; `:940` `len(parts) == 5` dengan `conv_id = parts[4]`, bukan `parts[3]`) + cek kepemilikan `entryId` terhadap `mapping` di `/api/mapping/validate` (`:662-677`) (S3) | `dispatcher.py:662-677, 927-950` | `test_authz_user_isolation.py` |
| Hapus fallback `else 2` (S5) + `else 1` (N3) → wajib sesi | `dispatcher.py:928,954` | `test_endpoint_auth.py` |
| Wajib sesi + batas ukuran file (S4) | `dispatcher.py:846` | `test_parse_pdf_guard.py` |
| Hapus path `/mnt/g/...` (S11) | `data_access/adapters/sqlite_adapter.py:37-38` | `test_no_machine_paths.py` |
| Tutup enumerasi email di register (N4) | `dispatcher.py:256` | `test_register_enumeration.py` |
| Hapus `ACTIVE` hardcoded di payment (N4) | `dispatcher.py:288-296` | `test_payment_gate.py` |
| Allowlist host/path koneksi DB (N5) + hapus default `user="root"` (S12) *(atau matikan endpoint adapter sementara selama PoC ERPNext)* | `dispatcher.py:457-462`, `data_access/adapters/mysql_adapter.py:10` | `test_db_connection_ssrf.py` |

**DITUNDA ke #4b** (bukan dibatalkan): CSRF, CORS, rate limit login, seed creds,
`password_hash` → `Password`.
Alasan: `rate_limit` adalah decorator `@frappe.whitelist` (tidak jalan di
`before_request`), CSRF Frappe hanya aktif setelah pakai `sid`, dan konversi
`password_hash` → `Password` **terbukti mengunci semua login** (§3b).

**Verifikasi:** tanpa cookie ke setiap endpoint AIOS → 401. Cookie `_Test User Alpha` ke
resource `_Test User Beta` → 403.

---

### #2 — `chore/fix-app-layout` · 1–2 hari · **risiko tertinggi**

Memperbaiki akar "struktur folder ngaco".

| Aksi | Detail |
|---|---|
| Hapus `intelligence_chat` (2 salinan) | `aios_v1/page/` + `aios_v1/aios_v1/page/intelligence_chat/` |
| Hapus `aios_portals` | `aios_v1/aios_v1/page/aios_portals/` |
| Hapus `aios_v1/api.py` | tidak ada pemanggil setelah page dihapus (A3) |
| Pindahkan/hapus `aios_v1/doctype/{aios_mapping,aios_mapping_entry}` | **terverifikasi identik** (SHA256) → hapus salinan luar (A4) |
| Hapus 9 `managers/*.py` (0 byte) | A9 |
| Hapus **16** skrip debug/test root package | lihat K3 (termasuk `test_dispatcher_direct.py` & `test_login_direct.py` yang mencetak `password_hash`, serta `setup_tahap2.py` setelah skema `Pending Action Draft` masuk repo di Tahap C) |
| Hapus `aios_v1/www/aios_web_handler.html` | XSS sink mati `{{ html_content \| safe }}` tanpa controller (A11) |

**Test:** `aios_v1/tests/test_app_structure.py` — sekarang harus **HIJAU** (di #0 sengaja merah).
Menguji: tidak ada `doctype/`/`page/` di luar package, tidak ada modul ter-shadow,
tidak ada file 0 byte di `managers/`, tidak ada `www/aios_web_handler.html`,
`bench migrate` tetap menemukan seluruh doctype dalam package (12 awal + `Pending Action Draft` dari Tahap C = 13 doctype).

**Verifikasi:** `bench migrate` sukses, doctype terdeteksi, CI hijau.

**Kenapa dipisah dari #3:** #2 **memindahkan file yang aktif dipakai Frappe**,
#3 **menghapus file mati**. Kalau digabung dan pecah, penyebabnya tidak jelas.

---

### #3 — `chore/repo-hygiene` · 1 hari · risiko rendah

- Hapus `aios_v1/public/frontend/` — 396 file / 39 MB (K1)
- Hapus 25 `lib/demo_tahap*.py` — 2.546 LOC (menutup 11 kegagalan import A2/K4 + memangkas mayoritas `print(` K8)
- Hapus path Windows/WSL di `build-to-frappe.mjs` (K2)
- **Bersihkan emoji dekoratif di frontend (Zero Emoji in UI):** ganti 9 emoji di `frontend/lib/branches.ts:16-79` (`📊`, `💰`, `📈`, `🛒`, `📦`, `🏭`, `📋`, `👥`, `🔧`) serta emoji di `frontend/components/aios/ChatDock.tsx` dengan key ikon vektor (`lucide-react`: `bar-chart-3`, `wallet`, `trending-up`, `shopping-cart`, `package`, `factory`, `clipboard-list`, `users`, `wrench`)
- Rapikan `pyproject.toml` & `license.txt`: deklarasikan dependensi runtime (`requests`, `pypdf`, `pytesseract`, `pdf2image`, **`openpyxl`** — **K6**), selaraskan `requires-python` ke `>=3.14` & `license` (**K7** — `frappe` v16.33.1 memakai `>=3.14,<3.15`), serta **aktifkan kembali rule `ruff`** `F401, F403, F405, B904, B023` (**K9**) ditambah **`S110` (`try-except-pass`) & `BLE001` (`blind-except`)** untuk melarang silent error setelah file sampah hilang
- Perbaiki `.gitignore`

**Test:** `aios_v1/tests/test_repo_hygiene.py` — assert tidak ada artifact ter-track
(cek `git ls-files`), tidak ada file `demo_tahap*`, tidak ada emoji dekoratif di `frontend/lib/branches.ts` & `ChatDock.tsx`, smoke import **0 gagal**,
`ruff check` lolos dengan rule K9 + `S110`/`BLE001` aktif, **cek AST bahwa setiap blok `except` di modul produksi memanggil `frappe.log_error` atau melakukan `raise`** (tidak ada `except ...: pass`/`continue` diam-diam), serta **cek AST bahwa tidak ada file `test_*.py` yang memanggil `frappe.db.commit()`**.

> Urutan penting: reviewer menyarankan #3 **mendahului** #2 agar #2 tidak memindahkan
> file yang toh akan dihapus. **Tidak diikuti** — #2 memindahkan doctype **aktif**
> (butuh `bench migrate`), #3 menghapus file mati. Kalau #3 duluan, `test_app_structure.py`
> tetap merah dan tidak ada bedanya bagi #2. Urutan #2→#3 tetap.

---

### Tahap C — Ownership per `User` (dikerjakan sebelum #4a penuh)

**Status:** **SELESAI 2026-10-21** — scope **menengah**, bukan #4a penuh.
Alasan: lubang IDOR harus ditutup sekarang, tetapi `AIOS DB Connection` belum bisa
lepas `tenant` sampai injeksi `user_id` dari sesi selesai (#7 / L7).

**Keputusan yang dikunci:**

1. **`AIOS Conversation`, `AIOS Agent State`, `Pending Action Draft` → `user -> Link(User)`.**
   Field `tenant` **dihapus** dari ketiganya di Tahap C — tanpa shim.
2. **`AIOS DB Connection` → tambah `user`** (`Link -> User`, `reqd`, `in_standard_filter`);
   `tenant` **tetap** sampai #4a. Ini satu-satunya kolom transisi yang tersisa, karena
   `query_engine.get_mapping_lookup()` dan `data_access_agent` mencari koneksi lewat
   `tenant` dan dipakai seluruh 9 modul tool. Pengganti amannya adalah `user_id` dari
   sesi (#7 / L7), bukan argumen LLM.
3. **`Pending Action Draft` dibuat sebagai file JSON di repo**
   (`aios_v1/aios_v1/doctype/pending_action_draft/`) pada Tahap C, bukan #1 S2: 7 field
   lama + `user` (`reqd=1`, `in_standard_filter=1`) + `rejection_reason`.
   `escalate_to_human_approval` mengisi `user = frappe.session.user`;
   `get_draft`/`approve_draft`/`reject_draft` mencabut `allow_guest` dan menolak
   `doc.user != session.user` (kecuali `AIOS Admin`/`Administrator`).
4. **Data lama:** `user = NULL`. Baris `NULL` hanya terlihat `AIOS Admin`/`Administrator`;
   `permission_query_conditions` untuk `AIOS Client` menolak `NULL` eksplisit.
5. **Hook:** `permission_query_conditions` + `has_permission` aktif di `hooks.py` untuk
   `AIOS Conversation`, `AIOS DB Connection`, `AIOS Agent State`, `Pending Action Draft`;
   `AIOS Message` lewat join `conversation`. `Administrator` tidak disentuh (bypass native).
6. **Test:** `test_authz_user_isolation.py` ditulis ulang sesuai skema nyata — `AIOS Message`
   tanpa `user`/`datetime`, `AIOS DB Connection` tanpa `connection_name`, memakai
   `handle_api_request` (bukan `handle`). Tambah `test_doctype_exists.py` (S2) dan
   cakupan kepemilikan draft.

**Kriteria selesai:** Alpha tidak bisa `get_doc`/`get_list` resource Beta (403/404);
baris `user=NULL` tidak terlihat `AIOS Client`; Alpha tetap bisa akses miliknya; tanpa
sesi → 401; `Administrator`/`AIOS Admin` penuh; draft milik orang lain tidak bisa
di-approve.

**Bukti verifikasi (2026-10-21):**

- `bench --site aios-v16.localhost run-tests --app aios_v1 --module aios_v1.tests.test_authz_user_isolation` → **8/8 OK**: Alpha ditolak `403/404`, daftar Beta kosong, resource sendiri lolos, tanpa sesi `401`, `Administrator` lolos, draft Beta tidak bisa di-approve Alpha, draft baru terikat ke sesi.
- Test P0/P1 modular: `test_authz_dispatcher` **5/5**, `test_authz_write` **6/6**, `test_conversation_manager` **3/3**, `test_draft_flow` **3/3**, `test_permissions_installer` **4/4** — semua OK.
- `pytest -q` → **41 passed, 2 skipped, 10 xfailed, 1 xpassed** (xpass = doctype count 13, target #2; `strict=False`).
- `bench --site aios-v16.localhost migrate` → sukses; `Pending Action Draft` terdaftar; `Custom DocPerm` `AIOS Client`/`AIOS Admin` terpasang untuk 5 doctype.

**Catatan regression-before-fix:** test lama di-`@unittest.skip` dan membuat field yang tidak ada (`datetime`, `connection_name`, `user` di Message), jadi kegagalannya dulu adalah kegagalan skema, bukan bukti izin. Bukti izin diambil dari test baru yang lulus + hook terpasang, bukan dari test lama.

**Deviasi transisi yang dicatat:** `AIOS DB Connection` sementara punya `tenant` + `user`.
Dihapus di #4a setelah #7 menyediakan injeksi `user_id` dari sesi.

**Non-scope Tahap C:** hapus `AIOS Tenant`, `AIOS Token Usage`, `AIOS Setting.default_company`,
matriks `Custom DocPerm` ERPNext (#4b), audit 30 `get_all` → `get_list`, dan konversi
`tenant_id` di 9 modul tool (232 titik — #4a/#7).

---

### #4a — `refactor/frappe-identity-doctypes` 🏗️

Bagian 1 dari 3 (dari saran reviewer: "#4 terlalu besar").

- **Hapus DocType `AIOS Tenant` & Ganti Seluruh Relasi `tenant` Menjadi `user -> Link(User)`:**
  - Sesuai arahan arsitektur **`1 Client = 1 Site`**, 1 site Frappe adalah 1 perusahaan klien, sehingga DocType `AIOS Tenant` dihapus sepenuhnya.
  - **Bersihkan referensi kode hidup ke `tabAIOS Tenant`:** hapus/ganti query SQL mentah `FROM \`tabAIOS Tenant\` t` di `aios_v1/lib/monitoring_service.py:281` dan `dispatcher.py:708,749,751,802,932` menjadi pembacaan `User` + **`AIOS Token Usage`** agar `/api/monitoring/usage` tidak melempar `ProgrammingError: table not found` setelah `migrate_schema.py` dihapus di #2.
  - Tambah field `default_company` (`Link -> Company`), `company_context_persona` (`Small Text`), `default_user_token_limit` (`Int`), `site_token_limit` (`Int`), `site_tokens_used` (`Int`, `read_only=1`), `max_users` (`Int`), dan `default_max_tokens` (`Int`) pada Single DocType **`AIOS Setting`**.
  - Buat DocType **`AIOS Token Usage`** (`user -> Link(User)`, `conversation -> Link(AIOS Conversation)`, `branch`, `agent_key`, `provider`, `model_id`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `estimated_cost_usd`).
  - **Atur permission role `AIOS Client` / `AIOS Admin` pada seluruh doctype AIOS & ERPNext sesuai klasifikasi relasi `User`:**
    1. **Punya field langsung `user -> Link(User)` (5):** `AIOS Conversation`, `AIOS DB Connection`, `AIOS Agent State`, **`Pending Action Draft`** (dibuat di Tahap C; field kepemilikannya sudah `user -> Link(User)`), dan **`AIOS Token Usage`** (`read=1` saja untuk `AIOS Client`, insert via service backend).
    2. **Terhubung lewat 1-hop join (tanpa field `user` langsung) (3):**
       - `AIOS Message` → via `conversation -> Link(AIOS Conversation)`
       - `AIOS Mapping` → via `connection -> Link(AIOS DB Connection)`
       - `AIOS Schema Snapshot` → via `connection -> Link(AIOS DB Connection)`
    3. **Terhubung lewat 2-hop join (1):** `AIOS Mapping Entry` → via `mapping -> AIOS Mapping -> connection -> AIOS DB Connection`
    4. **Single DocType rahasia/konfigurasi (`issingle=1`) (2):** `AIOS Setting` (menyimpan `api_key` LLM & default site) & `AIOS Telegram Setting` (menyimpan `bot_token`) → **JANGAN beri permission baca ke `AIOS Client`** (hanya `System Manager` / `AIOS Admin` sesuai kebutuhan)
    5. **DocType Telegram (2):** `AIOS Telegram Session` & `AIOS Telegram Message` (hanya untuk `AIOS Admin`)
    6. **`Custom DocPerm` (`read=1, report=1`) untuk `AIOS Client` pada DocType ERPNext target Finance & Sales:** di-script di `after_install` & `after_migrate` via `add_permission` + `update_permission_property` (`frappe/permissions.py:659,693`) untuk `Company`, `Customer`, `Item`, `Sales Order`, `Delivery Note`, `Sales Invoice`, `Purchase Order`, `Purchase Invoice`, `Payment Entry`, `Journal Entry`, `GL Entry`, `Stock Ledger Entry`, `Account`, `Cost Center`, `Fiscal Year`, `Warehouse`, `Quotation`. *(Wajib `report=1` karena `frappe/desk/query_report.py:289` mengecek `frappe.has_permission(report.ref_doctype, "report")`)*
- Hook `permission_query_conditions` (**wajib eksplisit menolak `user IS NULL` untuk role `AIOS Client`**):
  - `AIOS Conversation`, `AIOS DB Connection`, `AIOS Agent State`, `Pending Action Draft`, `AIOS Token Usage` → untuk `AIOS Client`, filter ketat `\`tab<DocType>\`.user = {frappe.db.escape(user)}` (tolak `NULL`); untuk `AIOS Admin`, akses penuh di site tersebut.
  - `AIOS Message` → **lewat join ke `AIOS Conversation`**
  - `AIOS Mapping`, `AIOS Schema Snapshot` → **lewat join ke `AIOS DB Connection`**
  - `AIOS Mapping Entry` → **lewat join `AIOS Mapping` → `AIOS DB Connection`**
  - DocType transaksi ERPNext (`Sales Order`, `Sales Invoice`, `Payment Entry`, `Journal Entry`, `GL Entry`, dll.) → filter `company = {frappe.db.escape(default_company)}` di mana `default_company` di-resolve via `frappe.db.get_single_value("AIOS Setting", "default_company") or frappe.db.get_single_value("Global Defaults", "default_company")`
- Hook `has_permission` untuk `get_doc` (S3, A13) — `permission_query_conditions`
  **tidak** mencakup `get_doc`, dan semua panggilan `frappe.get_doc(doctype, name, check_permission="read")` wajib menyertakan `check_permission="read"` (`document.py:186`)
- **Audit & konversi selektif 30 `get_all` → `get_list`** + audit 103 `ignore_permissions` satu per satu:
  1. **Jalur background/cron/webhook tanpa sesi user** (`draft_manager.py:7` `expire_old_drafts`, `telegram_service.py:205,307,332`) **tetap memakai `get_all`**, karena tidak ada `frappe.session.user` klien saat dieksekusi worker.
  2. **Query agregasi & pembacaan kamus mapping utuh** (`dispatcher.py:708-830` `/api/monitoring/usage`, `query_engine.py:16,22` pembacaan `AIOS Mapping Entry`) yang dikonversi ke `get_list` **wajib menyertakan `limit_page_length=0`** agar tidak terpotong diam-diam menjadi 20 baris.
  3. **Endpoint daftar percakapan/pesan/draft milik user** memakai `get_list` dengan pagination eksplisit.

> ⚠️ **JEBAKAN KRITIS (`get_all` vs `get_list`):** `get_all` memaksa
> `ignore_permissions=True` **dan** `limit_page_length=0` (`__init__.py:1402`,
> `:1404-1405`), sedangkan `get_list` memakai default **`limit_page_length=20`**.
> Artinya: (1) `db_query.py:676` melewati `build_match_conditions()` kalau
> `ignore_permissions=True`, sehingga konversi `get_all` → `get_list` **dan**
> pencabutan `ignore_permissions=True` wajib dikerjakan bersama; (2) konversi ke
> `get_list` **mengubah perilaku pagination** (terpotong 20 baris) kecuali
> `limit_page_length=0` diset eksplisit pada pemanggil agregasi/mapping.

**Test:** `aios_v1/tests/test_permission_scoping.py` (dua user `AIOS Client`: User A tidak melihat baris User B maupun baris `user=NULL`, dan `AIOS Tenant` sudah tidak dipakai),
`aios_v1/tests/test_message_scoping.py` (Message & Mapping via join), `aios_v1/tests/test_get_doc_permission.py`
(`get_doc` lintas user ditolak + `AIOS Setting` ditolak untuk `AIOS Client`).

---

### #4d — Penyiapan data PoC (ERPNext) · **dikerjakan sebelum #8**

**Bukan branch kode**, tapi prasyarat keras #8 (**L10**): PoC butuh data nyata, bukan mock.

Skrip sudah ditulis: **`aios_v1/setup_poc/seed_erpnext_demo.py`** (560 baris, syntax OK, **belum pernah dijalankan**)

| Fungsi | Gunanya |
|---|---|
| `status()` | **read-only** — laporkan kondisi site, tidak menulis apa pun |
| `run()` | Fiscal Year → Company dasar → cek idempotensi `<Company> (Demo)` → `setup_demo_data()` → deteksi silent rollback (`Error Log` via timestamp) → verifikasi |
| `clear()` | `clear_demo_data()` — kembalikan ke kondisi sebelum demo (dengan `frappe.log_error` bila gagal) |
| `main()` | alias `run(**kwargs)` |

Cara jalankan (hanya oleh pemilik project via `bench`):

```bash
cd ~/mybench-v16
bench --site aios-v16.localhost backup --with-files          # WAJIB dulu
bench --site aios-v16.localhost execute aios_v1.setup_poc.seed_erpnext_demo.status
bench --site aios-v16.localhost execute aios_v1.setup_poc.seed_erpnext_demo.run
```

Yang dihasilkan (generator resmi ERPNext via `erpnext/hooks.py:100-103` `demo_transaction_doctypes = ["purchase_order", "sales_order"]` + `convert_order_to_invoices()`):
master Item (~10) · Customer (~3) · Supplier (~3) · serta transaksi Sales Order,
Purchase Order, Sales Invoice, Purchase Invoice, Payment Entry, GL Entry, dan Stock Ledger Entry
dengan sebagian order **sengaja dibiarkan unbilled/unpaid** — bagus untuk PoC pertanyaan seperti *"order mana yang belum ditagih?"*.
*(Catatan penting: (1) file `demo_data/journal_entry.json` di ERPNext adalah dead file yang tidak dipanggil `setup_demo_data`, sehingga `Journal Entry` memang 0; (2) generator memakai `randint`, sehingga jumlah dokumen transaksi bervariasi tiap run — semua verifikasi/test wajib memakai **assert range (`>=`)**, bukan exact count.)*

**Jebakan yang sudah ditangani skrip (Nol Silent Error & Nol Hardcode):**
- **Deteksi Silent Rollback (`erpnext/setup/demo.py:23-32`):** `setup_demo_data` membungkus seluruh proses dalam `try...except Exception:` dan melakukan `rollback(save_point="demo_data")` + `log_error()` **tanpa re-raise**. Skrip `run()` mencatat `run_started_at = now_datetime()` sebelum jalan dan memverifikasi `Sales Order > 0` serta `GL Entry > 0` di `<Company> (Demo)` pasca-run; bila `0`, skrip menarik seluruh entri `Error Log` dengan `creation >= run_started_at` (tanpa hardcode judul) dan memanggil `frappe.throw(...)`
- **Nol Silent Exception di Helper:** `_active_fiscal_years()`, `_count()`, dan `clear()` tidak menelan exception; bila gagal, mencatat ke `frappe.log_error(title=..., message=frappe.get_traceback())` dan melempar ulang (`raise`)
- **Resolusi Dinamis Tanpa Hardcode (`Country` → `Currency` & COA):** `Currency` diambil dinamis dari `frappe.db.get_value("Country", country, "default_currency")`, dan template Chart of Accounts diambil dinamis via fungsi resmi ERPNext `get_charts_for_country(country)` (`chart_of_accounts.py`); `run(...)` juga menerima parameter kustom lewat `--kwargs` maupun `frappe.conf`
- **Idempotensi `<Company> (Demo)` (`demo.py:86`):** bila `<Company> (Demo)` sudah ada dan memiliki transaksi (`Sales Order > 0`), `run()` melewati `setup_demo_data()` agar tidak memicu `DuplicateEntryError`
- `setup_demo_data` **membuat salinan** Company bernama `<Company> (Demo)`
  (`demo.py:82-95`) → Company dasar hanya jadi cetakan
- Butuh **Fiscal Year aktif**, kalau tidak → `FiscalYearError` (`demo.py:123-130`)
- Butuh **≥ 4 warehouse non-group**, karena `warehouses[randint(0, 3)]`
  (`demo.py:254`) → kalau kurang = `IndexError`. `create_default_warehouses()`
  (`company.py:383-390`) otomatis membuat 4 (Stores, WIP, Finished Goods, Goods In Transit) **hanya bila `Warehouse Type = "Transit"` ada**; skrip memverifikasi keberadaan `"Transit"` dan jumlah warehouse `>= 4` sebelum jalan

**Test:** `aios_v1/tests/test_poc_data_available.py` — assert range (`count >= N`, bukan exact count karena `randint`) bahwa `Item`/`Sales Order`/`GL Entry` punya baris di Company demo; di-skip otomatis kalau site belum di-seed.

---

### #4b — `refactor/frappe-identity-auth` 🏗️

Bagian 2 dari 3.

- **[AKSI PERTAMA — prasyarat]** Daftarkan Role, Role Profile, Custom Field `User`, dan `Custom DocPerm` melalui script Python pada hook **`after_install` dan `after_migrate`** di `hooks.py` (**BUKAN `fixtures` JSON**):
  - Di `hooks.py`, pastikan keduanya terpasang:
    ```python
    after_install = "aios_v1.setup.after_install"
    after_migrate = "aios_v1.setup.after_migrate"
    ```
  - Gunakan fungsi resmi **`create_custom_fields(custom_fields, update=True)`** dari `frappe.custom.doctype.custom_field.custom_field`, diikuti `frappe.clear_cache(doctype="User")` dan `frappe.db.updatedb("User")` secara eksplisit (dilarang keras memakai `frappe.get_doc("DocType", "User").append("fields", ...)` yang mengotori `tabDocField`).
  - **Custom Field yang di-script pada `User` (6 field, tipe data terkunci permanen karena `CustomField.validate` menolak perubahan `fieldtype` di luar `ALLOWED_FIELDTYPE_CHANGE`):**
    1. `aios_persona` (`Select`: `\nexecutive\nfinance\nsales\noperations\nsystem`)
    2. `aios_persona_context` (`Small Text` — instruksi tambahan per user)
    3. `aios_status` (`Select`: `Pending Provisioning\nActive\nSuspended`, `default="Pending Provisioning"`)
    4. `aios_company_name` (`Data`)
    5. `aios_token_limit` (`Int`)
    6. `aios_tokens_used` (`Int`, `read_only=1`)
  - **Role, Role Profile, & `Custom DocPerm` yang di-script pada `after_install` & `after_migrate`:**
    1. Role `AIOS Admin` (`desk_access = 1`) & `AIOS Client` (**WAJIB `desk_access = 0`** — karena `role.json:33-42` default `1` dan `user.py:415` mengubah user menjadi `System User` bila ada role dengan `desk_access == 1`)
    2. Role Profile `AIOS Admin Profile` & `AIOS Client Profile` (di-assign ke `User.role_profiles` Table MultiSelect)
    3. `Custom DocPerm` (`read=1, report=1`) untuk `AIOS Client` pada ke-17 DocType ERPNext target Finance & Sales via `add_permission` + `update_permission_property` (`frappe/permissions.py:659,693`)
  - **Test:** `aios_v1/tests/test_setup_hooks_schema.py` (assert `after_install` & `after_migrate` terdaftar di `hooks.py`, tidak ada key `fixtures`, `create_custom_fields` membuat ke-6 Custom Field di `tabCustom Field` untuk `User`, `AIOS Client` memiliki `desk_access == 0`, dan `Custom DocPerm` `read=1, report=1` terpasang).
- Buang `lib/auth.py` (89 LOC) — session sendiri, scrypt sendiri, `portal_from_request` (menutup N6), serta ganti referensi `AIOS Tenant` di `dispatcher.py:208,255,258` dengan pembacaan `User`
- Cookie `aios_session` → `sid` Frappe; login → `/api/method/login` bawaan
- **Rename role**: `DEVELOPER` → **`AIOS Admin`**, `CLIENT` → **`AIOS Client`**
- `Website User` untuk klien (tidak menambah seat desk karena `AIOS Client` memiliki `desk_access = 0`)
- **Mekanisme konkret CSRF untuk sesi API (menutup S7):** karena `POST /api/method/login` tidak mengembalikan `csrf_token` dan `validate_csrf_token` (`auth.py:87`) melewati cek bila `frappe.session.data.csrf_token` kosong, tambahkan endpoint bootstrap `@frappe.whitelist()` (mis. `get_session_context() -> dict`) atau `on_login` hook yang memanggil `frappe.sessions.get_csrf_token()` (`sessions.py:197-205`). Ini memastikan `csrf_token` ter-generate di Redis session dan dikembalikan ke frontend untuk dikirim via header `X-Frappe-CSRF-Token`
- **Alur Registrasi Mandiri Klien (`/aios/register`) dengan Status `Pending Provisioning` & Pertahanan 3 Lapis (menutup N4 & S10):**
  - Sesuai konsep **`1 Client = 1 Site`**, ketika calon klien mendaftar sendiri di `/aios/register` (Nama, Email, Password, Nama Perusahaan), instance site baru tidak bisa langsung ready dalam 1 request.
  - Saat registrasi valid (dengan rate limit dan tanpa enumerasi email):
    1. Membuat record `User` bawaan Frappe dengan `AIOS Client Profile` (`Website User`, `desk_access = 0`).
    2. **Lapis 1 (Cegah kebocoran email reset password):** set `user_doc.send_welcome_email = 0` dan `user_doc.flags.no_welcome_mail = True` sebelum `.insert()` (karena `user.json:180` default `send_welcome_email = 1` yang memicu pengiriman link `/update-password?key=...` di `user.py:463-467`).
    3. **Lapis 2 (Sinkronisasi `aios_status` ↔ `enabled`):** mengisi `User.aios_status = "Pending Provisioning"`, `User.enabled = 0`, `User.aios_company_name = company_name`, `User.aios_token_limit = AIOS Setting.default_user_token_limit`, dan `User.aios_tokens_used = 0`. Di `doc_events["User"]["validate"]`, bila user memiliki role `AIOS Client`, paksa `doc.enabled = 1 if doc.aios_status == "Active" else 0`.
    4. **Lapis 3 (Guard `on_login` & `auth_hooks`):** pasang `on_login` (`auth.py:172`) dan `auth_hooks` (`auth.py:750`) yang membaca `frappe.db.get_value("User", login_manager.user, "aios_status")` (bukan `frappe.session.data`) dan melempar `frappe.AuthenticationError` bila user `AIOS Client` memiliki `aios_status != "Active"`.
    5. **Tidak** membuat `AIOS Tenant`, **tidak** membuat `Company` ERPNext secara paksa di dalam request publik tersebut, dan **tidak** langsung *auto-login* ke `/aios`.
    6. Mengembalikan status `"PENDING_PROVISIONING"` agar UI menampilkan layar *"Pendaftaran Diterima — Instance Site Anda Sedang Disiapkan"*.
  - Hapus `/api/payment/status` hardcoded `ACTIVE`.
- Rate limit & lockout: `LoginAttemptTracker` (`auth.py:530`) + `System Settings` (menutup S9)
- **Tunda** CSRF/CORS/seed-creds (S6, S7, S8) dari #1 ke sini

**Test:** `aios_v1/tests/test_setup_hooks_schema.py`, `aios_v1/tests/test_login_flow.py`, `aios_v1/tests/test_role_portal.py`,
`aios_v1/tests/test_website_user_access.py` (verifikasi `AIOS Client` bertipe `Website User` dengan `desk_access == 0` dan bisa memanggil
`@frappe.whitelist` — terverifikasi secara source: `is_whitelisted` hanya menolak
`Guest`), `aios_v1/tests/test_persona_per_user.py`, `aios_v1/tests/test_lockout.py`, `aios_v1/tests/test_self_register_pending_provisioning.py` (verifikasi *Self-Register* membuat `User` dengan `aios_status == "Pending Provisioning"` tanpa `AIOS Tenant` dan menolak akses `/aios` sebelum aktif).

---

### #4c — `refactor/frappe-identity-ui` 🏗️

Bagian 3 dari 3.

- Frontend: halaman Sign Up mandiri klien (`/aios/register` yang menampilkan layar *Pending Provisioning* pasca-daftar) dan Login lewat Frappe, baca role (`AIOS Admin` vs `AIOS Client`) dan `aios_status` dari endpoint session bootstrap (bukan `role_home_page`, yang hanya memengaruhi halaman web Frappe)
- Tangani `sid` lintas port (8083 ↔ 8084 via proxy Next.js) + ambil `csrf_token` dari `get_session_context()` pasca-login dan kirim di `X-Frappe-CSRF-Token`
- Arahkan tampilan UI otomatis berdasarkan role: `AIOS Admin` ke Portal Admin (konfigurasi Provider/Model, Plugin/MCP, manajemen `User` & kuota token) dan `AIOS Client` ke Workspace Bisnis (Finance & Sales)

**Test:** `aios_v1/tests/test_frontend_contract.py` — kontrak endpoint (termasuk keberadaan `csrf_token` di session context); test e2e opsional.

---

### #5 — `feat/site-and-user-quota` · ikut #4

- Field standar `max_users` (`Int`) dan `default_user_token_limit` (`Int`) disimpan di Single DocType **`AIOS Setting`** (sedangkan `aios_token_limit` dan `aios_tokens_used` menempel di **`User`** via `create_custom_fields` pada `after_install` & `after_migrate` di #4b).
- Saat `User` dibuat (`before_insert`), jika `doc.aios_token_limit` belum diisi, otomatis disalin secara dinamis dari `AIOS Setting.default_user_token_limit`.
- Validasi batas jumlah user aktif di site pada `User.before_insert` + `User.validate` (via `doc_events` di `hooks.py`) → `frappe.db.count("User", {"enabled": 1, "aios_status": "Active", "name": ["!=", doc.name]})` dibandingkan dengan `AIOS Setting.max_users`.
- Klien = `Website User` (`desk_access = 0`), Operator = `AIOS Admin`.

**Alasan `before_insert` + `validate`, bukan dispatcher:** berlaku di semua jalur (UI, API, import, maupun saat re-enable user).
Dispatcher bisa dilewati lewat `/app/user/new`.

**Primitif:** `get_total_users()` (`user.py:1211`), `get_system_users()` (`:1225`) —
`Website User` dikecualikan dari seat Desk Frappe (`:1236`).

**Test:** `aios_v1/tests/test_site_user_quota.py` — buat user aktif ke-N+1 harus **ditolak**,
lewat tiga jalur (API, `frappe.client.insert`, langsung `doc.insert`), serta verifikasi `User.aios_token_limit` otomatis mewarisi `AIOS Setting.default_user_token_limit`.

---

### #6 — `chore/extract-constants` · kecil

- `frontend/next.config.ts:13` hardcode `127.0.0.1:8083` → env var
- `lib/pricing.py`: `PRICING = {...}` (sekarang tersebar di `dispatcher.py:745` dst)
- `MAX_LIMIT`, `MAX_CHAIN_DEPTH`, `CIRCUIT_BREAKER_THRESHOLD` → konstanta bernama
- Hapus port literal `8083`/`8084`/`8085` dan nilai konfigurasi/host/path yang masih di-hardcode di file produksi maupun test

**Yang TETAP di kode sebagai konstanta bernama satu tempat:** harga token dasar, threshold circuit breaker, limit baris query.

**Test:** `aios_v1/tests/test_no_hardcoded_env.py` — grep penanda port/path absolut/konfigurasi di source
(assert tidak ada), `aios_v1/tests/test_pricing_constants.py`.

---

### #7 — `fix/llm-tool-sandbox` 🆕 · **SEBELUM #8**

**Prasyarat #8.** Konteks: LLM akan menjalankan tool terhadap data keuangan klien.
Status per lapisan ada di §4 🟣. Yang harus dikerjakan:

| Lapisan | Aksi | Test |
|---|---|---|
| **L5** | Validasi `aggregate.fn` ke whitelist `{COUNT,SUM,AVG,MIN,MAX}` — **celah terverifikasi** (`data_access/query_engine.py:93-103`) | `test_sql_readonly_guard.py` |
| **L6** | Read-only berlapis di `data_access/adapters/{sqlite,postgres,mysql}_adapter.py`: (1) level koneksi/driver (`sqlite3.connect(f"file:{path}?mode=ro", uri=True)` + `PRAGMA query_only = ON`; Postgres `conn.set_session(readonly=True, autocommit=True)`; MySQL `SET SESSION TRANSACTION READ ONLY`); (2) validasi statement tunggal & blokir `INTO`/`ATTACH`/`OUTFILE`/stacked; (3) wajib `frappe.log_error` bila query gagal | `test_sql_readonly_guard.py` |
| **L7** | Konteks `User` & `Company` di lapisan tool: `execute_tool` menyuntikkan `user_id = frappe.session.user` dari sesi server (mengabaikan klaim dari argumen LLM), lalu meresolusi `allowed_company` secara **100% dinamis dari Single DocType site** via `frappe.db.get_single_value("AIOS Setting", "default_company") or frappe.db.get_single_value("Global Defaults", "default_company")` (**dilarang memakai `frappe.db.get_default`** yang per-user, dan **dilarang keras hardcode nama company** di kode Python; bila kosong, catat `frappe.log_error` & tolak akses) | `test_tool_user_and_company_boundary.py` |
| **L8** | Buat modul akuntansi token **`aios_v1/services/usage.py`** (`check_user_token_quota` & `record_token_usage`) untuk kuota token per `User` (`User.aios_tokens_used` vs `User.aios_token_limit`) & `AIOS Setting.site_token_limit` + **bereskan A12**: kirim `"stream_options": {"include_usage": True}` di `lib/llm_client.py:39-43` (dan ganti `except Exception: continue` di `:70` dengan `frappe.log_error`), akumulasikan `usage` di seluruh putaran loop `tool_calls` pada `managers/base_manager.py:201,220`, catat log ke `AIOS Token Usage`, dan **update `User.aios_tokens_used` secara atomik via SQL (`UPDATE \`tabUser\` SET aios_tokens_used = COALESCE(aios_tokens_used, 0) + %s WHERE name = %s`)** — dilarang memakai `user_doc.save()` yang rentan *race condition* & memicu `User.on_update` berat | `test_llm_cost_quota.py` |
| **L9** | Selesaikan alur approval operasi tulis (DocType JSON `Pending Action Draft` sudah dibuat di **Tahap C**): wajibkan write-tool melewati `create_draft()` dengan `user = frappe.session.user` terisi + bereskan 2 TODO eksekusi/notifikasi di `lib/draft_manager.py:42,60` | `test_draft_approval_flow.py` |

Sudah aman, **jangan diutak-atik**: L1–L4 (tidak ada SQL mentah, value
parameterized, whitelist tool per worker, nol akses OS).

**Verifikasi:** satu cabang ERP (**finance**) end-to-end **sebelum** #8 membuka semua.
Ini juga jawaban untuk kritik reviewer bahwa "70% mati bukan bukti nilai" — bukti
nilainya harus ditunjukkan per-cabang, bukan per-LOC.

---

### #8 — `feat/erpnext-tool-poc` 🚀 · Jembatan ke Roadmap Pengembangan Harness (`docs/06`)

**Disempitkan & Diperdalam (*Depth over Breadth*): ERPNext-first pada 2 cabang inti yang saling berelasi (`finance` & `sales` — siklus *Order-to-Cash*).**
**Prasyarat keras:** `#1` (auth & IDOR darurat pada `/stream`), `#4d` (backup site + `seed_erpnext_demo.run`), dan `#7` (sandbox LLM) **wajib selesai lebih dulu** (L10).

> **Catatan Arsitektur Harness:** Rincian lengkap pengembangan kapabilitas *Business AI Harness* (Multi-Provider & Per-Agent Model Routing UI, Plugin/MCP Manager & 7 Built-in Default Plugins, Delegasi Sub-Agent Nyata + Konsultasi Lintas Divisi `Sales ↔ Finance` dengan *Live Agent Trace*, serta *Isolated Workspace & 5-Tier Artifact/Canvas Space*) dijabarkan secara mendalam di **[`docs/06-roadmap-pengembangan-harness.md`](./06-roadmap-pengembangan-harness.md)** (Tahap `H1` s/d `H5`).

**Kenapa ERPNext dulu (Finance & Sales):**
- Tool lama mengembalikan **angka karangan** (`finance_tools.py`: `remaining_budget:
  180000000`, `total_payables: 280000000`; `sales_tools.py`: `credit_limit = 100000000.0`). Kalau ditunjukkan sebagai PoC, yang terlihat bukan "AIOS menganalisis data" tapi "AIOS mengarang angka".
- ERPNext sudah terpasang; generator data demo resmi tersedia → data **nyata** &
  bisa di-query langsung maupun lewat *Standard Query Reports* ERPNext.
- Menghapus N5 (SSRF), S12 (`root` MySQL), A5 (entitas kanonik), A6 (keyword), S11 (`/mnt/g`) dari
  jalur kritis PoC, karena tidak ada koneksi DB eksternal.

**Peran ganda ERPNext:** (1) fondasi *Business AI Harness* untuk `Finance` & `Sales`; (2) **target uji adapter** — MariaDB
ERPNext punya skema nyata, jadi adapter SQLite/MySQL bisa diuji tanpa DB klien
terpisah di masa depan.

**Aksi Fondasi di #8 (sebelum/bersama Tahap H1–H5 di `docs/06`):**
- Bangun plugin bawaan ERPNext Finance & Sales (`erpnext-core-data`, `erpnext-financial-reports`, `erpnext-action-drafts`) yang membaca doctype & query report ERPNext asli (`Sales Order`, `Sales Invoice`, `Payment Entry`, `GL Entry`, `Customer`, `Item`) di mana `allowed_company` diambil dinamis dari `AIOS Setting.default_company` / `Global Defaults` di site tersebut (nol nama company hardcoded di kode; setiap error dicatat via `frappe.log_error(title=..., message=frappe.get_traceback())`, lihat #7 L7)
- `base_manager.py` → kirim `tools=get_tools_schema_for_worker(...)`
- Tangani `tool_calls` + loop eksekusi + umpan balik hasil (serta akumulasi token `usage` lintas putaran ke `User.aios_tokens_used` — L8)
- Pakai `lib/pdf_extractor.py` (121 LOC mati, ganti `logging` biasa dengan `frappe.log_error`) menggantikan duplikasi inline di `dispatcher.py:889-919`

**JANGAN dirombak sekarang:** 7 cabang non-prioritas di `lib/tools/*` yang lama (beserta file test mock lama di `aios_v1/tests/` — **K5**) serta fitur Telegram (`telegram_service.py`) yang di-*hide/dormant* sementara.

**`feat/`, bukan `fix/`** — LLM mulai mengeksekusi tool = perubahan perilaku.

**Test:** `aios_v1/tests/test_erpnext_finance_tools.py` (**100% READ-ONLY** pada data PoC, angka cocok dengan
query langsung), `aios_v1/tests/test_tool_execution_loop.py`.

---

### #9 — `refactor/dispatcher-router` · setelah #4b

- Pecah 1.061 baris → router per-domain (<150 baris/file) (A8)
- `_ADAPT_JOBS` → `frappe.cache` atau `frappe.enqueue` (fix multi-worker, A7)
- Hapus `time.sleep(0.8)` per-tabel yang memblokir worker (A7)
- Logika bisnis dari `before_request` → `@frappe.whitelist` methods **wajib type-annotated** (`require_type_annotated_api_methods = True` di `hooks.py:275`), serta **hapus panggilan `frappe.db.commit()` manual** di request handler (biarkan siklus request Frappe yang otomatis commit saat sukses dan rollback saat exception)
- **A10**: pindahkan polling Telegram manual (`lib/telegram_service.py:769`) ke `scheduler_events` Frappe (`single_run=True`) atau webhook terkelola
- **K8**: bersihkan seluruh sisa `print(` dan `except Exception` tanpa log di modul produksi hidup (`dispatcher`, `managers`, `lib`, `data_access`) → setiap tangkapan exception wajib mencatat `frappe.log_error(title=..., message=frappe.get_traceback())` atau melempar exception spesifik ke handler Frappe

**Test:** semua test #1 dan #4a harus tetap hijau (regression). Tambah
`aios_v1/tests/test_adapt_jobs_multiprocess.py`.

---

### #10 — `docs/status-reality` · 30 menit

README + tabel status jujur: apa yang jalan, apa yang belum tersambung (termasuk status adapter DB klien yang ditunda, cabang non-finance yang masih mock, dan mekanisme servis Telegram **A10** bila masih manual saat itu).
(Tidak 5 menit — perlu verifikasi klaim.)

---

## 6. Strategi Test

**Aturan:** tidak ada branch dianggap selesai tanpa test yang membuktikan klaimnya.

> **Lokasi test (revisi 7 — WAJIB):** seluruh `test_*.py` baru hidup di **paket dalam `aios_v1/tests/`**
> (yaitu `apps/aios_v1/aios_v1/tests/`), **bukan** `tests/` di root app. Sebab: `bench run-tests`
> hanya me-walk `frappe.get_app_path(app)` = paket dalam (`apps/aios_v1/aios_v1`), sehingga
> `tests/` di root app tidak pernah dieksekusi `bench`. Pola sama dipakai
> `apps/ekasa_logbook/ekasa_logbook/tests/` yang sudah berjalan di mesin ini.
> Semua path di §6a relatif ke root repo (`apps/aios_v1/`).

### 6a. Peta branch → test

| Branch | File test | Apa yang dibuktikan |
|---|---|---|
| #0 | `test_import_smoke.py` | seluruh modul via `rglob("*.py")` bisa di-import + restore `sys.path`; **baseline terukur: 149 OK / 11 gagal** (`demo_tahap*`, target #3). Denominator dihitung dinamis — **tidak** di-hardcode |
| #0 | `test_app_structure.py` | kontrak struktur app (merah di #0, hijau di #2) |
| #1 | `test_endpoint_auth.py` | setiap endpoint AIOS tanpa sesi → 401 |
| #1 | `test_authz_user_isolation.py` | cookie A → resource B → 403 (IDOR N2, S3 `parts[4]`, `mapping/validate` `entryId`) |
| #1 | `test_parse_pdf_guard.py` | tanpa sesi ditolak; file >batas ditolak |
| Tahap C | `test_doctype_exists.py` | `Pending Action Draft` ada di repo lengkap dengan field kepemilikan `user -> Link(User)` & `rejection_reason` (S2) |
| Tahap C | `test_authz_dispatcher.py` | `/api/chat`: daftar hanya milik sendiri, detail & `/stream` `conversationId` user lain → 404, tanpa sesi → 401 (N2) |
| Tahap C | `test_authz_write.py` | `AIOS Client` tidak bisa write/delete/create untuk user lain; `AIOS Admin` bisa read/write/delete |
| Tahap C | `test_conversation_manager.py` | `ensure_conversation` membuat/mereuse percakapan milik user sesi, tidak mereuse milik user lain |
| Tahap C | `test_draft_flow.py` | approve/reject draft sendiri, `rejection_reason` tersimpan, Guest ditolak |
| Tahap C | `test_permissions_installer.py` | `ensure_aios_permissions` idempoten; matriks `AIOS Client`/`AIOS Admin` |
| Tahap C | `test_draft_contract.py` | `draft_manager` tanpa `allow_guest`, memakai `check_permission` (S1) |
| #1 | `test_register_enumeration.py` | respons tidak membedakan email terdaftar/tidak |
| #1 | `test_payment_gate.py` | `ACTIVE` tidak hardcoded |
| #1 | `test_db_connection_ssrf.py` | host/IP privat ditolak + tidak ada default `user="root"` (N5, S12) |
| #1 | `test_no_machine_paths.py` | tidak ada `/mnt/g`, `/home/<user>` di source |
| #2 | `test_app_structure.py` | hijau: tidak ada pohon serakan, 16 skrip K3 & `aios_web_handler.html` (A11) hilang |
| #3 | `test_repo_hygiene.py` | tidak ada artifact/`demo_tahap*` ter-track, tidak ada emoji dekoratif di `branches.ts`/`ChatDock.tsx`, rule `ruff` K9 + `S110`/`BLE001` aktif & lolos, AST zero silent except, AST nol `frappe.db.commit()` di file test |
| #4a | `test_permission_scoping.py` | User A (`AIOS Client`) tidak melihat baris User B maupun baris `user=NULL` (termasuk `AIOS Token Usage`); `AIOS Tenant` & `monitoring_service.py` legacy dihapus |
| #4a | `test_message_scoping.py` | scoping Message/Mapping/Snapshot via join 1-hop & 2-hop berbasis `user` |
| #4a | `test_get_doc_permission.py` | `get_doc(..., check_permission="read")` lintas user ditolak + `AIOS Setting` ditolak untuk `AIOS Client` |
| #4b | `test_setup_hooks_schema.py` | `after_install` & `after_migrate` di `hooks.py` membuat Role (`AIOS Client` `desk_access=0`), Role Profile, `Custom DocPerm` (`read=1, report=1`), & ke-6 Custom Field di `User` via `create_custom_fields` (tanpa `fixtures`) |
| #4b | `test_login_flow.py` | login via Frappe, guard 3 lapis `aios_status == "Active"` (`enabled`, `on_login`, `auth_hooks`), sesi `sid` + bootstrap `csrf_token` |
| #4b | `test_role_portal.py` | portal dari role (`AIOS Admin`/`AIOS Client`), bukan port |
| #4b | `test_website_user_access.py` | `AIOS Client` bertipe `Website User` (`desk_access=0`) & bisa panggil whitelist |
| #4b | `test_persona_per_user.py` | `User.aios_persona` & `User.aios_persona_context` ditambahkan ke prompt |
| #4b | `test_lockout.py` | lockout Frappe aktif |
| #4b | `test_self_register_pending_provisioning.py` | registrasi mandiri membuat `User` (`aios_status = "Pending Provisioning"`, `enabled = 0`, `send_welcome_email = 0`, tanpa `AIOS Tenant`) dan tidak bisa langsung masuk `/aios` |
| #4c | `test_frontend_contract.py` | kontrak endpoint untuk UI (termasuk `csrf_token`) |
| #5 | `test_site_user_quota.py` | user aktif ke-N+1 ditolak di 3 jalur + `User.aios_token_limit` mewarisi `AIOS Setting.default_user_token_limit` |
| #6 | `test_no_hardcoded_env.py`, `test_pricing_constants.py` | tidak ada port/path literal |
| **#4d** | `test_poc_data_available.py` | **100% READ-ONLY:** data ERPNext ada (`Item`/`Sales Order`/`GL Entry`) pakai **assert range (`>=`)** karena `randint` — **skip** kalau belum seed |
| #7 | `test_sql_readonly_guard.py` | `aggregate.fn` ditolak di luar whitelist; koneksi read-only; stacked/`UNION`/`ATTACH`/`INTO` diblokir |
| #7 | `test_tool_user_and_company_boundary.py` | `execute_tool` injeksi `user_id` sesi & resolusi `default_company` site via `get_single_value` |
| #7 | `test_llm_cost_quota.py` | kuota token per `User` (`aios_tokens_used` vs `aios_token_limit`) via `aios_v1/services/usage.py` (update SQL atomik) + akuntansi token akurat (`stream_options.include_usage` lintas putaran tool, A12) |
| #7 | `test_draft_approval_flow.py` | write-tool membuat `Pending Action Draft` terikat ke `user` & alur approve/reject jalan (L9) |
| **#8** | `test_erpnext_finance_tools.py` | **100% READ-ONLY pada data NYATA** — angka tool == hasil query langsung ke ERPNext |
| #8 | `test_tool_execution_loop.py` | LLM memanggil tool, hasil kembali ke prompt |
| #9 | `test_adapt_jobs_multiprocess.py` + regression | tidak ada yang pecah; job adaptasi aman lintas worker |

**Ditunda bersama jalur adapter DB klien** (bukan dihapus) — hanya relevan kalau
adapter SQLite/MySQL ke DB klien dipakai lagi:

| Branch | File test | Apa yang dibuktikan |
|---|---|---|
| nanti | `test_canonical_entities.py` | entitas yang ditanyakan ada di kamus kanonik (A5) |
| nanti | `test_keyword_matching.py` | `"pembelian"` tidak memicu SalesOrder (A6) |

### 6b. Dua kelas test & Jaminan Isolasi Database (Zero Data Pollution)

| Kelas | Butuh DB? | Basis | Contoh |
|---|---|---|---|
| **Statis** | tidak | `unittest.TestCase` + AST/grep | smoke import, struktur app, path literal, konstanta |
| **Integrasi** | ya | `frappe.tests.IntegrationTestCase` | scoping, IDOR, quota, login |

`IntegrationTestCase` (dari `frappe.tests`) menyediakan `setUpClass`/`tearDownClass`
+ rollback transaksi otomatis. Gunakan itu, jangan bootstrap manual seperti
13 test lama yang tidak bisa jalan (K5). Agar **tidak ada satu pun test yang merusak,
mengubah, atau mengotori data DocType/Company/User yang sudah ada di site**, tiga
aturan isolasi berikut **WAJIB** diterapkan di seluruh test integrasi:

1. **Wajib Entitas Dummy (`_Test ...`) untuk Semua Test Fitur/Mutasi:**
   - Seluruh test fitur (`#1`, `#4a`, `#4b`, `#4c`, `#5`, `#7`) **wajib membuat record dummy terisolasi sendiri** dengan prefiks `_Test` (mis. `_Test User Alpha`, `_Test User Beta`, `_Test Company AIOS`).
   - **Dilarang keras** menggunakan, mengubah, atau menghapus record `Company` atau `User` nyata yang sudah ada di database.
2. **Test Data PoC (`#4d` & `#8`) Bersifat 100% Read-Only:**
   - Hanya `test_poc_data_available.py` (#4d) dan `test_erpnext_finance_tools.py` (#8) yang boleh membaca `PT Demo AIOS (Demo)`, dan keduanya **wajib murni `SELECT` / `get_list` / `count`** (nol `.insert()`, `.save()`, `.set_value()`, atau `.delete()`).
3. **Monkeypatch `frappe.db.commit` selama Test Berjalan (Penangkal 87 `db.commit()` Manual di Kode AIOS):**
   - Kode AIOS lama memanggil `frappe.db.commit()` secara manual di **87 titik** (`dispatcher.py`, `base_manager.py`, `draft_manager.py`, dll.). Di MariaDB, pemanggilan `frappe.db.commit()` di tengah jalan langsung menyimpan transaksi ke disk dan **membatalkan `frappe.db.rollback()` otomatis milik `IntegrationTestCase`**!
   - Karena itu, base test class / fixture untuk test integrasi **wajib men-*monkeypatch* `frappe.db.commit` menjadi *no-op*** selama test dieksekusi dan memanggil `frappe.db.rollback()` di `tearDown`.
   - File `test_*.py` **dilarang keras** memanggil `frappe.db.commit()` (dijaga otomatis oleh AST check di `aios_v1/tests/test_repo_hygiene.py`).

### 6c. Test keamanan isolasi antar-`User` — baseline

Permintaan reviewer, dan **paling penting**: ini mengubah klaim keamanan dari
"hasil baca statis" jadi bukti.

> **Catatan istilah (revisi 7):** karena multi-tenant berada di level **Site**
> (`1 Client = 1 Site`) dan `AIOS Tenant` sudah dihapus (§2), baseline ini **tidak**
> membuat "tenant A/B" di dalam satu database — ia membuat **dua `User` (`AIOS Client`)
> di site yang sama** dan membuktikan isolasi baris antar-`User`. Uji ini
> **tidak** menggantikan pengujian isolasi lintas-site (itu dijamin fisik oleh
> `dns_multitenant` + database terpisah, di luar cakupan CI).

`test_authz_user_isolation.py` harus:
1. Buat `_Test User Alpha` + `_Test User Beta` (role `AIOS Client`) di site yang sama
2. Login sebagai Alpha
3. Coba akses setiap resource milik Beta (conversation, message, connection, draft)
4. Assert **403/404**, bukan 200
5. Ulangi **tanpa** cookie → assert 401

> **Koreksi skema (Tahap C):** versi test saat ini membuat `AIOS Conversation` dengan
> `datetime`, `AIOS Message` dengan `user`, dan `AIOS DB Connection` dengan
> `connection_name` — ketiganya tidak ada di doctype, sehingga test gagal karena field,
> bukan karena izin. Saat ditulis ulang: `AIOS Message` tanpa `user` (1-hop lewat
> `conversation`), `AIOS Conversation` tanpa `datetime`, `AIOS DB Connection` tanpa
> `connection_name`, dan impor `handle_api_request` (bukan `handle`).

Jalankan **sebelum** #1 (harus merah) dan **sesudah** #1 (harus hijau). Itu buktinya.

---

## 7. Urutan & Timeline

```
#0  →  #1  →  #2  →  #3            ≈ seminggu       ← repo sehat, lubang kritis tertutup
#4d (data PoC)                     kapan saja        ← prasyarat #8
#7  →  #8 (finance)                setelah #1 & #4d  ← sandbox dulu, baru tool ERPNext
#4a →  #4b →  #4c →  #5            pekerjaan besar   ← fondasi identity
#6, #10                            kapan saja
#9                                 setelah #4b
```

> **Catatan urutan:** Setelah **#0** dan **#1** selesai, jalur PoC (**#4d → #7 → #8**)
> **bisa jalan paralel** dengan jalur pembersihan/identity (**#2 → #3 → #4a–#4c**).
> **Penting:** `#1` **wajib** selesai sebelum `#8` dinyalakan agar eksekusi tool ERPNext
> tidak terekspos ke `/stream` tanpa sesi (`S5`) atau IDOR `conversationId` (`N2`).
> Jadi jalur tercepat yang aman menuju PoC: **#0 → #1 → #4d → #7 → #8 (finance)**.

**#0–#3 selesai dalam hitungan hari dan menutup semua temuan kritis.**
#4 ke atas adalah pekerjaan produk.

| Branch | Risiko | Boleh digabung? |
|---|---|---|
| #0 CI | rendah | harus pertama |
| #1 keamanan | **sedang-tinggi** | **JANGAN** digabung — review tenggelam di kebisingan diff |
| #2 layout | **tertinggi** | pisah dari #3 |
| #3 hygiene | rendah | boleh besar |
| #4a identity | tinggi | **pecahkan** (dari saran reviewer) |
| #4b identity | tinggi | jangan |
| #4c identity | sedang | setelah #4b |
| #4d data PoC | **rendah** (tapi menulis DB) | **backup dulu** |
| #5 quota | rendah | ikut #4 |
| #6 konstanta | rendah | kapan saja |
| #7 LLM sandbox | tinggi | **sebelum** #8 |
| #8 ERPNext PoC | tinggi | **`feat/`**, bukan `fix/` (wajib setelah #1, #4d, #7) |
| #9 dispatcher | sedang | setelah #4b |
| #10 docs | rendah | kapan saja |

---

## 8. Yang TIDAK Akan Dilakukan

- **Bikin ulang dari nol.** Alasan lama ("70% kode = aset") **diganti**: 70% itu
  mati dan belum pernah dijalankan, jadi LOC bukan bukti nilai. Alasan yang benar:
  **SOP 171 KB + adapter DB + registry layak diselamatkan** (domain knowledge yang
  butuh berminggu-minggu ditulis ulang), dan `git log` 68 commit berisi perbaikan
  nyata (mis. `c278616` hapus backdoor login) yang akan lahir lagi. **Tool layer
  harus dibuktikan satu cabang end-to-end (#7) sebelum dipercaya** — itu yang
  menggantikan klaim LOC.
- **Ubah harga token/threshold jadi config database** — config yang tidak ter-review,
  tidak ter-version, tidak ada test. Lebih buruk.
- **Gabung #1 dengan branch lain** — review keamanan hilang di kebisingan diff.
- **Hapus `registry.py`** — contoh terbaik di project: data terstruktur satu modul.
- **Pasang `rate_limit` di `before_request`** — tidak mungkin, itu decorator
  `@frappe.whitelist` (`rate_limiter.py:104`).
- **Konversi `password_hash` → `Password` tanpa mengubah kode login** — terbukti
  mengunci semua user (§3b).
- **Andalkan `role_home_page` untuk Next.js** — hanya memengaruhi halaman web Frappe.
- **Taruh Custom Field di `fixtures` atau mutasi `tabDocField` lewat `doc.append("fields", ...)`.**
  - Sesuai arahan atasan & pembuktian source Frappe 16 (`frappe/model/__init__.py:103-122` di mana `User` masuk `core_doctypes_list` sehingga ditolak Customize Form UI di `custom_field.py:281-282`), seluruh Custom Field pada `User` wajib di-script menggunakan **`create_custom_fields(custom_fields, update=True)`** (`custom_field.py:322-350`) di dalam hook **`after_install` dan `after_migrate`** pada `hooks.py`.
- **Mempertahankan DocType `AIOS Tenant` atau konsep `1 Client = 1 Company` di 1 site.**
  - Karena konsep multi-tenant adalah **`1 Client = 1 Site`**, seluruh atribut pengguna & kuota ditaruh langsung di `User` (+ default tingkat site di `AIOS Setting`), dan registrasi mandiri masuk status `Pending Provisioning`.
- **Tambahkan `Administrator` ke permission role AIOS.** Dia sudah melewati semua
  cek (`permissions.py:108,306`) — menambahkannya hanya menciptakan baris permission
  tak berguna dan menyesatkan pembaca berikutnya.
- **Labeli `AIOS Admin` sebagai pengganti Administrator.** Beda: Administrator = user
  root tunggal, tidak bisa dihapus (`STANDARD_USERS` di `__init__.py:79`); `AIOS Admin`
  = role biasa yang bisa di-assign, tanpa hak mengubah skema.
- **Rombak 5.235 LOC `lib/tools/*` sekarang.** Ditunda sampai PoC satu cabang (#8)
  terbukti. Keputusan adaptasi-vs-buang diambil dengan data, bukan tebakan.
- **Buang adapter DB klien sepenuhnya.** Itu tujuan akhir (arahan atasan). PoC
  ERPNext hanya jalur cepat; adapter tetap disiapkan agar dua driver berdampingan.

---

## 9. Catatan Teknis Berguna

### Primitif Frappe terverifikasi

| Kebutuhan | Primitif | Lokasi | Catatan |
|---|---|---|---|
| Masking password | `Password` → `*****` di `as_dict()` | `base_document.py:1349-1369` | asli di `__Auth` |
| Hashing password | `passlib` + `CryptContext` + `needs_update` | `password.py:15-20` | **untuk `User`**, bukan field `Password` biasa |
| Enkripsi field Password | Fernet, `encrypted=1` | `password.py:189-195` | bisa didekripsi, bukan hash |
| Baca password terenkripsi | `get_decrypted_password` | `password.py:23` | **satu-satunya cara**; `db.get_value` tidak bisa |
| Seat counting | `SUM(simultaneous_sessions)` | `user.py:1211,1225` | `Website User` dikecualikan (`:1236`) |
| Role desk access | `Role.desk_access` (default `1`) | `role.json:33-42`, `user.py:415` | `AIOS Client` **wajib** `desk_access = 0` agar jadi `Website User` |
| Login + cookie | `sid`, `set_user_info` | `auth.py:146,191` | Website User → `home_page` |
| **Lockout login** | `LoginAttemptTracker` | `auth.py:530`, dipakai `:518` | dikendalikan `System Settings` |
| Halaman per role | `role_home_page` | `website/utils.py:156` | **hanya web Frappe** |
| Scoping baris (query) | `permission_query_conditions` | `db_query.py:1159`, dipanggil `:1081` | **tidak mencakup `get_doc`** |
| Scoping `get_doc` | `check_permission` | `document.py:178-186` | default `None` = tidak cek |
| Rate limit | `rate_limit` **decorator** | `rate_limiter.py:104` | butuh `@frappe.whitelist` |
| CSRF | `validate_csrf_token` | `auth.py:81-97` | dilewati kalau sesi tanpa `csrf_token` |
| Buat csrf_token | `get_csrf_token` / `generate_csrf_token` | `sessions.py:197-205` | panggil via endpoint `@frappe.whitelist()` / `on_login` untuk sesi API |
| `Website User` + whitelist | `is_whitelisted` | `__init__.py:479-483` | hanya menolak `Guest` → **bisa** |
| **Batas penting** | `get_list` cek / `get_all` tidak | `__init__.py:1360,1383` | `get_all` juga set `limit_page_length=0` (`:1404-1405`) |
| **Kumpulan role** | `Role Profile` (doctype, isi: tabel `roles`) | `core/doctype/role_profile/` | bungkus banyak role jadi satu profil |
| **Assign role ke user** | `User.role_profiles` (Table **MultiSelect**) | `user.py:131,225-234` | ⚠️ **bukan** `role_profile_name` (Link, cara lama) |
| Role dari profil → user | `populate_role_profile_roles()` | `user.py:226,263` | menyalin role profil ke `user.roles` |
| **Administrator bypass** | `if user == "Administrator"` | `permissions.py:108,306` | "Allowed everything" / "all permissions granted" |
| Administrator terkunci | `STANDARD_USERS` | `__init__.py:79` | `("Guest", "Administrator")`, tidak bisa dihapus (`user.py:221,267`) |
| **`User` di `core_doctypes_list`** | `core_doctypes_list` | `frappe/model/__init__.py:103-122`, `custom_field.py:281-282` | UI Customize Form menolak tambah field ke `User`; wajib pakai `create_custom_fields` via `after_install` & `after_migrate` |
| **Buat Custom Field via Hooks** | `create_custom_fields(custom_fields, update=True)` | `custom_field.py:322-350` | dipanggil di `after_install` & `after_migrate` pada `hooks.py` (tanpa `fixtures`) |
| **Data demo ERPNext** | `setup_demo_data(company_name)` | `erpnext/setup/demo.py:19-32` | butuh Fiscal Year + ≥4 warehouse; ⚠️ **silent rollback** bila gagal (`:23-32`) |
| Doctype transaksi demo | `demo_transaction_doctypes` | `erpnext/hooks.py:100-103` | hanya `["purchase_order", "sales_order"]` (`journal_entry.json` dead file) |
| Bersihkan demo | `clear_demo_data()` | `erpnext/setup/demo.py:53` | butuh `System Manager` |
| Warehouse otomatis | `create_default_warehouses()` | `company.py:383-390` | bikin 4 non-group (butuh `Warehouse Type = "Transit"`) |

### Lingkungan

- Frappe 16.33.1, Python 3.14, env: `/home/samue/mybench-v16/env/bin/python`
- Apps: `frappe`, `erpnext`, `aios_v1`, `ekasa_logbook`
- Site: `aios-v16.localhost`, `ekasa-logbook.localhost`
- `sites/assets/aios_v1` → symlink ke `apps/aios_v1/aios_v1/public`
- Modul app ber-**CRLF** (line terminator). Perhatikan saat edit/`ruff format`
- **Gunakan `/home/samue/mybench-v16/env/bin/python`**, bukan `python3` sistem
  (frappe tidak ada di sana — penyebab koreksi #21)

---

## 10. Batasan Lingkungan (penting untuk test)

Sesi audit ini berjalan dengan sandbox `workspace-write`:

- `/home/samue/logs` **read-only** → `frappe.connect()` gagal:
  `OSError: [Errno 30] Read-only file system: '/home/samue/logs/database.log'`
- Site logs (`sites/<site>/logs`) juga tidak writable

**Konsekuensi:**

| Bisa dijalankan di sini | Harus dijalankan pemilik project |
|---|---|
| Import smoke (sudah: 149 OK / 11 gagal) | Semua `IntegrationTestCase` (butuh DB) |
| Analisis AST/grep struktural | `bench migrate`, `bench --site … run-tests` |
| Verifikasi `file:line` source | Test scoping/IDOR/quota/login |

**Test integrasi di §6 ditulis supaya bisa dijalankan dengan:**
`bench --site aios-v16.localhost run-tests --app aios_v1`

### Dua angka yang sudah terpecahkan

1. **Smoke import (160 vs 131)**: penyusun mengukur **149 OK / 11 gagal dari 160 modul unik**; reviewer melaporkan "11 gagal, **120** lolos" (**131** total). **Penyebab selisih 29 modul terverifikasi:** `160 modul unik - 29 file __init__.py = 131 modul non-__init__` (`149 - 29 = 120` lolos). Selain itu, direktori `aios_v1/lib/` **belum memiliki `__init__.py`**, sehingga `pkgutil.walk_packages` akan melewatkan seluruh `lib/` kecuali dicari dengan `Path.rglob("*.py")`. Yang **sepakat**: 11 `demo_tahap*` gagal. **Diverifikasi ulang 2026-10-20 (revisi 7):** `TOTAL=163 OK=152 FAIL=11` bila `setup_poc/` untracked ikut dihitung ⇒ **149 OK / 11 gagal dari 160 modul tracked** — angka penyusun **benar**. Satu koreksi kecil: file `__init__.py` ter-track = **30**, bukan 29 (`131 + 30 = 161` file; menjadi 160 modul unik karena kolisi `aios_v1/api.py` vs `aios_v1/api/__init__.py`).
2. **58 live / 102 mati**: angka ini **bergantung root BFS**. Root yang dipakai:
   `api.dispatcher`, `hooks`, `lib.telegram_service` + semua `page`/`doctype`.
   Kalau telegram dianggap tidak jalan (dijalankan manual, A10), angkanya bergeser.

---

## 11. Langkah Berikutnya

Setelah **#0** dan **#1** selesai sebagai fondasi wajib (CI baseline + penutupan lubang keamanan aktif agar `/stream` tidak terbuka tanpa sesi), eksekusi terbagi menjadi **dua jalur paralel**:

```
                                       ┌─► #4d (backup + seed demo) ─► #7 (sandbox LLM) ─► #8 (PoC ERPNext finance)
#0 (CI baseline) ─► #1 (security) ─────┤
                                       └─► #2 (layout) ─► #3 (hygiene) ─► #4a ─► #4b ─► #4c ─► #5
                                                                                   └─► #9 (router)
```

1. **Jalur Cepat PoC Produk (`#0 → #1 → #4d → #7 → #8`):**
   - Dipilih bila prioritas utama adalah mendemokan AIOS menganalisis data ERPNext nyata (cabang `finance`) ke atasan secepatnya, **tanpa** mengekspos eksekusi tool ERPNext ke request tanpa sesi (`S5`) atau IDOR (`N2`).
   - **Prasyarat keras sebelum #8 (L10):** **Tahap C** sudah menutup lubang auth/IDOR darurat (`N1, N2, S1–S5`), pemilik project **wajib** menjalankan backup site + `seed_erpnext_demo.run` (#4d) via `bench`, dan branch **#7** (`fix/llm-tool-sandbox`: whitelist `aggregate.fn` L5, guard read-only L6, injeksi konteks `user_id` sesi + resolusi `default_company` site L7, akuntansi token & kuota `User` L8/A12, alur approval `Pending Action Draft` L9) **wajib hijau lebih dulu**.
2. **Jalur Pembersihan & Fondasi SaaS (`#0 → #1 → #2 → #3 → #4a → #4b → #4c → #5 → #9`):**
   - Merapikan pohon doctype/page & 16 skrip root (#2), membersihkan 396 file artifact & 25 `demo_tahap*` (#3), menghapus `AIOS Tenant` & memindahkan atribut/kuota ke `User` + `AIOS Setting` via `create_custom_fields` di `after_install` & `after_migrate` (`#4a–#4b`, `#5`), mengatur alur *Self-Registration* (`Pending Provisioning`), serta merapikan router (#9).

---

### ✅ `#0` Selesai — `chore/ci-baseline` (2026-10-20)

Deliverable #0 (**semua terpenuhi**, lihat §3k untuk hasil terukur):
1. `aios_v1/tests/test_import_smoke.py` — baseline terukur **149 OK / 11 gagal** (`demo_tahap*`) atas seluruh modul via `rglob("*.py")` + restore `sys.path` setelah `check_db.py:2` (modul bermasalah di-*xfail* **eksplisit per nama**, tanpa angka mati; alasan: target #3)
2. `aios_v1/tests/test_app_structure.py` — kontrak struktur app (di-*xfail* di #0, wajib hijau di #2)
3. `aios_v1/tests/test_authz_user_isolation.py` — **baseline keamanan dua user/klien** (IntegrationTestCase untuk `bench run-tests`; merah sebelum #1, hijau di #1)
4. `aios_v1/tests/test_repo_hygiene.py` — kontrak kebersihan repo (di-*xfail* di #0, wajib hijau di #3)
5. `aios_v1/tests/conftest.py` — pemisah suite statis vs integrasi: saat `frappe` tidak ada (CI), `collect_ignore` membuang seluruh `test_*.py` di luar allowlist statis. **Wajib** — 14 file meng-`import frappe` di module level sehingga tanpa ini pytest mati di fase collect (`18 errors`, exit 2, CI MERAH)
6. `.github/workflows/ci.yml` + `[tool.pytest.ini_options]` di `pyproject.toml` (`testpaths = ["aios_v1/tests"]`, `norecursedirs = ["frontend", ...]`, rapikan suite `aios_v1/tests/` **K5**) — CI memakai `ruff==0.17.1` + `pytest==9.1.1` saja (**tanpa** `frappe`, **tanpa** `apt-get`); test butuh-site dijalankan lokal via `bench --site aios-v16.localhost run-tests --app aios_v1`; `ruff format --check` ditunda ke #3
7. `pyproject.toml` → dev-dependency `pytest==9.1.1` & `ruff==0.17.1` (2 paket kecil)

**Kriteria selesai #0:** CI **HIJAU** — `pytest` exit 0 baik **dengan** frappe (lokal) maupun **tanpa** frappe (CI), dan `ruff check` tetap **746** error (baseline tidak bergerak; gate-nya baru mengetat di #3).

**Belum ada keputusan terbuka yang menghalangi.**

---

### ⏭️ Aksi Berikutnya: `#4a` (`refactor/frappe-identity-doctypes`)

Tahap C selesai: ownership per `User` + hook izin + `Pending Action Draft` sudah terpasang
(8/8 test isolasi hijau). Berikutnya #4a: hapus `AIOS Tenant`, tambah `AIOS Token Usage`,
field site-level di `AIOS Setting`, matriks `Custom DocPerm` ERPNext (#4b), dan konversi
`tenant_id` di 9 modul tool (232 titik) yang masih memakai `AIOS DB Connection.tenant`
sebagai kolom transisi.

**Prasyarat:** #7 (injeksi `user_id` dari sesi) harus selesai sebelum
`AIOS DB Connection.tenant` dihapus.
