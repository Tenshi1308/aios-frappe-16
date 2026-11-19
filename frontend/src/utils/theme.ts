import { ref } from 'vue';
import type { SettingsBrand, SettingsTheme } from '../types';

export const THEME_STORAGE_KEY = 'aios.desk.theme';
export const ALLOWED_THEMES: readonly SettingsTheme[] = ['Automatic', 'Light', 'Dark'];
export const BRAND_STORAGE_KEY = 'aios.desk.brand';
export const DEFAULT_BRAND: SettingsBrand = 'finto';
export const ALLOWED_BRANDS: readonly SettingsBrand[] = ['finto', 'ekasa'];

export const currentBrand = ref<SettingsBrand>(DEFAULT_BRAND);
export const currentTheme = ref<SettingsTheme>('Automatic');
export const systemPrefersDark = ref<boolean>(
  typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)').matches
    : false,
);

export function isSettingsTheme(value: unknown): value is SettingsTheme {
  return value === 'Automatic' || value === 'Light' || value === 'Dark';
}

export function normalizeTheme(value: unknown): SettingsTheme {
  return isSettingsTheme(value) ? value : 'Automatic';
}

export function isSettingsBrand(value: unknown): value is SettingsBrand {
  return value === 'finto' || value === 'ekasa';
}

export function normalizeBrand(value: unknown): SettingsBrand {
  return isSettingsBrand(value) ? value : DEFAULT_BRAND;
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

export function readCachedBrand(): SettingsBrand | null {
  try {
    const raw = window.localStorage.getItem(BRAND_STORAGE_KEY);
    return isSettingsBrand(raw) ? raw : null;
  } catch {
    return null;
  }
}

export function cacheBrand(value: SettingsBrand): void {
  try {
    window.localStorage.setItem(BRAND_STORAGE_KEY, value);
  } catch {
    // localStorage dapat ditolak di mode privat/sandbox browser; diabaikan dengan aman.
  }
}

export function applyTheme(value: SettingsTheme): void {
  const normalized = normalizeTheme(value);
  currentTheme.value = normalized;
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    systemPrefersDark.value = window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
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

export function applyBrand(value: SettingsBrand): void {
  const normalized = normalizeBrand(value);
  currentBrand.value = normalized;
  const root = document.documentElement;
  root.dataset.brand = normalized;
  document.title = normalized === 'finto' ? 'Finto Desk' : 'Ekasa Desk';
  cacheBrand(normalized);
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

export function isDarkEffective(): boolean {
  if (currentTheme.value === 'Light') return false;
  if (currentTheme.value === 'Dark') return true;
  return systemPrefersDark.value;
}
