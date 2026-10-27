<script setup lang="ts">
import { useSessionStore } from '../../stores/session';
import EkasaMark from '../base/EkasaMark.vue';

const session = useSessionStore();
</script>

<template>
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
</template>
