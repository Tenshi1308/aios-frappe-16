<script setup lang="ts">
import { computed } from 'vue';
import { useSessionStore } from '../../stores/session';
import { currentBrand, isDarkEffective } from '../../utils/theme';
import lockupLightImg from '../../assets/branding/finto-logo-utama-nobg.png';
import lockupDarkImg from '../../assets/branding/finto-logo-pill-blue.png';
import fintoHeroFrontImg from '../../assets/branding/finto-hero-front-transparent.png';
import EkasaMark from '../base/EkasaMark.vue';

const session = useSessionStore();
const isFintoBrand = computed(() => currentBrand.value === 'finto');
const lockupSrc = computed(() => (isDarkEffective() ? lockupDarkImg : lockupLightImg));
</script>

<template>
  <div class="about">
    <template v-if="isFintoBrand">
      <img class="about-lockup" :src="lockupSrc" alt="Finto OS" />
      <img class="about-mascot" :src="fintoHeroFrontImg" alt="Fino" />
      <div class="about-line">
        Desktop bisnis cerdas: tanyakan data dan pekerjaanmu kepada agent, lampirkan berkas,
        dan pantau semuanya dari satu layar.
      </div>
    </template>
    <template v-else>
      <EkasaMark :size="44" />
      <div class="about-word">Ekasa Desk</div>
      <div class="about-line">
        Desktop AIOS untuk bisnis: tanyakan data dan pekerjaanmu kepada agent, lampirkan berkas,
        dan pantau semuanya dari satu layar.
      </div>
    </template>
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
</template>
