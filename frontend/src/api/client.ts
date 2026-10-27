export class ApiError extends Error {
  code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.code = code;
  }
}

function errorText(data: unknown): string | null {
  if (data && typeof data === 'object' && 'error' in data) {
    const value = (data as { error?: unknown }).error;
    if (typeof value === 'string' && value.trim()) return value;
  }
  return null;
}

/** Pesan aman dari body Frappe (_server_messages) tanpa detail internal.
 *  Pesan server kadang dibungkus tag HTML (mis. div Frappe) — dibersihkan
 *  menjadi teks polos sebelum ditampilkan. */
function serverMessage(data: unknown): string | null {
  if (data && typeof data === 'object' && '_server_messages' in data) {
    try {
      const list = JSON.parse(String((data as { _server_messages: unknown })._server_messages));
      if (Array.isArray(list) && list.length) {
        const item = typeof list[0] === 'string' ? JSON.parse(list[0]) : list[0];
        if (item && typeof item.message === 'string' && item.message.trim()) {
          return item.message
            .replace(/<[^>]*>/g, '')
            .replace(/&quot;/g, '"')
            .replace(/&#39;/g, "'")
            .replace(/&amp;/g, '&')
            .trim();
        }
      }
    } catch {
      return null;
    }
  }
  return null;
}

function safeMessage(data: unknown, fallback: string): string {
  return errorText(data) ?? serverMessage(data) ?? fallback;
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

export async function apiFetch(url: string, init: RequestInit = {}): Promise<unknown> {
  let res: Response;
  try {
    res = await fetch(url, { credentials: 'same-origin', ...init });
  } catch {
    throw new ApiError('Tidak dapat menghubungi server. Periksa koneksi.');
  }
  const data = await readBody(res);
  if (!res.ok) throw new ApiError(safeMessage(data, 'Permintaan gagal.'));
  if (data && typeof data === 'object' && (data as { success?: unknown }).success === false) {
    const body = data as { error?: unknown; code?: unknown };
    throw new ApiError(
      typeof body.error === 'string' && body.error ? body.error : 'Permintaan gagal.',
      typeof body.code === 'string' ? body.code : undefined,
    );
  }
  return data;
}

export function unwrapMessage<T>(data: unknown): T | null {
  if (data && typeof data === 'object' && 'message' in data) {
    return (data as { message: T }).message;
  }
  return (data as T) ?? null;
}

export interface ClientErrorPayload {
  message: string;
  context?: string;
  stack?: string;
}

export async function reportClientError(
  payload: ClientErrorPayload,
  csrfToken?: string,
): Promise<boolean> {
  try {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (csrfToken) {
      headers['X-Frappe-CSRF-Token'] = csrfToken;
    }
    const res = await fetch('/api/method/aios_v1.api.desktop.log_client_error', {
      method: 'POST',
      credentials: 'same-origin',
      headers,
      body: JSON.stringify({
        message: payload.message,
        context: payload.context ?? '',
        stack: payload.stack ?? '',
      }),
    });
    return res.ok;
  } catch (err) {
    console.warn('Gagal melaporkan error klien ke server:', err);
    return false;
  }
}

