<template>
  <div class="topbar d-print-none">
    <div class="container-fluid px-3 px-lg-4">
      <nav
        class="topbar-custom d-flex justify-content-between align-items-center w-100"
        id="topbar-custom"
      >
        <ul
          class="topbar-item list-unstyled d-inline-flex align-items-center mb-0"
        >
          <li>
            <button
              class="nav-link mobile-menu-btn nav-icon"
              id="togglemenu"
              @click="toggleLeftSideBar"
            >
              <i class="iconoir-menu-scale"></i>
            </button>
          </li>
          <li class="mx-2 mx-md-3 welcome-text">
            <h5 class="mb-0 fw-bold text-truncate" style="max-width: 320px;" :title="`${greeting}, ${displayName}!`">
              {{ greeting }}, {{ displayName }}!
            </h5>
          </li>
        </ul>
        <ul
          class="topbar-item list-unstyled d-inline-flex align-items-center mb-0"
        >
          <li v-if="auth.isSuperAdministrator" class="topbar-item me-2" data-guide="layout.view-as">
            <select
              class="form-select form-select-sm"
              :value="auth.viewAsRole || ''"
              title="Lihat dashboard sebagai role lain (khusus admin)"
              aria-label="Lihat dashboard sebagai"
              @change="switchView(($event.target as HTMLSelectElement).value)"
            >
              <option value="">Admin</option>
              <option v-for="r in VIEW_AS_ROLES" :key="r" :value="r">Lihat sebagai: {{ r }}</option>
            </select>
          </li>
          <li class="hide-phone app-search" data-guide="layout.search">
            <form role="search" @submit.prevent="searchFaq">
              <input
                v-model="faqQuery"
                type="search"
                name="search"
                class="form-control top-search mb-0"
                placeholder="Cari di FAQ..."
                aria-label="Cari di FAQ"
              />
              <button type="submit" aria-label="Cari"><i class="iconoir-search"></i></button>
            </form>
          </li>
          <li class="topbar-item" data-guide="layout.calendar">
            <router-link class="nav-link nav-icon" :to="{ name: 'calendar' }" title="Kalender" aria-label="Kalender">
              <i class="iconoir-calendar"></i>
            </router-link>
          </li>
          <li class="topbar-item" data-guide="layout.help">
            <a
              class="nav-link nav-icon"
              href="javascript:void(0);"
              title="Panduan halaman ini"
              aria-label="Panduan halaman ini"
              @click="onboarding.requestReplay()"
            >
              <i class="iconoir-help-circle"></i>
            </a>
          </li>
          <li class="topbar-item">
            <a
              class="nav-link nav-icon"
              href="javascript:void(0);"
              id="light-dark-mode"
              @click="toggleTheme"
            >
              <i class="icofont-sun dark-mode"></i>
              <i class="icofont-moon light-mode"></i>
            </a>
          </li>

          <DropDown is="li" custom-class="topbar-item">
            <a
              class="nav-link dropdown-toggle arrow-none nav-icon"
              data-bs-toggle="dropdown"
              href="#"
              role="button"
              aria-haspopup="false"
              aria-expanded="false"
              data-guide="layout.bell"
              @click="loadNotifications"
            >
              <i class="icofont-bell-alt"></i>
              <span
                v-if="unreadCount > 0"
                class="position-absolute badge rounded-pill bg-danger notif-count"
                :aria-label="`${unreadCount} notifikasi belum dibaca`"
              >{{ unreadCount > 99 ? "99+" : unreadCount }}</span>
            </a>
            <div class="dropdown-menu stop dropdown-menu-end dropdown-lg py-0">
              <h5 class="dropdown-item-text m-0 py-3 d-flex justify-content-between align-items-center">
                Notifikasi
                <b-badge v-if="unreadCount > 0" :variant="null" class="bg-primary-subtle text-primary badge-pill">
                  {{ unreadCount }} belum dibaca
                </b-badge>
              </h5>
              <simplebar class="ms-0" style="max-height: 320px" data-simplebar>
                <div v-if="notifications.length === 0" class="text-center text-muted small py-4">Belum ada notifikasi.</div>
                <a
                  v-for="n in notifications"
                  :key="n.name"
                  href="javascript:void(0);"
                  class="dropdown-item py-3"
                  :class="{ 'bg-primary-subtle': !n.read }"
                  @click="readNotification(n)"
                >
                  <small class="float-end text-muted ps-2">{{ timeAgo(n.creation) }}</small>
                  <div class="d-flex align-items-start">
                    <div class="flex-shrink-0 bg-warning-subtle text-warning thumb-md rounded-circle">
                      <i class="iconoir-bell fs-4"></i>
                    </div>
                    <div class="flex-grow-1 ms-2" style="white-space: normal">
                      <h6 class="my-0 text-dark fs-13" :class="n.read ? 'fw-normal' : 'fw-semibold'">
                        <span v-if="!n.read" class="d-inline-block rounded-circle bg-primary me-1 unread-dot" title="Belum dibaca"></span>{{ n.subject }}
                      </h6>
                      <small class="text-muted mb-0 d-block">{{ plainText(n.email_content) }}</small>
                    </div>
                  </div>
                </a>
              </simplebar>
              <a
                v-if="unreadCount > 0"
                href="javascript:void(0);"
                class="dropdown-item text-center text-dark fs-13 py-2"
                @click="markAllRead"
              >
                Tandai semua dibaca
              </a>
            </div>
          </DropDown>

          <DropDown is="li" custom-class="topbar-item">
            <a
              class="nav-link dropdown-toggle arrow-none nav-icon"
              data-bs-toggle="dropdown"
              href="#"
              role="button"
              aria-haspopup="false"
              aria-expanded="false"
            >
              <img
                :src="profileImage"
                :alt="displayName"
                class="thumb-lg rounded-circle"
              />
            </a>
            <div class="dropdown-menu dropdown-menu-end py-0">
              <div
                class="d-flex align-items-center dropdown-item py-2 bg-secondary-subtle"
              >
                <div class="flex-shrink-0">
                  <img
                    :src="profileImage"
                    :alt="displayName"
                    class="thumb-md rounded-circle"
                  />
                </div>
                <div class="flex-grow-1 ms-2 text-truncate align-self-center">
                  <h6 class="my-0 fw-medium text-dark fs-13">
                    {{ displayName }}
                  </h6>
                  <small class="text-muted mb-0">{{ username }}</small>
                </div>
              </div>
              <div class="dropdown-divider mt-0"></div>
              <router-link class="dropdown-item" :to="{ name: 'help.faq' }">
                <i class="las la-question-circle fs-18 me-1 align-text-bottom"></i>
                FAQ &amp; Bantuan
              </router-link>
              <a class="dropdown-item" href="javascript:void(0);" @click="passwordModal.open = true">
                <i class="las la-key fs-18 me-1 align-text-bottom"></i>
                Ganti Password
              </a>
              <a class="dropdown-item" href="javascript:void(0);" @click="replayAllGuides">
                <i class="las la-route fs-18 me-1 align-text-bottom"></i>
                Tampilkan ulang semua panduan
              </a>
              <a v-if="isSuperAdministrator" class="dropdown-item" :href="deskUrl" target="_blank" rel="noopener">
                <i class="las la-external-link-alt fs-18 me-1 align-text-bottom"></i>
                Desk ERPNext
              </a>
              <a v-if="isSuperAdministrator" class="dropdown-item" href="javascript:void(0);" @click="switchToDesktop">
                <i class="las la-desktop fs-18 me-1 align-text-bottom"></i>
                Ganti ke tampilan Desktop
              </a>
              <div class="dropdown-divider mb-0"></div>
              <button
                type="button"
                class="dropdown-item text-danger"
                :disabled="isLoggingOut"
                @click="handleLogout"
              >
                <i class="las la-power-off fs-18 me-1 align-text-bottom"></i>
                {{ isLoggingOut ? "Keluar..." : "Keluar (Logout)" }}
              </button>
            </div>
          </DropDown>

          <li class="topbar-item ms-2">
            <button
              type="button"
              class="btn btn-sm btn-outline-danger d-flex align-items-center gap-1 py-1 px-2"
              title="Keluar dari Aplikasi"
              :disabled="isLoggingOut"
              @click="handleLogout"
            >
              <i class="las la-power-off fs-16"></i>
              <span class="d-none d-md-inline fs-12 fw-semibold">Keluar</span>
            </button>
          </li>
        </ul>
      </nav>
    </div>
  </div>
</template>
<script setup lang="ts">
import { passwordModal } from "@/features/account/api";
import { computed, ref, onMounted, onUnmounted } from "vue";
import simplebar from "simplebar-vue";
import Swal from "sweetalert2/dist/sweetalert2.js";
import DropDown from "@/components/DropDown.vue";
import { useLayoutStore } from "@/stores/layout";
import { useAuthStore } from "@/stores/auth";
import { getMyNotifications, markNotificationsRead, type AppNotification } from "@/features/notifications/api";
import { useRouter } from "vue-router";
import { resolveNotificationRoute } from "@/helpers/notification-route";
import { useOnboardingStore } from "@/stores/onboarding";
import { useUiStore } from "@/stores/ui";
import type { RoleProfile } from "@/types/auth";

const router = useRouter();

/** Dashboard yang dapat dilihat Super Administrator lewat "Lihat sebagai". */
const VIEW_AS_ROLES: RoleProfile[] = ["Branch Manager", "Principal", "Finance", "CSO", "Teacher", "Parent", "Student", "Staff Yayasan"];

function switchView(value: string) {
  auth.setViewAsRole((value || null) as RoleProfile | null);
  router.push({ name: "home" });
}
const onboarding = useOnboardingStore();
const ui = useUiStore();
const faqQuery = ref("");

function searchFaq() {
  router.push({ name: "help.faq", query: faqQuery.value.trim() ? { q: faqQuery.value.trim() } : {} });
}

/** Super Administrator: aktifkan mode tampilan desktop (Finto OS) untuk SEMUA pengguna. */
async function switchToDesktop() {
  const answer = await Swal.fire({
    icon: "question",
    title: "Beralih ke tampilan Desktop?",
    text: "Sistem akan tampil seperti sistem operasi (ikon, jendela, taskbar) untuk SEMUA pengguna. Dapat dikembalikan dari menu Start.",
    showCancelButton: true,
    confirmButtonText: "Ya, ubah",
    cancelButtonText: "Batal",
  });
  if (!answer.isConfirmed) return;
  try {
    await ui.setMode("desktop");
    router.replace({ name: "desktop.home" });
  } catch {
    Swal.fire({ icon: "error", title: "Gagal mengubah mode tampilan" });
  }
}

async function replayAllGuides() {
  try {
    await onboarding.reset();
    onboarding.requestReplay();
  } catch {
    // abaikan
  }
}

// Notifikasi in-app (Notification Log), mis. penggeseran / hangusnya bulan SPP prabayar
const notifications = ref<AppNotification[]>([]);
const unreadCount = ref(0);
let notificationTimer: ReturnType<typeof setInterval> | undefined;

async function loadNotifications() {
  try {
    const res = await getMyNotifications(20);
    notifications.value = res.items;
    unreadCount.value = res.unread;
  } catch {
    // notifikasi bukan fitur kritis: abaikan bila gagal dimuat
  }
}

async function readNotification(n: AppNotification) {
  if (!n.read) {
    try {
      unreadCount.value = (await markNotificationsRead([n.name])).unread;
      n.read = 1;
    } catch {
      // abaikan: tetap arahkan ke halaman terkait
    }
  }
  const target = resolveNotificationRoute(n, auth.effectiveRoleProfile);
  if (target) router.push(target);
}

async function markAllRead() {
  try {
    unreadCount.value = (await markNotificationsRead()).unread;
    notifications.value.forEach((n) => (n.read = 1));
  } catch {
    // abaikan
  }
}

function plainText(html: string | null) {
  // DOMParser tidak menjalankan skrip / event handler (aman untuk konten berisi input pengguna)
  const doc = new DOMParser().parseFromString((html || "").replace(/<br\s*\/?>/gi, " · "), "text/html");
  return doc.body.textContent || "";
}

function timeAgo(value: string) {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(value.replace(" ", "T")).getTime()) / 60000));
  if (minutes < 1) return "baru saja";
  if (minutes < 60) return `${minutes} mnt lalu`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} jam lalu`;
  return `${Math.round(minutes / 1440)} hari lalu`;
}
const isLoggingOut = ref(false);
const useLayout = useLayoutStore();
const auth = useAuthStore();
const { layout, setLeftSideBarSize } = useLayout;

const displayName = computed(() => auth.user?.fullName || "Pengguna");
const username = computed(() => auth.user?.username || "");
const isSuperAdministrator = computed(() => auth.user?.username === "Administrator");
const deskUrl = `${((import.meta.env.VITE_FRAPPE_URL as string | undefined) || "").replace(/\/$/, "")}/app/home`;
const profileImage = computed(() => auth.user?.userImage || avatar1);
const greeting = computed(() => {
  const hour = new Date().getHours();
  if (hour < 11) return "Selamat pagi";
  if (hour < 15) return "Selamat siang";
  if (hour < 18) return "Selamat sore";
  return "Selamat malam";
});

const handleLogout = async () => {
  const result = await Swal.fire({
    title: "Keluar dari SPI Digital System?",
    text: "Anda perlu login kembali untuk mengakses akun.",
    icon: "warning",
    showCancelButton: true,
    confirmButtonColor: "#176df8",
    cancelButtonColor: "#6c757d",
    confirmButtonText: "Ya, logout",
    cancelButtonText: "Batal",
    reverseButtons: true,
  });

  if (!result.isConfirmed) {
    return;
  }

  isLoggingOut.value = true;
  try {
    await auth.logout();
  } finally {
    isLoggingOut.value = false;
  }
};

const toggleTheme = () => {
  if (useLayout.layout.theme === "light") {
    return useLayout.setTheme("dark");
  }
  useLayout.setTheme("light");
};

const toggleLeftSideBar = () => {
  if (useLayout.layout.leftSideBarSize === "default") {
    return useLayout.setLeftSideBarSize("collapsed");
  }
  if (useLayout.layout.leftSideBarSize === "collapsed") {
    return useLayout.setLeftSideBarSize("default");
  }
};

const resize = () => {
  if (window.innerWidth < 1441) {
    setLeftSideBarSize("collapsed");
  } else {
    setLeftSideBarSize(
      layout.leftSideBarSize === "collapsed"
        ? "default"
        : layout.leftSideBarSize,
    );
  }
};

import avatar1 from "@/assets/images/users/avatar-1.jpg";

const windowScroll = () => {
  const navbar = document.getElementById("topbar-custom");
  if (navbar) {
    if (
      document.body.scrollTop >= 50 ||
      document.documentElement.scrollTop >= 50
    ) {
      navbar.classList.add("nav-sticky");
    } else {
      navbar.classList.remove("nav-sticky");
    }
  }
};

const leftSideBarClick = () => {
  window.addEventListener("click", (e: any) => {
    const startbar = document.getElementById("startbar");
    const togglemenu = document.getElementById("togglemenu");
    if (!(startbar && startbar.contains(e.target))) {
      if (window.innerWidth < 1441) {
        if (togglemenu && togglemenu.contains(e.target)) {
          setLeftSideBarSize("default");
        } else {
          setLeftSideBarSize("collapsed");
        }
      }
    }
  });
};

onMounted(() => {
  loadNotifications();
  notificationTimer = setInterval(loadNotifications, 120000);
  useLayout.init();
  resize();
  window.addEventListener("scroll", (ev) => {
    ev.preventDefault();
    windowScroll();
  });
  window.addEventListener("resize", () => {
    resize();
  });
  leftSideBarClick();
});

onUnmounted(() => {
  if (notificationTimer) clearInterval(notificationTimer);
});
</script>

<style scoped>
.notif-count {
  top: 4px;
  right: 0;
  font-size: 12px;
  min-width: 18px;
  padding: 3px 5px;
}
.unread-dot {
  width: 8px;
  height: 8px;
  vertical-align: middle;
}
</style>
