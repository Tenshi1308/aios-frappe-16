<script setup lang="ts">
import { computed } from 'vue';
import { useChatStore } from '../../stores/chat';
import type { TraceEvent } from '../../types';
import { formatDurationMs, prettyJson, traceStepLabel } from '../../utils/format';

const props = defineProps<{ messageId: string }>();

const chat = useChatStore();
const message = computed(() => chat.findMessage(props.messageId));

function stepDetail(event: TraceEvent): string {
  switch (event.type) {
    case 'trace_delegate_start':
      return event.instruction;
    case 'trace_subagent_prompt':
      return event.task_prompt;
    case 'trace_subagent_tool':
      return `${event.tool}\n${prettyJson(event.args)}`;
    case 'trace_subagent_result':
      return `${event.summary}\n${formatDurationMs(event.duration_ms)}`;
    case 'trace_cross_branch':
      return `payload: ${prettyJson(event.payload)}\nhasil: ${prettyJson(event.result)}`;
    default:
      return '';
  }
}

function isSubagentTool(event: TraceEvent): event is Extract<TraceEvent, { type: 'trace_subagent_tool' }> {
  return event.type === 'trace_subagent_tool';
}
</script>

<template>
  <div class="trace-detail">
    <div v-if="!message" class="td-empty">Langkah tidak ditemukan (trace hanya tersedia untuk sesi aktif).</div>
    <template v-else>
      <div v-if="!message.steps?.length" class="td-empty">Tidak ada langkah yang terekam pada jawaban ini.</div>
      <div v-for="(step, i) in message.steps ?? []" :key="i" class="td-step">
        <div class="td-head">
          <b>{{ i + 1 }}. {{ traceStepLabel(step) }}</b>
          <span v-if="isSubagentTool(step)" class="td-tool">{{ step.tool }}</span>
        </div>
        <pre class="td-body">{{ stepDetail(step) }}</pre>
      </div>
      <div class="td-empty td-usage" v-if="message.tokens || message.durationMs">
        {{ message.tokens ?? 0 }} token · {{ formatDurationMs(message.durationMs) }}
      </div>
    </template>
  </div>
</template>

<style scoped>
.trace-detail {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  overflow: auto;
}
.td-empty {
  color: var(--muted);
  font-size: 12px;
}
.td-usage {
  color: var(--faint);
}
.td-step {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-2);
}
.td-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: var(--fg);
  font-size: 12px;
}
.td-tool {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--faint);
}
.td-body {
  margin: 0;
  overflow: auto;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
