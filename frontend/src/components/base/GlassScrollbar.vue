<script setup lang="ts">
// Global custom scrollbar component (Apple glass style, 5px, no arrow buttons).
// Mounted once in App.vue; .tb-center and .ap-tabs retain scrollbar-width: none via higher specificity.
</script>

<template>
  <span class="glass-scrollbar-anchor" aria-hidden="true" hidden />
</template>

<style>
* {
  scrollbar-width: thin;
  scrollbar-color: var(--glass-line) transparent;
}
*::-webkit-scrollbar {
  width: 5px;
  height: 5px;
}
*::-webkit-scrollbar-button {
  display: none;
  width: 0;
  height: 0;
}
*::-webkit-scrollbar-track {
  background: transparent;
}
*::-webkit-scrollbar-thumb {
  background: var(--glass);
  border: 1px solid var(--glass-line);
  border-radius: var(--radius-pill);
  backdrop-filter: var(--glass-blur-sm);
  -webkit-backdrop-filter: var(--glass-blur-sm);
}
*::-webkit-scrollbar-thumb:hover {
  background: var(--faint);
}
</style>
