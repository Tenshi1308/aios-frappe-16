import { ApiError, apiFetch, unwrapMessage } from './client';
import type {
  BootstrapData,
  Branch,
  BranchWorker,
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
  Pagination,
  SearchResult,
} from '../types';

const DESKTOP_API = '/api/method/aios_v1.api.desktop';

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
    modules,
    csrf_token: csrfToken,
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
