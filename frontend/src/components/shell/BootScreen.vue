<script setup lang="ts">
import { computed } from 'vue';
import { useSessionStore } from '../../stores/session';
import { currentBrand, isDarkEffective } from '../../utils/theme';
import lockupPillImg from '../../assets/branding/finto-logo-pill-blue.png';
import lockupLightImg from '../../assets/branding/finto-logo-utama-nobg.png';
import EkasaMark from '../base/EkasaMark.vue';

const session = useSessionStore();
const isFintoBrand = computed(() => currentBrand.value === 'finto');
const isDark = computed(() => isDarkEffective());
const lockupSrc = computed(() => (isDark.value ? lockupPillImg : lockupLightImg));
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
          <img class="boot-lockup" :class="{ 'light-lockup': !isDark }" :src="lockupSrc" alt="Finto OS" />
        </div>
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
