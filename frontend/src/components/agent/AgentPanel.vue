<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { useBranchesStore } from '../../stores/branches';
import { useChatStore } from '../../stores/chat';
import { useModulesStore } from '../../stores/modules';
import { useSessionStore } from '../../stores/session';
import {
  AGENT_PANEL_MAX_W,
  AGENT_PANEL_MIN_W,
  useUiStore,
} from '../../stores/ui';
import { MAX_UPLOAD_BYTES, UPLOAD_EXTENSIONS } from '../../api/chat';
import { useWindowManager } from '../../composables/useWindowManager';
import { formatDurationMs, formatTokenCount } from '../../utils/format';
import type { ArtifactEvent, ChatMessage, ConversationItem, FileEntry } from '../../types';
import AgentStep from './AgentStep.vue';
import AgentAvatar from '../base/AgentAvatar.vue';
import AppIcon from '../base/AppIcon.vue';
import RichText from '../base/RichText.vue';

interface SpeechRecognitionAlternativeLike {
  transcript: string;
}
interface SpeechRecognitionResultLike {
  isFinal: boolean;
  0: SpeechRecognitionAlternativeLike;
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
}
interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((ev: SpeechRecognitionEventLike) => void) | null;
  onerror: ((ev: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

const WIDE_SIDEBAR_BREAKPOINT = 640;

const session = useSessionStore();
const branches = useBranchesStore();
const chat = useChatStore();
const modules = useModulesStore();
const ui = useUiStore();

const draft = ref('');
const inputEl = ref<HTMLTextAreaElement | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const threadEl = ref<HTMLElement | null>(null);
const panelEl = ref<HTMLElement | null>(null);
const uploading = ref(false);
const traceOpenId = ref<string | null>(null);
const contextOpen = ref(false);
const headerMenuOpen = ref(false);

// Menu tiga titik riwayat & aksi per percakapan
const historyMenuOpen = ref(false);
const historyListCollapsed = ref(false);
const activeConvMenuId = ref<string | null>(null);
const renamingConvId = ref<string | null>(null);
const renameDraft = ref('');
const confirmingDeleteId = ref<string | null>(null);
const convActionBusy = ref(false);

// Dikte suara (Web Speech API)
const listening = ref(false);
let recognition: SpeechRecognitionLike | null = null;
const SpeechRecognitionCtor =
  typeof window !== 'undefined'
    ? ((
        window as unknown as {
          SpeechRecognition?: new () => SpeechRecognitionLike;
          webkitSpeechRecognition?: new () => SpeechRecognitionLike;
        }
      ).SpeechRecognition ??
      (
        window as unknown as {
          webkitSpeechRecognition?: new () => SpeechRecognitionLike;
        }
      ).webkitSpeechRecognition)
    : undefined;
const voiceSupported = Boolean(SpeechRecognitionCtor);

void branches.load();
void chat.loadPendingDrafts();
void modules.loadConversationSettings();

const branch = computed(() => branches.selected);
const branchKey = computed(() => branch.value?.key ?? '');
const messages = computed(() => chat.threadFor(branchKey.value));
const referral = computed(() => chat.referralFor(branchKey.value));
const streaming = computed(() => chat.isStreaming(branchKey.value));
const files = computed(() => chat.files(branchKey.value));
const uploadPercent = computed(() => chat.uploadProgress[branchKey.value]);
const suggestions = computed(() => branches.suggestions(branchKey.value));
const conversations = computed(() => chat.conversations[branchKey.value] ?? []);
const historyError = computed(() => chat.historyError[branchKey.value] ?? '');
const isArchivedView = computed(() => !!chat.historyArchived[branchKey.value]);
const historySort = computed(() => chat.historySort[branchKey.value] ?? 'desc');
const legacyFiles = computed(() => {
  const conversationId = chat.currentConversation[branchKey.value];
  return conversationId ? chat.legacyFiles[conversationId] ?? [] : [];
});

const isWideMode = computed(
  () => ui.agentFullscreen || ui.agentWidth >= WIDE_SIDEBAR_BREAKPOINT,
);
const sidebarVisible = computed(() =>
  isWideMode.value ? ui.agentSidebarOpen : !!chat.historyOpen[branchKey.value],
);
const panelStyle = computed(() => {
  if (ui.agentFullscreen) return {};
  return { width: `min(${ui.agentWidth}px, calc(100% - 20px))` };
});

watch(
  () => [isWideMode.value, ui.agentSidebarOpen, branchKey.value] as const,
  ([wide, open, key]) => {
    if (wide && open && key && !chat.conversations[key] && !chat.historyLoading[key]) {
      void chat.loadConversations(key);
    }
  },
  { immediate: true },
);

const firstName = computed(() => session.firstName);
const currentContext = computed(() => chat.contextFor(branchKey.value));

const segSystem = computed(() => {
  if (!currentContext.value || !currentContext.value.limit) return 0;
  return Math.min(100, (currentContext.value.system / currentContext.value.limit) * 100);
});
const segTools = computed(() => {
  if (!currentContext.value || !currentContext.value.limit) return 0;
  return Math.min(100, (currentContext.value.tools / currentContext.value.limit) * 100);
});
const segMessages = computed(() => {
  if (!currentContext.value || !currentContext.value.limit) return 0;
  return Math.min(100, (currentContext.value.messages / currentContext.value.limit) * 100);
});

function onDocumentClick(e: MouseEvent) {
  const target = e.target as HTMLElement | null;
  if (contextOpen.value && !target?.closest('.ap-context-wrap')) {
    contextOpen.value = false;
  }
  if (headerMenuOpen.value && !target?.closest('.ap-head-menu-wrap')) {
    headerMenuOpen.value = false;
  }
  if (historyMenuOpen.value && !target?.closest('.ap-history-menu-wrap')) {
    historyMenuOpen.value = false;
  }
  if (activeConvMenuId.value && !target?.closest('.ap-conv-menu-wrap')) {
    activeConvMenuId.value = null;
    confirmingDeleteId.value = null;
  }
}

const greeting = computed(() => {
  const name = firstName.value ? `Halo, ${firstName.value}.` : 'Halo.';
  const b = branch.value;
  if (!b) return name;
  const role = b.description ? ` ${b.description}` : '';
  return `${name}\nSaya membantu di bidang ${b.name}.${role}`;
});
const showGreeting = computed(() => messages.value.length === 0);
const showTyping = computed(
  () => streaming.value && messages.value.length > 0 && messages.value[messages.value.length - 1].text === '',
);
const canSend = computed(() => !!draft.value.trim() && !streaming.value);

function shortName(name: string) {
  return name.split(/\s+/)[0] ?? name;
}

function summaryText(m: ChatMessage) {
  const parts = [`${m.steps?.length ?? 0} langkah`, `${m.tokens ?? 0} token`];
  if (m.durationMs) parts.push(formatDurationMs(m.durationMs));
  return parts.join(' · ');
}

// Tick 1 detik untuk durasi live (header Working for + durasi item berjalan).
const tick = ref(0);
let tickTimer: ReturnType<typeof setInterval> | null = null;
function resizeInput() {
  const el = inputEl.value;
  if (!el) return;
  el.style.height = 'auto';
  const cs = window.getComputedStyle(el);
  const lineH = parseFloat(cs.lineHeight) || 19;
  const padY = (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0);
  const maxH = Math.ceil(lineH * 5 + padY);
  const nextH = Math.min(el.scrollHeight, maxH);
  el.style.height = `${nextH}px`;
  el.style.overflowY = el.scrollHeight > maxH ? 'auto' : 'hidden';
}

watch(draft, () => {
  void nextTick(resizeInput);
});

onMounted(() => {
  window.addEventListener('click', onDocumentClick);
  resizeInput();
  tickTimer = setInterval(() => {
    tick.value += 1;
  }, 1000);
});
onUnmounted(() => {
  window.removeEventListener('click', onDocumentClick);
  if (tickTimer) clearInterval(tickTimer);
  if (recognition && listening.value) {
    recognition.stop();
  }
});

function stepDurationText(m: ChatMessage, i: number): string {
  const times = m.stepTimes ?? [];
  const start = times[i];
  if (start === undefined) return '';
  const end = times[i + 1] ?? (m.live ? performance.now() : (m.startedAt ?? start) + (m.durationMs ?? 0));
  return formatDurationMs(Math.max(0, end - start));
}

function workingText(m: ChatMessage): string {
  void tick.value;
  if (!m.startedAt) return 'Working…';
  return `Working for ${formatDurationMs(performance.now() - m.startedAt)}`;
}

function openPendingDrafts() {
  useWindowManager().open('pending-drafts', 'Persetujuan Tertunda');
}

function toggleSidebarOrHistory() {
  if (isWideMode.value) {
    ui.toggleAgentSidebar();
    if (ui.agentSidebarOpen && branchKey.value && !chat.conversations[branchKey.value]) {
      void chat.loadConversations(branchKey.value);
    }
  } else {
    chat.toggleHistory(branchKey.value);
  }
}

function closeSidebarOrHistory() {
  if (isWideMode.value) {
    ui.setAgentSidebarOpen(false);
  } else if (branchKey.value) {
    chat.historyOpen[branchKey.value] = false;
  }
}

function startResize(e: PointerEvent) {
  if (ui.agentFullscreen || e.button !== 0) return;
  const el = e.currentTarget as HTMLElement;
  const startX = e.clientX;
  const startW = panelEl.value?.getBoundingClientRect().width ?? ui.agentWidth;
  const deskMax = panelEl.value?.parentElement
    ? Math.max(AGENT_PANEL_MIN_W, panelEl.value.parentElement.clientWidth - 20)
    : AGENT_PANEL_MAX_W;
  const maxW = Math.min(AGENT_PANEL_MAX_W, deskMax);
  el.setPointerCapture(e.pointerId);
  const onMove = (ev: PointerEvent) => {
    const nextW = Math.max(AGENT_PANEL_MIN_W, Math.min(maxW, startW - (ev.clientX - startX)));
    ui.setAgentWidth(nextW);
  };
  const onUp = () => {
    el.removeEventListener('pointermove', onMove);
    el.removeEventListener('pointerup', onUp);
    el.removeEventListener('pointercancel', onUp);
  };
  el.addEventListener('pointermove', onMove);
  el.addEventListener('pointerup', onUp);
  el.addEventListener('pointercancel', onUp);
}

function toggleVoiceDictation() {
  if (!SpeechRecognitionCtor || streaming.value) return;
  if (listening.value && recognition) {
    recognition.stop();
    listening.value = false;
    return;
  }
  const rec = new SpeechRecognitionCtor();
  rec.lang = 'id-ID';
  rec.interimResults = false;
  rec.continuous = false;
  rec.onresult = (ev) => {
    const chunks: string[] = [];
    for (let i = ev.resultIndex; i < ev.results.length; i += 1) {
      const res = ev.results[i];
      if (res.isFinal && res[0]?.transcript) {
        chunks.push(res[0].transcript.trim());
      }
    }
    const spoken = chunks.join(' ').trim();
    if (spoken) {
      draft.value = draft.value.trim() ? `${draft.value.trimEnd()} ${spoken}` : spoken;
    }
  };
  rec.onerror = (ev) => {
    listening.value = false;
    if (ev.error && ev.error !== 'aborted' && ev.error !== 'no-speech') {
      ui.toast('Dikte suara gagal atau izin mikrofon ditolak.');
    }
  };
  rec.onend = () => {
    listening.value = false;
  };
  recognition = rec;
  try {
    rec.start();
    listening.value = true;
  } catch {
    listening.value = false;
    ui.toast('Tidak dapat memulai mikrofon.');
  }
}

async function toggleArchivedList() {
  historyMenuOpen.value = false;
  if (!branchKey.value) return;
  await chat.setHistoryArchived(branchKey.value, !isArchivedView.value);
}

async function changeSort(order: 'asc' | 'desc') {
  historyMenuOpen.value = false;
  if (!branchKey.value) return;
  await chat.setHistorySort(branchKey.value, order);
}

function toggleConvMenu(convId: string) {
  confirmingDeleteId.value = null;
  activeConvMenuId.value = activeConvMenuId.value === convId ? null : convId;
}

function startRename(c: ConversationItem) {
  activeConvMenuId.value = null;
  renamingConvId.value = c.id;
  renameDraft.value = c.title;
}

async function submitRename(convId: string) {
  const nextTitle = renameDraft.value.trim();
  if (!nextTitle || !branchKey.value || convActionBusy.value) return;
  convActionBusy.value = true;
  try {
    await chat.renameConversation(branchKey.value, convId, nextTitle);
    renamingConvId.value = null;
  } catch (err) {
    ui.toast(err instanceof Error ? err.message : 'Gagal mengganti nama percakapan.');
  } finally {
    convActionBusy.value = false;
  }
}

async function togglePin(c: ConversationItem) {
  activeConvMenuId.value = null;
  if (!branchKey.value || convActionBusy.value) return;
  convActionBusy.value = true;
  try {
    await chat.togglePinConversation(branchKey.value, c.id, !c.isPinned);
  } catch (err) {
    ui.toast(err instanceof Error ? err.message : 'Gagal menyematkan percakapan.');
  } finally {
    convActionBusy.value = false;
  }
}

async function toggleArchive(c: ConversationItem) {
  activeConvMenuId.value = null;
  if (!branchKey.value || convActionBusy.value) return;
  convActionBusy.value = true;
  try {
    await chat.toggleArchiveConversation(branchKey.value, c.id, !c.isArchived);
  } catch (err) {
    ui.toast(err instanceof Error ? err.message : 'Gagal mengarsipkan percakapan.');
  } finally {
    convActionBusy.value = false;
  }
}

async function confirmDelete(convId: string) {
  if (!branchKey.value || convActionBusy.value) return;
  convActionBusy.value = true;
  try {
    await chat.deleteConversation(branchKey.value, convId);
    confirmingDeleteId.value = null;
    activeConvMenuId.value = null;
  } catch (err) {
    ui.toast(err instanceof Error ? err.message : 'Gagal menghapus percakapan.');
  } finally {
    convActionBusy.value = false;
  }
}

function selectConversation(convId: string) {
  if (!branchKey.value) return;
  void chat.openConversation(branchKey.value, convId);
  if (isWideMode.value) {
    // Tetap biarkan sidebar terbuka di mode lebar agar navigasi cepat.
    chat.historyOpen[branchKey.value] = false;
  }
}

function confirmHandoff(m: ChatMessage) {
  if (!m.handoff || m.handoffAccepted || !branchKey.value) return;
  void chat.executeHandoff(branchKey.value, m.id, m.handoff);
}

function openArtifactChip(artifact: ArtifactEvent) {
  if (artifact.type === 'APPROVAL_CARD') {
    useWindowManager().open(`approval:${artifact.draft_id}`, 'Persetujuan Aksi');
  } else {
    chat.openArtifact(artifact);
  }
}

function openConversationFile(file: FileEntry) {
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

function fmtDate(value: string) {
  if (!value) return '';
  const d = new Date(value.replace(' ', 'T'));
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('id-ID', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

watch(
  () => [
    messages.value.length,
    messages.value[messages.value.length - 1]?.text,
    messages.value[messages.value.length - 1]?.steps?.length,
    messages.value[messages.value.length - 1]?.artifacts?.length,
    chat.uploadProgress[branchKey.value],
  ],
  () => {
    void nextTick(() => {
      const el = threadEl.value;
      if (el) el.scrollTop = el.scrollHeight;
    });
  },
);

function switchBranch(key: string) {
  branches.selectBranch(key);
  chat.historyOpen[key] = false;
  if (isWideMode.value && ui.agentSidebarOpen && !chat.conversations[key]) {
    void chat.loadConversations(key);
  }
  void nextTick(() => {
    const el = threadEl.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

function send(text?: string) {
  const value = (text ?? draft.value).trim();
  if (!value || streaming.value || !branchKey.value) return;
  draft.value = '';
  void chat.send(branchKey.value, value);
}

function pickFiles() {
  fileInput.value?.click();
}

async function onFilesPicked(e: Event) {
  const input = e.target as HTMLInputElement;
  const list = Array.from(input.files ?? []);
  input.value = '';
  if (!list.length || !branchKey.value) return;
  const rejected = list.find(
    (f) => !UPLOAD_EXTENSIONS.includes((f.name.split('.').pop() ?? '').toLowerCase()),
  );
  if (rejected) {
    ui.toast(`Format ${rejected.name} tidak didukung. Gunakan ${UPLOAD_EXTENSIONS.join(', ')}.`);
    return;
  }
  const oversize = list.find((f) => f.size > MAX_UPLOAD_BYTES);
  if (oversize) {
    ui.toast(`Ukuran ${oversize.name} melebihi batas 10 MB.`);
    return;
  }
  uploading.value = true;
  try {
    await chat.uploadFiles(branchKey.value, list);
  } catch (err) {
    ui.toast(err instanceof Error ? err.message : 'Unggahan gagal.');
  } finally {
    uploading.value = false;
  }
}
</script>

<template>
  <aside
    ref="panelEl"
    class="agent-panel"
    :class="{ wide: isWideMode, fullscreen: ui.agentFullscreen }"
    :style="panelStyle"
    aria-label="AI agents"
  >
    <div
      v-if="!ui.agentFullscreen"
      class="ap-resize-handle"
      role="separator"
      aria-orientation="vertical"
      aria-label="Ubah lebar panel chat"
      @pointerdown.stop="startResize"
    />

    <header class="ap-head">
      <div class="ap-title">
        <button
          v-if="sidebarVisible"
          type="button"
          class="icon-btn ap-head-sidebar-btn"
          aria-label="Sembunyikan sidebar"
          title="Sembunyikan sidebar"
          @click="closeSidebarOrHistory"
        >
          <AppIcon name="sidebar" :size="17" />
        </button>
        <AgentAvatar v-if="branch" :branch-key="branch.key" :name="branch.name" size="lg" />
        <div v-if="branch">
          <b :title="branch.name">{{ branch.name }}</b>
        </div>
        <div v-else><b>AI Agents</b><small>Memuat agent dari backend…</small></div>
      </div>
      <div class="ap-head-menu-wrap">
        <button
          type="button"
          class="icon-btn approvals"
          :aria-label="
            chat.pendingDrafts.length
              ? `Persetujuan tertunda: ${chat.pendingDrafts.length}`
              : chat.pendingDraftsError
                ? 'Gagal memuat persetujuan tertunda'
                : 'Menu panel'
          "
          :title="
            chat.pendingDrafts.length
              ? `Persetujuan tertunda (${chat.pendingDrafts.length})`
              : chat.pendingDraftsError
                ? 'Gagal memuat persetujuan tertunda'
                : 'Menu panel'
          "
          @click.stop="headerMenuOpen = !headerMenuOpen"
        >
          <AppIcon name="more-vertical" :size="18" />
          <span v-if="chat.pendingDrafts.length" class="badge">{{ chat.pendingDrafts.length }}</span>
          <span v-else-if="chat.pendingDraftsError" class="badge">!</span>
        </button>
        <div v-if="headerMenuOpen" class="ap-popover-menu ap-head-menu" @click.stop>
          <button
            type="button"
            @click="
              headerMenuOpen = false;
              toggleSidebarOrHistory();
            "
          >
            <AppIcon name="list" :size="14" />
            <span>Riwayat percakapan</span>
          </button>
          <button
            type="button"
            @click="
              headerMenuOpen = false;
              openPendingDrafts();
            "
          >
            <AppIcon name="file" :size="14" />
            <span>Daftar dan riwayat draft</span>
            <span v-if="chat.pendingDrafts.length" class="ap-menu-count">{{ chat.pendingDrafts.length }}</span>
            <span v-else-if="chat.pendingDraftsError" class="ap-menu-count warn">!</span>
          </button>
        </div>
      </div>
      <button
        class="icon-btn"
        :aria-label="ui.agentFullscreen ? 'Kembalikan ukuran' : 'Layar penuh'"
        :title="ui.agentFullscreen ? 'Kembalikan ukuran' : 'Layar penuh'"
        @click="ui.toggleAgentFullscreen()"
      >
        <AppIcon :name="ui.agentFullscreen ? 'restore' : 'square'" :size="17" />
      </button>
      <button class="icon-btn" aria-label="Tutup panel agent" @click="ui.closeAgent()">
        <AppIcon name="x" :size="18" />
      </button>
    </header>

    <nav v-if="!isWideMode" class="ap-tabs" aria-label="Daftar agent">
      <button
        v-for="b in branches.branches"
        :key="b.key"
        :class="{ on: b.key === branchKey }"
        :title="b.description || b.tagline || b.name"
        @click="switchBranch(b.key)"
      >
        <AgentAvatar :branch-key="b.key" :name="b.name" size="xs" />
        {{ shortName(b.name) }}
      </button>
    </nav>

    <div class="ap-body">
      <aside
        v-if="sidebarVisible"
        class="ap-history"
        :class="{ sidebar: isWideMode }"
        aria-label="Sidebar riwayat percakapan"
      >
        <div v-if="isWideMode" class="ap-tabs ap-tabs-sidebar" aria-label="Daftar agent">
          <button
            v-for="b in branches.branches"
            :key="b.key"
            :class="{ on: b.key === branchKey }"
            :title="b.description || b.tagline || b.name"
            @click="switchBranch(b.key)"
          >
            <AgentAvatar :branch-key="b.key" :name="b.name" size="xs" />
            {{ shortName(b.name) }}
          </button>
        </div>

        <div class="ap-history-head">
          <div class="ap-history-sort-group">
            <span class="ap-sort-enum">{{ historySort === 'asc' ? 'Terlama' : 'Terbaru' }}</span>
            <button
              type="button"
              class="icon-btn ap-collapse-btn"
              :aria-expanded="!historyListCollapsed"
              :aria-label="historyListCollapsed ? 'Tampilkan daftar percakapan' : 'Lipat daftar percakapan'"
              :title="historyListCollapsed ? 'Tampilkan daftar percakapan' : 'Lipat daftar percakapan'"
              @click="historyListCollapsed = !historyListCollapsed"
            >
              <AppIcon :name="historyListCollapsed ? 'chevron-right' : 'chevron-down'" :size="14" />
            </button>
            <span v-if="isArchivedView" class="ap-archived-pill">Arsip</span>
          </div>

          <div class="ap-history-head-actions">
            <div class="ap-history-menu-wrap" :class="{ open: historyMenuOpen }">
              <button
                type="button"
                class="icon-btn ap-history-more-btn"
                aria-label="Opsi daftar percakapan"
                title="Opsi daftar percakapan"
                @click.stop="historyMenuOpen = !historyMenuOpen"
              >
                <AppIcon name="more-vertical" :size="16" />
              </button>
              <div v-if="historyMenuOpen" class="ap-popover-menu" @click.stop>
                <button
                  type="button"
                  :class="{ active: historySort === 'desc' }"
                  @click="changeSort('desc')"
                >
                  <AppIcon name="arrow-up-down" :size="14" />
                  <span>Terbaru</span>
                </button>
                <button
                  type="button"
                  :class="{ active: historySort === 'asc' }"
                  @click="changeSort('asc')"
                >
                  <AppIcon name="arrow-up-down" :size="14" />
                  <span>Terlama</span>
                </button>
                <div class="ap-menu-sep" />
                <button type="button" @click="toggleArchivedList">
                  <AppIcon name="archive" :size="14" />
                  <span>{{ isArchivedView ? 'Kembali ke aktif' : 'Archived' }}</span>
                </button>
              </div>
            </div>
            <button
              v-if="!isArchivedView"
              type="button"
              class="icon-btn"
              aria-label="Percakapan baru"
              title="Percakapan baru"
              @click="chat.newConversation(branchKey)"
            >
              <AppIcon name="plus" :size="16" />
            </button>
          </div>
        </div>

        <div v-if="!historyListCollapsed" class="ap-history-list">
          <div
            v-for="c in conversations"
            :key="c.id"
            class="ap-history-row"
            :class="{ on: c.id === chat.currentConversation[branchKey] }"
          >
            <form
              v-if="renamingConvId === c.id"
              class="ap-rename-form"
              @submit.prevent="submitRename(c.id)"
            >
              <input
                v-model="renameDraft"
                type="text"
                class="ap-rename-input"
                aria-label="Judul percakapan baru"
                autofocus
                @keydown.escape.prevent="renamingConvId = null"
              />
              <button type="submit" class="icon-btn" aria-label="Simpan nama" :disabled="convActionBusy">
                <AppIcon name="check" :size="14" />
              </button>
              <button type="button" class="icon-btn" aria-label="Batal" @click="renamingConvId = null">
                <AppIcon name="x" :size="14" />
              </button>
            </form>
            <template v-else>
              <button
                type="button"
                class="ap-history-item"
                :class="{ on: c.id === chat.currentConversation[branchKey] }"
                @click="selectConversation(c.id)"
              >
                <span class="ap-history-title-row">
                  <AppIcon v-if="c.isPinned" name="pin" :size="12" class="ap-pin-icon" />
                  <b>{{ c.title }}</b>
                </span>
                <small>{{ fmtDate(c.updatedAt) }}</small>
              </button>
              <div class="ap-conv-menu-wrap" :class="{ open: activeConvMenuId === c.id }">
                <button
                  type="button"
                  class="icon-btn ap-conv-more"
                  aria-label="Menu percakapan"
                  @click.stop="toggleConvMenu(c.id)"
                >
                  <AppIcon name="more-vertical" :size="14" />
                </button>
                <div v-if="activeConvMenuId === c.id" class="ap-popover-menu" @click.stop>
                  <template v-if="confirmingDeleteId === c.id">
                    <div class="ap-confirm-text">Hapus permanen?</div>
                    <button
                      type="button"
                      class="danger"
                      :disabled="convActionBusy"
                      @click="confirmDelete(c.id)"
                    >
                      <AppIcon name="trash" :size="14" />
                      <span>Konfirmasi Hapus</span>
                    </button>
                    <button type="button" @click="confirmingDeleteId = null">
                      <AppIcon name="x" :size="14" />
                      <span>Batal</span>
                    </button>
                  </template>
                  <template v-else>
                    <button type="button" :disabled="convActionBusy" @click="togglePin(c)">
                      <AppIcon name="pin" :size="14" />
                      <span>{{ c.isPinned ? 'Unpin' : 'Pin' }}</span>
                    </button>
                    <button type="button" :disabled="convActionBusy" @click="startRename(c)">
                      <AppIcon name="edit" :size="14" />
                      <span>Rename</span>
                    </button>
                    <button type="button" :disabled="convActionBusy" @click="toggleArchive(c)">
                      <AppIcon name="archive" :size="14" />
                      <span>{{ c.isArchived ? 'Unarchive' : 'Archive' }}</span>
                    </button>
                    <button
                      type="button"
                      class="danger"
                      :disabled="convActionBusy"
                      @click="confirmingDeleteId = c.id"
                    >
                      <AppIcon name="trash" :size="14" />
                      <span>Delete</span>
                    </button>
                  </template>
                </div>
              </div>
            </template>
          </div>

          <div v-if="chat.historyLoading[branchKey]" class="empty-note">
            Memuat riwayat…
          </div>
          <div v-else-if="historyError" class="ap-history-error" role="alert">
            <span>{{ historyError }}</span>
            <button
              type="button"
              class="btn ghost"
              :disabled="chat.historyLoading[branchKey]"
              @click="chat.loadConversations(branchKey)"
            >
              Coba lagi
            </button>
          </div>
          <div v-else-if="!conversations.length" class="empty-note">
            {{ isArchivedView ? 'Tidak ada percakapan diarsipkan.' : 'Belum ada percakapan di cabang ini.' }}
          </div>
        </div>
      </aside>

      <div class="ap-main">
        <div ref="threadEl" class="ap-thread">
          <div class="ap-thread-inner">
            <div v-if="referral" class="ap-referral-banner" role="status">
            <div class="ap-referral-head">
              <AppIcon name="arrow-right" :size="13" />
              <b>Dialihkan dari {{ referral.fromBranchName }}</b>
            </div>
            <small v-if="referral.reason">{{ referral.reason }}</small>
            <details v-if="referral.summary" class="ap-referral-details">
              <summary>Ringkasan konteks &amp; lampiran</summary>
              <pre>{{ referral.summary }}</pre>
            </details>
          </div>
          <div v-if="showGreeting" class="msg agent">
            <div class="msg-who">
              <AgentAvatar v-if="branch" :branch-key="branch.key" :name="branch.name" size="xs" />
              {{ branch?.name ?? 'Agent' }}
            </div>
            <div class="bubble"><RichText :text="greeting" /></div>
          </div>
          <template v-for="m in messages" :key="m.id">
            <div class="msg" :class="m.role">
              <div v-if="m.role === 'agent'" class="msg-who">
                <AgentAvatar v-if="branch" :branch-key="branch.key" :name="branch.name" size="xs" />
                {{ branch?.name ?? 'Agent' }}
              </div>
              <div v-if="m.role === 'agent' && m.steps?.length" class="trace-block" :class="{ live: m.live }">
                <button class="trace-head" @click="traceOpenId = traceOpenId === m.id ? null : m.id">
                  <span v-if="m.live" class="trace-live-dot" aria-hidden="true" />
                  <b v-if="m.live">{{ workingText(m) }}</b>
                  <template v-else>
                    <b>Langkah agent · {{ m.steps.length }}</b>
                    <span class="trace-summary">{{ summaryText(m) }}</span>
                  </template>
                  <span class="trace-toggle">{{ traceOpenId === m.id ? 'Sembunyikan' : 'Lihat detail' }}</span>
                </button>
                <div v-if="traceOpenId === m.id || m.live" class="trace-steps">
                  <AgentStep
                    v-for="(step, si) in m.steps"
                    :key="si"
                    :step="step"
                    :default-open="!!m.live && si === (m.steps?.length ?? 0) - 1"
                    :running="!!m.live && si === (m.steps?.length ?? 0) - 1"
                    :duration-text="stepDurationText(m, si)"
                  />
                </div>
              </div>
              <div class="bubble"><RichText :text="m.text || (m.stopped ? '[Respons dihentikan oleh pengguna]' : '')" /></div>
              <div v-if="m.stopped" class="msg-stopped-tag">Dihentikan oleh pengguna</div>
              <div v-if="m.handoff" class="ap-handoff-card">
                <div class="ap-handoff-info">
                  <b>Rujukan ke {{ m.handoff.to_branch_name || m.handoff.to_branch }}</b>
                  <small v-if="m.handoff.reason">{{ m.handoff.reason }}</small>
                </div>
                <button
                  v-if="!m.handoffAccepted"
                  type="button"
                  class="ap-handoff-btn"
                  @click="confirmHandoff(m)"
                >
                  <AppIcon name="arrow-right" :size="13" />
                  <span>Pindahkan ke {{ m.handoff.to_branch_name || m.handoff.to_branch }}</span>
                </button>
                <span v-else class="ap-handoff-done">
                  <AppIcon name="check" :size="13" />
                  <span>Dialihkan ke {{ m.handoff.to_branch_name || m.handoff.to_branch }}</span>
                </span>
              </div>
              <div v-if="m.artifacts?.length" class="msg-artifacts">
                <button
                  v-for="a in m.artifacts"
                  :key="a.type === 'FILE' ? (a.file_id || a.file_url) : a.draft_id"
                  class="msg-artifact"
                  type="button"
                  @click="openArtifactChip(a)"
                >
                  <template v-if="a.type === 'FILE'">
                    <AppIcon name="file" :size="12" />
                    <span>{{ a.file_name }}</span>
                  </template>
                  <template v-else>{{ `Persetujuan ${a.action_type}` }}</template>
                </button>
              </div>
            </div>
          </template>
          <div v-if="legacyFiles.length" class="msg legacy-files-entry">
            <div class="legacy-files-heading">File lama dari percakapan ini; pesan asal tidak tercatat.</div>
            <div class="legacy-file-list">
              <button
                v-for="file in legacyFiles"
                :key="file.file_id || file.file_url"
                class="msg-artifact"
                type="button"
                @click="openConversationFile(file)"
              >
                <AppIcon name="file" :size="12" />
                <span>{{ file.file_name }}</span>
              </button>
            </div>
          </div>
          <div v-if="showTyping" class="msg agent">
            <div class="bubble typing"><i /><i /><i /></div>
          </div>
          </div>
        </div>

        <div v-if="showGreeting && !streaming" class="ap-prompts">
          <button v-for="p in suggestions" :key="p" class="chip" @click="send(p)">{{ p }}</button>
        </div>

        <div v-if="files.length || uploadPercent !== undefined" class="ap-files">
          <div v-if="uploadPercent !== undefined" class="ap-file">
            <AppIcon name="paperclip" :size="13" />
            <span>Mengunggah… {{ uploadPercent }}%</span>
            <span class="bar"><i :style="{ width: uploadPercent + '%' }" /></span>
          </div>
          <div v-for="f in files" :key="f.id" class="ap-file">
            <AppIcon name="file" :size="13" />
            <span>{{ f.file_name }}</span>
            <button class="icon-btn" style="width: 20px; height: 20px" aria-label="Hapus lampiran" @click="chat.removeFile(branchKey, f.id)">
              <AppIcon name="x" :size="12" />
            </button>
          </div>
        </div>

        <form class="ap-input" @submit.prevent="send()">
          <textarea
            id="agent-input"
            ref="inputEl"
            v-model="draft"
            rows="1"
            :placeholder="'Kirim pesan ke ' + (branch?.name ?? 'agent')"
            aria-label="Pesan"
            @input="resizeInput"
            @keydown.enter.exact.prevent="send()"
          />
          <button
            class="icon-btn"
            :class="{ listening }"
            type="button"
            :disabled="!voiceSupported || streaming"
            :aria-label="
              voiceSupported
                ? listening
                  ? 'Hentikan dikte suara'
                  : 'Dikte suara'
                : 'Dikte suara tidak didukung di browser ini'
            "
            :title="
              voiceSupported
                ? listening
                  ? 'Hentikan dikte suara'
                  : 'Dikte suara'
                : 'Dikte suara tidak didukung di browser ini'
            "
            @click="toggleVoiceDictation"
          >
            <AppIcon :name="voiceSupported ? 'mic' : 'mic-off'" :size="17" />
          </button>
          <button class="icon-btn" type="button" aria-label="Lampirkan berkas" :disabled="uploading" @click="pickFiles">
            <AppIcon name="paperclip" :size="17" />
          </button>
          <input
            ref="fileInput"
            type="file"
            :accept="UPLOAD_EXTENSIONS.map((e) => '.' + e).join(',')"
            multiple
            hidden
            aria-hidden="true"
            @change="onFilesPicked"
          />
          <button
            v-if="streaming"
            class="send stop"
            type="button"
            aria-label="Hentikan jawaban"
            title="Hentikan jawaban"
            @click="chat.stopStreaming(branchKey)"
          >
            <AppIcon name="stop" :size="16" />
          </button>
          <button v-else class="send" type="submit" :disabled="!canSend" aria-label="Kirim">
            <AppIcon name="send" :size="16" />
          </button>
        </form>
        <div class="ap-foot">
          <span class="ap-foot-note">AIOS dapat keliru, periksa kembali info penting.</span>
          <div v-if="currentContext" class="ap-context-wrap">
            <button
              type="button"
              class="ap-context-pill"
              :class="{
                compacted: currentContext.compacted,
                warn: currentContext.percent >= 75,
              }"
              :title="`Context: ${currentContext.percent}% (~${formatTokenCount(currentContext.total)} / ${formatTokenCount(currentContext.limit)})`"
              :aria-expanded="contextOpen"
              aria-label="Rincian penggunaan konteks AI Agent"
              @click.stop="contextOpen = !contextOpen"
            >
              <span class="cp-ring" aria-hidden="true" />
              <span class="cp-percent">{{ currentContext.percent }}%</span>
              <span v-if="currentContext.compacted" class="cp-pill-tag">Compacted</span>
            </button>

            <div v-if="contextOpen" class="ap-context-popover" @click.stop>
              <div class="cp-head">
                <span class="cp-title">{{ currentContext.percent }}% of context used</span>
                <span class="cp-ratio">~{{ formatTokenCount(currentContext.total) }} / {{ formatTokenCount(currentContext.limit) }}</span>
              </div>
              <div class="cp-bar" role="progressbar" :aria-valuenow="currentContext.percent" aria-valuemin="0" aria-valuemax="100">
                <span class="seg seg-system" :style="{ width: `${segSystem}%` }" :title="`System: ~${formatTokenCount(currentContext.system)}`" />
                <span class="seg seg-tools" :style="{ width: `${segTools}%` }" :title="`Tools: ~${formatTokenCount(currentContext.tools)}`" />
                <span class="seg seg-messages" :style="{ width: `${segMessages}%` }" :title="`Messages: ~${formatTokenCount(currentContext.messages)}`" />
              </div>
              <div class="cp-breakdown">
                <div class="cp-row">
                  <span class="cp-dot dot-system">■</span>
                  <span class="cp-label">System prompt</span>
                  <span class="cp-val">~{{ formatTokenCount(currentContext.system) }}</span>
                </div>
                <div class="cp-row">
                  <span class="cp-dot dot-tools">■</span>
                  <span class="cp-label">Tool definitions</span>
                  <span class="cp-val">~{{ formatTokenCount(currentContext.tools) }}</span>
                </div>
                <div class="cp-row">
                  <span class="cp-dot dot-messages">■</span>
                  <span class="cp-label">Messages</span>
                  <span class="cp-val">~{{ formatTokenCount(currentContext.messages) }}</span>
                </div>
              </div>
              <div v-if="currentContext.compacted" class="cp-compacted-note">
                <span class="cp-compacted-badge">Compacted</span>
                <span>Memori bergulir aktif</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>
