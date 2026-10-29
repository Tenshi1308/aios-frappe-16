import type {
  AdminTheme,
  DashboardPayload,
  HealthCheckPayload,
  PendingInboxPayload,
  SafeErrorPayload,
  SetUserStatusPayload,
  TotalsPayload,
  UsersPagePayload,
} from './types';

let csrfToken: string | null = null;

function isSafeError(data: unknown): data is SafeErrorPayload {
  return (
    typeof data === 'object' &&
    data !== null &&
    (data as SafeErrorPayload).success === false &&
    typeof (data as SafeErrorPayload).error === 'string'
  );
}

function serverMessage(data: unknown): string | null {
  if (typeof data === 'object' && data !== null && '_server_messages' in data) {
    try {
      const list = JSON.parse(String((data as { _server_messages: unknown })._server_messages));
      if (Array.isArray(list) && list.length) {
        const item = typeof list[0] === 'string' ? JSON.parse(list[0]) : list[0];
        if (item && typeof item.message === 'string' && item.message.trim()) {
          return item.message.replace(/<[^>]*>/g, '').trim();
        }
      }
    } catch {
      return null;
    }
  }
  return null;
}

export class ApiError extends Error {
  code?: string;
  forbidden?: boolean;

  constructor(message: string, options: { code?: string; forbidden?: boolean } = {}) {
    super(message);
    this.code = options.code;
    this.forbidden = options.forbidden ?? false;
  }
}

async function readBody(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, { credentials: 'same-origin', ...init });
  } catch {
    throw new ApiError('Tidak dapat menghubungi server. Periksa koneksi.');
  }
  const data = await readBody(res);
  if (res.status === 403) {
    throw new ApiError('Akses ditolak.', { forbidden: true });
  }
  if (!res.ok) {
    throw new ApiError(serverMessage(data) ?? 'Permintaan gagal.');
  }
  if (isSafeError(data)) {
    throw new ApiError(data.error, { code: data.code });
  }
  if (data && typeof data === 'object' && 'message' in data) {
    return (data as { message: unknown }).message as T;
  }
  return data as T;
}

/** Ambil csrf_token dari sesi Frappe; disimpan di memori saja, tanpa localStorage. */
export async function loadSession(): Promise<void> {
  const data = await request<{ csrf_token?: string }>(
    '/api/method/aios_v1.setup.get_session_context',
  );
  csrfToken = typeof data?.csrf_token === 'string' && data.csrf_token ? data.csrf_token : null;
}

function qs(params: Record<string, string | number | null | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== '') sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export function fetchDashboard(page: number, pageSize = 20): Promise<DashboardPayload> {
  return request<DashboardPayload>(
    `/api/method/aios_v1.api.control_plane.dashboard${qs({ page, page_size: pageSize })}`,
  );
}

export function fetchUsersPage(
  site: string,
  page: number,
  pageSize = 20,
  status?: string | null,
): Promise<UsersPagePayload> {
  return request<UsersPagePayload>(
    `/api/method/aios_v1.api.control_plane.users_page${qs({ site, page, page_size: pageSize, status })}`,
  );
}

export function fetchTotals(): Promise<TotalsPayload> {
  return request<TotalsPayload>('/api/method/aios_v1.api.control_plane.totals');
}

export function fetchPendingInbox(sitePage: number, sitePageSize = 20): Promise<PendingInboxPayload> {
  return request<PendingInboxPayload>(
    `/api/method/aios_v1.api.control_plane.pending_inbox${qs({
      site_page: sitePage,
      site_page_size: sitePageSize,
    })}`,
  );
}

export function checkHealth(site: string): Promise<HealthCheckPayload> {
  return request<HealthCheckPayload>(
    '/api/method/aios_v1.api.control_plane.health_check',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-Frappe-CSRF-Token': csrfToken ?? '',
      },
      body: new URLSearchParams({ site }),
    },
  );
}

export function setUserStatus(site: string, user: string, status: string): Promise<SetUserStatusPayload> {
  return request<SetUserStatusPayload>(
    '/api/method/aios_v1.api.control_plane.set_user_status',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-Frappe-CSRF-Token': csrfToken ?? '',
      },
      body: new URLSearchParams({ site, user, status }),
    },
  );
}

export async function saveTheme(theme: AdminTheme): Promise<void> {
  await request('/api/method/frappe.core.doctype.user.user.switch_theme', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-Frappe-CSRF-Token': csrfToken ?? '',
    },
    body: new URLSearchParams({ theme }),
  });
}
