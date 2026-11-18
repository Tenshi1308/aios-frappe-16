import { roleProfileRoutes } from "@/router/profile-routes";

const setTitle = (title: string) => {
  return title ? `${title} | SPI Digital System` : "SPI Digital System";
};

const authRoutes = [
  {
    path: "/auth/sign-in",
    name: "auth.sign-in",
    meta: {
      title: setTitle("Sign In"),
    },
    component: () => import("@/views/auth/login.vue"),
  },
  {
    path: "/auth/register",
    name: "auth.register",
    meta: {
      title: setTitle("Register"),
    },
    component: () => import("@/views/auth/register.vue"),
  },
  {
    path: "/auth/reset-pass",
    name: "auth.reset-pass",
    meta: {
      title: setTitle("Reset Password"),
    },
    component: () => import("@/views/auth/reset-pass.vue"),
  },
  {
    path: "/auth/lock-screen",
    name: "auth.lock-screen",
    meta: {
      title: setTitle("Lock Screen"),
    },
    component: () => import("@/views/auth/lock-screen.vue"),
  },
  {
    path: "/auth/maintenance",
    name: "auth.maintenance",
    meta: {
      title: setTitle("Maintenance"),
    },
    component: () => import("@/views/auth/maintenance.vue"),
  },
  // Mode desktop (Finto OS): animasi booting & layar login gaya OS.
  {
    path: "/boot",
    name: "desktop.boot",
    meta: { title: setTitle("Finto OS") },
    component: () => import("@/features/desktop/pages/BootScreen.vue"),
  },
  {
    path: "/desktop/login",
    name: "desktop.login",
    meta: { title: setTitle("Masuk") },
    component: () => import("@/features/desktop/pages/DesktopLogin.vue"),
  },
  {
    path: "/registers",
    name: "public.registers",
    meta: {
      title: setTitle("Pendaftaran Siswa Baru (PPDB Online)"),
    },
    component: () => import("@/views/public/RegistersPage.vue"),
  },
];

const errorRoutes = [
  {
    path: "/auth/error-404",
    name: "error.404",
    meta: {
      title: setTitle("Error 404"),
    },
    component: () => import("@/views/auth/error-404.vue"),
  },
  {
    path: "/auth/error-500",
    name: "error.500",
    meta: {
      title: setTitle("Error 500"),
    },
    component: () => import("@/views/auth/error-500.vue"),
  },
  {
    path: "/:catchAll(.*)",
    redirect: "/auth/error-404",
  },
];

const dashboardRoutes = [
  {
    path: "/",
    name: "home",
    meta: {
      title: setTitle("Dashboard"),
      authRequired: true,
    },
    component: () => import("@/layouts/components/Loading.vue"),
  },
  {
    path: "/dashboard/administrator",
    name: "dashboard.administrator",
    meta: {
      title: setTitle("Dashboard Admin"),
      authRequired: true,
      systemManagerOnly: true,
    },
    component: () => import("@/features/dashboard/pages/DashboardPage.vue"),
    props: { variant: "administrator" },
  },
  {
    path: "/dashboard/unassigned",
    name: "dashboard.unassigned",
    meta: {
      title: setTitle("Dashboard"),
      authRequired: true,
    },
    component: () => import("@/features/dashboard/pages/DashboardPage.vue"),
    props: { variant: "unassigned" },
  },
  {
    path: "/desktop",
    name: "desktop.home",
    meta: { title: setTitle("Desktop"), authRequired: true },
    component: () => import("@/features/desktop/pages/DesktopShell.vue"),
  },
  {
    path: "/faq",
    name: "help.faq",
    meta: {
      title: setTitle("FAQ & Pusat Bantuan"),
      authRequired: true,
    },
    component: () => import("@/features/faq/pages/FaqPage.vue"),
  },
  {
    path: "/calendar",
    name: "calendar",
    meta: {
      title: setTitle("Kalender"),
      authRequired: true,
    },
    component: () => import("@/features/calendar/pages/CalendarPage.vue"),
  },
  ...roleProfileRoutes,
];

const administratorRoutes = [
  {
    path: "/administrator/users",
    name: "administrator.users",
    meta: {
      title: setTitle("User"),
      authRequired: true,
      systemManagerOnly: true,
    },
    component: () => import("@/features/users/pages/UserListPage.vue"),
  },
  {
    path: "/administrator/institutions",
    name: "administrator.institutions",
    meta: {
      title: setTitle("Institusi"),
      authRequired: true,
      systemManagerOnly: true,
    },
    component: () =>
      import("@/features/institutions/pages/InstitutionListPage.vue"),
  },
  {
    path: "/administrator/migration",
    name: "administrator.migration",
    meta: {
      title: setTitle("Migrasi Data"),
      authRequired: true,
      systemManagerOnly: true,
    },
    component: () =>
      import("@/features/data-migration/pages/DataMigrationPage.vue"),
  },
  // Activity Monitoring & Session Replay (core finto_edu): hanya user Administrator, tidak saat "Lihat sebagai".
  {
    path: "/administrator/activity-monitor",
    name: "administrator.activity-monitor",
    meta: {
      title: setTitle("Monitoring Aktivitas"),
      authRequired: true,
      systemManagerOnly: true,
      superAdministratorOnly: true,
    },
    component: () =>
      import("@/features/activity-monitor/pages/ActivityMonitorPage.vue"),
  },
  {
    path: "/administrator/session-replay",
    name: "administrator.session-replay",
    meta: {
      title: setTitle("Session Replay"),
      authRequired: true,
      systemManagerOnly: true,
      superAdministratorOnly: true,
    },
    component: () =>
      import("@/features/activity-monitor/pages/SessionReplayPage.vue"),
  },
  {
    path: "/administrator/ai-settings",
    name: "administrator.ai-settings",
    meta: {
      title: setTitle("Konfigurasi AI Assistant"),
      authRequired: true,
      systemManagerOnly: true,
    },
    component: () =>
      import("@/features/ai-settings/pages/AISettingsPage.vue"),
  },
];

const appRoutes = [
  // Analytics
  {
    path: "/apps/analytics/customers",
    name: "apps.analytics.customers",
    meta: {
      title: setTitle("Customers"),
      authRequired: true,
    },
    component: () => import("@/views/apps/analytics/customers/index.vue"),
  },
  {
    path: "/apps/analytics/reports",
    name: "apps.analytics.reports",
    meta: {
      title: setTitle("Reports"),
      authRequired: true,
    },
    component: () => import("@/views/apps/analytics/reports/index.vue"),
  },

  // Projects
  {
    path: "/apps/projects/clients",
    name: "apps.projects.clients",
    meta: {
      title: setTitle("Clients"),
      authRequired: true,
    },
    component: () => import("@/views/apps/projects/clients/index.vue"),
  },
  {
    path: "/apps/projects/team",
    name: "apps.projects.team",
    meta: {
      title: setTitle("Team"),
      authRequired: true,
    },
    component: () => import("@/views/apps/projects/team/index.vue"),
  },
  {
    path: "/apps/projects/project",
    name: "apps.projects.project",
    meta: {
      title: setTitle("Project"),
      authRequired: true,
    },
    component: () => import("@/views/apps/projects/project/index.vue"),
  },
  {
    path: "/apps/projects/task",
    name: "apps.projects.task",
    meta: {
      title: setTitle("Task"),
      authRequired: true,
    },
    component: () => import("@/views/apps/projects/task/index.vue"),
  },
  {
    path: "/apps/projects/kanban",
    name: "apps.projects.kanban",
    meta: {
      title: setTitle("Kanban Board"),
      authRequired: true,
    },
    component: () => import("@/views/apps/projects/kanban/index.vue"),
  },
  {
    path: "/apps/projects/users",
    name: "apps.projects.users",
    meta: {
      title: setTitle("Users"),
      authRequired: true,
    },
    component: () => import("@/views/apps/projects/users/index.vue"),
  },
  {
    path: "/apps/projects/create",
    name: "apps.projects.create",
    meta: {
      title: setTitle("Create"),
      authRequired: true,
    },
    component: () => import("@/views/apps/projects/create/index.vue"),
  },

  // Ecommerce
  {
    path: "/apps/ecommerce/products",
    name: "apps.ecommerce.products",
    meta: {
      title: setTitle("Products"),
      authRequired: true,
    },
    component: () => import("@/views/apps/ecommerce/products/index.vue"),
  },
  {
    path: "/apps/ecommerce/customers",
    name: "apps.ecommerce.customers",
    meta: {
      title: setTitle("Customers"),
      authRequired: true,
    },
    component: () => import("@/views/apps/ecommerce/customers/index.vue"),
  },
  {
    path: "/customers/:id",
    name: "ecommerce.customers.details",
    params: { id: "3001" },
    meta: {
      title: setTitle("Customers Details"),
      authRequired: true,
    },
    component: () => import("@/views/apps/ecommerce/customers/[id]/index.vue"),
  },
  {
    path: "/apps/ecommerce/orders",
    name: "apps.ecommerce.orders",
    meta: {
      title: setTitle("Orders"),
      authRequired: true,
    },
    component: () => import("@/views/apps/ecommerce/orders/index.vue"),
  },
  {
    path: "/orders/:id",
    name: "ecommerce.orders.details",
    params: { id: "3001" },
    meta: {
      title: setTitle("Orders Details"),
      authRequired: true,
    },
    component: () => import("@/views/apps/ecommerce/orders/[id]/index.vue"),
  },
  {
    path: "/apps/ecommerce/refunds",
    name: "apps.ecommerce.refunds",
    meta: {
      title: setTitle("Refunds"),
      authRequired: true,
    },
    component: () => import("@/views/apps/ecommerce/refunds/index.vue"),
  },

  {
    path: "/apps/chat",
    name: "apps.chat",
    meta: {
      title: setTitle("Chat"),
      authRequired: true,
    },
    component: () => import("@/views/apps/chat/index.vue"),
  },
  {
    path: "/apps/contacts",
    name: "apps.contacts",
    meta: {
      title: setTitle("Contacts"),
      authRequired: true,
    },
    component: () => import("@/views/apps/contacts/index.vue"),
  },
  {
    path: "/apps/calendar",
    name: "apps.calendar",
    meta: {
      title: setTitle("Help"),
      authRequired: true,
    },
    component: () => import("@/views/apps/calendar/index.vue"),
  },
  {
    path: "/apps/invoice",
    name: "apps.invoice",
    meta: {
      title: setTitle("Invoice"),
      authRequired: true,
    },
    component: () => import("@/views/apps/invoice/index.vue"),
  },
];

const emailtemplatesRoutes = [
  {
    path: "/email-templates/basic",
    name: "email-templates.basic",
    meta: {
      title: setTitle("Basic Email Templates"),
      authRequired: true,
    },
    component: () => import("@/views/email-templates/basic.vue"),
  },
  {
    path: "/email-templates/alert",
    name: "email-templates.alert",
    meta: {
      title: setTitle("Alert Email Templates"),
      authRequired: true,
    },
    component: () => import("@/views/email-templates/alert.vue"),
  },
  {
    path: "/email-templates/billing",
    name: "email-templates.billing",
    meta: {
      title: setTitle("Billing Email Templates"),
      authRequired: true,
    },
    component: () => import("@/views/email-templates/billing.vue"),
  },
];

const pagesRoutes = [
  {
    path: "/pages/profile",
    name: "pages.profile",
    meta: {
      title: setTitle("Profile"),
      authRequired: true,
    },
    component: () => import("@/views/pages/profile/index.vue"),
  },
  {
    path: "/pages/notifications",
    name: "pages.notifications",
    meta: {
      title: setTitle("Notifications"),
      authRequired: true,
    },
    component: () => import("@/views/pages/notifications/index.vue"),
  },
  {
    path: "/pages/timeline",
    name: "pages.timeline",
    meta: {
      title: setTitle("Timeline"),
      authRequired: true,
    },
    component: () => import("@/views/pages/timeline/index.vue"),
  },
  {
    path: "/pages/tree-view",
    name: "pages.tree-view",
    meta: {
      title: setTitle("Treeview"),
      authRequired: true,
    },
    component: () => import("@/views/pages/treeview/index.vue"),
  },
  {
    path: "/pages/starter",
    name: "pages.starter",
    meta: {
      title: setTitle("Starter"),
      authRequired: true,
    },
    component: () => import("@/views/pages/starter/index.vue"),
  },
  {
    path: "/pages/pricing",
    name: "pages.pricing",
    meta: {
      title: setTitle("Pricing"),
      authRequired: true,
    },
    component: () => import("@/views/pages/pricing/index.vue"),
  },
  {
    path: "/pages/blogs",
    name: "pages.blogs",
    meta: {
      title: setTitle("Blogs"),
      authRequired: true,
    },
    component: () => import("@/views/pages/blogs/index.vue"),
  },
  {
    path: "/pages/faqs",
    name: "pages.faqs",
    meta: {
      title: setTitle("FAQs"),
      authRequired: true,
    },
    component: () => import("@/views/pages/faqs/index.vue"),
  },
  {
    path: "/pages/gallery",
    name: "pages.gallery",
    meta: {
      title: setTitle("Gallery"),
      authRequired: true,
    },
    component: () => import("@/views/pages/gallery/index.vue"),
  },
];

const uiRoutes = [
  {
    path: "/ui/alerts",
    name: "ui.alerts",
    meta: {
      title: setTitle("Alerts"),
      authRequired: true,
    },
    component: () => import("@/views/ui/alerts.vue"),
  },
  {
    path: "/ui/avatars",
    name: "ui.avatars",
    meta: {
      title: setTitle("Avatars"),
      authRequired: true,
    },
    component: () => import("@/views/ui/avatars.vue"),
  },
  {
    path: "/ui/buttons",
    name: "ui.buttons",
    meta: {
      title: setTitle("Buttons"),
      authRequired: true,
    },
    component: () => import("@/views/ui/buttons.vue"),
  },
  {
    path: "/ui/badges",
    name: "ui.badges",
    meta: {
      title: setTitle("Badges"),
      authRequired: true,
    },
    component: () => import("@/views/ui/badges.vue"),
  },
  {
    path: "/ui/cards",
    name: "ui.cards",
    meta: {
      title: setTitle("Cards"),
      authRequired: true,
    },
    component: () => import("@/views/ui/cards.vue"),
  },
  {
    path: "/ui/carousel",
    name: "ui.carousel",
    meta: {
      title: setTitle("Carousel"),
      authRequired: true,
    },
    component: () => import("@/views/ui/carousel.vue"),
  },
  {
    path: "/ui/dropdowns",
    name: "ui.dropdowns",
    meta: {
      title: setTitle("Dropdowns"),
      authRequired: true,
    },
    component: () => import("@/views/ui/dropdowns.vue"),
  },
  {
    path: "/ui/grids",
    name: "ui.grids",
    meta: {
      title: setTitle("Grids"),
      authRequired: true,
    },
    component: () => import("@/views/ui/grids.vue"),
  },
  {
    path: "/ui/images",
    name: "ui.images",
    meta: {
      title: setTitle("images"),
      authRequired: true,
    },
    component: () => import("@/views/ui/images.vue"),
  },
  {
    path: "/ui/list",
    name: "ui.list",
    meta: {
      title: setTitle("Lists"),
      authRequired: true,
    },
    component: () => import("@/views/ui/list.vue"),
  },
  {
    path: "/ui/modals",
    name: "ui.modals",
    meta: {
      title: setTitle("Modals"),
      authRequired: true,
    },
    component: () => import("@/views/ui/modals.vue"),
  },
  {
    path: "/ui/navs",
    name: "ui.navs",
    meta: {
      title: setTitle("Navs"),
      authRequired: true,
    },
    component: () => import("@/views/ui/navs.vue"),
  },
  {
    path: "/ui/navbar",
    name: "ui.navbar",
    meta: {
      title: setTitle("Navbar"),
      authRequired: true,
    },
    component: () => import("@/views/ui/navbar.vue"),
  },
  {
    path: "/ui/paginations",
    name: "ui.pagination",
    meta: {
      title: setTitle("Pagination"),
      authRequired: true,
    },
    component: () => import("@/views/ui/paginations.vue"),
  },
  {
    path: "/ui/popovers-tooltips",
    name: "ui.popovers-tooltips",
    meta: {
      title: setTitle("Popovers & Tooltips"),
      authRequired: true,
    },
    component: () => import("@/views/ui/popovers-tooltips.vue"),
  },
  {
    path: "/ui/progress",
    name: "ui.progress",
    meta: {
      title: setTitle("Progress"),
      authRequired: true,
    },
    component: () => import("@/views/ui/progress.vue"),
  },
  {
    path: "/ui/spinners",
    name: "ui.spinners",
    meta: {
      title: setTitle("Spinners"),
      authRequired: true,
    },
    component: () => import("@/views/ui/spinners.vue"),
  },
  {
    path: "/ui/tabs-accordion",
    name: "ui.tabs-accordion",
    meta: {
      title: setTitle("Tabs & Accordion"),
      authRequired: true,
    },
    component: () => import("@/views/ui/tabs-accordion.vue"),
  },
  {
    path: "/ui/typography",
    name: "ui.typography",
    meta: {
      title: setTitle("Typography"),
      authRequired: true,
    },
    component: () => import("@/views/ui/typography.vue"),
  },
  {
    path: "/ui/videos",
    name: "ui.videos",
    meta: {
      title: setTitle("Videos"),
      authRequired: true,
    },
    component: () => import("@/views/ui/videos.vue"),
  },
];

const advancedUiRoutes = [
  {
    path: "/advanced/animation",
    name: "advanced.animation",
    meta: {
      title: setTitle("Animation"),
      authRequired: true,
    },
    component: () => import("@/views/advanced/animation/index.vue"),
  },
  {
    path: "/advanced/clipboard",
    name: "advanced.clipboard",
    meta: {
      title: setTitle("Clipboard"),
      authRequired: true,
    },
    component: () => import("@/views/advanced/clipboard/index.vue"),
  },
  {
    path: "/advanced/dragula",
    name: "advanced.dragula",
    meta: {
      title: setTitle("Dragula"),
      authRequired: true,
    },
    component: () => import("@/views/advanced/dragula/index.vue"),
  },
  {
    path: "/advanced/file-manager",
    name: "advanced.file-manager",
    meta: {
      title: setTitle("File Manager"),
      authRequired: true,
    },
    component: () => import("@/views/advanced/file-manager/index.vue"),
  },
  {
    path: "/advanced/highlight",
    name: "advanced.highlight",
    meta: {
      title: setTitle("Highlight"),
      authRequired: true,
    },
    component: () => import("@/views/advanced/highlight/index.vue"),
  },
  {
    path: "/advanced/range-slider",
    name: "advanced.range-slider",
    meta: {
      title: setTitle("Range Slider"),
      authRequired: true,
    },
    component: () => import("@/views/advanced/range-slider/index.vue"),
  },
  {
    path: "/advanced/ratings",
    name: "advanced.ratings",
    meta: {
      title: setTitle("Ratings"),
      authRequired: true,
    },
    component: () => import("@/views/advanced/ratings/index.vue"),
  },
  {
    path: "/advanced/ribbons",
    name: "advanced.ribbons",
    meta: {
      title: setTitle("Ribbons"),
      authRequired: true,
    },
    component: () => import("@/views/advanced/ribbons/index.vue"),
  },
  {
    path: "/advanced/alert",
    name: "advanced.alert",
    meta: {
      title: setTitle("Sweet Alert"),
      authRequired: true,
    },
    component: () => import("@/views/advanced/alerts/index.vue"),
  },
  {
    path: "/advanced/toasts",
    name: "advanced.toasts",
    meta: {
      title: setTitle("Toasts"),
      authRequired: true,
    },
    component: () => import("@/views/advanced/toasts/index.vue"),
  },
];

const chartsRoutes = [
  {
    path: "/charts/apex",
    name: "charts.apex",
    meta: {
      title: setTitle("Apex Charts"),
      authRequired: true,
    },
    component: () => import("@/views/charts/apex/index.vue"),
  },
  {
    path: "/charts/justgage",
    name: "charts.justgage",
    meta: {
      title: setTitle("Justgage Chart"),
      authRequired: true,
    },
    component: () => import("@/views/charts/justgage/index.vue"),
  },
  {
    path: "/charts/chartjs",
    name: "charts.chartjs",
    meta: {
      title: setTitle("Chartjs Chart"),
      authRequired: true,
    },
    component: () => import("@/views/charts/chartjs/index.vue"),
  },
];

const formsRoutes = [
  {
    path: "/forms/basic",
    name: "forms.basic",
    meta: {
      title: setTitle("Form Basic"),
      authRequired: true,
    },
    component: () => import("@/views/forms/basic/index.vue"),
  },
  {
    path: "/forms/advance",
    name: "forms.advance",
    meta: {
      title: setTitle("Form Advance"),
      authRequired: true,
    },
    component: () => import("@/views/forms/advance/index.vue"),
  },
  {
    path: "/forms/validation",
    name: "forms.validation",
    meta: {
      title: setTitle("Form Validation"),
      authRequired: true,
    },
    component: () => import("@/views/forms/validation/index.vue"),
  },
  {
    path: "/forms/wizard",
    name: "forms.wizard",
    meta: {
      title: setTitle("Form Wizard"),
      authRequired: true,
    },
    component: () => import("@/views/forms/wizard/index.vue"),
  },
  {
    path: "/forms/editors",
    name: "forms.editors",
    meta: {
      title: setTitle("Form Editors"),
      authRequired: true,
    },
    component: () => import("@/views/forms/editors/index.vue"),
  },
  {
    path: "/forms/file-uploads",
    name: "forms.file-uploads",
    meta: {
      title: setTitle("Form Uploads"),
      authRequired: true,
    },
    component: () => import("@/views/forms/file-uploads/index.vue"),
  },
  {
    path: "/forms/image-crop",
    name: "forms.image-crop",
    meta: {
      title: setTitle("Form Image Crop"),
      authRequired: true,
    },
    component: () => import("@/views/forms/image-crop/index.vue"),
  },
];

const tablesRoutes = [
  {
    path: "/tables/basic",
    name: "tables.basic",
    meta: {
      title: setTitle("Basic Tables"),
      authRequired: true,
    },
    component: () => import("@/views/tables/basic.vue"),
  },
  {
    path: "/tables/data-tables",
    name: "tables.data-tables",
    meta: {
      title: setTitle("Data Tables"),
      authRequired: true,
    },
    component: () => import("@/views/tables/data-tables.vue"),
  },
];

const iconsRoutes = [
  {
    path: "/icons/fontawesome",
    name: "icons.fontawesome",
    meta: {
      title: setTitle("Font Awesome Icons"),
      authRequired: true,
    },
    component: () => import("@/views/icons/fontawesome.vue"),
  },
  {
    path: "/icons/lineawesome",
    name: "icons.lineawesome",
    meta: {
      title: setTitle("Line Awesome Icons"),
      authRequired: true,
    },
    component: () => import("@/views/icons/lineawesome.vue"),
  },
  {
    path: "/icons/icofont",
    name: "icons.icofont",
    meta: {
      title: setTitle("Icofont Icons"),
      authRequired: true,
    },
    component: () => import("@/views/icons/icofont.vue"),
  },
  {
    path: "/icons/iconoir",
    name: "icons.iconoir",
    meta: {
      title: setTitle("Iconoir Icons"),
      authRequired: true,
    },
    component: () => import("@/views/icons/iconoir.vue"),
  },
];

const mapsRoutes = [
  {
    path: "/maps/google",
    name: "maps.google",
    meta: {
      title: setTitle("Google Map"),
      authRequired: true,
    },
    component: () => import("@/views/maps/google.vue"),
  },
  {
    path: "/maps/leaflet",
    name: "maps.leaflet",
    meta: {
      title: setTitle("Leaflet Map"),
      authRequired: true,
    },
    component: () => import("@/views/maps/leaflet.vue"),
  },
  {
    path: "/maps/vector",
    name: "maps.vector",
    meta: {
      title: setTitle("Vector Map"),
      authRequired: true,
    },
    component: () => import("@/views/maps/vector.vue"),
  },
];

const componentsRoutes = [
  ...uiRoutes,
  ...advancedUiRoutes,
  ...chartsRoutes,
  ...formsRoutes,
  ...tablesRoutes,
  ...iconsRoutes,
  ...mapsRoutes,
];

export const allRoute = [
  ...authRoutes,
  ...errorRoutes,
  ...dashboardRoutes,
  ...administratorRoutes,
  ...appRoutes,
  ...emailtemplatesRoutes,
  ...pagesRoutes,
  ...componentsRoutes,
];
