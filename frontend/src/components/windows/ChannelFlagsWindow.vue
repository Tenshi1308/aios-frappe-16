<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useSessionStore } from '../../stores/session';
import { useWindowManager } from '../../composables/useWindowManager';
import {
  closeFlag,
  fetchFlags,
  fetchOrderNotifications,
  reviewOrderNotification,
  type ChannelFlag,
  type ChannelOrderNotification,
} from '../../api/connector';
import { reportClientError } from '../../api/client';
import { formatDateTime } from '../../utils/format';
import AppIcon from '../base/AppIcon.vue';

const session = useSessionStore();
const wm = useWindowManager();

/** Poll interval for the bell badge. Realtime socket.io is not wired in the
 *  desk yet, so the badge refreshes on a timer; 30 s is the agreed ceiling. */
const POLL_MS = 30_000;

const flags = ref<ChannelFlag[]>([]);
const orders = ref<ChannelOrderNotification[]>([]);
const orderPage = ref(1);
const orderTotal = ref(0);
const orderTotalPages = ref(1);
const loading = ref(false);
const error = ref('');
const closing = ref<string | null>(null);
const reviewingOrder = ref<string | null>(null);
let timer: number | undefined;

const openFlags = computed(() => flags.value.filter((flag) => flag.status === 'Open'));
const totalCount = computed(() => openFlags.value.length + orderTotal.value);
const badge = computed(() => (totalCount.value > 99 ? '99+' : String(totalCount.value)));

async function load(targetPage?: number) {
  loading.value = true;
  error.value = '';
  let pageToFetch = targetPage ?? orderPage.value;
  try {
    const [fetchedFlags, orderRes] = await Promise.all([
      fetchFlags(),
      fetchOrderNotifications(true, pageToFetch),
    ]);
    flags.value = fetchedFlags;
    orderTotal.value = orderRes.total;
    orderTotalPages.value = orderRes.total_pages;

    // If current page is beyond total_pages and can step back, step back to last valid page
    if (orderRes.total_pages > 0 && pageToFetch > orderRes.total_pages && pageToFetch > 1) {
      pageToFetch = orderRes.total_pages;
      orderPage.value = pageToFetch;
      const validOrderRes = await fetchOrderNotifications(true, pageToFetch);
      orders.value = validOrderRes.orders;
      orderTotal.value = validOrderRes.total;
      orderTotalPages.value = validOrderRes.total_pages;
    } else {
      orders.value = orderRes.orders;
      orderPage.value = orderRes.page;
    }
  } catch (err) {
    error.value = 'Daftar peringatan kanal tidak dapat dimuat.';
    void reportClientError(
      {
        message: err instanceof Error ? err.message : String(err),
        context: 'connector:channel-items',
      },
      session.csrfToken,
    );
  } finally {
    loading.value = false;
  }
}

function changeOrderPage(newPage: number) {
  if (newPage < 1 || (orderTotalPages.value > 0 && newPage > orderTotalPages.value) || loading.value) return;
  orderPage.value = newPage;
  void load(newPage);
}

function notifyBell() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('aios:bell-refresh'));
  }
}

async function review(flag: ChannelFlag) {
  if (closing.value) return;
  closing.value = flag.name;
  try {
    await closeFlag(flag.name, '', session.csrfToken ?? '');
    await load();
    notifyBell();
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

async function handleReviewOrder(order: ChannelOrderNotification) {
  if (reviewingOrder.value) return;
  reviewingOrder.value = order.name;
  try {
    await reviewOrderNotification(order.name, session.csrfToken ?? '');
    notifyBell();
    await load(orderPage.value);
  } catch (err) {
    error.value = 'Pesanan tidak dapat ditandai sudah ditinjau.';
    void reportClientError(
      {
        message: err instanceof Error ? err.message : String(err),
        context: 'connector:review-order',
      },
      session.csrfToken,
    );
  } finally {
    reviewingOrder.value = null;
  }
}

function openDraft(draftId: string) {
  if (!draftId) return;
  wm.open(`approval:${draftId}`, 'Persetujuan Aksi');
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
        <b>{{ badge }}</b> item menunggu ditinjau ({{ openFlags.length }} percakapan ditandai, {{ orderTotal }} draf pesanan).
      </span>
      <button class="cf-btn" aria-label="Muat ulang" :disabled="loading" @click="load()">
        <AppIcon name="history" :size="15" />
      </button>
    </div>

    <div v-if="error" class="cf-error" role="alert">
      <span>{{ error }}</span>
      <button class="cf-btn" type="button" :disabled="loading" @click="load()">Coba lagi</button>
    </div>

    <div v-else-if="loading && !totalCount" class="cf-empty">Memuat peringatan…</div>
    <div v-else-if="!totalCount" class="cf-empty">
      Tidak ada percakapan atau pesanan yang perlu ditinjau.
    </div>

    <ul v-else class="cf-list">
      <!-- Unread order draft notifications -->
      <li v-for="order in orders" :key="order.name" class="cf-item cf-item-order">
        <div class="cf-row">
          <span class="cf-badge-order">{{ order.doctype }}</span>
          <b>{{ order.customer_name }}</b>
          <small>{{ formatDateTime(order.creation) }}</small>
        </div>
        <p class="cf-desc">Draf pesanan {{ order.doctype }} baru menunggu tindak lanjut staf.</p>
        <div class="cf-actions">
          <button class="cf-btn-open" type="button" @click="openDraft(order.draft_id)">
            <AppIcon name="desk" :size="13" />
            <span>Buka Draf</span>
          </button>
          <button
            class="cf-close"
            type="button"
            :disabled="reviewingOrder === order.name"
            @click="handleReviewOrder(order)"
          >
            {{ reviewingOrder === order.name ? 'Menandai…' : 'Tandai sudah ditinjau' }}
          </button>
        </div>
      </li>

      <!-- Order pagination controls below order list -->
      <li v-if="orderTotal > 0" class="cf-pagination">
        <button
          class="cf-btn cf-page-btn"
          type="button"
          :disabled="orderPage <= 1 || loading"
          @click="changeOrderPage(orderPage - 1)"
        >
          Sebelumnya
        </button>
        <span class="cf-page-info">Halaman {{ orderPage }} dari {{ orderTotalPages }}</span>
        <button
          class="cf-btn cf-page-btn"
          type="button"
          :disabled="orderPage >= orderTotalPages || loading"
          @click="changeOrderPage(orderPage + 1)"
        >
          Berikutnya
        </button>
      </li>

      <!-- Channel flags -->
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
.cf-item-order {
  border-left-color: var(--accent);
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
.cf-badge-order {
  padding: 0 var(--space-4);
  border-radius: var(--radius-3);
  background: var(--accent);
  color: var(--on-accent);
  font-size: var(--fs-10);
  font-weight: var(--fw-600);
  text-transform: uppercase;
}
.cf-desc {
  margin: 0;
  color: var(--fg);
  font-size: var(--fs-12);
}
.cf-btn-open {
  display: inline-flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4) var(--space-8);
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface-2);
  color: var(--fg);
  font-size: var(--fs-12);
  cursor: pointer;
}
.cf-btn-open:hover {
  background: var(--hover);
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
.cf-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-6) var(--space-10);
  border: 1px dashed var(--line);
  border-radius: var(--radius-6);
  background: var(--surface-1);
  font-size: var(--fs-12);
}
.cf-page-info {
  color: var(--muted);
  font-weight: var(--fw-500);
}
.cf-page-btn {
  padding: var(--space-4) var(--space-10);
}
.cf-page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
