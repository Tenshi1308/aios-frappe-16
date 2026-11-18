<template>
  <div class="link-autocomplete position-relative" ref="rootRef">
    <label v-if="label" class="form-label fw-semibold small">
      {{ label }} <span v-if="required" class="text-danger">*</span>
    </label>

    <div class="input-group">
      <span class="input-group-text bg-transparent border-end-0 text-muted">
        <i class="iconoir-search"></i>
      </span>
      <input
        type="text"
        class="form-control border-start-0 border-end-0"
        :class="{ 'is-invalid': hasError }"
        :placeholder="placeholder || 'Ketik untuk mencari...'"
        :value="displayLabel"
        :disabled="disabled"
        @input="handleInput"
        @focus="handleFocus"
        @keydown.down.prevent="navigateDown"
        @keydown.up.prevent="navigateUp"
        @keydown.enter.prevent="selectHighlighted"
        @keydown.esc="isOpen = false"
      />
      <button
        v-if="modelValue && !disabled"
        type="button"
        class="input-group-text bg-transparent border-start-0 text-muted"
        title="Hapus pilihan"
        @click="clearSelection"
      >
        <i class="iconoir-cancel"></i>
      </button>
      <span v-else class="input-group-text bg-transparent border-start-0 text-muted">
        <i class="iconoir-nav-arrow-down small"></i>
      </span>
    </div>

    <!-- Suggestion Dropdown List -->
    <div
      v-if="isOpen && filteredOptions.length > 0"
      class="suggestion-box shadow-lg rounded border bg-white position-absolute w-100 mt-1 p-1 z-3"
      style="max-height: 240px; overflow-y: auto; left: 0; top: 100%;"
    >
      <div
        v-for="(item, idx) in filteredOptions"
        :key="item.value"
        class="suggestion-item p-2 rounded cursor-pointer d-flex justify-content-between align-items-center"
        :class="{ 'bg-primary-subtle text-primary fw-semibold': idx === highlightedIndex, 'text-dark': idx !== highlightedIndex }"
        @mouseenter="highlightedIndex = idx"
        @mousedown.prevent="selectOption(item)"
      >
        <div>
          <div class="fw-semibold">{{ item.label }}</div>
          <div v-if="item.sublabel" class="small text-muted">{{ item.sublabel }}</div>
        </div>
        <span v-if="item.badge" class="badge bg-light text-secondary ms-2 small">
          {{ item.badge }}
        </span>
      </div>
    </div>

    <div
      v-else-if="isOpen && query && filteredOptions.length === 0"
      class="suggestion-box shadow-sm rounded border bg-white position-absolute w-100 mt-1 p-3 text-center text-muted small z-3"
      style="left: 0; top: 100%;"
    >
      Tidak ada hasil yang cocok dengan "{{ query }}"
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from "vue";

export interface AutocompleteOption {
  value: string;
  label: string;
  sublabel?: string;
  badge?: string;
}

const props = defineProps<{
  modelValue?: string;
  label?: string;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  hasError?: boolean;
  options: AutocompleteOption[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void;
  (e: "select", item: AutocompleteOption | null): void;
}>();

const rootRef = ref<HTMLElement | null>(null);
const isOpen = ref(false);
const query = ref("");
const highlightedIndex = ref(-1);

const selectedItem = computed(() => {
  return props.options.find((o) => o.value === props.modelValue);
});

const displayLabel = computed(() => {
  if (isOpen.value) {
    return query.value;
  }
  return selectedItem.value ? `${selectedItem.value.label} (${selectedItem.value.value})` : "";
});

const filteredOptions = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) {
    return props.options.slice(0, 30);
  }
  return props.options.filter(
    (o) =>
      o.label.toLowerCase().includes(q) ||
      o.value.toLowerCase().includes(q) ||
      (o.sublabel && o.sublabel.toLowerCase().includes(q))
  ).slice(0, 30);
});

function handleInput(e: Event) {
  query.value = (e.target as HTMLInputElement).value;
  isOpen.value = true;
  highlightedIndex.value = 0;
}

function handleFocus() {
  query.value = selectedItem.value ? selectedItem.value.label : "";
  isOpen.value = true;
  highlightedIndex.value = 0;
}

function selectOption(item: AutocompleteOption) {
  emit("update:modelValue", item.value);
  emit("select", item);
  isOpen.value = false;
  query.value = "";
}

function clearSelection() {
  emit("update:modelValue", "");
  emit("select", null);
  query.value = "";
  isOpen.value = false;
}

function navigateDown() {
  if (!isOpen.value) {
    isOpen.value = true;
    return;
  }
  if (highlightedIndex.value < filteredOptions.value.length - 1) {
    highlightedIndex.value++;
  }
}

function navigateUp() {
  if (highlightedIndex.value > 0) {
    highlightedIndex.value--;
  }
}

function selectHighlighted() {
  if (isOpen.value && highlightedIndex.value >= 0 && filteredOptions.value[highlightedIndex.value]) {
    selectOption(filteredOptions.value[highlightedIndex.value]);
  }
}

function handleClickOutside(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) {
    isOpen.value = false;
    query.value = "";
  }
}

onMounted(() => {
  document.addEventListener("click", handleClickOutside);
});

onBeforeUnmount(() => {
  document.removeEventListener("click", handleClickOutside);
});
</script>

<style scoped>
.cursor-pointer {
  cursor: pointer;
}
.suggestion-item:hover {
  background-color: var(--bs-primary-bg-subtle, #f0f7ff);
}
</style>
