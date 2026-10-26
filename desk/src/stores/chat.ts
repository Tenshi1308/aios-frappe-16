import { defineStore } from 'pinia';
import {
  approveDraft,
  fetchConversationMessages,
  fetchConversations,
  fetchMyFiles,
  fetchPendingDrafts,
  rejectDraft,
  streamChat,
  uploadAttachment,
} from '../api/chat';
import { useSessionStore } from './session';
import { useModulesStore } from './modules';
import type {
  ArtifactEvent,
  AttachmentMeta,
  ChatMessage,
  ConversationItem,
  FileEntry,
  PendingDraft,
  TraceEvent,
} from '../types';
import { useWindowManager } from '../composables/useWindowManager';

function newMessageId(): string {
  const rnd = globalThis.crypto?.randomUUID ? globalThis.crypto.randomUUID() : '';
  return rnd || `msg-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    conversations: {} as Record<string, ConversationItem[]>,
    myFiles: [] as FileEntry[],
    myFilesLoading: false,
    myFilesError: '',
    legacyFiles: {} as Record<string, FileEntry[]>,
    threads: {} as Record<string, ChatMessage[]>,
    currentConversation: {} as Record<string, string | null>,
    pendingNew: {} as Record<string, boolean>,
    pendingFiles: {} as Record<string, AttachmentMeta[]>,
    uploadProgress: {} as Record<string, number>,
    streaming: {} as Record<string, boolean>,
    historyOpen: {} as Record<string, boolean>,
    historyLoading: {} as Record<string, boolean>,
    pendingDrafts: [] as PendingDraft[],
    /** Artefak FILE yang jendelanya pernah dibuka (key = file_id, fallback file_url). */
    artifactWindows: {} as Record<string, ArtifactEvent>,
  }),
  getters: {
    /** Thread percakapan aktif (cache per conversationId — trace tidak tertimpa saat pindah sesi). */
    threadFor: (s) => (branch: string) => {
      const conv = s.currentConversation[branch];
      return s.threads[conv ?? `new:${branch}`] ?? [];
    },
    files: (s) => (branch: string) => s.pendingFiles[branch] ?? [],
    isStreaming: (s) => (branch: string) => s.streaming[branch] ?? false,
  },
  actions: {
    /** Buka jendela artefak FILE dari chip pesan (tidak auto-open saat event tiba). */
    openArtifact(artifact: ArtifactEvent) {
      if (artifact.type !== 'FILE') return;
      const artifactKey = artifact.file_id || artifact.file_url;
      this.artifactWindows[artifactKey] = artifact;
      useWindowManager().open(`artifact:${artifactKey}`, artifact.file_name);
    },
    async loadPendingDrafts() {
      const session = useSessionStore();
      try {
        this.pendingDrafts = await fetchPendingDrafts(session.csrfToken);
      } catch {
        this.pendingDrafts = [];
      }
    },
    async approveDraft(draftId: string) {
      const session = useSessionStore();
      const result = await approveDraft(draftId, session.csrfToken);
      await this.loadPendingDrafts();
      return result;
    },
    async rejectDraft(draftId: string, reason: string) {
      const session = useSessionStore();
      const result = await rejectDraft(draftId, reason, session.csrfToken);
      await this.loadPendingDrafts();
      return result;
    },
    async loadConversations(branch: string) {
      this.historyLoading[branch] = true;
      try {
        this.conversations[branch] = await fetchConversations(branch);
      } finally {
        this.historyLoading[branch] = false;
      }
    },
    async loadMyFiles() {
      this.myFilesLoading = true;
      this.myFilesError = '';
      try {
        this.myFiles = await fetchMyFiles();
      } catch {
        this.myFiles = [];
        this.myFilesError = 'Daftar file tidak dapat dimuat.';
      } finally {
        this.myFilesLoading = false;
      }
    },
    async openConversation(branch: string, conversationId: string) {
      // Membuka percakapan lama membatalkan niat "sesi baru".
      this.pendingNew[branch] = false;
      this.currentConversation[branch] = conversationId;
      this.historyOpen[branch] = false;
      // Cache per conversationId dipertahankan: pindah sesi lalu balik
      // tetap menampilkan trace/langkah yang sudah di-stream.
      if (!this.threads[conversationId]) {
        const history = await fetchConversationMessages(branch, conversationId);
        this.threads[conversationId] = history.messages;
        this.legacyFiles[conversationId] = history.legacyFiles;
      }
    },
    newConversation(branch: string) {
      // Klien saja: conversation baru benar-benar dibuat backend saat pesan/
      // lampiran pertama terkirim dengan flag `new_conversation`.
      this.pendingNew[branch] = true;
      this.currentConversation[branch] = null;
      this.threads[`new:${branch}`] = [];
      this.historyOpen[branch] = false;
      this.pendingFiles[branch] = [];
    },
    toggleHistory(branch: string) {
      this.historyOpen[branch] = !this.historyOpen[branch];
      if (this.historyOpen[branch] && !this.conversations[branch]) void this.loadConversations(branch);
    },
    async uploadFiles(branch: string, files: File[]) {
      const session = useSessionStore();
      this.pendingFiles[branch] = this.files(branch);
      for (const file of files) {
        const conversationId = this.currentConversation[branch] ?? null;
        const fresh = this.pendingNew[branch] && !conversationId;
        this.uploadProgress[branch] = 1;
        try {
          const result = await uploadAttachment(
            file,
            fresh ? { branch, newConversation: true } : { conversationId },
            session.csrfToken,
            (percent) => {
              this.uploadProgress[branch] = percent;
            },
          );
          // Percakapan baru materialize di sini bila upload duluan.
          this.currentConversation[branch] = result.conversationId;
          this.pendingNew[branch] = false;
          this.pendingFiles[branch] = [...this.files(branch), result.attachment];
          void this.loadMyFiles();
          void this.loadConversations(branch);
        } finally {
          delete this.uploadProgress[branch];
        }
      }
    },
    removeFile(branch: string, fileId: string) {
      this.pendingFiles[branch] = this.files(branch).filter((f) => f.id !== fileId);
    },
    async send(branch: string, text: string, opts: { workerKey?: string } = {}) {
      const session = useSessionStore();
      const trimmed = text.trim();
      if (!trimmed || this.isStreaming(branch)) return;
      const threadKey0 = this.currentConversation[branch] ?? `new:${branch}`;
      const pendingFiles = this.files(branch);
      const conversationId = this.currentConversation[branch] ?? '';
      const userArtifacts: ArtifactEvent[] = pendingFiles
        .filter((file) => !!file.file_url)
        .map((file) => ({
          type: 'FILE',
          file_name: file.file_name,
          file_url: file.file_url,
          format: file.format,
          size: file.file_size,
          conversation_id: conversationId,
        }));
      this.threads[threadKey0] = [
        ...(this.threads[threadKey0] ?? []),
        { id: newMessageId(), role: 'user', text: trimmed, artifacts: userArtifacts },
      ];
      this.streaming[branch] = true;
      const fileIds = pendingFiles.map((f) => f.id);
      this.pendingFiles[branch] = [];
      const placeholder: ChatMessage = {
        id: newMessageId(),
        role: 'agent',
        text: '',
        live: true,
        startedAt: performance.now(),
        stepTimes: [],
      };
      let threadKey = this.currentConversation[branch] ?? `new:${branch}`;
      const threadAtStart = this.threads[threadKey] ?? [];
      this.threads[threadKey] = [...threadAtStart, placeholder];
      const index = (this.threads[threadKey] ?? []).length - 1;
      const startedAt = performance.now();
      const appendDelta = (chunk: string) => {
        const list = this.threads[threadKey];
        if (!list || !list[index]) return;
        list[index] = { ...list[index], text: list[index].text + chunk };
      };
      const appendTrace = (event: TraceEvent) => {
        const list = this.threads[threadKey];
        if (!list || !list[index]) return;
        const msg = list[index];
        // Timing klien untuk durasi per item activity feed.
        list[index] = {
          ...msg,
          steps: [...(msg.steps ?? []), event],
          stepTimes: [...(msg.stepTimes ?? []), performance.now()],
        };
      };
      const turnDraftIds: string[] = [];
      const appendArtifact = (artifact: ArtifactEvent) => {
        const list = this.threads[threadKey];
        if (!list || !list[index]) return;
        const currentArtifacts = list[index].artifacts ?? [];
        if (
          artifact.type === 'FILE' &&
          currentArtifacts.some(
            (item) => item.type === 'FILE' && (item.file_id || item.file_url) === (artifact.file_id || artifact.file_url),
          )
        ) {
          return;
        }
        list[index] = { ...list[index], artifacts: [...currentArtifacts, artifact] };
        if (artifact.type === 'APPROVAL_CARD') {
          // Kartu diantrekan: backend commit transaksinya tepat sebelum event
          // `done`, jadi jendela kartu dibuka di onDone pertama, bukan saat event.
          turnDraftIds.push(artifact.draft_id);
        }
      };
      try {
        await streamChat(
          branch,
          {
            message: trimmed,
            workerKey: opts.workerKey,
            conversationId: this.currentConversation[branch] ?? null,
            file_ids: fileIds.length ? fileIds : undefined,
            new_conversation: this.pendingNew[branch] && !this.currentConversation[branch],
          },
          session.csrfToken,
          {
            onMeta: (conversationId) => {
              const previous = this.currentConversation[branch];
              if (previous !== conversationId) {
                this.currentConversation[branch] = conversationId;
                // Sesi baru materialize: pindahkan thread sementara (`new:<branch>`)
                // ke cache conversationId agar trace ikut saat pindah sesi.
                if (threadKey !== conversationId && threadKey === (previous ?? `new:${branch}`)) {
                  this.threads[conversationId] = this.threads[threadKey] ?? [];
                  delete this.threads[threadKey];
                  threadKey = conversationId;
                }
                void this.loadConversations(branch);
              }
              // Sesi baru sudah materialize; flag tidak perlu dibawa lagi.
              this.pendingNew[branch] = false;
            },
            onDelta: appendDelta,
            onTrace: appendTrace,
            onArtifact: appendArtifact,
            onOpenModule: (moduleKey) => {
              void useModulesStore().openModule(moduleKey);
            },
            onDone: (tokens) => {
              const list = this.threads[threadKey];
              const completedConversationId = this.currentConversation[branch];
              if (completedConversationId) void this.loadMyFiles();
              if (!list || !list[index]) return;
              // Waktu akhir turn: penutup durasi item terakhir activity feed.
              const msg = list[index];
              const stepTimes = [...(msg.stepTimes ?? []), performance.now()];
              list[index] = {
                ...msg,
                live: false,
                stepTimes,
                tokens: tokens ?? msg.tokens,
                durationMs: Math.round(performance.now() - startedAt),
              };
              if (tokens !== undefined && turnDraftIds.length) {
                // Commit backend terjadi tepat sebelum event `done`; buka kartu
                // terakhir turn ini (multi-kartu: sisanya lewat daftar pending).
                useWindowManager().open(
                  `approval:${turnDraftIds[turnDraftIds.length - 1]}`,
                  'Persetujuan Aksi',
                );
                void this.loadPendingDrafts();
              }
            },
          },
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Pesan gagal terkirim.';
        const list = this.threads[threadKey];
        if (list && list[index] && !list[index].text) {
          list[index] = { ...list[index], live: false, text: message };
        } else {
          this.threads[threadKey] = [...(list ?? []), { id: newMessageId(), role: 'agent', text: message }];
        }
      } finally {
        // Stream selesai tanpa satu pun delta: jangan biarkan bubble kosong
        // senyap — tampilkan pesan aman yang jujur.
        const list = this.threads[threadKey];
        if (list && list[index] && !list[index].text) {
          list[index] = { ...list[index], live: false, text: 'Jawaban tidak dapat ditampilkan. Silakan coba lagi.' };
        }
        if (list && list[index]) {
          list[index] = { ...list[index], live: false };
        }
        this.streaming[branch] = false;
      }
    },
  },
});
