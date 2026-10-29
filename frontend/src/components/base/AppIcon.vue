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
  tag: [
    'M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8z',
    'M7 7h.01',
  ],
  calc: [
    'M5 3h14v18H5z',
    'M8 7h8',
    'M8.5 12h.01',
    'M12 12h.01',
    'M15.5 12h.01',
    'M8.5 16h.01',
    'M12 16h.01',
    'M15.5 16h.01',
  ],
  cart: ['M6 6h15l-1.5 9h-12z', 'M6 6L5 3H2', 'M9 20h.01', 'M18 20h.01'],
  box: ['M21 8l-9-5-9 5v8l9 5 9-5z', 'M3 8l9 5 9-5', 'M12 13v8'],
  factory: ['M2 20V9l6 4V9l6 4V5h4l2 15z', 'M2 20h20'],
  kanban: ['M3 3h18v18H3z', 'M8 7v7', 'M12 7v4', 'M16 7v9'],
  target: [
    'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z',
    'M12 6a6 6 0 1 0 0 12 6 6 0 0 0 0-12z',
    'M12 10a2 2 0 1 0 0 4 2 2 0 0 0 0-4z',
  ],
  building: ['M4 21V3h10v18', 'M14 9h6v12', 'M8 7h2', 'M8 11h2', 'M8 15h2', 'M2 21h20'],
  headset: ['M3 14v-2a9 9 0 0 1 18 0v2', 'M3 14h4v6H3z', 'M17 14h4v6h-4z'],
  wallet: ['M3 7h18v13H3z', 'M3 7l3-4h12l3 4', 'M16 13h2'],
  shield: ['M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z', 'M9 12l2 2 4-4'],
  chart: ['M3 3v18h18', 'M7 15l4-4 3 3 5-6'],
  gear: [
    'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
    'M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z',
  ],
  'user-round-check': ['M2 21a8 8 0 0 1 13.292-6', 'm16 19 2 2 4-4'],
};

const ICON_CIRCLES: Record<string, Array<{ cx: number; cy: number; r: number }>> = {
  'user-round-check': [{ cx: 10, cy: 8, r: 5 }],
};

const props = withDefaults(defineProps<{ name: string; size?: number | string }>(), { size: 18 });
const paths = computed(() => ICONS[props.name] ?? ICONS.file ?? []);
const circles = computed(() => ICON_CIRCLES[props.name] ?? []);
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
    <circle v-for="(c, i) in circles" :key="'c' + i" :cx="c.cx" :cy="c.cy" :r="c.r" />
  </svg>
</template>
