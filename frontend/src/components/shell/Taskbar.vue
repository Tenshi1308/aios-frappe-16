<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useSessionStore } from '../../stores/session';
import { useUiStore } from '../../stores/ui';
import { useWindowManager } from '../../composables/useWindowManager';
import { fetchFlags, fetchOrderNotifications } from '../../api/connector';
import AppIcon from '../base/AppIcon.vue';
import EkasaMark from '../base/EkasaMark.vue';

const session = useSessionStore();
const ui = useUiStore();
const wm = useWindowManager();
const activeId = wm.activeId;

const now = ref(new Date());
let timer: number | undefined;
onMounted(() => {
  timer = window.setInterval(() => (now.value = new Date()), 15_000);
});
onUnmounted(() => window.clearInterval(timer));

// Channel alert badge: flags Open + unread order notifications
// Refreshed on a 30s timer and whenever an 'aios:bell-refresh' event is fired.
const bellCount = ref(0);
let flagTimer: number | undefined;

async function refreshBell() {
  try {
    const [flags, orders] = await Promise.all([
      fetchFlags('Open'),
      fetchOrderNotifications(true),
    ]);
    bellCount.value = flags.length + orders.length;
  } catch {
    // Badge is decoration; a failed poll must not disturb the taskbar.
    bellCount.value = 0;
  }
}

const bellBadgeText = computed(() => {
  if (bellCount.value > 99) return '99+';
  return bellCount.value > 0 ? String(bellCount.value) : '';
});

function openFlags() {
  wm.open('channel-flags', 'Peringatan Kanal');
}

onMounted(() => {
  void refreshBell();
  flagTimer = window.setInterval(() => void refreshBell(), 30_000);
  window.addEventListener('aios:bell-refresh', refreshBell);
});
onUnmounted(() => {
  if (flagTimer) window.clearInterval(flagTimer);
  window.removeEventListener('aios:bell-refresh', refreshBell);
});

const timeStr = computed(() => now.value.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }));
const shortDate = computed(() => now.value.toLocaleDateString('en-GB'));
const siteName = computed(() => session.context?.aios_company_name || session.context?.company || 'AIOS');
</script>

<template>
  <footer class="taskbar">
    <div class="tb-left">
      <button class="tb-site" :title="'Terhubung ke ' + siteName">
        <span class="dot ok" />
        <span style="min-width: 0"><b>{{ siteName }}</b><small>AIOS · online</small></span>
      </button>
    </div>
    <div class="tb-center">
      <button class="tb-btn start" :class="{ on: ui.flyout === 'start' }" aria-label="Menu mulai" @click="ui.toggleFlyout('start')">
        <EkasaMark :size="22" />
      </button>
      <button class="tb-search" aria-label="Pencarian" @click="ui.openSearch()">
        <AppIcon name="search" :size="16" />
        <span>Cari</span>
      </button>
      <button class="tb-btn only-narrow" :class="{ on: ui.flyout === 'search' }" aria-label="Pencarian" @click="ui.openSearch()">
        <AppIcon name="search" :size="19" />
      </button>
      <button
        class="tb-btn agent-btn"
        :class="{ on: ui.agentOpen }"
        aria-label="AI agents"
        title="AI agents (Ctrl J)"
        @click="ui.toggleAgent()"
      >
        <AppIcon name="sparkle" :size="21" />
      </button>
      <span v-if="wm.windows.length" class="tb-sep" />
      <button
        v-for="w in wm.windows"
        :key="w.id"
        class="tb-btn app"
        :class="{ active: w.id === activeId && !w.min }"
        :title="w.title"
        :aria-label="w.title"
        @click="wm.taskClick(w.id)"
      >
        <span class="tile neutral"><AppIcon name="desk" :size="15" /></span>
      </button>
    </div>
    <div class="tb-right">
      <button class="tray bell" aria-label="Peringatan kanal" title="Peringatan kanal" @click="openFlags()">
        <AppIcon name="bell" :size="17" />
        <span v-if="bellCount" class="bell-badge">{{ bellBadgeText }}</span>
      </button>
      <div class="tray" aria-label="Status koneksi">
        <AppIcon name="wifi" :size="16" />
      </div>
      <button class="clock" aria-label="Jam">
        <span>{{ timeStr }}</span>
        <span>{{ shortDate }}</span>
      </button>
    </div>
  </footer>
</template>

<style scoped>
.tray.bell {
  position: relative;
  cursor: pointer;
  border: 1px solid transparent;
  border-radius: var(--radius-6);
  background: transparent;
  color: var(--fg);
}
.tray.bell:hover {
  background: var(--hover);
}
.bell-badge {
  position: absolute;
  top: -2px;
  right: -2px;
  min-width: 15px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-pill);
  background: var(--bad);
  color: var(--on-accent);
  font-size: var(--fs-10);
  font-weight: var(--fw-600);
  line-height: 15px;
  text-align: center;
}
</style>
