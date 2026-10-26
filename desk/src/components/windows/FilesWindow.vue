<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useBranchesStore } from '../../stores/branches';
import { useChatStore } from '../../stores/chat';
import type { FileEntry } from '../../types';
import { formatBytes } from '../../utils/format';
import AppIcon from '../base/AppIcon.vue';

interface ConversationFolder {
  id: string;
  title: string;
  files: FileEntry[];
}

interface BranchFolder {
  key: string;
  conversations: ConversationFolder[];
}

const chat = useChatStore();
const branches = useBranchesStore();
const selectedConversationId = ref('');
const expandedBranches = ref(new Set<string>());

const branchFolders = computed<BranchFolder[]>(() => {
  const grouped = new Map<string, Map<string, ConversationFolder>>();
  for (const file of chat.myFiles) {
    const branchKey = file.branch || '';
    let conversations = grouped.get(branchKey);
    if (!conversations) {
      conversations = new Map();
      grouped.set(branchKey, conversations);
    }
    let conversation = conversations.get(file.conversation_id);
    if (!conversation) {
      conversation = {
        id: file.conversation_id,
        title: file.conversation_title || file.conversation_id,
        files: [],
      };
      conversations.set(file.conversation_id, conversation);
    }
    conversation.files.push(file);
  }
  return [...grouped].map(([key, conversations]) => ({ key, conversations: [...conversations.values()] }));
});

const selectedFiles = computed(
  () => chat.myFiles.filter((file) => file.conversation_id === selectedConversationId.value),
);
const selectedBranchKey = computed(() => selectedFiles.value[0]?.branch ?? '');
const selectedBranchName = computed(
  () => branches.byKey(selectedBranchKey.value)?.name ?? selectedBranchKey.value,
);
const selectedConversationTitle = computed(() => selectedFiles.value[0]?.conversation_title ?? '');

function toggleBranch(key: string) {
  if (expandedBranches.value.has(key)) expandedBranches.value.delete(key);
  else expandedBranches.value.add(key);
}

function selectConversation(conversation: ConversationFolder, branchKey: string) {
  selectedConversationId.value = conversation.id;
  expandedBranches.value.add(branchKey);
}

async function refreshFiles() {
  await chat.loadMyFiles();
  if (!chat.myFiles.some((file) => file.conversation_id === selectedConversationId.value)) {
    selectedConversationId.value = chat.myFiles[0]?.conversation_id ?? '';
  }
  if (selectedBranchKey.value) expandedBranches.value.add(selectedBranchKey.value);
}

function formatDate(value: string) {
  if (!value) return '';
  const date = new Date(value.replace(' ', 'T'));
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('id-ID', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function openFile(file: FileEntry) {
  chat.openArtifact({
    type: 'FILE',
    file_id: file.file_id,
    file_name: file.file_name,
    file_url: file.file_url,
    format: file.format,
    size: file.file_size,
    conversation_id: file.conversation_id,
  });
}

onMounted(() => {
  void branches.load();
  void refreshFiles();
});
</script>

<template>
  <div class="files-window">
    <header class="files-toolbar">
      <nav class="files-breadcrumb" aria-label="Lokasi berkas">
        <span>Files</span>
        <template v-if="selectedFiles.length">
          <span aria-hidden="true">›</span>
          <span>{{ selectedBranchName }}</span>
          <span aria-hidden="true">›</span>
          <span class="files-crumb-current">{{ selectedConversationTitle }}</span>
        </template>
      </nav>
      <button class="files-refresh" type="button" :disabled="chat.myFilesLoading" @click="refreshFiles">
        <AppIcon name="refresh" :size="14" />
        Refresh
      </button>
    </header>

    <div class="files-layout">
      <aside class="files-sidebar" aria-label="Folder percakapan">
        <div class="files-sidebar-title">Folder</div>
        <div v-if="chat.myFilesLoading && !branchFolders.length" class="files-sidebar-note">Memuat file…</div>
        <div v-else-if="!branchFolders.length" class="files-sidebar-note">Belum ada file</div>
        <template v-for="branchFolder in branchFolders" :key="branchFolder.key">
          <button
            class="files-tree-branch"
            type="button"
            :aria-expanded="expandedBranches.has(branchFolder.key)"
            @click="toggleBranch(branchFolder.key)"
          >
            <AppIcon name="folder" :size="16" />
            <span>{{ branches.byKey(branchFolder.key)?.name ?? branchFolder.key }}</span>
          </button>
          <div v-if="expandedBranches.has(branchFolder.key)" class="files-tree-conversations">
            <button
              v-for="conversation in branchFolder.conversations"
              :key="conversation.id"
              class="files-tree-conversation"
              :class="{ selected: conversation.id === selectedConversationId }"
              type="button"
              @click="selectConversation(conversation, branchFolder.key)"
            >
              <AppIcon name="folder" :size="14" />
              <span>{{ conversation.title }}</span>
            </button>
          </div>
        </template>
      </aside>

      <section class="files-content" aria-label="Isi percakapan">
        <div v-if="chat.myFilesLoading && !chat.myFiles.length" class="files-empty">Memuat file…</div>
        <div v-else-if="chat.myFilesError" class="files-empty files-error">{{ chat.myFilesError }}</div>
        <div v-else-if="!selectedFiles.length" class="files-empty">Belum ada file</div>
        <template v-else>
          <div class="files-list-head" aria-hidden="true">
            <span>Nama</span>
            <span>Format</span>
            <span>Ukuran</span>
            <span>Tanggal</span>
          </div>
          <button
            v-for="file in selectedFiles"
            :key="file.file_id || file.file_url"
            class="files-row"
            type="button"
            :aria-label="`Buka ${file.file_name}`"
            @click="openFile(file)"
          >
            <span class="files-name"><AppIcon name="file" :size="15" />{{ file.file_name }}</span>
            <span class="files-format">{{ file.format.toUpperCase() }}</span>
            <span>{{ formatBytes(file.file_size) }}</span>
            <span>{{ formatDate(file.creation) }}</span>
          </button>
        </template>
      </section>
    </div>
  </div>
</template>

<style scoped>
.files-window {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 280px;
  color: var(--fg);
}
.files-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 32px;
}
.files-breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: var(--muted);
  font-size: 12px;
}
.files-breadcrumb span:first-child {
  color: var(--fg);
  font-weight: 700;
}
.files-crumb-current {
  overflow: hidden;
  color: var(--fg);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.files-refresh,
.files-tree-branch,
.files-tree-conversation,
.files-row {
  border: 1px solid transparent;
  color: var(--fg);
  font: inherit;
  cursor: pointer;
}
.files-refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 9px;
  border-color: var(--line);
  border-radius: 6px;
  background: var(--surface-2);
  font-size: 11px;
}
.files-refresh:hover:not(:disabled),
.files-row:hover {
  background: var(--hover);
}
.files-refresh:disabled {
  cursor: wait;
  opacity: 0.65;
}
.files-layout {
  display: grid;
  grid-template-columns: minmax(150px, 220px) minmax(0, 1fr);
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
}
.files-sidebar {
  overflow: auto;
  padding: 8px;
  border-right: 1px solid var(--line);
  background: var(--surface-2);
}
.files-sidebar-title {
  padding: 5px 7px 8px;
  color: var(--muted);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
}
.files-sidebar-note,
.files-empty {
  padding: 18px 12px;
  color: var(--muted);
  font-size: 12px;
}
.files-tree-branch,
.files-tree-conversation {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 7px;
  padding: 7px;
  border-radius: 6px;
  background: transparent;
  text-align: left;
  font-size: 11px;
}
.files-tree-branch span,
.files-tree-conversation span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.files-tree-branch:hover,
.files-tree-conversation:hover {
  background: var(--hover);
}
.files-tree-conversations {
  padding-left: 12px;
}
.files-tree-conversation.selected {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.files-content {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: auto;
}
.files-empty {
  margin: auto;
  text-align: center;
}
.files-error {
  color: var(--bad);
}
.files-list-head,
.files-row {
  display: grid;
  grid-template-columns: minmax(130px, 1fr) 58px 72px minmax(112px, 0.7fr);
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  text-align: left;
}
.files-list-head {
  position: sticky;
  top: 0;
  border-bottom: 1px solid var(--line);
  background: var(--surface-2);
  color: var(--muted);
  font-size: 10px;
  font-weight: 700;
}
.files-row {
  width: 100%;
  border-bottom: 1px solid var(--line);
  background: transparent;
  font-size: 11px;
}
.files-row > span:not(.files-name) {
  overflow: hidden;
  color: var(--muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.files-name {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 7px;
}
.files-name :deep(svg) {
  flex: 0 0 auto;
  color: var(--accent-strong);
}
.files-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 620px) {
  .files-layout {
    grid-template-columns: minmax(110px, 38%) minmax(0, 1fr);
  }
  .files-list-head,
  .files-row {
    grid-template-columns: minmax(90px, 1fr) 46px 58px;
  }
  .files-list-head span:last-child,
  .files-row > span:last-child {
    display: none;
  }
}
</style>
