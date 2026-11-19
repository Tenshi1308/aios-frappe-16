<script setup lang="ts">
import { computed } from 'vue';
import { useSessionStore } from '../../stores/session';
import { currentBrand } from '../../utils/theme';
import EkasaMark from '../base/EkasaMark.vue';
import FintoMark from '../base/FintoMark.vue';

const session = useSessionStore();
const isFintoBrand = computed(() => currentBrand.value === 'finto');
const status = computed(
  () =>
    session.bootLog[session.bootLog.length - 1] ??
    (isFintoBrand.value ? 'Menyalakan Finto OS…' : 'Menyalakan Ekasa OS…'),
);
const percentText = computed(() => `${String(session.bootProgress).padStart(3, '0')}%`);

function skip() {
  session.skipBoot();
}
</script>

<template>
  <section class="boot" tabindex="0" @click="skip" @keydown="skip">
    <div v-if="isFintoBrand" class="boot-grid" aria-hidden="true" />
    <div v-if="isFintoBrand" class="boot-scanline" aria-hidden="true" />
    <div v-if="isFintoBrand" class="boot-vignette" aria-hidden="true" />

    <div class="boot-center">
      <template v-if="isFintoBrand">
        <div class="boot-logo-wrap">
          <span class="boot-halo" aria-hidden="true" />
          <FintoMark :size="112" class="boot-finto-mark" />
        </div>
        <div class="boot-finto-name">FINTO OS</div>
      </template>
      <template v-else>
        <EkasaMark :size="64" class="boot-mark" />
        <div class="boot-word">Ekasa<span>OS</span></div>
      </template>
      <div
        class="boot-bar"
        :class="{ 'finto-bar': isFintoBrand }"
        role="progressbar"
        aria-label="Memuat"
        :aria-valuenow="session.bootProgress"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <i :style="{ width: session.bootProgress + '%' }" />
      </div>
      <div v-if="isFintoBrand" class="boot-status-row">
        <div class="boot-status">{{ status }}…</div>
        <span class="boot-pct">{{ percentText }}</span>
      </div>
      <div v-else class="boot-status">{{ status }}…</div>
    </div>
    <ol class="boot-log">
      <li v-for="(l, i) in session.bootLog" :key="i">
        <b>[  ok  ]</b> {{ l }}<span v-if="isFintoBrand && i === session.bootLog.length - 1" class="boot-cursor" aria-hidden="true">_</span>
      </li>
    </ol>
    <div class="boot-skip">Tekan sembarang tombol atau klik untuk melewati</div>
  </section>
</template>
