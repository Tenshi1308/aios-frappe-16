# 02 — Arsitektur Harness, Model Routing, Plugin/MCP, & Workspace Canvas

Dokumen ini menjelaskan bagaimana AIOS V1 mengadopsi arsitektur *AI Harness* modern (seperti OpenCode, Claude Code, dan Antigravity) yang disesuaikan khusus untuk pengguna bisnis di atas ERPNext dengan isolasi **`1 Client = 1 Site`**.

---

## 1. Manajemen Multi-Provider & Per-Agent Model Routing (Berbasis UI, Zero Hardcode)

Pada coding harness modern, pengguna mengatur provider dan model melalui file konfigurasi seperti `opencode.jsonc`. Karena target pengguna AIOS adalah pelaku bisnis, **seluruh konfigurasi tersebut dikelola melalui antarmuka grafis (UI) di Portal `AIOS Admin` dan disimpan di database DocType Frappe**—tanpa satu pun nama model atau URL provider yang di-hardcode di kode Python.

### 1.1. Kapabilitas Konfigurasi di Portal `AIOS Admin`
1. **Multi-Provider Registry (`AIOS LLM Provider`):**
   - `AIOS Admin` dapat menambah, mengubah, mengaktifkan/menonaktifkan, atau menghapus provider LLM (misalnya OpenRouter, OpenAI, Anthropic, Google Gemini, DeepSeek, atau server vLLM/Ollama internal).
   - Setiap provider menyimpan `provider_name`, `base_url`, `api_key` (menggunakan fieldtype `Password` terenkripsi Frappe; memisahkan rahasia dari `AIOS Setting`), daftar model yang tersedia, serta struktur tarif token (*input/output cost per 1M tokens*).
2. **Pemetaan Model Spesifik per Agen (`AIOS Agent Model Route`):**
   - Setiap **Orchestrator** (`Finance Manager`, `Sales Manager`) dan setiap **Sub-Agent Spesialis** (`cfo`, `financial-analyst`, `treasurer`, `budgeting-staff`, `finance-staff`, `sales-representative`, `sales-data-analyst`, `customer-service`, `marketing-specialist`) memiliki slot konfigurasi modelnya masing-masing.
   - Memiliki field unik `route_key` (`f"{branch_key}:{agent_key}:{user or '*'}"`) dan validasi `agent_key` terhadap `registry.py` saat `validate()` agar tidak pernah ada duplikasi rute atau salah ketik (*typo*) nama agen.
3. **Prinsip *Fail-Loudly* (Dilarang Fallback Hardcode):**
   - Apabila suatu Orchestrator atau Sub-Agent dipanggil namun provider atau modelnya belum dikonfigurasi/dinonaktifkan di database, sistem **wajib menolak eksekusi secara eksplisit** dengan pesan error yang jelas dan mencatatnya ke `Error Log` Frappe. Sistem dilarang keras jatuh ke nilai default hardcoded di dalam kode.
4. **Cakupan Site-Wide di `AIOS Admin` (Dengan Kesiapan Override Per-User):**
   - Karena setiap klien memiliki *site* sendiri (`1 Client = 1 Site`), konfigurasi Provider & Model diatur terpusat oleh `AIOS Admin` pada site tersebut (`user = NULL` / `*` pada `route_key`).
   - Jika terdapat rute spesifik untuk `user == frappe.session.user`, resolver memprioritaskan rute spesifik user tersebut sebelum jatuh ke rute global site.

---

## 2. Arsitektur Plugin & MCP Manager (`AIOS Plugin`)

Alih-alih menulis ratusan fungsi Python spesifik yang kaku dan sulit dirawat, lapisan eksekusi tool AIOS dibangun dengan arsitektur **Modular Plugin & Model Context Protocol (MCP)** melalui DocType **`AIOS Plugin`**.

### 2.1. Manajemen via UI (`AIOS Admin`)
- Menyediakan katalog plugin yang dapat di-*toggle* **On/Off** secara langsung dari UI.
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
| **`workspace-artifact-builder`** | Membuat file kerja nyata di ruang kerja sesi pengguna (`.xlsx`, `.csv`, `.pdf`, `.md`) melalui DocType `File` (`is_private=1`) serta mengirim spesifikasi grafik interaktif & diagram Mermaid ke panel Canvas UI. | Frappe Private `File` API (`save_file`) & Canvas Renderer |
| **`web-market-research`** | Mencari informasi bisnis publik terkini (kurs pajak/valas, regulasi keuangan/pajak terbaru, riset pasar & profil calon pelanggan B2B). | HTTP Web Search & Fetcher dengan guard anti-SSRF ketat (blokir IP privat RFC1918, loopback, link-local, cloud metadata `169.254.169.254`, dan re-check setiap hop redirect) |

---

## 3. Desain UI/UX Workspace: *Live Agent Trace* & *5-Tier Artifact Canvas*

Antarmuka kerja `AIOS Client` dibagi menjadi dua ruang utama yang bekerja berdampingan:

### 3.1. Kolom Kiri: Percakapan & *Live Agent Trace* (Tanpa Emoji)
- Seluruh elemen antarmuka menggunakan **ikon garis vektor bersih (Lucide/Geist)** dan **badge tipografi tegas** (`DELEGATE`, `CONSULT`, `TOOL CALL`, `COMPLETED`) — tanpa penggunaan emoji dekoratif (termasuk mengganti 9 ikon emoji di `frontend/lib/branches.ts` menjadi key ikon vektor).
- Ketika Orchestrator mendelegasikan tugas ke Sub-Agent (dibatasi `MAX_DELEGATION_DEPTH = 2` di mana Sub-Agent tidak menerima tool delegasi lagi untuk mencegah rekursi tak terbatas) atau melakukan konsultasi lintas cabang (`Sales` ↔ `Finance`), stream SSE mengirimkan 5 event kanonik (`aios_v1/shared/trace_events.py`):
  1. `trace_delegate_start`
  2. `trace_subagent_prompt`
  3. `trace_subagent_tool`
  4. `trace_subagent_result`
  5. `trace_cross_branch`
- Pengguna dapat membuka kartu trace untuk membaca instruksi prompt yang dikirim Orchestrator ke Sub-Agent, daftar pemanggilan tool beserta argumennya, durasi eksekusi, pemakaian token sub-agent, dan hasil analisis yang dikembalikan ke Orchestrator.

### 3.2. Kolom Kanan: *Isolated Workspace & 5-Tier Artifact/Canvas Space*
Setiap file artefak yang dibuat oleh agen disimpan sebagai **Private File (`is_private=1`)** di Frappe yang terikat ke `AIOS Conversation` milik `frappe.session.user` dan dirender ke panel **Canvas** di sebelah kanan layar chat:

1. **Tier 1 — Interactive Action & Approval Cards (Prioritas Tertinggi Transaksi ERP):**
   - Menampilkan rincian draf transaksi (`Pending Action Draft`) dalam bentuk kartu interaktif berisi tabel item/akun, nominal, dan alasan bisnis, dilengkapi tombol aksi **Approve & Post to ERPNext**, **Reject**, atau **Revise**.
2. **Tier 2 — Interactive Data Tables & Business Charts:**
   - Merender grafik keuangan dan penjualan interaktif (*Bar, Line, Area, Pie/Donut, Aging Breakdown*) beserta tabel data dinamis yang dapat diurutkan (*sort*) dan disaring (*filter*) langsung oleh pebisnis.
3. **Tier 3 — Structured Executive Documents & Mermaid Diagrams:**
   - Merender laporan naratif lengkap (Memo CFO, Analisis Kinerja Bulanan, Proposal Penawaran Sales) lengkap dengan diagram alur/struktur **Mermaid** dan opsi cetak/ekspor ke **PDF**.
4. **Tier 4 — Downloadable Business Spreadsheets (`.xlsx` / `.csv`):**
   - Menghasilkan file spreadsheet Excel (`.xlsx` via `openpyxl`) dan `.csv` dari hasil olahan data ERPNext yang dapat ditinjau (*preview*) di Canvas dan diunduh langsung oleh pengguna.
5. **Tier 5 — Static HTML Presentation Deck:**
   - Merender slide presentasi eksekutif ringkas berbasis HTML terisolasi untuk rapat manajemen.
