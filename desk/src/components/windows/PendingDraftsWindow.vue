<script setup lang="ts">
import { onMounted } from 'vue';
import { useChatStore } from '../../stores/chat';
import { useWindowManager } from '../../composables/useWindowManager';
import { formatDateTime } from '../../utils/format';
import AppIcon from '../base/AppIcon.vue';

const chat = useChatStore();
const wm = useWindowManager();

function openCard(name: string) {
  wm.open(`approval:${name}`, 'Persetujuan Aksi');
}

onMounted(() => {
  void chat.loadPendingDrafts();
});
</script>

<template>
  <div class="pending-drafts">
    <div class="pd-head">
      <span>Draft menunggu persetujuanmu — aksi tulis ke ERPNext hanya jalan setelah kamu setujui.</span>
      <button
        class="icon-btn"
        aria-label="Muat ulang daftar"
        :disabled="chat.pendingDraftsLoading"
        @click="chat.loadPendingDrafts()"
      >
        <AppIcon name="history" :size="15" />
      </button>
    </div>
    <div v-if="chat.pendingDraftsLoading" class="pd-empty">
      Memuat draft…
    </div>
    <div v-else-if="chat.pendingDraftsError" class="pd-error" role="alert">
      <span>{{ chat.pendingDraftsError }}</span>
      <button
        class="pd-retry"
        type="button"
        :disabled="chat.pendingDraftsLoading"
        @click="chat.loadPendingDrafts()"
      >
        Coba lagi
      </button>
    </div>
    <div v-else-if="!chat.pendingDrafts.length" class="pd-empty">
      Tidak ada draft yang menunggu persetujuan.
    </div>
    <template v-else>
      <button v-for="d in chat.pendingDrafts" :key="d.name" class="pd-item" @click="openCard(d.name)">
        <b>{{ d.type }} · {{ d.name }}</b>
        <small>
          <template v-if="d.branch">{{ d.branch }} · </template>
          dibuat {{ formatDateTime(d.creation) }} · kedaluwarsa {{ formatDateTime(d.expires_at) }}
        </small>
      </button>
    </template>
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
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-9) var(--space-11);
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface-2);
  color: var(--fg);
  text-align: left;
  cursor: pointer;
}
.pd-item:hover {
  background: var(--hover);
}
.pd-item b {
  font-size: var(--fs-12);
}
.pd-item small {
  color: var(--muted);
  font-size: var(--fs-11);
}
.pd-empty {
  color: var(--muted);
  font-size: var(--fs-12);
}
</style>
