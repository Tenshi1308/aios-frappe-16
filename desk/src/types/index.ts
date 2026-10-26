export interface SessionContext {
  user: string;
  full_name: string | null;
  roles: string[];
  aios_persona: string | null;
  aios_status: string | null;
  aios_company_name: string | null;
  company: string | null;
  csrf_token: string;
}

export interface BranchWorker {
  key: string;
  jobRole: string;
  exampleQuestions: string[];
}

export interface Branch {
  key: string;
  name: string;
  description: string;
  tagline: string;
  workers: BranchWorker[];
}

export interface ConversationItem {
  id: string;
  title: string;
  updatedAt: string;
}

export interface FileEntry {
  conversation_id: string;
  conversation_title: string;
  branch: string;
  file_name: string;
  file_url: string;
  file_size: number;
  format: string;
  creation: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'agent';
  text: string;
  /** True saat jawaban masih di-stream; blok trace tampil live di atas bubble. */
  live?: boolean;
  steps?: TraceEvent[];
  /** performance.now() saat tiap event trace diterima klien (durasi per item). */
  stepTimes?: number[];
  /** performance.now() saat turn dimulai (header "Working for …"). */
  startedAt?: number;
  tokens?: number;
  durationMs?: number;
  artifacts?: ArtifactEvent[];
}

/** Cermin payload event trace di `aios_v1/shared/trace_events.py` (dokumen docs/02 §3.1). */
export type TraceEvent =
  | { type: 'trace_delegate_start'; from: string; to: string; instruction: string; branch: string }
  | {
      type: 'trace_subagent_prompt';
      agent: string;
      system_prompt_summary: string;
      task_prompt: string;
      branch: string;
    }
  | {
      type: 'trace_subagent_tool';
      agent: string;
      tool: string;
      args: Record<string, unknown>;
      branch: string;
    }
  | {
      type: 'trace_subagent_result';
      agent: string;
      status: string;
      summary: string;
      usage: Record<string, unknown>;
      duration_ms: number;
      branch: string;
    }
  | { type: 'trace_cross_branch'; from_branch?: string; to_branch?: string; payload?: unknown; result?: unknown };

export interface ApprovalCardArtifact {
  type: 'APPROVAL_CARD';
  draft_id: string;
  action_type: string;
  doctype: string;
  branch: string;
}

export interface FileArtifact {
  type: 'FILE';
  file_name: string;
  file_url: string;
  format: string;
  size: number;
  conversation_id: string;
}

export type ArtifactEvent = ApprovalCardArtifact | FileArtifact;

export interface PendingDraft {
  name: string;
  type: string;
  branch: string | null;
  status: string;
  expires_at: string;
  creation: string;
}

/** Hasil `get_draft` — `payload` adalah string JSON yang di-parse UI. */
export interface DraftDetail {
  name: string;
  type: string;
  branch: string | null;
  status: string;
  payload: string;
  created_by_agent: string | null;
  rejection_reason: string | null;
  expires_at: string;
}

export interface DraftActionResult {
  status?: string;
  draft_status?: string;
  executed?: boolean;
  code?: string;
  message?: string;
  document?: string;
}

export interface AttachmentMeta {
  id: string;
  file_name: string;
  file_size: number;
  format: string;
}
