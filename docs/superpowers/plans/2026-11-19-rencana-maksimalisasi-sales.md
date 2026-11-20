# Rencana — Maksimalisasi Sales Agent (Entire Plan)

> **Untuk pelaksana (builder):** Rencana ini ditulis untuk builder yang mengerjakan pekerjaan ini di repo ini. Pelaksana membaca rencana ini dan mengerjakan tugasnya sesuai urutan. Reviewer memeriksa hasil kerja pelaksana terhadap kode, tes, dan build — reviewer tidak percaya laporan pelaksana mentah-mentah. Pengambil keputusan adalah Ten: scope, bentuk akhir, perubahan tes yang mengunci perilaku lama, dan perintah lanjut atau berhenti semuanya diputuskan Ten. Pelaksana tidak memutuskan desain atau scope sendiri.

**Goal:** Agent Sales di AIOS menjadi proaktif — memantau data ERP, memberi tahu karyawan sebelum ditanya, dan tetap hanya membuat draf bila disuruh — dimulai dari frontend chat yang longgar dan layak, dilanjutkan tiga detektor Tahap 1, lalu fitur-fitur kandidat berikutnya yang diputuskan Ten satu per satu.

**Architecture:** Urutan kerja: (A) frontend chat dilonggarkan dulu supaya layak menampung fitur baru; (B) tiga detektor proaktif Tahap 1 dibangun di atas pemicu yang mengikuti pola resmi Frappe; (C) fitur kandidat Tahap 2, Tahap 3, dan ronde 2 dibangun hanya setelah Ten memilihnya. Tiap bagian terdiri dari investigasi (baca kode saja) lalu implementasi — dua pekerjaan terpisah dengan dua perintah terpisah; implementasi hanya jalan setelah laporan investigasi direview dan Ten bilang lanjut.

**Tech Stack:** Frappe v16 + ERPNext, Vue (frontend Finto Desk), bench mybench-v16, branch feat/plugin-mcp-manager. Model builder untuk investigasi frontend: Gemini 4 Hydrogen Medium (perintah Ten). Model untuk pekerjaan berikutnya diputuskan saat drafnya dibaca Ten.

**Spec:** Spesifikasi adalah bagian-bagian di bawah ini. Laporan investigasi frontend (laporan-investigasi-frontend-chat-agent.md, di root repo) adalah acuan teknis Bagian A. Acuan menu tiga titik: pola menu konteks muse.ai — Pin, Rename, Archive, Delete — dari screenshot yang Ten lampirkan 19 Nov 20:13 WIB. Kondisi awal Sales agent yang sudah diverifikasi dari kode: cabang `sales` "Sales and Distribution" dengan 4 worker (Customer Service, Marketing Specialist, Sales Data Analyst, Sales Representative); 7 modul (sales_invoice, sales_order, quotation, delivery_note, customer, item, item_price); 10 skill Sales dari total 88 skill; tamu hanya bisa baca Item dan Item Price plus draf CREATE Sales Order dan Quotation dengan party kosong; agent hari ini hanya bekerja bila ditanya.

## Bagian A — Frontend chat dilonggarkan (SELESAI 19 Nov 2026 21:13 WIB)

Delapan kekurangan di bawah adalah spesifikasinya, lengkap dengan penjelasan tiap item. Investigasi sudah selesai (laporan di root repo), kelima keputusan sudah dikunci Ten, dan **Bagian A selesai**: commit d2495a8 pada 19 Nov 2026 21:13 WIB, diterima Ten 20 Nov 2026, docs sync 98c63d9. Rincian verifikasi ada di Tahap A2.

1. **Tombol stop AI.** Saat agent sedang menjawab (streaming), tombol kirim berubah menjadi tombol stop di baris input. Klik stop membatalkan jawaban yang sedang berjalan: batalkan di frontend (AbortController) dan tutup stream di backend. Teks jawaban yang sudah terkirim sebagian tetap tampil apa adanya. Setelah berhenti, tombol kirim aktif lagi. Hari ini: tidak ada tombol stop sama sekali, dan tidak ada AbortController di seluruh frontend/src — jadi jalur batal ini harus dibuat baru ujung ke ujung. Pola yang direkomendasikan (mengikuti harness pada umumnya — ChatGPT, coding agent terminal): stop harus sampai ke server, bukan cuma menutup stream di client; tool call yang sedang berjalan diselesaikan satu itu saja lalu hasilnya dibuang, tidak ada ronde LLM atau tool call baru; jawaban parsial tetap tampil dengan tanda berhenti dan TIDAK disimpan sebagai pesan selesai; token yang sudah keluar tetap terhitung. Pola ini sudah dikonfirmasi Ten lewat keputusan yang dikunci di bawah. Keputusan yang sudah dikunci (Ten, 19 Nov 20:55): pakai pola yang sudah dipakai orang-orang seperti ChatGPT dan muse.ai — client batalkan stream, server hentikan loop, tool call yang sedang berjalan diselesaikan satu itu saja lalu hasilnya dibuang, jawaban parsial tetap tampil dengan tanda berhenti dan tidak disimpan sebagai pesan selesai; DAN model harus tahu apa yang terjadi — giliran yang dihentikan tercatat lengkap di konteks percakapan agent (jawaban parsial bertanda berhenti), supaya agent punya konteks yang lengkap tentang apa yang terjadi dan tidak menganggap jawaban itu selesai — manusia dan agent tetap sinkron tentang apa yang terjadi.
2. **Voice speech-to-text.** Tombol mic di baris input, di samping tombol lampirkan berkas. Tekan mic, bicara, hasil ucapan masuk ke kolom draft sebagai teks yang masih bisa diedit sebelum dikirim. Yang dibangun malam ini adalah dikte — bicara jadi teks di kolom, agent tetap menjawab tulisan — mengikuti cara kerja tombol mic di ChatGPT dan Antigravity. Percakapan suara dua arah (voice mode: agent menjawab dengan suara, seperti tombol biru bergelombang di ChatGPT dan "Start Voice mode" di Antigravity yang memakai Gemini Live) adalah fitur besar tersendiri dan TIDAK masuk malam ini. Rekomendasi: dikte memakai Web Speech API (SpeechRecognition) bila tersedia di browser; bila browser tidak mendukung, tombol tidak tampil atau tampil nonaktif dengan penjelasan. Rekomendasi ini sudah dikonfirmasi Ten — lihat keputusan voice = dikte di status lima keputusan Bagian A.
3. **Tombol buka list conversation yang jelas.** Tombol header yang sekarang memakai ikon panah melingkar (mirip undo) diganti dengan ikon dan label yang jelas sebagai daftar percakapan — pengguna harus langsung paham tombol itu membuka list conversation, bukan mengulang atau membatalkan. Label aksesibilitas tetap "Riwayat percakapan". Pada layout hybrid yang dikunci (lihat status keputusan), tombol ini menjadi pengalih buka/tutup sidebar — sidebar itu sendiri juga punya tombol tutupnya sendiri.
4. **Arsip, rename, dan pin lewat menu tiga titik.** Tiap item di list conversation mendapat tombol tiga titik (⋯) yang membuka menu berisi Pin, Rename, Archive, Delete — sama seperti list conversation muse.ai. Pin menaruh conversation di atas; Rename mengubah judulnya; Archive menyembunyikan dari list aktif (tetap bisa dibuka dari arsip); Delete menghapus. Bila field atau endpoint backend untuk pin, rename, dan arsip belum ada, investigasi harus mencatatnya dan implementasi membuatnya. Keputusan yang sudah dikunci (Ten, 19 Nov 20:46): Delete = hapus permanen setelah konfirmasi (mengikuti pola muse.ai); Archive = sembunyi dari list aktif dan bisa dilihat lagi di tab Archived khusus; header list conversation mendapat tombol ⋯ berisi Archived dan Sort (naik dan turun); isi ⋯ per conversation untuk sekarang hanya Pin, Rename, Archive, Delete.
5. **Lebar chat bisa diatur.** Tepi panel bisa di-drag untuk mengubah lebar. Lebar yang dipilih tersimpan (per pengguna) supaya tidak kembali ke lebar awal setiap kali panel dibuka. Keputusan yang sudah dikunci (Ten, 19 Nov 20:53): lebar default panel TETAP sama seperti sekarang (410 px); panel bisa di-drag lebih kecil sampai batas minimum tertentu dan dilebarkan sampai batas maksimum tertentu — angka batas min/maks diusulkan di draf implementasi dan Ten putuskan saat membacanya (sudah diputuskan; hasilnya di Tahap A2 Step 6).
6. **Fullscreen.** Tombol expand di header membuka chat dalam mode layar penuh; tombol yang sama mengembalikan ke ukuran panel semula. Dalam mode layar penuh, semua fungsi chat tetap jalan (kirim, stop, voice, history, draft). Keputusan yang sudah dikunci (Ten, 19 Nov 20:46): tombol fullscreen menempati posisi tombol setting (gear) di header — gear hilang, fullscreen yang menggantikannya. Berlaku di semua opsi layout.
7. **Hapus tombol setting ganda.** Tombol gear "Pengaturan percakapan" di header chat dihapus, karena pengaturan percakapan sudah ada di Start. Menghapus tombolnya saja — fungsi pengaturan percakapannya sendiri tetap ada dan tetap bisa dibuka dari Start.
8. **List history draft.** Jendela draft tidak hanya menampilkan draft yang belum disetujui. Tambahkan tab atau daftar riwayat berisi draft yang sudah disetujui — lengkap dengan status, tanggal, dan tautan ke dokumen yang dibuat dari draft itu. Hari ini: tombol ikon draft di header hanya muncul bila ada draft tertunda, dan jendela draft hanya punya filter tertunda dan kedaluwarsa. Keputusan yang sudah dikunci (Ten, 19 Nov 20:46): status disetujui, dieksekusi, dan ditolak digabung dalam satu tab Riwayat, dengan filter di dalamnya untuk memisahkan Disetujui, Dieksekusi, dan Ditolak.

Lima keputusan Bagian A — status (19 Nov 20:57): SEMUA SUDAH DIKUNCI — **layout hybrid** (Opsi 2 dual-pane yang dimodifikasi: saat panel lebar/fullscreen, riwayat jadi sidebar kiri permanen di dalam panel; sidebar punya tombol tutup dan bisa dibuka lagi lewat tombol header; tab agent pindah ke dalam sidebar yang sama; lebar default panel tetap 410 px dan bisa di-drag lebih kecil sampai batas min dan lebih lebar sampai batas maks — angka batas diusulkan builder di draf implementasi dan dicatat di laporan); tombol fullscreen menggantikan gear; **pola Stop mengikuti ChatGPT/muse.ai** (client batalkan stream, server hentikan loop, tool call yang jalan diselesaikan satu itu lalu dibuang, parsial tetap tampil bertanda berhenti dan tidak disimpan sebagai pesan selesai) + **giliran yang dihentikan tercatat lengkap di konteks agent** supaya manusia dan agent tetap sinkron; **voice = dikte cara ChatGPT** (bicara jadi teks di kolom, bisa diedit, baru dikirim; Web Speech API; voice mode live TIDAK masuk malam ini); Delete = hapus permanen setelah konfirmasi terlebih dahulu, supaya tidak terjadi salah pencet (Ten, 19 Nov 20:58); tab Archived khusus + ⋯ header list (Archived, Sort naik/turun); ⋯ per conversation berisi Pin, Rename, Archive, Delete; tab Riwayat draft + filter Disetujui/Dieksekusi/Ditolak.

## Bagian B — Tahap 1 Sales: tiga detektor proaktif + fondasi (SELESAI 20 Nov 2026 10:35 WIB)

Tiga detektor di bawah adalah nilai utamanya. Semuanya hanya memberi tahu — draf tetap dibuat hanya bila karyawan meminta.

**Status: SELESAI 20 Nov 2026 10:35 WIB.** Commit 2749d89 + c08dfaf + b4e0c7a + bfcf34b, docs sync 67f5f20. Verifikasi: 105 tes hijau, build lolos, terverifikasi live di Desk client, data DEMO dibersihkan. Catatan jujur: pengiriman **Telegram nyata belum terverifikasi** — yang terbukti live baru jalur chat Desk.

1. **Quotation Follow-up Intelligence.** Memindai Quotation yang masa berlakunya hampir habis (misalnya 3 hari lagi) atau yang sudah lama tidak ada tindak lanjut. Memberi tahu karyawan lewat chat Desk dengan nama dokumen, nama customer, nilai, dan tanggal berlakunya. Karyawan yang memutuskan menindaklanjuti atau tidak.
2. **Sales Order Fulfillment Monitor.** Memindai Sales Order yang melewati tanggal kirim atau baru sebagian terkirim. Memberi tahu dengan nomor SO, nama customer, dan item yang tertunda.
3. **Delivered-but-Unbilled Detector.** Memindai Delivery Note yang barangnya sudah terkirim tetapi belum ada Sales Invoice-nya. Memberi tahu dengan nomor DN, nama customer, dan nilai yang belum ditagih.
4. **Perbaikan kecil yang ikut serta: notifikasi approval Quotation ke tamu.** Hari ini pemberitahuan "Pesanan Anda telah disetujui" ke tamu hanya dikirim untuk Sales Order; approval Quotation tidak mengirim apa-apa. Perbaikan ini mengirim pemberitahuan yang sama saat Quotation disetujui.

Fondasi yang dibutuhkan Bagian B (dibangun bersama tiga detektor):
- **Pemicu proaktif mengikuti pola resmi Frappe (Notification).** Pola yang sudah di-reverse-engineer dari kode Frappe: aturan disimpan sebagai data (DocType, field tanggal acuan, offset hari, kondisi, penerima); scheduler harian memindai dokumen yang tanggalnya cocok hari ini; tiap dokumen dievaluasi kondisinya; lalu dikirim; ada cara uji tanpa menunggu sehari (tombol "cek hari ini"). Yang dipakai ulang: scheduler, aturan-sebagai-data, aritmetika tanggal, gating kondisi, cara uji. Yang dibangun baru: pengiriman ke agent (bukan email), pemindaian antar-dokumen (misalnya DN tanpa invoice), dan dedup — catatan insight yang sudah terkirim per dokumen dan aturan — supaya agent tidak mengirim insight yang sama setiap pagi.
- **Tool dorong ke chat Desk.** Insight proaktif masuk ke percakapan cabang Sales di chat Desk (bukan hanya bell). Panel chat hari ini belum punya listener pesan proaktif — bagian ini harus dibuat. Telegram dipakai hanya bila pengguna jauh dari Desk (jalur kirim Telegram sudah ada).
- **Scenario seed + label DEMO.** Data seed hari ini memakai tanggal relatif tetapi tidak punya skenario pemicu yang disengaja. Dibutuhkan seed skenario terpisah: tanggal relatif + pemicu yang disengaja (misalnya 5 Quotation kedaluwarsa besok, 3 SO lewat tanggal kirim, 2 DN tanpa invoice, 1 customer terakhir beli 75 hari lalu), bisa dibersihkan kembali, dan tiap pesan proaktif dari data demo wajib berlabel DEMO.
- **Unit test aturan deteksi + perkaya skill 4 worker.** Aturan deteksi diuji sebagai fungsi murni dari status dan tanggal. Skill worker yang ada diperkaya dengan perilaku proaktif yang baru; skill benar-benar baru hanya bila tidak ada yang menutupinya.

## Bagian C — Tahap 2 (SELESAI 20 Nov 2026, commit cad237d)

**Status: SELESAI.** Diputuskan Ten 20 Nov 2026 10:40 WIB (keempat kandidat di bawah **ditambah** custom scheduler per detektor dari Desk — lima item Tahap 2), diimplementasi dan diverifikasi, commit **cad237d** (20 Nov 2026, 18 file).

**Hasil verifikasi:**
- Tes: **11/11** (`test_sales_proactive`, Tahap 1 — tidak ada regresi), **29/29** (`test_sales_proactive_tahap2`), **10/10** (`test_skills_engine`), **5/5** (`test_draft_contract`).
- DocType `AIOS Proactive Detector Setting` dan `AIOS Proactive Detector Schedule` ada di DB site klien.
- Data DEMO di site dev bersih (0 sisa).
- Pemindaian penuh di site klien: **110 temuan**, **58 terkirim**, **0 gagal**.

**Keputusan yang dikunci (K1–K12):** K1 churn 75 hari; K2 churn memakai `Sales Invoice` `docstatus=1` kecuali retur; K3 dedup churn sekali per 7 hari; K4 pola pembelian median interval dikurangi 7 hari dengan minimal 3 pembelian; K5 anomali harga ambang diskon 20% dan bukan `pricing_rules`; K6 overprice ikut ditandai; K7 `valid_till` draf +14 hari; K8 dispatcher per detektor; K9 tab Insight Proaktif di Pengaturan; K10 satu ringkasan gabungan 7 detektor per pemindaian (badge 1, hanya bila ada temuan) dan Drafting hanya menyiapkan bahan; K11 bangun `predict_customer_churn_risk`; K12 tambah entry scheduler baru tanpa mengubah entry harian lama. **Lookback** Churn 730 hari dan Drafting 180 hari (dikonfirmasi Ten 20 Nov 2026, tidak diubah).

1. **Churn & Reactivation Radar.** Menandai customer yang sudah lama tidak membeli (misalnya 60–90 hari) dan menyarankan tindak lanjut.
2. **Purchase Pattern & Reorder Intelligence.** Membaca pola pembelian customer dan memperkirakan kapan ia kemungkinan memesan lagi, serta item apa.
3. **Pricing & Discount Anomaly Detector.** Menandai harga atau diskon di Quotation dan Sales Order yang menyimpang jauh dari harga standar atau pola biasa.
4. **Intelligent Quotation & Order Drafting.** Menyiapkan draf Quotation atau Sales Order dari pembelian terakhir customer — draf tetap dibuat hanya bila karyawan meminta.
5. **Custom scheduler per detektor dari Desk.** Tiap detektor Tahap 2 punya penjadwalan sendiri yang bisa diatur dari Desk — bukan satu jadwal bersama untuk semua detektor. Rincian bentuk dan teknisnya dibahas di investigasi Tahap 2.

## Bagian D — Kandidat Tahap 3 (belum diputuskan)

1. **Transaction Anomaly & Duplicate Detector.** Menandai order atau invoice yang ganda atau janggal (nilai, tanggal, atau customer yang tidak biasa).
2. **Next-Best-Product Recommendation.** Menyarankan produk yang paling mungkin dibeli customer berikutnya berdasarkan pembelian sebelumnya.
3. **Predictive Sales Forecasting.** Memperkirakan penjualan periode berikutnya dari tren yang ada — angka dihitung oleh tool deterministik, bukan ditebak dari baris mentah oleh LLM.

## Bagian E — Kandidat ronde 2 (belum diputuskan)

1. **Lead & Opportunity Intelligence.** Memantau Lead dan Opportunity yang mandek dan menyarankan tindak lanjut. Catatan: Lead dan Opportunity belum ada di allowlist `ERP_CLIENT_DOCTYPES` — perlu perluasan allowlist dan modul.
2. **Pricing Rule Explainer & Promotion Intelligence.** Menjelaskan aturan harga dan promosi yang berlaku untuk suatu Quotation, dan menandai promosi yang segera berakhir.
3. **Sales Partner & Commission Intelligence.** Menghitung dan memantau komisi partner penjualan. Catatan: tool `calculate_sales_commission` dijanjikan skill tetapi belum dibangun.
4. **Sales Return & Customer Feedback Intelligence.** Memantau retur penjualan dan umpan balik customer yang masuk. Catatan: tool `approve_sales_return` dijanjikan skill tetapi belum dibangun.
5. **Customer Self-Service AI.** Customer bertanya lewat portal dan dijawab AI — dengan batas ketat: hanya dokumen miliknya sendiri yang bisa dibaca.
6. **Sales Command Center.** Satu tampilan komando untuk Sales di Desk (angka kunci, peringatan, dan daftar tindakan) memakai mekanisme Workspace Frappe.
7. **Contextual Sales Window.** Jendela Sales yang menampilkan konteks yang relevan dengan apa yang sedang dikerjakan pengguna saat itu.
8. **Cross-Department Demand Handoff.** Meneruskan kebutuhan dari Sales ke Purchasing secara baca-saja — pekerjaan penuh pindah ke cabang tujuan, bukan dikerjakan sendiri.

## Bagian F — Temuan: tool yang dijanjikan skill tetapi belum dibangun

Empat tool dirujuk oleh skill Sales tetapi tidak ada di kode (pencarian di seluruh `aios_v1/*.py` kosong): `approve_sales_return`, `calculate_sales_commission`, `analyze_sales_trends`, `generate_sales_forecast`. Petanya: `approve_sales_return` → Bagian E nomor 4; `calculate_sales_commission` → Bagian E nomor 3; `analyze_sales_trends` + `generate_sales_forecast` → Bagian D nomor 3. Tool-tool ini dibangun saat fiturnya masing-masing dipilih, bukan sekarang.

## Keputusan yang sudah dikunci

- **Kanal: Desk dulu, Telegram kalau jauh.** Insight proaktif masuk ke chat Desk dulu; Telegram hanya bila pengguna jauh dari Desk.
- **Wewenang: hanya kasih tahu, draf tetap nunggu disuruh.** Agent proaktif hanya memberi tahu; draf dibuat hanya bila karyawan meminta.
- **Data harus hidup.** Fitur butuh data yang mencerminkan kenyataan; seed yang dipakai untuk membangun dan memverifikasi memakai tanggal relatif dan skenario pemicu yang disengaja, berlabel DEMO, dan bisa dibersihkan. Aturan deteksi diuji dengan unit test. Jalur kode yang sama dipakai untuk data demo dan data live. Ada penjaga kesegaran data — agent melaporkan kapan data terakhir diperbarui.
- **Cara verifikasi live.** Tes statis (TDD) → full suite → build → pindai manual di site dev dengan scenario seed → pesan proaktif muncul di chat Desk cabang Sales (pesan agent + label DEMO + catatan kesegaran) → cek fallback Telegram dengan Desk tertutup dan pastikan tidak ada duplikat antar kanal → insight mengutip nama dan nilai dokumen yang benar-benar ada di ERP saat itu (bukti baca live) → pastikan tidak ada draf yang dibuat tanpa disuruh → cek ulang keesokan hari. Verifikasi manual dilakukan Ten sendiri. Batas jujur: benar tidaknya insight secara bisnis (misalnya apakah customer benar-benar akan churn) tidak bisa dibuktikan dari data seed — hanya dari data client yang sebenarnya; verifikasi live membuktikan pipelinenya jalan.

## Global Constraints

- Plan dibekukan sampai Lapis B (keputusan Ten + Pak Oscar, 19 Nov 19:05 WIB): tidak ada bidang baru, 4 bidang aktif tetap (Sales, Finance, Accounting, Purchasing), 7 planned tetap planned.
- Pelan dan benar mengalahkan cepat dan salah (Ten, 19 Nov): bila pekerjaan tidak selesai sesuai target, lanjut setelahnya tanpa ngebut.
- Persetujuan atas rencana BUKAN persetujuan atas isi draf perintah: tiap draf dibaca Ten dulu sebelum dikirim ke builder.
- Satu perintah sama dengan satu pekerjaan; investigasi saja dan implementasi saja tidak dicampur; sebut "draf investigasi" dan "draf implementasi", jangan "Fase 0/Fase 1".
- Yang dikunci hanya keputusan Ten; selain itu builder yang memikirkan cara terbaiknya — jangan persempit builder dengan aturan tambahan.
- Commit lokal dibuat setelah verifikasi berhasil; tidak push tanpa perintah eksplisit Ten.
- Bila temuan builder berbeda dengan temuan investigasi awal, STOP, jangan improvisasi, laporkan perbedaannya dan tunggu keputusan Ten.
- Verifikasi visual memakai layar Ten yang sebenarnya; hasil inspeksi di viewport kecil tidak boleh diklaim sebagai kondisi layar Ten (pelajaran 19 Nov: judul dan avatar ternyata tidak kepotong di layar Ten).

## Review Focus

- Builder berhenti karena tes mengunci perilaku lama (sudah terjadi dua kali: taskbar B2, agent Purchasing) — bila berhenti, kunci tes itu diverifikasi dulu di kode, lalu Ten yang memutuskan sebelum tes diubah; update tes bukan hal rutin.
- Hasil inspeksi visual di jendela browser kecil menyesatkan — verifikasi live harus di layar Ten yang sebenarnya, lewat tab Chrome yang Ten bukakan.
- Scope merayap ke bagian berikutnya sebelum bagian berjalan selesai — tiap bagian selesai dan diverifikasi dulu sebelum bagian berikutnya dimulai.
- Bentuk pelonggaran dan bentuk tiap fitur diputuskan Ten dari opsi laporan investigasi — builder tidak memutuskan desain sendiri.
- Tombol stop butuh jalur abort ujung ke ujung (frontend AbortController + penutupan SSE backend) — bila backend tidak bisa dihentikan, itu dilaporkan sebagai batasan dengan opsi, bukan ditambal diam-diam.
- Insight proaktif yang sama terkirim berulang setiap hari — dedup (catatan insight terkirim per dokumen dan aturan) wajib ada sebelum Bagian B dinyatakan selesai.

---

## Jadwal (aktual, WIB)

Kamis 19 Nov 2026 — Bagian A: SELESAI 21:13 WIB.
- Investigasi frontend selesai 20:32 WIB; laporan di root repo.
- Lima keputusan Bagian A dikunci Ten 20:46–20:58 WIB → draf implementasi ditulis dan dibaca Ten 20:59 WIB → implementasi builder berjalan (melanjutkan sesi investigasi yang sama) → verifikasi (tes, build, kode) → commit lokal d2495a8 pukul 21:13 WIB.
- Verifikasi visual live di layar Ten dan penerimaan Ten: 20 Nov 2026. Docs sync 98c63d9.

Jumat 20 Nov 2026 — Bagian B: SELESAI 10:35 WIB.
- Investigasi Tahap 1 → laporan direview Ten → draf implementasi → implementasi builder → verifikasi live dengan scenario seed → commit lokal 2749d89 + c08dfaf + b4e0c7a + bfcf34b → docs sync 67f5f20.
- Hasil: 105 tes hijau, build lolos, terverifikasi live di Desk client, data DEMO dibersihkan. Telegram nyata belum terverifikasi.

Sesudah Bagian B — Bagian C, D, E:
- Bagian C **selesai** 20 Nov 2026 (commit cad237d): lima item Tahap 2 (empat kandidat + custom scheduler per detektor dari Desk) terimplementasi dan terverifikasi.
- Bagian D dan E belum diputuskan. Tiap fitur yang dipilih mengikuti urutan yang sama (investigasi → review → implementasi → verifikasi). Tidak ada jadwal tetap sampai Ten memilih.

## Tahap-tahap kerja

### Tahap A1: Investigasi frontend — SELESAI 19 Nov 20:32 WIB

- Laporan: laporan-investigasi-frontend-chat-agent.md (root repo).
- Temuan yang sudah diverifikasi reviewer: panel terkunci 410 px; pola resize dan maximize sudah ada dan bisa dipakai ulang (useWindowManager.ts toggleMax/startResize/winStyle, WindowHost.vue tombol maximize/restore dan div resize); list draft hanya PENDING_APPROVAL dan EXPIRED (draft_manager.py:875-878); 7 dari 8 temuan investigasi awal sesuai, 1 nuansa bukan perbedaan nyata (tombol draft tetap muncul dengan badge ! saat pemuatan gagal).
- Lima keputusan sudah dikunci semua (lihat Bagian A); draf implementasi sudah ditulis dan implementasinya selesai 19 Nov 2026 21:13 WIB (commit d2495a8).

### Tahap A2: Implementasi frontend — SELESAI 19 Nov 2026 21:13 WIB, diterima Ten 20 Nov 2026

**Files:**
- Modify: `frontend/src/components/agent/AgentPanel.vue` dan komponen terkait yang laporan investigasi tunjuk (store chat, jendela draft, setting percakapan)
- Test: file tes yang laporan investigasi daftarkan sebagai terdampak (test_frontend_no_hardcode.py, test_approval_card_contract.py, test_draft_manager.py, test_authz_dispatcher.py; frontend tanpa unit test Vitest/Jest — verifikasi lewat typecheck dan build)

**Interfaces:**
- Consumes: laporan investigasi Tahap A1 + lima keputusan Ten.
- Produces: delapan item terbangun di chat agent + tes hijau + build hijau + commit lokal.

- [x] **Step 1: Draf implementasi ditulis** — sudah selesai 19 Nov 20:57 WIB, dicek baris demi baris dengan template prompt (0 "Ini:", 0 heading markdown, 0 path workspace, penutup benar). File: sales-maksimalisasi-frontend-longgar-draft-implementasi.md.
- [x] **Step 2 (Gate Ten): Ten baca draf implementasi dan bilang cocok** — sudah, Ten setuju 19 Nov 20:59 WIB ("saatnya implementasi, pake sesi sama, dan hydrogen medium").
- [x] **Step 3: Draf dikirim ke builder** — selesai, implementasi jalan 20:59–21:13 WIB, sesi investigasi yang sama, Hydrogen Medium.
- [x] **Step 4: Implementasi builder berjalan** — selesai 21:13 WIB, exit 0.
- [x] **Step 5: Hasil implementasi masuk (commit lokal)** — commit d2495a8, 12 file, +1713/-432, tidak di-push.
- [x] **Step 6 (Gate Reviewer): Verifikasi** — selesai 21:14 WIB oleh Muse: commit ada dengan angka persis (12 file, +1713/-432); delapan item dicek keberadaannya di kode (AbortController + stop_stream, SpeechRecognition ×17, is_pinned/is_archived + 4 endpoint, gear 0, resize 340/960 + sidebar ≥640, tab Riwayat + status APPROVED/EXECUTED/REJECTED, konteks berhenti di base_manager.py); npm run build hijau; bench test_draft_manager 12/12 OK + test_authz_dispatcher 18/18 OK (di-rerun Muse); pytest -q penuh menunjukkan 35 failed + 670 errors TAPI angka yang sama persis muncul di parent commit 3601dc8 (worktree check) — jadi gagal pre-existing karena pytest polos tanpa konteks bench, bukan regresi; angka 116 passed di laporan builder adalah subset statis, bukan direktori penuh. SISA saat itu: verifikasi visual live di layar Ten — sudah dilakukan dan **diterima Ten 20 Nov 2026**, docs sync 98c63d9.
- [x] **Step 7: Commit lokal** — sudah (d2495a8); tidak di-push tanpa perintah eksplisit Ten.

### Tahap B1: Investigasi Tahap 1 Sales — SELESAI (prasyarat Bagian B)

**Files:**
- Sasaran baca builder: `aios_v1/permissions.py` (allowlist `ERP_CLIENT_DOCTYPES`), `aios_v1/api/chat.py` (SSE), `aios_v1/lib/draft_manager.py` (notifikasi approval), `aios_v1/plugin_manager/registry.py` (cabang sales dan worker), `frappe/email/doctype/notification/notification.py` + `frappe/hooks.py` (pola pemicu resmi)

**Interfaces:**
- Consumes: tiga detektor + perbaikan notif + fondasi Bagian B + keputusan Ten yang sudah dikunci (kanal, wewenang, data, verifikasi).
- Produces: laporan investigasi + opsi bentuk implementasi + daftar tes yang terdampak.

- [x] **Step 1: Draf investigasi ditulis** — setelah Bagian A selesai dan Ten memutuskan scope-nya; sudah dilalui sebelum Bagian B dikerjakan.
- [x] **Step 2 (Gate Ten): Ten baca draf dan bilang cocok**
- [x] **Step 3: Investigasi builder berjalan; laporan masuk dan di-crosscheck ke kode**
- [x] **Step 4 (Gate Ten): Ten review laporan dan putuskan bentuk implementasi**

### Tahap B2: Implementasi Tahap 1 Sales — SELESAI 20 Nov 2026 10:35 WIB

- [x] **Step 1: Draf implementasi ditulis dan dibaca Ten** — selesai.
- [x] **Step 2: Implementasi builder berjalan** — selesai; commit 2749d89 + c08dfaf + b4e0c7a + bfcf34b.
- [x] **Step 3 (Gate Reviewer): Verifikasi** — tes, build, kode; lalu verifikasi live dengan scenario seed sesuai cara verifikasi yang dikunci (pesan muncul di chat Desk + label DEMO + kesegaran data, fallback Telegram tanpa duplikat, insight mengutip dokumen yang benar-benar ada, tidak ada draf tanpa disuruh, cek ulang keesokan hari). **Hasil:** 105 tes hijau, build lolos, terverifikasi live di Desk client, data DEMO dibersihkan. **Belum terverifikasi:** pengiriman Telegram nyata.
- [x] **Step 4: Commit lokal** — commit 67f5f20 (docs sync) setelah verifikasi hijau; tidak di-push tanpa perintah eksplisit Ten.

### Tahap C/D/E: Kandidat berikutnya — Bagian C SELESAI 20 Nov 2026 (cad237d, 5 item Tahap 2); Bagian D dan E belum diputuskan

- Bagian C: lima item Tahap 2 **selesai** 20 Nov 2026 (commit cad237d) — empat detektor baru (`churn_reactivation`, `purchase_pattern_reorder`, `pricing_discount_anomaly`, `intelligent_drafting`) plus custom scheduler per detektor, dengan tes 11/11, 29/29, 10/10, 5/5 hijau.
- Bagian D dan E: belum diputuskan — Ten memilih fitur berikutnya dari daftar kandidat.
- Tiap fitur yang dipilih Ten mengikuti urutan yang sama (investigasi → review → implementasi → verifikasi). Tidak ada tugas yang ditulis sebelum Ten memilih.

## Definition of Done

- Bagian A: delapan item terbangun, tes hijau, build hijau, terlihat benar di layar Ten. — **TERPENUHI** (commit d2495a8, 19 Nov 2026 21:13 WIB; diterima Ten 20 Nov 2026).
- Bagian B: tiga detektor + perbaikan notif + fondasi terbangun; pesan proaktif muncul di chat Desk dengan label DEMO pada data demo; tidak ada duplikat antar kanal; tidak ada draf yang dibuat tanpa disuruh; dedup jalan. — **TERPENUHI** (commit 2749d89 + c08dfaf + b4e0c7a + bfcf34b, 20 Nov 2026 10:35 WIB; 105 tes hijau, build lolos, terverifikasi live di Desk client, DEMO dibersihkan), **kecuali jalur Telegram nyata yang belum terverifikasi**.
- Bagian C: empat detektor Tahap 2 + custom scheduler per detektor terbangun; tujuh detektor berjalan dalam satu pemindaian dengan satu ringkasan per pemindaian; jadwal tiap detektor bisa diubah dari Desk tanpa deploy; tidak ada draf yang dibuat otomatis. — **TERPENUHI** (commit cad237d, 20 Nov 2026; tes 11/11, 29/29, 10/10, 5/5; DocType ada di DB site klien; DEMO dev bersih; pemindaian penuh client 110 temuan / 58 terkirim / 0 gagal).
- Keseluruhan: tiap bagian selesai dan diverifikasi dulu sebelum bagian berikutnya dimulai; tidak ada push tanpa perintah Ten; tidak ada bidang baru selama freeze Lapis B.

## Yang TIDAK masuk rencana ini

- Bidang baru di luar Sales (freeze Lapis B).
- Sebelas fitur kandidat yang belum dipilih Ten (Bagian D 3 item + Bagian E 8 item) — masuk rencana kerja hanya setelah dipilih. Bagian C (lima item Tahap 2) **selesai** 20 Nov 2026 (commit cad237d).
- Empat tool yang hilang (Bagian F) — dibangun saat fiturnya masing-masing dipilih.

## Risiko dan bila meleset

- Bila investigasi atau implementasi molor dari target, lanjut setelahnya tanpa ngebut — tidak ada jalan pintas.
- Bila verifikasi live tidak bisa dilakukan pada waktunya (Ten sibuk), commit lokal tetap dibuat setelah tes dan build hijau, dan verifikasi visual dicatat sebagai menunggu Ten.
- Bila builder menemukan bahwa satu item tidak bisa dibangun seperti yang Ten bayangkan (misalnya stop tidak bisa menutup SSE backend), item itu dilaporkan sebagai batasan dengan opsi, bukan dipaksakan.
- Bila satu detektor memberi insight yang salah secara bisnis pada data demo, itu dicatat sebagai batasan demo — kebenaran bisnis hanya bisa dibuktikan dari data client yang sebenarnya.
