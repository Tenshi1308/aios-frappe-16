<script setup lang="ts">
import { useUiStore } from '../../stores/ui';

const ui = useUiStore();
</script>

<template>
  <TransitionGroup name="t-toast" tag="div" class="toasts">
    <div v-for="t in ui.toasts" :key="t.id" class="toast">{{ t.text }}</div>
  </TransitionGroup>
</template>
