import { defineStore } from 'pinia';
import {
  fetchConversationMessages,
  fetchConversations,
  streamChat,
  uploadAttachment,
} from '../api/chat';
import { useSessionStore } from './session';
import type { AttachmentMeta, ChatMessage, ConversationItem } from '../types';

export const useChatStore = defineStore('chat', {
  state: () => ({
    conversations: {} as Record<string, ConversationItem[]>,
    threads: {} as Record<string, ChatMessage[]>,
    currentConversation: {} as Record<string, string | null>,
    pendingNew: {} as Record<string, boolean>,
    pendingFiles: {} as Record<string, AttachmentMeta[]>,
    uploadProgress: {} as Record<string, number>,
    streaming: {} as Record<string, boolean>,
    historyOpen: {} as Record<string, boolean>,
    historyLoading: {} as Record<string, boolean>,
  }),
  getters: {
    thread: (s) => (branch: string) => s.threads[branch] ?? [],
    files: (s) => (branch: string) => s.pendingFiles[branch] ?? [],
    isStreaming: (s) => (branch: string) => s.streaming[branch] ?? false,
  },
  actions: {
    async loadConversations(branch: string) {
      this.historyLoading[branch] = true;
      try {
        this.conversations[branch] = await fetchConversations(branch);
      } finally {
        this.historyLoading[branch] = false;
      }
    },
    async openConversation(branch: string, conversationId: string) {
      // Membuka percakapan lama membatalkan niat "sesi baru".
      this.pendingNew[branch] = false;
      this.currentConversation[branch] = conversationId;
      this.historyOpen[branch] = false;
      this.threads[branch] = await fetchConversationMessages(branch, conversationId);
    },
    newConversation(branch: string) {
      // Klien saja: conversation baru benar-benar dibuat backend saat pesan/
      // lampiran pertama terkirim dengan flag `new_conversation`.
      this.pendingNew[branch] = true;
      this.currentConversation[branch] = null;
      this.threads[branch] = [];
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
      this.threads[branch] = [...this.thread(branch), { role: 'user', text: trimmed }];
      this.streaming[branch] = true;
      const fileIds = this.files(branch).map((f) => f.id);
      this.pendingFiles[branch] = [];
      const placeholder: ChatMessage = { role: 'agent', text: '' };
      const threadKey = branch;
      const threadAtStart = this.threads[threadKey] ?? [];
      this.threads[threadKey] = [...threadAtStart, placeholder];
      const index = (this.threads[threadKey] ?? []).length - 1;
      const appendDelta = (chunk: string) => {
        const list = this.threads[threadKey];
        if (!list || !list[index]) return;
        list[index] = { ...list[index], text: list[index].text + chunk };
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
              if (this.currentConversation[branch] !== conversationId) {
                this.currentConversation[branch] = conversationId;
                void this.loadConversations(branch);
              }
              // Sesi baru sudah materialize; flag tidak perlu dibawa lagi.
              this.pendingNew[branch] = false;
            },
            onDelta: appendDelta,
          },
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Pesan gagal terkirim.';
        const list = this.threads[threadKey];
        if (list && list[index] && !list[index].text) {
          list[index] = { ...list[index], text: message };
        } else {
          this.threads[threadKey] = [...(list ?? []), { role: 'agent', text: message }];
        }
      } finally {
        // Stream selesai tanpa satu pun delta: jangan biarkan bubble kosong
        // senyap — tampilkan pesan aman yang jujur.
        const list = this.threads[threadKey];
        if (list && list[index] && !list[index].text) {
          list[index] = { ...list[index], text: 'Jawaban tidak dapat ditampilkan. Silakan coba lagi.' };
        }
        this.streaming[branch] = false;
      }
    },
  },
});
