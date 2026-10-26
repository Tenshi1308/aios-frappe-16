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
  file_id?: string;
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
  file_id?: string;
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
  file_id?: string;
  file_name: string;
  file_url: string;
  file_size: number;
  format: string;
}

export type ModuleColumnFormat = 'text' | 'date' | 'currency' | 'number' | 'boolean';
export type ModuleCardFormat = 'number' | 'currency';
export type ModuleCardScope = 'company' | 'site';
export type ModuleFilterType = 'date' | 'text';
export type ModuleFilterKey = 'date_from' | 'date_to' | 'status' | 'party';

export interface ModuleColumn {
  key: string;
  label: string;
  field: string;
  format: ModuleColumnFormat;
}

export interface ModuleFilterDef {
  key: ModuleFilterKey;
  label: string;
  type: ModuleFilterType;
}

export interface ModuleCardMeta {
  key: string;
  label: string;
  format: ModuleCardFormat;
  scope: ModuleCardScope;
}

export interface ModuleMeta {
  key: string;
  label: string;
  group: string;
  icon: string;
  doctype: string;
  columns: ModuleColumn[];
  filters: ModuleFilterDef[];
  cards: ModuleCardMeta[];
}

export interface ModuleCard extends ModuleCardMeta {
  value: number;
  currency?: string;
}

export type ModuleRowValue = string | number | boolean | null;
export type ModuleRow = Record<string, ModuleRowValue>;

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ModuleDoctypeMeta {
  doctype: string;
  label: string;
  columns: ModuleColumn[];
}

export interface ModuleFilters {
  date_from?: string;
  date_to?: string;
  status?: string;
  party?: string;
}

export interface ModuleDetailData {
  module: ModuleMeta;
  cards: ModuleCard[];
  doctypes: ModuleDoctypeMeta[];
  rows: ModuleRow[];
  pagination: Pagination;
}

export interface ModuleListData {
  module: ModuleMeta;
  doctype: string;
  rows: ModuleRow[];
  pagination: Pagination;
}

export type SearchResult =
  | {
      kind: 'module';
      module: ModuleMeta;
    }
  | {
      kind: 'document';
      module: ModuleMeta;
      doctype: string;
      name: string;
      row: ModuleRow;
    };

export interface BootstrapData {
  user: {
    id: string;
    name: string;
  };
  company: {
    id: string;
    name: string;
    currency: string;
  };
  agents: Branch[];
  modules: ModuleMeta[];
  csrf_token: string;
}

export type SettingsResetSource = 'scheduled' | 'unknown';

export interface SettingsData {
  profile: {
    name: string;
    persona: string | null;
    status: string;
  };
  company: {
    id: string;
    name: string;
    currency: string;
  };
  quota: {
    limit: number;
    used: number;
    remaining: number | null;
    percent_used: number | null;
  };
  reset: {
    at: string | null;
    at_label: string | null;
    seconds_remaining: number | null;
    source: SettingsResetSource;
    scheduler_active: boolean;
  };
}

export interface ModulesApi {
  fetchBootstrap(): Promise<BootstrapData>;
  fetchModule(
    key: string,
    params?: { page?: number; pageSize?: number; filters?: ModuleFilters },
  ): Promise<ModuleDetailData>;
  fetchList(
    key: string,
    doctype: string,
    params?: { page?: number; pageSize?: number; filters?: ModuleFilters },
  ): Promise<ModuleListData>;
  search(q: string, limit?: number): Promise<SearchResult[]>;
  fetchSettings(): Promise<SettingsData>;
}
