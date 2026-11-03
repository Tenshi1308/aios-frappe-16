<script setup lang="ts">
import { useWindowManager } from '../../composables/useWindowManager';
import { useChatStore } from '../../stores/chat';
import AppIcon from '../base/AppIcon.vue';
import EkasaMark from '../base/EkasaMark.vue';
import ApprovalCardWindow from '../windows/ApprovalCardWindow.vue';
import AboutWindow from '../windows/AboutWindow.vue';
import ArtifactWindow from '../windows/ArtifactWindow.vue';
import ChannelFlagsWindow from '../windows/ChannelFlagsWindow.vue';
import FilesWindow from '../windows/FilesWindow.vue';
import PendingDraftsWindow from '../windows/PendingDraftsWindow.vue';
import SettingsWindow from '../windows/SettingsWindow.vue';
import ModuleWindow from '../module/ModuleWindow.vue';
import DomainWindow from '../domain/DomainWindow.vue';

const props = defineProps<{ narrow: boolean }>();

const wm = useWindowManager();
const chat = useChatStore();
const activeId = wm.activeId;

function artifactFileUrl(windowId: string) {
  const artifact = chat.artifactWindows[windowId.slice(9)];
  return artifact?.type === 'FILE' ? artifact.file_url : '';
}

function openAbout() {
  wm.open('about', 'Tentang AIOS');
}

defineExpose({ openAbout });
</script>

<template>
  <div class="win-layer">
    <div
      v-for="w in wm.windows"
      v-show="!w.min"
      :key="w.id"
      class="win"
      :class="{ active: w.id === activeId, max: w.max || props.narrow }"
      :style="wm.winStyle(w, props.narrow)"
      @pointerdown="wm.focus(w)"
    >
      <header class="win-title" @pointerdown="wm.startDrag($event, w, props.narrow)" @dblclick="wm.toggleMax(w)">
        <span class="tile sm"><EkasaMark :size="13" accent="var(--on-accent)" /></span>
        <span class="win-name">{{ w.title }}</span>
        <div class="win-ctrls">
          <button aria-label="Minimize" @click.stop="wm.minimize(w)"><AppIcon name="minus" :size="15" /></button>
          <button v-if="!props.narrow" :aria-label="w.max ? 'Restore' : 'Maximize'" @click.stop="wm.toggleMax(w)">
            <AppIcon :name="w.max ? 'restore' : 'square'" :size="13" />
          </button>
          <button class="close" aria-label="Close" @click.stop="wm.close(w)"><AppIcon name="x" :size="15" /></button>
        </div>
      </header>
      <div class="win-body">
        <AboutWindow v-if="w.id === 'about'" />
        <SettingsWindow v-else-if="w.id === 'settings'" />
        <PendingDraftsWindow v-else-if="w.id === 'pending-drafts'" />
        <FilesWindow v-else-if="w.id === 'files'" />
        <ChannelFlagsWindow v-else-if="w.id === 'channel-flags'" />
        <ApprovalCardWindow v-else-if="w.id.startsWith('approval:')" :draft-id="w.id.slice(9)" />
        <ArtifactWindow
          v-else-if="w.id.startsWith('artifact:')"
          :artifact-key="w.id.slice(9)"
          :file-url="artifactFileUrl(w.id)"
        />
        <ModuleWindow
          v-else-if="w.id.startsWith('module:')"
          :module-key="w.id.slice(7)"
        />
        <DomainWindow
          v-else-if="w.id.startsWith('domain:')"
          :domain-key="w.id.slice(7)"
        />
      </div>
      <div class="resize" @pointerdown.stop="wm.startResize($event, w, false)" />
    </div>
  </div>
</template>
