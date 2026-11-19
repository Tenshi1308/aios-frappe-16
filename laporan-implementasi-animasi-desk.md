# Laporan Implementasi Animasi Seluruh Finto Desk

**Tanggal:** 20 November 2026  
**Acuan:** [laporan-investigasi-animasi-desk.md](laporan-investigasi-animasi-desk.md) (Bagian 3 & Bagian 4)  
**Status:** Implementasi selesai; build frontend dan seluruh suite tes lolos; siap commit lokal (tanpa push).

---

## 1. Daftar File yang Diubah & Ditambahkan

### File Baru
- `frontend/src/components/base/AccordionTransition.vue` — komponen transisi `<Transition :css="false">` bersama untuk animasi buka/tutup accordion (`height` + `opacity` memakai `var(--dur-20)` / `var(--dur-18)` / `var(--dur-15)` serta memeriksa `prefers-reduced-motion`).

### File Diubah (`21` file)
1. `frontend/src/styles/base.css` — penambahan animasi/transisi pola lama pada elemen statis per permukaan, definisi pola baru (animasi keluar `<Transition>`, `errorShake`, `micRipple`, `skeletonShimmer`/`.is-loading`, `slideInLeft`/`slideOutLeft`, `t-win-close`, `t-sidebar-left`, `t-tab`, `.ap-geo-anim`, `.win-geo-anim`), promosi `.spin` + `@keyframes settings-spin` menjadi kelas bersama, dan aturan `@media (prefers-reduced-motion: reduce)`.
2. `frontend/src/App.vue` — membungkus pergantian fase layar (`BootScreen`, `DesktopView`, `RegisterView`, `PendingView`, `LoginView`) dengan `<Transition name="t-screen">`.
3. `frontend/src/views/DesktopView.vue` — membungkus `StartMenu`/`SearchFlyout` dengan `<Transition name="t-flyout">` dan `AgentPanel` dengan `<Transition name="t-panel-right">`.
4. `frontend/src/views/PendingView.vue` — menambahkan kelas `pending-avatar` pada `.avatar.xl` untuk pola `breathe`.
5. `frontend/src/composables/useWindowManager.ts` — menambahkan state reaktif `interacting` (`true` saat `startDrag`/`startResize`, `false` saat `pointerup`/`pointercancel`) agar transisi geometri maximize/restore tidak mengganggu drag/resize.
6. `frontend/src/components/shell/WindowHost.vue` — membungkus daftar jendela dengan `<TransitionGroup name="t-win-close" tag="div" class="win-layer">`, tiap slot dengan `.win-slot`, `<Transition name="t-win" appear>` pada `.win` (`v-show="!w.min"`), dan kelas kondisional `win-geo-anim` saat `!wm.interacting.value`.
7. `frontend/src/components/shell/Taskbar.vue` — `<TransitionGroup name="t-tb-app">` untuk tombol app taskbar, `<Transition name="t-pop">` untuk `.bell-badge`, serta transisi hover + press scale pada `.tray.bell`.
8. `frontend/src/components/shell/StartMenu.vue` — `<Transition name="t-pop-up">` untuk `.power-menu`.
9. `frontend/src/components/shell/SearchFlyout.vue` — kelas `.is-loading` pada `.empty-note` saat `modules.searchLoading`.
10. `frontend/src/components/base/Toasts.vue` — `<TransitionGroup name="t-toast" tag="div" class="toasts">` untuk masuk/keluar dan pergeseran tumpukan toast.
11. `frontend/src/components/base/PopoverMenu.vue` — `<Transition name="t-pop">` untuk animasi masuk/keluar `.ap-popover-menu`.
12. `frontend/src/components/agent/AgentPanel.vue` — state `resizing` + `ap-geo-anim` untuk transisi fullscreen, `<Transition :name="isWideMode ? 't-sidebar-left' : 't-slide-left'">` untuk sidebar/overlay riwayat, `<AccordionTransition>` untuk `.ap-history-list` dan `.trace-steps`, `<Transition name="t-pop-up">` untuk `.ap-context-popover`, dan `.is-loading` pada indikator muat riwayat.
13. `frontend/src/components/agent/AgentStep.vue` — `<AccordionTransition>` membungkus `.as-sub` + `.as-body` dan `transition: background var(--dur-15) ease` pada `.as-head`.
14. `frontend/src/components/domain/DomainWindow.vue` — kelas `.spin` pada `<AppIcon name="refresh">` saat `loading` dan `.is-loading` pada `.domain-state`.
15. `frontend/src/components/module/ModuleWindow.vue` — kelas `.spin` pada `<AppIcon name="refresh">` saat `loading`, `.is-loading` pada `.mod-state` saat loading, serta transisi & animasi scoped (`.mod-refresh`, `.mod-error`, `.mod-filter-error`, `.mod-card`, `.mod-filter-field input`, `.mod-table`).
16. `frontend/src/components/windows/ApprovalCardWindow.vue` — `.is-loading` pada `.ac-note` saat loading, `<Transition name="t-pop-up">` pada tombol `Konfirmasi Penolakan`, serta animasi/transisi scoped (`.ac-meta`, `.ac-section`, `.ac-json`, `.ac-fallback`, `.ac-expired-badge`, `.ac-table`, `.ac-result.fail`, `.ac-actions textarea`).
17. `frontend/src/components/windows/ArtifactWindow.vue` — `.is-loading` pada `.aw-note` saat loading serta animasi/transisi scoped (`.aw-meta`, `.aw-note`, `.aw-error`, `.aw-frame`, `.aw-table-wrap`, `.aw-md`, `.aw-download`).
18. `frontend/src/components/windows/ChannelFlagsWindow.vue` — `<TransitionGroup name="t-list" tag="ul" class="cf-list">`, `.is-loading` pada `.cf-empty` saat loading, serta transisi tombol & `errorShake` pada `.cf-error`.
19. `frontend/src/components/windows/FilesWindow.vue` — `.spin` pada `<AppIcon name="refresh">`, `<AccordionTransition>` pada `.files-tree-conversations`, `.is-loading` saat memuat, serta transisi baris & tree folder.
20. `frontend/src/components/windows/PendingDraftsWindow.vue` — `.is-loading` pada `.pd-empty`, `<Transition name="t-pop" mode="out-in">` pada konfirmasi tutup inline, transisi garis indikator `.pd-tab::after`, transisi `.pd-subfilter`/tombol, `rise2` pada `.pd-item`, dan `errorShake` pada `.pd-error`.
21. `frontend/src/components/windows/SettingsWindow.vue` — `<Transition name="t-tab" mode="out-in">` pada pergantian panel tab, `.is-loading` pada `.settings-state`/`.tg-loading`, menghapus duplikasi `@keyframes settings-spin`/`.spin` (memakai definisi bersama di `base.css`), serta menambah `errorShake`, `winIn`, `rise2`, transisi input/tombol staf, dan press scale `:active`.

---

## 2. Pola yang Dipakai per Permukaan

Seluruh durasi memakai token yang sudah ada di `frontend/src/styles/tokens.css` (`--dur-12`, `--dur-15`, `--dur-18`, `--dur-20`, `--dur-22`, `--dur-30`, `--dur-40`, `--dur-45`, `--dur-90`, `--dur-110`, `--dur-240`) tanpa warna literal (hanya CSS variable).

| Permukaan | Pola Lama yang Dipakai | Pola Baru yang Ditambahkan |
|---|---|---|
| **Boot** (`BootScreen.vue`, `App.vue`) | `rise2` (`.boot-finto-name`, `.boot-word`, `.boot-log li`), `fade` (`.boot-bar`, `.boot-status-row`, `.boot-status`), `breathe` (`.boot-skip`), plus animasi boot bawaan. | `t-screen` (`fade` / `fadeOut`) di `App.vue` agar keluar layar boot halus. |
| **LockScreen / Login / Register / Pending** | `fade` (`.lock`, `.lock-foot`), `rise2` (`.lock-clock`), `winIn` (`.lock-card`), `breathe` (`.pending-avatar`), `trace-pulse` (`.dot.ok`), transisi `--dur-15` (`.lock-field`, `.lock-go`, `.btn`, `.lock-link`). | `errorShake` (`.lock-error`), press scale `:active` (`.lock-go`, `.btn`). |
| **Desktop** (`DesktopView.vue`) | `fade` (`.desktop.wall`, `.desk-hint`, `.desk-banner`), transisi `--dur-15` (`.desk-icon`). | Press scale `:active` (`.desk-icon`), `t-flyout`, `t-panel-right`. |
| **Taskbar** (`Taskbar.vue`) | `rise2` (`.taskbar`), `trace-pulse` (`.dot.ok`), transisi `--dur-15` (`.tb-site`, `.tb-btn`, `.tb-btn.app::after`, `.tb-search`, `.tray`, `.clock`, `.tray.bell`). | `t-tb-app` (`winIn`/`winOut`), `t-pop` (`.bell-badge`), press scale `:active` (`.tb-btn`, `.tray.bell`). |
| **StartMenu & SearchFlyout** | `rise` (`.flyout`), `fade` (`.empty-note`), transisi `--dur-15` (`.fl-search`, `.mod`, `.agent-pill`, `.power-menu button`, `.fl-input`, `.chip`, `.sr-item`). | `t-flyout` (`rise`/`flyoutOut`), `t-pop-up` (`.power-menu`), `.is-loading` shimmer, press scale `:active` (`.mod`, `.agent-pill`, `.chip`). |
| **WindowHost** (`WindowHost.vue`, `useWindowManager.ts`) | `winIn` (buka/restore), transisi `--dur-15` (`.win` box-shadow, `.win-title`, `.win-ctrls button`). | `t-win` (`winIn`/`winOut` pada `v-show`), `t-win-close` (penutupan jendela pada `<TransitionGroup>`), `.win-geo-anim` untuk transisi maximize/restore non-drag. |
| **Windows (`components/windows/*`, `DomainWindow`, `ModuleWindow`)** | `fade`, `rise2`, `winIn`, `breathe`, `settings-spin` (`.spin`), transisi `--dur-15` / `--dur-20`, pola indikator garis `--dur-15` (`.pd-tab::after`). | `.is-loading` (`skeletonShimmer`), `errorShake` (`.ac-result.fail`, `.aw-error`, `.cf-error`, `.files-error`, `.pd-error`, `.settings-error`, `.tg-error`, `.persona-error`, `.domain-error`, `.mod-error`, `.mod-filter-error`), `<AccordionTransition>` (`FilesWindow`), `t-list` (`ChannelFlagsWindow`), `t-tab` (`SettingsWindow`), `t-pop` (`PendingDraftsWindow`), `t-pop-up` (`ApprovalCardWindow`), press scale `:active`. |
| **Panel Chat Agent** (`AgentPanel.vue`, `AgentStep.vue`) | `slideIn`, `blink`, `as-blink`, `trace-pulse`, `rise2`, `winIn`, `width var(--dur-12) linear` (`.ap-file .bar i`), transisi `--dur-12` / `--dur-15`. | `t-panel-right` (masuk/keluar panel), `ap-geo-anim` (transisi fullscreen non-resize), `t-slide-left` (`slideInLeft`/`slideOutLeft`) & `t-sidebar-left` (sidebar riwayat), `<AccordionTransition>` (`.ap-history-list`, `.trace-steps`, `.as-collapse`), `details::details-content` (`.ap-referral-details`), `micRipple` (`.icon-btn.listening::after`), `t-pop-up` (`.ap-context-popover`), `errorShake` (`.ap-history-error`), `.is-loading`, press scale `:active`. |
| **Toasts** (`Toasts.vue`) | `rise2` (masuk `.toast`). | `t-toast` (`rise2`/`riseOut` + `t-toast-move` pergeseran tumpukan). |
| **PopoverMenu** (`PopoverMenu.vue`) | Transisi hover `--dur-15` (`.ap-popover-menu button`). | `t-pop` (`winIn`/`winOut`). |
| **Aksesibilitas (`prefers-reduced-motion: reduce`)** | Aturan global `--dur-instant` di `base.css:2313-2321` dan `animation: none` boot. | Menonaktifkan semua animasi kontinu/spasial baru (`.boot-skip`, `.dot.ok`, `.pending-avatar`, `.icon-btn.listening::after`, `.is-loading`, `.spin`, `errorShake`), menonaktifkan `:active` scale, serta guard JS di `AccordionTransition.vue` dan `@media (prefers-reduced-motion: no-preference)` pada `details::details-content`. |

---

## 3. Hasil Build & Tes

Semua pemeriksaan dijalankan setelah edit terakhir dan seluruhnya lolos tanpa perubahan berkas tes:

| Pemeriksaan | Perintah | Hasil |
|---|---|---|
| Frontend typecheck & build | `cd frontend && npm run build` (`vue-tsc --noEmit && vite build`) | **Lolos** — `✓ 156 modules transformed`, built dalam `3.41s`, exit code `0`. |
| Kontrak statis anti-hardcode | `pytest -q aios_v1/tests/test_frontend_no_hardcode.py` | **Lolos** — `25 passed in 0.09s`. |
| Draft manager | `bench --site aios-v16.localhost run-tests --app aios_v1 --module aios_v1.tests.test_draft_manager` | **Lolos** — `Ran 12 tests in 1.973s — OK`. |
| Authz dispatcher | `bench --site aios-v16.localhost run-tests --app aios_v1 --module aios_v1.tests.test_authz_dispatcher` | **Lolos** — `Ran 18 tests in 6.668s — OK`. |
| Authz user isolation | `bench --site aios-v16.localhost run-tests --app aios_v1 --module aios_v1.tests.test_authz_user_isolation` | **Lolos** — `Ran 8 tests in 2.438s — OK`. |
| Authz write | `bench --site aios-v16.localhost run-tests --app aios_v1 --module aios_v1.tests.test_authz_write` | **Lolos** — `Ran 6 tests in 2.844s — OK`. |

*(Catatan: verifikasi visual gerakan di browser nyata tidak dijalankan otomatis dan dapat diamati langsung oleh Ten pada build frontend.)*
