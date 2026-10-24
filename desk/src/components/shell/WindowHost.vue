<script setup lang="ts">
import { useSessionStore } from '../../stores/session';
import { useWindowManager } from '../../composables/useWindowManager';
import AppIcon from '../base/AppIcon.vue';
import EkasaMark from '../base/EkasaMark.vue';

const props = defineProps<{ narrow: boolean }>();

const session = useSessionStore();
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
        <div class="about">
          <EkasaMark :size="44" />
          <div class="about-word">Ekasa Desk</div>
          <div class="about-line">
            Desktop AIOS untuk bisnis: tanyakan data dan pekerjaanmu kepada agent, lampirkan berkas,
            dan pantau semuanya dari satu layar.
          </div>
          <div class="about-meta">
            <span><b>Pengguna:</b> {{ session.context?.full_name ?? session.context?.user }}</span>
            <span v-if="session.context?.aios_company_name"><b>Perusahaan:</b> {{ session.context.aios_company_name }}</span>
            <span v-if="session.context?.company"><b>Company ERP:</b> {{ session.context.company }}</span>
          </div>
          <div class="about-keys">
            <span><kbd>Ctrl K</kbd> Pencarian</span>
            <span><kbd>Ctrl J</kbd> Agent</span>
            <span><kbd>Esc</kbd> Tutup</span>
          </div>
        </div>
      </div>
      <div class="resize" @pointerdown.stop="wm.startResize($event, w, false)" />
    </div>
  </div>
</template>
