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

interface RawThreads {
  threads?: ChannelThread[];
}

interface RawFlags {
  flags?: ChannelFlag[];
}

export async function fetchThreads(): Promise<ChannelThread[]> {
  const data = await apiFetch('/api/connector/threads');
  return (data as RawThreads)?.threads ?? [];
}

export async function fetchFlags(status?: 'Open' | 'Closed'): Promise<ChannelFlag[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : '';
  const data = await apiFetch(`/api/connector/flags${query}`);
  return (data as RawFlags)?.flags ?? [];
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
