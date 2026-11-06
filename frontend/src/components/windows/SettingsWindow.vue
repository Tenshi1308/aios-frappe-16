<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useModulesStore } from '../../stores/modules';
import type { SettingsTheme } from '../../types';
import { formatNumber } from '../../utils/format';
import { resolveTheme } from '../../utils/theme';
import AppIcon from '../base/AppIcon.vue';

type TabId = 'general' | 'connector' | 'personalization';

interface MenuTab {
  id: TabId;
  label: string;
  icon: string;
}

const MENU_TABS: MenuTab[] = [
  { id: 'general', label: 'Umum', icon: 'gear' },
  { id: 'connector', label: 'Konektor', icon: 'link' },
  { id: 'personalization', label: 'Personalisasi', icon: 'sparkle' },
];

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

const modules = useModulesStore();

const activeTab = ref<TabId>('general');
const tabRefs = ref<HTMLElement[]>([]);

function setTabRef(el: any, index: number) {
  if (el) {
    tabRefs.value[index] = el as HTMLElement;
  }
}

function selectTab(id: TabId) {
  activeTab.value = id;
}

function onTabKeydown(e: KeyboardEvent, index: number) {
  let targetIndex = index;
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    targetIndex = (index + 1) % MENU_TABS.length;
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    targetIndex = (index - 1 + MENU_TABS.length) % MENU_TABS.length;
  } else if (e.key === 'Home') {
    e.preventDefault();
    targetIndex = 0;
  } else if (e.key === 'End') {
    e.preventDefault();
    targetIndex = MENU_TABS.length - 1;
  } else {
    return;
  }
  const nextTab = MENU_TABS[targetIndex];
  if (nextTab) {
    activeTab.value = nextTab.id;
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
  void modules.loadTelegramStatus();
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
  void modules.loadTelegramStatus();
}

const copySuccess = ref(false);

async function handleGenerateTelegram() {
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
</script>

<template>
  <div class="settings-win">
    <div v-if="error" class="settings-error" role="alert">
      <span>{{ error }}</span>
      <button
        type="button"
        class="settings-retry-btn"
        aria-label="Coba lagi"
        title="Coba lagi"
        @click="refresh"
      >
        <AppIcon name="refresh" :size="14" />
      </button>
    </div>

    <div v-if="loading && !data" class="settings-state">
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
            v-for="(tab, i) in MENU_TABS"
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
        <!-- Halaman UMUM -->
        <div v-if="activeTab === 'general'" class="settings-sections">
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

        <!-- Halaman KONEKTOR -->
        <div v-else-if="activeTab === 'connector'" class="settings-sections">
          <section class="settings-card" aria-label="Integrasi Telegram">
            <div class="card-head">
              <div class="card-title-wrap">
                <AppIcon name="telegram" :size="18" />
                <h5>Integrasi Telegram</h5>
              </div>
              <span v-if="modules.telegramStatus?.linked" class="badge-linked">Tersambung</span>
            </div>

            <div v-if="modules.telegramLoading" class="tg-loading">
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
                    @click="handleCopyLink"
                  >
                    <AppIcon :name="copySuccess ? 'check' : 'copy'" :size="15" />
                  </button>
                  <button
                    type="button"
                    class="btn-primary-tg-icon"
                    aria-label="Buka Telegram langsung"
                    title="Buka Telegram langsung"
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
        <div v-else-if="activeTab === 'personalization'" class="settings-sections">
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
  transition: background var(--dur-15) ease;
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
    border-color var(--dur-15) ease;
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

.spin {
  animation: settings-spin var(--dur-90) linear infinite;
}

@keyframes settings-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.badge-linked {
  background: var(--ok-soft);
  color: var(--ok);
  padding: var(--space-2) var(--space-8);
  border-radius: var(--radius-4);
  font-size: var(--fs-11);
  font-weight: var(--fw-600);
}

.tg-loading {
  font-size: var(--fs-12);
  color: var(--muted);
  padding: var(--space-6) 0;
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
  transition: opacity var(--dur-15) ease;
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
  transition: background var(--dur-15) ease;
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
  transition: background var(--dur-15) ease;
}

.btn-danger-icon:hover {
  background: var(--bad-soft);
}

.tg-actions-flow {
  display: flex;
  flex-direction: column;
  gap: var(--space-10);
}

.tg-warning-banner {
  background: var(--warn-soft);
  border: 1px solid var(--warn);
  color: var(--warn);
  padding: var(--space-8) var(--space-12);
  border-radius: var(--radius-6);
  font-size: var(--fs-12);
  line-height: 1.4;
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
  transition: background var(--dur-15) ease;
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
