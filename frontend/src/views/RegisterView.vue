<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { useSessionStore } from '../stores/session';
import { listCountries } from '../api/session';
import EkasaMark from '../components/base/EkasaMark.vue';

const session = useSessionStore();
const form = reactive({ full_name: '', email: '', company_name: '', country: '' });
const countries = ref<string[]>([]);
const loadingCountries = ref(false);

onMounted(async () => {
  loadingCountries.value = true;
  try {
    countries.value = await listCountries();
  } catch (err) {
    session.registerError = err instanceof Error ? err.message : 'Gagal memuat daftar negara.';
  } finally {
    loadingCountries.value = false;
  }
});

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
        <div class="lock-field">
          <select v-model="form.country" aria-label="Negara" required :disabled="loadingCountries">
            <option value="" disabled>{{ loadingCountries ? 'Memuat negara…' : 'Pilih negara' }}</option>
            <option v-for="c in countries" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>
      </div>
      <div v-if="session.registerError" class="lock-error" role="alert">{{ session.registerError }}</div>
      <div class="lock-actions">
        <button class="btn agent wide" type="submit" :disabled="session.registering || loadingCountries">
          {{ session.registering ? 'Mengirim…' : 'Daftar' }}
        </button>
        <button class="lock-link" type="button" @click="session.phase = 'lock'">Sudah punya akun? Masuk</button>
      </div>
    </form>
    <div class="lock-foot"><span class="dot ok" /> AIOS · server terhubung</div>
  </section>
</template>
