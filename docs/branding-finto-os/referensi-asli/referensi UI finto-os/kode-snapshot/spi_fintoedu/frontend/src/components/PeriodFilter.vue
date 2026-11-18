<template>
  <div class="d-inline-flex flex-wrap gap-2 align-items-center" role="group" aria-label="Filter periode">
    <select v-model.number="yearModel" class="form-select form-select-sm" style="width: 120px" aria-label="Tahun">
      <option v-if="allowAll" :value="0">Semua tahun</option>
      <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
    </select>
    <select v-model.number="monthModel" class="form-select form-select-sm" style="width: 150px" aria-label="Bulan" :disabled="!yearModel">
      <option :value="0">Semua bulan</option>
      <option v-for="(m, i) in MONTHS" :key="m" :value="i + 1">{{ m }}</option>
    </select>
  </div>
</template>

<script setup lang="ts">
/**
 * Filter periode Tahun + Bulan (keputusan pemilik 11 Nov 2026: daftar/laporan berperiode punya filter tahun & bulan
 * dengan nilai default — pakai `defaultPeriod()`; pengecualian: Matriks SPP 12 bulan hanya tahun).
 *   <PeriodFilter v-model:year="year" v-model:month="month" @change="load" />
 * month 0 = semua bulan; year 0 = semua tahun (hanya bila allow-all).
 */
import { computed } from "vue";

const MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"];

const props = withDefaults(defineProps<{ year: number; month: number; allowAll?: boolean; span?: number }>(), {
  allowAll: true,
  span: 6,
});
const emit = defineEmits<{ (e: "update:year", v: number): void; (e: "update:month", v: number): void; (e: "change"): void }>();

const now = new Date();
const years = computed(() => Array.from({ length: props.span }, (_, i) => now.getFullYear() + 1 - i));

const yearModel = computed({
  get: () => props.year,
  set: (v: number) => {
    emit("update:year", v);
    if (!v) emit("update:month", 0);
    emit("change");
  },
});
const monthModel = computed({
  get: () => props.month,
  set: (v: number) => {
    emit("update:month", v);
    emit("change");
  },
});
</script>
