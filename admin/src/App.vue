<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import {
  ApiError,
  checkHealth,
  fetchDashboard,
  fetchSignupLeads,
  fetchTotals,
  fetchUsersPage,
  loadSession,
  saveTheme,
  setUserStatus,
} from './api';
import type {
  AdminTheme,
  DashboardPayload,
  SignupLead,
  TotalsPayload,
  UsersPagePayload,
} from './types';
import { applyTheme } from '../../frontend/src/utils/theme';
import MetricsCards from './components/MetricsCards.vue';
import PagerBar from './components/PagerBar.vue';
import PendingTable from './components/PendingTable.vue';
import SignupsTable from './components/SignupsTable.vue';
import SiteTable from './components/SiteTable.vue';
import EkasaMark from '../../frontend/src/components/base/EkasaMark.vue';
import AppIcon from '../../frontend/src/components/base/AppIcon.vue';
import './styles/admin.css';

type Tab = 'signups' | 'sites' | 'users';

const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'signups', label: 'Pendaftar' },
  { key: 'sites', label: 'Site' },
  { key: 'users', label: 'Pengguna' },
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

const signupsData = ref<SignupLead[]>([]);
const signupsLoading = ref(false);

const invitationModal = ref<{
  open: boolean;
  user: string;
  site: string;
  url: string;
  copied: boolean;
}>({
  open: false,
  user: '',
  site: '',
  url: '',
  copied: false,
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
    const payload = await fetchDashboard(sitePage.value, 20);
    data.value = payload;
    applyTheme(payload.theme.value);
    siteNames.value = payload.sites.map((s) => s.site_name);
    if (!userSite.value && siteNames.value.length > 0) {
      userSite.value = siteNames.value[0];
    }
  } catch (err) {
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
      usersData.value = {
        site: '',
        users: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 1,
        error: null,
      };
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
  if (tab === 'signups') {
    void loadSignups();
  } else if (tab === 'users') {
    void loadUsers();
  }
}

async function loadSignups(): Promise<void> {
  signupsLoading.value = true;
  try {
    signupsData.value = await fetchSignupLeads();
  } catch (err) {
    error.value = failureMessage(err);
  } finally {
    signupsLoading.value = false;
  }
}

async function copyInvitation(): Promise<void> {
  if (!invitationModal.value.url) return;
  try {
    await navigator.clipboard.writeText(invitationModal.value.url);
    invitationModal.value.copied = true;
    setTimeout(() => {
      invitationModal.value.copied = false;
    }, 2500);
  } catch {
    // fallback if clipboard API is not available
  }
}

function closeInvitationModal(): void {
  invitationModal.value.open = false;
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

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape') {
    if (invitationModal.value.open) closeInvitationModal();
  }
}

async function onOpenPending(site: string): Promise<void> {
  userSite.value = site;
  userFilter.value = 'pending';
  userPage.value = 1;
  activeTab.value = 'users';
  await loadUsers();
}

async function onReload(): Promise<void> {
  await Promise.all([refresh(), loadTotals()]);
  if (activeTab.value === 'signups') {
    await loadSignups();
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
    await Promise.all([refresh({ clearNotice: false }), loadTotals()]);
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
    if (result.ok && result.invitation_url) {
      invitationModal.value = {
        open: true,
        user: payload.user,
        site: payload.site,
        url: result.invitation_url,
        copied: false,
      };
    }
    await loadUsers();
    await Promise.all([refresh({ clearNotice: false }), loadTotals()]);
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
  await Promise.all([refresh(), loadTotals()]);
  if (activeTab.value === 'signups') {
    await loadSignups();
  } else if (activeTab.value === 'users') {
    await loadUsers();
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

      <!-- Top Summary Bar: Metrik Ringkas Sistem -->
      <div v-if="totalsData" class="aios-admin-top-summary">
        <MetricsCards :totals="totalsData.totals" />
        <div
          v-if="totalsData.totals.sites_unreachable > 0"
          class="aios-admin-error aios-admin-unreachable-warn"
          data-tone="warn"
        >
          {{ totalsData.totals.sites_unreachable }} site tidak dapat dibaca; angka di atas tidak lengkap.
        </div>
      </div>

      <section v-if="activeTab === 'signups'" class="aios-admin-surface">
        <SignupsTable :leads="signupsData" :loading="signupsLoading" />
      </section>

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
      v-if="invitationModal.open"
      class="aios-admin-overlay"
      role="presentation"
      @click.self="closeInvitationModal()"
    >
      <div
        class="aios-admin-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="invitation-dialog-title"
        tabindex="-1"
      >
        <header class="aios-admin-dialog-head">
          <h2 id="invitation-dialog-title" class="aios-admin-dialog-title">
            Tautan Undangan Berhasil Diterbitkan
          </h2>
          <button
            class="aios-admin-icon-btn"
            type="button"
            aria-label="Tutup"
            title="Tutup"
            @click="closeInvitationModal()"
          >
            <AppIcon name="x" :size="16" />
          </button>
        </header>

        <div class="aios-admin-dialog-body">
          <p>
            Akun <strong>{{ invitationModal.user }}</strong> pada site
            <strong>{{ invitationModal.site }}</strong> siap menerima password baru. Tautan resmi Frappe berikut
            bersifat <em>sekali pakai</em>:
          </p>
          <div class="aios-admin-invitation-card">
            <div class="aios-admin-invitation-row">
              <input
                type="text"
                readonly
                :value="invitationModal.url"
                class="aios-admin-invitation-input"
                @focus="($event.target as HTMLInputElement).select()"
              />
              <button
                class="aios-admin-button"
                data-variant="primary"
                type="button"
                @click="copyInvitation()"
              >
                {{ invitationModal.copied ? 'Tersalin!' : 'Salin Tautan' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
