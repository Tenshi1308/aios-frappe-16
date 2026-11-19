<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useChatStore } from '../../stores/chat';
import { useWindowManager } from '../../composables/useWindowManager';
import type { DraftListStatus, PendingDraft } from '../../types';
import { formatDateTime } from '../../utils/format';
import AppIcon from '../base/AppIcon.vue';

const chat = useChatStore();
const wm = useWindowManager();

type HistorySubFilter = 'ALL' | 'APPROVED' | 'EXECUTED' | 'REJECTED';

const activeFilter = ref<DraftListStatus>('PENDING_APPROVAL');
const historySubFilter = ref<HistorySubFilter>('ALL');
const confirmingCloseId = ref<string | null>(null);
const closingId = ref<string | null>(null);
const closeError = ref('');

const STATUS_LABELS: Record<string, string> = {
  PENDING_APPROVAL: 'Menunggu',
  APPROVED: 'Disetujui',
  EXECUTED: 'Dieksekusi',
  REJECTED: 'Ditolak',
  EXPIRED: 'Kedaluwarsa',
};

const visibleDrafts = computed(() => {
  if (activeFilter.value === 'EXPIRED') return chat.expiredDrafts;
  if (activeFilter.value === 'HISTORY') {
    if (historySubFilter.value === 'ALL') return chat.historyDrafts;
    return chat.historyDrafts.filter((d) => d.status === historySubFilter.value);
  }
  return chat.pendingDrafts;
});
const isLoading = computed(() => {
  if (activeFilter.value === 'EXPIRED') return chat.expiredDraftsLoading;
  if (activeFilter.value === 'HISTORY') return chat.historyDraftsLoading;
  return chat.pendingDraftsLoading;
});
const loadError = computed(() => {
  if (activeFilter.value === 'EXPIRED') return chat.expiredDraftsError;
  if (activeFilter.value === 'HISTORY') return chat.historyDraftsError;
  return chat.pendingDraftsError;
});

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

function documentUrl(d: PendingDraft): string {
  if (!d.document_doctype || !d.document_name) return '';
  const slug = d.document_doctype.trim().toLowerCase().replace(/\s+/g, '-');
  return `/app/${encodeURIComponent(slug)}/${encodeURIComponent(d.document_name)}`;
}

function isRowExpired(d: PendingDraft): boolean {
  if (d.status === 'EXPIRED') return true;
  if (typeof d.expired === 'boolean') return d.expired;
  if (!d.expires_at) return false;
  const normalized =
    d.expires_at.includes(' ') && !d.expires_at.includes('T')
      ? d.expires_at.replace(' ', 'T')
      : d.expires_at;
  const ms = Date.parse(normalized);
  return !Number.isNaN(ms) && ms <= Date.now();
}

function selectFilter(status: DraftListStatus) {
  if (activeFilter.value === status) return;
  activeFilter.value = status;
  confirmingCloseId.value = null;
  closeError.value = '';
  void chat.loadPendingDrafts(status);
}

function reloadActive() {
  closeError.value = '';
  void chat.loadPendingDrafts(activeFilter.value);
}

function openCard(name: string) {
  wm.open(`approval:${name}`, 'Persetujuan Aksi');
}

async function confirmClose(name: string) {
  closingId.value = name;
  closeError.value = '';
  try {
    await chat.closeDraft(name);
    confirmingCloseId.value = null;
  } catch (err) {
    closeError.value =
      err instanceof Error && err.message.trim()
        ? err.message
        : `Draf ${name} tidak dapat ditutup.`;
  } finally {
    closingId.value = null;
  }
}

onMounted(() => {
  void chat.loadPendingDrafts(activeFilter.value);
});
</script>

<template>
  <div class="pending-drafts">
    <div class="pd-head">
      <span>Draft menunggu persetujuanmu — aksi tulis ke ERPNext hanya jalan setelah kamu setujui.</span>
      <button
        type="button"
        class="icon-btn"
        aria-label="Muat ulang daftar"
        :disabled="isLoading"
        @click="reloadActive()"
      >
        <AppIcon name="history" :size="15" />
      </button>
    </div>

    <div class="pd-tabs" role="tablist" aria-label="Filter status persetujuan">
      <button
        id="pd-tab-pending"
        type="button"
        role="tab"
        class="pd-tab"
        :aria-selected="activeFilter === 'PENDING_APPROVAL'"
        @click="selectFilter('PENDING_APPROVAL')"
      >
        Menunggu
      </button>
      <button
        id="pd-tab-expired"
        type="button"
        role="tab"
        class="pd-tab"
        :aria-selected="activeFilter === 'EXPIRED'"
        @click="selectFilter('EXPIRED')"
      >
        Kedaluwarsa
      </button>
      <button
        id="pd-tab-history"
        type="button"
        role="tab"
        class="pd-tab"
        :aria-selected="activeFilter === 'HISTORY'"
        @click="selectFilter('HISTORY')"
      >
        Riwayat
      </button>
    </div>

    <div v-if="activeFilter === 'HISTORY'" class="pd-subfilters" role="group" aria-label="Filter riwayat draft">
      <button
        type="button"
        class="pd-subfilter"
        :class="{ on: historySubFilter === 'ALL' }"
        @click="historySubFilter = 'ALL'"
      >
        Semua
      </button>
      <button
        type="button"
        class="pd-subfilter"
        :class="{ on: historySubFilter === 'APPROVED' }"
        @click="historySubFilter = 'APPROVED'"
      >
        Disetujui
      </button>
      <button
        type="button"
        class="pd-subfilter"
        :class="{ on: historySubFilter === 'EXECUTED' }"
        @click="historySubFilter = 'EXECUTED'"
      >
        Dieksekusi
      </button>
      <button
        type="button"
        class="pd-subfilter"
        :class="{ on: historySubFilter === 'REJECTED' }"
        @click="historySubFilter = 'REJECTED'"
      >
        Ditolak
      </button>
    </div>

    <div v-if="closeError" class="pd-error" role="alert">
      <span>{{ closeError }}</span>
    </div>

    <div
      role="tabpanel"
      :aria-labelledby="
        activeFilter === 'EXPIRED'
          ? 'pd-tab-expired'
          : activeFilter === 'HISTORY'
            ? 'pd-tab-history'
            : 'pd-tab-pending'
      "
      class="pd-panel"
    >
      <div v-if="isLoading" class="pd-empty">
        Memuat draft…
      </div>
      <div v-else-if="loadError" class="pd-error" role="alert">
        <span>{{ loadError }}</span>
        <button
          class="pd-retry"
          type="button"
          :disabled="isLoading"
          @click="reloadActive()"
        >
          Coba lagi
        </button>
      </div>
      <div v-else-if="!visibleDrafts.length" class="pd-empty">
        {{
          activeFilter === 'EXPIRED'
            ? 'Tidak ada draft yang kedaluwarsa.'
            : activeFilter === 'HISTORY'
              ? 'Belum ada riwayat draft pada filter ini.'
              : 'Tidak ada draft yang menunggu persetujuan.'
        }}
      </div>
      <template v-else>
        <div v-for="d in visibleDrafts" :key="d.name" class="pd-item">
          <button type="button" class="pd-row-main" @click="openCard(d.name)">
            <span class="pd-title-row">
              <b>{{ d.type }} · {{ d.name }}</b>
              <span v-if="isRowExpired(d) && d.status === 'PENDING_APPROVAL'" class="pd-expired-badge">Kedaluwarsa</span>
              <span v-if="activeFilter !== 'PENDING_APPROVAL'" class="pd-status-tag" :class="d.status.toLowerCase()">
                {{ statusLabel(d.status) }}
              </span>
            </span>
            <small>
              <template v-if="d.branch">{{ d.branch }} · </template>
              <template v-if="activeFilter === 'HISTORY'">
                dibuat {{ formatDateTime(d.creation) }}
                <template v-if="d.modified"> · diperbarui {{ formatDateTime(d.modified) }}</template>
              </template>
              <template v-else>
                dibuat {{ formatDateTime(d.creation) }} · kedaluwarsa {{ formatDateTime(d.expires_at) }}
              </template>
            </small>
          </button>
          <a
            v-if="d.status === 'EXECUTED' && d.document_doctype && d.document_name"
            class="pd-doc-link"
            :href="documentUrl(d)"
            target="_blank"
            rel="noopener noreferrer"
            @click.stop
          >
            <AppIcon name="external-link" :size="12" />
            <span>{{ d.document_doctype }} · {{ d.document_name }}</span>
          </a>
          <div v-if="d.status === 'PENDING_APPROVAL' && isRowExpired(d)" class="pd-row-actions">
            <template v-if="confirmingCloseId === d.name">
              <button
                type="button"
                class="pd-action-btn confirm"
                :disabled="closingId === d.name"
                :aria-label="`Konfirmasi tutup draf ${d.name}`"
                @click="confirmClose(d.name)"
              >
                {{ closingId === d.name ? 'Menutup…' : 'Konfirmasi Tutup' }}
              </button>
              <button
                type="button"
                class="pd-action-btn"
                :disabled="closingId === d.name"
                @click="confirmingCloseId = null"
              >
                Batal
              </button>
            </template>
            <button
              v-else
              type="button"
              class="pd-action-btn"
              :disabled="closingId !== null"
              :aria-label="`Tutup draf ${d.name}`"
              @click="confirmingCloseId = d.name"
            >
              Tutup
            </button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.pending-drafts {
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
  height: 100%;
  overflow: auto;
}
.pd-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-8);
  color: var(--muted);
  font-size: var(--fs-12);
}
.pd-tabs {
  display: flex;
  gap: var(--space-4);
  border-bottom: 1px solid var(--line);
}
.pd-tab {
  position: relative;
  min-block-size: 28px;
  padding: var(--space-4) var(--space-10);
  border: none;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: var(--fs-12);
  cursor: pointer;
}
.pd-tab:hover {
  color: var(--fg);
}
.pd-tab[aria-selected='true'] {
  color: var(--fg);
}
.pd-tab[aria-selected='true']::after {
  content: '';
  position: absolute;
  inset: auto 0 0;
  border-block-end: 2px solid var(--accent);
}
.pd-subfilters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
}
.pd-subfilter {
  padding: var(--space-3) var(--space-10);
  border: 1px solid var(--line);
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  color: var(--muted);
  font: inherit;
  font-size: var(--fs-11-5);
  font-weight: var(--fw-600);
  cursor: pointer;
}
.pd-subfilter:hover {
  color: var(--fg);
  background: var(--hover);
}
.pd-subfilter.on {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--fg);
}
.pd-doc-link {
  display: inline-flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4) var(--space-8);
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface);
  color: var(--fg);
  font-size: var(--fs-11-5);
  font-weight: var(--fw-600);
  text-decoration: none;
  white-space: nowrap;
}
.pd-doc-link:hover {
  background: var(--hover);
}
.pd-tab:focus-visible,
.pd-row-main:focus-visible,
.pd-action-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.pd-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
}
.pd-error {
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
.pd-retry {
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
.pd-retry:hover:not(:disabled) {
  background: var(--hover);
}
.pd-retry:disabled {
  opacity: 0.65;
  cursor: wait;
}
.pd-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-8);
  padding: var(--space-9) var(--space-11);
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface-2);
}
.pd-item:hover {
  background: var(--hover);
}
.pd-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: 0;
  border: none;
  background: transparent;
  color: var(--fg);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.pd-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-6);
}
.pd-item b {
  font-size: var(--fs-12);
}
.pd-item small {
  color: var(--muted);
  font-size: var(--fs-11);
}
.pd-expired-badge {
  display: inline-flex;
  align-items: center;
  padding: var(--space-1) var(--space-6);
  border: 1px solid var(--bad);
  border-radius: var(--radius-4);
  background: var(--bad-soft);
  color: var(--bad);
  font-size: var(--fs-10);
  font-weight: 600;
}
.pd-status-tag {
  display: inline-flex;
  align-items: center;
  padding: var(--space-1) var(--space-6);
  border: 1px solid var(--line);
  border-radius: var(--radius-4);
  color: var(--muted);
  font-size: var(--fs-10);
}
.pd-row-actions {
  display: flex;
  align-items: center;
  gap: var(--space-6);
  flex-shrink: 0;
}
.pd-action-btn {
  min-block-size: 26px;
  padding: var(--space-4) var(--space-8);
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface);
  color: var(--fg);
  font: inherit;
  font-size: var(--fs-11);
  cursor: pointer;
}
.pd-action-btn:hover:not(:disabled) {
  background: var(--hover);
}
.pd-action-btn.confirm {
  border-color: var(--bad);
  background: var(--bad-soft);
  color: var(--bad);
}
.pd-action-btn:disabled {
  opacity: 0.65;
  cursor: wait;
}
.pd-empty {
  color: var(--muted);
  font-size: var(--fs-12);
}
</style>
