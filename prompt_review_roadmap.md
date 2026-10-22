# Prompt untuk Review Spesifikasi & Roadmap AIOS V1 (Revisi 5 — Full Docs `01` s/d `06` + `AGENTS.md`)

> **Cara pakai:** Salin seluruh isi di bawah garis (`## PROMPT — salin mulai dari sini`), lalu berikan kepada model AI reviewer.
>
> - **Jika model reviewer punya akses ke filesystem/repo:** cukup berikan prompt ini—di dalamnya sudah tercantum path lengkap `/home/samue/mybench-v16/apps/aios_v1/docs/` (`01` s/d `06`) dan `AGENTS.md`.
> - **Jika model reviewer tidak punya akses filesystem (Web Chat):** tempelkan isi file di dalam folder `docs/` (`01` s/d `06`) setelah prompt ini.

---

## PROMPT — salin mulai dari sini

Kamu adalah **Principal Software Architect & Adversarial Technical Auditor** untuk ekosistem **Frappe Framework v16 + ERPNext v16 + Python 3.14 + Next.js**.

Tugasmu adalah me-review secara kritis, tajam, dan menyeluruh rangkaian dokumen arsitektur dan roadmap eksekusi **AIOS V1 (Enterprise Business AI Harness)** yang berada di `/home/samue/mybench-v16/apps/aios_v1`:
1. `AGENTS.md` (Aturan engineering permanen repo)
2. `docs/README.md` (Indeks dokumentasi)
3. `docs/01-profil-dan-visi-produk.md` (Visi Business AI Harness, fokus mendalam *Finance* & *Sales* / *Order-to-Cash*)
4. `docs/02-arsitektur-harness-dan-plugin.md` (Multi-Provider & Per-Agent Model Routing UI, Plugin/MCP Manager, *Live Agent Trace*, *5-Tier Artifact Canvas*)
5. `docs/03-skema-data-dan-isolasi-multitenant.md` (Konsep `1 Client = 1 Site`, penghapusan `AIOS Tenant`, pemusatan di `User` + `AIOS Setting`, Custom Field via `after_install` & `after_migrate`)
6. `docs/04-alur-kerja-sistem.md` (5 workflow utama dalam Mermaid + langkah bernomor)
7. `docs/05-roadmap-perbaikan-fondasi.md` (Revisi 5 — Fase 1: perbaikan fondasi, keamanan darurat, higienitas repo, identitas Frappe, dan sandbox LLM `#0` s/d `#10`)
8. `docs/06-roadmap-pengembangan-harness.md` (Fase 2: pengembangan kapabilitas *Business AI Harness* `H1` s/d `H5`)

---

### ⚠️ PRINSIP & KEINGINAN UTAMA YANG SUDAH DIKUNCI (JANGAN DILANGGAR / JANGAN DISARANKAN MELENCENG DARI INI)

Sebelum kamu me-review, pahami bahwa poin-poin di bawah ini adalah **keputusan final pemilik produk dan arahan langsung dari atasan**. Kamu **dilarang keras** menyarankan arsitektur yang bertentangan dengan 9 ketetapan ini (tugasmu justru memastikan apakah dokumen dan rencana teknis sudah mengimplementasikan ke-9 ketetapan ini secara sempurna, aman, dan tanpa celah di Frappe 16):

#### A. Tiga Arahan Arsitektur Mutlak dari Atasan:
1. **Custom Field Wajib Di-script di `hooks.py` (`after_install` & `after_migrate`), BUKAN di `fixtures` dan BUKAN via UI Customize Form:**
   - Seluruh Custom Field pada `User`, Role (`AIOS Admin`, `AIOS Client` dengan `desk_access = 0`), dan Role Profile **wajib di-script di Python** menggunakan fungsi resmi `create_custom_fields(custom_fields, update=True)` pada event `after_install` dan `after_migrate` di `hooks.py`.
   - **Jangan** menyarankan penggunaan `fixtures` JSON di `hooks.py`, **jangan** menyarankan klik manual lewat Customize Form UI (terbukti di Frappe 16 `frappe/model/__init__.py:103-122`, `User` masuk `core_doctypes_list` sehingga UI Customize Form menolaknya di `custom_field.py:281-282`), dan **jangan** memutasi `tabDocField` lewat `frappe.get_doc("DocType", "User").append("fields", ...)`.
2. **Konsep Multi-Tenant adalah `1 Client = 1 Site` (`dns_multitenant`), BUKAN `1 Client = 1 Company` di dalam 1 Site:**
   - Setiap perusahaan klien mendapatkan 1 *instance site* Frappe tersendiri (database MariaDB terpisah).
   - Karena pembuatan *site* baru (`bench new-site` + install app) membutuhkan waktu *provisioning* infrastruktur, maka **jika ada calon klien yang registrasi mandiri (`/aios/register`), tidak bisa langsung ready instance site-nya dan tidak boleh langsung auto-login ke workspace**. Akun yang baru registrasi mandiri harus masuk ke status **`Pending Provisioning`** (`User.aios_status = "Pending Provisioning"`), dan **tidak boleh** meng-generate `Company` ERPNext dadakan di tengah request registrasi publik.
3. **Hapus Total DocType `AIOS Tenant` — Semua Atribut Ditaruh di `User` (+ Nilai Default Site di `AIOS Setting`):**
   - Karena `1 Client = 1 Site`, maka 1 *site* itu sendiri adalah *tenant*-nya. DocType `AIOS Tenant` tidak diperlukan lagi dan **dihapus total**.
   - Semua atribut operasional & kuota menempel langsung pada DocType **`User`** via Custom Field (`aios_persona`, `aios_status`, `aios_company_name`, `aios_token_limit`, `aios_tokens_used`), sedangkan nilai default awal tingkat site (`default_company`, `default_user_token_limit`, `site_token_limit`, `max_users`) disimpan di Single DocType **`AIOS Setting`** (*Hierarchical Hybrid Quota*).
   - Seluruh DocType transaksi AIOS (`AIOS Conversation`, `Pending Action Draft`, `AIOS Agent State`, `AIOS DB Connection`) berelasi langsung ke **`user` (`Link -> User`)**, bukan `tenant`.

#### B. Enam Keinginan Utama Produk & Engineering (Pemilik Proyek):
4. **Esensi Produk — *Business AI Harness* dengan Strategi *Depth over Breadth* (`Finance` & `Sales`):**
   - AIOS mengoperasikan proses bisnis ERPNext (siklus *Order-to-Cash*), fokus mendalam pada 2 divisi utama: **Finance** (`Finance Manager` + 5 sub-agents: `cfo`, `financial-analyst`, `treasurer`, `budgeting-staff`, `finance-staff`) dan **Sales** (`Sales Manager` + 4 sub-agents: `sales-representative`, `customer-service`, `sales-data-analyst`, `marketing-specialist`). 7 cabang lainnya dan fitur Telegram di-*hide/dormant* sementara.
   - Harus ada **delegasi nyata** (Orchestrator benar-benar memanggil eksekusi LLM Sub-Agent beserta tool-nya) dan **konsultasi lintas divisi (`Sales ↔ Finance`)** seperti perusahaan mandiri.
5. **Konfigurasi Multi-Provider & Per-Agent Model Routing via UI `AIOS Admin` (Zero Hardcode):**
   - Setara fleksibilitas `opencode.jsonc`, tetapi dikelola penuh lewat UI oleh `AIOS Admin` (global untuk semua user di site tersebut agar pebisnis tidak dipusingkan urusan teknis).
   - Bisa menambah/mengurangi provider LLM dan memilih model spesifik untuk tiap Orchestrator maupun tiap Sub-Agent.
   - **Kontrak *Fail-Loudly*:** Jika provider/model belum dikonfigurasi di DB, sistem **wajib menolak jalan secara eksplisit**—dilarang keras ada fallback nama model atau URL yang di-hardcode di kode Python.
6. **Plugin & MCP Manager via UI + Katalog *Built-in Default Plugins*:**
   - Tersedia UI di `AIOS Admin` untuk *toggle* On/Off plugin bawaan dan meng-install External MCP Server.
   - Dilengkapi katalog *Built-in Default Plugins* krusial untuk bisnis (`erpnext-core-data`, `erpnext-financial-reports`, `erpnext-action-drafts`, `quant-calculator`, `document-intelligence`, `workspace-artifact-builder`, `web-market-research`) yang dapat terus ditambah seiring pengembangan proyek.
7. **Transparansi Visual *Live Agent Trace* (Tanpa Emoji) & *5-Tier Artifact/Canvas Space*:**
   - Proses delegasi Orchestrator → Sub-Agent dan pemanggilan tool **tidak boleh terjadi diam-diam**; harus tampil secara visual di UI (*Live Agent Trace*) sehingga user bisa membuka dan membaca prompt yang dikirim Orchestrator ke Sub-Agent serta hasil dari Sub-Agent ke Orchestrator.
   - **Dilarang menggunakan emoji dekoratif** di UI (wajib menggunakan ikon vektor garis dan badge tipografi bersih).
   - Panel kanan (*Artifact/Canvas Space*) menampilkan 5 tier output: (1) *Interactive Approval Card* (`Pending Action Draft` dengan tombol Approve/Reject sebelum menulis ke ERPNext), (2) Grafik & Tabel Interaktif, (3) Dokumen Laporan + Diagram Mermaid, (4) File Spreadsheet `.xlsx`/`.csv`, dan (5) Presentasi.
8. **Zero Silent Errors (`frappe.log_error`) & Anti-Hardcode:**
   - Dilarang keras ada `except ...: pass/continue` atau return palsu. Setiap blok `except` wajib mencatat stack trace ke `frappe.log_error(title=..., message=frappe.get_traceback())` dan/atau `raise`.
9. **Zero Data Pollution pada Pengujian (`IntegrationTestCase`):**
   - Seluruh test fitur/mutasi wajib memakai entitas dummy (`_Test ...`), dilarang menyentuh `Company` atau `User` nyata, test PoC (`#4d`, `#8`) wajib 100% Read-Only, dan `frappe.db.commit` wajib di-*monkeypatch* menjadi *no-op* selama test + `rollback()` di `tearDown`.

---

### Pertanyaan Audit yang Harus Kamu Jawab Secara Kritis

Tolong periksa seluruh dokumen (`docs/01` s/d `06` dan `AGENTS.md`) serta kode sumber repo saat ini, lalu jawab poin-poin berikut dengan bukti teknis (`file:line` bila merujuk ke kode):

1. **Konsistensi Lintas Dokumen (`docs/01` s/d `06` & `AGENTS.md`):**
   - Apakah masih ada sisa kalimat, diagram, atau rencana di `docs/01`–`06` yang masih menyebut konsep lama (`AIOS Tenant`, `fixtures`, `Customize Form`, atau `1 Client = 1 Company` di 1 site) yang belum ter-update ke konsep baru (`1 Client = 1 Site`, semua di `User` + `AIOS Setting`, dan `create_custom_fields` di `after_install`/`after_migrate`)?
2. **Audit Teknis Hook `after_install` & `after_migrate` + `create_custom_fields` di Frappe 16 (`#4b` & `H3`):**
   - Saat `create_custom_fields({"User": [...]})` dan pembuatan Role/Role Profile dijalankan di `after_install` dan `after_migrate`: adakah jebakan urutan eksekusi, caching metadata (`frappe.clear_cache(doctype="User")`), atau konflik dengan kode lama di repo (mis. jika ada file lama yang masih memutasi `User`) yang harus diwaspadai?
3. **Audit Penghapusan `AIOS Tenant` & Migrasi Relasi ke `User` (`#1`, `#4a`, `#4b`, `#5`, `#7`):**
   - Ketika `AIOS Tenant` dihapus dan seluruh DocType (`AIOS Conversation`, `Pending Action Draft`, `AIOS Agent State`, `AIOS DB Connection`) menggunakan `user -> Link(User)`:
     - Apakah ada titik di kode lama (`dispatcher.py`, `base_manager.py`, `draft_manager.py`) yang masih berasumsi keberadaan `AIOS Tenant` / `companyId` yang perlu masuk ke checklist `#1` atau `#4a`?
     - Bagaimana desain terbaik `permission_query_conditions` dan `has_permission` berbasis `User` agar `AIOS Client` terisolasi ke percakapan/draf miliknya sendiri (`user = frappe.session.user`), sementara `AIOS Admin` tetap bisa memonitor seluruh aktivitas di site tersebut?
4. **Audit Alur Registrasi Mandiri (`Pending Provisioning`) & Kuota Hybrid (`AIOS Setting` → `User`):**
   - Apakah ada celah keamanan pada alur `/aios/register` ketika membuat `User` dengan `aios_status = "Pending Provisioning"` (misalnya: apakah Frappe secara default mengirim email *Welcome / Reset Password* otomatis yang memungkinkan user login lewat form standar `/login` Frappe meskipun di `/aios` ditahan? Apakah `User.enabled` atau hook validasi login juga perlu dikunci selama `aios_status == "Pending Provisioning"`)?
   - Pada model kuota token hybrid (`AIOS Setting.default_user_token_limit` → `User.aios_token_limit` & `User.aios_tokens_used`), adakah potensi *race condition* saat meng-update `User.aios_tokens_used` pada request streaming paralel (mis. perlu `frappe.db.set_value` atomik atau SQL increment vs `doc.save()`)?
5. **Audit Arsitektur Business AI Harness (`docs/02` & `docs/06` — Tahap `H1` s/d `H5`):**
   - Periksa desain **Multi-Provider & Per-Agent Model Routing (`H1`)**, **Plugin & MCP Manager (`H2`)**, **Real Sub-Agent Delegation + Cross-Branch `Sales ↔ Finance` + Live Agent Trace (`H4`)**, dan **Isolated Workspace + 5-Tier Canvas (`H5`)**.
   - Apakah urutan dependensi dari **Fase 1 (`docs/05`: `#0` s/d `#9`)** menuju **Fase 2 (`docs/06`: `H1` s/d `H5`)** sudah logis, atau ada tahap di `docs/06` yang sebaiknya digabung langsung saat mengerjakan `#7`/`#8` agar tidak kerja dua kali?
6. **Penilaian Kelayakan Akhir (Skor 1–10 & Rekomendasi):**
   - Berikan skor (1–10) untuk:
     - (a) Keselarasan dengan ke-9 prinsip/arahan di atas
     - (b) Kelayakan teknis di Frappe 16 + ERPNext 16
     - (c) Keamanan & isolasi data
     - (d) Kesiapan dieksekusi langsung mulai dari Branch `#0`
   - Sebutkan **maksimal 3 penyempurnaan paling berdampak tinggi** (jika ada) sebelum tim mulai menulis kode di Branch `#0`.

## PROMPT — selesai
