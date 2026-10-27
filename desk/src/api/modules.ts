import { ApiError, apiFetch, unwrapMessage } from './client';
import type {
  BootstrapData,
  Branch,
  BranchWorker,
  DomainCard,
  DomainDetailData,
  DomainMeta,
  DomainModule,
  ModuleCard,
  ModuleCardFormat,
  ModuleCardMeta,
  ModuleCardScope,
  ModuleColumn,
  ModuleColumnFormat,
  ModuleDetailData,
  ModuleDoctypeMeta,
  ModuleFilterDef,
  ModuleFilterKey,
  ModuleFilters,
  ModuleFilterType,
  ModuleListData,
  ModuleMeta,
  ModuleRow,
  ModuleRowValue,
  ModulesApi,
  Pagination,
  SearchResult,
  SettingsData,
  SettingsResetSource,
  SettingsTheme,
} from '../types';
import { ALLOWED_THEMES, isSettingsTheme, normalizeTheme } from '../utils/theme';

const DESKTOP_API = '/api/method/aios_v1.api.desktop';
const SWITCH_THEME_API = '/api/method/frappe.core.doctype.user.user.switch_theme';

const ALLOWED_FILTER_KEYS: ReadonlySet<ModuleFilterKey> = new Set([
  'date_from',
  'date_to',
  'status',
  'party',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function asColumnFormat(value: unknown): ModuleColumnFormat {
  if (
    value === 'text' ||
    value === 'date' ||
    value === 'currency' ||
    value === 'number' ||
    value === 'boolean'
  ) {
    return value;
  }
  return 'text';
}

function asCardFormat(value: unknown): ModuleCardFormat {
  return value === 'currency' ? 'currency' : 'number';
}

function asCardScope(value: unknown): ModuleCardScope {
  return value === 'site' ? 'site' : 'company';
}

function asFilterType(value: unknown): ModuleFilterType {
  return value === 'date' ? 'date' : 'text';
}

function mapColumns(raw: unknown): ModuleColumn[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(isRecord)
    .filter((c) => typeof c.key === 'string' && !!c.key && typeof c.field === 'string' && !!c.field)
    .map((c) => ({
      key: c.key as string,
      label: asString(c.label, c.key as string),
      field: c.field as string,
      format: asColumnFormat(c.format),
    }));
}

function mapFilters(raw: unknown): ModuleFilterDef[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(isRecord)
    .filter(
      (f): f is Record<string, unknown> & { key: ModuleFilterKey } =>
        typeof f.key === 'string' && ALLOWED_FILTER_KEYS.has(f.key as ModuleFilterKey),
    )
    .map((f) => ({
      key: f.key,
      label: asString(f.label, f.key),
      type: asFilterType(f.type),
    }));
}

function mapCardMetas(raw: unknown): ModuleCardMeta[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(isRecord)
    .filter((c) => typeof c.key === 'string' && !!c.key)
    .map((c) => ({
      key: c.key as string,
      label: asString(c.label, c.key as string),
      format: asCardFormat(c.format),
      scope: asCardScope(c.scope),
    }));
}

function mapDomainMeta(raw: unknown): DomainMeta | null {
  if (!isRecord(raw)) return null;
  if (typeof raw.key !== 'string' || !raw.key) return null;
  return {
    key: raw.key,
    label: asString(raw.label, raw.key),
    icon: asString(raw.icon, 'tag'),
    color_token: asString(raw.color_token, `domain-${raw.key}`),
    module_count: Math.max(0, Math.trunc(asNumber(raw.module_count, 0))),
  };
}

function mapDomainCard(raw: unknown): DomainCard | null {
  if (!isRecord(raw)) return null;
  if (typeof raw.key !== 'string' || !raw.key) return null;
  const format: 'number' | 'currency' = raw.format === 'currency' ? 'currency' : 'number';
  const card: DomainCard = {
    key: raw.key,
    label: asString(raw.label, raw.key),
    value: asNumber(raw.value, 0),
    format,
  };
  if (typeof raw.currency === 'string' && raw.currency.trim()) {
    card.currency = raw.currency.trim();
  }
  return card;
}

function mapDomainModule(raw: unknown): DomainModule | null {
  if (!isRecord(raw)) return null;
  if (typeof raw.key !== 'string' || !raw.key) return null;
  return {
    key: raw.key,
    label: asString(raw.label, raw.key),
    icon: asString(raw.icon, 'file'),
    row_count: Math.max(0, Math.trunc(asNumber(raw.row_count, 0))),
  };
}

function mapModuleMeta(raw: unknown): ModuleMeta | null {
  if (!isRecord(raw)) return null;
  if (typeof raw.key !== 'string' || !raw.key || typeof raw.doctype !== 'string' || !raw.doctype) {
    return null;
  }
  return {
    key: raw.key,
    label: asString(raw.label, raw.key),
    group: asString(raw.group),
    icon: asString(raw.icon, 'file'),
    doctype: raw.doctype,
    columns: mapColumns(raw.columns),
    filters: mapFilters(raw.filters),
    cards: mapCardMetas(raw.cards),
  };
}

function mapCards(raw: unknown): ModuleCard[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(isRecord)
    .filter((c) => typeof c.key === 'string' && !!c.key)
    .map((c) => {
      const card: ModuleCard = {
        key: c.key as string,
        label: asString(c.label, c.key as string),
        value: asNumber(c.value, 0),
        format: asCardFormat(c.format),
        scope: asCardScope(c.scope),
      };
      if (typeof c.currency === 'string' && c.currency.trim()) {
        card.currency = c.currency;
      }
      return card;
    });
}

function mapRow(raw: unknown, allowedFields?: ReadonlySet<string>): ModuleRow | null {
  if (!isRecord(raw)) return null;
  const row: ModuleRow = {};
  for (const [k, v] of Object.entries(raw)) {
    if (allowedFields && allowedFields.size > 0 && !allowedFields.has(k)) continue;
    if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean' || v === null) {
      row[k] = v as ModuleRowValue;
    } else if (typeof v === 'undefined') {
      row[k] = null;
    } else {
      row[k] = String(v);
    }
  }
  return row;
}

function mapRows(raw: unknown, columns: ModuleColumn[]): ModuleRow[] {
  if (!Array.isArray(raw)) return [];
  const allowed = new Set(columns.map((c) => c.field));
  allowed.add('name');
  return raw
    .map((item) => mapRow(item, allowed))
    .filter((item): item is ModuleRow => item !== null);
}

function mapPagination(raw: unknown): Pagination {
  if (!isRecord(raw)) {
    return { page: 1, page_size: 25, total: 0, total_pages: 0 };
  }
  return {
    page: Math.max(1, Math.trunc(asNumber(raw.page, 1))),
    page_size: Math.max(1, Math.trunc(asNumber(raw.page_size, 25))),
    total: Math.max(0, Math.trunc(asNumber(raw.total, 0))),
    total_pages: Math.max(0, Math.trunc(asNumber(raw.total_pages, 0))),
  };
}

function mapDoctypes(raw: unknown, fallback: ModuleMeta): ModuleDoctypeMeta[] {
  if (!Array.isArray(raw)) {
    return [{ doctype: fallback.doctype, label: fallback.label, columns: fallback.columns }];
  }
  const list = raw
    .filter(isRecord)
    .filter((d) => typeof d.doctype === 'string' && !!d.doctype)
    .map((d) => ({
      doctype: d.doctype as string,
      label: asString(d.label, d.doctype as string),
      columns: mapColumns(d.columns),
    }));
  return list.length
    ? list
    : [{ doctype: fallback.doctype, label: fallback.label, columns: fallback.columns }];
}

function mapWorkers(raw: unknown): BranchWorker[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(isRecord)
    .filter((w) => typeof w.key === 'string' && !!w.key)
    .map((w) => ({
      key: w.key as string,
      jobRole: asString(w.jobRole, w.key as string),
      exampleQuestions: Array.isArray(w.exampleQuestions)
        ? w.exampleQuestions.filter((q): q is string => typeof q === 'string' && !!q.trim())
        : [],
    }));
}

function mapBranches(raw: unknown): Branch[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(isRecord)
    .filter((b) => typeof b.key === 'string' && !!b.key)
    .map((b) => ({
      key: b.key as string,
      name: asString(b.name, b.key as string),
      description: asString(b.description),
      tagline: asString(b.tagline),
      workers: mapWorkers(b.workers),
    }));
}

function cleanFilters(filters?: ModuleFilters): Record<string, string> {
  const out: Record<string, string> = {};
  if (!filters) return out;
  for (const key of ALLOWED_FILTER_KEYS) {
    const val = filters[key];
    if (typeof val === 'string' && val.trim()) {
      out[key] = val.trim();
    }
  }
  return out;
}

export async function fetchBootstrap(): Promise<BootstrapData> {
  const raw = unwrapMessage<unknown>(await apiFetch(`${DESKTOP_API}.bootstrap`));
  if (!isRecord(raw) || !isRecord(raw.user) || !isRecord(raw.company)) {
    throw new ApiError('Data bootstrap desktop tidak valid.');
  }
  const userId = asString(raw.user.id);
  const companyId = asString(raw.company.id);
  const currency = asString(raw.company.currency);
  const csrfToken = asString(raw.csrf_token);
  if (!userId || !companyId || !currency || !csrfToken) {
    throw new ApiError('Data bootstrap desktop tidak lengkap.');
  }
  const domains = Array.isArray(raw.domains)
    ? raw.domains.map(mapDomainMeta).filter((d): d is DomainMeta => d !== null)
    : [];
  const modules = Array.isArray(raw.modules)
    ? raw.modules.map(mapModuleMeta).filter((m): m is ModuleMeta => m !== null)
    : [];
  return {
    user: {
      id: userId,
      name: asString(raw.user.name, userId),
    },
    company: {
      id: companyId,
      name: asString(raw.company.name, companyId),
      currency,
    },
    agents: mapBranches(raw.agents),
    domains,
    modules,
    csrf_token: csrfToken,
  };
}

export async function fetchDomain(key: string): Promise<DomainDetailData> {
  const qs = new URLSearchParams({ domain: key });
  const raw = unwrapMessage<unknown>(await apiFetch(`${DESKTOP_API}.domain?${qs.toString()}`));
  if (!isRecord(raw) || !isRecord(raw.domain) || !isRecord(raw.company)) {
    throw new ApiError('Respons bidang tidak valid.');
  }
  const domKey = asString(raw.domain.key);
  if (!domKey) {
    throw new ApiError('Definisi bidang tidak valid.');
  }
  const modulesList = Array.isArray(raw.modules)
    ? raw.modules.map(mapDomainModule).filter((m): m is DomainModule => m !== null)
    : [];
  const cardsList = Array.isArray(raw.cards)
    ? raw.cards.map(mapDomainCard).filter((c): c is DomainCard => c !== null)
    : [];
  const domainMeta: DomainMeta = {
    key: domKey,
    label: asString(raw.domain.label, domKey),
    icon: asString(raw.domain.icon, 'tag'),
    color_token: asString(raw.domain.color_token, `domain-${domKey}`),
    module_count:
      typeof raw.domain.module_count === 'number'
        ? Math.max(0, Math.trunc(asNumber(raw.domain.module_count, 0)))
        : modulesList.length,
  };
  return {
    domain: domainMeta,
    company: {
      id: asString(raw.company.id),
      name: asString(raw.company.name, asString(raw.company.id)),
      currency: asString(raw.company.currency),
    },
    cards: cardsList,
    modules: modulesList,
  };
}

export async function fetchModule(
  key: string,
  params: { page?: number; pageSize?: number; filters?: ModuleFilters } = {},
): Promise<ModuleDetailData> {
  const qs = new URLSearchParams();
  qs.set('module', key);
  if (params.page && params.page > 0) qs.set('page', String(params.page));
  if (params.pageSize && params.pageSize > 0) qs.set('page_size', String(params.pageSize));
  const cleaned = cleanFilters(params.filters);
  if (Object.keys(cleaned).length > 0) {
    qs.set('filters', JSON.stringify(cleaned));
  }
  const raw = unwrapMessage<unknown>(await apiFetch(`${DESKTOP_API}.module?${qs.toString()}`));
  if (!isRecord(raw)) {
    throw new ApiError('Respons modul tidak valid.');
  }
  const mod = mapModuleMeta(raw.module);
  if (!mod) {
    throw new ApiError('Definisi modul tidak valid.');
  }
  const doctypes = mapDoctypes(raw.doctypes, mod);
  const columns = doctypes[0]?.columns.length ? doctypes[0].columns : mod.columns;
  return {
    module: mod,
    cards: mapCards(raw.cards),
    doctypes,
    rows: mapRows(raw.rows, columns),
    pagination: mapPagination(raw.pagination),
  };
}

export async function fetchList(
  key: string,
  doctype: string,
  params: { page?: number; pageSize?: number; filters?: ModuleFilters } = {},
): Promise<ModuleListData> {
  const qs = new URLSearchParams();
  qs.set('module', key);
  qs.set('doctype', doctype);
  if (params.page && params.page > 0) qs.set('page', String(params.page));
  if (params.pageSize && params.pageSize > 0) qs.set('page_size', String(params.pageSize));
  const cleaned = cleanFilters(params.filters);
  if (Object.keys(cleaned).length > 0) {
    qs.set('filters', JSON.stringify(cleaned));
  }
  const raw = unwrapMessage<unknown>(await apiFetch(`${DESKTOP_API}.list?${qs.toString()}`));
  if (!isRecord(raw)) {
    throw new ApiError('Respons daftar dokumen tidak valid.');
  }
  const mod = mapModuleMeta(raw.module);
  if (!mod || typeof raw.doctype !== 'string' || !raw.doctype) {
    throw new ApiError('Data daftar dokumen tidak valid.');
  }
  return {
    module: mod,
    doctype: raw.doctype,
    rows: mapRows(raw.rows, mod.columns),
    pagination: mapPagination(raw.pagination),
  };
}

export async function search(q: string, limit?: number): Promise<SearchResult[]> {
  const trimmed = q.trim();
  if (!trimmed) return [];
  const qs = new URLSearchParams({ q: trimmed });
  if (limit && limit > 0) qs.set('limit', String(limit));
  const raw = unwrapMessage<unknown>(await apiFetch(`${DESKTOP_API}.search?${qs.toString()}`));
  if (!isRecord(raw) || !Array.isArray(raw.results)) return [];
  const out: SearchResult[] = [];
  for (const item of raw.results) {
    if (!isRecord(item)) continue;
    const kind = item.kind ?? item.type;
    const mod = mapModuleMeta(item.module);
    if (!mod) continue;
    if (kind === 'module') {
      out.push({ kind: 'module', module: mod });
    } else if (kind === 'document' && typeof item.doctype === 'string' && !!item.doctype) {
      const row = mapRow(item.row, new Set(mod.columns.map((c) => c.field))) ?? {};
      const name = asString(item.name, typeof row.name === 'string' ? row.name : '');
      if (!name) continue;
      out.push({
        kind: 'document',
        module: mod,
        doctype: item.doctype,
        name,
        row,
      });
    }
  }
  return out;
}

function asNullableNumber(value: unknown): number | null {
  if (value === null || typeof value === 'undefined') return null;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function asResetSource(value: unknown): SettingsResetSource {
  return value === 'scheduled' ? 'scheduled' : 'unknown';
}

export async function fetchSettings(): Promise<SettingsData> {
  const raw = unwrapMessage<unknown>(await apiFetch(`${DESKTOP_API}.settings`));
  if (
    !isRecord(raw) ||
    !isRecord(raw.profile) ||
    !isRecord(raw.company) ||
    !isRecord(raw.quota) ||
    !isRecord(raw.reset)
  ) {
    throw new ApiError('Data pengaturan desktop tidak valid.');
  }

  const profileName = asString(raw.profile.name);
  const profileStatus = asString(raw.profile.status);
  const companyId = asString(raw.company.id);
  const companyCurrency = asString(raw.company.currency);
  if (!profileName || !companyId || !companyCurrency) {
    throw new ApiError('Data pengaturan desktop tidak lengkap.');
  }

  const personaRaw = asString(raw.profile.persona);
  const limit = Math.max(0, Math.trunc(asNumber(raw.quota.limit, 0)));
  const used = Math.max(0, Math.trunc(asNumber(raw.quota.used, 0)));
  const remainingRaw = asNullableNumber(raw.quota.remaining);
  const percentRaw = asNullableNumber(raw.quota.percent_used);

  const atRaw = asString(raw.reset.at);
  const atLabelRaw = asString(raw.reset.at_label);
  const secondsRaw = asNullableNumber(raw.reset.seconds_remaining);

  const themeRecord = isRecord(raw.theme) ? raw.theme : null;
  const themeValue = normalizeTheme(themeRecord?.value);
  const rawOptions = Array.isArray(themeRecord?.options)
    ? themeRecord.options.filter(isSettingsTheme)
    : [];
  const themeOptions: SettingsTheme[] = rawOptions.length > 0 ? rawOptions : [...ALLOWED_THEMES];

  return {
    profile: {
      name: profileName,
      persona: personaRaw || null,
      status: profileStatus,
    },
    company: {
      id: companyId,
      name: asString(raw.company.name, companyId),
      currency: companyCurrency,
    },
    quota: {
      limit,
      used,
      remaining: remainingRaw === null ? null : Math.max(0, Math.trunc(remainingRaw)),
      percent_used: percentRaw,
    },
    reset: {
      at: atRaw || null,
      at_label: atLabelRaw || null,
      seconds_remaining: secondsRaw === null ? null : Math.max(0, Math.trunc(secondsRaw)),
      source: asResetSource(raw.reset.source),
      scheduler_active: Boolean(raw.reset.scheduler_active),
    },
    theme: {
      value: themeValue,
      options: themeOptions,
    },
  };
}

export async function saveTheme(theme: SettingsTheme, csrfToken: string): Promise<void> {
  await apiFetch(SWITCH_THEME_API, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Frappe-CSRF-Token': csrfToken,
    },
    body: JSON.stringify({ theme }),
  });
}

export const modulesApi = {
  fetchBootstrap,
  fetchDomain,
  fetchModule,
  fetchList,
  search,
  fetchSettings,
  saveTheme,
} satisfies ModulesApi;
