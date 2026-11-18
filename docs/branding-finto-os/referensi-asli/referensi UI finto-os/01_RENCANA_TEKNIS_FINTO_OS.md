# Rencana Teknis — Finto OS sebagai Platform Bersama Aplikasi Ekasa Technology

| | |
|---|---|
| Status | **Rencana** (belum dikerjakan). Disusun 12 Nov 2026 dari kondisi kode `spi_fintoedu` + `finto_edu` di bench `bench16-spi`. |
| Tujuan pemilik | Semua aplikasi/site buatan Ekasa Technology punya **tampilan & perilaku yang seragam** (animasi booting, desktop, login, komponen, warna) **selama tidak ada permintaan kustomisasi** pelanggan. |
| Pembaca | Developer / AI agent yang akan membangun `finto_os`. Baca juga `02_SPESIFIKASI_TAMPILAN_FINTO_OS.md` (agar tampilan sama persis), `03_INVENTARIS_FILE.md`, `04_SELISIH_FRONTEND_FINTO_EDU_VS_SPI.md`, dan kode di `kode-snapshot/`. |

---

## 1. Masalah saat ini

1. **Frontend disalin, bukan dibagi.** `spi_fintoedu/frontend` adalah salinan `finto_edu/frontend` (template Rizz, Vue 3, Bootstrap Vue Next — `package.json` sama). Per 12 Nov 2026: **56 file berbeda, 60 file hanya di SPI** (lihat 04_…). Perbaikan di satu sisi harus disalin manual dan dalam praktik tertinggal.
2. **Finto OS hanya ada di `spi_fintoedu`.** Mode desktop (booting, layar kunci/login, shell, jendela, taskbar, menu Start, wallpaper, posisi ikon) dan pengaturannya (`api/ui_settings.py`, `api/desktop_prefs.py`) tidak dimiliki `finto_edu` maupun produk Ekasa lain.
3. **Komponen umum terkunci di app pelanggan:** modal detail transaksi, filter periode, input Rupiah, tur panduan, tab hub, token warna/kontras, gaya tab & baris transaksi.
4. **Fitur platform berada di app produk:** Activity Monitoring (`finto_edu/services/activity_monitor*.py`) tidak ada hubungannya dengan pendidikan.
5. **Branding di-hardcode:** logo, nama "SPI", teks booting, palet — mengubahnya untuk pelanggan lain berarti mengubah kode.

## 2. Arsitektur target — tiga lapis

```
┌──────────────────────────────────────────────────────────────┐
│ App pelanggan (overlay)   spi_fintoedu, <pelanggan>_fintoedu │  aturan bisnis pelanggan, halaman khusus,
│                                                              │  menu tambahan, override halaman tertentu
├──────────────────────────────────────────────────────────────┤
│ App produk                finto_edu, finto_<produk lain>     │  fitur domain umum (sekolah: murid, rombel,
│                                                              │  LMS, tagihan, penilaian, ...)
├──────────────────────────────────────────────────────────────┤
│ Platform                  finto_os                           │  shell & tampilan seragam, branding, preferensi,
│                                                              │  menu registry, notifikasi, tur, FAQ, monitoring
├──────────────────────────────────────────────────────────────┤
│ Frappe / ERPNext / Education / HRMS                          │
└──────────────────────────────────────────────────────────────┘
```

- `required_apps`: `finto_edu` → `["finto_os"]`; `spi_fintoedu` → `["finto_edu"]`. Produk Ekasa non-pendidikan cukup `["finto_os"]`.
- **Aturan emas:** `finto_os` TIDAK berisi logika bisnis (tidak ada murid, SPP, guru). App produk TIDAK berisi aturan khusus satu pelanggan. App pelanggan TIDAK berisi salinan komponen tampilan.
- **Seragam secara default, kustom lewat konfigurasi:** perbedaan pelanggan diutamakan lewat **Finto OS Settings** (branding). Baru bila tidak cukup → override halaman di app pelanggan.

## 3. Isi `finto_os` — backend (Frappe app)

| Modul | Asal sekarang | Isi | Catatan migrasi |
|---|---|---|---|
| **ui_settings** | `spi_fintoedu/api/ui_settings.py` | mode tampilan global web/desktop (default global `spi_ui_mode` → ganti `finto_os_ui_mode`) | pertahankan endpoint lama sebagai *shim* (`override_whitelisted_methods` atau fungsi pembungkus) selama 1–2 rilis; patch salin default lama → baru |
| **desktop_prefs** | `spi_fintoedu/api/desktop_prefs.py` | wallpaper per user (preset / unggah, File privat), posisi ikon per user & peran (`spi_desktop_icon_layout`) | patch salin user default `spi_desktop_*` → `finto_os_desktop_*` |
| **Finto OS Settings** (DocType Single, BARU) | — (hardcode di frontend) | nama aplikasi, logo utama, logo login/pelanggan, palet (6 warna), teks booting (log lines + versi), durasi booting, wallpaper bawaan, mode bawaan, teks login ("Gunakan akun SPI Anda") | endpoint publik `get_branding()` (allow_guest, hanya data non-rahasia, di-cache) dibaca sebelum login |
| **Menu registry** | `frontend/src/assets/data/menu-catalog.ts` (mekanisme + isi) | mekanisme: grup, hub, label per peran, `when`, `pane`, `documentTypes`, rute per Role Profile | backend tidak wajib; isi menu disumbang app lewat frontend (lihat §5.3). Opsional hook Python `finto_os_menu` untuk menu yang hak aksesnya dicek server |
| **Onboarding/tur** | `spi_fintoedu/api/onboarding.py`, `features/onboarding/*` | status tur per user, PageGuide, TourGuide | konten tur (`page-tours.ts`) tetap di app pemilik halaman |
| **Notifikasi lonceng** | `spi_fintoedu/api/notifications.py`, `features/notifications/*` | daftar, tandai dibaca, badge, routing klik (`notification-route.ts`) | pemetaan DocType → rute disumbang app (registry) |
| **FAQ / Help** | `spi_fintoedu/api/faq.py` (+ `faq_seed.py`) | daftar Help Article berkelompok + cari | seed konten tetap per app |
| **Desk guard** | `spi_fintoedu/desk_guard.py` | `/app` & `/desk` hanya user Administrator; `spi_frontend_url` | jadikan pengaturan di Finto OS Settings (aktif/nonaktif, URL SPA) |
| **Activity Monitoring** | `finto_edu` (DocType `Activity Monitor *`, `services/activity_monitor*.py`, scheduler) | rekam & replay sesi | pindah utuh; hook `activity_monitoring_*` tetap. Rencanakan *rename module* DocType (Module Def) dengan patch |
| **Detail transaksi** (opsional) | `spi_fintoedu/api/transaction_detail.py` | *mekanismenya* (bentuk respons seragam + modal) | builder per DocType + aturan izin tetap di app yang memiliki aturan; finto_os menyediakan registry `finto_os_transaction_detail = {doctype: "path.builder"}` |
| **Akun** | `spi_fintoedu/api/account.py`, `features/account` | ganti password, wajib ganti password | generik → finto_os |

Yang **tidak** masuk finto_os: SPP, status murid, honor, rombel, LMS, migrasi data SPI, peran CSO/Marketing, harga, laporan cabang.

## 4. Isi `finto_os` — frontend: paket `@ekasa/finto-os-ui`

### 4.1 Isi paket
| Kelompok | File sekarang (spi_fintoedu/frontend/src) |
|---|---|
| Shell desktop | `features/desktop/**` (BootScreen, DesktopLogin, DesktopShell, DesktopWindow, WallpaperModal, appStyles, wallpapers, iconLayout, prefsApi, context, desktop.css), `stores/desktop.ts`, `stores/ui.ts` |
| Layout web | `layouts/DefaultLayout.vue` (deteksi `DESKTOP_WINDOW`), `layouts/components/*` (TopBar: tombol ganti mode), sidebar builder `helpers/menu.ts` |
| Router guard | potongan `router/index.ts` (`desktopGuard`, `DESKTOP_PASSTHROUGH`, mode web↔desktop) → ekspor `installFintoOsGuards(router, opts)` |
| Komponen | `components/HubTabs`, `PeriodFilter.vue`, `CurrencyInput.vue`, `LinkAutocomplete.vue`, `FlatPicker.vue`, `SuggestInput.vue`, `features/transactions/*` (modal + composable), `features/onboarding/*` |
| Utilitas | `helpers/http-client.ts`, `helpers/period.ts`, `composables/usePageRoute.ts`, `helpers/notification-route.ts` (mekanisme) , `stores/auth.ts` (bagian umum) |
| Gaya | token palet (§02), `assets/scss/config/_variables.scss` (abu-abu kontras AA `#64708a`), `componets/_spi-tabs.scss`, `componets/_spi-transactions.scss` → ganti prefix `_fos-*` |
| Aset | `assets/images/finto-os-logo.png` (logo utama), ikon/wallpaper bawaan |

### 4.2 Bentuk paket & distribusi
- Lokasi sumber: `apps/finto_os/frontend-kit/` (dalam repo finto_os) — satu sumber kebenaran.
- Format: library Vite (`build.lib`) **atau** dikonsumsi sebagai *source* lewat workspace (lebih sederhana untuk Vue SFC + SCSS). Rekomendasi awal: **source package** (`"exports": {"./*": "./src/*"}`) + `peerDependencies` (vue, vue-router, pinia, bootstrap, bootstrap-vue-next, sweetalert2, flatpickr) agar tidak ada dua salinan Vue.
- Konsumsi: `npm` workspace di bench (`apps/*/frontend*`) atau dependensi `file:../../finto_os/frontend-kit`. Pin versi (`"version"` di package.json kit) + CHANGELOG.
- API publik paket (contoh):
  ```ts
  import { createFintoOsApp } from "@ekasa/finto-os-ui";
  createFintoOsApp({
    appKey: "spi_fintoedu",            // namespace localStorage, prefix API override
    routes,                             // rute fitur (produk + overlay)
    menu: [...eduMenu, ...spiMenu],     // MENU_FEATURES dari tiap lapis
    hubs, pageTours, notificationRoutes,
    branding: await getBranding(),     // dari Finto OS Settings
    apiBase: { ui: "finto_os.api.ui_settings", prefs: "finto_os.api.desktop_prefs" },
  }).mount("#app");
  ```

### 4.3 Frontend produk & pelanggan
- **finto_edu/frontend** menjadi frontend dasar produk: hanya `features/` pendidikan + konfigurasi menu, memakai kit untuk segalanya yang umum.
- **spi_fintoedu** tidak lagi punya salinan penuh. Opsi (pilih satu saat proyek dimulai):
  - **(Disarankan) Overlay build-time:** `spi_fintoedu/frontend-overlay/` berisi `features/` khusus SPI, `menu.ts`, `routes.ts`, dan *override* halaman (`overrides/fees/pages/FeeListPage.vue`). Vite config produk membaca daftar overlay yang terpasang (`apps.txt` / env) → alias `@overlay/*` + plugin resolve: file overlay mengganti file produk dengan path sama. Output build ke `spi_fintoedu/public/frontend` (seperti sekarang).
  - Alternatif runtime (micro-frontend / module federation): lebih rumit, tunda.
- Aturan override: override **seminimal mungkin** dan didaftarkan di `OVERRIDES.md` app pelanggan (alasan + tanggal) agar saat produk berubah, override ditinjau.

## 5. Kontrak antar lapis

### 5.1 Hook Python (finto_os membaca dari app lain)
| Hook | Pemberi | Isi |
|---|---|---|
| `finto_os_branding_defaults` | app produk/pelanggan | default branding bila Settings kosong (mis. SPI: logo SPI di login) |
| `finto_os_transaction_detail` | app pemilik DocType | `{doctype: "dotted.path.builder"}` |
| `finto_os_notification_routes` | app | `{doctype: feature_id}` untuk klik lonceng |
| `activity_monitoring_*` | app konsumen | sudah ada di finto_edu; dipindah apa adanya |
| `finto_os_boot_log` | app produk | baris log booting tambahan ("Memuat modul Keuangan SPP") |

### 5.2 Endpoint publik finto_os (target)
`finto_os.api.branding.get_branding` (guest), `finto_os.api.ui_settings.get_ui_settings|set_ui_mode`, `finto_os.api.desktop_prefs.get_desktop_prefs|set_wallpaper_preset|upload_wallpaper|reset_wallpaper|set_icon_layout|reset_icon_layout`, `finto_os.api.onboarding.*`, `finto_os.api.notifications.*`, `finto_os.api.faq.*`, `finto_os.api.account.*`, `finto_os.api.transaction_detail.get_transaction_detail`.

### 5.3 Menu
- Kit menyediakan tipe `MenuFeature`, `MenuHub`, `MENU_GROUPS` dasar (Utama, Master Data, Keuangan, Laporan, Pengaturan Sistem, Bantuan, Portal) + fungsi `getMenuItems(ctx)`.
- Produk & overlay menyumbang `MenuFeature[]`; overlay boleh `hideFeatures: [...]` / `patchFeatures: {...}`.
- Susunan ikon desktop bawaan (Master Data dulu, jarak antar kategori) tetap di kit (`iconLayout.ts`).

## 6. Branding & kustomisasi pelanggan
Urutan prioritas nilai tampilan: **Finto OS Settings (site)** → `finto_os_branding_defaults` (app terpasang, pelanggan > produk) → default kit (palet Finto OS, logo Finto OS). Contoh SPI: logo login = logo SPI, teks "Gunakan akun SPI Anda" — saat ini hardcode di `DesktopLogin.vue`, nanti dari branding.

## 7. Tahapan pengerjaan (urut, masing-masing bisa dirilis sendiri)

| # | Tahap | Hasil | Risiko |
|---|---|---|---|
| 0 | Persiapan | repo `finto_os` (bench new-app), CI lint/test, CHANGELOG, `AGENTS.md` dengan aturan emas §2 | rendah |
| 1 | Backend platform | pindah `ui_settings`, `desktop_prefs`, `onboarding`, `notifications`, `faq`, `account`, `desk_guard` ke finto_os + shim endpoint lama + patch salin user default; DocType **Finto OS Settings** + `get_branding` | rendah (shim) |
| 2 | Kit frontend v0 | `frontend-kit` berisi shell desktop + layout + komponen §4.1 + token gaya; **SPI memakai kit** (hapus salinan lokal) — tampilan harus identik (bandingkan dengan spesifikasi 02 & snapshot) | sedang |
| 3 | finto_edu memakai kit | finto_edu mendapat mode desktop & komponen seragam; hapus duplikasi | sedang |
| 4 | Overlay SPI | ubah `spi_fintoedu/frontend` menjadi overlay di atas `finto_edu/frontend` per fitur, mengikuti tabel 04_… (A: ke kit/produk/overlay; B: gabungkan; C: pastikan tetap ada di produk) | **tinggi** — kerjakan per fitur, uji per peran |
| 5 | Activity Monitoring → finto_os | pindah DocType (Module Def), service, scheduler; patch | sedang |
| 6 | Branding penuh | semua teks/logo/warna dari Settings; uji satu pelanggan fiktif ("tanpa kustomisasi" = tampilan Finto OS murni) | rendah |

Kriteria selesai tiap tahap: test backend lulus (`bench run-tests --app finto_os` + app lain), `npm run type-check && npm run build` semua frontend, **uji visual banding** layar booting/login/desktop dengan spesifikasi 02, dokumen (`docs/` tiap app, `SPI_HANDOFF.md`) diperbarui.

## 8. Uji & jaminan "sama persis"
- Simpan **tangkapan layar acuan** (boot 0,5 s / 1,5 s / 3 s, layar kunci, form login, desktop kosong, desktop + 2 jendela, menu Start) dari versi SPI saat ini sebelum tahap 2; bandingkan (Playwright `toHaveScreenshot`, ambang kecil) setelah pindah ke kit.
- Unit test murni: `iconLayout.ts` (defaultLayout/resolveLayout/moveIcon), `period.ts`, format `CurrencyInput`.
- Backend: pindahkan `test_desktop_icon_layout.py`, test wallpaper & desk guard dari `test_help_and_access.py`.

## 9. Keputusan yang masih perlu dari pemilik (saat proyek dimulai)
1. Nama paket & repo (`finto_os`, `@ekasa/finto-os-ui`) dan lisensi.
2. Overlay build-time vs runtime (§4.3) — rekomendasi build-time.
3. Apakah mode **web** (sidebar) tetap didukung jangka panjang atau desktop jadi satu-satunya.
4. Kustomisasi yang diizinkan lewat Settings saja vs boleh override kode.
5. Kebijakan versi: semua app Ekasa wajib versi kit yang sama per rilis?

## 10. Keputusan pemilik yang sudah ada (jangan diubah tanpa konfirmasi)
- Mode tampilan global diatur Super Administrator; default **Desktop** (6 Nov 2026).
- Booting tiap muat/refresh halaman selama belum login, **tanpa tombol Lewati** (12 Nov 2026).
- Logo utama Finto OS = `finto-os-logo.png`, juga tombol Start (12 Nov 2026). Palet Finto OS (12 Nov 2026) — lihat 02.
- Jendela dibuka **ukuran normal**, bukan maximize; layar < 768 px penuh (11 Nov 2026).
- Ikon desktop dapat diseret; disimpan per user & per peran; susunan bawaan Master Data dulu + jarak antar kategori (12 Nov 2026).
- Wallpaper per user (preset atau unggahan sendiri, privat) (6 Nov 2026).
- Desk `/app` hanya user Administrator; "Lihat sebagai" hanya Administrator.
- Abu-abu tidak dipakai untuk label tombol/teks utama (kontras AA); tab berbatas; baris transaksi dapat diklik → detail.
