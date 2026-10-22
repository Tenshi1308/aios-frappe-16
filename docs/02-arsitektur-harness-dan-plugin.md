# 02 — Arsitektur Harness, Model Routing, Plugin/MCP, & Kontrak Trace

Dokumen ini menjelaskan bagaimana AIOS V1 mengadopsi arsitektur *AI Harness* modern (seperti OpenCode, Claude Code, dan Antigravity) yang disesuaikan khusus untuk pengguna bisnis di atas ERPNext dengan isolasi **`1 Client = 1 Site`**.

---

## 1. Manajemen Multi-Provider & Per-Agent Model Routing (Berbasis UI, Zero Hardcode)

Pada coding harness modern, pengguna mengatur provider dan model melalui file konfigurasi seperti `opencode.jsonc`. Karena target pengguna AIOS adalah pelaku bisnis, **seluruh konfigurasi tersebut dikelola melalui antarmuka grafis (UI) di Developer Control Plane `AIOS Admin` dan disimpan di database DocType Frappe milik site klien**—tanpa satu pun nama model atau URL provider yang di-hardcode di kode Python.

> **Batas control plane vs data plane:** UI pengaturan (provider, model routing, plugin/MCP) berada di Developer Control Plane agar `AIOS Admin` bisa mengelola banyak klien dari satu dashboard; **datanya tetap tersimpan di site klien masing-masing** (`docs/03` §1.4). Control plane hanya menyimpan registry site + kredensial Control API, sehingga kredensial LLM klien tidak pernah terkonsentrasi di satu database developer.

### 1.1. Kapabilitas Konfigurasi di Developer Control Plane
1. **Multi-Provider Registry (`AIOS LLM Provider`, data di site klien):**
   - `AIOS Admin` dapat menambah, mengubah, mengaktifkan/menonaktifkan, atau menghapus provider LLM (misalnya OpenRouter, OpenAI, Anthropic, Google Gemini, DeepSeek, atau server vLLM/Ollama internal) untuk *site* klien yang dipilih dari registry `AIOS Client Site`.
   - Setiap provider menyimpan `provider_name`, `base_url`, `api_key` (menggunakan fieldtype `Password` terenkripsi Frappe; memisahkan rahasia dari `AIOS Setting`), daftar model yang tersedia, serta struktur tarif token (*input/output cost per 1M tokens*). Penulisan ke site klien berjalan lewat Control API dengan role `AIOS Control`, bukan login Desk.
2. **Pemetaan Model Spesifik per Agen (`AIOS Agent Model Route`):**
   - Setiap **Orchestrator** (`Finance Manager`, `Sales Manager`) dan setiap **Sub-Agent Spesialis** (`cfo`, `financial-analyst`, `treasurer`, `budgeting-staff`, `finance-staff`, `sales-representative`, `sales-data-analyst`, `customer-service`, `marketing-specialist`) memiliki slot konfigurasi modelnya masing-masing.
   - Memiliki field unik `route_key` (`f"{branch_key}:{agent_key}:{user or '*'}"`) dan validasi `agent_key` terhadap `registry.py` saat `validate()` agar tidak pernah ada duplikasi rute atau salah ketik (*typo*) nama agen.
3. **Prinsip *Fail-Loudly* (Dilarang Fallback Hardcode):**
   - Apabila suatu Orchestrator atau Sub-Agent dipanggil namun provider atau modelnya belum dikonfigurasi/dinonaktifkan di database, sistem **wajib menolak eksekusi secara eksplisit** dengan pesan error yang jelas dan mencatatnya ke `Error Log` Frappe. Sistem dilarang keras jatuh ke nilai default hardcoded di dalam kode.
4. **Cakupan Site-Wide di Site Klien (Dengan Kesiapan Override Per-User):**
   - Karena setiap klien memiliki *site* sendiri (`1 Client = 1 Site`), konfigurasi Provider & Model diatur per site klien (`user = NULL` / `*` pada `route_key`) oleh `AIOS Admin` dari control plane.
   - Jika terdapat rute spesifik untuk `user == frappe.session.user`, resolver memprioritaskan rute spesifik user tersebut sebelum jatuh ke rute global site.

---

## 2. Arsitektur Plugin & MCP Manager (`AIOS Plugin`)

Alih-alih menulis ratusan fungsi Python spesifik yang kaku dan sulit dirawat, lapisan eksekusi tool AIOS dibangun dengan arsitektur **Modular Plugin & Model Context Protocol (MCP)** melalui DocType **`AIOS Plugin`**.

### 2.1. Manajemen via UI (Developer Control Plane, data di site klien)
- Menyediakan katalog plugin yang dapat di-*toggle* **On/Off** secara langsung dari UI control plane untuk *site* klien yang dipilih.
- Mengatur *Role-Scoping* (*Least Privilege*) melalui child table `AIOS Plugin Scope`: menentukan plugin/tool mana yang boleh diakses oleh cabang (`finance`, `sales`) dan jabatan sub-agent tertentu.
- Mendukung pendaftaran **External MCP Server / Plugin** (melalui endpoint *Streamable HTTP / SSE* atau paket standar komunitas open-source) sehingga kemampuan agen dapat terus bertambah tanpa mengubah kode inti (*core engine*) AIOS.

### 2.2. Katalog *Built-in Default Plugins* (Fondasi Bisnis)
AIOS hadir dengan himpunan plugin bawaan (*default*) untuk kebutuhan kritikal bisnis yang dapat terus ditambah seiring pengembangan proyek:

| ID Plugin Bawaan (`AIOS Plugin`) | Fungsi Utama | Sumber / Primitif yang Dipakai |
|---|---|---|
| **`erpnext-core-data`** | Intropeksi skema DocType, pembacaan daftar & detail dokumen master maupun transaksi (`Sales Order`, `Sales Invoice`, `Delivery Note`, `Payment Entry`, `Journal Entry`, `GL Entry`, `Customer`, `Supplier`, `Item`) yang terfilter ketat ke `Company` aktif di site tersebut (`frappe.db.get_single_value("AIOS Setting", "default_company")`). | `frappe.get_list`, `frappe.get_doc(..., check_permission="read")`, `frappe.get_meta` (didukung `Custom DocPerm` `read=1` untuk `AIOS Client`) |
| **`erpnext-financial-reports`** | Menjalankan mesin laporan akuntansi & penjualan resmi bawaan ERPNext (*General Ledger*, *Accounts Receivable/Payable Aging*, *Trial Balance*, *Profit and Loss Statement*, *Balance Sheet*, *Cash Flow*, *Sales Analytics*). | `frappe.desk.query_report.run` (didukung `Custom DocPerm` `report=1` untuk `AIOS Client` pada DocType referensi laporan) |
| **`erpnext-action-drafts`** | Menyusun draf transaksi bisnis baru (*Quotation*, *Sales Order*, *Sales Invoice*, *Payment Entry*, *Journal Entry*) ke tabel antrean persetujuan manusia (`Pending Action Draft` dengan `user = frappe.session.user`). | Doctype `Pending Action Draft` + validasi skema ERPNext |
| **`quant-calculator`** | Kalkulator finansial dan statistik deterministik di Python (perhitungan margin, delta pertumbuhan MoM/YoY, pajak, proyeksi arus kas, dan rekonsiliasi selisih angka) agar LLM tidak pernah menebak hitungan matematika. | Modul komputasi numerik Python stdlib terisolasi (tanpa dependency berat) |
| **`document-intelligence`** | Mengekstrak teks dan tabel terstruktur dari dokumen yang diunggah pengguna klien (PDF invoice/PO, CSV, spreadsheet Excel `.xlsx`) untuk dianalisis atau dicocokkan dengan pembukuan ERPNext. | `pypdf`, `openpyxl`, parser tabular CSV/XLSX |
| **`workspace-artifact-builder`** | Membuat file kerja nyata di ruang kerja sesi pengguna (`.xlsx`, `.csv`, `.pdf`, `.md`) melalui DocType `File` (`is_private=1`) serta mengirim spesifikasi grafik interaktif & diagram Mermaid agar dibuka sebagai jendela di desktop. | Frappe Private `File` API (`save_file`) & renderer artefak (`docs/08` §5) |
| **`web-market-research`** | Mencari informasi bisnis publik terkini (kurs pajak/valas, regulasi keuangan/pajak terbaru, riset pasar & profil calon pelanggan B2B). | HTTP Web Search & Fetcher dengan guard anti-SSRF ketat (blokir IP privat RFC1918, loopback, link-local, cloud metadata `169.254.169.254`, dan re-check setiap hop redirect) |

> **Tiga plugin ERPNext adalah *wrapper tipis*, bukan implementasi baru.**
> - **Logika data memakai ERPNext sendiri:** `frappe.get_list` / `frappe.get_doc` untuk dokumen, `frappe.desk.query_report.run` untuk laporan keuangan, dan API dokumen Frappe untuk penulisan. Karena berjalan di dalam proses Frappe dengan `frappe.session.user`, izin user berlaku **native** — tidak perlu kredensial layanan.
> - **Skema tool dipinjam, bukan dikarang ulang:** nama tool, deskripsi, dan skema parameter diadaptasi dari [`@casys/mcp-erpnext`](https://www.npmjs.com/package/@casys/mcp-erpnext) v3.3.0 (**MIT**). Notice lisensinya **wajib** disertakan di `THIRD_PARTY_NOTICES.md`.
> - **Yang tetap ditulis sendiri:** eksekusi, pemaksaan `company`, pengecekan izin, pencatatan token, dan trace. Bagian inilah yang menentukan keamanan, jadi tidak boleh dipinjam.
> - **Yang tidak diambil:** `@casys/mcp-erpnext` sebagai *server* MCP (satu API key untuk semua user) dan FAC (AGPL-3.0). Lihat §2.3.

### 2.3. Batas Eksekusi Agen (*Sandbox*)

Agen AIOS dijalankan di dalam **kotak tertutup**: ia hanya bisa melakukan apa yang diizinkan tool-nya, dan tidak bisa keluar dari batas itu. Prinsipnya **memperkecil permukaan, bukan mengurung proses** — kalau tidak ada pintu, tidak perlu penjara.

| Aturan (mengikat) | Status penegakan sekarang |
|---|---|
| Agen **tidak punya shell/terminal** — tidak ada `subprocess`, `os.system`, `eval`, atau `exec` di lapisan tool | **Ditegakkan** (`aios_v1/lib/tools/`, `tool_registry.py`) |
| Agen **tidak boleh membaca/menulis file server** di luar DocType `File` Frappe (private, terikat `AIOS Conversation`) | **Belum relevan** — belum ada tool file; aturan mengikat saat tool baru ditambahkan |
| Agen **tidak punya akses jaringan bebas**; hanya plugin terdaftar, dengan guard anti-SSRF | **Ditegakkan** pada `web-market-research` |
| Agen **tidak bisa memalsukan identitas/company** — `user_id`, `tenant_id`, `allowed_company` disembunyikan dari LLM dan diisi dari sesi | **Ditegakkan** (`_HIDDEN_TOOL_PARAMS` + `execute_tool`) |
| Agen **tidak menjalankan SQL sama sekali** — tidak ada akses ke database eksternal | **Ditegakkan** — adapter DB eksternal dihapus (`#13`) |
| Delegasi maksimal **2 tingkat** | **Ditegakkan** (`MAX_DELEGATION_DEPTH = 2`) |
| Setiap tool call **tercatat** | **Sebagian** — trace event ada, audit trail terpisah belum |

**Status jujur:** beberapa aturan aman *karena tool-nya belum ada*, bukan karena ada penahan. Aturan di atas tetap mengikat dan wajib diuji saat tool baru ditambahkan.

**Yang sengaja belum dipakai:** isolasi level OS (container/seccomp per agen). Tool berjalan di proses web Frappe yang sama, jadi kurungannya **logis** (dijaga kode), bukan **fisik**. Ini dicatat sebagai jalur *upgrade* bila satu server memuat banyak klien sekaligus — bukan kebutuhan PoC.

**MCP eksternal untuk ERPNext — dievaluasi, tidak dipakai di PoC.** Server MCP ERPNext sudah ada di pasar dan diuji: `@casys/mcp-erpnext` (MIT, 127 tool) dan Frappe Assistant Core (AGPL-3.0, 24 tool). Keduanya tidak dipakai sebagai server karena:
1. **Identitas.** casys memakai satu `ERPNEXT_API_KEY`/`API_SECRET` untuk semua pemanggil — semua user AIOS akan tampil sebagai satu user ERPNext, sehingga isolasi per-user tidak lagi dijamin ERPNext.
2. **Lisensi.** FAC berlisensi AGPL-3.0; memakai kodenya akan menarik kewajiban AGPL ke seluruh AIOS yang akan dijual.
3. **Sandbox.** Server MCP adalah proses eksternal; setiap tool call menjadi lompatan jaringan keluar, sehingga batas eksekusi agen menjadi lebih sulit dipertanggungjawabkan.

Keputusan: **skema tool-nya dipinjam (MIT), servernya tidak.** Ini memberi keuntungan desain tool tanpa mengorbankan isolasi.

---

## 3. Kontrak *Live Agent Trace* & Artefak

Tata letak antarmuka (desktop OS, taskbar, panel agent, jendela modul) diatur di **[`docs/08`](./08-desain-ekasa-desk.md)**. Bagian ini hanya menetapkan **kontrak** yang tidak boleh berubah walau tampilannya berubah.

### 3.1. *Live Agent Trace* (Kontrak 5 Event)

Ketika Orchestrator mendelegasikan tugas ke Sub-Agent (dibatasi `MAX_DELEGATION_DEPTH = 2`; Sub-Agent tidak menerima tool delegasi lagi untuk mencegah rekursi) atau melakukan konsultasi lintas cabang (`Sales` ↔ `Finance`), stream SSE mengirimkan 5 event kanonik (`aios_v1/shared/trace_events.py`):

1. `trace_delegate_start`
2. `trace_subagent_prompt`
3. `trace_subagent_tool`
4. `trace_subagent_result`
5. `trace_cross_branch`

**Isi yang wajib bisa dibaca pengguna:** instruksi tugas yang dikirim Orchestrator ke Sub-Agent, panggilan tool beserta **argumen aslinya**, durasi, pemakaian token sub-agent, dan hasil yang dikembalikan.

**Yang tidak boleh ditampilkan:** *system prompt* internal AIOS (instruksi dasar, ETHOS, guard). Trace menampilkan **tugas, tool, dan hasil** — bukan resep produk.

### 3.2. Artefak (Private `File`)

Setiap artefak yang dibuat agen disimpan sebagai **Private File (`is_private=1`)** Frappe, terikat ke `AIOS Conversation` milik `frappe.session.user`. Bentuk tampilannya — file dan jendela di desktop — diatur di `docs/08` §5.

Jenis artefak yang didukung: **Approval Card** (draf transaksi), tabel & grafik data, dokumen eksekutif + diagram Mermaid, spreadsheet `.xlsx`/`.csv`, dan presentasi HTML terisolasi.
