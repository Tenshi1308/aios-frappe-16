# Selisih frontend finto_edu vs spi_fintoedu (snapshot 12 Nov 2026)

Dibuat otomatis dengan `diff -rq finto_edu/frontend/src spi_fintoedu/frontend/src`. Kolom **Saran** = tujuan di arsitektur baru
(lihat 01_RENCANA_TEKNIS_FINTO_OS.md §5): **os** = paket finto-os-ui, **edu** = frontend produk finto_edu, **spi** = overlay pelanggan SPI.
Saran ini titik awal — putuskan per file saat migrasi.

## A. Hanya ada di spi_fintoedu (60)

| Path | Saran |
|---|---|
| `assets/data/menu-catalog.ts` | tinjau |
| `assets/data/page-tours.ts` | tinjau |
| `assets/images/finto-os-logo.png` | os |
| `assets/images/spi-logo-full.png` | tinjau |
| `assets/scss/componets/_spi-tabs.scss` | os |
| `assets/scss/componets/_spi-transactions.scss` | os |
| `components/CurrencyInput.vue` | os |
| `components/HubTabs` | os |
| `components/PeriodFilter.vue` | os |
| `components/SuggestInput.vue` | tinjau |
| `components/TheoryContent` | tinjau |
| `composables` | tinjau |
| `features/academic` | tinjau |
| `features/account` | os |
| `features/action-center` | edu? / spi |
| `features/activity-monitor` | os |
| `features/admissions/components` | tinjau |
| `features/admissions/leadFollowUpApi.ts` | tinjau |
| `features/admissions/pages/CancelRegisterPage.vue` | tinjau |
| `features/admissions/pages/TrialSchedulePage.vue` | tinjau |
| `features/auth/employment.ts` | tinjau |
| `features/calendar` | edu? / spi |
| `features/controlling` | edu? / spi |
| `features/curriculum` | edu? / spi |
| `features/dashboard/components` | tinjau |
| `features/dashboard/config/cso.ts` | tinjau |
| `features/dashboard/config/yayasan.ts` | tinjau |
| `features/data-migration` | edu? / spi |
| `features/desktop` | os |
| `features/faq` | os |
| `features/fees/components` | tinjau |
| `features/fees/pages/PaymentListPage.vue` | tinjau |
| `features/fees/pages/PaymentModeAccountPage.vue` | tinjau |
| `features/fees/pages/SppPricePage.vue` | tinjau |
| `features/follow-ups` | edu? / spi |
| `features/guardians` | edu? / spi |
| `features/guest-book` | edu? / spi |
| `features/notifications` | os |
| `features/onboarding` | os |
| `features/payroll` | edu? / spi |
| `features/reports` | edu? / spi |
| `features/rooms` | edu? / spi |
| `features/sessions` | edu? / spi |
| `features/student-documents` | edu? / spi |
| `features/student-status` | edu? / spi |
| `features/students/components/StudentLeadHistory.vue` | tinjau |
| `features/teacher-class` | tinjau |
| `features/teacher-fees` | edu? / spi |
| `features/transactions` | os |
| `features/users/components/GuestTeacherAccess.vue` | tinjau |
| `helpers/notification-route.ts` | os |
| `helpers/period.ts` | os |
| `helpers/theory-embed.ts` | tinjau |
| `router/profile-routes/cso.ts` | tinjau |
| `router/profile-routes/yayasan.ts` | tinjau |
| `stores/actionPane.ts` | tinjau |
| `stores/desktop.ts` | tinjau |
| `stores/onboarding.ts` | tinjau |
| `stores/ui.ts` | tinjau |
| `views/public` | tinjau |

## B. Ada di keduanya tetapi berbeda (56)

| Path | Saran |
|---|---|
| `App.vue` | os (gabungkan, ambil versi SPI sebagai dasar) |
| `assets/data/menu-items.ts` | mekanisme → os, isi → edu/spi |
| `assets/scss/app.scss` | os (gabungkan, ambil versi SPI sebagai dasar) |
| `assets/scss/componets/_tables.scss` | os (gabungkan, ambil versi SPI sebagai dasar) |
| `assets/scss/config/_variables.scss` | os (gabungkan, ambil versi SPI sebagai dasar) |
| `assets/scss/structure/_startbar.scss` | os (gabungkan, ambil versi SPI sebagai dasar) |
| `components/AppMenu/MenuItemLink.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/academic-master/components/AcademicMasterFormModal.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/academic-master/pages/AcademicMasterPage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/admissions/api.ts` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/admissions/pages/AdmissionListPage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/ai-settings/pages/AISettingsPage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/assessments/pages/AssessmentPage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/attendance/pages/AttendancePage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/dashboard/api.ts` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/dashboard/config/index.ts` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/dashboard/pages/DashboardPage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/employees/components/EmployeeFormModal.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/employees/pages/EmployeeListPage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/fees/api.ts` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/fees/pages/FeeListPage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/fees/pages/FeeMatrixPage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/finance-reports/api.ts` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/finance-reports/pages/FinancialStatementsPage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/institutions/components/InstitutionFormModal.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/institutions/pages/InstitutionListPage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/lms/api.ts` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/lms/pages/LMSCoursePage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/portals/pages/ParentPortalPage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/portals/pages/StudentPortalPage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/student-groups/api.ts` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/student-groups/pages/StudentGroupListPage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/students/components/StudentFormModal.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/students/types.ts` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/transfers/pages/StudentTransferPage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/users/api.ts` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/users/components/UserFormModal.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `features/users/pages/UserListPage.vue` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `helpers/constants.ts` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `helpers/http-client.ts` | os (gabungkan, ambil versi SPI sebagai dasar) |
| `helpers/menu.ts` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `layouts/DefaultLayout.vue` | os (gabungkan, ambil versi SPI sebagai dasar) |
| `layouts/components/Footer.vue` | os (gabungkan, ambil versi SPI sebagai dasar) |
| `layouts/components/LeftSideBar.vue` | os (gabungkan, ambil versi SPI sebagai dasar) |
| `layouts/components/TopBar.vue` | os (gabungkan, ambil versi SPI sebagai dasar) |
| `router/index.ts` | os (gabungkan, ambil versi SPI sebagai dasar) |
| `router/profile-routes/branch-manager.ts` | mekanisme → os, isi → edu/spi |
| `router/profile-routes/finance.ts` | mekanisme → os, isi → edu/spi |
| `router/profile-routes/index.ts` | mekanisme → os, isi → edu/spi |
| `router/profile-routes/marketing.ts` | mekanisme → os, isi → edu/spi |
| `router/profile-routes/principal.ts` | mekanisme → os, isi → edu/spi |
| `router/profile-routes/teacher.ts` | mekanisme → os, isi → edu/spi |
| `router/routes.ts` | mekanisme → os, isi → edu/spi |
| `stores/auth.ts` | os (gabungkan, ambil versi SPI sebagai dasar) |
| `types/auth.ts` | edu (bandingkan; perubahan khusus SPI → overlay spi) |
| `types/menu.ts` | edu (bandingkan; perubahan khusus SPI → overlay spi) |

## C. Hanya ada di finto_edu (2)

- `features/journal`
- `features/students/pages`
