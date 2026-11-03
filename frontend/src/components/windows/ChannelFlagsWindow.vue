<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useSessionStore } from '../../stores/session';
import {
  closeFlag,
  fetchFlags,
  type ChannelFlag,
} from '../../api/connector';
import { reportClientError } from '../../api/client';
import { formatDateTime } from '../../utils/format';
import AppIcon from '../base/AppIcon.vue';

const session = useSessionStore();

/** Poll interval for the bell badge. Realtime socket.io is not wired in the
 *  desk yet, so the badge refreshes on a timer; 30 s is the agreed ceiling. */
const POLL_MS = 30_000;

const flags = ref<ChannelFlag[]>([]);
const loading = ref(false);
const error = ref('');
const closing = ref<string | null>(null);
let timer: number | undefined;

const openFlags = computed(() => flags.value.filter((flag) => flag.status === 'Open'));
const badge = computed(() => openFlags.value.length);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    flags.value = await fetchFlags();
  } catch (err) {
    error.value = 'Daftar peringatan tidak dapat dimuat.';
    void reportClientError(
      {
        message: err instanceof Error ? err.message : String(err),
        context: 'connector:flags',
      },
      session.csrfToken,
    );
  } finally {
    loading.value = false;
  }
}

async function review(flag: ChannelFlag) {
  if (closing.value) return;
  closing.value = flag.name;
  try {
    await closeFlag(flag.name, '', session.csrfToken ?? '');
    await load();
  } catch (err) {
    error.value = 'Peringatan tidak dapat ditutup.';
    void reportClientError(
      {
        message: err instanceof Error ? err.message : String(err),
        context: 'connector:close-flag',
      },
      session.csrfToken,
    );
  } finally {
    closing.value = null;
  }
}

onMounted(() => {
  void load();
  timer = window.setInterval(() => void load(), POLL_MS);
});
onUnmounted(() => window.clearInterval(timer));
</script>

<template>
  <div class="cf">
    <div class="cf-head">
      <span>
        <b>{{ badge }}</b> percakapan ditandai dan menunggu ditinjau. Tanda berasal dari aturan
        otomatis; penilaian akhir tetap di tangan manusia.
      </span>
      <button class="cf-btn" aria-label="Muat ulang" :disabled="loading" @click="load()">
        <AppIcon name="history" :size="15" />
      </button>
    </div>

    <div v-if="error" class="cf-error" role="alert">
      <span>{{ error }}</span>
      <button class="cf-btn" type="button" :disabled="loading" @click="load()">Coba lagi</button>
    </div>

    <div v-else-if="loading && !flags.length" class="cf-empty">Memuat peringatan…</div>
    <div v-else-if="!openFlags.length" class="cf-empty">
      Tidak ada percakapan yang perlu ditinjau.
    </div>

    <ul v-else class="cf-list">
      <li v-for="flag in openFlags" :key="flag.name" class="cf-item" :data-severity="flag.severity">
        <div class="cf-row">
          <span class="cf-sev">{{ flag.severity }}</span>
          <b>{{ flag.label || flag.rule_key }}</b>
          <small>{{ formatDateTime(flag.creation) }}</small>
        </div>
        <p v-if="flag.excerpt" class="cf-excerpt">{{ flag.excerpt }}</p>
        <p v-if="flag.reason_text" class="cf-reason">{{ flag.reason_text }}</p>
        <div class="cf-actions">
          <small v-if="flag.message_ids">Bukti: {{ flag.message_ids }}</small>
          <button
            class="cf-close"
            type="button"
            :disabled="closing === flag.name"
            @click="review(flag)"
          >
            {{ closing === flag.name ? 'Menutup…' : 'Tandai sudah ditinjau' }}
          </button>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.cf {
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
  height: 100%;
  overflow: auto;
}
.cf-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-8);
  color: var(--muted);
  font-size: var(--fs-12);
}
.cf-btn {
  display: inline-flex;
  align-items: center;
  padding: var(--space-4) var(--space-8);
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface-2);
  color: var(--fg);
  font-size: var(--fs-12);
  cursor: pointer;
}
.cf-btn:hover:not(:disabled) {
  background: var(--hover);
}
.cf-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-8);
  padding: var(--space-8) var(--space-12);
  border: 1px solid var(--bad);
  border-radius: var(--radius-8);
  background: var(--bad-soft);
  color: var(--bad);
  font-size: var(--fs-12);
}
.cf-empty {
  color: var(--muted);
  font-size: var(--fs-13);
}
.cf-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  margin: 0;
  padding: 0;
  list-style: none;
}
.cf-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-9) var(--space-11);
  border: 1px solid var(--line);
  border-left: 3px solid var(--warn);
  border-radius: var(--radius-6);
  background: var(--surface-2);
}
.cf-item[data-severity='high'] {
  border-left-color: var(--bad);
}
.cf-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-6);
  font-size: var(--fs-13);
}
.cf-row small {
  margin-left: auto;
  color: var(--faint);
  font-size: var(--fs-11);
}
.cf-sev {
  padding: 0 var(--space-4);
  border-radius: var(--radius-3);
  background: var(--hover);
  color: var(--muted);
  font-size: var(--fs-10);
  text-transform: uppercase;
}
.cf-excerpt,
.cf-reason {
  margin: 0;
  color: var(--muted);
  font-size: var(--fs-12);
}
.cf-reason {
  color: var(--fg);
}
.cf-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-8);
}
.cf-actions small {
  color: var(--faint);
  font-size: var(--fs-11);
}
.cf-close {
  padding: var(--space-4) var(--space-9);
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface-2);
  color: var(--fg);
  font-size: var(--fs-12);
  cursor: pointer;
}
.cf-close:hover:not(:disabled) {
  background: var(--hover);
}
.cf-close:disabled {
  opacity: 0.65;
  cursor: wait;
}
</style>
