<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { fetchBranches } from '../../api/branches';
import { useModulesStore } from '../../stores/modules';
import { useSessionStore } from '../../stores/session';
import type { ClientStaffUser, HandoffMode, SettingsBrand, SettingsTheme } from '../../types';
import { formatNumber } from '../../utils/format';
import { currentBrand, resolveTheme } from '../../utils/theme';
import AppIcon from '../base/AppIcon.vue';
import ErrorState from '../base/ErrorState.vue';
import FintoSelect from '../base/FintoSelect.vue';

type TabId =
  | 'general'
  | 'design'
  | 'conversation'
  | 'connector'
  | 'personalization'
  | 'receivers'
  | 'staff'
  | 'proactive';

interface MenuTab {
  id: TabId;
  label: string;
  icon: string;
}

const BASE_TABS: MenuTab[] = [
  { id: 'general', label: 'Umum', icon: 'gear' },
  { id: 'design', label: 'Desain', icon: 'desk' },
  { id: 'conversation', label: 'Percakapan', icon: 'arrow-right' },
  { id: 'connector', label: 'Konektor', icon: 'link' },
  { id: 'personalization', label: 'Personalisasi', icon: 'sparkle' },
];

const OWNER_TABS: MenuTab[] = [
  { id: 'receivers', label: 'Penerima Kanal', icon: 'bell' },
  { id: 'staff', label: 'Kelola Staf', icon: 'users' },
];

// D11: tab Insight Proaktif hanya muncul selama ada bidang aktif yang punya
// proaktif. Daftarnya datang dari server (settings.proactive_branches).
const PROACTIVE_TAB: MenuTab = {
  id: 'proactive',
  label: 'Insight Proaktif',
  icon: 'sparkle',
};

const THEME_LABELS: Record<SettingsTheme, string> = {
  Automatic: 'Ikuti sistem',
  Light: 'Terang',
  Dark: 'Gelap',
};

const THEME_ICONS: Record<SettingsTheme, string> = {
  Automatic: 'desk',
  Light: 'sun',
  Dark: 'moon',
};

const PERSONA_OPTIONS = [
  { value: 'sales', label: 'Sales' },
  { value: 'finance', label: 'Finance' },
  { value: 'accounting', label: 'Accounting' },
  { value: 'purchasing', label: 'Purchasing' },
  { value: 'operations', label: 'Operations' },
  { value: 'executive', label: 'Executive' },
  { value: 'system', label: 'System' },
];

const modules = useModulesStore();
const session = useSessionStore();

const isClientOwner = computed(() =>
  (session.context?.roles ?? []).includes('AIOS Client Owner'),
);

// D11: kelompok bidang yang punya proaktif; tab tampil bila daftar tidak kosong.
const proactiveGroups = computed(() => modules.settings?.proactive_branches ?? []);
const hasProactiveBranch = computed(() => proactiveGroups.value.length > 0);

// Batch D (Gap 4): fitur Telegram melekat pada bidang Sales (keputusan Ten).
// Sumber status: fetchBranches -> list_branches dengan flag `enabled` per
// cabang — bukan proactive_branches yang berarti "bidang berproaktif". Gagal
// memuat katalog dianggap tidak tersedia (fail-closed); backend tetap yang
// menolak dengan pesan resminya.
const salesBranchActive = ref(true);
const telegramDisabled = computed(() => !salesBranchActive.value);

async function loadSalesBranchActive() {
  try {
    const branches = await fetchBranches();
    const sales = branches.find((b) => b.key === 'sales');
    salesBranchActive.value = sales ? sales.enabled === true : false;
  } catch {
    salesBranchActive.value = false;
  }
}

const visibleTabs = computed<MenuTab[]>(() => {
  if (!isClientOwner.value) return BASE_TABS;
  const tabs = [...BASE_TABS, ...OWNER_TABS];
  if (hasProactiveBranch.value) tabs.push(PROACTIVE_TAB);
  return tabs;
});

const activeTab = ref<TabId>(modules.settingsTab || 'general');

// Tab yang dipilih lewat openSettings() harus ikut memuat datanya, bukan hanya saat diklik.
watch(
  activeTab,
  (tab) => {
    if (tab === 'proactive' && hasProactiveBranch.value) {
      void modules.loadDetectorSchedules();
    }
  },
  { immediate: true },
);
const tabRefs = ref<HTMLElement[]>([]);

watch(
  () => modules.settingsTab,
  (nextTab) => {
    if (nextTab && visibleTabs.value.some((t) => t.id === nextTab)) {
      activeTab.value = nextTab;
    }
  },
);

const HANDOFF_MODE_OPTIONS: Array<{ value: HandoffMode; label: string; description: string }> = [
  {
    value: 'confirm',
    label: 'Minta konfirmasi dulu',
    description: 'Tampilkan tombol persetujuan di chat sebelum berpindah ke tab cabang tujuan.',
  },
  {
    value: 'auto',
    label: 'Otomatis langsung pindah',
    description: 'Langsung alihkan tab ke cabang tujuan dan kirim ulang pertanyaan asli Anda.',
  },
];

const BRAND_OPTIONS: Array<{ value: SettingsBrand; label: string; description: string }> = [
  {
    value: 'finto',
    label: 'Finto Desk',
    description: 'Shell dan taskbar navy Finto OS, maskot Fino, serta jendela mengikuti Mode Warna.',
  },
  {
    value: 'ekasa',
    label: 'Ekasa Desk',
    description: 'Desain klasik Ekasa dengan aksen emas hangat dan mark geometris.',
  },
];

const currentBrandValue = computed<SettingsBrand>(
  () => modules.brandSettings?.brand.value ?? currentBrand.value,
);

function selectBrand(brand: SettingsBrand) {
  if (modules.brandSettingsSaving || currentBrandValue.value === brand) return;
  void modules.setBrand(brand);
}

const currentHandoffMode = computed<HandoffMode>(
  () => modules.conversationSettings?.handoff_mode.value ?? 'confirm',
);

function selectHandoffMode(mode: HandoffMode) {
  if (modules.conversationSettingsSaving || currentHandoffMode.value === mode) return;
  void modules.setHandoffMode(mode);
}

function setTabRef(el: any, index: number) {
  if (el) {
    tabRefs.value[index] = el as HTMLElement;
  }
}

function selectTab(id: TabId) {
  activeTab.value = id;
  if ((id === 'receivers' || id === 'staff') && isClientOwner.value && !modules.staffData) {
    void modules.loadClientStaffAndRecipients();
  }
  if (id === 'proactive' && hasProactiveBranch.value) {
    void modules.loadDetectorSchedules();
  }
}

function onTabKeydown(e: KeyboardEvent, index: number) {
  const tabs = visibleTabs.value;
  let targetIndex = index;
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    targetIndex = (index + 1) % tabs.length;
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    targetIndex = (index - 1 + tabs.length) % tabs.length;
  } else if (e.key === 'Home') {
    e.preventDefault();
    targetIndex = 0;
  } else if (e.key === 'End') {
    e.preventDefault();
    targetIndex = tabs.length - 1;
  } else {
    return;
  }
  const nextTab = tabs[targetIndex];
  if (nextTab) {
    selectTab(nextTab.id);
    tabRefs.value[targetIndex]?.focus();
  }
}

const data = computed(() => modules.settings);
const loading = computed(() => modules.settingsLoading);
const error = computed(() => modules.settingsError);
const themeSaving = computed(() => modules.themeSaving);

function themeLabel(opt: SettingsTheme): string {
  return THEME_LABELS[opt];
}

function themeIcon(opt: SettingsTheme): string {
  return THEME_ICONS[opt];
}

const activeThemeBadge = computed(() => {
  if (themeSaving.value) return 'Menyimpan…';
  const current = data.value?.theme.value;
  if (!current) return '';
  const resolved = resolveTheme(current);
  return resolved === 'dark' ? THEME_LABELS.Dark : THEME_LABELS.Light;
});

function selectTheme(opt: SettingsTheme) {
  if (themeSaving.value || data.value?.theme.value === opt) return;
  void modules.setTheme(opt);
}

const remainingSeconds = ref<number | null>(null);
let countdownTimer: ReturnType<typeof setInterval> | null = null;

function syncRemainingFromStore() {
  const reset = data.value?.reset;
  if (!reset || reset.source === 'unknown' || !reset.at || reset.seconds_remaining === null) {
    remainingSeconds.value = null;
    return;
  }
  remainingSeconds.value = Math.max(0, Math.trunc(reset.seconds_remaining));
}

watch(
  () => data.value?.reset,
  () => {
    syncRemainingFromStore();
  },
  { immediate: true },
);

onMounted(() => {
  if (!data.value && !loading.value) {
    void modules.loadSettings(true);
  }
  void modules.loadBrandSettings(true);
  void modules.loadConversationSettings(true);
  void modules.loadTelegramStatus();
  void loadSalesBranchActive();
  if (isClientOwner.value) {
    void modules.loadClientStaffAndRecipients();
  }
  syncRemainingFromStore();
  countdownTimer = setInterval(() => {
    if (remainingSeconds.value !== null && remainingSeconds.value > 0) {
      remainingSeconds.value = Math.max(0, remainingSeconds.value - 1);
    }
  }, 1000);
});

onUnmounted(() => {
  if (countdownTimer !== null) {
    clearInterval(countdownTimer);
    countdownTimer = null;
  }
});

const progressPercent = computed(() => {
  const pct = data.value?.quota.percent_used;
  if (pct === null || typeof pct !== 'number' || !Number.isFinite(pct)) return 0;
  return Math.min(100, Math.max(0, pct));
});

const quotaBarState = computed(() => {
  const pct = data.value?.quota.percent_used;
  if (pct === null || typeof pct !== 'number') return 'normal';
  if (pct >= 100) return 'danger';
  if (pct >= 80) return 'warn';
  return 'normal';
});

const isResetUnscheduled = computed(() => {
  const reset = data.value?.reset;
  return !reset || reset.source === 'unknown' || !reset.at || remainingSeconds.value === null;
});

const isWaitingNextReset = computed(() => {
  return !isResetUnscheduled.value && remainingSeconds.value === 0;
});

const countdownText = computed(() => {
  const secs = remainingSeconds.value;
  if (secs === null || secs <= 0) return '';
  const hours = Math.floor(secs / 3600);
  const minutes = Math.floor((secs % 3600) / 60);
  return `${hours} jam ${minutes} menit lagi`;
});

function refresh() {
  void modules.loadSettings(true);
  void modules.loadBrandSettings(true);
  void modules.loadConversationSettings(true);
  void modules.loadTelegramStatus();
  void loadSalesBranchActive();
  if (isClientOwner.value) {
    void modules.loadClientStaffAndRecipients();
  }
}

const copySuccess = ref(false);

async function handleGenerateTelegram() {
  // Batch D (Gap 4): Sales mati -> tidak ada token baru; backend juga menolak.
  if (telegramDisabled.value) return;
  await modules.generateTelegramLink();
}

async function handleCopyLink() {
  if (!modules.telegramDeepLink) return;
  try {
    await navigator.clipboard.writeText(modules.telegramDeepLink);
    copySuccess.value = true;
    setTimeout(() => {
      copySuccess.value = false;
    }, 2500);
  } catch {
    copySuccess.value = true;
  }
}

function handleOpenTelegram() {
  if (!modules.telegramDeepLink) return;
  window.open(modules.telegramDeepLink, '_blank');
}

async function handleUnlink() {
  await modules.unlinkTelegram();
}

// Personalisasi (company_context_persona)
const personaDraft = ref('');
const personaSaving = ref(false);
const personaSaved = ref(false);
const personaError = ref('');

watch(
  () => data.value?.company_context_persona,
  (val) => {
    personaDraft.value = val ?? '';
  },
  { immediate: true },
);

const isPersonaDirty = computed(() => {
  const serverVal = data.value?.company_context_persona ?? '';
  return personaDraft.value !== serverVal;
});

function resetPersonaDraft() {
  personaDraft.value = data.value?.company_context_persona ?? '';
  personaError.value = '';
}

async function handleSavePersona() {
  if (personaSaving.value || !isPersonaDirty.value) return;
  personaSaving.value = true;
  personaError.value = '';
  personaSaved.value = false;
  try {
    await modules.saveCompanyPersona(personaDraft.value);
    personaSaved.value = true;
    setTimeout(() => {
      personaSaved.value = false;
    }, 2500);
  } catch (err: unknown) {
    personaError.value = err instanceof Error ? err.message : 'Gagal menyimpan konteks perusahaan.';
  } finally {
    personaSaving.value = false;
  }
}

// Penerima Kanal & Kelola Staf (AIOS Client Owner)
const activeClientUsers = computed<ClientStaffUser[]>(() =>
  (modules.staffData?.users ?? []).filter((u) => u.enabled && u.status === 'Active'),
);

const newStaffName = ref('');
const newStaffEmail = ref('');
const newStaffPersona = ref('sales');
const newStaffInvitationUrl = ref('');
const newStaffCreatedFor = ref('');
const inviteCopied = ref(false);

async function handleToggleReceiver(user: ClientStaffUser) {
  if (modules.staffLoading) return;
  try {
    await modules.toggleChannelReceiver(user.user, !user.is_channel_receiver);
  } catch {
    // Error sudah diset di modules.staffError
  }
}

async function handleCreateStaff() {
  if (modules.staffLoading) return;
  const fullName = newStaffName.value.trim();
  const email = newStaffEmail.value.trim();
  if (!fullName || !email) return;
  try {
    const res = await modules.addClientStaff({
      email,
      full_name: fullName,
      persona: newStaffPersona.value,
    });
    newStaffInvitationUrl.value = res.invitation_url;
    newStaffCreatedFor.value = res.user;
    newStaffName.value = '';
    newStaffEmail.value = '';
    inviteCopied.value = false;
  } catch {
    // Error sudah diset di modules.staffError
  }
}

async function handleCopyInviteUrl() {
  if (!newStaffInvitationUrl.value) return;
  try {
    await navigator.clipboard.writeText(newStaffInvitationUrl.value);
    inviteCopied.value = true;
    setTimeout(() => {
      inviteCopied.value = false;
    }, 2500);
  } catch {
    inviteCopied.value = true;
  }
}

async function handleRegenerateInvite(user: ClientStaffUser) {
  if (modules.staffLoading) return;
  try {
    const res = await modules.regenerateStaffInvite(user.user);
    newStaffInvitationUrl.value = res.invitation_url;
    newStaffCreatedFor.value = res.user;
    inviteCopied.value = false;
  } catch {
    // Error sudah diset di modules.staffError
  }
}

async function handleToggleStaffStatus(user: ClientStaffUser) {
  if (modules.staffLoading || user.is_client_owner) return;
  const nextStatus = user.status === 'Active' ? 'Suspended' : 'Active';
  try {
    await modules.changeClientStaffStatus(user.user, nextStatus);
  } catch {
    // Error sudah diset di modules.staffError
  }
}
// --- K9: tab Insight Proaktif ---
const detectorRows = computed(() => modules.detectorSchedules?.detectors ?? []);

// D11: satu bagian per bidang yang punya proaktif. Bagian Sales hilang saat
// Sales dimatikan; tab tetap ada selama bidang lain masih punya proaktif.
// Semua detektor hari ini milik Sales, jadi bagian lain belum punya baris.
const proactiveSections = computed(() =>
  proactiveGroups.value.map((group) => ({
    ...group,
    detectors: group.branch === 'sales' ? detectorRows.value : [],
  })),
);
const detectorFrequencies = computed(
  () => modules.detectorSchedules?.frequencies ?? ['daily', 'weekly', 'monthly'],
);
const detectorDays = computed(
  () =>
    modules.detectorSchedules?.days ??
    ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
);

const FREQUENCY_LABELS: Record<string, string> = {
  daily: 'Harian',
  weekly: 'Mingguan',
  monthly: 'Bulanan',
};

const DAY_LABELS: Record<string, string> = {
  Monday: 'Senin',
  Tuesday: 'Selasa',
  Wednesday: 'Rabu',
  Thursday: 'Kamis',
  Friday: 'Jumat',
  Saturday: 'Sabtu',
  Sunday: 'Minggu',
};

// Opsi dropdown dibangun sekali; tiap info hanya tampil sekali di kartu.
const frequencyOptions = computed(() =>
  detectorFrequencies.value.map((f) => ({ value: f, label: FREQUENCY_LABELS[f] ?? f })),
);

const hourOptions = Array.from({ length: 24 }, (_, h) => ({
  value: h,
  label: `${String(h).padStart(2, '0')}:00`,
}));

function dayOptions(row: { day_of_week: string }) {
  const days = detectorDays.value;
  const list = row.day_of_week && !days.includes(row.day_of_week) ? [row.day_of_week, ...days] : days;
  return list.map((d) => ({ value: d, label: DAY_LABELS[d] ?? d }));
}

function patchDetector(index: number, patch: Record<string, unknown>) {
  const rows = detectorRows.value.map((row, i) => (i === index ? { ...row, ...patch } : row));
  void modules.saveDetectorSchedule(rows);
}
</script>

<template>
  <div class="settings-win">
    <ErrorState
      v-if="error"
      :message="error"
      container-class="settings-error"
      button-class="settings-retry-btn"
      icon-only
      :icon-size="14"
      @retry="refresh"
    />

    <div v-if="loading && !data" class="settings-state is-loading">
      Memuat pengaturan site…
    </div>

    <div v-else-if="data" class="settings-body">
      <!-- Menu Kiri -->
      <aside class="settings-nav" aria-label="Navigasi Pengaturan">
        <div
          class="settings-nav-list"
          role="tablist"
          aria-orientation="vertical"
          aria-label="Menu Pengaturan"
        >
          <button
            v-for="(tab, i) in visibleTabs"
            :key="tab.id"
            :ref="(el) => setTabRef(el, i)"
            :id="'settings-tab-' + tab.id"
            type="button"
            role="tab"
            class="settings-nav-item"
            :class="{ active: activeTab === tab.id }"
            :aria-selected="activeTab === tab.id"
            :aria-controls="'settings-panel-' + tab.id"
            :tabindex="activeTab === tab.id ? 0 : -1"
            @click="selectTab(tab.id)"
            @keydown="onTabKeydown($event, i)"
          >
            <AppIcon :name="tab.icon" :size="16" />
            <span>{{ tab.label }}</span>
          </button>
        </div>

        <div class="settings-nav-footer">
          <button
            type="button"
            class="settings-refresh-btn"
            :disabled="loading"
            aria-label="Muat ulang pengaturan"
            title="Muat ulang pengaturan"
            @click="refresh"
          >
            <AppIcon name="refresh" :size="15" :class="{ spin: loading }" />
          </button>
        </div>
      </aside>

      <!-- Panel Konten Kanan -->
      <main
        class="settings-pane"
        role="tabpanel"
        :id="'settings-panel-' + activeTab"
        :aria-labelledby="'settings-tab-' + activeTab"
        tabindex="0"
      >
        <Transition name="t-tab" mode="out-in">
        <!-- Halaman UMUM -->
        <div v-if="activeTab === 'general'" key="general" class="settings-sections">
          <!-- Profil Pengguna -->
          <section class="settings-card" aria-label="Profil pengguna">
            <div class="card-head">
              <h5>Profil pengguna</h5>
              <span class="status-pill">{{ data.profile.status }}</span>
            </div>
            <dl class="meta-grid">
              <div class="meta-item">
                <dt>Nama</dt>
                <dd>{{ data.profile.name }}</dd>
              </div>
              <div class="meta-item">
                <dt>Persona</dt>
                <dd>{{ data.profile.persona ?? '—' }}</dd>
              </div>
              <div class="meta-item">
                <dt>Status</dt>
                <dd>{{ data.profile.status }}</dd>
              </div>
            </dl>
          </section>

          <!-- Tema Tampilan -->
          <section class="settings-card" aria-label="Tema tampilan">
            <div class="card-head">
              <h5>Tema tampilan</h5>
              <span class="theme-pill">{{ activeThemeBadge }}</span>
            </div>
            <div class="theme-group" role="radiogroup" aria-label="Pilihan tema tampilan">
              <button
                v-for="opt in data.theme.options"
                :key="opt"
                type="button"
                role="radio"
                class="theme-opt-btn"
                :class="{ active: data.theme.value === opt }"
                :aria-checked="data.theme.value === opt"
                :aria-label="themeLabel(opt)"
                :title="themeLabel(opt)"
                :disabled="themeSaving"
                @click="selectTheme(opt)"
              >
                <AppIcon :name="themeIcon(opt)" :size="16" />
              </button>
            </div>
          </section>

          <!-- Company Aktif -->
          <section class="settings-card" aria-label="Company aktif">
            <div class="card-head">
              <h5>Company aktif</h5>
              <span class="currency-pill">{{ data.company.currency }}</span>
            </div>
            <dl class="meta-grid">
              <div class="meta-item">
                <dt>Nama company</dt>
                <dd>{{ data.company.name }}</dd>
              </div>
              <div class="meta-item">
                <dt>Mata uang</dt>
                <dd>{{ data.company.currency }}</dd>
              </div>
            </dl>
          </section>

          <!-- Kuota Site -->
          <section class="settings-card" aria-label="Kuota site">
            <div class="card-head">
              <h5>Kuota site</h5>
              <span v-if="data.quota.percent_used !== null" class="quota-pct">
                {{ formatNumber(data.quota.percent_used) }}%
              </span>
            </div>

            <div
              class="quota-bar-track"
              role="progressbar"
              aria-label="Pemakaian kuota site"
              :aria-valuenow="progressPercent"
              aria-valuemin="0"
              aria-valuemax="100"
            >
              <div
                class="quota-bar-fill"
                :data-state="quotaBarState"
                :style="{ width: `${progressPercent}%` }"
              />
            </div>

            <dl class="meta-grid quota-grid">
              <div class="meta-item">
                <dt>Terpakai / limit</dt>
                <dd class="mono">
                  {{ formatNumber(data.quota.used) }} /
                  {{ data.quota.limit > 0 ? formatNumber(data.quota.limit) : '—' }} token
                </dd>
              </div>
              <div class="meta-item">
                <dt>Sisa kuota site</dt>
                <dd class="mono">
                  {{ data.quota.remaining !== null ? `${formatNumber(data.quota.remaining)} token` : '—' }}
                </dd>
              </div>
            </dl>
          </section>

          <!-- Reset Kuota Site -->
          <section class="settings-card" aria-label="Reset kuota site">
            <div class="card-head">
              <h5>Jadwal reset kuota site</h5>
            </div>

            <div v-if="isResetUnscheduled" class="reset-warn" role="status">
              Reset belum terjadwal
            </div>
            <div v-else-if="isWaitingNextReset" class="reset-info" role="status">
              <b>Menunggu reset berikutnya</b>
              <span v-if="data.reset.at_label" class="reset-time">pukul {{ data.reset.at_label }}</span>
            </div>
            <div v-else class="reset-info" role="status">
              <b>{{ countdownText }}</b>
              <span v-if="data.reset.at_label" class="reset-time">pukul {{ data.reset.at_label }}</span>
            </div>
          </section>
        </div>

        <!-- Halaman DESAIN -->
        <div v-else-if="activeTab === 'design'" key="design" class="settings-sections">
          <section class="settings-card" aria-label="Pilihan desain tampilan">
            <div class="card-head">
              <div class="card-title-wrap">
                <AppIcon name="desk" :size="16" />
                <h5>Desain tampilan</h5>
              </div>
              <span v-if="modules.brandSettingsSaving" class="save-status-pill">Menyimpan…</span>
              <span v-else class="status-pill">
                {{ currentBrandValue === 'finto' ? 'Finto Desk' : 'Ekasa Desk' }}
              </span>
            </div>

            <p class="tg-info-text">
              Pilih identitas visual desktop. Mode Warna (Otomatis, Terang, atau Gelap) tetap diatur terpisah pada halaman Umum.
            </p>

            <div class="handoff-options" role="radiogroup" aria-label="Pilihan desain tampilan">
              <button
                v-for="opt in BRAND_OPTIONS"
                :key="opt.value"
                type="button"
                role="radio"
                class="handoff-opt-btn"
                :class="{ active: currentBrandValue === opt.value }"
                :aria-checked="currentBrandValue === opt.value"
                :disabled="modules.brandSettingsSaving || modules.brandSettingsLoading"
                @click="selectBrand(opt.value)"
              >
                <span class="handoff-opt-head">
                  <b>{{ opt.label }}</b>
                  <AppIcon v-if="currentBrandValue === opt.value" name="check" :size="14" />
                </span>
                <small>{{ opt.description }}</small>
              </button>
            </div>

            <p v-if="modules.brandSettingsError" class="tg-error" role="alert">
              {{ modules.brandSettingsError }}
            </p>
          </section>
        </div>

        <!-- Halaman PERCAKAPAN -->
        <div v-else-if="activeTab === 'conversation'" key="conversation" class="settings-sections">
          <section class="settings-card" aria-label="Pengaturan percakapan dan hand-off">
            <div class="card-head">
              <div class="card-title-wrap">
                <AppIcon name="arrow-right" :size="16" />
                <h5>Mode pindah cabang (Hand-off)</h5>
              </div>
              <span v-if="modules.conversationSettingsSaving" class="save-status-pill">Menyimpan…</span>
              <span v-else class="status-pill">
                {{ currentHandoffMode === 'auto' ? 'Otomatis' : 'Konfirmasi' }}
              </span>
            </div>

            <p class="tg-info-text">
              Atur perilaku saat AI Manager perlu mengalihkan pekerjaan lanjutan ke cabang bidang lain. Pertanyaan fakta baca-saja tetap dijawab langsung di tab aktif.
            </p>

            <div class="handoff-options" role="radiogroup" aria-label="Mode pindah cabang">
              <button
                v-for="opt in HANDOFF_MODE_OPTIONS"
                :key="opt.value"
                type="button"
                role="radio"
                class="handoff-opt-btn"
                :class="{ active: currentHandoffMode === opt.value }"
                :aria-checked="currentHandoffMode === opt.value"
                :disabled="modules.conversationSettingsSaving || modules.conversationSettingsLoading"
                @click="selectHandoffMode(opt.value)"
              >
                <span class="handoff-opt-head">
                  <b>{{ opt.label }}</b>
                  <AppIcon v-if="currentHandoffMode === opt.value" name="check" :size="14" />
                </span>
                <small>{{ opt.description }}</small>
              </button>
            </div>

            <p v-if="modules.conversationSettingsError" class="tg-error" role="alert">
              {{ modules.conversationSettingsError }}
            </p>
          </section>
        </div>

        <!-- Halaman KONEKTOR -->
        <div v-else-if="activeTab === 'connector'" key="connector" class="settings-sections">
          <section class="settings-card" aria-label="Integrasi Telegram">
            <div class="card-head">
              <div class="card-title-wrap">
                <AppIcon name="telegram" :size="18" />
                <h5>Integrasi Telegram</h5>
              </div>
              <span v-if="modules.telegramStatus?.linked" class="badge-linked">Tersambung</span>
            </div>

            <!-- Batch D (Gap 4): Sales mati -> fitur Telegram dinonaktifkan. -->
            <p v-if="telegramDisabled" class="tg-sales-note" role="note">
              Fitur ini hanya tersedia untuk bidang Sales
            </p>

            <div v-if="modules.telegramLoading" class="tg-loading is-loading">
              <span>Memproses…</span>
            </div>

            <div v-else-if="modules.telegramStatus?.linked" class="tg-linked-box">
              <p class="tg-status-text">
                Akun Anda terhubung dengan Telegram
                <b v-if="modules.telegramStatus.telegram_username">@{{ modules.telegramStatus.telegram_username }}</b>
                <span v-else>ID: {{ modules.telegramStatus.external_thread_id }}</span>.
              </p>
              <div>
                <button
                  type="button"
                  class="btn-danger-icon"
                  aria-label="Putuskan tautan Telegram"
                  title="Putuskan tautan Telegram"
                  @click="handleUnlink"
                >
                  <AppIcon name="unlink" :size="15" />
                </button>
              </div>
            </div>

            <div v-else class="tg-unlinked-box">
              <p class="tg-info-text">
                Sambungkan akun Telegram Anda untuk bertindak sebagai staf resmi penjualan dan mengakses perintah internal.
              </p>

              <div v-if="!modules.telegramDeepLink">
                <button
                  type="button"
                  class="btn-primary-tg-icon"
                  aria-label="Hubungkan ke Telegram"
                  title="Hubungkan ke Telegram"
                  :disabled="telegramDisabled"
                  @click="handleGenerateTelegram"
                >
                  <AppIcon name="telegram" :size="16" />
                </button>
              </div>

              <div v-else class="tg-actions-flow">
                <div class="tg-warning-banner" role="alert">
                  <b>Peringatan:</b> Jangan bagikan tautan ini, siapa pun yang membukanya akan tersambung ke akunmu.
                </div>

                <div class="tg-buttons-dual">
                  <button
                    type="button"
                    class="btn-secondary-copy-icon"
                    :aria-label="copySuccess ? 'Tersalin' : 'Salin tautan Telegram'"
                    :title="copySuccess ? 'Tersalin' : 'Salin tautan Telegram'"
                    :disabled="telegramDisabled"
                    @click="handleCopyLink"
                  >
                    <AppIcon :name="copySuccess ? 'check' : 'copy'" :size="15" />
                  </button>
                  <button
                    type="button"
                    class="btn-primary-tg-icon"
                    aria-label="Buka Telegram langsung"
                    title="Buka Telegram langsung"
                    :disabled="telegramDisabled"
                    @click="handleOpenTelegram"
                  >
                    <AppIcon name="external-link" :size="15" />
                  </button>
                </div>
              </div>
            </div>

            <p v-if="modules.telegramError" class="tg-error" role="alert">
              {{ modules.telegramError }}
            </p>
          </section>
        </div>

        <!-- Halaman PERSONALISASI -->
        <div v-else-if="activeTab === 'personalization'" key="personalization" class="settings-sections">
          <section class="settings-card" aria-label="Konteks Perusahaan">
            <div class="card-head">
              <div class="card-title-wrap">
                <AppIcon name="sparkle" :size="16" />
                <h5>Konteks Perusahaan</h5>
              </div>
              <span v-if="personaSaved" class="save-status-pill ok">Tersimpan</span>
              <span v-else-if="personaSaving" class="save-status-pill">Menyimpan…</span>
            </div>

            <div class="persona-form">
              <textarea
                v-model="personaDraft"
                class="persona-textarea"
                rows="8"
                maxlength="2000"
                placeholder="Tuliskan profil perusahaan, produk, target pasar, atau ketentuan umum bisnis Anda di sini…"
                aria-label="Konteks perusahaan untuk agen AI"
              />
              <div class="persona-foot">
                <span class="char-count" :class="{ 'char-warn': personaDraft.length >= 1800 }">
                  {{ personaDraft.length }} / 2000 karakter
                </span>
                <div class="persona-actions">
                  <button
                    v-if="isPersonaDirty"
                    type="button"
                    class="btn-cancel-icon"
                    :disabled="personaSaving"
                    aria-label="Batalkan perubahan"
                    title="Batal"
                    @click="resetPersonaDraft"
                  >
                    <AppIcon name="x" :size="15" />
                  </button>
                  <button
                    type="button"
                    class="btn-save-icon"
                    :disabled="personaSaving || !isPersonaDirty"
                    aria-label="Simpan konteks perusahaan"
                    title="Simpan"
                    @click="handleSavePersona"
                  >
                    <AppIcon name="check" :size="15" />
                  </button>
                </div>
              </div>
              <p v-if="personaError" class="persona-error" role="alert">
                {{ personaError }}
              </p>
            </div>
          </section>
        </div>

        <!-- Halaman PENERIMA KANAL (Khusus AIOS Client Owner) -->
        <div v-else-if="activeTab === 'receivers' && isClientOwner" key="receivers" class="settings-sections">
          <section class="settings-card" aria-label="Penerima Notifikasi Kanal">
            <div class="card-head">
              <div class="card-title-wrap">
                <AppIcon name="bell" :size="16" />
                <h5>Penerima Notifikasi Kanal</h5>
              </div>
              <span class="status-pill">
                {{ (modules.staffData?.effective_recipients ?? []).length }} penerima aktif
              </span>
            </div>

            <p class="tg-info-text">
              Pilih pengguna aktif yang menerima notifikasi pesanan baru dan percakapan berbendera dari kanal Telegram.
            </p>

            <div
              v-if="modules.staffData?.using_owner_fallback"
              class="tg-warning-banner"
              role="status"
            >
              <b>Mode Cadangan Pemilik:</b> Belum ada penerima khusus yang dipilih. Notifikasi saat ini otomatis dikirim ke pemilik klien aktif.
            </div>

            <div v-if="modules.staffLoading && !modules.staffData" class="tg-loading is-loading">
              <span>Memuat daftar pengguna…</span>
            </div>

            <div v-else class="staff-list">
              <div
                v-for="u in activeClientUsers"
                :key="u.user"
                class="staff-row"
              >
                <div class="staff-info">
                  <div class="staff-name-line">
                    <span class="staff-name">{{ u.full_name }}</span>
                    <span v-if="u.is_client_owner" class="badge-role owner">Pemilik</span>
                    <span class="badge-role">{{ u.persona }}</span>
                  </div>
                  <span class="staff-email">{{ u.user }}</span>
                </div>
                <label class="receiver-toggle">
                  <input
                    type="checkbox"
                    :checked="u.is_channel_receiver"
                    :disabled="modules.staffLoading"
                    :aria-label="'Jadikan ' + u.full_name + ' penerima notifikasi'"
                    @change="handleToggleReceiver(u)"
                  />
                  <span>{{ u.is_channel_receiver ? 'Penerima' : 'Non-penerima' }}</span>
                </label>
              </div>
            </div>

            <p v-if="modules.staffError" class="tg-error" role="alert">
              {{ modules.staffError }}
            </p>
          </section>
        </div>

        <!-- Halaman INSIGHT PROAKTIF (Khusus AIOS Client Owner) -->
        <div v-else-if="activeTab === 'proactive' && hasProactiveBranch" key="proactive" class="settings-sections">
          <section
            v-for="group in proactiveSections"
            :key="group.branch"
            class="settings-card"
            :aria-label="'Jadwal detektor proaktif ' + group.label"
          >
            <div class="card-head">
              <div class="card-title-wrap">
                <AppIcon name="sparkle" :size="16" />
                <h5>Jadwal Detektor Proaktif {{ group.label }}</h5>
              </div>
              <span class="status-pill">{{ group.detectors.length }} detektor</span>
            </div>
            <p class="tg-info-text">
              Atur kapan tiap detektor berjalan. Perubahan langsung dipakai pemindaian
              berikutnya tanpa deploy. Satu ringkasan gabungan dikirim per pemindaian.
            </p>

            <div v-if="modules.detectorSchedulesLoading && !group.detectors.length" class="tg-loading is-loading">
              <span>Memuat jadwal detektor…</span>
            </div>

            <div v-else class="detector-grid">
              <article
                v-for="row in group.detectors"
                :key="row.detector_key"
                class="detector-card"
                :class="{ 'is-off': !row.enabled }"
              >
                <header class="detector-card-head">
                  <h6 class="detector-card-title">{{ row.label || row.detector_key }}</h6>
                  <button
                    type="button"
                    class="detector-toggle"
                    role="switch"
                    :aria-checked="!!row.enabled"
                    :aria-label="'Aktifkan detektor ' + (row.label || row.detector_key)"
                    :disabled="modules.detectorSchedulesSaving"
                    @click="patchDetector(detectorRows.indexOf(row), { enabled: row.enabled ? 0 : 1 })"
                  >
                    <span class="detector-toggle-knob" />
                  </button>
                </header>

                <div class="detector-card-controls">
                  <FintoSelect
                    :model-value="row.frequency"
                    :options="frequencyOptions"
                    :ariaLabel="'Frekuensi ' + (row.label || row.detector_key)"
                    :disabled="modules.detectorSchedulesSaving || !row.enabled"
                    icon="refresh"
                    @update:model-value="patchDetector(detectorRows.indexOf(row), { frequency: String($event) })"
                  />
                  <FintoSelect
                    :model-value="row.run_hour"
                    :options="hourOptions"
                    :ariaLabel="'Jam jalan ' + (row.label || row.detector_key)"
                    :disabled="modules.detectorSchedulesSaving || !row.enabled"
                    icon="history"
                    @update:model-value="patchDetector(detectorRows.indexOf(row), { run_hour: Number($event) })"
                  />
                  <FintoSelect
                    v-if="row.frequency === 'weekly'"
                    :model-value="row.day_of_week"
                    :options="dayOptions(row)"
                    :ariaLabel="'Hari ' + (row.label || row.detector_key)"
                    :disabled="modules.detectorSchedulesSaving || !row.enabled"
                    icon="target"
                    @update:model-value="patchDetector(detectorRows.indexOf(row), { day_of_week: String($event) })"
                  />
                </div>
              </article>
            </div>

            <p v-if="modules.detectorSchedulesError" class="tg-error" role="alert">
              {{ modules.detectorSchedulesError }}
            </p>
            <p v-if="modules.detectorSchedulesSaving" class="tg-info-text" role="status">
              Menyimpan jadwal…
            </p>
          </section>
        </div>
        <!-- Halaman KELOLA STAF (Khusus AIOS Client Owner) -->
        <div v-else-if="activeTab === 'staff' && isClientOwner" key="staff" class="settings-sections">
          <!-- Plafon Pengguna -->
          <section class="settings-card" aria-label="Plafon pengguna aktif">
            <div class="card-head">
              <div class="card-title-wrap">
                <AppIcon name="users" :size="16" />
                <h5>Kuota Pengguna Aktif</h5>
              </div>
              <span class="quota-pct">
                {{ modules.staffData?.quota.active_users ?? 0 }} / {{ modules.staffData?.quota.max_users ?? 0 }} aktif
              </span>
            </div>
            <p class="tg-info-text">
              Sisa slot pengguna aktif yang tersedia:
              <b>{{ modules.staffData?.quota.remaining_slots ?? 0 }} kursi</b>.
            </p>
          </section>

          <!-- Form Tambah Staf -->
          <section class="settings-card" aria-label="Tambah staf baru">
            <div class="card-head">
              <h5>Tambah Staf Baru</h5>
            </div>

            <form class="staff-form" @submit.prevent="handleCreateStaff">
              <div class="staff-form-grid">
                <label class="staff-field">
                  <span>Nama Lengkap</span>
                  <input
                    v-model="newStaffName"
                    type="text"
                    class="staff-input"
                    placeholder="Contoh: Budi Santoso"
                    maxlength="140"
                    required
                    :disabled="modules.staffLoading || (modules.staffData?.quota.remaining_slots ?? 0) <= 0"
                  />
                </label>
                <label class="staff-field">
                  <span>Email Login</span>
                  <input
                    v-model="newStaffEmail"
                    type="email"
                    class="staff-input"
                    placeholder="staf@perusahaan.id"
                    required
                    :disabled="modules.staffLoading || (modules.staffData?.quota.remaining_slots ?? 0) <= 0"
                  />
                </label>
                <label class="staff-field">
                  <span>Persona</span>
                  <select
                    v-model="newStaffPersona"
                    class="staff-input"
                    :disabled="modules.staffLoading || (modules.staffData?.quota.remaining_slots ?? 0) <= 0"
                  >
                    <option v-for="p in PERSONA_OPTIONS" :key="p.value" :value="p.value">
                      {{ p.label }}
                    </option>
                  </select>
                </label>
              </div>

              <div class="staff-form-actions">
                <button
                  type="submit"
                  class="btn-primary-staff"
                  :disabled="
                    modules.staffLoading ||
                    !newStaffName.trim() ||
                    !newStaffEmail.trim() ||
                    (modules.staffData?.quota.remaining_slots ?? 0) <= 0
                  "
                >
                  Buat Staf &amp; Tautan Undangan
                </button>
              </div>
            </form>

            <div v-if="newStaffInvitationUrl" class="invite-banner" role="region" aria-label="Tautan undangan staf">
              <div class="invite-banner-head">
                <b>Tautan Undangan untuk {{ newStaffCreatedFor }}</b>
                <span class="invite-note">Berlaku 20 menit (sekali pakai)</span>
              </div>
              <div class="invite-url-row">
                <input
                  type="text"
                  class="staff-input mono"
                  :value="newStaffInvitationUrl"
                  readonly
                  aria-label="URL tautan undangan"
                />
                <button
                  type="button"
                  class="btn-secondary-copy-icon"
                  :aria-label="inviteCopied ? 'Tersalin' : 'Salin tautan undangan'"
                  :title="inviteCopied ? 'Tersalin' : 'Salin tautan undangan'"
                  @click="handleCopyInviteUrl"
                >
                  <AppIcon :name="inviteCopied ? 'check' : 'copy'" :size="15" />
                </button>
              </div>
            </div>

            <p v-if="modules.staffError" class="tg-error" role="alert">
              {{ modules.staffError }}
            </p>
          </section>

          <!-- Daftar Staf -->
          <section class="settings-card" aria-label="Daftar staf perusahaan">
            <div class="card-head">
              <h5>Daftar Staf Perusahaan</h5>
            </div>

            <div class="staff-list">
              <div
                v-for="u in modules.staffData?.users ?? []"
                :key="u.user"
                class="staff-row"
              >
                <div class="staff-info">
                  <div class="staff-name-line">
                    <span class="staff-name">{{ u.full_name }}</span>
                    <span v-if="u.is_client_owner" class="badge-role owner">Pemilik</span>
                    <span class="badge-role">{{ u.persona }}</span>
                    <span
                      class="status-pill"
                      :class="{ 'ok': u.status === 'Active' }"
                    >
                      {{ u.status }}
                    </span>
                  </div>
                  <span class="staff-email">{{ u.user }}</span>
                </div>

                <div v-if="!u.is_client_owner" class="staff-actions">
                  <button
                    v-if="u.status === 'Active' && !u.has_logged_in"
                    type="button"
                    class="btn-staff-secondary"
                    :disabled="modules.staffLoading"
                    @click="handleRegenerateInvite(u)"
                  >
                    Tautan Baru
                  </button>
                  <button
                    type="button"
                    class="btn-staff-secondary"
                    :class="{ danger: u.status === 'Active' }"
                    :disabled="
                      modules.staffLoading ||
                      (u.status !== 'Active' && (modules.staffData?.quota.remaining_slots ?? 0) <= 0)
                    "
                    @click="handleToggleStaffStatus(u)"
                  >
                    {{ u.status === 'Active' ? 'Nonaktifkan' : 'Aktifkan' }}
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>
        </Transition>
      </main>
    </div>
  </div>
</template>

<style scoped>
.settings-win {
  display: flex;
  flex-direction: column;
  gap: var(--space-12);
  height: 100%;
  padding: var(--space-14) var(--space-16);
  color: var(--fg);
  font-family: var(--font-ui);
  overflow: hidden;
  box-sizing: border-box;
}

.settings-refresh-btn,
.settings-retry-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-8);
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--fg);
  cursor: pointer;
  transition: background var(--dur-15) ease, transform var(--dur-12) ease;
}

.settings-refresh-btn:active:not(:disabled),
.settings-retry-btn:active:not(:disabled) {
  transform: scale(0.95);
}

.settings-refresh-btn:hover:not(:disabled),
.settings-retry-btn:hover {
  background: var(--hover);
}

.settings-refresh-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.settings-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-10);
  padding: var(--space-9) var(--space-12);
  border-radius: var(--radius-9);
  border: 1px solid var(--bad);
  background: var(--bad-soft);
  color: var(--bad);
  font-size: var(--fs-12-5);
  flex: none;
  animation: errorShake var(--dur-30) ease-in-out;
}

.settings-state {
  padding: var(--space-28) var(--space-14);
  text-align: center;
  color: var(--muted);
  font-size: var(--fs-13);
}

.settings-body {
  display: grid;
  grid-template-columns: 168px minmax(0, 1fr);
  gap: var(--space-14);
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.settings-nav {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding-right: var(--space-8);
  border-right: 1px solid var(--line);
  min-height: 0;
  overflow: hidden;
}

.settings-nav-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  overflow-y: auto;
}

.settings-nav-footer {
  margin-top: auto;
  padding-top: var(--space-10);
  display: flex;
  align-items: center;
}

.settings-nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-8);
  width: 100%;
  padding: var(--space-8) var(--space-10);
  border-radius: var(--radius-8);
  border: 1px solid transparent;
  background: transparent;
  color: var(--muted);
  font-family: var(--font-ui);
  font-size: var(--fs-13);
  font-weight: var(--fw-600);
  text-align: left;
  cursor: pointer;
  transition:
    background var(--dur-15) ease,
    color var(--dur-15) ease;
}

.settings-nav-item:hover:not(.active) {
  background: var(--hover);
  color: var(--fg);
}

.settings-nav-item.active {
  background: var(--surface-2);
  color: var(--accent);
  border-color: var(--line);
}

.settings-pane {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-gutter: stable;
  padding-right: var(--space-4);
}

.settings-sections {
  display: flex;
  flex-direction: column;
  gap: var(--space-10);
}

.settings-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-10);
  padding: var(--space-12) var(--space-14);
  border-radius: var(--radius-10);
  border: 1px solid var(--line);
  background: var(--surface);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-8);
}

.card-head h5 {
  margin: 0;
  font-size: var(--fs-12-5);
  font-weight: var(--fw-700);
  color: var(--fg);
}

.card-title-wrap {
  display: flex;
  align-items: center;
  gap: var(--space-8);
  color: var(--fg);
}

.status-pill,
.currency-pill,
.theme-pill,
.quota-pct,
.save-status-pill {
  padding: var(--space-2) var(--space-8);
  border-radius: var(--radius-pill);
  font-size: var(--fs-11);
  font-weight: var(--fw-600);
  background: var(--surface-2);
  color: var(--muted);
  animation: winIn var(--dur-18) ease-out;
}

.save-status-pill.ok {
  background: var(--ok-soft);
  color: var(--ok);
}

.theme-group {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-6);
  padding: var(--space-4);
  border-radius: var(--radius-8);
  border: 1px solid var(--line);
  background: var(--surface-2);
}

.theme-opt-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 34px;
  padding: 0;
  border-radius: var(--radius-6);
  border: 1px solid transparent;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  transition:
    background var(--dur-15) ease,
    color var(--dur-15) ease,
    border-color var(--dur-15) ease,
    transform var(--dur-12) ease;
}

.theme-opt-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.theme-opt-btn:hover:not(:disabled):not(.active) {
  background: var(--hover);
  color: var(--fg);
}

.theme-opt-btn.active {
  border-color: var(--line);
  background: var(--surface);
  color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.theme-opt-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.handoff-options {
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
}

.handoff-opt-btn {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-10) var(--space-12);
  border-radius: var(--radius-8);
  border: 1px solid var(--line);
  background: var(--surface-2);
  color: var(--fg);
  font-family: var(--font-ui);
  text-align: left;
  cursor: pointer;
  transition:
    background var(--dur-15) ease,
    border-color var(--dur-15) ease,
    transform var(--dur-12) ease;
}

.handoff-opt-btn:active:not(:disabled) {
  transform: scale(0.98);
}

.handoff-opt-btn:hover:not(:disabled):not(.active) {
  background: var(--hover);
}

.handoff-opt-btn.active {
  border-color: var(--accent);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.handoff-opt-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.handoff-opt-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-8);
  font-size: var(--fs-13);
  color: var(--fg);
}

.handoff-opt-btn.active .handoff-opt-head {
  color: var(--accent);
}

.handoff-opt-btn small {
  font-size: var(--fs-11-5);
  color: var(--muted);
  line-height: 1.4;
}

.quota-pct {
  font-family: var(--font-mono);
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: var(--space-10);
  margin: 0;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.meta-item dt {
  font-size: var(--fs-11);
  font-weight: var(--fw-600);
  color: var(--muted);
}

.meta-item dd {
  margin: 0;
  font-size: var(--fs-13-5);
  font-weight: var(--fw-600);
  color: var(--fg);
}

.meta-item dd.mono {
  font-family: var(--font-mono);
}

.quota-bar-track {
  width: 100%;
  height: 8px;
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  overflow: hidden;
}

.quota-bar-fill {
  height: 100%;
  border-radius: var(--radius-pill);
  background: var(--accent);
  transition: width var(--dur-20) ease;
}

.quota-bar-fill[data-state='warn'] {
  background: var(--warn);
}

.quota-bar-fill[data-state='danger'] {
  background: var(--bad);
}

.reset-warn {
  padding: var(--space-8) var(--space-10);
  border-radius: var(--radius-8);
  background: var(--warn-soft);
  color: var(--warn);
  font-size: var(--fs-12-5);
  font-weight: var(--fw-600);
}

.reset-info {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-10);
  font-size: var(--fs-13);
}

.reset-time {
  font-family: var(--font-mono);
  font-size: var(--fs-12);
  color: var(--muted);
}

.badge-linked {
  background: var(--ok-soft);
  color: var(--ok);
  padding: var(--space-2) var(--space-8);
  border-radius: var(--radius-4);
  font-size: var(--fs-11);
  font-weight: var(--fw-600);
  animation: winIn var(--dur-18) ease-out;
}

.tg-loading {
  font-size: var(--fs-12);
  color: var(--muted);
  padding: var(--space-6) var(--space-8);
}

.tg-linked-box,
.tg-unlinked-box {
  display: flex;
  flex-direction: column;
  gap: var(--space-10);
  margin-top: var(--space-6);
}

.tg-status-text,
.tg-info-text {
  font-size: var(--fs-12-5);
  line-height: 1.5;
  color: var(--muted);
  margin: 0;
}

/* Batch D (Gap 4): catatan fitur Telegram dinonaktifkan saat Sales mati. */
.tg-sales-note {
  display: flex;
  align-items: center;
  gap: var(--space-6);
  margin: 0;
  padding: var(--space-8) var(--space-10);
  border: 1px dashed var(--line);
  border-radius: var(--radius-8);
  background: var(--surface-2);
  color: var(--muted);
  font-size: var(--fs-12);
  line-height: 1.4;
}

.btn-primary-tg-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-8);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  cursor: pointer;
  transition: opacity var(--dur-15) ease, transform var(--dur-12) ease;
}

.btn-primary-tg-icon:active {
  transform: scale(0.95);
}

.btn-primary-tg-icon:hover {
  opacity: 0.9;
}

.btn-secondary-copy-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-8);
  border: 1px solid var(--line);
  background: var(--surface-2);
  color: var(--fg);
  cursor: pointer;
  transition: background var(--dur-15) ease, transform var(--dur-12) ease;
}

.btn-secondary-copy-icon:active {
  transform: scale(0.95);
}

.btn-secondary-copy-icon:hover {
  background: var(--hover);
}

.btn-danger-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-8);
  border: 1px solid var(--bad);
  background: transparent;
  color: var(--bad);
  cursor: pointer;
  transition: background var(--dur-15) ease, transform var(--dur-12) ease;
}

.btn-danger-icon:active {
  transform: scale(0.95);
}

.btn-danger-icon:hover {
  background: var(--bad-soft);
}

.tg-actions-flow {
  display: flex;
  flex-direction: column;
  gap: var(--space-10);
  animation: rise2 var(--dur-20) ease-out;
}

.tg-warning-banner {
  background: var(--warn-soft);
  border: 1px solid var(--warn);
  color: var(--warn);
  padding: var(--space-8) var(--space-12);
  border-radius: var(--radius-6);
  font-size: var(--fs-12);
  line-height: 1.4;
  animation: rise2 var(--dur-20) ease-out;
}

.tg-buttons-dual {
  display: flex;
  align-items: center;
  gap: var(--space-10);
}

.tg-error {
  color: var(--bad);
  font-size: var(--fs-12);
  margin: var(--space-6) 0 0 0;
  animation: errorShake var(--dur-30) ease-in-out;
}

/* Personalisasi */
.persona-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
}

.persona-textarea {
  width: 100%;
  padding: var(--space-10) var(--space-12);
  border-radius: var(--radius-8);
  border: 1px solid var(--line);
  background: var(--surface-2);
  color: var(--fg);
  font-family: var(--font-ui);
  font-size: var(--fs-13);
  line-height: 1.5;
  resize: vertical;
  min-height: 140px;
  box-sizing: border-box;
  transition: border-color var(--dur-15) ease, background var(--dur-15) ease;
}

.persona-textarea:focus {
  outline: none;
  border-color: var(--accent);
  background: var(--surface);
}

.persona-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-10);
}

.char-count {
  font-family: var(--font-mono);
  font-size: var(--fs-11);
  color: var(--muted);
}

.char-count.char-warn {
  color: var(--warn);
}

.persona-actions {
  display: flex;
  align-items: center;
  gap: var(--space-8);
}

.btn-save-icon,
.btn-cancel-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-8);
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--fg);
  cursor: pointer;
  transition: background var(--dur-15) ease, transform var(--dur-12) ease;
}

.btn-save-icon:active:not(:disabled),
.btn-cancel-icon:active:not(:disabled) {
  transform: scale(0.95);
}

.btn-save-icon:hover:not(:disabled),
.btn-cancel-icon:hover:not(:disabled) {
  background: var(--hover);
}

.btn-save-icon:disabled,
.btn-cancel-icon:disabled {
  opacity: 0.4;
  cursor: default;
}

.persona-error {
  margin: 0;
  color: var(--bad);
  font-size: var(--fs-12);
  animation: errorShake var(--dur-30) ease-in-out;
}

/* Insight Proaktif (K9) */
.detector-grid {
  display: grid;
  /* Dua kolom sama lebar — lebar kartu tidak mengikuti panjang teks. */
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-10);
  align-items: stretch;
}

.detector-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-10);
  min-width: 0;
  padding: var(--space-12);
  border-radius: var(--radius-12);
  border: 1px solid var(--line);
  background: var(--surface-2);
  transition:
    border-color var(--dur-18) ease,
    background var(--dur-18) ease,
    transform var(--dur-18) ease,
    box-shadow var(--dur-18) ease;
  animation: rise2 var(--dur-20) ease-out both;
}

.detector-card:hover {
  border-color: var(--teal-line);
  background: var(--surface);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.detector-card.is-off {
  opacity: 0.62;
}

/* Kartu masuk berurutan supaya terasa hidup, bukan muncul serentak. */
.detector-card:nth-child(1) { animation-delay: 0ms; }
.detector-card:nth-child(2) { animation-delay: 40ms; }
.detector-card:nth-child(3) { animation-delay: 80ms; }
.detector-card:nth-child(4) { animation-delay: 120ms; }
.detector-card:nth-child(5) { animation-delay: 160ms; }
.detector-card:nth-child(6) { animation-delay: 200ms; }
.detector-card:nth-child(7) { animation-delay: 240ms; }

.detector-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-8);
  min-width: 0;
}

.detector-card-title {
  margin: 0;
  font-size: var(--fs-13);
  font-weight: var(--fw-600);
  color: var(--fg);
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.detector-toggle {
  position: relative;
  flex: none;
  width: 34px;
  height: 20px;
  padding: 0;
  border: none;
  border-radius: var(--radius-pill);
  background: var(--line);
  cursor: pointer;
  transition: background var(--dur-18) ease;
}

.detector-toggle[aria-checked="true"] {
  background: var(--teal);
}

.detector-toggle:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.detector-toggle-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: var(--radius-circle);
  background: var(--surface);
  box-shadow: var(--shadow-knob);
  transition: transform var(--dur-18) cubic-bezier(0.2, 0.8, 0.2, 1);
}

.detector-toggle[aria-checked="true"] .detector-toggle-knob {
  transform: translateX(14px);
}

.detector-card-controls {
  display: grid;
  /* Ditumpuk selebar kartu supaya label "Harian"/"06:00" tidak terpotong. */
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-6);
}

@media (max-width: 720px) {
  .detector-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .detector-card,
  .detector-card:hover,
  .detector-toggle-knob {
    animation: none;
    transition: none;
    transform: none;
  }
}

/* Penerima Kanal & Kelola Staf */
.staff-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
  max-height: 240px;
  overflow-y: auto;
  padding-right: var(--space-4);
}

.staff-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-10);
  padding: var(--space-8) var(--space-10);
  border-radius: var(--radius-8);
  border: 1px solid var(--line);
  background: var(--surface-2);
  transition: background var(--dur-15) ease;
  animation: rise2 var(--dur-20) ease-out;
}

.staff-row:hover {
  background: var(--hover);
}

.staff-info {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
}

.staff-name-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-6);
}

.staff-name {
  font-size: var(--fs-13);
  font-weight: var(--fw-600);
  color: var(--fg);
}

.staff-email {
  font-size: var(--fs-11-5);
  color: var(--muted);
  font-family: var(--font-mono);
  overflow: hidden;
  text-overflow: ellipsis;
}

.badge-role {
  padding: var(--space-1) var(--space-6);
  border-radius: var(--radius-4);
  font-size: var(--fs-10-5);
  font-weight: var(--fw-600);
  background: var(--surface);
  color: var(--muted);
  border: 1px solid var(--line);
  text-transform: capitalize;
}

.badge-role.owner {
  background: var(--ok-soft);
  color: var(--ok);
  border-color: transparent;
}

.receiver-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--space-6);
  font-size: var(--fs-12);
  font-weight: var(--fw-600);
  color: var(--fg);
  cursor: pointer;
  user-select: none;
}

.staff-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-10);
}

.staff-form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--space-8);
}

.staff-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  font-size: var(--fs-11-5);
  font-weight: var(--fw-600);
  color: var(--muted);
}

.staff-input {
  width: 100%;
  padding: var(--space-7) var(--space-10);
  border-radius: var(--radius-6);
  border: 1px solid var(--line);
  background: var(--surface-2);
  color: var(--fg);
  font-family: var(--font-ui);
  font-size: var(--fs-12-5);
  box-sizing: border-box;
  transition: border-color var(--dur-15) ease, background var(--dur-15) ease;
}

.staff-input.mono {
  font-family: var(--font-mono);
}

.staff-form-actions {
  display: flex;
  justify-content: flex-end;
}

.btn-primary-staff {
  padding: var(--space-7) var(--space-12);
  border-radius: var(--radius-8);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font-family: var(--font-ui);
  font-size: var(--fs-12-5);
  font-weight: var(--fw-600);
  cursor: pointer;
  transition: opacity var(--dur-15) ease, transform var(--dur-12) ease;
}

.btn-primary-staff:active:not(:disabled) {
  transform: scale(0.97);
}

.btn-primary-staff:disabled {
  opacity: 0.5;
  cursor: default;
}

.invite-banner {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  padding: var(--space-10);
  border-radius: var(--radius-8);
  border: 1px solid var(--ok);
  background: var(--ok-soft);
  animation: rise2 var(--dur-20) ease-out;
}

.invite-banner-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-8);
  font-size: var(--fs-12);
  color: var(--fg);
}

.invite-note {
  font-size: var(--fs-11);
  color: var(--muted);
}

.invite-url-row {
  display: flex;
  align-items: center;
  gap: var(--space-8);
}

.staff-actions {
  display: flex;
  align-items: center;
  gap: var(--space-6);
}

.btn-staff-secondary {
  padding: var(--space-5) var(--space-10);
  border-radius: var(--radius-6);
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--fg);
  font-family: var(--font-ui);
  font-size: var(--fs-11-5);
  font-weight: var(--fw-600);
  cursor: pointer;
  transition: background var(--dur-15) ease, opacity var(--dur-15) ease, transform var(--dur-12) ease;
}

.btn-staff-secondary:active:not(:disabled) {
  transform: scale(0.97);
}

.btn-staff-secondary:hover:not(:disabled) {
  background: var(--hover);
}

.btn-staff-secondary.danger {
  border-color: var(--bad);
  color: var(--bad);
}

.btn-staff-secondary:disabled {
  opacity: 0.5;
  cursor: default;
}

@media (prefers-reduced-motion: reduce) {
  .settings-error,
  .tg-error,
  .persona-error {
    animation: none;
  }
  .settings-refresh-btn:active,
  .settings-retry-btn:active,
  .theme-opt-btn:active,
  .handoff-opt-btn:active,
  .btn-primary-tg-icon:active,
  .btn-secondary-copy-icon:active,
  .btn-danger-icon:active,
  .btn-save-icon:active,
  .btn-cancel-icon:active,
  .btn-primary-staff:active,
  .btn-staff-secondary:active {
    transform: none;
  }
}

@media (max-width: 560px) {
  .settings-body {
    grid-template-columns: 1fr;
    gap: var(--space-10);
  }
  .settings-nav {
    flex-direction: row;
    align-items: center;
    border-right: none;
    border-bottom: 1px solid var(--line);
    padding-right: 0;
    padding-bottom: var(--space-8);
    overflow-x: auto;
  }
  .settings-nav-list {
    flex-direction: row;
    overflow-x: auto;
  }
  .settings-nav-footer {
    margin-top: 0;
    padding-top: 0;
    margin-left: auto;
  }
  .settings-nav-item {
    width: auto;
    white-space: nowrap;
  }
}
</style>
