<template>
  <div
    class="os-root os-wallpaper"
    :style="{ '--os-taskbar-h': `${desktop.TASKBAR_HEIGHT}px`, ...wallpaperStyle }"
    @pointerdown="onBackgroundPointer"
    @contextmenu="onContextMenu"
  >
    <!-- Ikon desktop -->
    <!-- Posisi ikon: grid, dapat diseret (iconLayout.ts); disimpan per user & peran -->
    <div ref="iconArea" class="os-icons" role="list" aria-label="Aplikasi" data-guide="desktop.icons">
      <button
        v-for="app in apps"
        :key="app.key"
        type="button"
        role="listitem"
        class="os-icon"
        :class="{ selected: selectedIcon === app.key, dragging: drag?.key === app.key && drag.moved }"
        :style="iconStyle(app.key)"
        :title="`${app.description}${app.description ? '\n' : ''}Kategori: ${app.group} · seret untuk memindahkan`"
        @pointerdown="onIconPointerDown($event, app)"
        @click="onIconClick(app)"
        @dblclick="launch(app)"
        @keydown.enter="launch(app)"
      >
        <span class="os-icon-img" :style="app.tile"><i :class="app.icon"></i></span>
        <span class="os-icon-label">{{ app.label }}</span>
      </button>
    </div>

    <!-- Jendela -->
    <DesktopWindow
      v-for="w in desktop.windows"
      :key="w.id"
      :win="w"
      :active="w.id === activeId"
      @tour="runPageTour"
    />

    <!-- Panel kanan Tindak Lanjut: jendela maksimal menyusut selebar panel (--spi-pane-w) -->
    <ActionPane desktop />

    <!-- Menu Start -->
    <transition name="os-pop">
      <div v-if="desktop.startOpen" class="os-start" role="dialog" aria-label="Menu Start" @pointerdown.stop>
        <div class="os-start-search">
          <i class="iconoir-search"></i>
          <input
            ref="searchInput"
            v-model="search"
            type="search"
            placeholder="Cari aplikasi, menu, atau bantuan"
            aria-label="Cari aplikasi"
            @keydown.enter="launchFirst"
            @keydown.esc="desktop.startOpen = false"
          />
        </div>

        <div class="os-start-body">
          <div class="d-flex justify-content-between align-items-center mb-2">
            <h2 class="os-start-h">{{ search ? "Hasil pencarian" : "Aplikasi" }}</h2>
          </div>
          <div v-if="filteredApps.length" class="os-start-grid">
            <button v-for="app in filteredApps" :key="app.key" type="button" class="os-start-app" :title="app.description" @click="launch(app)">
              <span class="os-start-app-icon" :style="app.tile"><i :class="app.icon"></i></span>
              <span class="os-start-app-label">{{ app.label }}</span>
            </button>
          </div>
          <div v-else class="text-muted small py-3 text-center">
            Tidak ada aplikasi yang cocok.
            <a href="javascript:void(0);" @click="searchFaq">Cari "{{ search }}" di FAQ</a>
          </div>

          <template v-if="!search && recentApps.length">
            <h2 class="os-start-h mt-4">Terakhir dibuka</h2>
            <div class="os-start-recent">
              <button v-for="app in recentApps" :key="app.key" type="button" class="os-recent" @click="launch(app)">
                <i :class="app.icon" class="text-primary"></i>
                <span class="text-truncate">{{ app.label }}</span>
              </button>
            </div>
          </template>

          <template v-if="auth.isSuperAdministrator">
            <h2 class="os-start-h mt-4">Admin</h2>
            <div class="row g-2">
              <div class="col-12 col-sm-6">
                <label class="form-label small mb-1" for="os-view-as">Lihat sebagai</label>
                <select id="os-view-as" class="form-select form-select-sm" :value="auth.viewAsRole || ''" @change="switchView(($event.target as HTMLSelectElement).value)">
                  <option value="">Admin</option>
                  <option v-for="r in VIEW_AS_ROLES" :key="r" :value="r">{{ r }}</option>
                </select>
              </div>
              <div class="col-12 col-sm-6">
                <label class="form-label small mb-1" for="os-ui-mode">Mode tampilan</label>
                <select id="os-ui-mode" class="form-select form-select-sm" :value="ui.mode" @change="changeMode(($event.target as HTMLSelectElement).value as UiMode)">
                  <option value="desktop">Desktop (Finto OS)</option>
                  <option value="web">Web</option>
                </select>
              </div>
            </div>
          </template>
        </div>

        <div class="os-start-footer">
          <div class="d-flex align-items-center gap-2 min-w-0">
            <span class="os-avatar">{{ initial }}</span>
            <div class="min-w-0">
              <div class="fw-semibold small text-truncate">{{ auth.user?.fullName }}</div>
              <div class="text-muted" style="font-size: 11px">{{ roleLabel }}</div>
            </div>
          </div>
          <div class="d-flex gap-1">
            <button type="button" class="os-round" title="Tampilkan ulang semua panduan" aria-label="Tampilkan ulang panduan" @click="replayGuides">
              <i class="iconoir-map"></i>
            </button>
            <button type="button" class="os-round" title="Ganti Password" aria-label="Ganti Password" @click="passwordModal.open = true">
              <i class="iconoir-key"></i>
            </button>
            <button type="button" class="os-round" title="Keluar (Logout)" aria-label="Keluar" @click="logout">
              <i class="iconoir-log-out"></i>
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Panel notifikasi -->
    <transition name="os-pop">
      <div v-if="notifOpen" class="os-notif" role="dialog" aria-label="Notifikasi" @pointerdown.stop>
        <div class="d-flex justify-content-between align-items-center px-3 py-2 border-bottom">
          <strong>Notifikasi</strong>
          <button v-if="unread > 0" type="button" class="btn btn-link btn-sm p-0" @click="markAll">Tandai semua dibaca</button>
        </div>
        <div class="os-notif-list">
          <div v-if="!notifications.length" class="text-center text-muted small py-4">Belum ada notifikasi.</div>
          <button
            v-for="n in notifications"
            :key="n.name"
            type="button"
            class="os-notif-item"
            :class="{ unread: !n.read }"
            @click="openNotification(n)"
          >
            <span v-if="!n.read" class="os-dot" aria-label="Belum dibaca"></span>
            <span class="d-block fw-semibold small">{{ n.subject }}</span>
            <span class="d-block text-muted" style="font-size: 12px">{{ plainText(n.email_content) }}</span>
          </button>
        </div>
      </div>
    </transition>

    <!-- Taskbar -->
    <footer class="os-taskbar" @pointerdown.stop>
      <div class="os-task-left d-none d-md-flex">
        <span class="small text-truncate">{{ greeting }}, {{ firstName }}</span>
      </div>
      <div class="os-task-center">
        <button type="button" class="os-task-btn" :class="{ on: desktop.startOpen }" title="Start" aria-label="Menu Start" data-guide="desktop.start" @click="toggleStart">
          <img :src="logoSm" alt="" class="os-start-logo" />
        </button>
        <button type="button" class="os-task-btn" title="Cari" aria-label="Cari" data-guide="desktop.search" @click="openSearch">
          <i class="iconoir-search"></i>
        </button>
        <div class="os-task-windows" data-guide="desktop.taskbar-windows">
          <button
            v-for="w in desktop.windows"
            :key="w.id"
            type="button"
            class="os-task-btn os-task-win"
            :class="{ on: w.id === activeId, open: true }"
            :title="w.title"
            :aria-label="w.title"
            @click="desktop.toggleFromTaskbar(w.id)"
          >
            <i :class="w.icon"></i>
          </button>
        </div>
      </div>
      <div class="os-task-right">
        <button type="button" class="os-task-btn position-relative" title="Notifikasi" aria-label="Notifikasi" data-guide="desktop.bell" @click="toggleNotif">
          <i class="iconoir-bell"></i>
          <span v-if="unread > 0" class="os-badge">{{ unread > 99 ? "99+" : unread }}</span>
        </button>
        <button type="button" class="os-task-btn" title="Panduan" aria-label="Panduan" @click="replayWelcome">
          <i class="iconoir-help-circle"></i>
        </button>
        <button
          type="button"
          class="os-clock"
          :title="`${fullDate} — klik untuk membuka Kalender`"
          aria-label="Buka Kalender"
          data-guide="desktop.clock"
          @click.stop="openRoute('calendar')"
        >
          <div>{{ time }}</div>
          <div>{{ shortDate }}</div>
        </button>
      </div>
    </footer>

    <!-- Menu klik kanan di area kosong desktop -->
    <ul
      v-if="ctxMenu"
      class="os-ctx"
      role="menu"
      :style="{ left: `${ctxMenu.x}px`, top: `${ctxMenu.y}px` }"
      @pointerdown.stop
      @contextmenu.prevent
    >
      <li role="menuitem" tabindex="0" @click="openWallpaper" @keydown.enter="openWallpaper">
        <i class="iconoir-media-image"></i> Ganti latar belakang…
      </li>
      <li role="menuitem" tabindex="0" @click="ctxAction(() => toggleStart())" @keydown.enter="ctxAction(() => toggleStart())">
        <i class="iconoir-app-window"></i> Buka menu Start
      </li>
      <li role="menuitem" tabindex="0" @click="ctxAction(resetIcons)" @keydown.enter="ctxAction(resetIcons)">
        <i class="iconoir-view-grid"></i> Rapikan ikon (susunan bawaan)
      </li>
      <li role="menuitem" tabindex="0" @click="ctxAction(replayWelcome)" @keydown.enter="ctxAction(replayWelcome)">
        <i class="iconoir-help-circle"></i> Tampilkan panduan
      </li>
      <li class="sep" role="separator"></li>
      <li role="menuitem" tabindex="0" @click="ctxAction(reloadPage)" @keydown.enter="ctxAction(reloadPage)">
        <i class="iconoir-refresh"></i> Muat ulang
      </li>
    </ul>

    <WallpaperModal v-model="wallpaperOpen" :current="wallpaper" @changed="wallpaper = $event" />

    <TourGuide
      v-model="tourOpen"
      :title="tour?.title || ''"
      :eyebrow="tour?.eyebrow"
      :steps="tour?.steps || []"
      :finish-label="tour?.key === WELCOME_GUIDE_KEY ? 'Mulai bekerja' : 'Selesai'"
      @done="onTourDone"
    />
  </div>
</template>

<script setup lang="ts">
import { passwordModal } from "@/features/account/api";
/**
 * Mode desktop (Finto OS): tampilan seperti sistem operasi. Menu menjadi ikon desktop & aplikasi di menu Start,
 * setiap halaman terbuka sebagai jendela (bisa digeser, diubah ukuran, minimalkan, maksimalkan, tutup),
 * taskbar berisi Start, cari, jendela terbuka, notifikasi, dan jam. Aktif bila Super Administrator memilih
 * mode "desktop" (spi_fintoedu.api.ui_settings).
 */
import HttpClient from "@/helpers/http-client";
import { getDashboardRouteName } from "@/features/dashboard/config/index";
import ActionPane from "@/features/action-center/components/ActionPane.vue";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import Swal from "sweetalert2";
import "../desktop.css";
import logoSm from "@/assets/images/finto-os-logo.png"; // logo utama Finto OS (12 Nov 2026)
import DesktopWindow from "../components/DesktopWindow.vue";
import WallpaperModal from "../components/WallpaperModal.vue";
import { appStyle } from "../appStyles";
import { presetCss } from "../wallpapers";
import { getDesktopPrefs, resetIconLayout, setIconLayout, type IconLayouts, type Wallpaper } from "../prefsApi";
import { CELL_H, CELL_W, moveIcon, resolveLayout, type Pos } from "../iconLayout";
import TourGuide, { type TourStep } from "@/features/onboarding/components/TourGuide.vue";
import { findFeatureByRouteName, getFeatureLabel, getHub, MENU_GROUPS } from "@/assets/data/menu-catalog";
import { PAGE_TOURS } from "@/assets/data/page-tours";
import { getMenuItems } from "@/helpers/menu";
import { resolveNotificationRoute } from "@/helpers/notification-route";
import { getMyNotifications, markNotificationsRead, type AppNotification } from "@/features/notifications/api";
import { useAuthStore } from "@/stores/auth";
import { useDesktopStore } from "@/stores/desktop";
import { useOnboardingStore, WELCOME_GUIDE_KEY } from "@/stores/onboarding";
import { useUiStore, type UiMode } from "@/stores/ui";
import type { RoleProfile } from "@/types/auth";
import type { MenuItemType } from "@/types/menu";

type App = {
  key: string;
  label: string;
  icon: string;
  description: string;
  routeName?: string;
  url?: string;
  group: string;
  tile: Record<string, string>;
};

/** Id gaya ikon (appStyles.ts): hub / fitur / dashboard / faq / menu Super Administrator. */
function appIdFor(item: MenuItemType): string {
  const key = item.key;
  if (key.startsWith("dashboard-")) return "dashboard";
  if (key.startsWith("faq-")) return "faq";
  if (key.startsWith("calendar-")) return "calendar";
  if (key.startsWith("administrator-")) {
    const map: Record<string, string> = {
      "administrator-users": "admin-users",
      "administrator-institutions": "admin-institutions",
      "administrator-ai-settings": "admin-ai",
      "administrator-desk": "admin-desk",
      "administrator-activity-monitor": "admin-activity",
      "administrator-session-replay": "admin-replay",
    };
    return map[key] ?? key;
  }
  const feature = findFeatureByRouteName(item.route?.name as string | undefined);
  if (!feature) return key;
  const hub = getHub(feature.hub);
  return hub && item.label === hub.label ? hub.id : feature.id;
}

const VIEW_AS_ROLES: RoleProfile[] = ["Branch Manager", "Principal", "Finance", "CSO", "Teacher", "Parent", "Student", "Staff Yayasan"];

const auth = useAuthStore();
const desktop = useDesktopStore();
const ui = useUiStore();
const onboarding = useOnboardingStore();
const router = useRouter();

const search = ref("");
const searchInput = ref<HTMLInputElement | null>(null);
const selectedIcon = ref<string | null>(null);

// ---------------------------------------------------------------- aplikasi (dari menu role)
const apps = computed<App[]>(() => {
  let group = "";
  const out: App[] = [];
  for (const item of getMenuItems(auth.menuContext) as MenuItemType[]) {
    if (item.isTitle) {
      group = item.label;
      continue;
    }
    const style = appStyle(appIdFor(item));
    out.push({
      key: item.key,
      label: item.label,
      icon: style.icon || item.icon || "iconoir-app-window",
      tile: { background: `linear-gradient(145deg, ${style.from}, ${style.to})` },
      description: item.description || "",
      routeName: item.route?.name as string | undefined,
      url: item.url,
      group,
    });
  }
  return out;
});

// ---------------------------------------------------------------- tata letak ikon (seret & lepas, 12 Nov 2026)
const iconArea = ref<HTMLElement | null>(null);
const grid = ref({ rows: 6, cols: 10 });
const iconLayouts = ref<IconLayouts>({});
const layoutRole = computed(() => auth.effectiveRoleProfile || auth.user?.roleProfile || "default");
const layout = computed<Record<string, Pos>>(() =>
  resolveLayout(apps.value, iconLayouts.value[layoutRole.value] as Record<string, Pos> | undefined, grid.value.rows, grid.value.cols),
);
const drag = ref<{ key: string; startX: number; startY: number; dx: number; dy: number; moved: boolean } | null>(null);
let suppressClick = false;

function measureGrid() {
  const el = iconArea.value;
  if (!el) return;
  grid.value = { rows: Math.max(1, Math.floor(el.clientHeight / CELL_H)), cols: Math.max(1, Math.floor(el.clientWidth / CELL_W)) };
}

function iconStyle(key: string) {
  const p = layout.value[key];
  if (!p) return {};
  const d = drag.value?.key === key && drag.value.moved ? drag.value : null;
  return {
    left: `${p[0] * CELL_W + (d ? d.dx : 0)}px`,
    top: `${p[1] * CELL_H + (d ? d.dy : 0)}px`,
  };
}

function onIconPointerDown(e: PointerEvent, app: App) {
  if (e.button !== 0) return;
  drag.value = { key: app.key, startX: e.clientX, startY: e.clientY, dx: 0, dy: 0, moved: false };
  window.addEventListener("pointermove", onIconPointerMove);
  window.addEventListener("pointerup", onIconPointerUp, { once: true });
}

function onIconPointerMove(e: PointerEvent) {
  const d = drag.value;
  if (!d) return;
  d.dx = e.clientX - d.startX;
  d.dy = e.clientY - d.startY;
  if (!d.moved && Math.hypot(d.dx, d.dy) > 6) d.moved = true;
}

let saveTimer: ReturnType<typeof setTimeout> | null = null;
function onIconPointerUp() {
  window.removeEventListener("pointermove", onIconPointerMove);
  const d = drag.value;
  drag.value = null;
  if (!d || !d.moved) return;
  suppressClick = true;
  const from = layout.value[d.key];
  const col = Math.min(Math.max(0, Math.round((from[0] * CELL_W + d.dx) / CELL_W)), grid.value.cols - 1);
  const row = Math.min(Math.max(0, Math.round((from[1] * CELL_H + d.dy) / CELL_H)), grid.value.rows - 1);
  const next = moveIcon(layout.value, d.key, [col, row]);
  iconLayouts.value = { ...iconLayouts.value, [layoutRole.value]: next };
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    setIconLayout(layoutRole.value, next).catch((err) => console.warn("Gagal menyimpan posisi ikon", err));
  }, 400);
}

async function resetIcons() {
  const { [layoutRole.value]: _removed, ...rest } = iconLayouts.value;
  iconLayouts.value = rest;
  try {
    iconLayouts.value = (await resetIconLayout(layoutRole.value)).icon_layouts;
  } catch (err) {
    console.warn("Gagal mengatur ulang posisi ikon", err);
  }
}

const filteredApps = computed(() => {
  const q = search.value.trim().toLowerCase();
  if (!q) return apps.value;
  return apps.value.filter((a) => `${a.label} ${a.description} ${a.group}`.toLowerCase().includes(q));
});

const recentApps = computed(() =>
  desktop.recent
    .map((routeName) => apps.value.find((a) => a.routeName === routeName))
    .filter((a): a is App => Boolean(a))
    .slice(0, 6),
);

const activeId = computed(() => desktop.activeId());

function launch(app: App) {
  desktop.startOpen = false;
  search.value = "";
  if (app.url) {
    window.open(app.url, "_blank", "noopener");
    return;
  }
  if (app.routeName) openRoute(app.routeName);
}

function launchFirst() {
  if (filteredApps.value[0]) launch(filteredApps.value[0]);
  else searchFaq();
}

/** Tur halaman dipicu watcher jumlah jendela (berlaku juga untuk jendela yang dibuka lewat router). */
function openRoute(routeName: string, query: Record<string, string> = {}) {
  desktop.openWindow(routeName, query);
}

function searchFaq() {
  const q = search.value.trim();
  desktop.startOpen = false;
  search.value = "";
  openRoute("help.faq", q ? { q } : {});
}

// Desktop: satu klik memilih, dua klik membuka (seperti OS). Layar sentuh/HP: satu klik membuka.
function onIconClick(app: App) {
  if (suppressClick) {
    suppressClick = false; // klik setelah seret: bukan memilih ikon
    return;
  }
  if (window.matchMedia("(pointer: coarse)").matches) launch(app);
  else selectedIcon.value = app.key;
}

function onBackgroundPointer() {
  selectedIcon.value = null;
  desktop.startOpen = false;
  notifOpen.value = false;
  ctxMenu.value = null;
}

// ---------------------------------------------------------------- personalisasi (per pengguna)
/**
 * Latar terakhir disimpan juga di browser (per akun) agar langsung tampil saat halaman di-refresh dan tidak
 * kembali ke latar bawaan bila permintaan ke server sempat gagal. Sumber kebenaran tetap server (api/desktop_prefs.py).
 */
const wallpaperCacheKey = () => `spi_wallpaper:${auth.user?.username || ""}`;
function readCachedWallpaper(): Wallpaper | null {
  try {
    const v = JSON.parse(localStorage.getItem(wallpaperCacheKey()) || "null");
    return v && (v.kind === "preset" || v.kind === "image") && typeof v.value === "string" ? v : null;
  } catch {
    return null;
  }
}
const wallpaper = ref<Wallpaper>(readCachedWallpaper() ?? { kind: "preset", value: "finto" });
watch(
  wallpaper,
  (v) => {
    try {
      localStorage.setItem(wallpaperCacheKey(), JSON.stringify(v));
    } catch {
      // abaikan
    }
  },
  { deep: true },
);
const wallpaperOpen = ref(false);
/** URL gambar yang benar-benar dipakai: langsung dari server, atau blob bila pemuatan langsung gagal. */
const wallpaperSrc = ref("");
let wallpaperBlobUrl = "";
watch(
  () => (wallpaper.value.kind === "image" ? wallpaper.value.value : ""),
  (url) => {
    if (wallpaperBlobUrl) URL.revokeObjectURL(wallpaperBlobUrl);
    wallpaperBlobUrl = "";
    wallpaperSrc.value = url;
    if (!url) return;
    const probe = new Image();
    probe.onerror = async () => {
      // mis. cookie/proxy berbeda untuk file privat: ambil lewat HttpClient (sesi yang sama dengan API)
      try {
        const res = await HttpClient.get(url, { responseType: "blob" });
        if (wallpaper.value.kind === "image" && wallpaper.value.value === url) {
          wallpaperBlobUrl = URL.createObjectURL(res.data as Blob);
          wallpaperSrc.value = wallpaperBlobUrl;
        }
      } catch (err) {
        console.warn("Gambar latar tidak dapat dimuat", url, err);
      }
    };
    probe.src = url;
  },
  { immediate: true },
);
const wallpaperStyle = computed<Record<string, string>>(() =>
  wallpaper.value.kind === "image"
    ? { background: `#0b1e3f url("${(wallpaperSrc.value || wallpaper.value.value).replace(/"/g, '\\"')}") center / cover no-repeat` }
    : { background: presetCss(wallpaper.value.value) },
);

async function loadPrefs(attempt = 0) {
  try {
    const prefs = await getDesktopPrefs();
    wallpaper.value = prefs.wallpaper;
    iconLayouts.value = prefs.icon_layouts || {};
  } catch (err) {
    // jangan diam-diam kembali ke latar bawaan: pertahankan latar terakhir & coba lagi
    console.warn("Gagal memuat latar desktop", err);
    if (attempt < 3) setTimeout(() => loadPrefs(attempt + 1), 1500 * (attempt + 1));
  }
}

const ctxMenu = ref<{ x: number; y: number } | null>(null);

/** Klik kanan hanya di area kosong desktop (bukan ikon, jendela, taskbar, atau panel). */
function onContextMenu(e: MouseEvent) {
  const target = e.target as HTMLElement;
  if (target.closest(".os-icon, .os-window, .os-taskbar, .os-start, .os-notif, .os-ctx, .modal")) return;
  e.preventDefault();
  desktop.startOpen = false;
  notifOpen.value = false;
  const w = 220;
  const h = 205;
  ctxMenu.value = {
    x: Math.min(e.clientX, window.innerWidth - w - 8),
    y: Math.min(e.clientY, window.innerHeight - desktop.TASKBAR_HEIGHT - h - 8),
  };
}

function ctxAction(fn: () => unknown) {
  ctxMenu.value = null;
  fn();
}

function openWallpaper() {
  ctxMenu.value = null;
  wallpaperOpen.value = true;
}

function reloadPage() {
  window.location.reload();
}

async function toggleStart() {
  notifOpen.value = false;
  desktop.startOpen = !desktop.startOpen;
  if (desktop.startOpen) {
    await nextTick();
    searchInput.value?.focus();
  }
}

async function openSearch() {
  if (!desktop.startOpen) await toggleStart();
  else searchInput.value?.focus();
}

// ---------------------------------------------------------------- notifikasi
const notifOpen = ref(false);
const notifications = ref<AppNotification[]>([]);
const unread = ref(0);
let notifTimer: ReturnType<typeof setInterval> | undefined;

async function loadNotifications() {
  try {
    const res = await getMyNotifications(30);
    notifications.value = res.items;
    unread.value = res.unread;
  } catch {
    // tidak kritis
  }
}

function toggleNotif() {
  desktop.startOpen = false;
  notifOpen.value = !notifOpen.value;
  if (notifOpen.value) loadNotifications();
}

async function openNotification(n: AppNotification) {
  if (!n.read) {
    try {
      unread.value = (await markNotificationsRead([n.name])).unread;
      n.read = 1;
    } catch {
      // abaikan
    }
  }
  const target = resolveNotificationRoute(n, auth.effectiveRoleProfile);
  notifOpen.value = false;
  if (target && typeof target === "object" && "name" in target && target.name) {
    openRoute(String(target.name), (target.query as Record<string, string>) || {});
  }
}

async function markAll() {
  try {
    unread.value = (await markNotificationsRead()).unread;
    notifications.value.forEach((n) => (n.read = 1));
  } catch {
    // abaikan
  }
}

function plainText(html: string | null) {
  const doc = new DOMParser().parseFromString((html || "").replace(/<br\s*\/?>/gi, " · "), "text/html");
  return doc.body.textContent || "";
}

// ---------------------------------------------------------------- jam & sapaan
const now = ref(new Date());
let clockTimer: ReturnType<typeof setInterval> | undefined;
const time = computed(() => now.value.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }));
const shortDate = computed(() => now.value.toLocaleDateString("id-ID", { day: "2-digit", month: "2-digit", year: "numeric" }));
const fullDate = computed(() => now.value.toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long", year: "numeric" }));
const greeting = computed(() => {
  const h = now.value.getHours();
  return h < 11 ? "Selamat pagi" : h < 15 ? "Selamat siang" : h < 18 ? "Selamat sore" : "Selamat malam";
});
const firstName = computed(() => (auth.user?.fullName || "Pengguna").split(" ")[0]);
const initial = computed(() => (auth.user?.fullName || "U").charAt(0).toUpperCase());
const roleLabel = computed(() => {
  if (auth.isSuperAdministrator) return auth.viewAsRole ? `Admin · lihat ${auth.viewAsRole}` : "Admin";
  if (auth.user?.isSystemManager) return "System Manager";
  return auth.user?.roleProfile || "Pengguna";
});

// ---------------------------------------------------------------- Super Administrator
function switchView(value: string) {
  auth.setViewAsRole((value || null) as RoleProfile | null);
  desktop.closeAll();
}

async function changeMode(mode: UiMode) {
  if (mode === ui.mode) return;
  const answer = await Swal.fire({
    icon: "question",
    title: mode === "web" ? "Beralih ke tampilan Web?" : "Beralih ke tampilan Desktop?",
    text: "Mode tampilan berlaku untuk SEMUA pengguna.",
    showCancelButton: true,
    confirmButtonText: "Ya, ubah",
    cancelButtonText: "Batal",
  });
  if (!answer.isConfirmed) return;
  try {
    await ui.setMode(mode);
    desktop.startOpen = false;
    if (mode === "web") router.replace({ name: "home" });
  } catch (err) {
    Swal.fire({ icon: "error", title: "Gagal mengubah mode", text: String(err) });
  }
}

async function logout() {
  const answer = await Swal.fire({
    title: "Keluar dari SPI Digital System?",
    icon: "warning",
    showCancelButton: true,
    confirmButtonText: "Ya, keluar",
    cancelButtonText: "Batal",
  });
  if (!answer.isConfirmed) return;
  desktop.closeAll();
  await auth.logout();
}

// ---------------------------------------------------------------- tur panduan
type ActiveTour = { key: string; title: string; eyebrow: string; steps: TourStep[] };
const tourOpen = ref(false);
const tour = ref<ActiveTour | null>(null);

function welcomeTour(): ActiveTour {
  const groups = [...new Set(apps.value.map((a) => a.group).filter((g) => MENU_GROUPS.some((m) => m.label === g)))];
  return {
    key: WELCOME_GUIDE_KEY,
    title: "Selamat datang di SPI Digital System",
    eyebrow: roleLabel.value,
    steps: [
      { title: `Halo, ${auth.user?.fullName || "Pengguna"}!`, body: "Ini tampilan desktop SPI. Cara pakainya mirip komputer: ikon di desktop, jendela untuk setiap halaman, dan taskbar di bawah." },
      { target: "desktop.icons", placement: "right", title: "Ikon aplikasi", body: `Klik dua kali ikon untuk membuka halaman di jendela baru. Isi: ${groups.join(", ")}.` },
      { target: "desktop.start", placement: "top", title: "Menu Start", body: "Semua aplikasi, pencarian, halaman terakhir dibuka, dan tombol keluar ada di sini." },
      { target: "desktop.search", placement: "top", title: "Cari", body: "Ketik nama menu untuk membukanya cepat, atau cari jawaban di FAQ." },
      { target: "desktop.taskbar-windows", placement: "top", title: "Jendela terbuka", body: "Jendela yang sedang terbuka tampil di sini. Klik untuk berpindah atau meminimalkan." },
      { target: "desktop.bell", placement: "top", title: "Notifikasi", body: "Angka merah = notifikasi belum dibaca. Klik notifikasi untuk membuka halaman terkait." },
      { title: "Jendela", body: "Geser jendela lewat judulnya, ubah ukuran dari sudut kanan bawah, klik dua kali judul untuk memperbesar. Tombol ? di judul jendela memutar panduan halaman itu." },
    ],
  };
}

function pageTourFor(routeName: string): ActiveTour | null {
  const feature = findFeatureByRouteName(routeName);
  const key = routeName.startsWith("dashboard.") ? "dashboard" : feature?.id;
  if (!key) return null;
  const label = feature ? getFeatureLabel(feature, auth.effectiveRoleProfile) : "Dashboard";
  const steps: TourStep[] = PAGE_TOURS[key]?.length
    ? PAGE_TOURS[key]
    : feature
      ? [{ title: label, body: feature.description }, ...feature.steps.map((s) => ({ title: s.title, body: s.body }))]
      : [];
  return steps.length ? { key: `page.${key}`, title: `Panduan: ${label}`, eyebrow: label, steps } : null;
}

function show(t: ActiveTour | null) {
  if (!t || tourOpen.value) return;
  tour.value = t;
  tourOpen.value = true;
}

async function maybePageTour(routeName: string) {
  await onboarding.ensureLoaded();
  if (!onboarding.loaded || !onboarding.isSeen(WELCOME_GUIDE_KEY)) return;
  const t = pageTourFor(routeName);
  if (t && !onboarding.isSeen(t.key)) {
    await nextTick();
    show(t);
  }
}

function runPageTour(win: { id: string; routeName: string }) {
  desktop.focus(win.id);
  show(pageTourFor(win.routeName) ?? welcomeTour());
}

function replayWelcome() {
  show(welcomeTour());
}

async function replayGuides() {
  desktop.startOpen = false;
  try {
    await onboarding.reset();
  } catch {
    // abaikan
  }
  show(welcomeTour());
}

async function onTourDone() {
  const key = tour.value?.key;
  tour.value = null;
  if (key) await onboarding.markSeen(key);
}

// Router membuka jendela untuk navigasi dari dalam halaman (router.push / router-link di halaman).
watch(
  () => desktop.windows.length,
  (n, old) => {
    if (n > (old ?? 0)) {
      const latest = desktop.windows[desktop.windows.length - 1];
      if (latest) maybePageTour(latest.routeName);
    }
  },
);

/** Setelah login: buka Dashboard otomatis sekali per sesi, dalam posisi TIDAK dimaksimalkan (keputusan pemilik). */
function autoOpenDashboard() {
  const KEY = "spi_dashboard_autoopened";
  try {
    if (sessionStorage.getItem(KEY)) return;
    sessionStorage.setItem(KEY, "1");
  } catch {
    return;
  }
  const user = auth.user;
  if (!user) return;
  const route = auth.isSuperAdministrator && auth.viewAsRole
    ? getDashboardRouteName(auth.viewAsRole, false)
    : getDashboardRouteName(user.roleProfile, user.isSystemManager);
  if (!desktop.windows.some((w) => w.routeName === route)) desktop.openWindow(route, {}, { maximized: false });
}

onMounted(async () => {
  clockTimer = setInterval(() => (now.value = new Date()), 15_000);
  autoOpenDashboard();
  loadNotifications();
  loadPrefs();
  measureGrid();
  window.addEventListener("resize", measureGrid);
  notifTimer = setInterval(loadNotifications, 120_000);
  await onboarding.ensureLoaded();
  if (onboarding.loaded && !onboarding.isSeen(WELCOME_GUIDE_KEY)) show(welcomeTour());
});

onBeforeUnmount(() => {
  clearInterval(clockTimer);
  clearInterval(notifTimer);
  window.removeEventListener("resize", measureGrid);
  window.removeEventListener("pointermove", onIconPointerMove);
});
</script>

<style scoped>
.os-root {
  position: fixed;
  inset: 0;
  overflow: hidden;
  color: var(--bs-body-color);
}
.os-icons {
  position: absolute;
  top: 12px;
  left: 8px;
  right: 8px;
  bottom: calc(var(--os-taskbar-h) + 8px);
}
.os-icon {
  position: absolute;
  touch-action: none;
  transition: left 0.15s ease, top 0.15s ease;
  width: 104px;
  padding: 8px 4px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.7);
}
.os-icon:hover {
  background: rgba(255, 255, 255, 0.12);
}
.os-icon.dragging {
  transition: none;
  z-index: 5;
  opacity: 0.85;
  cursor: grabbing;
}
.os-icon.selected,
.os-icon:focus-visible {
  background: rgba(255, 255, 255, 0.22);
  border-color: rgba(255, 255, 255, 0.35);
  outline: none;
}
.os-icon-img {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: #fff;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3);
  text-shadow: none;
}
.os-icon-label {
  font-size: 12px;
  line-height: 1.2;
  text-align: center;
  overflow-wrap: break-word;
  hyphens: auto;
}

/* Taskbar */
.os-taskbar {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: var(--os-taskbar-h);
  display: flex;
  align-items: center;
  padding: 0 10px;
  background: rgba(243, 244, 246, 0.85);
  backdrop-filter: blur(24px);
  border-top: 1px solid rgba(0, 0, 0, 0.08);
  z-index: 10000;
  color: #111827;
}
.os-task-left {
  width: 220px;
  align-items: center;
}
.os-task-center {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.os-task-windows {
  display: flex;
  gap: 4px;
  overflow-x: auto;
  max-width: 60vw;
}
.os-task-right {
  display: flex;
  align-items: center;
  gap: 2px;
  justify-content: flex-end;
}
@media (min-width: 768px) {
  .os-task-right {
    width: 220px;
  }
}
.os-task-btn {
  position: relative;
  width: 40px;
  height: 40px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #111827;
  font-size: 19px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.os-task-btn:hover,
.os-task-btn.on {
  background: rgba(255, 255, 255, 0.85);
}
.os-task-win.open::after {
  content: "";
  position: absolute;
  bottom: 2px;
  left: 50%;
  width: 6px;
  height: 3px;
  margin-left: -3px;
  border-radius: 2px;
  background: #9ca3af;
}
.os-task-win.on::after {
  width: 16px;
  margin-left: -8px;
  background: var(--bs-primary, #176df8);
}
.os-task-win i {
  color: var(--bs-primary, #176df8);
}
.os-start-logo {
  width: 24px;
  height: 24px;
  object-fit: contain;
}
.os-badge {
  position: absolute;
  top: 2px;
  right: 0;
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  border-radius: 9px;
  background: #dc2626;
  color: #fff;
  font-size: 12px;
  line-height: 17px;
}
.os-clock {
  text-align: right;
  font-size: 11.5px;
  line-height: 1.3;
  padding: 2px 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: inherit;
}
.os-clock:hover {
  background: rgba(255, 255, 255, 0.35);
}

/* Menu Start */
.os-start {
  position: absolute;
  left: 50%;
  bottom: calc(var(--os-taskbar-h) + 10px);
  transform: translateX(-50%);
  width: min(640px, calc(100vw - 16px));
  max-height: calc(100vh - var(--os-taskbar-h) - 24px);
  display: flex;
  flex-direction: column;
  background: rgba(243, 244, 246, 0.94);
  backdrop-filter: blur(30px);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 10px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.35);
  z-index: 10001;
  color: #111827;
}
.os-start-search {
  margin: 20px 28px 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fff;
  border: 1px solid #d1d5db;
  border-radius: 999px;
  padding: 6px 16px;
}
.os-start-search input {
  border: 0;
  outline: 0;
  flex: 1;
  background: transparent;
  font-size: 14px;
}
.os-start-body {
  padding: 12px 28px 16px;
  overflow-y: auto;
}
.os-start-h {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
}
.os-start-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 4px;
}
.os-start-app {
  border: 0;
  background: transparent;
  border-radius: 6px;
  padding: 10px 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: #111827;
}
.os-start-app:hover {
  background: rgba(255, 255, 255, 0.9);
}
.os-start-app-icon {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}
.os-start-app-label {
  font-size: 12px;
  text-align: center;
  line-height: 1.2;
}
.os-start-recent {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 4px;
  margin-top: 8px;
}
.os-recent {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 0;
  background: transparent;
  border-radius: 6px;
  padding: 8px 10px;
  text-align: left;
  font-size: 13px;
  color: #111827;
}
.os-recent:hover {
  background: rgba(255, 255, 255, 0.9);
}
.os-start-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 28px;
  border-top: 1px solid rgba(0, 0, 0, 0.08);
  background: rgba(229, 231, 235, 0.7);
  border-radius: 0 0 10px 10px;
}
.os-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--bs-primary, #176df8);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  flex-shrink: 0;
}
.os-round {
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  font-size: 17px;
  color: #111827;
}
.os-round:hover {
  background: rgba(255, 255, 255, 0.9);
}
.min-w-0 {
  min-width: 0;
}

/* Notifikasi */
.os-notif {
  position: absolute;
  right: 10px;
  bottom: calc(var(--os-taskbar-h) + 10px);
  width: min(380px, calc(100vw - 20px));
  max-height: 60vh;
  display: flex;
  flex-direction: column;
  background: rgba(243, 244, 246, 0.96);
  backdrop-filter: blur(30px);
  border-radius: 10px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.35);
  z-index: 10001;
  color: #111827;
}
.os-notif-list {
  overflow-y: auto;
}
.os-notif-item {
  position: relative;
  display: block;
  width: 100%;
  text-align: left;
  border: 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  background: transparent;
  padding: 10px 16px 10px 28px;
}
.os-notif-item:hover {
  background: rgba(255, 255, 255, 0.9);
}
.os-notif-item.unread {
  background: rgba(23, 109, 248, 0.07);
}
.os-dot {
  position: absolute;
  left: 12px;
  top: 16px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--bs-primary, #176df8);
}

.os-ctx {
  position: absolute;
  z-index: 10002;
  min-width: 220px;
  margin: 0;
  padding: 6px;
  list-style: none;
  background: rgba(243, 244, 246, 0.96);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3);
  color: #111827;
  font-size: 13px;
}
.os-ctx li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 12px;
  border-radius: 5px;
  cursor: default;
}
.os-ctx li:hover,
.os-ctx li:focus {
  background: rgba(23, 109, 248, 0.1);
  outline: none;
}
.os-ctx li.sep {
  height: 1px;
  padding: 0;
  margin: 4px 6px;
  background: rgba(0, 0, 0, 0.1);
}
.os-ctx i {
  font-size: 16px;
  color: #475569;
}

.os-pop-enter-active,
.os-pop-leave-active {
  transition: all 0.18s ease;
}
.os-pop-enter-from,
.os-pop-leave-to {
  opacity: 0;
  transform: translate(-50%, 16px);
}
.os-notif.os-pop-enter-from,
.os-notif.os-pop-leave-to {
  transform: translateY(16px);
}

@media (max-width: 767.98px) {
  .os-icons {
    flex-direction: row;
    right: 8px;
  }
  .os-icon {
    width: calc(25% - 4px);
  }
}
</style>
