<template>
  <input
    :value="display"
    type="text"
    inputmode="numeric"
    autocomplete="off"
    :placeholder="placeholder"
    :aria-label="ariaLabel"
    :disabled="disabled"
    @input="onInput"
    @blur="onBlur"
  />
</template>

<script setup lang="ts">
/**
 * Input nominal Rupiah dengan pemisah ribuan (keputusan pemilik 11 Nov 2026: "tampilkan thousand separator supaya user
 * tidak bingung"). Tampil "1.100.000", v-model tetap angka (null = kosong). Hanya bilangan bulat ≥ 0.
 *   <CurrencyInput v-model="amount" class="form-control form-control-sm text-end" placeholder="-" />
 */
import { ref, watch } from "vue";

const props = defineProps<{ modelValue: number | null | undefined; placeholder?: string; ariaLabel?: string; disabled?: boolean }>();
const emit = defineEmits<{ (e: "update:modelValue", v: number | null): void }>();

const fmt = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });
const format = (v: number | null | undefined) => (v === null || v === undefined || Number.isNaN(v) ? "" : fmt.format(v));
const display = ref(format(props.modelValue));

watch(
  () => props.modelValue,
  (v) => {
    if (parse(display.value) !== (v ?? null)) display.value = format(v);
  },
);

function parse(text: string): number | null {
  const digits = text.replace(/\D/g, "");
  return digits ? Number(digits) : null;
}

function onInput(e: Event) {
  const el = e.target as HTMLInputElement;
  const digitsBeforeCaret = el.value.slice(0, el.selectionStart ?? el.value.length).replace(/\D/g, "").length;
  const value = parse(el.value);
  display.value = format(value);
  el.value = display.value;
  // pertahankan posisi kursor setelah titik pemisah disisipkan
  let pos = 0;
  let seen = 0;
  while (pos < el.value.length && seen < digitsBeforeCaret) {
    if (/\d/.test(el.value[pos])) seen++;
    pos++;
  }
  el.setSelectionRange(pos, pos);
  emit("update:modelValue", value);
}

function onBlur() {
  display.value = format(props.modelValue);
}
</script>
