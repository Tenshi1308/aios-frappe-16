<template>
  <div class="lock os-wallpaper" @click="reveal" @keydown="reveal">
    <!-- Layar kunci: jam besar; klik / tekan tombol untuk masuk -->
    <transition name="lock-slide">
      <div v-if="!showForm" class="lock-clock" aria-hidden="false">
        <div class="lock-time">{{ time }}</div>
        <div class="lock-date">{{ date }}</div>
        <div class="lock-hint">Klik atau tekan tombol apa saja untuk masuk</div>
      </div>
    </transition>

    <transition name="lock-fade">
      <form v-if="showForm" class="lock-form" @submit.prevent="submit" @click.stop>
        <div class="lock-brand">
          <img :src="spiLogo" alt="Sekolah Programming Indonesia" />
        </div>
        <h1 class="lock-title">Masuk</h1>
        <p class="lock-sub">Gunakan akun SPI Anda</p>
        <div v-if="error" class="alert alert-danger py-2 small w-100" role="alert">{{ error }}</div>
        <label class="visually-hidden" for="os-username">Username atau email</label>
        <input
          id="os-username"
          ref="userInput"
          v-model.trim="username"
          type="text"
          class="form-control lock-input"
          placeholder="Username atau email"
          autocomplete="username"
          required
        />
        <div class="lock-pass">
          <label class="visually-hidden" for="os-password">Kata sandi</label>
          <input
            id="os-password"
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            class="form-control lock-input"
            placeholder="Kata sandi"
            autocomplete="current-password"
            required
          />
          <button type="submit" class="lock-go" :disabled="loading" aria-label="Masuk">
            <span v-if="loading" class="spinner-border spinner-border-sm"></span>
            <i v-else class="iconoir-arrow-right"></i>
          </button>
        </div>
        <button type="button" class="btn btn-link btn-sm text-white-50 mt-1" @click="showPassword = !showPassword">
          {{ showPassword ? "Sembunyikan" : "Tampilkan" }} kata sandi
        </button>
      </form>
    </transition>

    <div class="lock-footer">Powered by Finto OS</div>
  </div>
</template>

<script setup lang="ts">
/** Layar login mode desktop (gaya layar kunci sistem operasi). Setelah login langsung ke desktop. */
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import "../desktop.css";
import spiLogo from "@/assets/images/spi-logo-full.png";
import { getAuthErrorMessage } from "@/features/auth/api";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const showForm = ref(false);
const username = ref("");
const password = ref("");
const showPassword = ref(false);
const loading = ref(false);
const error = ref("");
const userInput = ref<HTMLInputElement | null>(null);

const time = ref("");
const date = ref("");
let clock: ReturnType<typeof setInterval> | undefined;

function tick() {
  const now = new Date();
  time.value = now.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
  date.value = now.toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long" });
}

async function reveal() {
  if (showForm.value) return;
  showForm.value = true;
  await nextTick();
  userInput.value?.focus();
}

function onKey(e: KeyboardEvent) {
  if (!showForm.value && !e.metaKey && !e.ctrlKey) reveal();
}

async function submit() {
  if (loading.value) return;
  loading.value = true;
  error.value = "";
  try {
    await auth.login({ username: username.value, password: password.value });
    const from = route.query.redirectedFrom;
    // Router membuka halaman tujuan sebagai jendela di desktop.
    await router.replace(typeof from === "string" && from !== "/" ? from : { name: "desktop.home" });
  } catch (err) {
    error.value = getAuthErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  tick();
  clock = setInterval(tick, 10_000);
  window.addEventListener("keydown", onKey);
});

onBeforeUnmount(() => {
  clearInterval(clock);
  window.removeEventListener("keydown", onKey);
});
</script>

<style scoped>
.lock {
  position: fixed;
  inset: 0;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.lock-clock {
  position: absolute;
  top: 16vh;
  text-align: center;
  text-shadow: 0 2px 12px rgba(0, 0, 0, 0.35);
}
.lock-time {
  font-size: clamp(64px, 12vw, 120px);
  font-weight: 600;
  line-height: 1;
}
.lock-date {
  font-size: clamp(18px, 2.4vw, 26px);
  margin-top: 8px;
}
.lock-hint {
  margin-top: 40vh;
  font-size: 13px;
  opacity: 0.75;
}
.lock-form {
  width: min(340px, calc(100vw - 32px));
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 28px 24px;
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.35);
  backdrop-filter: blur(18px);
}
.lock-brand {
  width: 100%;
  background: #fff;
  border-radius: 12px;
  padding: 10px 16px;
  margin-bottom: 6px;
  display: flex;
  justify-content: center;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
}
.lock-brand img {
  width: 100%;
  max-width: 260px;
  height: auto;
  /* logo SPI berlatar putih: potong margin kosong di atas/bawah gambar */
  aspect-ratio: 976 / 300;
  object-fit: cover;
}
.lock-title {
  font-size: 22px;
  margin: 0;
  font-weight: 600;
}
.lock-sub {
  font-size: 13px;
  opacity: 0.8;
  margin: 0 0 8px;
}
.lock-input {
  background: rgba(255, 255, 255, 0.92);
  border: 0;
}
.lock-pass {
  position: relative;
  width: 100%;
}
.lock-pass .lock-input {
  padding-right: 44px;
}
.lock-go {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  width: 34px;
  height: 30px;
  border: 0;
  border-radius: 6px;
  background: var(--bs-primary, #176df8);
  color: #fff;
}
.lock-footer {
  position: absolute;
  bottom: 18px;
  font-size: 12px;
  opacity: 0.7;
}
.lock-slide-leave-active,
.lock-fade-enter-active {
  transition: all 0.35s ease;
}
.lock-slide-leave-to {
  transform: translateY(-60px);
  opacity: 0;
}
.lock-fade-enter-from {
  opacity: 0;
  transform: scale(0.97);
}
</style>
