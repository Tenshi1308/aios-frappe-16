<script setup lang="ts">
withDefaults(defineProps<{ size?: number; accent?: string }>(), { size: 22, accent: 'var(--accent)' });
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true">
    <rect x="2" y="2" width="9" height="9" rx="2.4" :fill="accent" />
    <rect x="13" y="2" width="9" height="9" rx="2.4" fill="currentColor" opacity=".88" />
    <rect x="2" y="13" width="9" height="9" rx="2.4" fill="currentColor" opacity=".62" />
    <rect x="13" y="13" width="9" height="9" rx="4.5" fill="currentColor" opacity=".36" />
  </svg>
</template>
