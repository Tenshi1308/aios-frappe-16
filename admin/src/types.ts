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
  users: DashboardUser[];
  metrics: SiteMetrics | null;
  error: string | null;
}

export interface DashboardTotals {
  sites: number;
  active_users: number;
  total_users: number;
  site_tokens_used: number;
  site_token_limit: number;
  tokens_today: number;
}

export interface DashboardPayload {
  sites: SiteEntry[];
  totals: DashboardTotals;
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
}

export interface SafeErrorPayload {
  success: false;
  error: string;
  code: string;
}
