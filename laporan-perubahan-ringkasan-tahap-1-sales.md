# Laporan Perubahan Tahap 1 Sales: Ringkasan Insight Proaktif (Satu Pesan per Pemindaian)

**Tanggal:** 20 November 2026  
**Cabang:** `feat/plugin-mcp-manager`  
**Dasar:** Perubahan dari perilaku per-temuan (`2749d89`) menjadi **satu pesan ringkasan per pemindaian per penerima**.

---

## 1. Ringkasan Perubahan & Lokasi Kode

1. **Pembangun Ringkasan Deterministik Tanpa LLM (`aios_v1/lib/sales_proactive.py:404-462`):**
   - Menambahkan `_DETECTOR_LABELS`, `_format_finding_timing()`, dan `build_proactive_summary(findings, insight_date)`.
   - Menghasilkan satu teks ringkasan berisi judul + tanggal pemindaian, baris jumlah dokumen & total `base_grand_total` per detektor yang memiliki temuan, dan 5 temuan teratas berdasarkan nilai terbesar (nomor dokumen, customer, nilai terformat, umur/keterlambatan, serta prefiks `[DEMO]` bila data demo).
2. **Pengiriman Ringkasan & Dedup per Dokumen (`aios_v1/lib/sales_proactive.py:465-597`):**
   - Mengganti pengiriman per temuan dengan `_deliver_summary_to_user(user, summary_text)`.
   - `dispatch_proactive_findings` menyaring dedup per dokumen di `AIOS Proactive Insight Log`, menggabungkan seluruh temuan baru per penerima menjadi 1 ringkasan, mengirim 1 kali via rute Desk/Telegram yang sama, mencatat log dedup tetap per dokumen, dan menandai `is_read = 0` hanya pada 1 baris perwakilan per batch `SENT_DESK` sehingga **badge belum dibaca bernilai 1 per pemindaian** (bukan sebanyak temuan).
   - Bila `findings` kosong atau seluruh temuan sudah ter-dedup (`new_findings == []`), **0 pesan** dikirim.
3. **Pembaruan & Penambahan Test TDD (`aios_v1/tests/test_sales_proactive.py:246-554`):**
   - Menambahkan `TestSalesProactiveSummary` (`test_summary_builder_includes_per_detector_totals_top_5_and_demo_label`, `test_dispatch_10_findings_sends_1_summary_and_logs_10_dedup_rows`).
   - Memperbarui `test_duplicate_scan_sends_and_logs_only_once`, `test_mid_scan_failure_does_not_resend_already_logged_documents`, dan `test_routing_desk_active_vs_away_telegram_vs_unlinked_and_no_drafts` agar sesuai kontrak satu pesan ringkasan per pemindaian.

*(Tidak ada perubahan DocType sehingga tidak diperlukan `bench migrate`, dan tidak ada perubahan file di luar scope.)*

---

## 2. Hasil Tes

| Modul Tes | Hasil | Detail |
|---|---|---|
| `aios_v1.tests.test_sales_proactive` | **9/9 LOLOS** | Detektor (3), Dedup & gagal tengah jalan (2), Scheduler & routing (2), Ringkasan 10 temuan -> 1 pesan & 0 temuan -> 0 pesan (2) |
| `aios_v1.tests.test_draft_manager` | **12/12 LOLOS** | Seluruh tes approval, reject, expire, scheduler |
| `aios_v1.tests.test_guest_draft_customer_creation` | **22/22 LOLOS** | Seluruh tes draf tamu & notifikasi approval Quotation/SO |
| `aios_v1.tests.test_frontend_no_hardcode` | **25/25 LOLOS** | Validasi CSS, komponen, token, store |
| `aios_v1.tests.test_desktop_modules` | **35/35 LOLOS** | Modul desktop & query |

---

## 3. Hasil Verifikasi Manual di Site Dev (`aios-v16.localhost`)

- **Scenario Seed (`seed_demo_scenarios`):** Membuat `SAL-QTN-2026-00001`, `SAL-QTN-2026-00002`, `SAL-ORD-2026-00008`, `SAL-ORD-2026-00009`, dan `MAT-DN-2026-00001`.
- **Pemindaian Manual (`trigger_sales_proactive_scan` setelah `record_desk_heartbeat("Administrator")`):**
  - Menghasilkan `findings_count: 7` (5 dokumen `DEMO` baru + 2 SO existing yang sudah ter-dedup dari uji sebelumnya).
  - Mengirim tepat **1 pesan ringkasan** (`messages_sent: 1, sent: 5, skipped_dedup: 2, failed: 0`) ke `AIOS Message` (ID `13684`) berisi ringkasan 3 detektor + 5 temuan teratas berlabel `[DEMO]` berurutan dari `Rp 8.000.000` hingga `Rp 3.000.000`.
  - Catatan `get_unread_sales_insights`: pada uji `bench execute`, penerima aktif dari `get_channel_recipients()` adalah user klien (bukan `Administrator`), sehingga `unread_count` untuk session `Administrator` bernilai `0` sementara `unread_count == 1` terverifikasi di `TestSalesProactiveSummary.test_dispatch_10_findings_sends_1_summary_and_logs_10_dedup_rows` untuk user penerima aktif.
- **Cleanup (`cleanup_demo_scenarios`):** Menghapus bersih `Delivery Note: 1`, `Sales Order: 2`, `Quotation: 2`, dan `AIOS Proactive Insight Log: 5`.

---

## 4. Hal yang Belum Terverifikasi

- Pengamatan visual langsung di UI browser Desk (site client) bahwa pemindaian berikutnya menampilkan 1 pesan ringkasan dan badge bernilai `1` (86 pesan riwayat lama di site client sengaja tidak dihapus).
- Pengiriman pesan ringkasan via bot Telegram live pada environment dengan token Telegram aktif (terverifikasi lewat mock `telegram_client.send_message` di unit test).
