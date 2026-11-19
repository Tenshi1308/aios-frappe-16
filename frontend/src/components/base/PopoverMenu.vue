<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue';

const props = defineProps<{
  open: boolean;
  menuClass?: string;
  ariaLabel?: string;
}>();

const emit = defineEmits<{
  close: [];
}>();

function onKeydown(e: KeyboardEvent) {
  if (props.open && e.key === 'Escape') {
    e.stopPropagation();
    emit('close');
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown);
});

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown);
});
</script>

<template>
  <div
    v-if="open"
    class="ap-popover-menu"
    :class="menuClass"
    role="menu"
    :aria-label="ariaLabel"
    @click.stop
  >
    <slot />
  </div>
</template>
