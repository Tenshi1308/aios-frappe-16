# Dokumentasi Proyek AIOS V1 (Enterprise Business AI Harness)

Folder `docs/` ini memuat spesifikasi produk, arsitektur teknis, tata kelola *Site-Level Multi-Tenancy* (`1 Client = 1 Site`), alur kerja *end-to-end*, roadmap eksekusi berurutan, serta referensi pasar/kompetitor untuk **AIOS V1** di atas **Frappe 16 + ERPNext** dengan frontend **Vue 3 (Ekasa Desk)**.

> **Mulai dari [`00 — Target PoC`](./00-poc-target.md).** Dokumen itu yang menjawab “PoC selesai bila apa” dan “apa yang masuk/keluar PoC”. Dokumen lain adalah detail.

## Daftar Dokumen (Urutan Baca & Eksekusi)

> **Klasifikasi tiap dokumen** (pakai ini saat kode dan dokumen berbeda):
> - *Spesifikasi normatif* — apa yang harus benar. Bila kode ≠ dokumen, **yang diubah adalah kode**.
> - *Roadmap & status* — rencana eksekusi + progres. Bila kode belum sesuai, artinya belum dikerjakan (atau salah); **yang diperbarui statusnya**, bukan kode yang diundur.
> - *Referensi pasar* — konteks eksternal & positioning. Dipakai untuk keputusan produk, bukan aturan perilaku; bila berbeda dengan spesifikasi normatif, spesifikasi yang menang.
> - *Kontrak scope PoC* — definisi target, scope masuk/keluar, acceptance end-to-end, glossary, decision log. **Acuan pertama** sebelum dokumen lain.

0. **[00 — Target PoC AIOS V1](./00-poc-target.md)** — *kontrak scope PoC*
   - Definisi “PoC selesai bila apa”, scope wajib/pendukung/di luar PoC, acceptance end-to-end, urutan, glossary, decision log, dan known gaps.
   - **Baca ini dulu** sebelum `05.1` atau `06`.

1. **[01 — Profil dan Visi Produk](./01-profil-dan-visi-produk.md)** — *spesifikasi normatif*
   - Esensi AIOS sebagai *Business AI Harness* (bukan chatbot tanya-jawab biasa dan bukan coding harness).
   - Strategi *Depth over Breadth*: fokus kedalaman penuh pada divisi **Finance** dan **Sales** (*Order-to-Cash* & pelaporan akuntansi) sebagai fondasi pembuktian produk.
   - Struktur organisasi agen bisnis (Orchestrator / AI Manager & Sub-Agents spesialis) yang bekerja layaknya perusahaan mandiri.
   - Model SaaS **1 Client = 1 Site** dengan **Developer Control Plane** (site developer, role `AIOS Admin`) + **Ekasa Desk** (site klien, role `AIOS Client`, antarmuka desktop OS — `docs/08`).

2. **[02 — Arsitektur Harness, Model Routing, Plugin/MCP, & Kontrak Trace](./02-arsitektur-harness-dan-plugin.md)** — *spesifikasi normatif*
   - Konfigurasi Provider LLM & pemetaan model per Orchestrator/Sub-Agent berbasis UI & DocType (`AIOS LLM Provider` & `AIOS Agent Model Route` dengan `route_key` unik dan validasi ke `registry.py`, *Zero Hardcode*). **UI dan sumber kebenaran di Developer Control Plane; konfigurasi disalin ke tiap site klien.**
   - Arsitektur **Plugin & MCP Manager (`AIOS Plugin`)**: katalog 7 *Built-in Default Plugins* (didukung `Custom DocPerm` `read=1, report=1` untuk `AIOS Client`) dan dukungan External MCP Server.
   - **Batas Eksekusi Agen (§2.3):** agen tanpa shell, tanpa akses file server di luar `File` Frappe, tanpa jaringan bebas, identitas tak bisa dipalsukan; isolasi level OS sengaja ditunda.
   - **Kontrak trace & artefak (§3):** 5 event SSE; system prompt internal tidak pernah ditampilkan.
   - **Plugin ERPNext = wrapper tipis** di atas API ERPNext; skema tool diadaptasi dari `@casys/mcp-erpnext` (MIT). Server MCP eksternal dievaluasi dan **tidak dipakai** (§2.3).
   - Desain **Live Agent Trace** (5 event SSE kanonik termasuk `trace_subagent_prompt`, batas rekursi `MAX_DELEGATION_DEPTH = 2`, tanpa emoji dekoratif).
   - Arsitektur **Isolated Workspace (Frappe Private `File`)**; artefak tampil sebagai berkas/jendela desktop (`docs/08`).

3. **[03 — Skema Data, Identitas Frappe (`User`), & Arsitektur `1 Client = 1 Site`](./03-skema-data-dan-isolasi-multitenant.md)** — *spesifikasi normatif*
   - Konsep **1 Client = 1 Site (`dns_multitenant`)**: setiap klien memiliki *site* dan database MariaDB terpisah, sehingga DocType `AIOS Tenant` dihapus sepenuhnya.
   - Pemusatan atribut operasional pada DocType **`User`** bawaan Frappe (`aios_persona`, `aios_persona_context`, `aios_status`, `aios_company_name`, `aios_tokens_used`); kuota token = plafon site di **`AIOS Setting`** (`site_token_limit`), counter di-update atomik via SQL.
   - **Developer Control Plane (§1.4):** registry `AIOS Client Site` di site developer, role layanan `AIOS Control`, Control API per site klien, dan batas wewenang lintas site.
   - **Adapter DB eksternal dihapus (§2):** `AIOS DB Connection`, `AIOS Mapping`, `AIOS Mapping Entry`, `AIOS Schema Snapshot` tidak lagi bagian dari skema — PoC ERPNext-first.
   - Matriks otoritatif `User.aios_status` × `User.enabled` beserta pertahanan 3 lapis (`send_welcome_email = 0` + `no_welcome_mail = True`, sinkronisasi `enabled = 0`, serta hook `on_login` & `auth_hooks`).
   - Pendaftaran skema Custom Field, Role, Role Profile, dan `Custom DocPerm` secara terprogram pada hook **`after_install` dan `after_migrate`** di `hooks.py` (**tanpa `fixtures` JSON**).

4. **[04 — Alur Kerja Sistem (End-to-End Workflows)](./04-alur-kerja-sistem.md)** — *spesifikasi normatif*
   - **Alur 1:** *Self-Registration* calon klien (`Pending Provisioning`, `enabled = 0`, tanpa email reset password) & aktivasi `User` dari Developer Control Plane.
   - **Alur 2:** Pengelolaan Provider LLM, Model Routing per agen, Kuota Token `User`, dan Plugin/MCP oleh `AIOS Admin` — UI dan sumber kebenaran di control plane; konfigurasi disalin ke tiap site klien.
   - **Alur 3:** Autentikasi Frappe, guard 3 lapis `aios_status == "Active"`, bootstrap `csrf_token`, dan penentuan portal berbasis Role.
   - **Alur 4:** Eksekusi tugas analitik, delegasi sub-agent (5 event SSE kanonik), kolaborasi lintas divisi (**Sales ↔ Finance**), dan pembuatan artefak sebagai berkas/jendela desktop.
   - **Alur 5:** Eskalasi aksi tulis ke **Pending Action Draft** (*Human-in-the-Loop Approval*) hingga eksekusi ke ERPNext; jenis aksi `CREATE` / `UPDATE_DRAFT` / `CANCEL_AND_AMEND` dan batas **draft vs submitted**.
   - **Alur 6:** Provisioning klien lintas site (termasuk tombol **Buat Site**), undangan sekali pakai, dan monitoring dari Developer Control Plane.
   - **Alur 7:** Membuka modul dan membaca data ERPNext dari desktop (baca saja, `company` dipaksa server).

5. **[05.1 — Roadmap Perbaikan Fondasi, Keamanan, & Higienitas Repo (Fondasi — Dikerjakan Pertama)](./05.1-roadmap-perbaikan-fondasi.md)** — *roadmap & status*
   - **Peta Tahap 1–8** (urutan baca: semua item `#n` disusun per tahap) + checklist status (`✅` selesai / `🟡` sebagian / `⬜` belum / `⛔` terkunci) + dependency + acceptance per item.
   - Rencana eksekusi **Branch `#0` s/d `#13`** untuk memasang CI, menutup celah keamanan darurat (langsung berbasis `User`, tanpa `AIOS Tenant`), menghapus `AIOS Tenant` & `monitoring_service.py` legacy, mendaftarkan Custom Field & `Custom DocPerm` via `after_install`/`after_migrate`, membersihkan 39 MB artefak sampah & emoji UI, serta mengunci sandbox LLM & akuntansi token atomik (`usage.py`).
   - **`#11 — Developer Control Plane`:** dua fase — (1) dashboard lintas site (registry `AIOS Client Site`, role `AIOS Control`, Control API, undangan sekali pakai, monitoring agregat); (2) tombol **Buat Site** untuk provisioning otomatis. Kontrak: `docs/03` §1.4 & `docs/04` Alur 6.
   - **`#12 — Frontend Vue Desktop`:** Ekasa Desk dalam Vue; cutover selesai (`frontend/` sekarang Vue 3).
   - **`#13 — Hapus adapter DB eksternal`:** dikerjakan paling awal; memotong scope `#4a-1`, `#4a-2`, dan menggugurkan L5/L6 `#7a`.
   - **Lampiran arsip:** **[05.2 — Lampiran Roadmap Fondasi](./05.2-lampiran-roadmap-fondasi.md)** — *arsip/referensi*: temuan `file:line`, riwayat koreksi, baseline angka, detail rencana lama, strategi test, catatan lingkungan. **Bukan status terkini.**

6. **[06 — Roadmap Pengembangan Business AI Harness (Bagian dari PoC)](./06-roadmap-pengembangan-harness.md)** — *roadmap & status*
   - Detail tahap H1–H5. **H1 ditunda**; **H2–H5 wajib PoC**.
     - **H1 — ditunda:** Multi-Provider & Per-Agent Model Routing; PoC cukup satu model di `AIOS Setting`.
     - **H2 — wajib:** Plugin & MCP Manager (`AIOS Plugin`) + 7 *Built-in Default Plugins*.
     - **H3 — wajib, = `#11`:** Developer Control Plane; jangan dikerjakan dua kali.
     - **H4 — wajib, = pendalaman `#8`:** Deep Finance/Sales agents + delegasi nyata + Live Agent Trace.
     - **H5 — wajib:** Isolated Workspace/artefak; ini **sandbox file** agent.

7. **[07 — Referensi Kompetitor AI ERP & Posisi AIOS](./07-referensi-kompetitor-ai-erp.md)** — *referensi pasar*
   - Peta 7 platform AI ERP: Microsoft Dynamics 365, SAP Joule, Odoo 19, Oracle Fusion, HashMicro, Ukirama, dan Keysoft (Mr. Key), beserta pola UI masing-masing.
   - Pemisahan **table-stakes** (tanya-jawab ERP, ringkasan, forecasting, human review, trace, admin) dari **celah pembeda** (tim agen nyata, approval tulis yang benar-benar posting, instance sendiri + model bebas, kontrol biaya per user/agen).
   - Pola UI/UX yang layak ditiru dan yang harus dihindari.
   - Implikasi untuk AIOS: fokus **depth Sales & Finance** pada satu alur *Order-to-Cash* utuh, dengan 9 divisi sebagai peta kemampuan — bukan sembilan divisi yang dangkal.

8. **[08 — Desain Ekasa Desk (Antarmuka Desktop OS)](./08-desain-ekasa-desk.md)** — *spesifikasi normatif*
   - Konsep desktop OS: boot → sign-in → desktop, taskbar, flyout (`Ctrl+K`, `Ctrl+J`), panel agent.
   - **Live Agent Trace** di panel agent (langkah bisa dimekarkan) — instruksi tugas & argumen tool terlihat, *system prompt* internal tidak.
   - Artefak sebagai berkas/jendela desktop; modul sebagai jendela baca-saja.
   - **Zero hardcoded** untuk agent, modul, doctype, company, kuota; token CSS dua lapis (primitives → semantic); komponen dilarang menulis warna/font/shadow langsung.
   - Stack Vite + Vue 3 + TypeScript + Router + Pinia; struktur `frontend/`; kontrak API desktop; halaman yang diport.
