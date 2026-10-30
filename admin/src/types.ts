// Tipe payload dashboard. Sumber kebenaran: aios_v1.api.control_plane.

export type SiteStatus = 'Provisioning' | 'Active' | 'Suspended' | 'Decommissioned';

export interface DashboardUser {
  name: string;
  full_name: string | null;
  aios_status: string | null;
  aios_persona: string | null;
  enabled: 0 | 1;
  last_login: string | null;
}

export interface SiteMetrics {
  site_tokens_used: number;
  site_token_limit: number;
  active_users: number;
  total_users: number;
  pending_users: number;
  tokens_today: number;
}

export interface SiteEntry {
  site_name: string;
  base_url: string;
  company_name: string | null;
  contact_name: string | null;
  contact_email: string | null;
  status: SiteStatus | null;
  last_seen: string | null;
  last_error: string | null;
  metrics: SiteMetrics | null;
  error: string | null;
}

export interface DashboardTotals {
  sites: number;
  active_users: number;
  total_users: number;
  pending_users: number;
  site_tokens_used: number;
  site_token_limit: number;
  tokens_today: number;
}

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export type AdminTheme = 'Automatic' | 'Light' | 'Dark';

export interface ThemePayload {
  value: AdminTheme;
  options: AdminTheme[];
}

export interface DashboardPayload {
  sites: SiteEntry[];
  pagination: Pagination;
  theme: ThemePayload;
}

export interface UsersPagePayload {
  site: string;
  users: DashboardUser[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  error: string | null;
}

export interface TotalsPayload {
  totals: DashboardTotals & { sites_unreachable: number };
  sites_total: number;
  sites_scanned: number;
}

export interface PendingInboxPayload {
  site_page: number;
  site_page_size: number;
  sites_total: number;
  sites_scanned: number;
  total_pending: number;
  entries: Array<{ site: string; pending_users: number; users: DashboardUser[] }>;
  partial: boolean;
  error: string | null;
}

export interface HealthCheckPayload {
  ok: boolean;
  site: string;
  last_seen: string | null;
  last_error: string | null;
}

export interface SetUserStatusPayload {
  ok: boolean;
  site: string;
  user: string;
  aios_status: string | null;
  invitation_url?: string | null;
}

export interface SignupLead {
  name: string;
  lead_name: string;
  first_name: string;
  email_id: string;
  company_name: string;
  country: string;
  creation: string;
  status?: string;
  site_name?: string | null;
}

export interface SafeErrorPayload {
  success: false;
  error: string;
  code: string;
}
