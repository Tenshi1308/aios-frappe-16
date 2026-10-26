<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useModulesStore } from '../../stores/modules';
import { formatNumber } from '../../utils/format';
import AppIcon from '../base/AppIcon.vue';

const modules = useModulesStore();

const data = computed(() => modules.settings);
const loading = computed(() => modules.settingsLoading);
const error = computed(() => modules.settingsError);

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
          <span class="settings-sub">Profil, company, dan kuota site · Baca saja</span>
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
    </div>
  </div>
</template>

<style scoped>
.settings-win {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  padding: 14px 16px;
  color: var(--fg);
  font-family: var(--font-ui);
  overflow-y: auto;
}

.settings-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
}

.settings-title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.settings-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.2;
}

.settings-sub {
  display: block;
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--muted);
}

.settings-refresh-btn,
.settings-retry-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 11px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--fg);
  font-family: var(--font-ui);
  font-size: 12px;
  font-weight: 600;
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
  gap: 10px;
  padding: 9px 12px;
  border-radius: 9px;
  border: 1px solid var(--bad);
  background: var(--bad-soft);
  color: var(--bad);
  font-size: 12.5px;
}

.settings-state {
  padding: 28px 14px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

.settings-sections {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.settings-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--surface);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.card-head h5 {
  margin: 0;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--fg);
}

.status-pill,
.currency-pill,
.quota-pct {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  background: var(--surface-2);
  color: var(--muted);
}

.quota-pct {
  font-family: var(--font-mono);
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
  margin: 0;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.meta-item dt {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
}

.meta-item dd {
  margin: 0;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--fg);
}

.meta-item dd.mono {
  font-family: var(--font-mono);
}

.quota-bar-track {
  width: 100%;
  height: 8px;
  border-radius: 999px;
  background: var(--surface-2);
  overflow: hidden;
}

.quota-bar-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--accent);
  transition: width 0.2s ease;
}

.quota-bar-fill[data-state='warn'] {
  background: var(--warn);
}

.quota-bar-fill[data-state='danger'] {
  background: var(--bad);
}

.reset-warn {
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--warn-soft);
  color: var(--warn);
  font-size: 12.5px;
  font-weight: 600;
}

.reset-info {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
}

.reset-time {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--muted);
}

.spin {
  animation: settings-spin 0.9s linear infinite;
}

@keyframes settings-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
