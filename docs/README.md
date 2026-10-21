# Dokumentasi Proyek AIOS V1 (Enterprise Business AI Harness)

Folder `docs/` ini memuat spesifikasi produk, arsitektur teknis, tata kelola *Site-Level Multi-Tenancy* (`1 Client = 1 Site`), alur kerja *end-to-end*, roadmap eksekusi berurutan, serta referensi pasar/kompetitor untuk **AIOS V1** di atas **Frappe 16 + ERPNext** dan **Next.js**.

## Daftar Dokumen (Urutan Baca & Eksekusi)

> **Klasifikasi tiap dokumen** (pakai ini saat kode dan dokumen berbeda):
> - *Spesifikasi normatif* — apa yang harus benar. Bila kode ≠ dokumen, **yang diubah adalah kode**.
> - *Roadmap & status* — rencana eksekusi + progres. Bila kode belum sesuai, artinya belum dikerjakan (atau salah); **yang diperbarui statusnya**, bukan kode yang diundur.
> - *Referensi pasar* — konteks eksternal & positioning. Dipakai untuk keputusan produk, bukan aturan perilaku; bila berbeda dengan spesifikasi normatif, spesifikasi yang menang.

1. **[01 — Profil dan Visi Produk](./01-profil-dan-visi-produk.md)** — *spesifikasi normatif*
   - Esensi AIOS sebagai *Business AI Harness* (bukan chatbot tanya-jawab biasa dan bukan coding harness).
   - Strategi *Depth over Breadth*: fokus kedalaman penuh pada divisi **Finance** dan **Sales** (*Order-to-Cash* & pelaporan akuntansi) sebagai fondasi pembuktian produk.
   - Struktur organisasi agen bisnis (Orchestrator / AI Manager & Sub-Agents spesialis) yang bekerja layaknya perusahaan mandiri.
   - Model SaaS **1 Client = 1 Site** dan dua portal berbasis Role (`AIOS Admin` & `AIOS Client`).

2. **[02 — Arsitektur Harness, Model Routing, Plugin/MCP, & Workspace Canvas](./02-arsitektur-harness-dan-plugin.md)** — *spesifikasi normatif*
   - Konfigurasi Provider LLM & pemetaan model per Orchestrator/Sub-Agent berbasis UI & DocType (`AIOS LLM Provider` & `AIOS Agent Model Route` dengan `route_key` unik dan validasi ke `registry.py`, *Zero Hardcode*).
   - Arsitektur **Plugin & MCP Manager (`AIOS Plugin`)**: katalog 7 *Built-in Default Plugins* (didukung `Custom DocPerm` `read=1, report=1` untuk `AIOS Client`) dan dukungan External MCP Server.
   - Desain **Live Agent Trace** (5 event SSE kanonik termasuk `trace_subagent_prompt`, batas rekursi `MAX_DELEGATION_DEPTH = 2`, tanpa emoji dekoratif).
   - Arsitektur **Isolated Workspace (Frappe Private `File`) & 5-Tier Artifact/Canvas Space**.

3. **[03 — Skema Data, Identitas Frappe (`User`), & Arsitektur `1 Client = 1 Site`](./03-skema-data-dan-isolasi-multitenant.md)** — *spesifikasi normatif*
   - Konsep **1 Client = 1 Site (`dns_multitenant`)**: setiap klien memiliki *site* dan database MariaDB terpisah, sehingga DocType `AIOS Tenant` dihapus sepenuhnya.
   - Pemusatan atribut operasional & kuota langsung pada DocType **`User`** bawaan Frappe (`aios_persona`, `aios_persona_context`, `aios_status`, `aios_company_name`, `aios_token_limit`, `aios_tokens_used`) dengan update kuota atomik via SQL dan nilai *default* tingkat site di **`AIOS Setting`**.
   - Matriks otoritatif `User.aios_status` × `User.enabled` beserta pertahanan 3 lapis (`send_welcome_email = 0` + `no_welcome_mail = True`, sinkronisasi `enabled = 0`, serta hook `on_login` & `auth_hooks`).
   - Pendaftaran skema Custom Field, Role, Role Profile, dan `Custom DocPerm` secara terprogram pada hook **`after_install` dan `after_migrate`** di `hooks.py` (**tanpa `fixtures` JSON**).

4. **[04 — Alur Kerja Sistem (End-to-End Workflows)](./04-alur-kerja-sistem.md)** — *spesifikasi normatif*
   - **Alur 1:** *Self-Registration* calon klien (`Pending Provisioning`, `enabled = 0`, tanpa email reset password) & aktivasi `User` di dalam *site* klien.
   - **Alur 2:** Pengelolaan Provider LLM, Model Routing per agen, Kuota Token `User`, dan Plugin/MCP oleh `AIOS Admin`.
   - **Alur 3:** Autentikasi Frappe, guard 3 lapis `aios_status == "Active"`, bootstrap `csrf_token`, dan penentuan portal berbasis Role.
   - **Alur 4:** Eksekusi tugas analitik, delegasi sub-agent (5 event SSE kanonik), kolaborasi lintas divisi (**Sales ↔ Finance**), dan pembuatan *Artifact/Canvas*.
   - **Alur 5:** Eskalasi aksi tulis ke **Pending Action Draft** (*Human-in-the-Loop Approval*) hingga eksekusi ke ERPNext.

5. **[05 — Roadmap Perbaikan Fondasi, Keamanan, & Higienitas Repo (Fase 1 — Dikerjakan Pertama)](./05-roadmap-perbaikan-fondasi.md)** — *roadmap & status*
   - Audit menyeluruh basis kode awal beserta verifikasi `file:line`.
   - Rencana eksekusi **Branch `#0` s/d `#10`** untuk memasang CI, menutup celah keamanan darurat (langsung berbasis `User`, tanpa `AIOS Tenant`), menghapus `AIOS Tenant` & `monitoring_service.py` legacy, mendaftarkan Custom Field & `Custom DocPerm` via `after_install`/`after_migrate`, membersihkan 39 MB artefak sampah & emoji UI, serta mengunci sandbox LLM & akuntansi token atomik (`usage.py`).

6. **[06 — Roadmap Pengembangan Business AI Harness (Fase 2 — Setelah Fondasi)](./06-roadmap-pengembangan-harness.md)** — *roadmap & status*
   - Rencana eksekusi bertahap (**Tahap `H1` s/d `H5`**, bebas duplikasi dengan Fase 1):
     - **H1:** Multi-Provider & Per-Agent Model Routing (`AIOS LLM Provider` & `AIOS Agent Model Route` + UI `AIOS Admin`).
     - **H2:** Plugin & MCP Manager (`AIOS Plugin`) + Katalog Lengkap 7 *Built-in Default Plugins*.
     - **H3:** UI Portal `AIOS Admin` untuk Manajemen User, Aktivasi Provisioning, & Analitik Kuota Token.
     - **H4:** *Deep Finance & Sales Autonomous Agents* + Delegasi Nyata (`MAX_DELEGATION_DEPTH = 2`) & *Live Agent Trace*.
     - **H5:** *Isolated Workspace* (Frappe Private `File`) & *5-Tier Artifact/Canvas Space*.

7. **[07 — Referensi Kompetitor AI ERP & Posisi AIOS](./07-referensi-kompetitor-ai-erp.md)** — *referensi pasar*
   - Peta 7 platform AI ERP: Microsoft Dynamics 365, SAP Joule, Odoo 19, Oracle Fusion, HashMicro, Ukirama, dan Keysoft (Mr. Key), beserta pola UI masing-masing.
   - Pemisahan **table-stakes** (tanya-jawab ERP, ringkasan, forecasting, human review, trace, admin) dari **celah pembeda** (tim agen nyata, approval tulis yang benar-benar posting, instance sendiri + model bebas, kontrol biaya per user/agen).
   - Pola UI/UX yang layak ditiru dan yang harus dihindari.
   - Implikasi untuk AIOS: fokus **depth Sales & Finance** pada satu alur *Order-to-Cash* utuh, dengan 9 divisi sebagai peta kemampuan — bukan sembilan divisi yang dangkal.
