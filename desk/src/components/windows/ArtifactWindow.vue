<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useChatStore } from '../../stores/chat';
import type { FileArtifact } from '../../types';
import { formatBytes } from '../../utils/format';
import AppIcon from '../base/AppIcon.vue';

const props = defineProps<{ fileUrl: string }>();

const chat = useChatStore();
const artifact = computed<FileArtifact | null>(() => {
  const a = chat.artifactWindows[props.fileUrl];
  return a && a.type === 'FILE' ? a : null;
});

const PREVIEW_TEXT_FORMATS = new Set(['csv', 'md']);
const PREVIEW_MAX_BYTES = 2 * 1024 * 1024;

const loading = ref(false);
const error = ref('');
const textContent = ref('');

const mode = computed<'text' | 'pdf' | 'meta' | 'too-large' | 'unknown'>(() => {
  const a = artifact.value;
  if (!a) return 'unknown';
  if (a.size > PREVIEW_MAX_BYTES) return 'too-large';
  if (PREVIEW_TEXT_FORMATS.has(a.format)) return 'text';
  if (a.format === 'pdf') return 'pdf';
  return 'meta';
});

async function loadText() {
  if (mode.value !== 'text') return;
  loading.value = true;
  error.value = '';
  try {
    const res = await fetch(props.fileUrl, { credentials: 'same-origin' });
    if (!res.ok) {
      error.value = 'Pratinjau tidak dapat dimuat.';
      return;
    }
    textContent.value = await res.text();
  } catch {
    error.value = 'Pratinjau tidak dapat dimuat.';
  } finally {
    loading.value = false;
  }
}

onMounted(loadText);
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

      <pre v-else-if="mode === 'text'" class="aw-text">{{ textContent }}</pre>
      <iframe
        v-else-if="mode === 'pdf'"
        :src="props.fileUrl"
        :title="artifact.file_name"
        class="aw-frame"
      />
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
  gap: 8px;
  height: 100%;
  overflow: auto;
}
.aw-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-2);
  color: var(--fg);
  font-size: 12px;
}
.aw-meta b {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.aw-chip {
  padding: 1px 7px;
  border-radius: 8px;
  background: var(--accent-soft);
  color: var(--accent-strong);
  font-size: 10px;
}
.aw-size {
  color: var(--muted);
}
.aw-note {
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-2);
  color: var(--muted);
  font-size: 12px;
}
.aw-error {
  color: var(--bad);
}
.aw-text {
  flex: 1;
  margin: 0;
  padding: 10px;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-2);
  color: var(--fg);
  font-family: var(--font-mono);
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-word;
}
.aw-frame {
  flex: 1;
  width: 100%;
  min-height: 300px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface);
}
.aw-download {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-2);
  color: var(--fg);
  font-size: 12px;
  text-decoration: none;
}
.aw-download:hover {
  background: var(--hover);
}
</style>
