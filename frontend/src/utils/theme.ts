import type { SettingsTheme } from '../types';

export const THEME_STORAGE_KEY = 'aios.desk.theme';
export const ALLOWED_THEMES: readonly SettingsTheme[] = ['Automatic', 'Light', 'Dark'];

export function isSettingsTheme(value: unknown): value is SettingsTheme {
  return value === 'Automatic' || value === 'Light' || value === 'Dark';
}

export function normalizeTheme(value: unknown): SettingsTheme {
  return isSettingsTheme(value) ? value : 'Automatic';
}

export function readCachedTheme(): SettingsTheme | null {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isSettingsTheme(raw) ? raw : null;
  } catch {
    return null;
  }
}

export function cacheTheme(value: SettingsTheme): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, value);
  } catch {
    // localStorage dapat ditolak di mode privat/sandbox browser; diabaikan dengan aman.
  }
}

export function applyTheme(value: SettingsTheme): void {
  const normalized = normalizeTheme(value);
  const root = document.documentElement;
  if (normalized === 'Light') {
    root.dataset.theme = 'light';
  } else if (normalized === 'Dark') {
    root.dataset.theme = 'dark';
  } else {
    delete root.dataset.theme;
  }
  cacheTheme(normalized);
}

export function resolveTheme(value: SettingsTheme): 'light' | 'dark' {
  const normalized = normalizeTheme(value);
  if (normalized === 'Light') return 'light';
  if (normalized === 'Dark') return 'dark';
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return 'light';
}
