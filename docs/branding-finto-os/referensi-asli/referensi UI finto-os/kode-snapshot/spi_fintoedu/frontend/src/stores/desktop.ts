import { defineStore } from "pinia";
import { ref } from "vue";
import type { LocationQueryRaw } from "vue-router";
import { findFeatureByRouteName, getFeatureLabel } from "@/assets/data/menu-catalog";
import { ADMINISTRATOR_MENU_ITEMS } from "@/assets/data/menu-items";
import { ROLE_DASHBOARD_CONFIGS } from "@/features/dashboard/config/index";
import { useAuthStore } from "@/stores/auth";
import { trackWindowRoute } from "@/features/activity-monitor/tracker";

export type DesktopWindow = {
  id: string;
  routeName: string;
  query: LocationQueryRaw;
  title: string;
  icon: string;
  x: number;
  y: number;
  w: number;
  h: number;
  z: number;
  minimized: boolean;
  maximized: boolean;
};

const STORAGE_KEY = "spi_desktop_windows";
const TASKBAR_HEIGHT = 48;

/** Judul & ikon jendela dari katalog menu / dashboard / menu administrator. */
export function describeRoute(routeName: string): { title: string; icon: string } {
  const auth = useAuthStore();
  if (routeName === "help.faq") return { title: "FAQ & Bantuan", icon: "iconoir-help-circle" };
  if (routeName === "calendar") return { title: "Kalender", icon: "iconoir-calendar" };
  if (routeName === "teacher.class-detail") return { title: "Detail Rombel", icon: "iconoir-community" };
  const feature = findFeatureByRouteName(routeName);
  if (feature) return { title: getFeatureLabel(feature, auth.effectiveRoleProfile), icon: feature.icon };
  const dash = Object.values(ROLE_DASHBOARD_CONFIGS).find((d) => d.routeName === routeName);
  if (dash) return { title: dash.menuLabel, icon: "iconoir-home-simple" };
  const admin = ADMINISTRATOR_MENU_ITEMS.find((m) => m.route?.name === routeName);
  if (admin) return { title: admin.label, icon: admin.icon || "iconoir-app-window" };
  if (routeName === "dashboard.administrator") return { title: "Dashboard Admin", icon: "iconoir-home-simple" };
  return { title: routeName, icon: "iconoir-app-window" };
}

/**
 * Jendela yang terbuka di mode desktop. Disimpan di sessionStorage agar refresh tidak menutup jendela.
 * Satu jendela per rute (membuka lagi = memfokuskan jendela yang ada).
 */
export const useDesktopStore = defineStore("desktop_store", () => {
  const windows = ref<DesktopWindow[]>(load());
  const recent = ref<string[]>([]);
  const startOpen = ref(false);
  let zTop = Math.max(10, ...windows.value.map((w) => w.z));

  function load(): DesktopWindow[] {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "[]");
    } catch {
      return [];
    }
  }

  function persist() {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(windows.value));
    } catch {
      // abaikan
    }
  }

  const isMobile = () => window.innerWidth < 768;

  function focus(id: string) {
    const win = windows.value.find((w) => w.id === id);
    if (!win) return;
    win.z = ++zTop;
    win.minimized = false;
    persist();
    // Activity Monitoring: jendela aktif = halaman yang sedang dilihat (tidak mengganda untuk jendela yang sama).
    trackWindowRoute(win.routeName, win.query as Record<string, unknown>);
  }

  function openWindow(routeName: string, query: LocationQueryRaw = {}, opts: { maximized?: boolean } = {}) {
    startOpen.value = false;
    recent.value = [routeName, ...recent.value.filter((r) => r !== routeName)].slice(0, 6);
    const existing = windows.value.find((w) => w.routeName === routeName);
    if (existing) {
      existing.query = query;
      focus(existing.id);
      return existing;
    }
    const { title, icon } = describeRoute(routeName);
    const vw = window.innerWidth;
    const vh = window.innerHeight - TASKBAR_HEIGHT;
    const w = Math.min(1100, Math.round(vw * 0.78));
    const h = Math.min(760, Math.round(vh * 0.82));
    const offset = (windows.value.length % 6) * 28;
    const win: DesktopWindow = {
      id: `w${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
      routeName,
      query,
      title,
      icon,
      x: Math.max(8, Math.round((vw - w) / 2) - 60 + offset),
      y: Math.max(8, Math.round((vh - h) / 2) - 30 + offset),
      w,
      h,
      z: ++zTop,
      minimized: false,
      // Keputusan pemilik (11 Nov 2026, menggantikan 6 Nov): jendela dibuka dengan ukuran NORMAL (tidak dimaksimalkan);
      // pengguna bisa memaksimalkan lewat tombol jendela. Layar sempit (< 768px) tetap penuh agar bisa dipakai.
      maximized: opts.maximized ?? vw < 768,
    };
    windows.value.push(win);
    persist();
    trackWindowRoute(routeName, query as Record<string, unknown>);
    return win;
  }

  function navigate(id: string, routeName: string, query: LocationQueryRaw = {}) {
    const win = windows.value.find((w) => w.id === id);
    if (!win) return;
    // Rute tujuan sudah terbuka di jendela lain: fokuskan itu saja.
    const other = windows.value.find((w) => w.routeName === routeName && w.id !== id);
    if (other) {
      focus(other.id);
      return;
    }
    Object.assign(win, { routeName, query, ...describeRoute(routeName) });
    persist();
    trackWindowRoute(routeName, query as Record<string, unknown>);
  }

  function close(id: string) {
    windows.value = windows.value.filter((w) => w.id !== id);
    persist();
  }

  function minimize(id: string) {
    const win = windows.value.find((w) => w.id === id);
    if (win) win.minimized = true;
    persist();
  }

  function toggleMaximize(id: string) {
    const win = windows.value.find((w) => w.id === id);
    if (win) win.maximized = !win.maximized;
    persist();
  }

  function update(id: string, patch: Partial<Pick<DesktopWindow, "x" | "y" | "w" | "h">>) {
    const win = windows.value.find((w) => w.id === id);
    if (win) Object.assign(win, patch);
    persist();
  }

  /** Klik ikon taskbar: jendela aktif -> minimize; lainnya -> fokus. */
  function toggleFromTaskbar(id: string) {
    const win = windows.value.find((w) => w.id === id);
    if (!win) return;
    const isTop = !win.minimized && win.z === zTop;
    if (isTop) minimize(id);
    else focus(id);
  }

  function activeId() {
    const visible = windows.value.filter((w) => !w.minimized);
    return visible.length ? visible.reduce((a, b) => (a.z > b.z ? a : b)).id : null;
  }

  function closeAll() {
    windows.value = [];
    persist();
  }

  return {
    windows,
    recent,
    startOpen,
    openWindow,
    navigate,
    focus,
    close,
    minimize,
    toggleMaximize,
    update,
    toggleFromTaskbar,
    activeId,
    closeAll,
    TASKBAR_HEIGHT,
  };
});
