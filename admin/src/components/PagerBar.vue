<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  page: number;
  pageSize: number;
  total: number;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  (event: 'change', page: number): void;
}>();

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / Math.max(1, props.pageSize))));
</script>

<template>
  <footer class="aios-admin-pager">
    <span class="aios-admin-pager-info">
      Halaman {{ page }} dari {{ totalPages }} · {{ total }} baris
    </span>
    <div class="aios-admin-pager-btns">
      <button
        class="aios-admin-button"
        type="button"
        :disabled="disabled || page <= 1"
        aria-label="Halaman sebelumnya"
        @click="emit('change', page - 1)"
      >
        Sebelumnya
      </button>
      <button
        class="aios-admin-button"
        type="button"
        :disabled="disabled || page >= totalPages"
        aria-label="Halaman berikutnya"
        @click="emit('change', page + 1)"
      >
        Berikutnya
      </button>
    </div>
  </footer>
</template>
