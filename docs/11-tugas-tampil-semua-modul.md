# Tugas: Tampilkan Semua Modul + Branding Finto OS

Daftar tugas gaya Superpowers — menandai posisi kita sekarang. Peta analisis/keputusan ada di `peta-tampil-semua-modul.md` (dokumen acuan, stabil); file ini yang hidup (dicentang tiap selesai). Detail tiap tugas (nilai yang dipin, langkah 1–8) ada di plan (`rencana-lapis-a-superpowers.md`); file ini cermin checklist-nya supaya alur tiap fase kelihatan dari A sampai Z.

## 📍 POSISI SEKARANG
Plan Superpowers Fase 1 DISETUJUI Ten (20:44) + file-file SUDAH di repo (20:54, 97 file, terverifikasi, tanpa commit — masih untracked di PC). **Task 1 (Delivery Note) SELESAI PENUH + terverifikasi live oleh Ten (17 Nov 10:35 WIB, commit 7fbf92c, sudah push 17 Nov 12:54). Task 2 (Item Price) kode + tes SELESAI (commit a17b0f1, sudah push); tinggal verifikasi live — menunggu bench/PC nyala.** Berikutnya: sinkronisasi dokumen via cloud di feat/plugin-mcp-manager (sesi remote sedang checkout branch kerja + setup ulang environment; file di-upload sebagai Resource; draf prompt menunggu Ten baca), lalu Task 3 setelah Task 2 ditutup.

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

### Task 2: Item Price → Sales — kode + tes selesai, tinggal verifikasi live
- [x] Draf investigasi ditulis Muse → dibaca Ten → dikirim ke Gemini
- [x] Investigasi Gemini + crosscheck Muse (semua 10 tugas terkonfirmasi; contoh harga Standard Selling client1: LAP-ENT-14 Rp 18.500.000)
- [x] Draf implementasi ditulis Muse → dibaca Ten → dikirim ke Gemini (Revisi 1; Ten setuju 10:53)
- [x] Implementasi Gemini + crosscheck Muse (commit 9dbecc3 lalu di-amend Ten 12:54 jadi a17b0f1; 4 file draf dihapus dari repo atas keputusan Ten — draf hanya ada di tempat Muse)
- [x] Tes hijau (27/27, 8/8, 13/13 — angka klaim Gemini, Muse belum menjalankan ulang); hitung langsung client1: 15 baris selling=1
- [x] Scope company dicek: Item Price tanpa field company → pengecualian `_server_filters` (desktop.py:226); sudah bisa dibaca tamu sekalipun, jadi bukan blocker
- [ ] Verifikasi live oleh Gemini (checklist: Sales 7 modul termasuk Item Price tanpa error; kartu "Harga item di site" = 15; LAP-ENT-14 terlihat; search "Laptop Enterprise" menemukan baris) — menunggu bench/PC nyala
- [x] Commit a17b0f1, sudah push 17 Nov 12:54 (7 file, +131/−4)

### Task 3: Journal Entry → Accounting — BELUM DIMULAI (aktifkan bidang Accounting)
- [ ] Draf investigasi
- [ ] Investigasi Gemini + crosscheck Muse
- [ ] Draf implementasi
- [ ] Implementasi Gemini + crosscheck Muse
- [ ] Tes
- [ ] Verifikasi live
- [ ] Commit
- Catatan: bidang Accounting planned → active; kartu KPI `journal_debit` "Total debit jurnal"; Journal Entry tidak punya field status (filter Jenis menggantikannya).

### Task 4: GL Entry → Accounting — BELUM DIMULAI
- [ ] Draf investigasi
- [ ] Investigasi Gemini + crosscheck Muse
- [ ] Draf implementasi
- [ ] Implementasi Gemini + crosscheck Muse
- [ ] Tes
- [ ] Verifikasi live
- [ ] Commit
- Catatan: base_filters `{"is_cancelled": 0}` — BUKAN `{"docstatus": 1}` (GL Entry tidak pernah disubmit); 3 kartu bidang (Entri GL tercatat, Total debit, Total kredit).

### Task 5: Account → Accounting — BELUM DIMULAI
- [ ] Draf investigasi
- [ ] Investigasi Gemini + crosscheck Muse
- [ ] Draf implementasi
- [ ] Implementasi Gemini + crosscheck Muse
- [ ] Tes
- [ ] Verifikasi live
- [ ] Commit
- Catatan: kartu "Akun aktif" (tanpa "di site"); base_filters `{"disabled": 0}`; Account punya field company (di-scope ke company aktif).

### Task 6: Company → Accounting — BELUM DIMULAI
- [ ] Draf investigasi
- [ ] Investigasi Gemini + crosscheck Muse
- [ ] Draf implementasi
- [ ] Implementasi Gemini + crosscheck Muse
- [ ] Tes
- [ ] Verifikasi live
- [ ] Commit
- Catatan: list site-wide tanpa filter company (record Company ADALAH company itu sendiri); kartu "Company di site". Keadaan akhir Fase 1: 14 modul, 3 bidang aktif (sales, finance, accounting), 8 bidang planned.

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
