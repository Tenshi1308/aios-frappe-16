import { defineStore } from 'pinia';
import {
  approveDraft,
  closeDraft,
  confirmDraftCashPayment,
  deleteConversation as deleteConversationApi,
  fetchConversationMessages,
  fetchConversations,
  fetchMyFiles,
  fetchPendingDrafts,
  fetchUnreadSalesInsights,
  markSalesInsightsRead,
  rejectDraft,
  renameConversation as renameConversationApi,
  setConversationArchive as setConversationArchiveApi,
  setConversationPin as setConversationPinApi,
  stopStream as stopStreamApi,
  streamChat,
  uploadAttachment,
} from '../api/chat';
import { useBranchesStore } from './branches';
import { useSessionStore } from './session';
import { useModulesStore } from './modules';
import { reportClientError } from '../api/client';
import type {
  ArtifactEvent,
  AttachmentMeta,
  ChatMessage,
  ContextUsageStats,
  ConversationItem,
  ConversationReferral,
  DraftListStatus,
  FileEntry,
  HandoffEvent,
  PendingDraft,
  TraceEvent,
} from '../types';
import { useWindowManager } from '../composables/useWindowManager';

const streamControllers = new Map<string, AbortController>();
const stoppedBranches = new Set<string>();

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
    historyError: {} as Record<string, string>,
    historyArchived: {} as Record<string, boolean>,
    historySort: {} as Record<string, 'asc' | 'desc'>,
    pendingDrafts: [] as PendingDraft[],
    pendingDraftsLoading: false,
    pendingDraftsError: '',
    expiredDrafts: [] as PendingDraft[],
    expiredDraftsLoading: false,
    expiredDraftsError: '',
    historyDrafts: [] as PendingDraft[],
    historyDraftsLoading: false,
    historyDraftsError: '',
    contextUsage: {} as Record<string, ContextUsageStats | null>,
    referrals: {} as Record<string, ConversationReferral | null>,
    /** Artefak FILE yang jendelanya pernah dibuka (key = file_id, fallback file_url). */
    artifactWindows: {} as Record<string, ArtifactEvent>,
    proactiveUnreadCount: 0,
    proactiveConversationId: null as string | null,
  }),
  getters: {
    /** Thread percakapan aktif (cache per conversationId — trace tidak tertimpa saat pindah sesi). */
    threadFor: (s) => (branch: string) => {
      const conv = s.currentConversation[branch];
      return s.threads[conv ?? `new:${branch}`] ?? [];
    },
    contextFor: (s) => (branch: string) => {
      const conv = s.currentConversation[branch];
      return s.contextUsage[conv ?? `new:${branch}`] ?? null;
    },
    referralFor: (s) => (branch: string) => {
      const conv = s.currentConversation[branch];
      return s.referrals[conv ?? `new:${branch}`] ?? null;
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
    async loadPendingDrafts(status: DraftListStatus = 'PENDING_APPROVAL') {
      const session = useSessionStore();
      if (status === 'HISTORY') {
        this.historyDraftsLoading = true;
        this.historyDraftsError = '';
        try {
          this.historyDrafts = await fetchPendingDrafts(session.csrfToken, 'HISTORY');
        } catch (err) {
          this.historyDrafts = [];
          this.historyDraftsError = 'Daftar riwayat draft tidak dapat dimuat.';
          const msg =
            err instanceof Error && err.message.trim()
              ? err.message
              : 'Daftar riwayat draft tidak dapat dimuat.';
          void reportClientError(
            {
              message: msg,
              context: 'loadPendingDrafts:HISTORY',
              stack: err instanceof Error ? (err.stack ?? '') : '',
            },
            session.csrfToken,
          );
        } finally {
          this.historyDraftsLoading = false;
        }
        return;
      }
      if (status === 'EXPIRED') {
        this.expiredDraftsLoading = true;
        this.expiredDraftsError = '';
        try {
          this.expiredDrafts = await fetchPendingDrafts(session.csrfToken, 'EXPIRED');
        } catch (err) {
          this.expiredDrafts = [];
          this.expiredDraftsError = 'Daftar draft tidak dapat dimuat.';
          const msg =
            err instanceof Error && err.message.trim()
              ? err.message
              : 'Daftar draft tidak dapat dimuat.';
          void reportClientError(
            {
              message: msg,
              context: 'loadPendingDrafts:EXPIRED',
              stack: err instanceof Error ? (err.stack ?? '') : '',
            },
            session.csrfToken,
          );
        } finally {
          this.expiredDraftsLoading = false;
        }
        return;
      }

      this.pendingDraftsLoading = true;
      this.pendingDraftsError = '';
      try {
        this.pendingDrafts = await fetchPendingDrafts(session.csrfToken, 'PENDING_APPROVAL');
      } catch (err) {
        this.pendingDrafts = [];
        this.pendingDraftsError = 'Daftar draft tidak dapat dimuat.';
        const msg =
          err instanceof Error && err.message.trim()
            ? err.message
            : 'Daftar draft tidak dapat dimuat.';
        void reportClientError(
          {
            message: msg,
            context: 'loadPendingDrafts',
            stack: err instanceof Error ? (err.stack ?? '') : '',
          },
          session.csrfToken,
        );
      } finally {
        this.pendingDraftsLoading = false;
      }
    },
    async approveDraft(draftId: string) {
      const session = useSessionStore();
      const result = await approveDraft(draftId, session.csrfToken);
      await this.loadPendingDrafts('PENDING_APPROVAL');
      return result;
    },
    async rejectDraft(draftId: string, reason: string) {
      const session = useSessionStore();
      const result = await rejectDraft(draftId, reason, session.csrfToken);
      await this.loadPendingDrafts('PENDING_APPROVAL');
      return result;
    },
    async closeDraft(draftId: string) {
      const session = useSessionStore();
      const result = await closeDraft(draftId, session.csrfToken);
      await this.loadPendingDrafts('PENDING_APPROVAL');
      return result;
    },
    async confirmDraftCashPayment(draftId: string) {
      const session = useSessionStore();
      return await confirmDraftCashPayment(draftId, session.csrfToken);
    },
    async pollProactiveInsights() {
      const session = useSessionStore();
      try {
        const res = await fetchUnreadSalesInsights();
        this.proactiveUnreadCount = res.unread_count;
        this.proactiveConversationId = res.conversation_id;
        if (
          res.conversation_id &&
          !(this.conversations.sales ?? []).some((c) => c.id === res.conversation_id)
        ) {
          await this.loadConversations('sales');
        }
      } catch (err) {
        console.error('[pollProactiveInsights]', err);
        void reportClientError(
          {
            message: err instanceof Error && err.message.trim() ? err.message : 'Gagal memeriksa insight proaktif Sales.',
            context: 'pollProactiveInsights',
            stack: err instanceof Error ? (err.stack ?? '') : '',
          },
          session.csrfToken,
        );
      }
    },
    async clearProactiveUnread() {
      const session = useSessionStore();
      if (this.proactiveUnreadCount <= 0) return;
      try {
        await markSalesInsightsRead(session.csrfToken);
        this.proactiveUnreadCount = 0;
      } catch (err) {
        console.error('[clearProactiveUnread]', err);
        void reportClientError(
          {
            message: err instanceof Error && err.message.trim() ? err.message : 'Gagal menandai insight proaktif sudah dibaca.',
            context: 'clearProactiveUnread',
            stack: err instanceof Error ? (err.stack ?? '') : '',
          },
          session.csrfToken,
        );
      }
    },
    async loadConversations(branch: string) {
      const session = useSessionStore();
      this.historyLoading[branch] = true;
      this.historyError[branch] = '';
      try {
        this.conversations[branch] = await fetchConversations(branch, {
          archived: !!this.historyArchived[branch],
          sort: this.historySort[branch] ?? 'desc',
        });
      } catch (err) {
        this.conversations[branch] = [];
        this.historyError[branch] = 'Riwayat percakapan tidak bisa dimuat. Coba lagi.';
        const msg =
          err instanceof Error && err.message.trim()
            ? err.message
            : 'Riwayat percakapan tidak bisa dimuat.';
        console.error('[loadConversations]', err);
        void reportClientError(
          {
            message: msg,
            context: 'loadConversations',
            stack: err instanceof Error ? (err.stack ?? '') : '',
          },
          session.csrfToken,
        );
      } finally {
        this.historyLoading[branch] = false;
      }
    },
    async setHistoryArchived(branch: string, archived: boolean) {
      this.historyArchived[branch] = archived;
      await this.loadConversations(branch);
    },
    async setHistorySort(branch: string, sort: 'asc' | 'desc') {
      this.historySort[branch] = sort;
      await this.loadConversations(branch);
    },
    async renameConversation(branch: string, conversationId: string, title: string) {
      const session = useSessionStore();
      try {
        const updated = await renameConversationApi(conversationId, title, session.csrfToken);
        const list = this.conversations[branch] ?? [];
        this.conversations[branch] = list.map((c) =>
          c.id === conversationId ? { ...c, title: updated.title } : c,
        );
      } catch (err) {
        console.error('[renameConversation]', err);
        void reportClientError(
          {
            message: err instanceof Error && err.message.trim() ? err.message : 'Gagal mengganti nama percakapan.',
            context: 'renameConversation',
            stack: err instanceof Error ? (err.stack ?? '') : '',
          },
          session.csrfToken,
        );
        throw new Error('Gagal mengganti nama percakapan.');
      }
    },
    async togglePinConversation(branch: string, conversationId: string, pinned: boolean) {
      const session = useSessionStore();
      try {
        await setConversationPinApi(conversationId, pinned, session.csrfToken);
      } catch (err) {
        console.error('[togglePinConversation]', err);
        void reportClientError(
          {
            message: err instanceof Error && err.message.trim() ? err.message : 'Gagal menyematkan percakapan.',
            context: 'togglePinConversation',
            stack: err instanceof Error ? (err.stack ?? '') : '',
          },
          session.csrfToken,
        );
        throw new Error('Gagal menyematkan percakapan.');
      }
      await this.loadConversations(branch);
    },
    async toggleArchiveConversation(branch: string, conversationId: string, archived: boolean) {
      const session = useSessionStore();
      try {
        await setConversationArchiveApi(conversationId, archived, session.csrfToken);
      } catch (err) {
        console.error('[toggleArchiveConversation]', err);
        void reportClientError(
          {
            message: err instanceof Error && err.message.trim() ? err.message : 'Gagal mengarsipkan percakapan.',
            context: 'toggleArchiveConversation',
            stack: err instanceof Error ? (err.stack ?? '') : '',
          },
          session.csrfToken,
        );
        throw new Error('Gagal mengarsipkan percakapan.');
      }
      if (archived && this.currentConversation[branch] === conversationId) {
        this.newConversation(branch);
      }
      await this.loadConversations(branch);
    },
    async deleteConversation(branch: string, conversationId: string) {
      const session = useSessionStore();
      try {
        await deleteConversationApi(conversationId, session.csrfToken);
      } catch (err) {
        console.error('[deleteConversation]', err);
        void reportClientError(
          {
            message: err instanceof Error && err.message.trim() ? err.message : 'Gagal menghapus percakapan.',
            context: 'deleteConversation',
            stack: err instanceof Error ? (err.stack ?? '') : '',
          },
          session.csrfToken,
        );
        throw new Error('Gagal menghapus percakapan.');
      }
      delete this.threads[conversationId];
      delete this.legacyFiles[conversationId];
      delete this.contextUsage[conversationId];
      delete this.referrals[conversationId];
      if (this.currentConversation[branch] === conversationId) {
        this.newConversation(branch);
      }
      await this.loadConversations(branch);
    },
    stopStreaming(branch: string) {
      const session = useSessionStore();
      const controller = streamControllers.get(branch);
      if (!controller) return;
      stoppedBranches.add(branch);
      const conversationId = this.currentConversation[branch];
      if (conversationId) {
        void stopStreamApi(conversationId, session.csrfToken).catch((err) => {
          void reportClientError(
            {
              message: err instanceof Error ? err.message : 'Gagal mengirim sinyal stop stream.',
              context: 'stopStreaming',
              stack: err instanceof Error ? (err.stack ?? '') : '',
            },
            session.csrfToken,
          );
        });
      }
      controller.abort();
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
        this.referrals[conversationId] = history.referral ?? null;
        if (history.context) {
          this.contextUsage[conversationId] = history.context;
        }
      }
      if (
        branch === 'sales' &&
        this.proactiveConversationId &&
        conversationId === this.proactiveConversationId &&
        this.proactiveUnreadCount > 0
      ) {
        await this.clearProactiveUnread();
      }
    },
    newConversation(branch: string) {
      // Klien saja: conversation baru benar-benar dibuat backend saat pesan/
      // lampiran pertama terkirim dengan flag `new_conversation`.
      this.pendingNew[branch] = true;
      this.currentConversation[branch] = null;
      this.threads[`new:${branch}`] = [];
      this.contextUsage[`new:${branch}`] = null;
      this.referrals[`new:${branch}`] = null;
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
    async executeHandoff(fromBranch: string, messageId: string, handoff: HandoffEvent) {
      const toBranch = (handoff.to_branch || '').trim();
      if (!toBranch || toBranch === fromBranch) return;
      const branches = useBranchesStore();
      if (!branches.byKey(toBranch)) return;
      const sourceThreadKey = this.currentConversation[fromBranch] ?? `new:${fromBranch}`;
      const sourceList = this.threads[sourceThreadKey];
      if (sourceList) {
        const idx = sourceList.findIndex((item) => item.id === messageId);
        if (idx !== -1) {
          if (sourceList[idx].handoffAccepted) return;
          sourceList[idx] = { ...sourceList[idx], handoffAccepted: true };
        }
      }
      this.streaming[fromBranch] = false;
      branches.selectBranch(toBranch);
      this.newConversation(toBranch);
      const query = (handoff.query || handoff.handoff_prompt || '').trim();
      if (!query) return;
      await this.send(toBranch, query, {
        fileIds: handoff.file_ids,
        handoff,
      });
    },
    async send(
      branch: string,
      text: string,
      opts: { workerKey?: string; fileIds?: string[]; handoff?: HandoffEvent } = {},
    ) {
      const session = useSessionStore();
      const trimmed = text.trim();
      if (!trimmed || this.isStreaming(branch)) return;
      if (opts.handoff) {
        this.referrals[`new:${branch}`] = {
          fromBranchName: opts.handoff.from_branch_name || opts.handoff.from_branch,
          reason: opts.handoff.reason,
          originalQuery: opts.handoff.query,
          summary: opts.handoff.referral_summary,
        };
      }
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
      const fileIds =
        opts.fileIds && opts.fileIds.length ? opts.fileIds : pendingFiles.map((f) => f.id);
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
      const handoffHolder: { event: HandoffEvent | null } = { event: null };
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
      const controller = new AbortController();
      streamControllers.set(branch, controller);
      stoppedBranches.delete(branch);
      let wasStopped = false;
      try {
        await streamChat(
          branch,
          {
            message: trimmed,
            workerKey: opts.workerKey,
            conversationId: this.currentConversation[branch] ?? null,
            file_ids: fileIds.length ? fileIds : undefined,
            new_conversation:
              Boolean(opts.handoff) || (this.pendingNew[branch] && !this.currentConversation[branch]),
            handoff: opts.handoff
              ? {
                  from_branch: opts.handoff.from_branch,
                  from_branch_name: opts.handoff.from_branch_name,
                  reason: opts.handoff.reason,
                  referral_summary: opts.handoff.referral_summary,
                  source_conversation_id: opts.handoff.source_conversation_id,
                }
              : undefined,
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
                  if (this.referrals[threadKey]) {
                    this.referrals[conversationId] = this.referrals[threadKey];
                    delete this.referrals[threadKey];
                  }
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
            onOpenDomain: (domainKey) => {
              useModulesStore().openDomain(domainKey);
            },
            onHandoff: (handoffEvent) => {
              handoffHolder.event = handoffEvent;
              const list = this.threads[threadKey];
              if (list && list[index]) {
                list[index] = { ...list[index], handoff: handoffEvent, handoffAccepted: false };
              }
            },
            onDone: (tokens, context) => {
              const list = this.threads[threadKey];
              const completedConversationId = this.currentConversation[branch];
              if (completedConversationId) void this.loadMyFiles();
              if (context) {
                if (completedConversationId) {
                  this.contextUsage[completedConversationId] = context;
                }
                this.contextUsage[threadKey] = context;
              }
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
          controller.signal,
        );
      } catch (err) {
        const isAbort =
          stoppedBranches.has(branch) ||
          (err instanceof DOMException && err.name === 'AbortError') ||
          (err instanceof Error && err.name === 'AbortError');
        if (isAbort) {
          wasStopped = true;
          const list = this.threads[threadKey];
          if (list && list[index]) {
            list[index] = { ...list[index], live: false, stopped: true };
          }
        } else {
          const message = err instanceof Error ? err.message : 'Pesan gagal terkirim.';
          const list = this.threads[threadKey];
          if (list && list[index] && !list[index].text) {
            list[index] = { ...list[index], live: false, text: message };
          } else {
            this.threads[threadKey] = [...(list ?? []), { id: newMessageId(), role: 'agent', text: message }];
          }
        }
      } finally {
        streamControllers.delete(branch);
        stoppedBranches.delete(branch);
        // Stream selesai tanpa satu pun delta: jangan biarkan bubble kosong
        // senyap — tampilkan pesan aman yang jujur (kecuali dihentikan user).
        const list = this.threads[threadKey];
        const finalHandoff = handoffHolder.event;
        if (list && list[index] && !list[index].text && !wasStopped) {
          const fallbackText = finalHandoff
            ? `Permintaan dialihkan ke ${finalHandoff.to_branch_name || finalHandoff.to_branch}.`
            : 'Jawaban tidak dapat ditampilkan. Silakan coba lagi.';
          list[index] = { ...list[index], live: false, text: fallbackText };
        }
        if (list && list[index]) {
          list[index] = {
            ...list[index],
            live: false,
            stopped: wasStopped || list[index].stopped,
          };
        }
        this.streaming[branch] = false;
        if (finalHandoff) {
          const mode = useModulesStore().conversationSettings?.handoff_mode.value;
          const shouldAuto = mode ? mode === 'auto' : !!finalHandoff.auto_send;
          if (shouldAuto) {
            void this.executeHandoff(branch, placeholder.id, finalHandoff);
          }
        }
      }
    },
  },
});
