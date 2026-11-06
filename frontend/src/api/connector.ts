import { ApiError, apiFetch } from './client';

/** Channel connector surface (docs/02 §2.4). Read-only threads + flag review. */

export interface ChannelThread {
  name: string;
  channel: string;
  external_thread_id: string;
  conversation: string;
  display_name?: string;
  username?: string;
  party_type?: string;
  party?: string;
  status: string;
  linked_user?: string;
  linked_at?: string;
  last_inbound_at?: string;
  last_outbound_at?: string;
}

export interface ChannelFlag {
  name: string;
  thread: string;
  conversation?: string;
  rule_key: string;
  severity: 'low' | 'medium' | 'high';
  status: 'Open' | 'Closed';
  label?: string;
  excerpt?: string;
  message_ids?: string;
  reason_text?: string;
  creation?: string;
  closed_by?: string;
  closed_at?: string;
  closing_note?: string;
}

export interface ChannelOrderNotification {
  name: string;
  draft_id: string;
  doctype: string;
  customer_name: string;
  subject: string;
  creation: string;
  read: number;
}

interface RawThreads {
  threads?: ChannelThread[];
}

export interface FlagListResponse {
  flags: ChannelFlag[];
  total: number;
}

interface RawFlags {
  flags?: ChannelFlag[];
  total?: number;
}

export interface OrderListResponse {
  orders: ChannelOrderNotification[];
  total: number;
  page: number;
  page_length: number;
  total_pages: number;
}

interface RawOrders {
  orders?: ChannelOrderNotification[];
  total?: number;
  page?: number;
  page_length?: number;
  total_pages?: number;
}

export async function fetchThreads(): Promise<ChannelThread[]> {
  const data = await apiFetch('/api/connector/threads');
  return (data as RawThreads)?.threads ?? [];
}

export async function fetchFlags(status?: 'Open' | 'Closed'): Promise<FlagListResponse> {
  const query = status ? `?status=${encodeURIComponent(status)}` : '';
  const data = (await apiFetch(`/api/connector/flags${query}`)) as RawFlags;
  const flags = data?.flags ?? [];
  const total = typeof data?.total === 'number' ? data.total : (flags.length || 0);
  return {
    flags,
    total,
  };
}

export async function fetchOrderNotifications(
  unreadOnly = true,
  page = 1,
): Promise<OrderListResponse> {
  const unreadParam = unreadOnly ? 'unread=1' : 'unread=0';
  const query = `?${unreadParam}&page=${encodeURIComponent(page)}`;
  const data = (await apiFetch(`/api/connector/orders${query}`)) as RawOrders;
  const orders = data?.orders ?? [];
  const total = typeof data?.total === 'number' ? data.total : (orders.length || 0);
  const total_pages = typeof data?.total_pages === 'number' ? data.total_pages : (Math.ceil(total / 20) || 1);
  const resPage = typeof data?.page === 'number' ? data.page : page;
  const page_length = typeof data?.page_length === 'number' ? data.page_length : 20;

  return {
    orders,
    total,
    page: resPage,
    page_length,
    total_pages,
  };
}

export async function reviewOrderNotification(
  notificationId: string,
  csrfToken: string,
): Promise<{ success: boolean }> {
  if (!notificationId) throw new ApiError('Notifikasi wajib dipilih.');
  const data = await apiFetch('/api/connector/order/review', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Frappe-CSRF-Token': csrfToken,
    },
    body: JSON.stringify({ notification_id: notificationId }),
  });
  return (data as { success: boolean }) ?? { success: false };
}

export async function closeFlag(
  flag: string,
  note: string,
  csrfToken: string,
): Promise<{ status: string }> {
  if (!flag) throw new ApiError('Flag wajib dipilih.');
  const data = await apiFetch('/api/connector/flag/close', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Frappe-CSRF-Token': csrfToken,
    },
    body: JSON.stringify({ flag, note }),
  });
  const status = (data as { status?: unknown })?.status;
  return { status: typeof status === 'string' ? status : 'Closed' };
}

export interface TelegramLinkStatus {
  linked: boolean;
  external_thread_id?: string;
  telegram_username?: string;
  display_name?: string;
  linked_at?: string;
}

export async function fetchTelegramStatus(): Promise<TelegramLinkStatus> {
  const data = await apiFetch('/api/connector/link-status');
  return (data as TelegramLinkStatus) ?? { linked: false };
}

export async function createTelegramLinkToken(csrfToken: string): Promise<{ deep_link: string; expires_in_seconds: number }> {
  const data = await apiFetch('/api/connector/link-token', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Frappe-CSRF-Token': csrfToken,
    },
    body: JSON.stringify({}),
  });
  return data as { deep_link: string; expires_in_seconds: number };
}

export async function unlinkTelegramAccount(csrfToken: string): Promise<{ success: boolean }> {
  const data = await apiFetch('/api/connector/unlink', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Frappe-CSRF-Token': csrfToken,
    },
    body: JSON.stringify({}),
  });
  return data as { success: boolean };
}
