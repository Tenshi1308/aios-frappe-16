# Laporan Perubahan Tahap 1 Sales: Sesi Baru Tiap Pemindaian Ringkasan Proaktif

**Tanggal:** 20 November 2026  
**Cabang:** `feat/plugin-mcp-manager`  
**Dasar:** Perubahan dari pengiriman ke satu utas berulang (`c08dfaf`) menjadi **satu sesi `AIOS Conversation` baru per pemindaian** saat pengiriman ke Desk.

---

## 1. Ringkasan Perubahan & Lokasi Kode

1. **Pemeriksaan Jalur Tandai-Dibaca (Tugas 1):**
   - `aios_v1/api/sales_proactive.py:52-88`: `get_unread_sales_insights` menghitung `AIOS Proactive Insight Log` dengan `status="SENT_DESK"` dan `is_read=0` untuk `recipient_user`, serta mengambil `AIOS Conversation` terbaru di `branch="sales"` (`order_by="modified desc"`). `mark_sales_insights_read` menandai seluruh log belum-dibaca milik user menjadi `is_read=1` secara global di cabang `sales`.
   - `frontend/src/components/agent/AgentPanel.vue:211-223`: saat panel dibuka di cabang `sales`, memanggil `chat.openConversation('sales', chat.proactiveConversationId)` dan `chat.clearProactiveUnread()`.
   - **Kesimpulan:** Jalur tandai-dibaca sudah global dan otomatis menunjuk sesi terbaru; tidak ada perubahan frontend maupun `api/sales_proactive.py`.
2. **Pembuatan Sesi Baru per Pemindaian (`aios_v1/lib/sales_proactive.py:370-391`):**
   - Mengganti `_get_or_create_sales_conversation` dengan `_create_sales_proactive_conversation(user, insight_date)` yang selalu membuat dokumen `AIOS Conversation` baru (`branch="sales"`, `title=f"Ringkasan Proaktif Sales {target_date}"`).
   - `_insert_desk_insight_message` dan `_deliver_summary_to_user` (`:459-490`) meneruskan `insight_date` hanya pada jalur Desk (`SENT_DESK`); jalur Telegram (`SENT_TELEGRAM`) tetap tanpa membuat `AIOS Conversation`.
   - `dispatch_proactive_findings` (`:559-585`) hanya memanggil `_deliver_summary_to_user` bila `new_findings` tidak kosong (sehingga tidak pernah membuat sesi kosong), dan menandai `is_read=0` hanya pada 1 baris perwakilan per batch `SENT_DESK` sehingga badge tetap `1` per pemindaian.
3. **Tes TDD (`aios_v1/tests/test_sales_proactive.py:570-667`):**
   - Menambahkan `TestSalesProactiveSessionPerScan`:
     - `test_two_scans_different_dates_create_two_dated_conversations_and_repeat_creates_none`: memverifikasi 2 pemindaian di tanggal berbeda menghasilkan 2 `AIOS Conversation` berbeda berjudul `Ringkasan Proaktif Sales 2026-11-20` dan `Ringkasan Proaktif Sales 2026-11-21` (masing-masing 1 pesan), pemindaian ulang di tanggal sama tanpa temuan baru tidak membuat sesi/pesan, badge naik 1 per pemindaian dan hilang setelah `mark_sales_insights_read`.
     - `test_telegram_delivery_does_not_create_conversation`: memverifikasi pengiriman Telegram tidak membuat `AIOS Conversation`.
   - Menyesuaikan signature mock `**kwargs` pada 3 test di `TestSalesProactiveDedup` & `TestSalesProactiveSummary` agar menerima `insight_date`.

*(Tidak ada perubahan DocType sehingga tidak dilakukan `bench migrate`; tidak ada perubahan file frontend karena jalur tandai-dibaca dan polling sudah menunjuk sesi terbaru secara otomatis.)*

---

## 2. Hasil Tes per Modul

| Modul Tes | Hasil | Detail |
|---|---|---|
| `aios_v1.tests.test_sales_proactive` | **11/11 LOLOS** | Detektor (3), Dedup (2), Routing & scheduler (2), Ringkasan (2), Sesi baru per pemindaian (2) |
| `aios_v1.tests.test_draft_manager` | **12/12 LOLOS** | Approval, reject, expire, scheduler |
| `aios_v1.tests.test_guest_draft_customer_creation` | **22/22 LOLOS** | Draf tamu & notifikasi approval Quotation/SO |
| `aios_v1.tests.test_frontend_no_hardcode` | **25/25 LOLOS** | Validasi CSS, komponen, token, store |
| `aios_v1.tests.test_desktop_modules` | **35/35 LOLOS** | Modul desktop & query |

---

## 3. Hasil Verifikasi Manual di Site Dev (`aios-v16.localhost`)

- **Penerima aktif:** `client@demo.id` (`get_sales_proactive_recipients()`).
- **Pemindaian #1 (dengan `seed_demo_scenarios` & heartbeat `client@demo.id`):**
  - `messages_sent: 1`, `sent: 5`, `skipped_dedup: 2`, `failed: 0`.
  - Terbentuk sesi baru `AIOS Conversation` **`26989`** berjudul **`Ringkasan Proaktif Sales 2026-11-20`** berisi 1 pesan ringkasan (3 detektor + 5 temuan `[DEMO]` teratas).
  - Jumlah baris `SENT_DESK` belum dibaca (`is_read=0`) bertambah tepat **1** saat panel tertutup (dan pembersihan ke `0` oleh `mark_sales_insights_read` terverifikasi di `TestSalesProactiveSessionPerScan`).
- **Pemindaian #2 (hari yang sama):**
  - `messages_sent: 0`, `sent: 0`, `skipped_dedup: 7`, `failed: 0` — tidak ada sesi baru atau pesan baru yang dibuat.
- **Cleanup:** `cleanup_demo_scenarios` menghapus `Delivery Note: 1`, `Sales Order: 2`, `Quotation: 2`, dan `AIOS Proactive Insight Log: 5`.

---

## 4. Hal yang Belum Terverifikasi

- Pengamatan visual langsung di UI browser Desk (site client) untuk memastikan sesi baru `Ringkasan Proaktif Sales <tanggal>` tampil terpisah di daftar riwayat dan badge `1` hilang saat sesi dibuka di browser.
- Pengiriman pesan Telegram nyata pada environment dengan token Telegram aktif (diverifikasi melalui mock `telegram_client.send_message` di test).
