<template>
  <TourGuide
    v-model="open"
    :title="active?.title || ''"
    :eyebrow="active?.eyebrow"
    :steps="active?.steps || []"
    :finish-label="active?.key === WELCOME_GUIDE_KEY ? 'Mulai bekerja' : 'Selesai'"
    @done="onDone"
  />
</template>

<script setup lang="ts">
/**
 * Tur panduan otomatis (menyorot elemen halaman, langkah demi langkah):
 *  1. Login pertama  -> tur "Selamat datang" (kunci `welcome`): sidebar, lonceng, panduan, pencarian, FAQ.
 *  2. Pertama kali membuka sebuah menu -> tur halaman (kunci `page.<feature id>`), langkah dari
 *     assets/data/page-tours.ts (target `data-guide`), cadangan: langkah teks di menu-catalog.ts.
 * Ikon "?" di TopBar memanggil onboarding.requestReplay() untuk memutar ulang tur halaman aktif.
 */
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import TourGuide, { type TourStep } from "./TourGuide.vue";
import { findFeatureByRouteName, getFeatureLabel, MENU_GROUPS } from "@/assets/data/menu-catalog";
import { PAGE_TOURS } from "@/assets/data/page-tours";
import { getMenuItems } from "@/helpers/menu";
import { useAuthStore } from "@/stores/auth";
import { useOnboardingStore, WELCOME_GUIDE_KEY } from "@/stores/onboarding";

type ActiveGuide = { key: string; title: string; eyebrow: string; steps: TourStep[] };

const route = useRoute();
const auth = useAuthStore();
const onboarding = useOnboardingStore();

const open = ref(false);
const active = ref<ActiveGuide | null>(null);

const roleName = computed(() => {
  if (auth.isSuperAdministrator) return auth.viewAsRole ? `Admin (lihat ${auth.viewAsRole})` : "Admin";
  if (auth.user?.isSystemManager) return "System Manager";
  return auth.user?.roleProfile || "Pengguna";
});

function welcomeGuide(): ActiveGuide {
  const groups = getMenuItems(auth.menuContext)
    .filter((m) => m.isTitle)
    .map((m) => m.label);
  const known = new Set(MENU_GROUPS.map((g) => g.label));
  return {
    key: WELCOME_GUIDE_KEY,
    title: "Selamat datang di SPI Digital System",
    eyebrow: roleName.value,
    steps: [
      {
        title: `Halo, ${auth.user?.fullName || "Pengguna"}!`,
        body: `Anda masuk sebagai ${roleName.value}. Tur singkat ini menunjukkan bagian-bagian penting aplikasi. Tekan Lanjut atau tombol panah kanan.`,
      },
      {
        target: "layout.sidebar",
        placement: "right",
        title: "Menu dikelompokkan per kategori",
        body: `Ini menu Anda, hanya berisi fitur yang boleh Anda pakai, dikelompokkan menjadi: ${groups.filter((g) => known.has(g)).join(", ")}. Arahkan kursor ke sebuah menu untuk melihat fungsinya.`,
      },
      {
        target: "layout.view-as",
        placement: "bottom",
        title: "Lihat sebagai role lain",
        body: "Khusus admin: pilih role untuk melihat menu dan dashboard role tersebut. Pilih \"Admin\" untuk kembali.",
      },
      {
        target: "layout.bell",
        placement: "bottom",
        title: "Notifikasi",
        body: "Angka merah menunjukkan notifikasi yang belum dibaca. Klik notifikasi untuk langsung membuka halaman terkait.",
      },
      {
        target: "layout.help",
        placement: "bottom",
        title: "Panduan halaman",
        body: "Saat pertama membuka sebuah menu, tur seperti ini akan muncul. Putar ulang kapan saja dengan ikon tanda tanya ini.",
      },
      {
        target: "layout.search",
        placement: "bottom",
        title: "Cari jawaban",
        body: "Ketik pertanyaan di sini untuk mencari di FAQ.",
      },
      {
        target: "layout.faq",
        placement: "right",
        title: "FAQ & Bantuan",
        body: "Kumpulan pertanyaan yang sering diajukan, dikelompokkan per topik.",
      },
    ],
  };
}

function tourKeyForRoute(): string | null {
  const name = (route.name as string | undefined) || "";
  if (name.startsWith("dashboard.")) return "dashboard";
  return findFeatureByRouteName(name)?.id ?? null;
}

function pageGuide(): ActiveGuide | null {
  const key = tourKeyForRoute();
  if (!key) return null;
  const feature = findFeatureByRouteName(route.name as string | undefined);
  const label = feature ? getFeatureLabel(feature, auth.effectiveRoleProfile) : "Dashboard";
  const group = feature ? MENU_GROUPS.find((g) => g.id === feature.group)?.label || "" : "Utama";
  const steps: TourStep[] = PAGE_TOURS[key]?.length
    ? PAGE_TOURS[key]
    : feature
      ? [{ title: label, body: feature.description }, ...feature.steps.map((s) => ({ title: s.title, body: s.body }))]
      : [];
  if (!steps.length) return null;
  return { key: `page.${key}`, title: `Panduan: ${label}`, eyebrow: `${group} · ${label}`, steps };
}

function show(guide: ActiveGuide | null) {
  if (!guide) return;
  active.value = guide;
  open.value = true;
}

async function maybeShow() {
  if (!auth.user || open.value) return;
  await onboarding.ensureLoaded();
  if (!onboarding.loaded) return;
  if (!onboarding.isSeen(WELCOME_GUIDE_KEY)) {
    show(welcomeGuide());
    return;
  }
  const guide = pageGuide();
  if (guide && !onboarding.isSeen(guide.key)) show(guide);
}

async function onDone() {
  const key = active.value?.key;
  if (!key) return;
  active.value = null;
  await onboarding.markSeen(key);
  // Setelah tur selamat datang selesai, lanjutkan tur halaman yang sedang dibuka.
  if (key === WELCOME_GUIDE_KEY) maybeShow();
}

watch(() => route.name, () => maybeShow());

watch(
  () => onboarding.replayRequest,
  () => {
    if (open.value) return;
    show(pageGuide() ?? welcomeGuide());
  },
);

onMounted(maybeShow);
</script>
