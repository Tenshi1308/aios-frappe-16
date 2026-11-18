# Spesifikasi Tampilan Finto OS (acuan "sama persis")

Snapshot 12 Nov 2026 dari `spi_fintoedu/frontend`. Kode lengkap ada di `kode-snapshot/spi_fintoedu/frontend/src/features/desktop/`.
Bila ada perbedaan antara dokumen ini dan kode snapshot, **kode snapshot yang benar**.

## 1. Palet Finto OS (pemilik, 12 Nov 2026)

| Token CSS | Hex | Nama | Peran |
|---|---|---|---|
| `--fos-navy` | `#0B1F3B` | Navy | Primary — latar booting / gelap |
| `--fos-blue` | `#0E63FF` | Blue | Brand |
| `--fos-cyan` | `#00D4C8` | Cyan | Intelligence — garis grid, persen, kursor |
| `--fos-lime` | `#A7F432` | Lime | Growth — "[ OK ]", ujung progress, denyut logo |
| `--fos-violet` | `#8B5CF6` | Violet | Innovation — cadangan aksen |
| `--fos-light` | `#F3F7FB` | Light | Surface — teks di atas gelap |

Teks sekunder aplikasi (bukan booting): abu-abu `#64708a` (kontras 4,97:1 di putih, WCAG AA) — `$secondary` & `$body-secondary-color`.

## 2. Logo
- File: `frontend/src/assets/images/finto-os-logo.png` (327×337, PNG RGBA, latar transparan) — huruf "F" dua bidang miring (cyan→biru) + daun lime.
- Dipakai: layar booting (112×116 px) dan tombol Start taskbar (24×24 px, `object-fit: contain`).
- Layar login memakai logo **pelanggan** (SPI: `spi-logo-full.png`) — nanti dari branding.

## 3. Animasi booting (`BootScreen.vue`, rute `/boot`, nama `desktop.boot`)

Kapan: mode desktop, **belum login**, setiap halaman dimuat/refresh (status "sudah boot" hanya di memori; tidak saat navigasi internal seperti logout). Tidak ada tombol Lewati.

Lapisan (z-order bawah → atas): latar → grid lantai → scanline → vignette → konten tengah.

| Elemen | Detail |
|---|---|
| Latar | `radial-gradient(ellipse at 50% 38%, rgba(14,99,255,.28) 0%, transparent 55%), radial-gradient(ellipse at 50% 40%, #12305a 0%, #0B1F3B 55%, #06111f 100%)` |
| Grid lantai | 48×48 px, garis cyan `rgba(0,212,200,.2)` & biru `rgba(14,99,255,.22)`, `perspective(420px) rotateX(62deg)`, tinggi 60% dari bawah, bergerak 2,4 s linear tak hingga, mask memudar ke atas |
| Scanline | garis 1 px tiap 3 px `rgba(255,255,255,.025)` + pita cahaya cyan 120 px turun 3,2 s |
| Vignette | `inset 0 0 180px rgba(4,12,24,.85)` |
| Konten | lebar `min(440px, 100vw-48px)`, tengah |
| Logo | masuk: dari `scale(.6) translateY(8px)` opacity 0 → normal, 0,9 s `cubic-bezier(.2,.9,.25,1.15)` tunda 0,15 s. Halo radial cyan/biru (inset −28 px, blur 6 px) berdenyut 2,4 s mulai 1,4 s. Kilau putih menyapu logo sekali (mask = bentuk logo) 1,1 s mulai 1,0 s. Denyut drop-shadow cyan ↔ lime 2,4 s mulai 1,4 s |
| Nama | "FINTO OS", huruf per huruf muncul (tunda 0,9 s + 0,06 s × indeks), 30 px, weight 300, letter-spacing .45em, warna Light, glow cyan+biru |
| Versi | "v1.0 · build 2026.11", 11 px, Light 60%, muncul 1,5 s |
| Progress | tinggi 3 px, latar Light 12%, bar gradasi **Blue → Cyan → Lime** + glow cyan; nilai `floor((1-(1-t)^2.2)×100)` maks 99 sampai selesai |
| Persen | "000%"–"100%", 11 px, Cyan, rata kanan |
| Log | font monospace 12 px, Light 82%, tiap baris "[ OK ]" (Lime) + teks; 7 baris muncul merata antara 0,7 s dan (total−0,4 s); kursor "_" Cyan berkedip 0,9 s |
| Durasi | total 4,2 s (1,5 s bila `prefers-reduced-motion`), selesai di total+0,25 s → keluar (opacity 0, scale 1.02, 0,5 s) → `desktop.login` |

Baris log saat ini (SPI): Memulai kernel Finto OS · Memeriksa koneksi server sekolah · Memuat modul Admisi & Murid · Memuat modul Akademik & LMS · Memuat modul Keuangan SPP · Memuat modul Penggajian · Menyiapkan antarmuka desktop. (Nanti: dari hook `finto_os_boot_log`.)

`index.html`: kelas `html.os-mode` dipasang sebelum aplikasi dimuat bila `localStorage.spi_ui_mode !== "web"` → splash logo lama disembunyikan.

## 4. Layar kunci & login (`DesktopLogin.vue`, `/desktop/login`)
- Latar = wallpaper (kelas `os-wallpaper`). Jam besar + tanggal + "Klik atau tekan tombol apa saja untuk masuk".
- Klik/tombol → form: logo pelanggan, "Masuk", "Gunakan akun SPI Anda", input username, input kata sandi dengan tombol panah bulat (submit), "Tampilkan kata sandi". Transisi `lock-slide` / `lock-fade`.

## 5. Desktop (`DesktopShell.vue`, `/desktop`)
| Bagian | Detail |
|---|---|
| Taskbar | tinggi 48 px (`--os-taskbar-h`), tombol Start (logo), Cari, tombol jendela terbuka, lonceng notifikasi (badge), jam |
| Ikon | grid sel 108×100 px, ikon 104 px lebar, tile 48×48 radius 12 gradien per aplikasi (`appStyles.ts`), label 12 px putih + bayangan; seret & lepas (ambang 6 px; sel terisi → tukar); simpan per user & peran; bawaan: kategori Master Data → Utama → Murid & Admisi → Akademik → Keuangan → Laporan → Portal → Pengaturan Sistem → Bantuan, tiap kategori kolom baru (layar sempit: jarak 1 sel). Klik kanan desktop: Ganti latar, Buka Start, **Rapikan ikon**, Tampilkan panduan, Muat ulang |
| Jendela | ukuran awal `min(1100, 78% vw) × min(760, 82% tinggi−taskbar)`, kaskade +28 px, **tidak dimaksimalkan** (kecuali lebar < 768 px), radius 10 px, tombol minimize kuning / maximize hijau / tutup merah, dapat diseret & diubah ukuran; satu jendela per rute; halaman di dalam jendela tanpa TopBar/sidebar (inject `DESKTOP_WINDOW`) |
| Menu Start | lebar `min(640px, 100vw−16px)`, cari, aplikasi per kategori, terakhir dibuka, profil & keluar |
| Wallpaper | preset: finto (Finto Biru, default), aurora, sunset (Senja), forest (Hutan), midnight (Tengah Malam), ocean, graphite, sakura — CSS di `wallpapers.ts`; unggahan JPG/PNG/WEBP ≤ 5 MB, privat |
| Panel kanan | "Tindak Lanjut" (ActionPane) — fitur SPI/produk, bukan platform; kit menyediakan slot panel kanan |

## 6. Gaya umum aplikasi (berlaku di dalam jendela & mode web)
- Tab (`nav-pills`/`nav-tabs`): bingkai + pemisah + "balon" aktif berjarak (`_spi-tabs.scss`).
- Baris transaksi dapat diklik → modal detail (`tr.tx-row`, `.tx-card` di `_spi-transactions.scss`; `TransactionDetailModal`).
- Input nominal Rupiah dengan pemisah ribuan (`CurrencyInput.vue`).
- Filter periode Tahun/Bulan default bulan berjalan (`PeriodFilter.vue`, `helpers/period.ts`).
- Tombol sekunder `outline-dark`/`outline-primary`, bukan abu-abu.
