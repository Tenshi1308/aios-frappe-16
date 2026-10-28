import type {
  DashboardPayload,
  HealthCheckPayload,
  SafeErrorPayload,
  SetUserStatusPayload,
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

export function fetchDashboard(): Promise<DashboardPayload> {
  return request<DashboardPayload>('/api/method/aios_v1.api.control_plane.dashboard');
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
