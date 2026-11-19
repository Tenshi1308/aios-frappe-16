<script setup lang="ts">
import { computed } from 'vue';
import { useSessionStore } from '../stores/session';
import { currentBrand } from '../utils/theme';
import fintoFlatLogoSvg from '../assets/branding/finto-flat-logo.svg';
import EkasaMark from '../components/base/EkasaMark.vue';

const session = useSessionStore();
const isFintoBrand = computed(() => currentBrand.value === 'finto');
const message = computed(
  () =>
    session.blockedMessage ||
    'Pendaftaranmu sudah kami terima. Administrator akan menghubungimu setelah akunmu siap.',
);
</script>

<template>
  <section class="lock wall">
    <div class="lock-clock">
      <div class="d">Akses dibatasi</div>
    </div>
    <div class="lock-card">
      <div class="avatar xl pending-avatar">
        <img v-if="isFintoBrand" class="avatar-flat-fino" :src="fintoFlatLogoSvg" alt="Fino" />
        <EkasaMark v-else :size="34" accent="var(--on-accent)" />
      </div>
      <div class="lock-name">Menunggu persetujuan</div>
      <div class="lock-mail">{{ message }}</div>
      <div class="lock-actions">
        <button v-if="session.blockedMessage" class="btn ghost wide" type="button" @click="void session.logout()">
          Keluar
        </button>
        <button class="lock-link" type="button" @click="session.phase = 'lock'">Kembali ke layar masuk</button>
      </div>
    </div>
    <div class="lock-foot"><span class="dot ok" /> AIOS · server terhubung</div>
  </section>
</template>
