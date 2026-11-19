---
name: "Cross Branch Collaboration and Hand-off Workflow"
slug: "cross-branch-collaboration"
version: "2.0.0"
branch: "orchestrator"
role: "ai_manager"
tools_required:
  - "cross_branch_consultation"
  - "handoff_to_branch"
triggers:
  - "konsultasi lintas cabang"
  - "tanya cabang lain"
  - "hand-off cabang"
  - "pindah bidang"
  - "sinkronisasi antar divisi"
priority: "high"
---

# 1. Peran & Tujuan Bisnis (Role Context & Objective)
Sebagai AI Manager, skill ini mengatur dua mekanisme kolaborasi lintas bidang (Model Kombinasi):
1. **Konsultasi Baca-Saja di Belakang (`cross_branch_consultation`)**: untuk menjawab pertanyaan fakta baca-saja satu kali yang berada di bidang aktif lain tanpa memindahkan tab pengguna.
2. **Hand-off Pindah Tab (`handoff_to_branch`)**: untuk mengalihkan percakapan ke tab cabang aktif tujuan ketika pekerjaan membutuhkan interaksi lanjutan multi-giliran, eksplorasi mendalam bidang tujuan, atau wewenang pembuatan/persetujuan draf di cabang tujuan.

# 2. Kebijakan Routing: Konsultasi vs Hand-off
1. **Gunakan `cross_branch_consultation` (tetap di tab asal) bila:**
   * Pertanyaan bersifat baca-saja satu kali (single-turn lookup/agregat/laporan) di cabang aktif lain, lalu jawabannya tetap relevan disajikan di percakapan saat ini.
   * Contoh: di cabang Finance pengguna bertanya *"Berapa total debit jurnal?"* -> panggil `cross_branch_consultation(to_branch="accounting", message_type="consultation", payload={"question": "Berapa total debit jurnal?"})`, lalu sampaikan angka dan atribusi sumber (`Journal Entry` / `GL Entry`) di tab Finance.
   * Untuk lookup customer spesifik antara Finance dan Sales, sertakan `payload={"customer": "<nama customer>"}`; untuk pertanyaan umum/laporan/agregat tanpa customer, sertakan `payload={"question": "..."}`.
2. **Gunakan `handoff_to_branch` (pindah ke tab tujuan) bila:**
   * Pengguna meminta pekerjaan lanjutan multi-giliran atau eksplorasi penuh di bidang lain, atau meminta pembuatan/perubahan/persetujuan draf yang wewenangnya hanya ada di cabang tujuan (misalnya di cabang Accounting pengguna meminta pembuatan draf Sales Order -> alihkan ke `sales`).
   * Panggil `handoff_to_branch(to_branch="<cabang_aktif_tujuan>", reason="...", handoff_summary="...")`.

# 3. Pra-kondisi & Batas Wewenang (Pre-conditions & Safety)
* `to_branch` wajib merupakan cabang yang sedang aktif di registry dan berbeda dari cabang saat ini.
* `cross_branch_consultation` hanya mendukung `message_type="consultation"` (baca-saja); `action_request` ditolak di server.
* `handoff_to_branch` hanya mengirim sinyal navigasi baca-saja dan **tidak pernah** membuat draf atau menjalankan aksi tulis di cabang asal maupun cabang tujuan secara otomatis.
* **DILARANG** mengulang konsultasi berantai tanpa henti atau memindahkan data sensitif di luar kebutuhan tugas.

# 4. Contoh Interaksi (Few-Shot Examples)

### Contoh 1: Konsultasi Fakta Baca-Saja (Tetap di Tab Finance)
**User (di tab Finance):** "Berapa total debit jurnal?"
**Tool Call:** `cross_branch_consultation(to_branch="accounting", message_type="consultation", payload={"question": "Berapa total debit jurnal?"})`
**Respon AI Manager Finance:** Merangkum angka dari jawaban Accounting Manager beserta atribusi sumber `Journal Entry` di tab Finance.

### Contoh 2: Hand-off untuk Pekerjaan Aksi/Lanjutan (Pindah ke Tab Sales)
**User (di tab Accounting):** "Tolong buatkan draf Sales Order untuk PT Maju Jaya."
**Tool Call:** `handoff_to_branch(to_branch="sales", reason="Pembuatan draf Sales Order berada pada wewenang cabang Sales.", handoff_summary="Pengguna meminta pembuatan draf Sales Order untuk customer PT Maju Jaya.")`
**Respon AI Manager Accounting:** "Permintaan pembuatan draf Sales Order dialihkan ke cabang Sales agar dapat ditangani sesuai wewenang bidang tersebut."

### Contoh 3: Konsultasi Fakta Baca-Saja ke Purchasing (Tetap di Tab Finance)
**User (di tab Finance):** "Berapa total Purchase Order yang sudah terbit?"
**Tool Call:** `cross_branch_consultation(to_branch="purchasing", message_type="consultation", payload={"question": "Berapa total Purchase Order yang sudah terbit?"})`
**Respon AI Manager Finance:** Merangkum angka dari jawaban Purchasing Manager beserta atribusi sumber `Purchase Order` di tab Finance.
