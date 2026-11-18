<template>
  <Teleport to="body">
    <div v-if="modelValue && current" class="spi-tour" role="dialog" aria-modal="true" :aria-label="title">
      <!-- Lapisan gelap + "lubang" sorotan di elemen target -->
      <div v-if="rect" class="spi-tour-spotlight" :style="spotlightStyle"></div>
      <div v-else class="spi-tour-backdrop"></div>
      <!-- Penangkap klik: halaman tidak bisa diklik selama tur -->
      <div class="spi-tour-blocker" @click.stop></div>

      <div ref="cardEl" class="card shadow-lg spi-tour-card" :class="`placement-${resolvedPlacement}`" :style="cardStyle">
        <div class="card-body p-3">
          <div class="d-flex align-items-center justify-content-between mb-2 gap-2">
            <span class="badge bg-primary-subtle text-primary text-truncate">{{ eyebrow || title }}</span>
            <small class="text-muted flex-shrink-0">Langkah {{ index + 1 }} / {{ visibleSteps.length }}</small>
          </div>
          <h6 class="fw-semibold mb-1">{{ current.title }}</h6>
          <p class="text-muted small mb-3 spi-tour-body">{{ current.body }}</p>
          <div class="progress mb-3" style="height: 4px">
            <div class="progress-bar" :style="{ width: `${((index + 1) / visibleSteps.length) * 100}%` }"></div>
          </div>
          <div class="d-flex align-items-center">
            <button type="button" class="btn btn-link btn-sm text-body px-0" @click="finish">Lewati tur</button>
            <div class="ms-auto d-flex gap-2">
              <button v-if="index > 0" type="button" class="btn btn-outline-dark btn-sm" @click="go(index - 1)">Kembali</button>
              <button v-if="!isLast" type="button" class="btn btn-primary btn-sm" @click="go(index + 1)">Lanjut</button>
              <button v-else type="button" class="btn btn-primary btn-sm" @click="finish">{{ finishLabel }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
/**
 * Tur langkah demi langkah yang MENYOROT elemen di halaman.
 * - Target: elemen dengan atribut `data-guide="<key>"` (lihat assets/data/page-tours.ts).
 * - Langkah yang targetnya tidak ada / tersembunyi (mis. tombol yang disembunyikan untuk role tsb) dilewati otomatis.
 * - Langkah tanpa target tampil di tengah layar.
 * - Keyboard: → / Enter = lanjut, ← = kembali, Esc = lewati.
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";

export type TourStep = {
  target?: string;
  title: string;
  body: string;
  placement?: "top" | "bottom" | "left" | "right";
};

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    title: string;
    steps: TourStep[];
    eyebrow?: string;
    finishLabel?: string;
  }>(),
  { eyebrow: "", finishLabel: "Selesai" },
);

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "done"): void;
}>();

const PADDING = 8;
const GAP = 14;
const CARD_WIDTH = 340;

const index = ref(0);
const visibleSteps = ref<TourStep[]>([]);
const rect = ref<DOMRect | null>(null);
const cardEl = ref<HTMLElement | null>(null);
const cardHeight = ref(180);
const viewport = ref({ w: window.innerWidth, h: window.innerHeight });
let raf = 0;

const current = computed(() => visibleSteps.value[index.value]);
const isLast = computed(() => index.value >= visibleSteps.value.length - 1);

function findTarget(step?: TourStep): HTMLElement | null {
  if (!step?.target) return null;
  const el = document.querySelector<HTMLElement>(`[data-guide="${CSS.escape(step.target)}"]`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  const style = window.getComputedStyle(el);
  if ((r.width === 0 && r.height === 0) || style.visibility === "hidden" || style.display === "none") return null;
  return el;
}

function computeVisibleSteps() {
  // Langkah dengan target yang tidak tersedia untuk user ini dibuang agar tur tidak "menunjuk ke kosong".
  visibleSteps.value = props.steps.filter((s) => !s.target || findTarget(s));
}

function measure() {
  const el = findTarget(current.value);
  rect.value = el ? el.getBoundingClientRect() : null;
  viewport.value = { w: window.innerWidth, h: window.innerHeight };
  if (cardEl.value) cardHeight.value = cardEl.value.offsetHeight;
}

function scheduleMeasure() {
  cancelAnimationFrame(raf);
  raf = requestAnimationFrame(measure);
}

async function go(i: number) {
  index.value = Math.max(0, Math.min(i, visibleSteps.value.length - 1));
  const el = findTarget(current.value);
  if (el) {
    el.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
  }
  await nextTick();
  measure();
  // smooth scroll: ukur ulang beberapa kali sampai posisi stabil
  setTimeout(measure, 250);
  setTimeout(measure, 500);
}

function finish() {
  emit("update:modelValue", false);
  emit("done");
}

function onKey(e: KeyboardEvent) {
  if (!props.modelValue) return;
  if (e.key === "Escape") finish();
  else if (e.key === "ArrowRight" || e.key === "Enter") (isLast.value ? finish() : go(index.value + 1));
  else if (e.key === "ArrowLeft" && index.value > 0) go(index.value - 1);
}

const spotlightStyle = computed(() => {
  const r = rect.value;
  if (!r) return {};
  return {
    top: `${r.top - PADDING}px`,
    left: `${r.left - PADDING}px`,
    width: `${r.width + PADDING * 2}px`,
    height: `${r.height + PADDING * 2}px`,
  };
});

const resolvedPlacement = computed<"top" | "bottom" | "left" | "right" | "center">(() => {
  const r = rect.value;
  if (!r) return "center";
  const { w, h } = viewport.value;
  const preferred = current.value?.placement;
  const fits = {
    bottom: r.bottom + GAP + cardHeight.value < h,
    top: r.top - GAP - cardHeight.value > 0,
    right: r.right + GAP + CARD_WIDTH < w,
    left: r.left - GAP - CARD_WIDTH > 0,
  };
  if (preferred && fits[preferred]) return preferred;
  if (w < 576) return fits.bottom ? "bottom" : fits.top ? "top" : "center";
  return (["bottom", "top", "right", "left"] as const).find((p) => fits[p]) ?? "center";
});

const cardStyle = computed(() => {
  const r = rect.value;
  const { w, h } = viewport.value;
  const width = Math.min(CARD_WIDTH, w - 32);
  const clampX = (x: number) => Math.max(16, Math.min(x, w - width - 16));
  const clampY = (y: number) => Math.max(16, Math.min(y, h - cardHeight.value - 16));
  const base = { width: `${width}px` };
  switch (resolvedPlacement.value) {
    case "bottom":
      return { ...base, top: `${r!.bottom + GAP}px`, left: `${clampX(r!.left + r!.width / 2 - width / 2)}px` };
    case "top":
      return { ...base, top: `${r!.top - GAP - cardHeight.value}px`, left: `${clampX(r!.left + r!.width / 2 - width / 2)}px` };
    case "right":
      return { ...base, top: `${clampY(r!.top + r!.height / 2 - cardHeight.value / 2)}px`, left: `${r!.right + GAP}px` };
    case "left":
      return { ...base, top: `${clampY(r!.top + r!.height / 2 - cardHeight.value / 2)}px`, left: `${r!.left - GAP - width}px` };
    default:
      return { ...base, top: `${Math.max(16, h / 2 - cardHeight.value / 2)}px`, left: `${w / 2 - width / 2}px` };
  }
});

function attach() {
  window.addEventListener("resize", scheduleMeasure);
  window.addEventListener("scroll", scheduleMeasure, true);
  window.addEventListener("keydown", onKey);
}

function detach() {
  window.removeEventListener("resize", scheduleMeasure);
  window.removeEventListener("scroll", scheduleMeasure, true);
  window.removeEventListener("keydown", onKey);
  cancelAnimationFrame(raf);
}

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) {
      detach();
      return;
    }
    // tunggu halaman selesai render (data async) sebelum mencari target
    await nextTick();
    await new Promise((resolve) => setTimeout(resolve, 350));
    computeVisibleSteps();
    if (!visibleSteps.value.length) {
      finish();
      return;
    }
    attach();
    go(0);
  },
  { immediate: true },
);

onBeforeUnmount(detach);
</script>

<style scoped>
.spi-tour {
  position: fixed;
  inset: 0;
  z-index: 1090;
}
.spi-tour-blocker {
  position: fixed;
  inset: 0;
  z-index: 1;
}
.spi-tour-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.55);
}
.spi-tour-spotlight {
  position: fixed;
  border-radius: 10px;
  box-shadow: 0 0 0 9999px rgba(15, 23, 42, 0.55);
  outline: 3px solid var(--bs-primary, #176df8);
  outline-offset: 2px;
  transition: all 0.25s ease;
  pointer-events: none;
}
.spi-tour-card {
  position: fixed;
  z-index: 2;
  border: 0;
  border-radius: 12px;
  transition: top 0.25s ease, left 0.25s ease;
}
.spi-tour-body {
  white-space: pre-line;
}
</style>
