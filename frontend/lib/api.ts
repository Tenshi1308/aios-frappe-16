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
  if (!res.ok) throw new Error(data?.error ?? `HTTP ${res.status}`);
  return data;
}

export function fmtNum(n: number | undefined | null): string {
  return (n ?? 0).toLocaleString("id-ID");
}
