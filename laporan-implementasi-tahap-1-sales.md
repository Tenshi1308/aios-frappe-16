# Laporan Implementasi Tahap 1 Sales

**Tanggal:** 20 November 2026  
**Cabang:** `feat/plugin-mcp-manager`  
**Status:** Implementasi dan verifikasi selesai; commit lokal dibuat tanpa push.

---

## 1. Ringkasan Perubahan per Tugas

1. **Notifikasi Approval Quotation ke Tamu (Tugas 1–2):**
   - Menambahkan `res["valid_till"]` di `_create_and_submit` (`aios_v1/lib/draft_manager.py:675-676`).
   - Menambahkan cabang `elif doc.type == "CREATE" and payload.get("doctype") == "Quotation":` di `approve_and_execute_draft` (`aios_v1/lib/draft_manager.py:1086-1112`) yang mengirim kabar tamu via `_send_proactive_guest_notification` berisi harga dasar, PPN 11%, total terformat, dan `valid_till`, tanpa nomor/label internal, tanpa emoji, dan tanpa wording tahan pengiriman / wajib Cash.
   - Menambahkan test TDD `test_proactive_notification_sent_on_quotation_approve_success` (`aios_v1/tests/test_guest_draft_customer_creation.py:1332-1393`).

2. **Tiga Detektor Proaktif Sales (Tugas 3–4):**
   - Membuat modul `aios_v1/lib/sales_proactive.py` berisi evaluator deterministik dan query live ERPNext:
     - `evaluate_quotation_rows` & `scan_quotation_followup`: `Quotation` `docstatus=1`, status `Open`/`Replied`/`Partially Ordered`, `valid_till` H-3 s/d H+0 serta kedaluwarsa hingga H+7, mengecualikan yang sudah tertaut ke `Sales Order` via `Sales Order Item.prevdoc_docname`.
     - `evaluate_so_rows` & `scan_so_fulfillment`: `Sales Order` `docstatus=1`, status `To Deliver and Bill`/`To Deliver`, `per_delivered < 100`, terlambat `>= 1` hari atau waspada H-2, memisahkan `partial` (`0 < per_delivered < 100`) dan `unshipped` (`per_delivered == 0`).
     - `evaluate_dn_rows` & `scan_delivered_unbilled`: `Delivery Note` `docstatus=1`, `is_return=0`, status `To Bill`/`Partially Billed`, `per_billed < 100`, umur `>= 3` hari dari `posting_date`.
     - Urutan hasil: `base_grand_total` terbesar dulu, tanggal paling awal sebagai penentu berikutnya.
   - Menambahkan 3 unit test deterministik di `aios_v1/tests/test_sales_proactive.py` (`TestSalesProactiveDetectors`).

3. **Log Dedup & Migrasi Dua Site (Tugas 5–6):**
   - Membuat DocType `AIOS Proactive Insight Log` (`aios_v1/aios_v1/doctype/aios_proactive_insight_log/`) dengan kunci `(rule_key, reference_doctype, reference_name, insight_date, recipient_user)` dan status `PENDING`, `SENT_DESK`, `SENT_TELEGRAM`, `FAILED`.
   - Menjalankan `bench migrate` di kedua site (`aios-v16.localhost` dan `aios-client1.localhost`).
   - Menambahkan 2 test dedup dan kegagalan tengah jalan di `aios_v1/tests/test_sales_proactive.py` (`TestSalesProactiveDedup`).

4. **Pemicu Daily & Manual (Tugas 7):**
   - Mendaftarkan `aios_v1.lib.sales_proactive.run_daily_sales_proactive_scan` pada `scheduler_events["daily"]` di `aios_v1/hooks.py:242`.
   - Membuat endpoint `@frappe.whitelist()` `aios_v1.api.sales_proactive.trigger_sales_proactive_scan` khusus admin/owner.

5. **Dorong ke Desk, Heartbeat, Fallback Telegram & Indikator Belum Dibaca (Tugas 8):**
   - Backend: `_insert_desk_insight_message` memasukkan pesan `role="manager"` ke `AIOS Conversation` cabang `sales`; `record_desk_heartbeat` & `is_user_away_from_desk` (batas 5 menit / 300 detik, tanpa LLM/token); `_deliver_finding_to_user` merutekan ke **satu kanal saja** (Desk jika aktif, Telegram via `get_channel_recipients` + `telegram_client.send_message` jika jauh & terlink; jika jauh tapi belum link Telegram -> simpan di Desk dengan `status="SENT_DESK"`, `is_read=0`, dan catat alasan di `reason` serta Error Log).
   - Frontend:
     - `frontend/src/api/chat.ts:511-543`: `sendDeskHeartbeat`, `fetchUnreadSalesInsights`, `markSalesInsightsRead`.
     - `frontend/src/stores/chat.ts:79-80, 204-238`: `proactiveUnreadCount`, `proactiveConversationId`, `pollProactiveInsights`, `clearProactiveUnread`.
     - `frontend/src/views/DesktopView.vue:31-51`: heartbeat tiap 60 detik (saat tab aktif) & polling insight tiap 30 detik.
     - `frontend/src/components/shell/Taskbar.vue:96-100`: badge belum dibaca pada tombol AI Agents saat `AgentPanel` tertutup.
     - `frontend/src/components/agent/AgentPanel.vue:211-223`: membuka percakapan `sales` dan menghapus badge saat panel dibuka di cabang `sales`.

6. **Scenario Seed Terpisah (Tugas 9):**
   - Membuat `aios_v1/setup_poc/seed_sales_proactive_demo.py` dengan `seed_demo_scenarios()` dan `cleanup_demo_scenarios()` berlabel `DEMO` dan tanggal relatif terhadap hari ini.

7. **Perkayaan 3 Skill `sales_representative` (Tugas 10):**
   - Memperkaya `quotation-and-pricing-management.md`, `order-fulfillment-and-crm.md`, dan `sales-order-and-invoicing.md` dengan instruksi pemantauan proaktif memakai `erpnext_doc_list`/`erpnext_doc_get` dan guardrail hanya memberi tahu tanpa membuat draf.

8. **Perbaikan Panel Melayang 62px (Tugas 11):**
   - `frontend/src/styles/base.css`: `.flyout` (`bottom: 10px`, `max-height: calc(100% - 20px)`), `.agent-panel` (`bottom: 10px`), dan `.toasts` (`bottom: 14px`); aturan `fullscreen` (`:1424`) dan `narrow` (`:2317`) tetap `bottom: 0`.

---

## 2. Hasil Tes & Build

| Pemeriksaan | Hasil | Detail |
|---|---|---|
| `aios_v1.tests.test_sales_proactive` | **7/7 LOLOS** | Detektor (3), Dedup & kegagalan tengah jalan (2), Scheduler & routing Desk/Telegram/unlinked/no-draft (2) |
| `aios_v1.tests.test_draft_manager` | **12/12 LOLOS** | Seluruh tes approval, reject, expire, scheduler |
| `aios_v1.tests.test_guest_draft_customer_creation` | **22/22 LOLOS** | Termasuk `test_proactive_notification_sent_on_quotation_approve_success` |
| `aios_v1.tests.test_frontend_no_hardcode` | **25/25 LOLOS** | Validasi CSS `base.css`, `AgentPanel.vue`, token, dan store |
| `aios_v1.tests.test_desktop_modules` | **35/35 LOLOS** | Modul desktop & query |
| `frontend`: `npm run build` (`vue-tsc --noEmit && vite build`) | **LOLOS** | Exit code 0, 156 modul ditransformasi |
| `bench --site aios-v16.localhost migrate` & `aios-client1.localhost migrate` | **LOLOS** | Kedua site termigrasi bersih |

---

## 3. Verifikasi Manual di Site Dev (`aios-v16.localhost`)

- **Scenario Seed & Pemindaian Manual:** `seed_demo_scenarios` membuat `SAL-QTN-2026-00001`, `SAL-QTN-2026-00002`, `SAL-ORD-2026-00008`, `SAL-ORD-2026-00009`, dan `MAT-DN-2026-00001`.
- Setelah `record_desk_heartbeat("Administrator")`, pemanggilan `trigger_sales_proactive_scan` mendeteksi **7 temuan** (5 dokumen `[DEMO]` dari ketiga detektor + 2 SO overdue existing), diurutkan dari nilai terbesar ke terkecil, dengan `sent: 7, skipped_dedup: 0, failed: 0`.
- `cleanup_demo_scenarios` membatalkan dan menghapus seluruh dokumen `DEMO` (`Delivery Note: 1, Sales Order: 2, Quotation: 2, AIOS Proactive Insight Log: 5`).
- Tidak ada `Pending Action Draft` yang terbuat selama pemindaian proaktif.

---

## 4. Hal yang Belum Terverifikasi (Menunggu Uji Visual/Live Browser & Telegram)

- Tampilan visual aktual panel `.agent-panel`, `.flyout`, dan `.toasts` pada jarak `10px`/`14px` di atas taskbar pada browser live.
- Kemunculan badge belum dibaca di `Taskbar.vue` dan pembersihan otomatisnya saat user membuka cabang Sales di UI browser live.
- Pengiriman pesan Telegram nyata ke bot/chat pelanggan/staf pada environment dengan token Telegram aktif (verifikasi di tes menggunakan mock `telegram_client.send_message`).
