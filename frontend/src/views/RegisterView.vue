<script setup lang="ts">
import { reactive } from 'vue';
import { useSessionStore } from '../stores/session';
import EkasaMark from '../components/base/EkasaMark.vue';

const session = useSessionStore();
const form = reactive({ full_name: '', email: '', company_name: '' });

async function submit() {
  if (session.registering) return;
  try {
    await session.register({ ...form });
  } catch {
    // pesan aman sudah di session.registerError
  }
}
</script>

<template>
  <section class="lock wall">
    <div class="lock-clock">
      <div class="d">Pendaftaran mandiri</div>
    </div>
    <form class="lock-card" @submit.prevent="submit">
      <div class="avatar xl"><EkasaMark :size="34" accent="var(--on-accent)" /></div>
      <div class="lock-name">Buat akun AIOS</div>
      <div class="lock-mail">Akun baru menunggu persetujuan administrator</div>
      <div class="lock-fields">
        <div class="lock-field">
          <input v-model="form.full_name" type="text" placeholder="Nama lengkap" aria-label="Nama lengkap" required />
        </div>
        <div class="lock-field">
          <input v-model="form.email" type="email" placeholder="Email" autocomplete="username" aria-label="Email" required />
        </div>
        <div class="lock-field">
          <input v-model="form.company_name" type="text" placeholder="Nama perusahaan" aria-label="Nama perusahaan" required />
        </div>
      </div>
      <div v-if="session.registerError" class="lock-error" role="alert">{{ session.registerError }}</div>
      <div class="lock-actions">
        <button class="btn agent wide" type="submit" :disabled="session.registering">
          {{ session.registering ? 'Mengirim…' : 'Daftar' }}
        </button>
        <button class="lock-link" type="button" @click="session.phase = 'lock'">Sudah punya akun? Masuk</button>
      </div>
    </form>
    <div class="lock-foot"><span class="dot ok" /> AIOS · server terhubung</div>
  </section>
</template>
