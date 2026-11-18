# Inventaris File — dari mana ke mana

Path relatif ke `apps/`. Kolom **Tujuan** mengikuti arsitektur di `01_RENCANA_TEKNIS_FINTO_OS.md` §3–4.
`kit` = `finto_os/frontend-kit/src/…`, `os` = backend `finto_os/finto_os/…`. Salinan file per 12 Nov 2026 ada di `kode-snapshot/`.

## Backend

| Asal | Tujuan | Catatan |
|---|---|---|
| `spi_fintoedu/spi_fintoedu/api/ui_settings.py` | `os/api/ui_settings.py` | ganti default `spi_ui_mode` → `finto_os_ui_mode` (patch salin); shim endpoint lama |
| `spi_fintoedu/spi_fintoedu/api/desktop_prefs.py` | `os/api/desktop_prefs.py` | user default `spi_desktop_wallpaper`, `spi_desktop_icon_layout` → prefix `finto_os_` (patch) |
| `spi_fintoedu/spi_fintoedu/api/onboarding.py` | `os/api/onboarding.py` | |
| `spi_fintoedu/spi_fintoedu/api/notifications.py` | `os/api/notifications.py` | pemetaan DocType → fitur via hook |
| `spi_fintoedu/spi_fintoedu/api/faq.py`, `faq_seed.py` | `os/api/faq.py` | seed konten tetap per app |
| `spi_fintoedu/spi_fintoedu/api/account.py` | `os/api/account.py` | + custom field `User.custom_must_change_password` |
| `spi_fintoedu/spi_fintoedu/desk_guard.py` | `os/desk_guard.py` | pengaturan di Finto OS Settings |
| `spi_fintoedu/spi_fintoedu/api/transaction_detail.py` | mekanisme → `os/api/transaction_detail.py`; builder per DocType tetap di app pemilik | registry hook `finto_os_transaction_detail` |
| `finto_edu/finto_edu/services/activity_monitor*.py`, `api/activity_monitor.py`, DocType `Activity Monitor *` | `os/…` | pindah Module Def + scheduler `process_pending` |
| (baru) | `os/finto_os/doctype/finto_os_settings/` + `os/api/branding.py` | branding & default tampilan |
| `spi_fintoedu/spi_fintoedu/tests/test_desktop_icon_layout.py`, bagian wallpaper/desk-guard di `test_help_and_access.py` | `os/tests/` | |

## Frontend (sumber: `spi_fintoedu/frontend/src/…`)

| Asal | Tujuan |
|---|---|
| `features/desktop/**` | `kit/desktop/**` |
| `stores/desktop.ts`, `stores/ui.ts` | `kit/stores/` (API base dari opsi `createFintoOsApp`) |
| `router/index.ts` (desktopGuard, DESKTOP_PASSTHROUGH, mode switch) | `kit/router/guards.ts` |
| `router/routes.ts` (rute `desktop.boot`, `desktop.login`, `desktop.home`) | `kit/router/routes.ts` |
| `layouts/DefaultLayout.vue`, `layouts/components/*` | `kit/layouts/` |
| `components/HubTabs`, `PeriodFilter.vue`, `CurrencyInput.vue`, `LinkAutocomplete.vue`, `FlatPicker.vue`, `SuggestInput.vue` | `kit/components/` |
| `features/transactions/*` | `kit/transactions/` |
| `features/onboarding/*`, `stores/onboarding.ts` | `kit/onboarding/` |
| `features/notifications/*`, `helpers/notification-route.ts` | `kit/notifications/` |
| `features/account/*` | `kit/account/` |
| `features/activity-monitor/tracker.ts` (+ halaman monitor & replay) | `kit/activity-monitor/` |
| `helpers/http-client.ts`, `helpers/period.ts`, `helpers/menu.ts`, `composables/usePageRoute.ts` | `kit/helpers/` |
| `assets/data/menu-catalog.ts` | tipe & mekanisme → `kit/menu/`; isi → `finto_edu` (fitur umum) + `spi_fintoedu` (fitur & peran SPI) |
| `assets/data/page-tours.ts` | mekanisme → kit; konten tetap per app |
| `assets/scss/config/_variables.scss` (abu-abu `#64708a`), `componets/_spi-tabs.scss`, `componets/_spi-transactions.scss` | `kit/styles/` (prefix `_fos-`) + token palet `--fos-*` |
| `assets/images/finto-os-logo.png` | `kit/assets/` |
| `index.html` (kelas `os-mode`, splash) | template `kit/index.html` |

Fitur domain yang **tidak** ke kit (tetap di produk/overlay): students, student-status, fees, spp, reports, controlling, teacher-fees, sessions, action-center, follow-ups, curriculum, data-migration, payroll, admissions, guest-book, guardians, rooms, calendar (calendar: pertimbangkan kit bila produk lain butuh).

## Daftar isi `kode-snapshot/`
- `spi_fintoedu/docs/FRONTEND_GUIDELINES.md`
- `spi_fintoedu/docs/specs/MENU_AND_HELP.md`
- `spi_fintoedu/docs/specs/TRANSACTION_DETAIL.md`
- `spi_fintoedu/frontend/index.html`
- `spi_fintoedu/frontend/package.json`
- `spi_fintoedu/frontend/src/assets/data/menu-catalog.ts`
- `spi_fintoedu/frontend/src/assets/data/menu-items.ts`
- `spi_fintoedu/frontend/src/assets/data/page-tours.ts`
- `spi_fintoedu/frontend/src/assets/images/finto-os-logo.png`
- `spi_fintoedu/frontend/src/assets/images/spi-logo-full.png`
- `spi_fintoedu/frontend/src/assets/scss/app.scss`
- `spi_fintoedu/frontend/src/assets/scss/componets/_spi-tabs.scss`
- `spi_fintoedu/frontend/src/assets/scss/componets/_spi-transactions.scss`
- `spi_fintoedu/frontend/src/assets/scss/config/_variables.scss`
- `spi_fintoedu/frontend/src/components/CurrencyInput.vue`
- `spi_fintoedu/frontend/src/components/FlatPicker.vue`
- `spi_fintoedu/frontend/src/components/HubTabs/HubTabs.vue`
- `spi_fintoedu/frontend/src/components/LinkAutocomplete.vue`
- `spi_fintoedu/frontend/src/components/PeriodFilter.vue`
- `spi_fintoedu/frontend/src/components/SuggestInput.vue`
- `spi_fintoedu/frontend/src/composables/usePageRoute.ts`
- `spi_fintoedu/frontend/src/features/account/ChangePasswordModal.vue`
- `spi_fintoedu/frontend/src/features/account/api.ts`
- `spi_fintoedu/frontend/src/features/action-center/components/ActionPane.vue`
- `spi_fintoedu/frontend/src/features/activity-monitor/tracker.ts`
- `spi_fintoedu/frontend/src/features/desktop/appStyles.ts`
- `spi_fintoedu/frontend/src/features/desktop/components/DesktopWindow.vue`
- `spi_fintoedu/frontend/src/features/desktop/components/WallpaperModal.vue`
- `spi_fintoedu/frontend/src/features/desktop/context.ts`
- `spi_fintoedu/frontend/src/features/desktop/desktop.css`
- `spi_fintoedu/frontend/src/features/desktop/iconLayout.ts`
- `spi_fintoedu/frontend/src/features/desktop/pages/BootScreen.vue`
- `spi_fintoedu/frontend/src/features/desktop/pages/DesktopLogin.vue`
- `spi_fintoedu/frontend/src/features/desktop/pages/DesktopShell.vue`
- `spi_fintoedu/frontend/src/features/desktop/prefsApi.ts`
- `spi_fintoedu/frontend/src/features/desktop/wallpapers.ts`
- `spi_fintoedu/frontend/src/features/notifications/api.ts`
- `spi_fintoedu/frontend/src/features/onboarding/api.ts`
- `spi_fintoedu/frontend/src/features/onboarding/components/PageGuide.vue`
- `spi_fintoedu/frontend/src/features/onboarding/components/TourGuide.vue`
- `spi_fintoedu/frontend/src/features/transactions/TransactionDetailModal.vue`
- `spi_fintoedu/frontend/src/features/transactions/api.ts`
- `spi_fintoedu/frontend/src/features/transactions/useTransactionDetail.ts`
- `spi_fintoedu/frontend/src/helpers/http-client.ts`
- `spi_fintoedu/frontend/src/helpers/menu.ts`
- `spi_fintoedu/frontend/src/helpers/notification-route.ts`
- `spi_fintoedu/frontend/src/helpers/period.ts`
- `spi_fintoedu/frontend/src/layouts/DefaultLayout.vue`
- `spi_fintoedu/frontend/src/layouts/components/TopBar.vue`
- `spi_fintoedu/frontend/src/router/index.ts`
- `spi_fintoedu/frontend/src/router/routes.ts`
- `spi_fintoedu/frontend/src/stores/auth.ts`
- `spi_fintoedu/frontend/src/stores/desktop.ts`
- `spi_fintoedu/frontend/src/stores/onboarding.ts`
- `spi_fintoedu/frontend/src/stores/ui.ts`
- `spi_fintoedu/frontend/vite.config.ts`
- `spi_fintoedu/spi_fintoedu/api/account.py`
- `spi_fintoedu/spi_fintoedu/api/desktop_prefs.py`
- `spi_fintoedu/spi_fintoedu/api/faq.py`
- `spi_fintoedu/spi_fintoedu/api/notifications.py`
- `spi_fintoedu/spi_fintoedu/api/onboarding.py`
- `spi_fintoedu/spi_fintoedu/api/transaction_detail.py`
- `spi_fintoedu/spi_fintoedu/api/ui_settings.py`
- `spi_fintoedu/spi_fintoedu/desk_guard.py`
- `spi_fintoedu/spi_fintoedu/faq_seed.py`
- `spi_fintoedu/spi_fintoedu/tests/test_desktop_icon_layout.py`
