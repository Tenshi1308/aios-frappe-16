<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useModulesStore } from '../../stores/modules';
import type { SettingsTheme } from '../../types';
import { formatNumber } from '../../utils/format';
import { resolveTheme } from '../../utils/theme';
import AppIcon from '../base/AppIcon.vue';

const THEME_LABELS: Record<SettingsTheme, string> = {
  Automatic: 'Ikuti sistem',
  Light: 'Terang',
  Dark: 'Gelap',
};

const modules = useModulesStore();

const data = computed(() => modules.settings);
const loading = computed(() => modules.settingsLoading);
const error = computed(() => modules.settingsError);
const themeSaving = computed(() => modules.themeSaving);

function themeLabel(opt: SettingsTheme): string {
  return THEME_LABELS[opt];
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
</script>

<template>
  <div class="settings-win">
    <div class="settings-head">
      <div class="settings-title-wrap">
        <span class="tile sm neutral">
          <AppIcon name="gear" :size="15" />
        </span>
        <div>
          <h4 class="settings-title">Pengaturan</h4>
          <span class="settings-sub">Profil, company, kuota site, dan tema</span>
        </div>
      </div>
      <button
        type="button"
        class="settings-refresh-btn"
        :disabled="loading"
        aria-label="Muat ulang pengaturan"
        @click="refresh"
      >
        <AppIcon name="refresh" :size="15" :class="{ spin: loading }" />
        <span>{{ loading ? 'Memuat…' : 'Refresh' }}</span>
      </button>
    </div>

    <div v-if="error" class="settings-error" role="alert">
      <span>{{ error }}</span>
      <button type="button" class="settings-retry-btn" @click="refresh">Coba lagi</button>
    </div>

    <div v-if="loading && !data" class="settings-state">
      Memuat pengaturan site…
    </div>

    <div v-else-if="data" class="settings-sections">
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
            :disabled="themeSaving"
            @click="selectTheme(opt)"
          >
            {{ themeLabel(opt) }}
          </button>
        </div>
      </section>

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

      <!-- Telegram Connector Integration Card -->
      <section class="settings-card" aria-label="Integrasi Telegram">
        <div class="card-head">
          <div class="tg-card-title">
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
            <button type="button" class="btn-danger-outline" @click="handleUnlink">
              Putuskan Tautan
            </button>
          </div>
        </div>

        <div v-else class="tg-unlinked-box">
          <p class="tg-info-text">
            Sambungkan akun Telegram Anda untuk bertindak sebagai staf resmi penjualan dan mengakses perintah internal.
          </p>

          <div v-if="!modules.telegramDeepLink">
            <button type="button" class="btn-primary-tg" @click="handleGenerateTelegram">
              <AppIcon name="telegram" :size="16" />
              <span>Hubungkan ke Telegram</span>
            </button>
          </div>

          <div v-else class="tg-actions-flow">
            <div class="tg-warning-banner" role="alert">
              <b>Peringatan:</b> Jangan bagikan tautan ini, siapa pun yang membukanya akan tersambung ke akunmu.
            </div>

            <div class="tg-buttons-dual">
              <button type="button" class="btn-secondary-copy" @click="handleCopyLink">
                <AppIcon name="file" :size="15" />
                <span>{{ copySuccess ? 'Tersalin!' : 'Salin Tautan' }}</span>
              </button>
              <button type="button" class="btn-primary-tg" @click="handleOpenTelegram">
                <AppIcon name="telegram" :size="15" />
                <span>Buka Telegram Langsung</span>
              </button>
            </div>
          </div>
        </div>

        <p v-if="modules.telegramError" class="tg-error" role="alert">
          {{ modules.telegramError }}
        </p>
      </section>
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
  overflow-y: auto;
}

.settings-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-12);
  padding-bottom: var(--space-10);
  border-bottom: 1px solid var(--line);
}

.settings-title-wrap {
  display: flex;
  align-items: center;
  gap: var(--space-10);
}

.settings-title {
  margin: 0;
  font-size: var(--fs-15);
  font-weight: var(--fw-700);
  line-height: 1.2;
}

.settings-sub {
  display: block;
  margin-top: var(--space-2);
  font-size: var(--fs-11-5);
  color: var(--muted);
}

.settings-refresh-btn,
.settings-retry-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-6);
  padding: var(--space-6) var(--space-11);
  border-radius: var(--radius-8);
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--fg);
  font-family: var(--font-ui);
  font-size: var(--fs-12);
  font-weight: var(--fw-600);
  cursor: pointer;
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
}

.settings-state {
  padding: var(--space-28) var(--space-14);
  text-align: center;
  color: var(--muted);
  font-size: var(--fs-13);
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

.status-pill,
.currency-pill,
.theme-pill,
.quota-pct {
  padding: var(--space-2) var(--space-8);
  border-radius: var(--radius-pill);
  font-size: var(--fs-11);
  font-weight: var(--fw-600);
  background: var(--surface-2);
  color: var(--muted);
}

.theme-group {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: var(--space-6);
  padding: var(--space-4);
  border-radius: var(--radius-8);
  border: 1px solid var(--line);
  background: var(--surface-2);
}

.theme-opt-btn {
  padding: var(--space-6) var(--space-10);
  border-radius: var(--radius-6);
  border: 1px solid transparent;
  background: transparent;
  color: var(--muted);
  font-family: var(--font-ui);
  font-size: var(--fs-12-5);
  font-weight: var(--fw-600);
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
  color: var(--fg);
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
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
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

.tg-card-title {
  display: flex;
  align-items: center;
  gap: var(--space-8, 8px);
  color: var(--fg);
}

.badge-linked {
  background: var(--ok-soft);
  color: var(--ok);
  padding: 2px 8px;
  border-radius: var(--radius-4, 4px);
  font-size: 11px;
  font-weight: 600;
}

.tg-loading {
  font-size: 12px;
  color: var(--muted);
  padding: 6px 0;
}

.tg-linked-box,
.tg-unlinked-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 6px;
}

.tg-status-text,
.tg-info-text {
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--muted);
  margin: 0;
}

.btn-primary-tg {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: var(--accent);
  color: var(--on-accent);
  border: none;
  padding: 7px 14px;
  border-radius: 6px;
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s ease;
}

.btn-primary-tg:hover {
  opacity: 0.9;
}

.btn-secondary-copy {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--surface-2);
  color: var(--fg);
  border: 1px solid var(--line);
  padding: 7px 12px;
  border-radius: 6px;
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
}

.btn-danger-outline {
  display: inline-flex;
  align-items: center;
  background: transparent;
  color: var(--bad);
  border: 1px solid var(--bad);
  padding: 5px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-danger-outline:hover {
  background: var(--bad-soft);
  border-color: var(--bad);
}

.tg-actions-flow {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tg-warning-banner {
  background: var(--warn-soft);
  border: 1px solid var(--warn);
  color: var(--warn);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.4;
}

.tg-buttons-dual {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.tg-error {
  color: var(--bad);
  font-size: 12px;
  margin: 6px 0 0 0;
}
</style>
