<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import Papa from 'papaparse';
import * as XLSX from 'xlsx';
import { useChatStore } from '../../stores/chat';
import type { FileArtifact } from '../../types';
import { formatBytes } from '../../utils/format';
import { renderMarkdown } from '../../utils/markdown';
import AppIcon from '../base/AppIcon.vue';

const props = defineProps<{ artifactKey?: string; fileUrl: string }>();

const chat = useChatStore();
const artifact = computed<FileArtifact | null>(() => {
  const a = chat.artifactWindows[props.artifactKey || props.fileUrl];
  return a && a.type === 'FILE' ? a : null;
});

const PREVIEW_MAX_BYTES = 2 * 1024 * 1024;

const loading = ref(false);
const error = ref('');
const csvRows = ref<string[][]>([]);
const mdHtml = ref('');
const sheetRows = ref<string[][]>([]);

const mode = computed<'csv' | 'md' | 'pdf' | 'xlsx' | 'meta' | 'too-large' | 'unknown'>(() => {
  const a = artifact.value;
  if (!a) return 'unknown';
  if (a.size > PREVIEW_MAX_BYTES) return 'too-large';
  if (a.format === 'csv') return 'csv';
  if (a.format === 'md') return 'md';
  if (a.format === 'pdf') return 'pdf';
  if (a.format === 'xlsx') return 'xlsx';
  return 'meta';
});

async function loadPreview() {
  const kind = mode.value;
  if (kind !== 'csv' && kind !== 'md' && kind !== 'xlsx') return;
  loading.value = true;
  error.value = '';
  try {
    const res = await fetch(props.fileUrl, { credentials: 'same-origin' });
    if (!res.ok) {
      error.value = 'Pratinjau tidak dapat dimuat.';
      return;
    }
    if (kind === 'csv') {
      const raw = await res.text();
      const parsed = Papa.parse<string[]>(raw, { skipEmptyLines: true });
      csvRows.value = parsed.data;
    } else if (kind === 'md') {
      const raw = await res.text();
      mdHtml.value = renderMarkdown(raw);
    } else {
      const buffer = await res.arrayBuffer();
      const workbook = XLSX.read(buffer, { type: 'array' });
      const sheet = workbook.Sheets[workbook.SheetNames[0]];
      sheetRows.value = sheet ? (XLSX.utils.sheet_to_json(sheet, { header: 1, raw: false }) as string[][]) : [];
    }
  } catch {
    error.value = 'Pratinjau tidak dapat dimuat.';
  } finally {
    loading.value = false;
  }
}

onMounted(loadPreview);
</script>

<template>
  <div class="artifact-win">
    <div v-if="artifact" class="aw-meta">
      <AppIcon name="file" :size="14" />
      <span><b>{{ artifact.file_name }}</b></span>
      <span class="aw-chip">{{ artifact.format.toUpperCase() }}</span>
      <span class="aw-size">{{ formatBytes(artifact.size) }}</span>
    </div>

    <div v-else class="aw-note">Artefak tidak ditemukan.</div>

    <template v-if="artifact">
      <div v-if="loading" class="aw-note">Memuat pratinjau…</div>
      <div v-else-if="error" class="aw-note aw-error">{{ error }}</div>
      <div v-else-if="mode === 'too-large'" class="aw-note">
        Terlalu besar untuk pratinjau — silakan unduh.
      </div>

      <div v-else-if="mode === 'csv' && csvRows.length" class="aw-table-wrap">
        <table class="aw-table">
          <thead>
            <tr><th v-for="(h, i) in csvRows[0]" :key="i">{{ h }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="(row, ri) in csvRows.slice(1)" :key="ri">
              <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else-if="mode === 'md'" class="aw-md md-body" v-html="mdHtml" />
      <iframe
        v-else-if="mode === 'pdf'"
        :src="props.fileUrl"
        :title="artifact.file_name"
        class="aw-frame"
      />
      <div v-else-if="mode === 'xlsx' && sheetRows.length" class="aw-table-wrap">
        <table class="aw-table">
          <tbody>
            <tr v-for="(row, ri) in sheetRows" :key="ri">
              <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="aw-note">Pratinjau untuk format ini belum tersedia — silakan unduh.</div>

      <a class="btn ghost aw-download" :href="props.fileUrl" :download="artifact.file_name">
        Unduh {{ artifact.file_name }}
      </a>
    </template>
  </div>
</template>

<style scoped>
.artifact-win {
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
  height: 100%;
  overflow: auto;
}
.aw-meta {
  display: flex;
  align-items: center;
  gap: var(--space-8);
  padding: var(--space-7) var(--space-10);
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface-2);
  color: var(--fg);
  font-size: var(--fs-12);
}
.aw-meta b {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.aw-chip {
  padding: var(--space-1) var(--space-7);
  border-radius: var(--radius-8);
  background: var(--accent-soft);
  color: var(--accent-strong);
  font-size: var(--fs-10);
}
.aw-size {
  color: var(--muted);
}
.aw-note {
  padding: var(--space-8) var(--space-10);
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface-2);
  color: var(--muted);
  font-size: var(--fs-12);
}
.aw-error {
  color: var(--bad);
}
.aw-text {
  flex: 1;
  margin: 0;
  padding: var(--space-10);
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface-2);
  color: var(--fg);
  font-family: var(--font-mono);
  font-size: var(--fs-11);
  white-space: pre-wrap;
  word-break: break-word;
}
.aw-frame {
  flex: 1;
  width: 100%;
  min-height: 300px;
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface);
}
.aw-download {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-6);
  padding: var(--space-6) var(--space-12);
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface-2);
  color: var(--fg);
  font-size: var(--fs-12);
  text-decoration: none;
}
.aw-download:hover {
  background: var(--hover);
}
.aw-table-wrap {
  flex: 1;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface-2);
}
.aw-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-11);
  color: var(--fg);
}
.aw-table th,
.aw-table td {
  padding: var(--space-4) var(--space-8);
  border-bottom: 1px solid var(--line);
  text-align: left;
  white-space: nowrap;
}
.aw-table th {
  position: sticky;
  top: 0;
  background: var(--surface);
  color: var(--muted);
  font-weight: var(--fw-600);
}
.aw-md {
  flex: 1;
  overflow: auto;
  padding: var(--space-10);
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface-2);
  color: var(--fg);
  font-size: var(--fs-12);
}
</style>
