<template>
  <div ref="rootRef" class="suggest-input position-relative">
    <input
      type="text"
      class="form-control"
      :class="[size ? `form-control-${size}` : '', { 'is-invalid': hasError }]"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      autocomplete="off"
      @input="handleInput"
      @focus="open"
      @keydown.down.prevent="move(1)"
      @keydown.up.prevent="move(-1)"
      @keydown.enter="handleEnter"
      @keydown.esc="isOpen = false"
      @keydown.tab="isOpen = false"
    />

    <!-- Daftar saran bergaya halaman (pengganti <datalist> native yang tampil sebagai balon hitam browser) -->
    <div
      v-if="isOpen && filtered.length"
      class="suggest-box border rounded shadow-sm bg-body position-absolute w-100 mt-1 p-1"
    >
      <div
        v-for="(item, idx) in filtered"
        :key="item.value"
        class="suggest-item px-2 py-1 rounded d-flex justify-content-between align-items-center gap-2"
        :class="idx === highlighted ? 'bg-primary-subtle text-primary' : 'text-body'"
        @mouseenter="highlighted = idx"
        @mousedown.prevent="select(item)"
      >
        <div class="text-truncate">
          <div class="text-truncate">{{ item.label }}</div>
          <div v-if="item.sublabel" class="small text-muted text-truncate">{{ item.sublabel }}</div>
        </div>
        <span v-if="item.badge" class="badge bg-light text-secondary small flex-shrink-0">{{ item.badge }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

/**
 * Input teks bebas + daftar saran (mis. nama Company/Yayasan). Berbeda dari LinkAutocomplete,
 * nilai yang belum ada di daftar tetap boleh diketik. Memilih saran mengisi `label` (default)
 * dan memancarkan `select` dengan item yang dipilih.
 */
export interface SuggestOption {
  value: string;
  label: string;
  sublabel?: string;
  badge?: string;
}

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    options: SuggestOption[];
    placeholder?: string;
    disabled?: boolean;
    hasError?: boolean;
    size?: "sm" | "lg";
    limit?: number;
  }>(),
  { modelValue: "", limit: 30 },
);

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void;
  (e: "select", item: SuggestOption): void;
  (e: "enter", value: string): void;
}>();

const rootRef = ref<HTMLElement | null>(null);
const isOpen = ref(false);
const highlighted = ref(-1);

const filtered = computed(() => {
  const q = (props.modelValue || "").trim().toLowerCase();
  const rows = q
    ? props.options.filter(
        (o) =>
          o.label.toLowerCase().includes(q) ||
          o.value.toLowerCase().includes(q) ||
          (o.sublabel || "").toLowerCase().includes(q),
      )
    : props.options;
  // Saran yang sama persis dengan isian tidak perlu ditampilkan lagi.
  return rows.filter((o) => o.label !== props.modelValue).slice(0, props.limit);
});

function open() {
  isOpen.value = true;
  highlighted.value = -1;
}

function handleInput(e: Event) {
  emit("update:modelValue", (e.target as HTMLInputElement).value);
  isOpen.value = true;
  highlighted.value = 0;
}

function move(step: number) {
  if (!isOpen.value) return open();
  const max = filtered.value.length - 1;
  highlighted.value = Math.min(max, Math.max(0, highlighted.value + step));
}

function select(item: SuggestOption) {
  emit("update:modelValue", item.label);
  emit("select", item);
  isOpen.value = false;
}

function handleEnter(e: KeyboardEvent) {
  const item = isOpen.value ? filtered.value[highlighted.value] : undefined;
  e.preventDefault();
  if (item) return select(item);
  isOpen.value = false;
  emit("enter", props.modelValue || "");
}

function handleClickOutside(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) isOpen.value = false;
}

onMounted(() => document.addEventListener("click", handleClickOutside));
onBeforeUnmount(() => document.removeEventListener("click", handleClickOutside));
</script>

<style scoped>
.suggest-box {
  left: 0;
  top: 100%;
  z-index: 1060;
  max-height: 240px;
  overflow-y: auto;
}
.suggest-item {
  cursor: pointer;
  font-size: 0.8125rem;
}
</style>
