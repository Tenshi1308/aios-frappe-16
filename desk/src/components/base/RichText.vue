<script setup lang="ts">
import { computed } from 'vue';

/**
 * Renderer teks aman tanpa raw-HTML injection: seluruh teks lolos interpolasi Vue
 * (auto-escape); hanya pasangan **tebal** dipecah menjadi segmen <b>.
 */
const props = defineProps<{ text: string }>();

interface Segment {
  bold: boolean;
  text: string;
}

const segments = computed<Segment[]>(() => {
  const out: Segment[] = [];
  const pattern = /\*\*(.+?)\*\*/g;
  let last = 0;
  let match: RegExpExecArray | null;
  const source = props.text ?? '';
  while ((match = pattern.exec(source)) !== null) {
    if (match.index > last) out.push({ bold: false, text: source.slice(last, match.index) });
    out.push({ bold: true, text: match[1] });
    last = match.index + match[0].length;
  }
  if (last < source.length) out.push({ bold: false, text: source.slice(last) });
  return out.length ? out : [{ bold: false, text: source }];
});
</script>

<template>
  <p class="rt"><template v-for="(seg, i) in segments" :key="i"><b v-if="seg.bold">{{ seg.text }}</b><template v-else>{{ seg.text }}</template></template></p>
</template>
