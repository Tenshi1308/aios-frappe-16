import { ApiError, apiFetch, unwrapMessage } from './client';
import type {
  ArtifactEvent,
  AttachmentMeta,
  ChatMessage,
  ConversationItem,
  DraftActionResult,
  DraftDetail,
  FileEntry,
  FileArtifact,
  PendingDraft,
  TraceEvent,
} from '../types';

/** Cermin batas backend (MAX_WORKSPACE_BYTES) untuk umpan balik cepat di klien;
 *  sumber kebenaran tetap divalidasi server. */
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const UPLOAD_EXTENSIONS = ['csv', 'pdf', 'xlsx'];

export interface StreamHandlers {
  onMeta?: (conversationId: string) => void;
  onDelta?: (text: string) => void;
  onTrace?: (event: TraceEvent) => void;
  onArtifact?: (artifact: ArtifactEvent) => void;
  onOpenModule?: (moduleKey: string) => void;
  onDone?: (tokens?: number) => void;
}

interface RawConversationList {
  conversations?: { id?: unknown; title?: unknown; updatedAt?: unknown }[];
}

interface RawConversationDetail {
  conversation?: {
    id?: unknown;
    title?: unknown;
    messages?: { id?: unknown; role?: unknown; content?: unknown; artifacts?: unknown }[];
    legacyFiles?: unknown;
  };
}

interface RawFileEntry {
  file_id?: unknown;
  conversation_id?: unknown;
  conversation_title?: unknown;
  branch?: unknown;
  file_name?: unknown;
  file_url?: unknown;
  file_size?: unknown;
  format?: unknown;
  creation?: unknown;
}

export async function fetchConversations(branch: string): Promise<ConversationItem[]> {
  const raw = unwrapMessage<RawConversationList>(await apiFetch(`/api/chat/${encodeURIComponent(branch)}/conversations`));
  const list = raw?.conversations ?? [];
  return list
    .filter((c) => (typeof c.id === 'string' && !!c.id) || typeof c.id === 'number')
    .map((c) => ({
      id: String(c.id),
      title: typeof c.title === 'string' && c.title ? c.title : 'Percakapan',
      updatedAt: typeof c.updatedAt === 'string' ? c.updatedAt : '',
    }));
}

function toFileEntry(row: RawFileEntry): FileEntry | null {
  if (
    typeof row.conversation_id !== 'string' ||
    typeof row.file_name !== 'string' ||
    typeof row.file_url !== 'string'
  ) {
    return null;
  }
  return {
    file_id: typeof row.file_id === 'string' ? row.file_id : undefined,
    conversation_id: row.conversation_id,
    conversation_title: typeof row.conversation_title === 'string' ? row.conversation_title : '',
    branch: typeof row.branch === 'string' ? row.branch : '',
    file_name: row.file_name,
    file_url: row.file_url,
    file_size: typeof row.file_size === 'number' ? row.file_size : Number(row.file_size) || 0,
    format: typeof row.format === 'string' ? row.format : '',
    creation: typeof row.creation === 'string' ? row.creation : '',
  };
}

function toFileArtifacts(value: unknown, conversationId: string): FileArtifact[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
    .filter((item) => item.type === 'FILE' && typeof item.file_name === 'string' && typeof item.file_url === 'string')
    .map((item) => ({
      type: 'FILE' as const,
      file_id: typeof item.file_id === 'string' ? item.file_id : undefined,
      file_name: item.file_name as string,
      file_url: item.file_url as string,
      format: typeof item.format === 'string' ? item.format : '',
      size: typeof item.size === 'number' ? item.size : Number(item.size) || 0,
      conversation_id:
        typeof item.conversation_id === 'string' ? item.conversation_id : conversationId,
    }));
}

/** Daftar file privat conversation dari endpoint server-side, bukan cache browser. */
export async function fetchMyFiles(conversationId?: string): Promise<FileEntry[]> {
  const query = conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : '';
  const raw = unwrapMessage<unknown>(
    await apiFetch(`/api/method/aios_v1.lib.workspace.list_my_files${query}`),
  );
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((row): row is RawFileEntry => !!row && typeof row === 'object')
    .map(toFileEntry)
    .filter((row): row is FileEntry => row !== null);
}

export async function fetchConversationMessages(
  branch: string,
  conversationId: string,
): Promise<{ messages: ChatMessage[]; legacyFiles: FileEntry[] }> {
  const raw = unwrapMessage<RawConversationDetail>(
    await apiFetch(`/api/chat/${encodeURIComponent(branch)}/conversations/${encodeURIComponent(conversationId)}`),
  );
  const list = raw?.conversation?.messages ?? [];
  const messages = list
    .filter((m) => typeof m.content === 'string')
    .map((m, i) => ({
      id: (typeof m.id === 'string' || typeof m.id === 'number') && String(m.id)
        ? String(m.id)
        : `hist-${conversationId}-${i}`,
      role: m.role === 'user' ? ('user' as const) : ('agent' as const),
      text: m.content as string,
      artifacts: toFileArtifacts(m.artifacts, conversationId),
    }));
  const legacyFiles = Array.isArray(raw?.conversation?.legacyFiles)
    ? raw.conversation.legacyFiles
        .filter((row): row is RawFileEntry => !!row && typeof row === 'object')
        .map(toFileEntry)
        .filter((row): row is FileEntry => row !== null)
    : [];
  return { messages, legacyFiles };
}

export async function uploadAttachment(
  file: File,
  opts: { conversationId?: string | null; branch?: string | null; newConversation?: boolean },
  csrfToken: string,
  onProgress?: (percent: number) => void,
): Promise<{ conversationId: string; attachment: AttachmentMeta }> {
  const form = new FormData();
  form.append('file', file);
  if (opts.newConversation) {
    // Sesi baru: conversationId sengaja tidak dikirim; backend membuat
    // conversation baru berdasarkan branch.
    form.append('new_conversation', '1');
    if (opts.branch) form.append('branch', opts.branch);
  } else if (opts.conversationId) {
    form.append('conversationId', opts.conversationId);
  } else if (opts.branch) {
    form.append('branch', opts.branch);
  }

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/chat/upload');
    xhr.setRequestHeader('X-Frappe-CSRF-Token', csrfToken);
    xhr.responseType = 'text';
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable && onProgress) onProgress(Math.round((ev.loaded / ev.total) * 100));
    };
    xhr.onerror = () => reject(new ApiError('Tidak dapat menghubungi server. Periksa koneksi.'));
    xhr.onload = () => {
      let data: unknown = null;
      try {
        data = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        data = null;
      }
      if (xhr.status >= 200 && xhr.status < 300 && data && typeof data === 'object') {
        const body = data as { conversationId?: unknown; attachment?: Record<string, unknown> };
        const attachment = body.attachment ?? {};
        if (typeof body.conversationId === 'undefined' || typeof attachment.id !== 'string') {
          reject(new ApiError('Respons unggahan tidak dikenal.'));
          return;
        }
        resolve({
          conversationId: String(body.conversationId),
          attachment: {
            id: attachment.id,
            file_id: attachment.id,
            file_name: typeof attachment.file_name === 'string' ? attachment.file_name : 'lampiran',
            file_url: typeof attachment.file_url === 'string' ? attachment.file_url : '',
            file_size: typeof attachment.file_size === 'number' ? attachment.file_size : 0,
            format: typeof attachment.format === 'string' ? attachment.format : '',
          },
        });
        return;
      }
      const message =
        data && typeof data === 'object' && 'error' in data && typeof (data as { error?: unknown }).error === 'string'
          ? (data as { error: string }).error
          : 'Unggahan gagal.';
      reject(new ApiError(message));
    };
    xhr.send(form);
  });
}

/** Konsumsi SSE dari POST /api/chat/<branch>/stream via fetch ReadableStream. */
export async function streamChat(
  branch: string,
  payload: {
    message: string;
    workerKey?: string;
    conversationId?: string | null;
    file_ids?: string[];
    new_conversation?: boolean;
  },
  csrfToken: string,
  handlers: StreamHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`/api/chat/${encodeURIComponent(branch)}/stream`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrfToken },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new ApiError('Tidak dapat menghubungi server. Periksa koneksi.');
  }
  if (!res.ok) {
    const text = await res.text();
    let data: unknown = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = null;
    }
    const message =
      data && typeof data === 'object' && 'error' in data && typeof (data as { error?: unknown }).error === 'string'
        ? (data as { error: string }).error
        : 'Pesan gagal terkirim.';
    throw new ApiError(message);
  }
  if (!res.body) throw new ApiError('Streaming tidak didukung.');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      for (const line of rawEvent.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        let event: { type?: string; [key: string]: unknown };
        try {
          event = JSON.parse(line.slice(6));
        } catch {
          continue;
        }
        if (event.type === 'meta' && typeof event.conversationId !== 'undefined') {
          handlers.onMeta?.(String(event.conversationId));
        } else if (event.type === 'delta' && typeof event.text === 'string') {
          handlers.onDelta?.(event.text);
        } else if (typeof event.type === 'string' && event.type.startsWith('trace_')) {
          handlers.onTrace?.(event as unknown as TraceEvent);
        } else if (event.type === 'artifact_created' && event.artifact) {
          handlers.onArtifact?.(event.artifact as ArtifactEvent);
        } else if (event.type === 'open_module' && typeof event.module === 'string' && event.module.trim()) {
          handlers.onOpenModule?.(event.module.trim());
        } else if (event.type === 'done') {
          const tokens = typeof event.tokens === 'number' ? event.tokens : undefined;
          handlers.onDone?.(tokens);
        }
      }
      boundary = buffer.indexOf('\n\n');
    }
  }
  handlers.onDone?.();
}

// ---------------------------------------------------------------------------
// Pending Action Draft (docs/04 Alur 5) — dipakai Approval Card UI #12 fase 2a.
// ---------------------------------------------------------------------------

const DRAFT_API = '/api/method/aios_v1.lib.draft_manager';

export async function fetchPendingDrafts(csrfToken: string): Promise<PendingDraft[]> {
  const raw = unwrapMessage<PendingDraft[]>(
    await apiFetch(`${DRAFT_API}.list_pending_drafts`, {
      headers: { 'X-Frappe-CSRF-Token': csrfToken },
    }),
  );
  if (!Array.isArray(raw)) return [];
  return raw.filter((d) => d && typeof d.name === 'string');
}

export async function fetchDraft(draftId: string, csrfToken: string): Promise<DraftDetail> {
  const raw = unwrapMessage<DraftDetail>(
    await apiFetch(
      `${DRAFT_API}.get_draft?draft_id=${encodeURIComponent(draftId)}`,
      { headers: { 'X-Frappe-CSRF-Token': csrfToken } },
    ),
  );
  if (!raw || typeof raw.name !== 'string') throw new ApiError('Draft tidak ditemukan.');
  return raw;
}

export async function approveDraft(
  draftId: string,
  csrfToken: string,
): Promise<DraftActionResult> {
  const raw = unwrapMessage<DraftActionResult>(
    await apiFetch(`${DRAFT_API}.approve_and_execute_draft`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrfToken },
      body: JSON.stringify({ draft_id: draftId }),
    }),
  );
  return raw ?? {};
}

export async function rejectDraft(
  draftId: string,
  reason: string,
  csrfToken: string,
): Promise<DraftActionResult> {
  const raw = unwrapMessage<DraftActionResult>(
    await apiFetch(`${DRAFT_API}.reject_draft`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrfToken },
      body: JSON.stringify({ draft_id: draftId, reason }),
    }),
  );
  return raw ?? {};
}
