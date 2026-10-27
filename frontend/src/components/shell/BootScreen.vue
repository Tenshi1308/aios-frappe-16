<script setup lang="ts">
import { computed } from 'vue';
import { useSessionStore } from '../../stores/session';
import EkasaMark from '../base/EkasaMark.vue';

const session = useSessionStore();
const status = computed(() => session.bootLog[session.bootLog.length - 1] ?? 'Menyalakan Ekasa OS…');

function skip() {
  if (session.bootProgress < 100) session.setProgress(100);
}
</script>

<template>
  <section class="boot" @click="skip" @keydown="skip">
    <div class="boot-center">
      <EkasaMark :size="64" class="boot-mark" />
      <div class="boot-word">Ekasa<span>OS</span></div>
      <div
        class="boot-bar"
        role="progressbar"
        aria-label="Memuat"
        :aria-valuenow="session.bootProgress"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <i :style="{ width: session.bootProgress + '%' }" />
      </div>
      <div class="boot-status">{{ status }}…</div>
    </div>
    <ol class="boot-log">
      <li v-for="(l, i) in session.bootLog" :key="i"><b>[  ok  ]</b> {{ l }}</li>
    </ol>
    <div class="boot-skip">Tekan sembarang tombol atau klik untuk melewati</div>
  </section>
</template>
