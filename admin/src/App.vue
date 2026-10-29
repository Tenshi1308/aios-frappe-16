<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue';
import {
  ApiError,
  checkHealth,
  fetchDashboard,
  fetchPendingInbox,
  fetchTotals,
  fetchUsersPage,
  loadSession,
  saveTheme,
  setUserStatus,
} from './api';
import type {
  AdminTheme,
  DashboardPayload,
  PendingInboxPayload,
  TotalsPayload,
  UsersPagePayload,
} from './types';
import { applyTheme } from '../../frontend/src/utils/theme';
import MetricsCards from './components/MetricsCards.vue';
import PagerBar from './components/PagerBar.vue';
import PendingTable from './components/PendingTable.vue';
import SiteTable from './components/SiteTable.vue';
import EkasaMark from '../../frontend/src/components/base/EkasaMark.vue';
import AppIcon from '../../frontend/src/components/base/AppIcon.vue';
import './styles/admin.css';

type Tab = 'sites' | 'users' | 'monitoring';

const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'sites', label: 'Site' },
  { key: 'users', label: 'Pengguna' },
  { key: 'monitoring', label: 'Monitoring' },
];

const THEME_ORDER: AdminTheme[] = ['Light', 'Automatic', 'Dark'];
const THEME_LABEL: Record<AdminTheme, string> = {
  Light: 'Terang',
  Automatic: 'Sistem',
  Dark: 'Gelap',
};

const activeTab = ref<Tab>('sites');
const loading = ref(true);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const data = ref<DashboardPayload | null>(null);
const themeSaving = ref(false);

const sitePage = ref(1);
const userPage = ref(1);
const userSite = ref<string>('');
const userFilter = ref<'pending' | 'all'>('pending');
const totalsData = ref<TotalsPayload | null>(null);
const totalsLoading = ref(false);
const usersData = ref<UsersPagePayload | null>(null);
const usersLoading = ref(false);
const siteNames = ref<string[]>([]);

const inboxOpen = ref(false);
const inboxPage = ref(1);
const inboxData = ref<PendingInboxPayload | null>(null);
const inboxLoading = ref(false);
const inboxDialog = ref<HTMLElement | null>(null);
const inboxTrigger = ref<HTMLElement | null>(null);

const inboxFrom = computed(() => {
  const d = inboxData.value;
  if (!d || !d.sites_total) return 0;
  return (d.site_page - 1) * d.site_page_size + 1;
});
const inboxTo = computed(() => {
  const d = inboxData.value;
  if (!d) return 0;
  return Math.min(d.site_page * d.site_page_size, d.sites_total);
});

const currentTheme = computed<AdminTheme>(() => data.value?.theme.value ?? 'Automatic');

function failureMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return 'Terjadi kesalahan tak terduga.';
}

async function refresh(options?: { clearNotice?: boolean }): Promise<void> {
  loading.value = true;
  error.value = null;
  if (options?.clearNotice !== false) {
    notice.value = null;
  }
  try {
    const dashboardData = await fetchDashboard(sitePage.value, 20);
    data.value = dashboardData;
    siteNames.value = dashboardData.sites.map((s) => s.site_name);
    if (!userSite.value && siteNames.value.length > 0) {
      userSite.value = siteNames.value[0];
    }
    if (dashboardData.theme?.value) {
      applyTheme(dashboardData.theme.value);
    }
  } catch (err) {
    data.value = null;
    error.value = failureMessage(err);
  } finally {
    loading.value = false;
  }
}

async function loadTotals(): Promise<void> {
  totalsLoading.value = true;
  try {
    totalsData.value = await fetchTotals();
  } catch (err) {
    error.value = failureMessage(err);
  } finally {
    totalsLoading.value = false;
  }
}

async function loadUsers(): Promise<void> {
  if (!userSite.value) {
    if (siteNames.value.length > 0) {
      userSite.value = siteNames.value[0];
    } else {
      usersData.value = null;
      return;
    }
  }
  usersLoading.value = true;
  try {
    const status = userFilter.value === 'pending' ? 'Pending Provisioning' : null;
    usersData.value = await fetchUsersPage(userSite.value, userPage.value, 20, status);
  } catch (err) {
    usersData.value = {
      site: userSite.value,
      users: [],
      total: 0,
      page: userPage.value,
      page_size: 20,
      total_pages: 1,
      error: failureMessage(err),
    };
  } finally {
    usersLoading.value = false;
  }
}

function onSelectTab(tab: Tab): void {
  activeTab.value = tab;
  if (tab === 'monitoring') {
    void loadTotals();
  } else if (tab === 'users') {
    void loadUsers();
  }
}

async function onSitePage(p: number): Promise<void> {
  sitePage.value = p;
  await refresh({ clearNotice: false });
}

async function onUserPage(p: number): Promise<void> {
  userPage.value = p;
  await loadUsers();
}

async function onUserSite(s: string): Promise<void> {
  userSite.value = s;
  userPage.value = 1;
  await loadUsers();
}

async function onUserFilter(f: 'pending' | 'all'): Promise<void> {
  userFilter.value = f;
  userPage.value = 1;
  await loadUsers();
}

async function loadInbox(): Promise<void> {
  inboxLoading.value = true;
  try {
    inboxData.value = await fetchPendingInbox(inboxPage.value, 20);
  } catch (err) {
    inboxData.value = {
      site_page: inboxPage.value,
      site_page_size: 20,
      sites_total: 0,
      sites_scanned: 0,
      total_pending: 0,
      entries: [],
      partial: false,
      error: failureMessage(err),
    };
  } finally {
    inboxLoading.value = false;
  }
}

async function closeInbox(): Promise<void> {
  inboxOpen.value = false;
  document.documentElement.style.overflow = '';
  await nextTick();
  inboxTrigger.value?.focus();
}

async function onOpenPendingFromInbox(site: string): Promise<void> {
  inboxOpen.value = false;
  document.documentElement.style.overflow = '';
  await onOpenPending(site);
}

async function onToggleInbox(): Promise<void> {
  inboxOpen.value = !inboxOpen.value;
  if (inboxOpen.value) {
    document.documentElement.style.overflow = 'hidden';
    inboxPage.value = 1;
    await loadInbox();
    await nextTick();
    inboxDialog.value?.focus();
  } else {
    await closeInbox();
  }
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape' && inboxOpen.value) void closeInbox();
}

async function onInboxPage(p: number): Promise<void> {
  inboxPage.value = p;
  await loadInbox();
}

async function onOpenPending(site: string): Promise<void> {
  userSite.value = site;
  userFilter.value = 'pending';
  userPage.value = 1;
  activeTab.value = 'users';
  inboxOpen.value = false;
  await loadUsers();
}

async function onReload(): Promise<void> {
  await refresh();
  if (activeTab.value === 'monitoring') {
    await loadTotals();
  } else if (activeTab.value === 'users') {
    await loadUsers();
  }
}

async function onSelectTheme(opt: AdminTheme): Promise<void> {
  if (themeSaving.value || opt === currentTheme.value) return;
  themeSaving.value = true;
  error.value = null;
  try {
    await saveTheme(opt);
    applyTheme(opt);
    if (data.value?.theme) {
      data.value.theme.value = opt;
    }
  } catch (err) {
    error.value = failureMessage(err);
  } finally {
    themeSaving.value = false;
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
    await refresh({ clearNotice: false });
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
    await loadUsers();
    await refresh({ clearNotice: false });
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
  if (activeTab.value === 'users') {
    await loadUsers();
  } else if (activeTab.value === 'monitoring') {
    await loadTotals();
  }
  window.addEventListener('keydown', onKeydown);
});

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown);
  document.documentElement.style.overflow = '';
});
</script>

<template>
  <div class="aios-admin wall">
    <div class="aios-admin-inner">
      <header class="aios-admin-header">
        <div class="aios-admin-brand">
          <EkasaMark :size="26" />
          <div>
            <h1 class="aios-admin-title">AIOS Admin</h1>
            <span class="aios-admin-sub">Developer Control Plane</span>
          </div>
        </div>
        <div class="aios-admin-tabs">
          <button
            v-for="tab in TABS"
            :key="tab.key"
            class="aios-admin-tab"
            :data-active="activeTab === tab.key"
            @click="onSelectTab(tab.key)"
          >
            {{ tab.label }}
          </button>
        </div>
        <div class="aios-admin-header-actions">
          <button
            ref="inboxTrigger"
            class="aios-admin-icon-btn"
            type="button"
            :disabled="inboxLoading"
            :aria-expanded="inboxOpen"
            aria-controls="aios-admin-inbox"
            aria-label="Lihat pengguna pending"
            title="Pengguna pending"
            @click="onToggleInbox()"
          >
            <AppIcon name="user-round-check" :size="16" />
          </button>
          <button
            class="aios-admin-icon-btn"
            type="button"
            :disabled="loading"
            aria-label="Muat ulang dashboard"
            title="Muat ulang"
            @click="onReload()"
          >
            <AppIcon name="refresh" :size="16" />
          </button>
          <div class="aios-admin-theme" role="radiogroup" aria-label="Tema tampilan">
            <button
              v-for="opt in THEME_ORDER"
              :key="opt"
              type="button"
              role="radio"
              class="aios-admin-theme-opt"
              :class="{ active: currentTheme === opt }"
              :aria-checked="currentTheme === opt"
              :disabled="themeSaving"
              @click="onSelectTheme(opt)"
            >
              {{ THEME_LABEL[opt] }}
            </button>
          </div>
        </div>
      </header>

      <div v-if="error" class="aios-admin-error" data-tone="error">{{ error }}</div>
      <div v-if="notice" class="aios-admin-error" data-tone="ok">{{ notice }}</div>

      <div v-if="activeTab === 'monitoring'">
        <div v-if="totalsLoading" class="aios-admin-muted aios-admin-loading">Memuat agregat semua site...</div>
        <template v-else-if="totalsData">
          <MetricsCards :totals="totalsData.totals" />
          <div
            v-if="totalsData.totals.sites_unreachable > 0"
            class="aios-admin-error aios-admin-unreachable-warn"
            data-tone="warn"
          >
            {{ totalsData.totals.sites_unreachable }} site tidak dapat dibaca; angka di atas tidak lengkap.
          </div>
        </template>
      </div>

      <section v-else-if="activeTab === 'sites'" class="aios-admin-surface">
        <template v-if="data">
          <SiteTable :sites="data.sites" @health="onHealth" @openPending="onOpenPending" />
          <PagerBar
            :page="data.pagination.page"
            :page-size="data.pagination.page_size"
            :total="data.pagination.total"
            :disabled="loading"
            @change="onSitePage"
          />
        </template>
        <div v-else-if="loading" class="aios-admin-muted aios-admin-loading">Memuat data dashboard...</div>
      </section>

      <section v-else-if="activeTab === 'users'" class="aios-admin-surface">
        <div v-if="usersData?.error" class="aios-admin-error" data-tone="error">{{ usersData.error }}</div>
        <PendingTable
          :users="usersData?.users ?? []"
          :site="userSite"
          :sites="siteNames"
          :filter="userFilter"
          @setStatus="onSetStatus"
          @changeSite="onUserSite"
          @changeFilter="onUserFilter"
        />
        <PagerBar
          :page="usersData?.page ?? 1"
          :page-size="usersData?.page_size ?? 20"
          :total="usersData?.total ?? 0"
          :disabled="usersLoading"
          @change="onUserPage"
        />
      </section>
    </div>

    <div
      v-if="inboxOpen"
      id="aios-admin-inbox"
      class="aios-admin-overlay"
      role="presentation"
      @click.self="closeInbox()"
    >
      <div
        ref="inboxDialog"
        class="aios-admin-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="aios-admin-inbox-title"
        tabindex="-1"
      >
        <header class="aios-admin-dialog-head">
          <h2 id="aios-admin-inbox-title" class="aios-admin-dialog-title">
            Pengguna pending
          </h2>
          <button
            class="aios-admin-icon-btn"
            type="button"
            aria-label="Tutup"
            title="Tutup"
            @click="closeInbox()"
          >
            <AppIcon name="x" :size="16" />
          </button>
        </header>

        <div class="aios-admin-dialog-body">
          <p class="aios-admin-muted">
            Memeriksa site {{ inboxFrom }}–{{ inboxTo }} dari
            {{ inboxData?.sites_total ?? 0 }} · {{ inboxData?.total_pending ?? 0 }} pending
          </p>
          <div v-if="inboxData?.error" class="aios-admin-error" data-tone="error">
            {{ inboxData.error }}
          </div>
          <div v-else-if="inboxLoading" class="aios-admin-muted aios-admin-loading">
            Memeriksa site...
          </div>
          <div v-else-if="!inboxData?.entries?.length" class="aios-admin-muted aios-admin-loading">
            Tidak ada pengguna pending di halaman site ini.
          </div>
          <div v-else class="aios-admin-table-wrap">
            <table class="aios-admin-table">
              <thead><tr><th>Site</th><th>Pending</th><th>Aksi</th></tr></thead>
              <tbody>
                <tr v-for="e in inboxData.entries" :key="e.site">
                  <td>{{ e.site }}</td>
                  <td><span class="aios-admin-badge" data-tone="warn">{{ e.pending_users }} pending</span></td>
                  <td>
                    <button
                      class="aios-admin-button"
                      type="button"
                      @click="onOpenPendingFromInbox(e.site)"
                    >
                      Buka
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="inboxData?.partial" class="aios-admin-error" data-tone="warn">
            Sebagian site punya lebih dari 1000 pengguna pending; daftar dipotong.
          </div>
        </div>

        <PagerBar
          :page="inboxData?.site_page ?? 1"
          :page-size="inboxData?.site_page_size ?? 20"
          :total="inboxData?.sites_total ?? 0"
          :disabled="inboxLoading"
          @change="onInboxPage"
        />
      </div>
    </div>
  </div>
</template>
