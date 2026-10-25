# 02 — Arsitektur Harness, Model Routing, Plugin/MCP, & Kontrak Trace

Dokumen ini menjelaskan bagaimana AIOS V1 mengadopsi arsitektur *AI Harness* modern (seperti OpenCode, Claude Code, dan Antigravity) yang disesuaikan khusus untuk pengguna bisnis di atas ERPNext dengan isolasi **`1 Client = 1 Site`**.

---

## 1. Manajemen Multi-Provider & Per-Agent Model Routing (Berbasis UI, Zero Hardcode)

Pada coding harness modern, pengguna mengatur provider dan model melalui file konfigurasi seperti `opencode.jsonc`. Karena target pengguna AIOS adalah pelaku bisnis, **seluruh konfigurasi tersebut dikelola melalui antarmuka grafis (UI) di Developer Control Plane `AIOS Admin` dan disimpan di site developer sebagai sumber kebenaran, lalu disalin ke tiap site klien**—tanpa satu pun nama model atau URL provider yang di-hardcode di kode Python.

> **Batas control plane vs data plane:** UI pengaturan (provider, model routing, plugin/MCP) berada di Developer Control Plane. **Konfigurasi operator** (provider, model, plugin) bersumber dari site developer dan disalin ke tiap site klien lewat Control API; **data bisnis** tetap tinggal di site klien masing-masing (`docs/03` §1.4). Konsekuensi yang diterima: kredensial LLM kini terkonsentrasi di satu database developer — diputuskan 2026-10-23 demi satu konfigurasi untuk semua site klien.

### 1.1. Kapabilitas Konfigurasi di Developer Control Plane
1. **Multi-Provider Registry (`AIOS LLM Provider`, sumber di site developer):**
   - `AIOS Admin` dapat menambah, mengubah, mengaktifkan/menonaktifkan, atau menghapus provider LLM (misalnya OpenRouter, OpenAI, Anthropic, Google Gemini, DeepSeek, atau server vLLM/Ollama internal). Konfigurasi ini berlaku untuk semua site klien, bukan dipilih per site.
   - Setiap provider menyimpan `provider_name`, `base_url`, `api_key` (menggunakan fieldtype `Password` terenkripsi Frappe; memisahkan rahasia dari `AIOS Setting`), daftar model yang tersedia, serta struktur tarif token (*input/output cost per 1M tokens*). Penulisan ke site klien berjalan lewat Control API dengan role `AIOS Control`, bukan login Desk.
2. **Pemetaan Model Spesifik per Agen (`AIOS Agent Model Route`):**
   - Setiap **Orchestrator** (`Finance Manager`, `Sales Manager`) dan setiap **Sub-Agent Spesialis** (`cfo`, `financial-analyst`, `treasurer`, `budgeting-staff`, `finance-staff`, `sales-representative`, `sales-data-analyst`, `customer-service`, `marketing-specialist`) memiliki slot konfigurasi modelnya masing-masing.
   - Memiliki field unik `route_key` (`f"{branch_key}:{agent_key}:*"`) dan validasi `agent_key` terhadap `registry.py` saat `validate()` agar tidak pernah ada duplikasi rute atau salah ketik (*typo*) nama agen.
3. **Prinsip *Fail-Loudly* (Dilarang Fallback Hardcode):**
   - Apabila suatu Orchestrator atau Sub-Agent dipanggil namun provider atau modelnya belum dikonfigurasi/dinonaktifkan di database, sistem **wajib menolak eksekusi secara eksplisit** dengan pesan error yang jelas dan mencatatnya ke `Error Log` Frappe. Sistem dilarang keras jatuh ke nilai default hardcoded di dalam kode.
4. **Cakupan Global Lintas Site (Tanpa Override):**
   - Konfigurasi Provider & Model diatur **sekali** oleh `AIOS Admin` di Developer Control Plane dan berlaku untuk **semua site klien**. Tidak ada konfigurasi per site dan tidak ada override per user (`route_key` cukup `f"{branch_key}:{agent_key}:*"`).
   - Site developer adalah sumber kebenaran; setiap perubahan disalin ke tiap site klien lewat Control API. Site klien menyimpan salinan lokal yang dipakai saat runtime, sehingga chat tidak bergantung pada hidup-matinya server developer.

---

## 2. Arsitektur Plugin & MCP Manager (`AIOS Plugin`)

Alih-alih menulis ratusan fungsi Python spesifik yang kaku dan sulit dirawat, lapisan eksekusi tool AIOS dibangun dengan arsitektur **Modular Plugin & Model Context Protocol (MCP)** melalui DocType **`AIOS Plugin`**.

### 2.1. Manajemen via UI (Developer Control Plane, berlaku untuk semua site klien)
- Menyediakan katalog plugin yang dapat di-*toggle* **On/Off** dari UI control plane. Katalog ini **global untuk semua site klien**: perubahan disalin ke tiap site klien, bukan diatur per site.
- Mengatur *Role-Scoping* (*Least Privilege*) melalui child table `AIOS Plugin Scope`: menentukan plugin/tool mana yang boleh diakses oleh cabang (`finance`, `sales`) dan jabatan sub-agent tertentu.
- Backend mendukung client **External MCP Streamable HTTP**; transport MCP SSE tetap tercatat di schema lama, tetapi ditolak saat runtime. Pendaftaran, discovery manual, health check, autentikasi, dan pengelolaan global berada di #11 atau tahap lanjutan; tidak ada UI MCP di fase H2 ini.

### 2.2. Katalog *Built-in Default Plugins* (Fondasi Bisnis)
AIOS hadir dengan himpunan plugin bawaan (*default*) untuk kebutuhan kritikal bisnis yang dapat terus ditambah seiring pengembangan proyek:

| ID Plugin Bawaan (`AIOS Plugin`) | Fungsi Utama | Sumber / Primitif yang Dipakai |
|---|---|---|
| **`erpnext-core-data`** | Intropeksi skema DocType, pembacaan daftar & detail dokumen master maupun transaksi (`Sales Order`, `Sales Invoice`, `Purchase Invoice`, `Delivery Note`, `Payment Entry`, `Journal Entry`, `GL Entry`, `Customer`, `Supplier`, `Item`) yang terfilter ketat ke `Company` aktif di site tersebut (`frappe.db.get_single_value("AIOS Setting", "default_company")`). Deskripsi tool dan error `DOCTYPE_NOT_ALLOWED` memakai daftar `ERP_CLIENT_DOCTYPES` satu-sumber + hint kondisional belanja (Purchase Invoice / report Accounts Payable) agar model tidak menebak DocType. Deskripsi `erpnext_doc_list` mewajibkan model menyebutkan filter/cakupan yang dipakai dan melarang menyebut hasil terfilter sebagai seluruh data. | `frappe.get_list`, `frappe.get_doc(..., check_permission="read")`, `frappe.get_meta` (didukung `Custom DocPerm` `read=1` untuk `AIOS Client`) |
| **`erpnext-financial-reports`** | Menjalankan mesin laporan akuntansi & penjualan resmi bawaan ERPNext (*General Ledger*, *Accounts Receivable/Payable Aging*, *Trial Balance*, *Profit and Loss Statement*, *Balance Sheet*, *Cash Flow*, *Sales Analytics*). Filter wajib per laporan divalidasi sebelum eksekusi (`REPORT_FILTER_GUIDE`, bersumber dari source ERPNext) dan kekurangan dikembalikan sebagai `REPORT_FILTER_REQUIRED` yang menyebut report dan filter kurang — tanpa default senyap. | `frappe.desk.query_report.run` (didukung `Custom DocPerm` `report=1` untuk `AIOS Client` pada DocType referensi laporan). Gate ganda report standar ERPNext (`Report.is_permitted()` memeriksa daftar role milik dokumen Report sebelum izin `report` pada DocType referensi) kini tertutup penuh: `ensure_report_roles()` rebuild `Custom Role` untuk 8 report allowlisted (roles = `Has Role` Report + `AIOS Client`, role stale dihapus, idempoten, dipanggil tiap install/migrate; edit manual lewat UI bisa tertimpa), dan `Purchase Invoice` read+report menutup gate kedua `Accounts Payable`. Entry `query_report.run` tetap dibungkus guard `aios_v1.api.report_guard` via `override_whitelisted_methods`: untuk `AIOS Client` report dibatasi `ALLOWED_REPORTS`, `filters["company"]` dipaksa ke company aktif, prepared report dimatikan; user lain pass-through. |
| **`erpnext-action-drafts`** | Menyusun draf transaksi bisnis baru (*Quotation*, *Sales Order*, *Sales Invoice*, *Payment Entry*, *Journal Entry*) ke tabel antrean persetujuan manusia (`Pending Action Draft` dengan `user = frappe.session.user`). | Doctype `Pending Action Draft` + validasi skema ERPNext |
| **`quant-calculator`** | Kalkulator finansial dan statistik deterministik di Python (perhitungan margin, delta pertumbuhan MoM/YoY, pajak, proyeksi arus kas, dan rekonsiliasi selisih angka) agar LLM tidak pernah menebak hitungan matematika. | Modul komputasi numerik Python stdlib terisolasi (tanpa dependency berat) |
| **`document-intelligence`** | Mengekstrak teks dan tabel terstruktur dari dokumen yang diunggah pengguna klien (PDF invoice/PO, CSV, spreadsheet Excel `.xlsx`) untuk dianalisis atau dicocokkan dengan pembukuan ERPNext. | `pypdf`, `openpyxl`, parser tabular CSV/XLSX |
| **`workspace-artifact-builder`** | Membuat file kerja nyata di ruang kerja sesi pengguna (`.xlsx`, `.csv`, `.pdf`, `.md`) melalui DocType `File` (`is_private=1`) serta mengirim spesifikasi grafik interaktif & diagram Mermaid agar dibuka sebagai jendela di desktop. | Frappe Private `File` API (`save_file`) & renderer artefak (`docs/08` §5) |
| **`web-market-research`** | Mengambil konten publik lewat `web_fetch`; `web_search` terdaftar tetapi gagal eksplisit dengan `SEARCH_PROVIDER_NOT_CONFIGURED` sampai provider tersedia. | HTTP(S) dengan validasi DNS, koneksi langsung ke IP yang divalidasi, TLS hostname/certificate check, redirect manual dengan validasi ulang, batas ukuran, waktu, dan content-type |

**Status katalog (2026-10-24):** tujuh dari tujuh plugin tersedia di kode — `workspace-artifact-builder` (tool `workspace_create_file` csv/xlsx/md/pdf sebagai Private File terikat conversation) selesai pada H5 fase 1 (`b07975f`); web search belum memiliki provider; chart interaktif dan diagram Mermaid pada artefak belum ada (UI #12). Seed plugin berjalan melalui hook install/migrate, tetapi data plugin pada suatu site baru berubah setelah hook dijalankan.

> **Tiga plugin ERPNext adalah *wrapper tipis*, bukan implementasi baru.**
> - **Logika data memakai ERPNext sendiri:** `frappe.get_list` / `frappe.get_doc` untuk dokumen, `frappe.desk.query_report.run` untuk laporan keuangan, dan API dokumen Frappe untuk penulisan. Karena berjalan di dalam proses Frappe dengan `frappe.session.user`, izin user berlaku **native** — tidak perlu kredensial layanan.
> - **Skema tool dipinjam, bukan dikarang ulang:** nama tool, deskripsi, dan skema parameter diadaptasi dari [`@casys/mcp-erpnext`](https://www.npmjs.com/package/@casys/mcp-erpnext) v3.3.0 (**MIT**). Notice lisensinya **wajib** disertakan di `THIRD_PARTY_NOTICES.md`.
> - **Yang tetap ditulis sendiri:** eksekusi, pemaksaan `company`, pengecekan izin, pencatatan token, dan trace. Bagian inilah yang menentukan keamanan, jadi tidak boleh dipinjam.
> - **Yang tidak diambil:** `@casys/mcp-erpnext` sebagai *server* MCP (satu API key untuk semua user) dan FAC (AGPL-3.0). Lihat §2.3.

### 2.3. Batas Eksekusi Agen (*Sandbox*)

Agen AIOS dijalankan di dalam **kotak tertutup**: ia hanya bisa melakukan apa yang diizinkan tool-nya, dan tidak bisa keluar dari batas itu. Prinsipnya **memperkecil permukaan, bukan mengurung proses** — kalau tidak ada pintu, tidak perlu penjara.

| Aturan (mengikat) | Status penegakan sekarang |
|---|---|
| Agen **tidak punya shell/terminal** — tidak ada `subprocess`, `os.system`, `eval`, atau `exec` di lapisan tool | **Ditegakkan** (`aios_v1/lib/tool_registry.py`; direktori `aios_v1/lib/tools/` dihapus di `#13`) |
| Agen **tidak boleh membaca/menulis file server** di luar DocType `File` Frappe (private, terikat `AIOS Conversation`) | **Ditegakkan** — upload chat (`/api/chat/upload`), workspace `workspace_create_file`, dan `document_extract` hanya memakai Private `File` terikat conversation milik session user (H5 fase 1); `has_permission` tidak diandalkan sendirian karena `Administrator` bypass |
| Agen **tidak punya akses jaringan bebas**; hanya plugin terdaftar, dengan guard anti-SSRF | `web_fetch` memvalidasi dan mem-pin koneksi ke IP publik, memeriksa ulang setiap redirect, dan membatasi ukuran/waktu/jenis konten. Client MCP memvalidasi endpoint serta DNS sebelum panggilan SDK, tetapi SDK melakukan resolusi koneksinya sendiri; pinning koneksi MCP belum terbukti |
| Agen **tidak bisa memalsukan identitas/company** — `user_id`, `allowed_company` disembunyikan dari LLM dan diisi dari sesi | **Ditegakkan** (`_HIDDEN_TOOL_PARAMS` + `execute_tool`) |
| Client hanya melihat data ERP **company aktif** di layer permission Frappe, bukan hanya di layer tool | **Ditegakkan** — hook `erp_company_query_conditions`/`erp_company_has_permission` untuk `ERP_CLIENT_DOCTYPES` (company dari `AIOS Setting.default_company`, fallback `Global Defaults`; fail-closed tanpa company; `Company` di-scope via `name`; DocType tanpa field `company` tidak di-scope) + guard `query_report.run` (`report_guard.py`) yang memaksa company aktif; Administrator/AIOS Admin bypass |
| Agen **tidak menjalankan SQL sama sekali** — tidak ada akses ke database eksternal | **Ditegakkan** — adapter DB eksternal dihapus (`#13`) |
| Delegasi maksimal **2 tingkat** | H4 fase 1: depth maksimum 2; Orchestrator depth 0 memanggil worker depth 1, worker tidak dapat mendelegasikan ulang. Key worker dinormalisasi ke key canonical (`financial_analyst`/`Financial Analyst` → `financial-analyst`); worker tak dikenal ditolak `DELEGATION_INVALID` dengan daftar worker valid cabang, tanpa menjalankan runner |
| Jawaban yang berhenti karena batas output model ditandai jujur | **Ditegakkan** — `chat_stream` membaca `finish_reason` provider; bila jawaban akhir berakhir `length`, handle_stream menambah penanda `_[Jawaban terpotong karena batas output model.]_` plus Error Log (tanpa isi prompt); `max_tokens` 2048 dan `MAX_TOOL_ROUNDS` 6 tidak berubah |
| Trace tool Sub-Agent | H4 fase 1 mengirim panggilan dan argumen aman lewat SSE; audit trail persisten dan trace tool Orchestrator belum ada |

**Status jujur:** beberapa aturan aman *karena tool-nya belum ada*, bukan karena ada penahan. Aturan di atas tetap mengikat dan wajib diuji saat tool baru ditambahkan.

**Batas H2 fase 3:** hanya Streamable HTTP untuk client MCP; SSE menghasilkan `MCP_TRANSPORT_UNSUPPORTED`, autentikasi belum didukung, dan tidak ada audit trail tool-call. MCP eksternal umum dapat dipakai setelah plugin dikonfigurasi dan discovery eksplisit; server MCP ERPNext tetap tidak digunakan untuk menjaga identitas dan izin per-user.

**Yang sengaja belum dipakai:** isolasi level OS (container/seccomp per agen). Tool berjalan di proses web Frappe yang sama, jadi kurungannya **logis** (dijaga kode), bukan **fisik**. Ini dicatat sebagai jalur *upgrade* bila satu server memuat banyak klien sekaligus — bukan kebutuhan PoC.

**MCP eksternal untuk ERPNext — dievaluasi, tidak dipakai di PoC.** Server MCP ERPNext sudah ada di pasar dan diuji: `@casys/mcp-erpnext` (MIT, 127 tool) dan Frappe Assistant Core (AGPL-3.0, 24 tool). Keduanya tidak dipakai sebagai server karena:
1. **Identitas.** casys memakai satu `ERPNEXT_API_KEY`/`API_SECRET` untuk semua pemanggil — semua user AIOS akan tampil sebagai satu user ERPNext, sehingga isolasi per-user tidak lagi dijamin ERPNext.
2. **Lisensi.** FAC berlisensi AGPL-3.0; memakai kodenya akan menarik kewajiban AGPL ke seluruh AIOS yang akan dijual.
3. **Sandbox.** Server MCP adalah proses eksternal; setiap tool call menjadi lompatan jaringan keluar, sehingga batas eksekusi agen menjadi lebih sulit dipertanggungjawabkan.

Keputusan: **skema tool-nya dipinjam (MIT), servernya tidak.** Ini memberi keuntungan desain tool tanpa mengorbankan isolasi.

Keputusan tersebut khusus server MCP ERPNext. Client MCP Streamable HTTP fase H2 dapat menghubungkan plugin eksternal yang dikonfigurasi operator; autentikasi dan pinning IP koneksi SDK belum didukung.

---

## 3. Kontrak *Live Agent Trace* & Artefak

Tata letak antarmuka (desktop OS, taskbar, panel agent, jendela modul) diatur di **[`docs/08`](./08-desain-ekasa-desk.md)**. Bagian ini hanya menetapkan **kontrak** yang tidak boleh berubah walau tampilannya berubah. Kontrak transport dan event dasar di luar trace ada di §3.3.

### 3.1. *Live Agent Trace* (Kontrak 5 Event)

Ketika Orchestrator mendelegasikan tugas ke Sub-Agent (maksimal 2 tingkat; Sub-Agent tidak menerima tool delegasi lagi) atau meminta konsultasi lintas cabang (`Sales` ↔ `Finance`), stream SSE memakai 5 event kanonik (`aios_v1/shared/trace_events.py`). `MAX_CHAIN_DEPTH = 5` membatasi rantai konsultasi lintas cabang dan terpisah dari `MAX_DELEGATION_DEPTH = 2`.

1. `trace_delegate_start`
2. `trace_subagent_prompt`
3. `trace_subagent_tool`
4. `trace_subagent_result`
5. `trace_cross_branch`

**Isi yang wajib bisa dibaca pengguna:** instruksi tugas yang dikirim Orchestrator ke Sub-Agent, panggilan tool beserta argumen bisnis (key sensitif disensor), durasi, pemakaian token sub-agent, dan hasil yang dikembalikan.

Kontrak trace: `trace_delegate_start` memuat `from`, `to`, `instruction`; `trace_subagent_prompt` memuat `agent`, ringkasan metadata role aman pada `system_prompt_summary`, dan `task_prompt`; `trace_subagent_tool` memuat `agent`, `tool`, `args`; `trace_subagent_result` memuat `agent`, `status` (`success`, `partial`, `failed`), `summary`, `usage`, dan `duration_ms`; `trace_cross_branch` memuat `from_branch`, `to_branch`, `payload`, dan `result` yang disanitasi. Argumen/payload menyensor nilai pada key yang mengandung `token`, `secret`, `password`, `credential`, atau `auth`, dan menghapus `user_id` serta `allowed_company`. Ringkasan prompt hanya metadata role, bukan system prompt, ETHOS, atau guard.

**Yang tidak boleh ditampilkan:** *system prompt* internal AIOS (instruksi dasar, ETHOS, guard). Trace menampilkan **tugas, tool, dan hasil** — bukan resep produk.

### 3.2. Approval Card dan Artefak File

Event `artifact_created` untuk Approval Card adalah kartu virtual backend H4, berisi `artifact.type = "APPROVAL_CARD"` dan `draft_id`; kartu mengambil nilai sebelum/sesudah dari `get_draft`. Event ini tidak membuat file. **Artefak file diimplementasikan pada H5 fase 1 (`b07975f`):** plugin `workspace-artifact-builder` membuat Private File (`is_private=1`) terikat ke `AIOS Conversation` milik `frappe.session.user` melalui `aios_v1/lib/workspace.py` (sanitasi nama, cek kepemilikan `conversation.user == session user`, verifikasi pasca-insert, tanpa commit di helper); `document_extract` kini hanya membaca File privat milik user yang terikat ke conversation aktif. Bentuk tampilan UI diatur di `docs/08` §5 dan masuk #12.

Jenis artefak yang direncanakan: Approval Card (kontrak approval Alur 5; event backend H4 fase 2), tabel & grafik data, dokumen eksekutif + diagram Mermaid, spreadsheet `.xlsx`/`.csv`, dan presentasi HTML terisolasi. File privat dan builder file selesai di backend H5 fase 1; grafik interaktif, Mermaid, dan iframe menyusul.

### 3.3. Transport SSE & Event Dasar

Semua event dikirim sebagai satu baris `data: <json>\n\n` pada response
`text/event-stream`. Setiap payload wajib punya field `type`.

**Event dasar yang dipakai sekarang** (`aios_v1/managers/base_manager.py`):

| Event | Payload | Kapan dikirim |
|---|---|---|
| `meta` | `{"type": "meta", "conversationId": <int>}` | sekali, di awal stream |
| `delta` | `{"type": "delta", "text": <str>}` | setiap potongan teks jawaban |
| `done` | `{"type": "done", "conversationId": <int>, "delegatedTo": <str>, "dataUsed": <list>, "limitation": <str>, "tokens": <int>}` | sekali, di akhir stream yang selesai normal |

**Event yang sudah ditetapkan; semua event di bawah telah diimplementasikan di backend:**

| Event | Payload | Kapan dikirim |
|---|---|---|
| `trace_delegate_start`, `trace_subagent_prompt`, `trace_subagent_tool`, `trace_subagent_result` | lihat §3.1 | H4 fase 1 |
| `trace_cross_branch` | lihat §3.1 | H4 fase 2 |
| `artifact_created` Approval Card | `{"type": "artifact_created", "artifact": {"type": "APPROVAL_CARD", "draft_id": ..., "action_type": ..., "doctype": ..., "branch": ...}}` | H4 fase 2; event backend, UI #12 |
| `artifact_created` file/workspace | `{"type": "artifact_created", "artifact": {"type": "FILE", "file_name": ..., "file_url": ..., "format": ..., "size": ..., "conversation_id": ...}}` — whitelist tanpa `file_id`, tanpa path filesystem, tanpa isi file | **H5 fase 1** (`b07975f`); dikirim manager maupun sub-agent setelah `workspace_create_file` sukses; UI #12 |

**Diperbarui #12 fase 2a (2026-10-25): event tool call tingkat Orchestrator kini dikirim** memakai ulang `trace_subagent_tool` dengan `agent = "Orchestrator"` (tanpa event baru; `cross_branch_consultation` dikecualikan karena sudah punya `trace_cross_branch`). **`artifact_created` APPROVAL_CARD kini juga dikirim dari loop Sub-Agent** (sebelumnya hanya Orchestrator), dengan bentuk payload yang sama. Method `list_pending_drafts` (whitelisted, owner-scoped, hanya `PENDING_APPROVAL`) tersedia untuk UI kartu setelah reload. Loop dibatasi `MAX_TOOL_ROUNDS = 6`; bila habis, stream mengirim pesan aman dan mencatatnya ke `Error Log`. Ketentuan tanpa audit trail untuk tool eksternal MCP pada H2 tetap berlaku; nonce manual dapat membuktikan panggilan, tetapi tidak menciptakan audit trail.
