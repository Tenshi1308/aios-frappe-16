<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { TraceEvent } from '../../types';
import { prettyJson, traceStepIcon, traceStepLabel, traceStepSubtext } from '../../utils/format';
import AppIcon from '../base/AppIcon.vue';

const props = defineProps<{
  step: TraceEvent;
  defaultOpen?: boolean;
  /** Item terakhir yang masih berjalan (live) — durasi dihitung klien. */
  running?: boolean;
  /** Teks durasi item (dihitung parent dari timing klien). */
  durationText?: string;
}>();

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
    case 'trace_subagent_tool':
      return [{ label: 'Argumen', text: prettyJson(step.args) }];
    case 'trace_subagent_result':
      return [
        { label: 'Ringkasan', text: step.summary },
        { label: 'Status', text: step.status },
        { label: 'Durasi (server)', text: formatServerDuration(step.duration_ms) },
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

function formatServerDuration(ms: number): string {
  if (!ms && ms !== 0) return '—';
  return `${(ms / 1000).toFixed(1)} dtk`;
}

const subtext = computed(() => traceStepSubtext(props.step));
</script>

<template>
  <div class="as-item" :class="{ open, running: props.running }">
    <button class="as-head" @click="open = !open">
      <span class="as-icon"><AppIcon :name="traceStepIcon(props.step)" :size="13" /></span>
      <span class="as-label">{{ traceStepLabel(props.step) }}</span>
      <span v-if="props.running" class="as-running" aria-hidden="true"><i /><i /><i /></span>
      <span v-else-if="props.durationText" class="as-meta">{{ props.durationText }}</span>
      <span class="as-chev">{{ open ? '−' : '+' }}</span>
    </button>
    <div v-if="open" class="as-sub" >{{ subtext }}</div>
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
  border-radius: var(--radius-6);
  background: var(--surface);
  overflow: hidden;
}
.as-item.running {
  border-color: var(--ok);
}
.as-head {
  display: flex;
  align-items: center;
  gap: var(--space-7);
  padding: var(--space-5) var(--space-9);
  background: transparent;
  border: none;
  color: var(--fg);
  font: inherit;
  font-size: var(--fs-11);
  text-align: left;
  cursor: pointer;
}
.as-head:hover {
  background: var(--hover);
}
.as-icon {
  display: inline-flex;
  color: var(--muted);
}
.as-item.running .as-icon {
  color: var(--ok);
}
.as-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.as-running {
  display: inline-flex;
  gap: var(--space-2);
}
.as-running i {
  width: 4px;
  height: 4px;
  border-radius: var(--radius-circle);
  background: var(--ok);
  animation: as-blink var(--dur-100) ease-in-out infinite;
}
.as-running i:nth-child(2) {
  animation-delay: var(--dur-20);
}
.as-running i:nth-child(3) {
  animation-delay: var(--dur-40);
}
@keyframes as-blink {
  0%, 100% { opacity: 0.25; }
  50% { opacity: 1; }
}
.as-meta {
  color: var(--faint);
  font-variant-numeric: tabular-nums;
}
.as-chev {
  color: var(--faint);
}
.as-sub {
  padding: 0 var(--space-9) var(--space-5) var(--space-29);
  color: var(--muted);
  font-size: var(--fs-11);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.as-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  padding: var(--space-6) var(--space-9) var(--space-8) var(--space-29);
  border-top: 1px solid var(--line);
  background: var(--surface-2);
}
.as-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.as-section-label {
  color: var(--muted);
  font-size: var(--fs-10);
  text-transform: uppercase;
}
.as-section pre {
  margin: 0;
  overflow: auto;
  font-family: var(--font-mono);
  font-size: var(--fs-11);
  color: var(--fg);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 180px;
}
.as-status {
  align-self: flex-start;
  padding: var(--space-1) var(--space-8);
  border-radius: var(--radius-8);
  font-size: var(--fs-10);
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
