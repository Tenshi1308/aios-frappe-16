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

export interface ChatMessage {
  role: 'user' | 'agent';
  text: string;
}

export interface AttachmentMeta {
  id: string;
  file_name: string;
  file_size: number;
  format: string;
}
