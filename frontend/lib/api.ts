export function getCsrfToken(): string | null {
  if (typeof window === "undefined") return null;
  const w = window as any;
  if (w.csrf_token) return w.csrf_token;
  if (w.frappe?.csrf_token) return w.frappe.csrf_token;
  const match = document.cookie.match(/csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

// Helper API — semua request same-origin via proxy /api (Next rewrites).
export async function api<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const csrfToken = getCsrfToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(csrfToken ? { "X-Frappe-CSRF-Token": csrfToken } : {}),
    ...((init?.headers as Record<string, string>) ?? {}),
  };

  const res = await fetch(`/api${path}`, {
    credentials: "include",
    headers,
    ...init,
  });
  const data = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) {
    const err = new Error(data?.error ?? `HTTP ${res.status}`) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return data;
}

// Pesan login yang aman: 401 selalu generik, tanpa membocorkan email mana yang terdaftar.
export function friendlyAuthError(err: unknown): string {
  const e = err as Error & { status?: number };
  if (e?.status === 401) return "Email atau password salah.";
  return e?.message ?? "Terjadi kesalahan.";
}

// Frappe membungkus return /api/method/* dalam { message: ... }.
export async function apiMethod<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const data = await api<{ message: T }>(path, init);
  return data.message;
}

export function fmtNum(n: number | undefined | null): string {
  return (n ?? 0).toLocaleString("id-ID");
}
