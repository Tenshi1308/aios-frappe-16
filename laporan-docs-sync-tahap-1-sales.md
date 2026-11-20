# Laporan Sinkronisasi Dokumentasi Tahap 1 Sales

**Tanggal:** 20 November 2026  
**Cabang:** `feat/plugin-mcp-manager`  
**Cakupan Kode:** Commit `2749d89`, `c08dfaf`, `b4e0c7a`, dan `bfcf34b` (tanpa perubahan kode, tanpa migrate, tanpa push).

---

## 1. Dokumen yang Diubah & Ringkasan Perubahan

| Dokumen | Perubahan yang Dilakukan |
|---|---|
| `docs/README.md` | Memperbarui ringkasan `docs/02` & `docs/11` agar mencerminkan selesainya Tahap 1 Sales (`2749d89`–`bfcf34b`) dan penutupan celah notifikasi approval `Quotation`. |
| `docs/00-poc-target.md` | Menambahkan entri `2026-11-20` pada Decision Log untuk seluruh fitur Tahap 1 Sales (3 detektor, ringkasan 1 pesan, sesi baru, badge, panel 62px, notif `Quotation`, custom scheduler dicatat sebagai kebutuhan berikut); menutup baris celah notifikasi approval `Quotation` di §7. |
| `docs/02-arsitektur-harness-dan-plugin.md` | Menutup catatan celah `Quotation` pada §2.4 dan menambahkan §4 tentang arsitektur pemindaian proaktif `sales_proactive.py`, `aios_v1/api/sales_proactive.py`, `scheduler_events["daily"]`, 3 skill `sales_representative` yang diperkaya, guardrail tanpa auto-draft, serta `seed_sales_proactive_demo.py`. |
| `docs/03-skema-data-dan-isolasi-multitenant.md` | Menambahkan §4 tentang DocType `AIOS Proactive Insight Log` (kunci dedup per dokumen, status `PENDING`/`SENT_DESK`/`SENT_TELEGRAM`/`FAILED`, aturan `is_read` untuk badge 1, termigrasi di `aios-v16.localhost` & `aios-client1.localhost`) serta field ERPNext terverifikasi untuk 3 detektor. |
| `docs/04-alur-kerja-sistem.md` | Memperbarui Alur 5 (notifikasi approval `Quotation` ke tamu dengan `valid_till`) dan menambahkan Alur 8 tentang pemindaian harian/manual, dedup, ringkasan 1 pesan per pemindaian, sesi baru `Ringkasan Proaktif Sales <YYYY-MM-DD>`, heartbeat 60s / batas jauh 5 menit, polling 30s, badge 1 + refresh daftar riwayat otomatis, dan routing satu kanal Desk/Telegram. |
| `docs/05.1-roadmap-perbaikan-fondasi.md` | Menambahkan ringkasan selesainya Tahap 1 Sales dan menghapus celah notifikasi `Quotation` dari daftar celah terbuka. |
| `docs/06-roadmap-pengembangan-harness.md` | Menutup celah `Quotation` di H4 dan menambahkan status Tahap 1 Sales selesai penuh (`2749d89`–`bfcf34b`), custom scheduler dicatat sebagai kebutuhan berikut, serta Tahap 2 & 3 tetap belum diputuskan. |
| `docs/08-desain-ekasa-desk.md` | Memperbarui §2.3 & §2.4: badge pada tombol AI Agents di `Taskbar.vue`, polling 30 detik & heartbeat 60 detik, auto-refresh daftar riwayat tanpa reload, serta jarak bawah `.flyout` (`10px`), `.agent-panel` (`10px`), dan `.toasts` (`14px`) di dalam `.desk-area`; menutup celah `Quotation` di §12 butir 8. |
| `docs/09-catatan-masalah-terbuka.md` | Memperbarui HEAD ke `bfcf34b`, menutup entri celah notifikasi `Quotation`, panel `62px`, penumpukan pesan/sesi proaktif, serta badge/daftar riwayat basi di §E.2 dengan merujuk commit terkait dan hasil verifikasi live; mencatat pengiriman Telegram live dengan token aktif sebagai hal yang belum terverifikasi live. |
| `docs/10-peta-tampil-semua-modul.md` | Memperbarui baris matriks approval bahwa notifikasi approval tamu kini mencakup `Sales Order` dan `Quotation`. |
| `docs/11-tugas-tampil-semua-modul.md` | Menandai checklist celah notifikasi approval `Quotation` ke tamu sebagai selesai (`[x]`, `2749d89`). |

---

## 2. Hal yang Sengaja Tidak Diubah & Alasannya

- **`docs/01-profil-dan-visi-produk.md`:** Berisi visi produk tingkat tinggi dan organisasi 9 cabang; tidak memuat detail implementasi Tahap 1 Sales.
- **`docs/05.2-lampiran-roadmap-fondasi.md`:** Dokumen arsip historis temuan lama (`docs/README.md` menandainya bukan status terkini).
- **`docs/07-referensi-kompetitor-ai-erp.md`:** Referensi pasar eksternal yang tidak berubah karena implementasi Tahap 1.
- **`README.md` (root repo):** Sudah ringkas dan akurat menunjuk `docs/README.md` serta `docs/00-poc-target.md` tanpa klaim usang yang bertentangan dengan Tahap 1.

---

## 3. Cek Silang & Hal yang Belum Terverifikasi

- **Cek silang:** Seluruh referensi usang ke `draft_manager.py:1023` dan `calc(var(--taskbar-h) + 10px)` pada `docs/` telah diverifikasi bersih (`0` sisa). Nama file, fungsi, DocType, ambang detektor, dan perilaku sesuai dengan kode di commit `bfcf34b`.
- **Belum terverifikasi live:** Pengiriman pesan ringkasan proaktif dan notifikasi approval `Quotation` melalui bot Telegram nyata pada environment dengan token Telegram aktif (telah diverifikasi melalui mock `telegram_client.send_message` di unit test).
