# Tugas: Tampilkan Semua Modul + Branding Finto OS

Daftar tugas gaya Superpowers — menandai posisi kita sekarang. Peta analisis/keputusan ada di `peta-tampil-semua-modul.md` (dokumen acuan, stabil); file ini yang hidup (dicentang tiap selesai). Detail tiap tugas (nilai yang dipin, langkah 1–8) ada di plan (`rencana-lapis-a-superpowers.md`); file ini cermin checklist-nya supaya alur tiap fase kelihatan dari A sampai Z.

## 📍 POSISI SEKARANG
Plan Superpowers Fase 1 DISETUJUI Ten (20:44). **Task 1 (Delivery Note) SELESAI PENUH + terverifikasi live oleh Ten (17 Nov 10:35 WIB, commit 7fbf92c, sudah push 17 Nov 12:54). Task 2 (Item Price) SELESAI PENUH + terverifikasi live oleh Ten (18 Nov 08:18 WIB, commit a17b0f1, sudah push). Task 3 (Journal Entry) SELESAI PENUH + terverifikasi live oleh Ten (18 Nov 08:46 WIB, commit lokal 362b51a, belum push). Task 4 (GL Entry) SELESAI PENUH + terverifikasi live oleh Ten (18 Nov 09:45 WIB, commit lokal 5381790, belum push). Task 5 (Account) SELESAI PENUH + terverifikasi live oleh Ten (18 Nov 10:34 WIB, commit lokal 6fad288, belum push).** Dokumentasi ini (docs 10, 11, plan) di-commit 18 Nov, up to date dengan kondisi Task 5. Berikutnya: Task 6 (Company), satu-satu, setelah Ten bilang lanjut.

## Fase 0 — Investigasi & peta (SELESAI)
- [x] Peta tampil-semua-modul (`peta-tampil-semua-modul.md`)
- [x] Keputusan scope Ten (20:11 + 20:14): semua bawaan ERPNext; tanpa HRIS/Payroll; agen ikut dibuka; laporan keuangan jadi modul Desk; branding barengan dengan modul; modul baru read-only dulu, aksi hanya Sales + Finance
- [x] Branding tersimpan (`branding/` — logo, maskot Fino, dokumen UI, snapshot kode, video booting)

## Setelah plan disetujui — masuk ke docs repo (ditaruh Muse 16 Nov 2026 atas perintah Ten, setelah Ten setujui plan)
- [x] Plan → `docs/superpowers/plans/2026-11-16-lapis-a-tampil-semua-modul.md` (tanggal plan: 16 Nov — plan ditulis 16 Nov)
- [x] Peta → `docs/10-peta-tampil-semua-modul.md`
- [x] Daftar tugas (file ini) → `docs/11-tugas-tampil-semua-modul.md`
- [x] Branding → `docs/branding-finto-os/` (logo, Fino, palet); `.md` + snapshot SPI → `docs/branding-finto-os/referensi-asli/` (referensi mentah Pak Oscar, bukan spec AIOS); zip 17 MB asli tetap di workspace sebagai arsip
- [x] SESUAIKAN SEMUA PATH: semua `~/workspace/aios/...` di plan/peta/tugas diubah ke path repo (`docs/...`) — JANGAN sampai kejadian Hydrogen ngecek Windows + WSL tapi tetap nggak nemu terulang

## Fase 1 — Lapis A: 6 modul sudah diizinkan (DISETUJUI Ten 16 Nov 20:44)
Target: bidang jadi 3 (Sales, Finance, Accounting). Tanpa ubah izin, tanpa migrate.
Satu modul = satu tugas = satu commit; tugas berjalan berurutan 1 → 6.
Tiap tugas: draf investigasi → investigasi + crosscheck → draf implementasi → implementasi + crosscheck → tes → verifikasi live → commit.
- [x] Plan doc Superpowers ditulis + diverifikasi Muse (disetujui Ten 20:44)
- [x] Rencana fase disetujui Ten (20:44 — semua 4 poin diputuskan, termasuk base_filters Item Price `{"selling": 1}`)
- [x] Builder (Gemini) juga menjalankan Cloudflare Security Audit Skill selama implementasi (review + perkuat security sambil jalan — keputusan Ten 20:43; skill tidak tersedia di environment Gemini, review keamanan manual sebagai pengganti)
- [x] 4 poin review plan dijawab Ten (20:43): pengecualian Item Price ✓, kartu KPI Accounting ✓, ikon Company ✓; base_filters Item Price — diputuskan Ten 20:44: `{"selling": 1}`

### Task 1: Delivery Note → Sales — SELESAI PENUH ✅
- [x] Draf investigasi ditulis Muse → dibaca Ten → dikirim ke Gemini
- [x] Investigasi Gemini + crosscheck Muse
- [x] Draf implementasi ditulis Muse → dibaca Ten → dikirim ke Gemini (Revisi 2 + amendemen; Ten baca + setuju)
- [x] Implementasi Gemini + crosscheck Muse
- [x] Tes hijau (25/25, 8/8, 13/13)
- [x] Verifikasi live oleh Ten 17 Nov 10:35 WIB (Sales 6 modul; kartu 35 / Rp 1.095.950.000)
- [x] Commit 7fbf92c, sudah push 17 Nov 12:54

### Task 2: Item Price → Sales — SELESAI PENUH ✅
- [x] Draf investigasi ditulis Muse → dibaca Ten → dikirim ke Gemini
- [x] Investigasi Gemini + crosscheck Muse (semua 10 tugas terkonfirmasi; contoh harga Standard Selling client1: LAP-ENT-14 Rp 18.500.000)
- [x] Draf implementasi ditulis Muse → dibaca Ten → dikirim ke Gemini (Revisi 1; Ten setuju 10:53)
- [x] Implementasi Gemini + crosscheck Muse (commit 9dbecc3 lalu di-amend Ten 12:54 jadi a17b0f1; 4 file draf dihapus dari repo atas keputusan Ten — draf hanya ada di tempat Muse)
- [x] Tes hijau (27/27, 8/8, 13/13 — angka klaim Gemini, Muse belum menjalankan ulang); hitung langsung client1: 15 baris selling=1
- [x] Scope company dicek: Item Price tanpa field company → pengecualian `_server_filters` (desktop.py:226); sudah bisa dibaca tamu sekalipun, jadi bukan blocker
- [x] Verifikasi live oleh Ten 18 Nov 08:18 WIB + crosscheck SSH Muse 08:12 WIB (Sales 7 modul; kartu "Harga item di site" = 15; Laptop Enterprise 14 Inch Standard Selling Rp 18.500.000 di list Item Price; hitung langsung client1 selling=1 = 15; catatan: search "Laptop Enterprise" tidak tampak eksplisit di screenshot, barisnya kelihatan di list dan jalur search tercakup tes hijau)
- [x] Commit a17b0f1, sudah push 17 Nov 12:54 (7 file, +131/−4)

### Task 3: Journal Entry → Accounting — SELESAI PENUH ✅
- [x] Draf investigasi — disetujui Ten 17 Nov 22:47 (`~/workspace/aios/lapis-a-task3-journal-entry-investigasi-draft.md`); dikirim Muse via CLI 18 Nov 08:22 (Hydrogen Medium, conversation baru)
- [x] Investigasi Gemini + crosscheck Muse (18 Nov 08:25, 10/10 TERKONFIRMASI; jangkar +3, voucher Debit/Credit Note terpisah, contoh ACC-JV-2026-00011 Rp 3.000.000)
- [x] Draf implementasi — ditulis Muse 18 Nov, dibaca + disetujui Ten, dikirim via CLI di sesi yang sama (conversation 4c26f81d)
- [x] Implementasi Gemini + crosscheck Muse (18 Nov 08:35, commit 362b51a; entri journal_entry :464, accounting active :177; hitung langsung client1: count 15, sum Rp 90.400.000 — cocok)
- [x] Tes (28/8/13 PASS — angka klaim Gemini, Muse belum menjalankan ulang)
- [x] Verifikasi live oleh Ten 18 Nov 08:46 WIB (Accounting aktif, kartu Total debit jurnal Rp 90.400.000; modul Journal Entry: kartu Jurnal terbit 15, ACC-JV-2026-00011 Rp 3.000.000 baris teratas; catatan: search "HPP Pembelian" tidak tampak eksplisit di screenshot, barisnya kelihatan dan jalur search tercakup tes hijau)
- [x] Commit 362b51a, lokal tanpa push
- Catatan: bidang Accounting planned → active; kartu KPI `journal_debit` "Total debit jurnal"; Journal Entry tidak punya field status (filter Jenis menggantikannya).

### Task 4: GL Entry → Accounting — SELESAI PENUH ✅
- [x] Draf investigasi — ditulis Muse 18 Nov, dibaca Ten, dikirim ke Gemini via CLI (conversation baru c6a896b6)
- [x] Investigasi Gemini + crosscheck Muse (18 Nov 09:27, 10/10; TEMUAN: docstatus GL selalu 1 — asumsi plan terbantah, base_filters is_cancelled tetap benar, komentar dipin perlu diubah; mock belum punya cabang accounting — Opsi A diputuskan Ten; hitung langsung client1: 576 entri, debit = kredit Rp 78.525.598.000, contoh ACC-GLE-2026-00580 Rp 5.328.000)
- [x] Draf implementasi — ditulis Muse 18 Nov, dibaca + disetujui Ten, dikirim via CLI di sesi yang sama (conversation c6a896b6, Hydrogen High)
- [x] Implementasi Gemini + crosscheck Muse (18 Nov 09:42, commit 5381790; entri GL Entry :513, komentar dipin :541, kartu gl_count/gl_debit/gl_credit, mock cabang accounting Opsi A, tes baru :896)
- [x] Tes (29/8/13 PASS + typecheck — angka klaim Gemini, Muse belum menjalankan ulang; suite penuh: 22 error + 1 failure pra-ada di luar scope — tabel 'tabError Log' crash)
- [x] Verifikasi live oleh Ten 18 Nov 09:45 WIB (Accounting 4 kartu: Total debit jurnal Rp 90.400.000, Entri GL tercatat 576, Total debit = Total kredit Rp 78.525.598.000; modul GL Entry: 3 kartu sama, baris teratas ACC-GLE-2026-00580; catatan: search "Kas Kecil" tidak tampak eksplisit di screenshot, barisnya kelihatan dan jalur search tercakup tes hijau)
- [x] Commit 5381790, lokal tanpa push
- Catatan: base_filters `{"is_cancelled": 0}` — BUKAN `{"docstatus": 1}` (GL Entry dibuat oleh posting dan selalu ber-docstatus 1 — pakai is_cancelled 0 untuk mengecualikan 4 entri batal); 3 kartu bidang (Entri GL tercatat, Total debit, Total kredit). Mock cabang accounting SELESAI (Opsi A).

### Task 5: Account → Accounting — SELESAI PENUH ✅
- [x] Draf investigasi — ditulis Muse 18 Nov, dibaca Ten, dikirim ke Gemini via CLI (conversation baru 7a4594a6)
- [x] Investigasi Gemini + crosscheck Muse (18 Nov 09:55, 10/10; TEMUAN: jangkar tes baru :304-308 di test_desktop_domains meng-assert daftar modul accounting ["journal_entry", "gl_entry"] — tidak disebut plan, wajib ikut diupdate; tes kartu master aktual :492-506, plan menyebut :485; hitung langsung client1: 220 akun aktif, semua milik Tenshi Company, 0 nonaktif)
- [x] Draf implementasi — ditulis Muse 18 Nov, dibaca + disetujui Ten, dikirim via CLI di sesi yang sama (conversation 7a4594a6, Hydrogen High)
- [x] Implementasi Gemini + crosscheck Muse (18 Nov 10:14, commit 6fad288; entri account :573-602, domain accounting 3 modul, mock module_count 3, assert :305-309, subTest loop customer + account)
- [x] Tes (29/8/13 PASS — angka klaim Gemini, Muse belum menjalankan ulang; follow-up: deadlock MariaDB bila 2 suite jalan paralel, berurutan lolos)
- [x] Verifikasi live oleh Ten 18 Nov 10:34 WIB (Accounting 3 modul + 4 kartu: Total debit jurnal Rp 90.400.000, Entri GL tercatat 576, Total debit Rp 78.525.598.000, Total kredit Rp 78.525.598.000; modul Account: kartu "Akun aktif" 220, list 220 baris, Halaman 1 dari 9, baris teratas 1142.001 - Uang Muka Pembelian - TC; catatan: search tidak tampak eksplisit di screenshot, Sales/Finance tidak kelihatan di shot ini, kartu Total debit terpotong sebagian)
- [x] Commit 6fad288, lokal tanpa push
- Catatan: kartu "Akun aktif" (tanpa "di site"); base_filters `{"disabled": 0}`; Account punya field company (di-scope ke company aktif). Klarifikasi Ten: 220 itu akun-akun akuntansi di bagan akun — bukan customer, bukan akun user Frappe.

### Task 6: Company → Accounting — BELUM DIMULAI
- [ ] Draf investigasi
- [ ] Investigasi Gemini + crosscheck Muse
- [ ] Draf implementasi
- [ ] Implementasi Gemini + crosscheck Muse
- [ ] Tes
- [ ] Verifikasi live
- [ ] Commit
- Catatan: list site-wide tanpa filter company (record Company ADALAH company itu sendiri); kartu "Company di site". Keadaan akhir Fase 1: 14 modul, 3 bidang aktif (sales, finance, accounting), 8 bidang planned.

## Sesudah Lapis A — antrean follow-up (keputusan Ten 18 Nov; dikerjakan urut, satu-satu, sesudah Task 6)
- [ ] Tombol tutup untuk draf kadaluarsa di list Persetujuan Tertunda (DRF-2026-11-00082 masih tampil padahal sudah kedaluwarsa 17 Nov 14.00; list mengembalikan semua PENDING_APPROVAL, hanya ditandai flag expired) — solusi yang diputuskan Ten: tambah tombol tutup saja (bukan sembunyikan otomatis). Urutan: tugas berikutnya sesudah Task 6.
- [ ] Persona agent Accounting (tiap agent bidang punya persona masing-masing; Finance dan Sales sudah punya, Accounting belum dibikin) — sesudah tombol tutup, atau sesuai arahan Ten nanti.

## Fase 2 — 1 bidang planned sebagai pola: Purchasing (BELUM DIMULAI)

Riset mendalam + plan Superpowers untuk fase ini dibuat SETELAH Fase 1 selesai (keputusan Ten 20:24) — begitu juga fase-fase berikutnya, satu per satu, bukan sekaligus di awal.
- [ ] Purchase Order + Purchase Receipt + Supplier Quotation
- [ ] Keputusan dicatat: membalik `assertNotIn("Purchase Order")` di tes katalog

## Fase 3 — Bidang planned lain (BELUM DIMULAI)
- [ ] Inventory, Manufacturing, Projects, CRM, Assets, Support, Quality (sesuai prioritas atasan)

## Branding Finto OS / Fino (PARALEL dengan modul)
- [ ] Palet + logo + maskot Fino diterapkan ke shell
- [ ] Urutan vs modul: bersamaan — diputuskan Ten 20:11 (supaya frontend tidak ditulis 2x)

## Ditunda
- [ ] HRMS / HRIS + Penggajian (perlu pasang aplikasi HRMS — proyek tersendiri, bukan penambahan modul)

## Catatan
- Modul baru read-only dulu; aksi hanya Sales + Finance — dua bidang ini yang "digaspol sampai pucuk tertinggi".
- Tampil di Desk = bisa dibaca agen (allowlist global `ERP_CLIENT_DOCTYPES`) — tidak bisa dipisah.
- Scope company Item Price (tanpa field company): dicek per-DocType saat implementasi; Item Price sudah bisa dibaca tamu sekalipun, jadi bukan blocker.
- **Sinkronisasi dokumen tiap tugas (Ten, 2026-11-17):** tiap tugas diakhiri dengan sinkronisasi dokumentasi repo yang terdampak (peta, daftar tugas ini, plan, README bila ada dokumen baru) — dikerjakan builder sekalian saat eksekusi tugas, bukan kerja terpisah; branding dikecualikan (referensi saja).
