<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { TraceEvent } from '../../types';
import { formatDurationMs, prettyJson, traceStepLabel } from '../../utils/format';

const props = defineProps<{ step: TraceEvent; defaultOpen?: boolean }>();

const open = ref(!!props.defaultOpen);

// Saat live, langkah terakhir yang baru terekam auto-expand.
watch(
  () => props.defaultOpen,
  (value) => {
    if (value) open.value = true;
  },
);

interface TraceSection {
  label: string;
  text: string;
}

const sections = computed<TraceSection[]>(() => {
  const step = props.step;
  switch (step.type) {
    case 'trace_delegate_start':
      return [{ label: 'Instruksi', text: step.instruction }];
    case 'trace_subagent_prompt':
      return [
        { label: 'Peran penerima', text: step.agent },
        { label: 'Tugas', text: step.task_prompt },
      ];
    case 'trace_subagent_tool': {
      const parts = [{ label: 'Argumen', text: prettyJson(step.args) }];
      return parts;
    }
    case 'trace_subagent_result':
      return [
        { label: 'Ringkasan', text: step.summary },
        { label: 'Status', text: step.status },
        { label: 'Durasi', text: formatDurationMs(step.duration_ms) },
      ];
    case 'trace_cross_branch':
      return [
        { label: 'Payload', text: prettyJson(step.payload) },
        { label: 'Hasil', text: prettyJson(step.result) },
      ];
    default:
      return [];
  }
});

const meta = computed(() => {
  const step = props.step;
  if (step.type === 'trace_subagent_result') return formatDurationMs(step.duration_ms);
  return '';
});
</script>

<template>
  <div class="as-item" :class="{ open }">
    <button class="as-head" @click="open = !open">
      <span class="as-label">{{ traceStepLabel(step) }}</span>
      <span v-if="meta" class="as-meta">{{ meta }}</span>
      <span class="as-chev">{{ open ? '−' : '+' }}</span>
    </button>
    <div v-if="open" class="as-body">
      <div v-for="(section, i) in sections" :key="i" class="as-section">
        <span class="as-section-label">{{ section.label }}</span>
        <pre>{{ section.text }}</pre>
      </div>
      <div v-if="step.type === 'trace_subagent_result'" class="as-status" :data-status="step.status">
        {{ step.status }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.as-item {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface);
  overflow: hidden;
}
.as-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 9px;
  background: transparent;
  border: none;
  color: var(--fg);
  font: inherit;
  font-size: 11px;
  text-align: left;
  cursor: pointer;
}
.as-head:hover {
  background: var(--hover);
}
.as-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.as-meta {
  color: var(--faint);
}
.as-chev {
  color: var(--faint);
}
.as-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px 9px;
  border-top: 1px solid var(--line);
  background: var(--surface-2);
}
.as-section {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.as-section-label {
  color: var(--muted);
  font-size: 10px;
  text-transform: uppercase;
}
.as-section pre {
  margin: 0;
  overflow: auto;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--fg);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 180px;
}
.as-status {
  align-self: flex-start;
  padding: 1px 8px;
  border-radius: 8px;
  font-size: 10px;
  color: var(--ok);
  background: var(--ok-soft);
}
.as-status[data-status='failed'] {
  color: var(--bad);
  background: var(--bad-soft);
}
.as-status[data-status='partial'] {
  color: var(--warn);
  background: var(--warn-soft);
}
</style>
