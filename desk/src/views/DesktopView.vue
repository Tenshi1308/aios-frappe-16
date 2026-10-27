<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useBranchesStore } from '../stores/branches';
import { useModulesStore } from '../stores/modules';
import { useSessionStore } from '../stores/session';
import { useUiStore } from '../stores/ui';
import { setWindowBounds, useWindowManager } from '../composables/useWindowManager';
import AgentPanel from '../components/agent/AgentPanel.vue';
import AppIcon from '../components/base/AppIcon.vue';
import Toasts from '../components/base/Toasts.vue';
import SearchFlyout from '../components/shell/SearchFlyout.vue';
import StartMenu from '../components/shell/StartMenu.vue';
import Taskbar from '../components/shell/Taskbar.vue';
import WindowHost from '../components/shell/WindowHost.vue';

const props = defineProps<{ narrow: boolean }>();

const session = useSessionStore();
const branches = useBranchesStore();
const modules = useModulesStore();
const ui = useUiStore();
const wm = useWindowManager();

const deskEl = ref<HTMLElement | null>(null);
const windowHost = ref<InstanceType<typeof WindowHost> | null>(null);

onMounted(() => {
  setWindowBounds(bounds);
  void branches.load();
  void modules.loadBootstrap();
  window.addEventListener('keydown', onKey);
});
onUnmounted(() => {
  window.removeEventListener('keydown', onKey);
});

function bounds() {
  const el = deskEl.value;
  return el ? { w: el.clientWidth, h: el.clientHeight } : { w: window.innerWidth, h: window.innerHeight - 52 };
}

const selectedIcon = ref<string | null>(null);
interface DeskIcon {
  id: string;
  label: string;
  icon: string;
  colorToken?: string;
  neutral?: boolean;
  run: () => void;
}
const desktopIcons = computed<DeskIcon[]>(() => {
  const domainIcons: DeskIcon[] = modules.domains.map((d) => ({
    id: `domain:${d.key}`,
    label: d.label,
    icon: d.icon || 'tag',
    colorToken: d.color_token,
    run: () => {
      void modules.openDomain(d.key);
    },
  }));
  const staticIcons: DeskIcon[] = [
    { id: 'agents', label: 'AI Agents', icon: 'sparkle', neutral: false, run: () => ui.openAgent() },
    { id: 'files', label: 'Files', icon: 'folder', neutral: true, run: () => wm.open('files', 'Files') },
    {
      id: 'about',
      label: 'Tentang AIOS',
      icon: 'desk',
      neutral: true,
      run: () => windowHost.value?.openAbout(),
    },
  ];
  return [...domainIcons, ...staticIcons];
});
function iconClick(d: DeskIcon) {
  selectedIcon.value = d.id;
  d.run();
}

function onKey(e: KeyboardEvent) {
  const k = e.key.toLowerCase();
  if ((e.ctrlKey || e.metaKey) && k === 'k') {
    e.preventDefault();
    ui.openSearch();
  } else if ((e.ctrlKey || e.metaKey) && k === 'j') {
    e.preventDefault();
    ui.toggleAgent();
  } else if (e.key === 'Escape') {
    if (ui.flyout) ui.closeFlyouts();
    else if (ui.agentOpen) ui.closeAgent();
  }
}
</script>

<template>
  <section class="desktop wall">
    <div class="desk-area" ref="deskEl" @pointerdown.self="ui.closeFlyouts()">
      <div class="desk-icons" @pointerdown.self="ui.closeFlyouts()">
        <button
          v-for="d in desktopIcons"
          :key="d.id"
          class="desk-icon"
          :class="{ sel: selectedIcon === d.id }"
          @click="iconClick(d)"
          @dblclick="d.run()"
          @keydown.enter.prevent="d.run()"
        >
          <span
            class="tile xl"
            :class="{ neutral: d.neutral }"
            :style="d.colorToken ? { background: `var(--${d.colorToken})` } : undefined"
          >
            <AppIcon :name="d.icon" :size="24" />
          </span>
          <span>{{ d.label }}</span>
        </button>
      </div>

      <div class="desk-hint">
        <span><kbd>Ctrl K</kbd> Cari</span>
        <span><kbd>Ctrl J</kbd> AI agents</span>
        <span>Klik dua kali ikon untuk membuka</span>
      </div>

      <WindowHost ref="windowHost" :narrow="narrow" />

      <StartMenu v-if="ui.flyout === 'start'" />
      <SearchFlyout v-else-if="ui.flyout === 'search'" />

      <AgentPanel v-if="ui.agentOpen" />

      <Toasts />
    </div>
    <Taskbar />
  </section>
</template>
