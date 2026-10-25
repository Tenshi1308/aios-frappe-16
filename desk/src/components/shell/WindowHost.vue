<script setup lang="ts">
import { useWindowManager } from '../../composables/useWindowManager';
import AppIcon from '../base/AppIcon.vue';
import EkasaMark from '../base/EkasaMark.vue';
import ApprovalCardWindow from '../windows/ApprovalCardWindow.vue';
import AboutWindow from '../windows/AboutWindow.vue';
import PendingDraftsWindow from '../windows/PendingDraftsWindow.vue';

const props = defineProps<{ narrow: boolean }>();

const wm = useWindowManager();
const activeId = wm.activeId;

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
        <PendingDraftsWindow v-else-if="w.id === 'pending-drafts'" />
        <ApprovalCardWindow v-else-if="w.id.startsWith('approval:')" :draft-id="w.id.slice(9)" />
      </div>
      <div class="resize" @pointerdown.stop="wm.startResize($event, w, false)" />
    </div>
  </div>
</template>
