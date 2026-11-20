# Laporan Perbaikan Tahap 1 Sales: Badge Ringkasan Proaktif & Daftar Riwayat

**Tanggal:** 20 November 2026  
**Cabang:** `feat/plugin-mcp-manager`  
**Dasar:** Perbaikan bug dari commit `b4e0c7a` di mana `pollProactiveInsights` menelan badge saat panel terbuka dan daftar riwayat `sales` tidak memuat ulang sesi baru tanpa reload tab.

---

## 1. Pemeriksaan Alur & Lokasi Kode yang Berubah

1. **Pemeriksaan Alur Sebelum Perbaikan (Tugas 1):**
   - `frontend/src/stores/chat.ts:206-219`: `pollProactiveInsights` memanggil `openConversation('sales', res.conversation_id)` dan `clearProactiveUnread()` di siklus polling yang sama saat `ui.agentOpen && branches.selectedKey === 'sales'`, sehingga badge diset `1` lalu langsung dihapus ke `0` dan tidak memuat ulang `conversations.sales`.
   - `frontend/src/components/agent/AgentPanel.vue:211-224`: watcher memanggil `openConversation` dan `clearProactiveUnread` secara bersamaan (tanpa menunggu isi percakapan selesai dimuat).
   - `frontend/src/components/shell/Taskbar.vue:99`: badge memakai `v-if="!ui.agentOpen && chat.proactiveUnreadCount > 0"` sehingga tersembunyi saat panel terbuka meskipun masih ada ringkasan proaktif yang belum dibuka.
2. **Perbaikan Polling (`frontend/src/stores/chat.ts:204-247`):**
   - `pollProactiveInsights` kini **hanya** memperbarui `proactiveUnreadCount` dan `proactiveConversationId`, serta memanggil `await this.loadConversations('sales')` bila `res.conversation_id` belum ada di `this.conversations.sales`. Tidak ada lagi pemanggilan `openConversation` maupun `clearProactiveUnread` dari polling; interval polling 30 detik tidak diubah.
   - `clearProactiveUnread` mencatat kegagalan lewat `console.error` dan `reportClientError` agar tidak ada error yang tertelan.
3. **Tandai-Dibaca Setelah Isi Sesi Dimuat (`frontend/src/stores/chat.ts:407-425`, `frontend/src/components/agent/AgentPanel.vue:211-218`):**
   - `openConversation(branch, conversationId)` memanggil `await this.clearProactiveUnread()` **hanya setelah** `fetchConversationMessages` selesai dan **hanya** bila `branch === 'sales' && conversationId === this.proactiveConversationId && this.proactiveUnreadCount > 0`. Membuka sesi lain tidak menghapus badge.
   - Watcher di `AgentPanel.vue` dipertahankan untuk membuka `chat.proactiveConversationId` saat panel dibuka di cabang `sales` ketika ada `proactiveUnreadCount > 0`, tanpa pemanggilan `clearProactiveUnread()` secara bersamaan.
4. **Visibilitas Badge Saat Panel Terbuka (`frontend/src/components/shell/Taskbar.vue:99`):**
   - Mengubah kondisi badge menjadi `v-if="chat.proactiveUnreadCount > 0"` agar badge bernilai `1` tetap terlihat baik saat panel tertutup maupun terbuka, sampai Ten benar-benar membuka sesi ringkasan terbaru.
5. **Tes TDD Frontend (`frontend/tests/proactiveBadge.test.ts`):**
   - Menambahkan 3 skenario pengujian: (1) polling saat panel terbuka di `sales` mempertahankan badge `1`, tidak memanggil `get_conversation`/`mark_sales_insights_read`, dan memuat ulang `list_conversations` sehingga sesi baru langsung masuk `conversations.sales`; (2) membuka sesi lama tidak menghapus badge; (3) membuka sesi ringkasan terbaru memanggil `mark_sales_insights_read` setelah `get_conversation` selesai dan mengubah badge menjadi `0`.

*(Backend dan DocType tidak berubah sama sekali.)*

---

## 2. Hasil Tes & Build

| Pemeriksaan | Hasil | Detail |
|---|---|---|
| `frontend/tests/proactiveBadge.test.ts` (`esbuild` + `node`) | **LOLOS (3/3 skenario)** | Polling, sesi lama tidak hapus badge, sesi terbaru hapus badge setelah muat isi |
| `frontend`: `npm run build` (`vue-tsc --noEmit && vite build`) | **LOLOS** | Exit code 0, 156 modul ditransformasi |
| `aios_v1.tests.test_sales_proactive` | **11/11 LOLOS** | Detektor, dedup, routing, ringkasan, sesi baru per pemindaian |
| `aios_v1.tests.test_draft_manager` | **12/12 LOLOS** | Approval, reject, expire, scheduler |
| `aios_v1.tests.test_guest_draft_customer_creation` | **22/22 LOLOS** | Draf tamu & notifikasi approval Quotation/SO |
| `aios_v1.tests.test_frontend_no_hardcode` | **25/25 LOLOS** | Validasi CSS, komponen, token, store |
| `aios_v1.tests.test_desktop_modules` | **35/35 LOLOS** | Modul desktop & query |

---

## 3. Hasil Verifikasi Manual di Site Dev (`aios-v16.localhost`)

- **Penerima aktif:** `client@demo.id` dengan heartbeat Desk aktif (`record_desk_heartbeat("client@demo.id")`).
- **Pemindaian #1 (`seed_demo_scenarios` + `trigger_sales_proactive_scan`):** `messages_sent: 1, sent: 5, skipped_dedup: 2, failed: 0`; baris `SENT_DESK` dengan `is_read = 0` bernilai **`1`**.
- **Setelah tandai-dibaca:** `is_read = 0` kembali **`0`**.
- **Pemindaian #2 (hari yang sama):** `messages_sent: 0, sent: 0, skipped_dedup: 7, failed: 0`; `is_read = 0` tetap **`0`** (tidak ada badge baru).
- **Cleanup:** `cleanup_demo_scenarios` menghapus `Delivery Note: 1`, `Sales Order: 2`, `Quotation: 2`, dan `AIOS Proactive Insight Log: 5`.

---

## 4. Hal yang Belum Terverifikasi

- Pengamatan visual langsung di browser live (site client) bahwa badge `1` tampak pada tombol AI Agents saat panel terbuka di cabang Sales, sesi baru muncul langsung di sidebar riwayat setelah siklus polling 30 detik tanpa reload, dan badge hilang setelah Ten mengklik sesi baru tersebut.
