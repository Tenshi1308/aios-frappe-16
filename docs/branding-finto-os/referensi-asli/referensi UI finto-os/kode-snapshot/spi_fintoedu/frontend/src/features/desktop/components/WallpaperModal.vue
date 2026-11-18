<template>
  <b-modal :model-value="modelValue" title="Ganti Latar Belakang" size="lg" centered hide-footer @update:model-value="emit('update:modelValue', $event)">
    <p class="text-muted small mb-3">
      Pilihan ini hanya berlaku untuk akun Anda dan ikut tersimpan di perangkat lain saat Anda login.
    </p>

    <h6 class="fw-semibold mb-2">Latar bawaan</h6>
    <div class="wp-grid mb-4">
      <button
        v-for="p in WALLPAPER_PRESETS"
        :key="p.id"
        type="button"
        class="wp-thumb"
        :class="{ active: current.kind === 'preset' && current.value === p.id }"
        :style="{ background: p.css }"
        :disabled="!!saving"
        :aria-pressed="current.kind === 'preset' && current.value === p.id"
        @click="choosePreset(p.id)"
      >
        <span class="wp-label">{{ p.label }}</span>
        <i v-if="current.kind === 'preset' && current.value === p.id" class="iconoir-check wp-check"></i>
      </button>
    </div>

    <h6 class="fw-semibold mb-2">Gambar sendiri</h6>
    <div class="d-flex flex-wrap align-items-center gap-3">
      <div v-if="current.kind === 'image'" class="wp-thumb wp-own active" :style="{ backgroundImage: `url('${current.value}')` }">
        <span class="wp-label">Gambar Anda</span>
        <i class="iconoir-check wp-check"></i>
      </div>
      <label class="btn btn-outline-primary mb-0" :class="{ disabled: saving }">
        <input type="file" accept="image/jpeg,image/png,image/webp" class="visually-hidden" :disabled="!!saving" @change="onFile" />
        <b-spinner v-if="saving === 'upload'" small class="me-1" />
        <i v-else class="iconoir-upload me-1"></i>
        Unggah gambar (JPG/PNG/WEBP, maks. 5 MB)
      </label>
      <b-button variant="link" class="text-body px-0" :disabled="!!saving" @click="reset">Kembalikan bawaan</b-button>
    </div>
    <div v-if="error" class="alert alert-danger py-2 small mt-3 mb-0">{{ error }}</div>
  </b-modal>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { extractErrorMessage } from "@/features/students/api";
import { WALLPAPER_PRESETS } from "../wallpapers";
import { resetWallpaper, setWallpaperPreset, uploadWallpaper, type Wallpaper } from "../prefsApi";

defineProps<{ modelValue: boolean; current: Wallpaper }>();
const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "changed", value: Wallpaper): void;
}>();

const MAX_BYTES = 5 * 1024 * 1024;
const saving = ref<"" | "preset" | "upload" | "reset">("");
const error = ref("");

async function run(kind: "preset" | "upload" | "reset", fn: () => Promise<{ wallpaper: Wallpaper }>) {
  saving.value = kind;
  error.value = "";
  try {
    emit("changed", (await fn()).wallpaper);
  } catch (err) {
    error.value = extractErrorMessage(err);
  } finally {
    saving.value = "";
  }
}

function choosePreset(id: string) {
  run("preset", () => setWallpaperPreset(id));
}

function onFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
    error.value = "Format gambar harus JPG, PNG, atau WEBP.";
    return;
  }
  if (file.size > MAX_BYTES) {
    error.value = "Ukuran gambar maksimal 5 MB.";
    return;
  }
  run("upload", () => uploadWallpaper(file));
}

function reset() {
  run("reset", () => resetWallpaper());
}
</script>

<style scoped>
.wp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}
.wp-thumb {
  position: relative;
  height: 86px;
  border-radius: 10px;
  border: 2px solid transparent;
  background-size: cover !important;
  background-position: center !important;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
  overflow: hidden;
  padding: 0;
}
.wp-own {
  width: 140px;
}
.wp-thumb:hover {
  border-color: rgba(23, 109, 248, 0.5);
}
.wp-thumb.active {
  border-color: var(--bs-primary);
}
.wp-label {
  position: absolute;
  left: 8px;
  bottom: 6px;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.6);
}
.wp-check {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--bs-primary);
  color: #fff;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
