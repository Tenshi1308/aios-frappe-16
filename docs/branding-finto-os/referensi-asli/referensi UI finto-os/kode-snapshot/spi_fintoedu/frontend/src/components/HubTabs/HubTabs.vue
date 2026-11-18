<template>
  <nav v-if="tabs.length > 1" class="hub-tabs mb-3" :aria-label="`Bagian ${hub?.label}`" data-guide="layout.hub-tabs">
    <div class="d-flex align-items-center gap-2 flex-wrap">
      <span class="hub-title text-muted small fw-semibold text-uppercase me-1">
        <i :class="hub?.icon" class="me-1"></i>{{ hub?.label }}
      </span>
      <template v-for="t in tabs" :key="t.id">
        <!-- Di jendela desktop: ganti isi jendela; di mode web: pindah rute. -->
        <button
          v-if="win"
          type="button"
          class="hub-tab border-0"
          :class="{ active: t.routeName === currentRoute }"
          :title="t.description"
          :aria-current="t.routeName === currentRoute ? 'page' : undefined"
          @click="win.navigate(t.routeName)"
        >
          <i :class="t.icon" class="me-1"></i>{{ t.label }}
        </button>
        <router-link
          v-else
          :to="{ name: t.routeName }"
          class="hub-tab"
          :class="{ active: t.routeName === currentRoute }"
          :title="t.description"
          :aria-current="t.routeName === currentRoute ? 'page' : undefined"
        >
          <i :class="t.icon" class="me-1"></i>{{ t.label }}
        </router-link>
      </template>
    </div>
  </nav>
</template>

<script setup lang="ts">
/**
 * Tab antar halaman dalam satu hub (mis. Murid: Data Murid · Status Murid · Wali Murid · Mutasi).
 * Satu menu di sidebar, berpindah bagian lewat tab ini. Hanya bagian yang boleh dipakai role yang tampil.
 */
import { computed, inject } from "vue";
import { useRoute } from "vue-router";
import {
  findFeatureByRouteName,
  getFeatureLabel,
  getHub,
  getHubFeatures,
  getSuperAdminHubFeatures,
  getSuperAdminRoute,
} from "@/assets/data/menu-catalog";
import { useAuthStore } from "@/stores/auth";
import { DESKTOP_WINDOW } from "@/features/desktop/context";

const props = defineProps<{ routeName?: string | null }>();

const route = useRoute();
const win = inject(DESKTOP_WINDOW, null);
const auth = useAuthStore();

const currentRoute = computed(() => props.routeName ?? (route.name as string | undefined) ?? "");
const feature = computed(() => findFeatureByRouteName(currentRoute.value));
const hub = computed(() => getHub(feature.value?.hub));

const tabs = computed(() => {
  const role = auth.effectiveRoleProfile;
  if (!hub.value) return [];
  if (!role && auth.isSuperAdministrator) {
    // Super Administrator: semua bagian hub (rute role dengan hak terluas).
    return getSuperAdminHubFeatures(hub.value.id).map((f) => ({
      id: f.id,
      routeName: getSuperAdminRoute(f)!,
      label: f.tabLabel || f.label,
      icon: f.icon,
      description: f.description,
    }));
  }
  if (!role) return [];
  const ctx = { role, employmentCategory: auth.employment?.category ?? null };
  return getHubFeatures(hub.value.id, ctx).map((f) => ({
    id: f.id,
    routeName: f.routes[role]!,
    label: f.tabLabel || getFeatureLabel(f, role),
    icon: f.icon,
    description: f.description,
  }));
});
</script>

<style scoped>
.hub-tabs {
  border-bottom: 1px solid var(--bs-border-color);
  padding-bottom: 10px;
}
.hub-tab {
  display: inline-flex;
  align-items: center;
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 13px;
  color: var(--bs-body-color);
  background: var(--bs-tertiary-bg);
  text-decoration: none;
  transition: background 0.15s;
}
.hub-tab:hover {
  background: var(--bs-secondary-bg);
}
.hub-tab.active {
  background: var(--bs-primary);
  color: #fff;
}
</style>
