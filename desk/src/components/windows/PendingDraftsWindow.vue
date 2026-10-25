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
      <button class="icon-btn" aria-label="Muat ulang daftar" @click="chat.loadPendingDrafts()">
        <AppIcon name="history" :size="15" />
      </button>
    </div>
    <button v-for="d in chat.pendingDrafts" :key="d.name" class="pd-item" @click="openCard(d.name)">
      <b>{{ d.type }} · {{ d.name }}</b>
      <small>
        <template v-if="d.branch">{{ d.branch }} · </template>
        dibuat {{ formatDateTime(d.creation) }} · kedaluwarsa {{ formatDateTime(d.expires_at) }}
      </small>
    </button>
    <div v-if="!chat.pendingDrafts.length" class="pd-empty">
      Tidak ada draft yang menunggu persetujuan.
    </div>
  </div>
</template>

<style scoped>
.pending-drafts {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  overflow: auto;
}
.pd-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: var(--muted);
  font-size: 12px;
}
.pd-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 9px 11px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-2);
  color: var(--fg);
  text-align: left;
  cursor: pointer;
}
.pd-item:hover {
  background: var(--hover);
}
.pd-item b {
  font-size: 12px;
}
.pd-item small {
  color: var(--muted);
  font-size: 11px;
}
.pd-empty {
  color: var(--muted);
  font-size: 12px;
}
</style>
