/**
 * Sidebar per Role Profile, dibangun dari katalog menu (menu-catalog.ts).
 * - Menu dikelompokkan per kategori (judul kategori = item `isTitle`).
 * - Menu yang tidak bisa dipakai role tersebut TIDAK ditampilkan.
 * - Kategori tanpa menu otomatis disembunyikan.
 */
import {
  CALENDAR_FEATURE,
  FAQ_FEATURE,
  MENU_FEATURES,
  MENU_GROUPS,
  getFeatureLabel,
  getHub,
  getHubFeatures,
  getSuperAdminHubFeatures,
  getSuperAdminRoute,
  isFeatureVisible,
  type MenuContext,
  type MenuGroupId,
} from "@/assets/data/menu-catalog";
import { ROLE_DASHBOARD_CONFIGS } from "@/features/dashboard/config/index";
import { ROLE_PROFILES, type RoleProfile } from "@/types/auth";
import type { MenuItemType } from "@/types/menu";

const calendarItem = (keySuffix: string): MenuItemType => ({
  key: `calendar-${keySuffix}`,
  icon: CALENDAR_FEATURE.icon,
  label: CALENDAR_FEATURE.label,
  description: CALENDAR_FEATURE.description,
  route: { name: "calendar" },
});

const faqItem = (keySuffix: string): MenuItemType => ({
  key: `faq-${keySuffix}`,
  icon: FAQ_FEATURE.icon,
  label: FAQ_FEATURE.label,
  description: FAQ_FEATURE.description,
  guide: "layout.faq",
  route: { name: "help.faq" },
});

const groupTitle = (id: MenuGroupId, keySuffix: string): MenuItemType => ({
  key: `group-${id}-${keySuffix}`,
  label: MENU_GROUPS.find((g) => g.id === id)?.label ?? id,
  isTitle: true,
});

/** Susun item per kategori sesuai urutan MENU_GROUPS; kategori kosong dilewati, judul yang sama tidak diulang. */
const assemble = (byGroup: Partial<Record<MenuGroupId, MenuItemType[]>>, keySuffix: string) => {
  let lastLabel = "";
  return MENU_GROUPS.flatMap(({ id, label }) => {
    const items = byGroup[id];
    if (!items?.length) return [];
    const withTitle = label === lastLabel ? items : [groupTitle(id, keySuffix), ...items];
    lastLabel = label;
    return withTitle;
  });
};

export const createRoleMenu = (
  roleProfile: RoleProfile,
  ctx: Omit<MenuContext, "role"> = { employmentCategory: null },
): MenuItemType[] => {
  const dashboard = ROLE_DASHBOARD_CONFIGS[roleProfile];
  const byGroup: Partial<Record<MenuGroupId, MenuItemType[]>> = {
    utama: [
      {
        key: `dashboard-${dashboard.slug}`,
        icon: "iconoir-home-simple",
        label: dashboard.menuLabel,
        description: dashboard.description,
        route: { name: dashboard.routeName },
      },
      calendarItem(dashboard.slug),
    ],
  };

  const fullCtx: MenuContext = { ...ctx, role: roleProfile };
  const doneHubs = new Set<string>();
  for (const feature of MENU_FEATURES) {
    const routeName = feature.routes[roleProfile];
    if (feature.pane || !routeName || !isFeatureVisible(feature, fullCtx)) continue;
    const hub = getHub(feature.hub);
    if (hub) {
      // Satu item menu per hub; halaman lain di hub dicapai lewat tab di dalam halaman.
      if (doneHubs.has(hub.id)) continue;
      doneHubs.add(hub.id);
      const members = getHubFeatures(hub.id, fullCtx);
      const single = members.length === 1;
      (byGroup[hub.group] ??= []).push({
        key: `hub-${hub.id}-${dashboard.slug}`,
        icon: single ? feature.icon : hub.icon,
        label: single ? getFeatureLabel(feature, roleProfile) : hub.label,
        description: single ? feature.description : hub.description,
        route: { name: routeName },
        activeRoutes: members.map((m) => m.routes[roleProfile]!).filter(Boolean),
      });
      continue;
    }
    (byGroup[feature.group] ??= []).push({
      key: `${feature.id}-${dashboard.slug}`,
      icon: feature.icon,
      label: getFeatureLabel(feature, roleProfile),
      description: feature.description,
      route: { name: routeName },
    });
  }

  byGroup.bantuan = [faqItem(dashboard.slug)];
  return assemble(byGroup, dashboard.slug);
};

/** Menu default per role (tanpa konteks kepegawaian). */
export const ROLE_MENU_ITEMS = Object.fromEntries(
  ROLE_PROFILES.map((roleProfile) => [roleProfile, createRoleMenu(roleProfile)]),
) as Record<RoleProfile, MenuItemType[]>;

const frappeBaseUrl = (import.meta.env.VITE_FRAPPE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

/** Semua menu operasional untuk Super Administrator (lihat getSuperAdminRoute), dikelompokkan seperti menu role. */
const superAdminOperationalMenu = (): Partial<Record<MenuGroupId, MenuItemType[]>> => {
  const byGroup: Partial<Record<MenuGroupId, MenuItemType[]>> = {};
  const doneHubs = new Set<string>();
  for (const feature of MENU_FEATURES) {
    const routeName = getSuperAdminRoute(feature);
    if (feature.pane || !routeName) continue;
    const hub = getHub(feature.hub);
    if (hub) {
      if (doneHubs.has(hub.id)) continue;
      doneHubs.add(hub.id);
      const members = getSuperAdminHubFeatures(hub.id);
      const single = members.length === 1;
      (byGroup[hub.group] ??= []).push({
        key: `hub-${hub.id}-administrator`,
        icon: single ? feature.icon : hub.icon,
        label: single ? feature.label : hub.label,
        description: single ? feature.description : hub.description,
        route: { name: routeName },
        activeRoutes: members.map((m) => getSuperAdminRoute(m)!).filter(Boolean),
      });
      continue;
    }
    (byGroup[feature.group] ??= []).push({
      key: `${feature.id}-administrator`,
      icon: feature.icon,
      label: feature.label,
      description: feature.description,
      route: { name: routeName },
    });
  }
  return byGroup;
};

const adminOps = superAdminOperationalMenu();

export const ADMINISTRATOR_MENU_ITEMS: MenuItemType[] = assemble(
  {
    ...adminOps,
    utama: [
      {
        key: "dashboard-administrator",
        icon: "iconoir-home-simple",
        label: "Dashboard Admin",
        description: "Ringkasan administrasi sistem.",
        route: { name: "dashboard.administrator" },
      },
      calendarItem("administrator"),
      ...(adminOps.utama ?? []),
    ],
    sistem: [
      {
        key: "administrator-users",
        icon: "iconoir-group",
        label: "User",
        description: "Kelola akun pengguna, Role Profile, dan cabang yang boleh diakses.",
        route: { name: "administrator.users" },
      },
      {
        key: "administrator-institutions",
        icon: "iconoir-building",
        label: "Institusi",
        description: "Data unit sekolah/cabang (Company), kode cabang, dan lokasi.",
        route: { name: "administrator.institutions" },
      },
      {
        key: "administrator-ai-settings",
        icon: "iconoir-cpu",
        label: "AI Assistant",
        description: "Penyedia model AI (Ollama/OpenAI/Anthropic), tes koneksi, dan uji coba percakapan.",
        route: { name: "administrator.ai-settings" },
      },
      {
        key: "administrator-migration",
        icon: "iconoir-data-transfer-both",
        label: "Migrasi Data",
        description: "Pindahkan data dari sistem SPI lama per langkah atau sekaligus, dengan log proses.",
        route: { name: "administrator.migration" },
      },
      {
        key: "administrator-activity-monitor",
        icon: "iconoir-activity",
        label: "Monitoring Aktivitas",
        description: "Riwayat aktivitas pengguna (halaman, klik, isian, sesi) dan pengaturan monitoring. Hanya admin.",
        route: { name: "administrator.activity-monitor" },
      },
      {
        key: "administrator-session-replay",
        icon: "iconoir-play",
        label: "Session Replay",
        description: "Putar ulang urutan aktivitas satu sesi pengguna (rekonstruksi, bukan rekaman layar). Hanya admin.",
        route: { name: "administrator.session-replay" },
      },
      {
        key: "administrator-desk",
        icon: "iconoir-open-new-window",
        label: "Desk ERPNext",
        description: "Buka Desk ERPNext (/app). Hanya untuk admin.",
        url: `${frappeBaseUrl}/app/home`,
        target: "_blank",
      },
    ],
    bantuan: [faqItem("administrator")],
  },
  "administrator",
);

export const UNASSIGNED_MENU_ITEMS: MenuItemType[] = assemble(
  {
    utama: [
      {
        key: "dashboard-unassigned",
        icon: "iconoir-home-simple",
        label: "Dashboard",
        route: { name: "dashboard.unassigned" },
      },
    ],
    bantuan: [faqItem("unassigned")],
  },
  "unassigned",
);
