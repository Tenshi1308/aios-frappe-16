# 04 — Alur Kerja Sistem (End-to-End Workflows)

Dokumen ini menggambarkan 5 alur kerja utama di dalam AIOS V1 dari awal pendaftaran pengguna hingga eksekusi kolaborasi agen dan persetujuan transaksi di ERPNext. Setiap alur disajikan dalam bentuk diagram **Mermaid** sekaligus **rincian langkah teknis bernomor** agar mudah dibaca manusia maupun diproses oleh AI agent.

---

## Alur 1 — *Self-Service Registration* (`/aios/register` — *Pending Provisioning*) & Aktivasi User

Karena arsitektur multi-tenant AIOS V1 adalah **`1 Client = 1 Site`** (setiap perusahaan klien memiliki *instance site* dan database tersendiri), pendaftaran mandiri di halaman web tidak langsung membuat `Company` dadakan atau *auto-login* ke workspace, melainkan masuk ke status **`Pending Provisioning`** pada DocType `User` dengan `enabled = 0` dan tanpa pengiriman email *reset password* otomatis.

```mermaid
sequenceDiagram
    actor Klien as Calon Klien (Pebisnis)
    participant UI as Registration UI (/aios/register)
    participant API as AIOS Registration API (auth.py)
    participant Setting as AIOS Setting (Site Defaults)
    participant DB as Frappe User DocType

    Klien->>UI: Isi Nama Lengkap, Email, Password, Nama Perusahaan
    UI->>API: POST /api/method/aios_v1.auth.register_account
    API->>Setting: Baca get_single_value("AIOS Setting", "default_user_token_limit")
    API->>DB: Buat DocType "User" (AIOS Client Profile, desk_access=0)
    Note over DB: Kunci Keamanan User Pending:<br/>aios_status = "Pending Provisioning"<br/>enabled = 0 (Sinkron via User.validate)<br/>send_welcome_email = 0 & flags.no_welcome_mail = True<br/>aios_company_name = Nama PT<br/>aios_persona = "executive"<br/>aios_token_limit = default_user_token_limit<br/>aios_tokens_used = 0
    DB-->>API: User tersimpan (Tanpa Email Reset Password & Tanpa Sesi Login)
    API-->>UI: Return { status: "PENDING_PROVISIONING" }
    UI-->>Klien: Tampilkan Layar "Pendaftaran Diterima — Instance Site Sedang Disiapkan"
```

### Rincian Langkah Alur 1:
1. **Input Registrasi Mandiri:** Calon klien mengisi Nama Lengkap, Email, Password, dan Nama Perusahaan/PT pada halaman `/aios/register`.
2. **Validasi & Proteksi Enumerasi:** Endpoint registrasi (`@frappe.whitelist(allow_guest=True)` + `@rate_limit`) memvalidasi input dan menerapkan respons seragam agar tidak dapat disalahgunakan untuk enumerasi email.
3. **Resolusi Kuota Default dari `AIOS Setting`:** Sistem membaca nilai `frappe.db.get_single_value("AIOS Setting", "default_user_token_limit")` (tanpa angka gaib hardcoded di kode Python).
4. **Pembuatan Akun `User` Terkunci (`Pending Provisioning`):**
   - Sistem membuat dokumen `User` bawaan Frappe dengan Role `AIOS Client` (`user_type = "Website User"`, `desk_access = 0`).
   - Mematikan pengiriman email sambutan/reset password bawaan Frappe (`user.send_welcome_email = 0` dan `user.flags.no_welcome_mail = True`) sehingga user yang belum di-provision tidak menerima link `/update-password`.
   - Mengisi Custom Field pada `User`:
     - `aios_status = "Pending Provisioning"` (yang secara otomatis menyetel `User.enabled = 0` di `User.validate` sehingga `/login` standar Frappe juga tertutup rapat).
     - `aios_company_name = company_name`
     - `aios_persona = "executive"`
     - `aios_token_limit = default_user_token_limit`
     - `aios_tokens_used = 0`
   - Sistem **tidak** membuat DocType `AIOS Tenant`, **tidak** membuat `Company` ERPNext secara paksa di dalam request tersebut, dan **tidak** melakukan *auto-login* (`login_as`) ke `/aios`.
5. **Tampilan Menunggu Provisioning:** UI menampilkan informasi bahwa pendaftaran telah diterima dan *dedicated site instance* perusahaan sedang disiapkan.
6. **Aktivasi User di Site Klien yang Sudah Ready:** Di dalam *site* klien yang sudah siap, `AIOS Admin` mengubah `User.aios_status = "Active"` (yang otomatis mengaktifkan `User.enabled = 1`), menetapkan `aios_persona` (`executive`, `finance`, `sales`), dan menyesuaikan `aios_token_limit` bila diperlukan.

---

## Alur 2 — Konfigurasi Provider, Model Routing, Plugin, & Kuota `User` oleh `AIOS Admin`

Operator/Admin (`AIOS Admin`) mengatur mesin kecerdasan, kapabilitas tool, serta kuota pemakaian token secara terpusat melalui Portal Admin.

```mermaid
flowchart TD
    Admin["AIOS Admin (Login di Portal Admin)"] --> Prov["1. Konfigurasi Provider LLM (AIOS LLM Provider)"]
    Prov --> ProvDetail["Tambah/Ubah Provider (OpenRouter, OpenAI, Anthropic, Gemini, dll.)\nSimpan Base URL, API Key (Password Terenkripsi), & Tarif Token"]
    ProvDetail --> Route["2. Pemetaan Model per Agen (AIOS Agent Model Route)"]
    Route --> RouteOrch["Set Model Orchestrator (route_key unik):\n- Finance Manager\n- Sales Manager"]
    Route --> RouteSub["Set Model per Sub-Agent (divalidasi ke registry.py):\n- CFO, Financial Analyst, Treasurer, Budgeting, Finance Staff\n- Sales Rep, Sales Analyst, Customer Service, Marketing"]
    RouteOrch --> Plugin["3. Manajemen Plugin & MCP (AIOS Plugin)"]
    RouteSub --> Plugin
    Plugin --> PluginBuiltIn["Toggle On/Off Built-in Default Plugins\n(ERPNext Core, Financial Reports, Action Drafts, Quant Calc, Doc Intel, Artifact Builder, Web Research)"]
    Plugin --> PluginExt["Install / Sambungkan External MCP Server\n& Atur Role-Scoping via Child Table AIOS Plugin Scope"]
    PluginBuiltIn --> Quota["4. Manajemen User & Hierarchical Token Quota"]
    PluginExt --> Quota
    Quota --> QuotaDetail["Atur default_user_token_limit & default_company di AIOS Setting\n& Sesuaikan aios_token_limit / aios_status Spesifik per User"]
```

### Rincian Langkah Alur 2:
1. **Pendaftaran Provider LLM (`AIOS LLM Provider`):** `AIOS Admin` menambahkan satu atau beberapa provider LLM lewat UI Admin, mengisi `base_url`, `api_key` (disimpan sebagai field `Password` terenkripsi Frappe pada `AIOS LLM Provider`), daftar model, serta tarif token per model.
2. **Pemetaan Model per Peran Agen (`AIOS Agent Model Route`):** `AIOS Admin` memilih provider dan model spesifik untuk masing-masing **Orchestrator** (`Finance Manager`, `Sales Manager`) maupun setiap **Sub-Agent** (`cfo`, `financial-analyst`, `treasurer`, `budgeting-staff`, `finance-staff`, `sales-representative`, `sales-data-analyst`, `customer-service`, `marketing-specialist`), dengan `route_key` unik dan validasi nama agen ke `registry.py`.
3. **Kontrak *Fail-Loudly* (Zero Default Hardcode):** Bila ada agen yang dipanggil tetapi belum memiliki rute model aktif di database, sistem langsung menghentikan eksekusi secara eksplisit (`frappe.throw`), mencatat ke `Error Log`, dan tidak pernah jatuh ke model default hardcoded.
4. **Pengaturan Plugin & MCP (`AIOS Plugin`):** `AIOS Admin` mengaktifkan/menonaktifkan *Built-in Default Plugins* maupun menyambungkan server MCP eksternal, serta mengatur hak akses plugin per cabang/sub-agent (*Least Privilege*).
5. **Manajemen Kuota Token Hybrid (`AIOS Setting` + `User`):** `AIOS Admin` mengatur nilai kuota awal di `AIOS Setting.default_user_token_limit`, memantau konsumsi token tiap pengguna (`User.aios_tokens_used` & log `AIOS Token Usage`), dan dapat menaikkan/menurunkan `User.aios_token_limit` atau mengubah `User.aios_status` (`Active` / `Suspended`) per individu.

---

## Alur 3 — Autentikasi Sesi, Guard 3 Lapis `aios_status`, Bootstrap CSRF, & Routing Portal

```mermaid
sequenceDiagram
    actor User as Pengguna (Admin / Klien)
    participant UI as Frontend Login UI
    participant FrappeAuth as Frappe Auth (authenticate + on_login + auth_hooks)
    participant CtxAPI as get_session_context (Whitelist)

    User->>UI: Masukkan Email & Password
    UI->>FrappeAuth: POST /api/method/login
    FrappeAuth->>FrappeAuth: 1. Cek User.enabled == 1 (auth.py:286)<br/>2. Hook on_login & auth_hooks cek db.get_value("User", user, "aios_status") == "Active"
    alt enabled == 0 atau aios_status != "Active"
        FrappeAuth-->>UI: Tolak Login (401/403 AuthenticationError — Tidak Ada Sesi Terbentuk)
    else enabled == 1 dan aios_status == "Active"
        FrappeAuth-->>UI: Set Cookie sid (HttpOnly, SameSite=Lax)
        UI->>CtxAPI: GET /api/method/aios_v1...get_session_context
        CtxAPI->>CtxAPI: Panggil frappe.sessions.get_csrf_token()
        CtxAPI->>CtxAPI: Baca Role (AIOS Admin vs AIOS Client), User Quota, & Default Company Site
        CtxAPI-->>UI: Return { user, roles, aios_persona, token_limit, tokens_used, company, csrf_token }
        alt Role == AIOS Admin
            UI-->>User: Render Portal AIOS Admin (Provider/Model, Plugin/MCP, Manajemen User & Kuota)
        else Role == AIOS Client
            UI-->>User: Render Workspace Bisnis (Divisi Finance & Sales + Canvas Panel)
        end
    end
```

### Rincian Langkah Alur 3:
1. **Login Standar Frappe + Guard 3 Lapis (`enabled`, `on_login`, `auth_hooks`):**
   - `LoginManager.authenticate()` (`frappe/auth.py:286`) menolak user bila `enabled == 0`.
   - Hook `on_login` (`frappe/auth.py:172`, dijalankan sebelum `make_session()`) dan `auth_hooks` (`frappe/auth.py:750`, dijalankan di setiap request) memeriksa `frappe.db.get_value("User", user, "aios_status")` secara langsung dari DB (tanpa cache). Jika nilainya bukan `"Active"`, request langsung dihentikan dengan `frappe.AuthenticationError`.
2. **Penerbitan Cookie Sesi (`sid`):** Jika aktif, Frappe membuat sesi di Redis dan mengirimkan cookie `sid` (`HttpOnly`, `SameSite=Lax`).
3. **Bootstrap Sesi & Token CSRF (`get_session_context`):** Frontend memanggil endpoint `@frappe.whitelist()` `get_session_context()` yang mengeksekusi `frappe.sessions.get_csrf_token()` untuk men-generate token di Redis sekaligus mengembalikannya ke frontend bersama informasi `roles`, `aios_persona`, `aios_token_limit`, `aios_tokens_used`, dan `default_company` site.
4. **Pemisahan Portal Berbasis Role:**
   - Jika pengguna memiliki role `AIOS Admin`, aplikasi mengarahkan ke **Portal Admin**.
   - Jika pengguna memiliki role `AIOS Client`, aplikasi mengarahkan ke **Workspace Bisnis (Finance & Sales)**.
5. **Penegakan CSRF:** Seluruh request tulis (`POST`/`PUT`/`DELETE`) berikutnya dari frontend wajib menyertakan header `X-Frappe-CSRF-Token`.

---

## Alur 4 — Eksekusi Tugas, Delegasi Agen (*Live Agent Trace*), Kolaborasi Lintas Divisi, & Render *Artifact/Canvas*

Alur ini terjadi ketika pengguna klien meminta analisis atau pekerjaan lintas peran (misalnya meminta evaluasi pesanan pelanggan sekaligus analisis arus kas dan pembuatan laporan Excel/grafik).

```mermaid
sequenceDiagram
    actor Client as AIOS Client (Pebisnis)
    participant UI as Workspace UI (Trace + Canvas)
    participant Orch as Orchestrator (Finance / Sales Manager)
    participant Sub as Sub-Agent Spesialis (mis. Treasurer / Sales Analyst)
    participant Swarm as Swarm Router (Lintas Divisi Sales <-> Finance)
    participant Tool as Plugin / Tool Executor (Scoped by Site Company)
    participant ERP as ERPNext Database & Query Reports

    Client->>UI: Kirim instruksi kerja di Cabang Sales / Finance
    UI->>Orch: POST /stream (SSE + Header X-Frappe-CSRF-Token)
    Orch->>Orch: Verifikasi kepemilikan Conversation (conv.user == session.user), Cek User Token Quota, Resolve Model Route
    
    opt Delegasi ke Sub-Agent di Divisi yang Sama (MAX_DELEGATION_DEPTH = 2)
        Orch-->>UI: SSE Event [trace_delegate_start]
        Orch->>Sub: Kirim Task Instruction & Context
        Sub-->>UI: SSE Event [trace_subagent_prompt]
        Sub->>Tool: Panggil Plugin (mis. erpnext-financial-reports / quant-calculator)
        Sub-->>UI: SSE Event [trace_subagent_tool]
        Tool->>Tool: Injeksi paksa Company aktif dari get_single_value("AIOS Setting", "default_company")
        Tool->>ERP: Eksekusi Query Report / get_list / get_doc(..., check_permission="read")
        ERP-->>Tool: Data Akuntansi / Penjualan Aktual
        Tool-->>Sub: Hasil JSON Tervalidasi
        Sub-->>UI: SSE Event [trace_subagent_result]
        Sub-->>Orch: Kembalikan Analisis Spesialis + Akumulasi Token Usage
    end

    opt Konsultasi Lintas Divisi (Sales <-> Finance)
        Orch->>Swarm: route_message(from="sales", to="finance", type="consultation")
        Swarm-->>UI: SSE Event [trace_cross_branch] (Sales Manager -> Finance Treasurer)
        Swarm->>Sub: Eksekusi Handler Cabang Tujuan (Cek Credit Limit & Overdue Invoice di ERPNext)
        Sub-->>Swarm: Status Plafon Kredit & Piutang Pelanggan Aktual
        Swarm-->>Orch: Kembalikan Hasil Konsultasi + Catat di Task Ledger
    end

    opt Pembuatan Artifact / Visualisasi di Canvas Space
        Orch->>Tool: Panggil workspace-artifact-builder (Buat Chart / Laporan / Private File .xlsx)
        Tool-->>UI: SSE Event [artifact_created] (Render Chart/Dokumen/File di Panel Canvas Kanan)
    end

    Orch-->>UI: Stream Jawaban Sintesis Akhir + Atomic SQL Increment User.aios_tokens_used & Insert AIOS Token Usage
```

### Rincian Langkah Alur 4:
1. **Verifikasi Awal Request (`/stream`):** Saat klien mengirim pesan, sistem memverifikasi kepemilikan `AIOS Conversation` terhadap `frappe.session.user` aktif, memastikan `User.aios_status == "Active"`, memeriksa sisa kuota token user (`User.aios_tokens_used < User.aios_token_limit`), dan mengambil konfigurasi model dari `AIOS Agent Model Route`.
2. **Perakitan Prompt Berlapis & Skema Plugin:** Sistem merakit System Prompt (`AIOS_ETHOS` + Identitas/SOP peran + `AIOS Setting.company_context_persona` + `User.aios_persona` + `User.aios_persona_context`) dan hanya menyertakan skema tool dari plugin yang aktif (`enabled = 1`) serta diizinkan untuk peran tersebut (di mana `orchestrator_delegate_to_subagent` hanya diberikan ke Orchestrator agar Sub-Agent tidak dapat mendelegasikan ulang tanpa batas).
3. **Delegasi Sub-Agent Nyata & 5 Event Kanonik *Live Agent Trace*:**
   - Bila Orchestrator memanggil `orchestrator_delegate_to_subagent`, backend mengirimkan event SSE kanonik (`trace_delegate_start`, `trace_subagent_prompt`, `trace_subagent_tool`, `trace_subagent_result`, `trace_cross_branch`) ke kolom kiri UI (**Live Agent Trace** tanpa emoji).
   - Sub-Agent yang ditunjuk benar-benar dieksekusi dengan model dan daftar tool spesifik miliknya.
4. **Injeksi Paksa Konteks `Company` Site-Level & Izin Baca ERPNext:**
   - Setiap kali Sub-Agent atau Orchestrator memanggil plugin (`erpnext-core-data`, `erpnext-financial-reports`, dll.), `execute_tool` mengabaikan klaim company dari argumen LLM dan menyuntikkan `allowed_company` yang dibaca secara site-level dari `frappe.db.get_single_value("AIOS Setting", "default_company") or frappe.db.get_single_value("Global Defaults", "default_company")`.
   - Pembacaan detail dokumen menggunakan `frappe.get_doc(doctype, name, check_permission="read")`.
   - Perhitungan angka finansial/statistik dilakukan secara deterministik melalui plugin `quant-calculator`.
5. **Kolaborasi Lintas Divisi (`Sales ↔ Finance`):**
   - Melalui `SwarmRouter(user=frappe.session.user)` (tanpa fallback default `1` dan tanpa fallback handler mock), divisi Sales berkonsultasi secara otonom ke divisi Finance untuk memeriksa plafon kredit dan piutang jatuh tempo di ERPNext sebelum pesanan baru dibuat.
6. **Pembuatan File & Visualisasi di *Artifact/Canvas Space*:**
   - File kerja (`.xlsx`, `.csv`, `.pdf`, `.md`) disimpan menggunakan DocType `File` Frappe (`is_private=1`, terikat ke `AIOS Conversation` milik user) dan sistem mengirim event `artifact_created` sehingga panel **Canvas** di sebelah kanan layar langsung merender hasilnya.
7. **Sintesis Jawaban & Akuntansi Token Atomik (`usage.py`):** Orchestrator menyusun jawaban akhir untuk pengguna, mencatat rincian ke DocType `AIOS Token Usage`, dan meng-update `User.aios_tokens_used` secara atomik menggunakan SQL (`SET aios_tokens_used = aios_tokens_used + %s`) tanpa memanggil `user_doc.save()`.

---

## Alur 5 — Aksi Tulis Bisnis & *Human-in-the-Loop Approval* (`Pending Action Draft`)

AIOS memegang prinsip keselamatan mutlak untuk data keuangan dan transaksi: **agen AI tidak pernah menulis atau mengubah dokumen transaksi langsung ke database ERPNext tanpa persetujuan eksplisit dari manusia.**

```mermaid
sequenceDiagram
    actor Client as AIOS Client (Pebisnis)
    participant UI as Workspace Canvas (Tier 1 Approval Card)
    participant Agent as Agen Finance / Sales
    participant DraftMgr as Draft Manager (Pending Action Draft)
    participant ERP as ERPNext (Sales Order / Invoice / Journal Entry)

    Client->>Agent: "Buatkan Sales Order untuk PT Maju Jaya / Catat jurnal penyesuaian ini"
    Agent->>DraftMgr: Panggil Plugin erpnext-action-drafts (create_draft)
    DraftMgr->>DraftMgr: Validasi kelengkapan field & ikat ke user = frappe.session.user
    DraftMgr->>DraftMgr: Simpan DocType "Pending Action Draft" (status = PENDING_APPROVAL)
    DraftMgr-->>UI: Kirim Event [artifact_created: APPROVAL_CARD] ke Canvas Panel Kanan
    UI-->>Client: Tampilkan Rincian Transaksi (Tabel Item/Akun, Nominal, Tombol Approve / Reject)

    alt Klien Klik "Approve & Post to ERPNext"
        Client->>UI: Klik Tombol Approve
        UI->>DraftMgr: POST approve_and_execute_draft(draft_id) + CSRF Token
        DraftMgr->>DraftMgr: Verifikasi draft.user == frappe.session.user (atau AIOS Admin)
        DraftMgr->>ERP: Buat & Simpan Dokumen Resmi di ERPNext (Company = default_company site)
        ERP-->>DraftMgr: Nomor Dokumen ERPNext (mis. SAL-ORD-2026-00001)
        DraftMgr->>DraftMgr: Update status = EXECUTED
        DraftMgr-->>UI: Tampilkan Konfirmasi & Link Dokumen Resmi
    else Klien Klik "Reject"
        Client->>UI: Klik Tombol Reject + Isi Alasan Penolakan
        UI->>DraftMgr: POST reject_draft(draft_id, reason) + CSRF Token
        DraftMgr->>DraftMgr: Verifikasi draft.user == frappe.session.user & Update status = REJECTED
        DraftMgr-->>UI: Tampilkan Status Ditolak beserta Alasannya
    end
```

### Rincian Langkah Alur 5:
1. **Permintaan atau Rekomendasi Aksi Tulis:** Pengguna meminta pembuatan dokumen transaksi baru (mis. *Quotation*, *Sales Order*, *Sales Invoice*, *Payment Entry*, atau *Journal Entry*) atau agen mengusulkan tindak lanjut transaksi dari hasil analisis.
2. **Pembuatan `Pending Action Draft`:** Agen memanggil plugin `erpnext-action-drafts` yang memvalidasi struktur payload dan menyimpannya ke doctype `Pending Action Draft` dengan `status = "PENDING_APPROVAL"`, terikat ketat ke `user = frappe.session.user`, dan memiliki batas waktu kedaluwarsa (`expires_at`).
3. **Render *Tier 1 Interactive Approval Card* di Canvas:** Panel Canvas di sebelah kanan ruang chat menampilkan kartu persetujuan berisi tabel rincian item/akun, nominal, justifikasi bisnis, serta tombol aksi **Approve & Post to ERPNext** dan **Reject**.
4. **Eksekusi Saat Disetujui (**Approve**):**
   - Pengguna menekan tombol **Approve**.
   - Backend (`approve_and_execute_draft`) memverifikasi autentikasi sesi, token CSRF, dan memastikan `draft.user == frappe.session.user` (atau user memiliki role `AIOS Admin`).
   - Sistem membuat dokumen resmi di ERPNext di bawah `Company` aktif pada site tersebut, mengubah status draf menjadi `EXECUTED`, dan mengembalikan nomor dokumen resmi ERPNext ke layar pengguna.
5. **Pembatalan Saat Ditolak (**Reject**):**
   - Bila pengguna menekan **Reject** dan mengisi alasan penolakan, sistem memverifikasi kepemilikan draf, memperbarui status draf menjadi `REJECTED`, dan menyimpan alasan penolakan ke field `rejection_reason` tanpa menyentuh database transaksi ERPNext.
