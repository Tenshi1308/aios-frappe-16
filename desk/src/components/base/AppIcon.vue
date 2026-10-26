<script setup lang="ts">
import { computed } from 'vue';

const ICONS: Record<string, string[]> = {
  search: ['M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z', 'M21 21l-4.3-4.3'],
  sparkle: [
    'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z',
    'M19 15l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z',
  ],
  wifi: ['M5 12.55a11 11 0 0 1 14 0', 'M8.5 16.1a6 6 0 0 1 7 0', 'M2 8.82a15 15 0 0 1 20 0', 'M12 20h.01'],
  x: ['M18 6L6 18', 'M6 6l12 12'],
  minus: ['M5 12h14'],
  square: ['M5 5h14v14H5z'],
  restore: ['M8 8h11v11H8z', 'M5 16V5h11'],
  send: ['M22 2L11 13', 'M22 2l-7 20-4-9-9-4z'],
  power: ['M12 2v10', 'M18.4 6.6a9 9 0 1 1-12.8 0'],
  lock: ['M5 11h14v10H5z', 'M8 11V7a4 4 0 0 1 8 0v4'],
  'arrow-right': ['M5 12h14', 'M12 5l7 7-7 7'],
  plus: ['M12 5v14', 'M5 12h14'],
  refresh: ['M21 12a9 9 0 1 1-3-6.7L21 8', 'M21 3v5h-5'],
  file: ['M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z', 'M14 2v6h6'],
  folder: ['M3 6h6l2 2h10v12H3z', 'M3 10h18'],
  desk: ['M3 4h18v12H3z', 'M8 20h8', 'M12 16v4'],
  paperclip: [
    'M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48',
  ],
  history: ['M1 4v6h6', 'M3.51 15a9 9 0 1 0 2.13-9.36L1 10'],
  wrench: [
    'M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z',
  ],
  users: [
    'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2',
    'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8',
    'M23 21v-2a4 4 0 0 0-3-3.87',
    'M16 3.13a4 4 0 0 1 0 7.75',
  ],
  check: ['M20 6L9 17l-5-5'],
};

const props = withDefaults(defineProps<{ name: string; size?: number | string }>(), { size: 18 });
const paths = computed(() => ICONS[props.name] ?? ICONS.file ?? []);
</script>

<template>
  <svg
    :width="props.size"
    :height="props.size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path v-for="(d, i) in paths" :key="i" :d="d" />
  </svg>
</template>
