import { ApiError, apiFetch, unwrapMessage } from './client';
import type { SessionContext } from '../types';

export async function fetchSessionContext(): Promise<SessionContext> {
  const ctx = unwrapMessage<SessionContext>(await apiFetch('/api/method/aios_v1.setup.get_session_context'));
  if (!ctx || typeof ctx.csrf_token !== 'string' || !ctx.csrf_token) {
    throw new ApiError('Sesi tidak valid. Silakan masuk kembali.');
  }
  return ctx;
}

export async function login(usr: string, pwd: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch('/api/method/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ usr, pwd }).toString(),
    });
  } catch {
    throw new ApiError('Tidak dapat menghubungi server. Periksa koneksi.');
  }
  if (!res.ok) throw new ApiError('Email atau password salah.');
}

export async function logout(): Promise<void> {
  await apiFetch('/api/auth/logout', { method: 'POST' });
}

export type RegistrationStatus = 'PENDING_PROVISIONING';

export interface RegisterPayload {
  full_name: string;
  email: string;
  company_name: string;
  country: string;
}

export async function listCountries(): Promise<string[]> {
  const raw = await apiFetch('/api/method/aios_v1.auth.list_countries');
  const countries = unwrapMessage<string[]>(raw);
  return Array.isArray(countries) ? countries : [];
}

export async function registerAccount(payload: RegisterPayload): Promise<RegistrationStatus> {
  const raw = await apiFetch('/api/method/aios_v1.auth.register_account', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const status = unwrapMessage<{ status?: string }>(raw)?.status;
  if (status !== 'PENDING_PROVISIONING') {
    throw new ApiError('Respons pendaftaran tidak dikenal.');
  }
  return status;
}
