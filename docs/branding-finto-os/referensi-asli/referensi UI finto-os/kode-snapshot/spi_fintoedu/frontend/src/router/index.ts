import {
  createRouter,
  createWebHistory,
  type LocationQueryRaw,
  type NavigationGuardReturn,
  type RouteLocationNormalized,
} from "vue-router";
import { allRoute } from "@/router/routes";
import { useAuthStore } from "@/stores/auth";
import { useDesktopStore } from "@/stores/desktop";
import { useUiStore } from "@/stores/ui";
import { getDashboardRouteName } from "@/features/dashboard/config/index";
import { isRoleProfile } from "@/types/auth";
import { setRouteResolver, trackRoute } from "@/features/activity-monitor/tracker";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: allRoute,
});

// Activity Monitoring (mode desktop): nama rute jendela → lokasi rute untuk dicatat sebagai halaman.
setRouteResolver((name, query) => router.resolve({ name, query: query as LocationQueryRaw }) as unknown as RouteLocationNormalized);

/** Rute di luar shell desktop (halaman publik / layar login) — tetap tampil penuh di mode desktop. */
const DESKTOP_PASSTHROUGH = new Set(["desktop.boot", "desktop.login", "public.registers", "error.404", "error.500"]);

router.beforeEach(async (to) => {
  const title = to.meta.title;
  if (title) {
    document.title = title.toString();
  }

  const ui = useUiStore();
  await ui.ensureLoaded();
  const authRequired = to.matched.some((route) => route.meta.authRequired);

  if (ui.mode === "desktop") {
    return desktopGuard(to, authRequired);
  }
  // Mode web: rute khusus desktop dialihkan ke padanan web.
  if (to.name === "desktop.home") return { name: "home" };
  if (to.name === "desktop.boot" || to.name === "desktop.login") return { name: "auth.sign-in", query: to.query };

  return webGuard(to, authRequired);
});

/**
 * Mode desktop (diatur Super Administrator):
 * - belum login: animasi booting (sekali per sesi) lalu layar login gaya OS;
 * - sudah login: semua halaman dibuka sebagai JENDELA di /desktop (URL tetap /desktop).
 * Hak akses rute tetap dicek dengan aturan yang sama seperti mode web.
 */
async function desktopGuard(to: RouteLocationNormalized, authRequired: boolean): Promise<NavigationGuardReturn> {
  if (DESKTOP_PASSTHROUGH.has(String(to.name))) {
    if (to.name === "desktop.login" && !useUiStore().hasBooted()) return { name: "desktop.boot", query: to.query };
    return true;
  }
  if (!authRequired) {
    // Halaman login web & auth lainnya -> layar login desktop.
    const auth = useAuthStore();
    if (await auth.initializeSession()) return { name: "desktop.home" };
    return { name: useUiStore().hasBooted() ? "desktop.login" : "desktop.boot", query: to.query };
  }
  const auth = useAuthStore();
  if (!(await auth.initializeSession())) {
    const query = to.name === "desktop.home" || to.name === "home" ? {} : { redirectedFrom: to.fullPath };
    return { name: useUiStore().hasBooted() ? "desktop.login" : "desktop.boot", query };
  }
  if (to.name === "home") return { name: "desktop.home" };
  if (to.name === "desktop.home") return true;

  const verdict = await webGuard(to, authRequired);
  if (verdict === true && to.name) {
    trackRoute(to);
    useDesktopStore().openWindow(String(to.name), { ...to.query } as LocationQueryRaw);
  }
  return { name: "desktop.home" };
}

async function webGuard(to: RouteLocationNormalized, authRequired: boolean): Promise<NavigationGuardReturn> {
  if (!authRequired) {
    return true;
  }

  const auth = useAuthStore();
  const user = await auth.initializeSession();
  if (!user) {
    return {
      name: "auth.sign-in",
      query: { redirectedFrom: to.fullPath },
    };
  }

  // Super Administrator ("Administrator") dapat melihat dashboard role lain (pilihan "Lihat sebagai").
  const isSuperAdministrator = user.username === "Administrator";
  const viewAs = isSuperAdministrator ? auth.viewAsRole : null;
  const dashboardRouteName = viewAs
    ? getDashboardRouteName(viewAs, false)
    : getDashboardRouteName(user.roleProfile, user.isSystemManager);

  if (to.name === "home") {
    return { name: dashboardRouteName };
  }

  // Monitoring Aktivitas & Session Replay: hanya user Administrator dan tidak saat "Lihat sebagai" (dicek ulang di server).
  const superAdministratorOnly = to.matched.some((route) => route.meta.superAdministratorOnly === true);
  if (superAdministratorOnly && (!isSuperAdministrator || viewAs)) {
    return { name: dashboardRouteName };
  }

  if (isSuperAdministrator) {
    return true;
  }

  const systemManagerOnly = to.matched.some(
    (route) => route.meta.systemManagerOnly === true,
  );
  if (systemManagerOnly && !user.isSystemManager) {
    return { name: dashboardRouteName };
  }

  const allowedRoleProfiles = to.matched.flatMap((route) => {
    const profiles = route.meta.roleProfiles;
    return Array.isArray(profiles) ? profiles.filter(isRoleProfile) : [];
  });
  if (
    allowedRoleProfiles.length &&
    (!user.roleProfile || !allowedRoleProfiles.includes(user.roleProfile))
  ) {
    return { name: dashboardRouteName };
  }

  if (
    to.name === "dashboard.unassigned" &&
    (user.roleProfile || user.isSystemManager)
  ) {
    return { name: dashboardRouteName };
  }

  return true;
}

// Activity Monitoring: catat perpindahan halaman (mode web). Tidak melakukan apa pun bila tracker tidak aktif.
router.afterEach((to, _from, failure) => {
  if (!failure && to.name !== "desktop.home") trackRoute(to);
});

export default router;
