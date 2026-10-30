<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useSessionStore } from '../stores/session';
import AppIcon from '../components/base/AppIcon.vue';
import EkasaMark from '../components/base/EkasaMark.vue';

const session = useSessionStore();
const now = ref(new Date());
let timer: number | undefined;
onMounted(() => {
  timer = window.setInterval(() => (now.value = new Date()), 15_000);
});
onUnmounted(() => window.clearInterval(timer));

const timeStr = computed(() => now.value.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }));
const longDate = computed(() =>
  now.value.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' }),
);

const email = ref('');
const password = ref('');

async function signIn() {
  if (session.loggingIn) return;
  try {
    await session.login(email.value.trim(), password.value);
    password.value = '';
  } catch (err) {
    console.error('Sign-in failed:', err);
  }
}
</script>

<template>
  <section class="lock wall">
    <div class="lock-clock">
      <div class="t">{{ timeStr }}</div>
      <div class="d">{{ longDate }}</div>
    </div>
    <form class="lock-card" @submit.prevent="signIn">
      <div class="avatar xl"><EkasaMark :size="34" accent="var(--on-accent)" /></div>
      <div class="lock-name">Ekasa Desk</div>
      <div class="lock-mail">Masuk untuk melanjutkan ke desktop</div>
      <div class="lock-fields">
        <div class="lock-field">
          <input
            id="usr"
            v-model="email"
            type="email"
            placeholder="Email"
            autocomplete="username"
            aria-label="Email"
            required
          />
        </div>
        <div class="lock-field">
          <input
            id="pw"
            v-model="password"
            type="password"
            placeholder="Password"
            autocomplete="current-password"
            aria-label="Password"
            required
          />
          <button class="lock-go" type="submit" aria-label="Masuk" :disabled="session.loggingIn">
            <AppIcon name="arrow-right" :size="18" />
          </button>
        </div>
      </div>
      <div v-if="session.lockError" class="lock-error" role="alert">{{ session.lockError }}</div>
      <div class="lock-actions">
        <button class="btn agent wide" type="submit" :disabled="session.loggingIn">
          {{ session.loggingIn ? 'Memproses…' : 'Masuk' }}
        </button>
        <button class="lock-link" type="button" @click="session.phase = 'register'">
          Belum punya akun? Daftar
        </button>
      </div>
    </form>
    <div class="lock-foot"><span class="dot ok" /> AIOS · server terhubung</div>
  </section>
</template>
