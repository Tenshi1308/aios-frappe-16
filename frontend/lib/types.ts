// Tipe bersama lintas halaman (cermin ringkas bentuk respons server).
export interface Me {
  role: "CLIENT" | "DEVELOPER";
  name: string;
}

export interface BranchInfo {
  key: string;
  name: string;
  tagline: string;
  description: string;
  icon: string;
  enabled: boolean;
  workers: WorkerInfo[];
}

export interface WorkerInfo {
  key: string;
  branch: string;
  jobRole: string;
  description: string;
  relevantEntities: string[];
  exampleQuestions: string[];
  enabled: boolean;
}

export interface MappingEntryView {
  id: number;
  canonicalEntity: string;
  canonicalField: string;
  sourceTable: string;
  sourceColumn: string;
  confidence: number;
  state: string;
  lowConfidence: boolean;
}

export interface MappingView {
  id: number;
  version: number;
  status: string;
  overallConfidence: number;
  notes?: string | null;
  entries: MappingEntryView[];
}

export interface ChatReply {
  conversationId: number;
  reply: string;
  delegatedTo: string | null;
  dataUsed: { entity: string; rowCount: number }[];
  limitation?: string;
}

export interface UsageCompany {
  id: string;
  name: string;
  status: string;
  conversations: number;
  inputTokens: number;
  outputTokens: number;
  costIdr: number;
}

export interface UsageBranch {
  branch: string;
  inputTokens: number;
  outputTokens: number;
  calls: number;
  costIdr: number;
}

export interface UsageWorker {
  workerKey: string;
  inputTokens: number;
  outputTokens: number;
  calls: number;
  costIdr: number;
}
