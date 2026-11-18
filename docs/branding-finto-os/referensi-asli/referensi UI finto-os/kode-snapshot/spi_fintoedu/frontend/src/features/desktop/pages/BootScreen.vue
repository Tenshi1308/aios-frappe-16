<template>
  <div class="boot" :class="{ leaving }" role="status" aria-live="polite" :aria-label="`Finto OS sedang memulai, ${progress}%`">
    <div class="boot-grid" aria-hidden="true"></div>
    <div class="boot-scan" aria-hidden="true"></div>
    <div class="boot-vignette" aria-hidden="true"></div>

    <div class="boot-center">
      <!-- Logo utama Finto OS (assets/images/finto-os-logo.png, pemilik 12 Nov 2026): muncul, berkilau, lalu berdenyut -->
      <div class="boot-logo-wrap" aria-hidden="true">
        <div class="boot-halo"></div>
        <img :src="logo" alt="" class="boot-logo" draggable="false" />
        <div class="boot-shine"></div>
      </div>

      <div class="boot-name" aria-hidden="true">
        <span v-for="(ch, i) in 'FINTO OS'" :key="i" class="ch" :style="{ animationDelay: `${0.9 + i * 0.06}s` }">{{ ch === " " ? " " : ch }}</span>
      </div>
      <div class="boot-ver">v1.0 · build 2026.11</div>

      <div class="boot-progress" aria-hidden="true">
        <div class="boot-bar" :style="{ width: `${progress}%` }"></div>
      </div>
      <div class="boot-pct">{{ progress.toString().padStart(3, "0") }}%</div>

      <ul class="boot-log" aria-hidden="true">
        <li v-for="(line, i) in shown" :key="i">
          <span class="ok">[ OK ]</span> {{ line }}
        </li>
        <li v-if="shown.length < LOG.length" class="cursor">_</li>
      </ul>
    </div>

  </div>
</template>

<script setup lang="ts">
/**
 * Animasi booting Finto OS (mode desktop, sebelum login; setiap halaman dimuat/refresh, bukan saat navigasi di dalam aplikasi).
 * Logo Finto OS + log booting bergaya terminal + progress. Logo SPI tampil di layar login.
 * Tanpa tombol "Lewati" (keputusan pemilik 12 Nov 2026); durasi tetap ±4 detik (1,5 detik bila reduced-motion).
 * Palet Finto OS (12 Nov 2026): Navy #0B1F3B (primary), Blue #0E63FF (brand), Cyan #00D4C8 (intelligence),
 * Lime #A7F432 (growth), Violet #8B5CF6 (innovation), Light #F3F7FB (surface).
 */
import { onBeforeUnmount, onMounted, ref } from "vue";
import logo from "@/assets/images/finto-os-logo.png";
import { useRoute, useRouter } from "vue-router";
import { useUiStore } from "@/stores/ui";

const router = useRouter();
const route = useRoute();
const ui = useUiStore();

const LOG = [
  "Memulai kernel Finto OS",
  "Memeriksa koneksi server sekolah",
  "Memuat modul Admisi & Murid",
  "Memuat modul Akademik & LMS",
  "Memuat modul Keuangan SPP",
  "Memuat modul Penggajian",
  "Menyiapkan antarmuka desktop",
];
const DURATION = 4200;

const shown = ref<string[]>([]);
const progress = ref(0);
const leaving = ref(false);
const timers: ReturnType<typeof setTimeout>[] = [];
let raf = 0;

function finish() {
  if (leaving.value) return;
  leaving.value = true;
  progress.value = 100;
  ui.markBooted();
  timers.push(setTimeout(() => router.replace({ name: "desktop.login", query: route.query }), 500));
}

onMounted(() => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const total = reduce ? 1500 : DURATION;
  const start = performance.now();
  const tick = (now: number) => {
    // progres sedikit tersendat agar terasa "memuat"
    const t = Math.min(1, (now - start) / total);
    const eased = 1 - Math.pow(1 - t, 2.2);
    progress.value = Math.min(99, Math.floor(eased * 100));
    if (t < 1 && !leaving.value) raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
  LOG.forEach((line, i) => timers.push(setTimeout(() => shown.value.push(line), 700 + (i * (total - 1100)) / LOG.length)));
  timers.push(setTimeout(finish, total + 250));
});

onBeforeUnmount(() => {
  timers.forEach(clearTimeout);
  cancelAnimationFrame(raf);
});
</script>

<style scoped>
.boot {
  --fos-navy: #0b1f3b;
  --fos-blue: #0e63ff;
  --fos-cyan: #00d4c8;
  --fos-lime: #a7f432;
  --fos-violet: #8b5cf6;
  --fos-light: #f3f7fb;
  position: fixed;
  inset: 0;
  z-index: 3000;
  background:
    radial-gradient(ellipse at 50% 38%, rgba(14, 99, 255, 0.28) 0%, transparent 55%),
    radial-gradient(ellipse at 50% 40%, #12305a 0%, var(--fos-navy) 55%, #06111f 100%);
  color: var(--fos-light);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  transition: opacity 0.5s ease, transform 0.5s ease;
}
.boot.leaving {
  opacity: 0;
  transform: scale(1.02);
}

/* Lantai grid perspektif yang bergerak */
.boot-grid {
  position: absolute;
  left: -50%;
  right: -50%;
  bottom: -10%;
  height: 60%;
  background-image:
    linear-gradient(rgba(0, 212, 200, 0.2) 1px, transparent 1px),
    linear-gradient(90deg, rgba(14, 99, 255, 0.22) 1px, transparent 1px);
  background-size: 48px 48px;
  transform: perspective(420px) rotateX(62deg);
  transform-origin: bottom;
  animation: grid-move 2.4s linear infinite;
  mask-image: linear-gradient(to top, rgba(0, 0, 0, 0.9), transparent);
}
.boot-scan {
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(to bottom, rgba(255, 255, 255, 0.025) 0 1px, transparent 1px 3px);
  pointer-events: none;
}
.boot-scan::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  height: 120px;
  background: linear-gradient(to bottom, transparent, rgba(0, 212, 200, 0.07), transparent);
  animation: scan 3.2s linear infinite;
}
.boot-vignette {
  position: absolute;
  inset: 0;
  box-shadow: inset 0 0 180px rgba(4, 12, 24, 0.85);
  pointer-events: none;
}

.boot-center {
  position: relative;
  width: min(440px, calc(100vw - 48px));
  display: flex;
  flex-direction: column;
  align-items: center;
}
.boot-logo-wrap {
  position: relative;
  width: 112px;
  height: 116px;
  opacity: 0;
  transform: scale(0.6) translateY(8px);
  animation: logo-in 0.9s cubic-bezier(0.2, 0.9, 0.25, 1.15) 0.15s forwards;
}
.boot-logo {
  position: relative;
  width: 100%;
  height: 100%;
  object-fit: contain;
  user-select: none;
  animation: logo-pulse 2.4s ease-in-out 1.4s infinite;
}
.boot-halo {
  position: absolute;
  inset: -28px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(0, 212, 200, 0.35) 0%, rgba(14, 99, 255, 0.18) 45%, transparent 70%);
  filter: blur(6px);
  animation: halo 2.4s ease-in-out 1.4s infinite;
}
/* kilau yang menyapu logo sekali setelah muncul */
.boot-shine {
  position: absolute;
  inset: 0;
  -webkit-mask: url("@/assets/images/finto-os-logo.png") center / contain no-repeat;
  mask: url("@/assets/images/finto-os-logo.png") center / contain no-repeat;
  background: linear-gradient(110deg, transparent 35%, rgba(243, 247, 251, 0.85) 50%, transparent 65%) -150% 0 / 250% 100% no-repeat;
  animation: shine 1.1s ease-in-out 1s forwards;
}

.boot-name {
  margin-top: 18px;
  font-family: "Segoe UI", Inter, system-ui, sans-serif;
  font-size: 30px;
  font-weight: 300;
  letter-spacing: 0.45em;
  padding-left: 0.45em;
  color: var(--fos-light);
  text-shadow: 0 0 12px rgba(0, 212, 200, 0.6), 0 0 28px rgba(14, 99, 255, 0.5);
}
.ch {
  display: inline-block;
  opacity: 0;
  transform: translateY(6px);
  animation: ch-in 0.35s ease-out forwards;
}
.boot-ver {
  margin-top: 4px;
  font-size: 11px;
  color: rgba(243, 247, 251, 0.6);
  letter-spacing: 0.15em;
  opacity: 0;
  animation: fade-in 0.4s ease 1.5s forwards;
}

.boot-progress {
  margin-top: 30px;
  width: 100%;
  height: 3px;
  background: rgba(243, 247, 251, 0.12);
  border-radius: 2px;
  overflow: hidden;
}
.boot-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--fos-blue), var(--fos-cyan), var(--fos-lime));
  box-shadow: 0 0 12px rgba(0, 212, 200, 0.8);
  transition: width 0.12s linear;
}
.boot-pct {
  align-self: flex-end;
  margin-top: 6px;
  font-size: 11px;
  color: var(--fos-cyan);
}

.boot-log {
  list-style: none;
  margin: 14px 0 0;
  padding: 0;
  width: 100%;
  min-height: 150px;
  font-size: 12px;
  line-height: 1.7;
  color: rgba(243, 247, 251, 0.82);
}
.boot-log li {
  animation: line-in 0.25s ease-out;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ok {
  color: var(--fos-lime);
}
.cursor {
  color: var(--fos-cyan);
  animation: blink 0.9s steps(1) infinite;
}

@keyframes logo-in {
  to {
    opacity: 1;
    transform: none;
  }
}
@keyframes halo {
  0%,
  100% {
    opacity: 0.55;
    transform: scale(0.95);
  }
  50% {
    opacity: 1;
    transform: scale(1.05);
  }
}
@keyframes shine {
  to {
    background-position: 150% 0;
  }
}
@keyframes logo-pulse {
  0%,
  100% {
    filter: drop-shadow(0 0 6px rgba(0, 212, 200, 0.4));
  }
  50% {
    filter: drop-shadow(0 0 18px rgba(167, 244, 50, 0.55));
  }
}
@keyframes ch-in {
  to {
    opacity: 1;
    transform: none;
  }
}
@keyframes fade-in {
  to {
    opacity: 1;
  }
}
@keyframes line-in {
  from {
    opacity: 0;
    transform: translateX(-6px);
  }
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
@keyframes grid-move {
  to {
    background-position: 0 48px, 0 0;
  }
}
@keyframes scan {
  from {
    top: -120px;
  }
  to {
    top: 100%;
  }
}
@media (prefers-reduced-motion: reduce) {
  .boot-grid,
  .boot-scan::after,
  .boot-logo,
  .boot-halo,
  .boot-shine,
  .cursor {
    animation: none;
  }
  .boot-logo-wrap {
    animation-duration: 0.01s;
  }
}
</style>
