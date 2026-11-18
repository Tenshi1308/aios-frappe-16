# Referensi — Finto OS (platform tampilan seragam Ekasa Technology)

Folder ini **tidak di dalam repo git** (`bench16-spi/referensi/`). Disiapkan 12 Nov 2026 untuk dikerjakan di kesempatan lain;
saat ini fokus tetap di SPI. Salin seluruh folder ini ke repo/proyek baru saat mulai mengerjakan.

| File | Isi |
|---|---|
| `01_RENCANA_TEKNIS_FINTO_OS.md` | **Mulai di sini.** Masalah, arsitektur 3 lapis (finto_os → produk → pelanggan), isi backend & frontend finto_os, kontrak hook/endpoint/menu, branding, tahapan kerja, uji, keputusan pemilik |
| `02_SPESIFIKASI_TAMPILAN_FINTO_OS.md` | Acuan visual "sama persis": palet, logo, timeline animasi booting, layar kunci/login, desktop, jendela, ikon, wallpaper, gaya umum |
| `03_INVENTARIS_FILE.md` | Tabel asal → tujuan setiap file/modul + daftar isi snapshot |
| `04_SELISIH_FRONTEND_FINTO_EDU_VS_SPI.md` | Hasil `diff` frontend finto_edu vs spi_fintoedu (file hanya di SPI, berbeda, hanya di finto_edu) dengan saran tujuan |
| `kode-snapshot/spi_fintoedu/…` | Salinan kode yang membentuk Finto OS & komponen bersama per 12 Nov 2026 (path asli dipertahankan): frontend desktop/booting/login, store, router, layout, komponen, gaya, logo, backend `ui_settings.py`, `desktop_prefs.py`, `onboarding.py`, `notifications.py`, `transaction_detail.py`, `desk_guard.py`, test, dan dokumen spesifikasi terkait |

## Cara memakai snapshot agar tampilan sama persis
1. Mulai dari `kode-snapshot/spi_fintoedu/frontend/src/features/desktop/` (BootScreen, DesktopLogin, DesktopShell, DesktopWindow, WallpaperModal, `desktop.css`, `appStyles.ts`, `wallpapers.ts`, `iconLayout.ts`, `prefsApi.ts`, `context.ts`) + `stores/desktop.ts`, `stores/ui.ts`, guard di `router/index.ts`, rute di `router/routes.ts`, `layouts/DefaultLayout.vue`, logo `assets/images/finto-os-logo.png`.
2. Dependensi frontend: lihat `kode-snapshot/spi_fintoedu/frontend/package.json` (Vue 3.4, vue-router, pinia, bootstrap 5 + bootstrap-vue-next 0.21, sweetalert2, flatpickr, iconoir icons, template Rizz 1.1 SCSS).
3. Backend minimum: `ui_settings.py` (mode web/desktop) + `desktop_prefs.py` (wallpaper & posisi ikon). Endpoint di snapshot masih ber-namespace `spi_fintoedu.api.*` — ganti ke namespace app baru (lihat 03).
4. Bandingkan hasil dengan `02_SPESIFIKASI_TAMPILAN_FINTO_OS.md`; bila berbeda, kode snapshot yang benar.

## Catatan
- Kode di snapshot adalah **salinan beku**; versi terbaru tetap di repo `spi_fintoedu`. Jika SPI berubah sebelum proyek dimulai, perbarui snapshot (salin ulang file yang sama) atau ambil langsung dari repo.
- Hal yang khusus SPI di file snapshot (logo SPI di login, teks "akun SPI", baris log "Keuangan SPP", menu & peran SPI di `menu-catalog.ts`) harus menjadi **branding/konfigurasi**, bukan bagian kit (lihat 01 §6).
