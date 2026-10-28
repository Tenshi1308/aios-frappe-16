<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { ApiError, checkHealth, fetchDashboard, loadSession, setUserStatus } from './api';
import type { DashboardPayload } from './types';
import MetricsCards from './components/MetricsCards.vue';
import PendingTable from './components/PendingTable.vue';
import SiteTable from './components/SiteTable.vue';
import './styles/admin.css';

type Tab = 'sites' | 'users' | 'monitoring';

const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'sites', label: 'Site' },
  { key: 'users', label: 'Pengguna' },
  { key: 'monitoring', label: 'Monitoring' },
];

const activeTab = ref<Tab>('sites');
const loading = ref(true);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const data = ref<DashboardPayload | null>(null);

function failureMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return 'Terjadi kesalahan tak terduga.';
}

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = null;
  notice.value = null;
  try {
    data.value = await fetchDashboard();
  } catch (err) {
    data.value = null;
    error.value = failureMessage(err);
  } finally {
    loading.value = false;
  }
}

async function onHealth(site: string): Promise<void> {
  error.value = null;
  notice.value = null;
  try {
    const payload = await checkHealth(site);
    notice.value = payload.ok
      ? `Site ${site} sehat. Terakhir dilihat diperbarui.`
      : `Cek kesehatan gagal: ${payload.last_error ?? 'tidak diketahui'}`;
    await refresh();
  } catch (err) {
    error.value = failureMessage(err);
  }
}

async function onSetStatus(payload: { site: string; user: string; status: string }): Promise<void> {
  error.value = null;
  notice.value = null;
  try {
    const result = await setUserStatus(payload.site, payload.user, payload.status);
    notice.value = result.ok
      ? `Pengguna ${payload.user} kini ${result.aios_status}.`
      : `Perubahan status gagal di site klien.`;
    await refresh();
  } catch (err) {
    error.value = failureMessage(err);
  }
}

onMounted(async () => {
  try {
    await loadSession();
  } catch (err) {
    error.value = failureMessage(err);
  }
  await refresh();
});
</script>

<template>
  <div class="aios-admin">
    <header class="aios-admin-header">
      <div>
        <h1 class="aios-admin-title">AIOS Admin</h1>
        <span class="aios-admin-sub">Developer Control Plane - aios-v16.localhost</span>
      </div>
      <div class="aios-admin-tabs">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          class="aios-admin-tab"
          :data-active="activeTab === tab.key"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>
      <button class="aios-admin-button" :disabled="loading" @click="refresh">Muat ulang</button>
    </header>

    <div v-if="error" class="aios-admin-error">{{ error }}</div>
    <div v-if="notice" class="aios-admin-error" data-tone="ok">{{ notice }}</div>

    <MetricsCards v-if="activeTab === 'monitoring'" :totals="data?.totals ?? null" />

    <SiteTable
      v-if="activeTab === 'sites' && data"
      :sites="data.sites"
      @health="onHealth"
    />

    <PendingTable
      v-if="activeTab === 'users' && data"
      :sites="data.sites"
      @set-status="onSetStatus"
    />

    <div v-if="loading" class="aios-admin-muted">Memuat data dashboard...</div>
  </div>
</template>
