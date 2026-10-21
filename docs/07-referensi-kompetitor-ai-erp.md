# 07 — Referensi Kompetitor AI ERP & Posisi AIOS

**Klasifikasi:** *Referensi pasar* — konteks eksternal untuk keputusan produk dan positioning.
Bukan spesifikasi perilaku. Bila isi dokumen ini berbeda dengan `docs/01`–`docs/04`, **spesifikasi normatif yang menang**.
**Diperiksa:** 2026-10-21, dari halaman resmi/marketing masing-masing vendor.
**Dipakai untuk:** menentukan pembeda PoC, prioritas fitur, dan bahasa positioning — bukan untuk menyalin fitur.

---

## 1. Tujuan

Dokumen ini menjawab satu pertanyaan: **apa yang sudah menjadi standar di pasar AI ERP, dan di mana AIOS masih bisa berbeda?**

Kesimpulan singkat: copilot/agent yang bisa membaca ERP dan menjawab pertanyaan sudah menjadi **table-stakes**. Pembeda AIOS tidak boleh berhenti di "ada AI-nya", tetapi pada **cara agen bekerja, cara aksi disetujui, dan seberapa terbuka konfigurasinya**.

---

## 2. Peta Pemain

| Platform | Fokus | Kekuatan utama | Pola UI yang terlihat | Sumber |
|---|---|---|---|---|
| **Microsoft Dynamics 365** | ERP + CRM | Copilot di dalam aplikasi, *agent feed*, MCP server, form fill, pencarian & visualisasi data, ringkasan record, Sales Order Agent, Payables Agent | Copilot menempel di form/tabel; feed aktivitas agen; human review | [Microsoft Learn](https://learn.microsoft.com/en-us/dynamics365/copilot/ai-get-started) |
| **SAP Joule** | ERP lintas fungsi | Joule Work (tanya), Joule Assistants/Agents, Joule Studio, Knowledge Graph, agent gateway, orkestrasi | "Intent to action": satu kotak untuk meminta, agen mengeksekusi alur; governance | [SAP Business AI](https://www.sap.com/products/artificial-intelligence.html) |
| **Odoo 19** | ERP all-in-one | Ask AI via `Ctrl+K` / tombol AI, membuka view & report; agent standar **tidak bisa mengubah data**; AI agents, AI fields, server actions | AI global dan kontekstual, tetapi read-only untuk agent standar | [Odoo 19 AI docs](https://www.odoo.com/documentation/19.0/applications/productivity/ai.html) |
| **Oracle Fusion Cloud ERP** | ERP enterprise | *Fusion Agentic Applications*: tim agen spesialis, Agent Marketplace, Agent Studio, observability/evaluation; banyak agen finance (Cash, Expenses, Ledger, Payables, Payments, Planning, Reconciliation) | Workspace per peran (mis. Sales Order Command Center, Collections, Close) | [Oracle Fusion AI](https://www.oracle.com/applications/fusion-ai/) |
| **HashMicro** | ERP Asia-Pasifik | *AI-native ERP*, Hashy AI chat dengan chart, AI coworkers per divisi, Workflow Studio, HMX rekomendasi proaktif | Chat-first, kartu "apa yang perlu perhatian", workflow builder | [HashMicro](https://www.hashmicro.com/) |
| **Ukirama** | ERP Indonesia | AI praktis: OCR invoice, smart inventory forecasting; otomatisasi di modul | Fitur otomatis di dalam modul, belum terlihat sebagai agent otonom | [Ukirama](https://ukirama.com/en) |
| **Keysoft (Mr. Key)** | ERP Indonesia | Agent untuk laporan penjualan & proyeksi, laporan otomatis, analisis prediktif, WhatsApp automation | Chat + laporan otomatis, channel WhatsApp | [Keysoft Mr. Key](https://keysoft.co.id/mr-key) |

> Catatan: tabel ini merangkum **klaim halaman resmi**, bukan hasil uji produk. Kedalaman fitur sebenarnya bisa berbeda dari materi marketing.

---

## 3. Yang Sudah Menjadi Table-Stakes

Semua hal berikut sudah ada di beberapa pemain, jadi **bukan pembeda** bila AIOS hanya punya ini:

1. Tanya-jawab natural language atas data ERP, disertai grafik/tabel.
2. Ringkasan record, insight, deteksi anomali, dan forecasting.
3. Titik masuk "Ask AI" yang kontekstual di dalam layar kerja.
4. Human review untuk aksi tulis.
5. Feed/trace aktivitas agen.
6. Panel admin untuk model, kuota, dan penggunaan.

---

## 4. Celah yang Bisa Diambil AIOS

1. **Tim agen nyata, bukan satu copilot.**
   Manager benar-benar mendelegasikan ke sub-agent spesialis, dan Sales bisa berkonsultasi ke Finance sebelum membuat order. Trace-nya bisa dibaca sampai level prompt dan argumen tool — bukan hanya "AI menjawab".

2. **Tulis dengan approval yang benar-benar posting.**
   Draft transaksi → Approve → menjadi dokumen resmi di ERPNext. Odoo standar read-only; Microsoft/Oracle punya approval, tetapi jarang transparan sampai detail tool dan payload.

3. **Instance sendiri + model bisa diganti.**
   `1 Client = 1 Site`, provider/model bisa diganti per agen, plugin/MCP terbuka. Ini kombinasi yang sulit ditandingi pemain global untuk klien yang peduli data residency dan vendor lock-in.

   > **Batas yang perlu dipahami (bukan "user bebas pilih model"):** yang mengganti model adalah `AIOS Admin` (operator), bukan tiap user akhir. Pada tahap awal, pilihan model juga dibatasi kapasitas server — model besar belum tentu bisa dijalankan. Jadi klaim yang benar adalah **"tidak terkunci ke satu vendor"**, bukan **"bebas memilih model apa pun"**. Jangan menuliskan yang kedua di materi produk.

4. **Kontrol biaya per user dan per agen.**
   Kuota token, routing model per agen, dan log pemakaian. Enterprise butuh angka biaya yang bisa dipertanggungjawabkan.

---

## 5. Pola UI/UX yang Layak Ditiru

| Pola | Contoh | Dipakai untuk AIOS |
|---|---|---|
| **Global AI entry** | Odoo `Ctrl+K` / tombol AI | Satu titik masuk cepat di workspace, selain chat utama |
| **Ringkasan inline di record** | Microsoft record summary | Ringkas Sales Order / Invoice tanpa membuka dokumen penuh |
| **Agent feed / activity feed** | Microsoft agent feed | Daftar aktivitas agen yang bisa diawasi |
| **Intent to action** | SAP Joule | Satu kotak untuk "minta", lalu agen mengeksekusi alur |
| **Workspace per peran** | Oracle Command Centers | Tampilan Finance vs Sales berbeda sesuai pekerjaan |
| **Kartu proaktif** | HashMicro HMX | "Piutang jatuh tempo", "stok menipis", "approval menunggu" |
| **Chat + chart inline** | HashMicro Hashy | Jawaban analitik langsung disertai visualisasi |
| **Channel eksternal** | Keysoft WhatsApp | Kandidat channel setelah workspace web stabil |

---

## 6. Yang Harus Dihindari

1. **Chatbot yang hanya bisa menjawab.** Kalau tidak bisa bertindak (dengan approval), ia akan terlihat seperti copilot biasa.
2. **Memamerkan 9 divisi setara.** Lebih baik satu alur Sales↔Finance yang utuh daripada sembilan divisi yang dangkal.
3. **Bahasa marketing "AI ajaib".** Pembeli enterprise mencari kontrol, audit, isolasi data, dan biaya yang jelas.
4. **UI chat-only tanpa canvas/artefak.** Approval card, tabel, laporan, dan file adalah bagian dari nilai produk.

---

## 7. Implikasi untuk AIOS (Fokus Sales & Finance)

Sesuai `docs/01` (Depth over Breadth), bukti utama produk adalah **satu alur Order-to-Cash yang utuh**, bukan luasnya divisi.

Alur yang harus terlihat:

1. Sales Manager menerima permintaan pesanan besar.
2. Sales berkonsultasi ke Finance: cek plafon kredit dan piutang jatuh tempo.
3. Agen menyusun draf Sales Order dan menampilkannya sebagai approval card.
4. Pengguna menekan Approve.
5. Sales Order resmi terbentuk di ERPNext.
6. Seluruh langkah terlihat di live trace.

Sembilan divisi tetap ditampilkan sebagai **peta kemampuan**, tetapi kedalaman implementasi dan demo difokuskan pada Sales dan Finance.

**Positioning yang disarankan:** bukan "copilot yang menempel di ERP", tetapi **"tim agen yang bekerja di instance ERP Anda sendiri, dengan persetujuan manusia dan jejak audit."**

---

## 8. Sumber

- Microsoft Learn — *Agents, Copilot, and AI capabilities in Dynamics 365 apps*: <https://learn.microsoft.com/en-us/dynamics365/copilot/ai-get-started>
- SAP — *Joule Business AI*: <https://www.sap.com/products/artificial-intelligence.html>
- Odoo 19 — *AI documentation*: <https://www.odoo.com/documentation/19.0/applications/productivity/ai.html>
- Oracle — *AI for Fusion Applications*: <https://www.oracle.com/applications/fusion-ai/>
- HashMicro — *AI-Native ERP*: <https://www.hashmicro.com/>
- Ukirama — *ERP Software Indonesia*: <https://ukirama.com/en>
- Keysoft — *Mr. Key AI Agent*: <https://keysoft.co.id/mr-key>

---

## 9. Batasan

- Sumber utama adalah halaman resmi/marketing; **bukan** hasil uji coba produk.
- Tanggal rilis dan kronologi versi yang disebut dalam brief awal **belum diverifikasi** di dokumen ini.
- Perbandingan harga, paket, dan kedalaman implementasi lokal belum dilakukan.
- Klaim kompetitor bisa berubah; perbarui dokumen ini bila ada informasi baru yang material.
