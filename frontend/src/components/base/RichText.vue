<script setup lang="ts">
import { computed } from 'vue';
import { renderMarkdown } from '../../utils/markdown';

/**
 * Renderer jawaban agent: markdown penuh (heading, list, tabel, code) yang
 * disanitasi (markdown-it html:false + DOMPurify) lalu dipasang via v-html.
 */
const props = defineProps<{ text: string }>();

const html = computed(() => renderMarkdown(props.text ?? ''));
</script>

<template>
  <p class="rt md" v-html="html" />
</template>
