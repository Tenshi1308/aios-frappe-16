<script setup lang="ts">
import AppIcon from './AppIcon.vue';

withDefaults(
  defineProps<{
    message: string;
    loading?: boolean;
    retryLabel?: string;
    containerClass?: string;
    buttonClass?: string;
    iconOnly?: boolean;
    showIcon?: boolean;
    iconSize?: number;
  }>(),
  {
    loading: false,
    retryLabel: 'Coba lagi',
    containerClass: '',
    buttonClass: 'btn ghost',
    iconOnly: false,
    showIcon: false,
    iconSize: 14,
  },
);

defineEmits<{
  retry: [];
}>();
</script>

<template>
  <div :class="containerClass" role="alert">
    <span>{{ message }}</span>
    <button
      type="button"
      :class="buttonClass"
      :disabled="loading"
      :aria-label="iconOnly ? retryLabel : undefined"
      :title="iconOnly ? retryLabel : undefined"
      @click="$emit('retry')"
    >
      <AppIcon v-if="iconOnly || showIcon" name="refresh" :size="iconSize" />
      <span v-if="!iconOnly">{{ retryLabel }}</span>
    </button>
  </div>
</template>
