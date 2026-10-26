import type {
  BootstrapData,
  ModuleDetailData,
  ModuleFilters,
  ModuleListData,
  ModuleMeta,
  ModulesApi,
  SearchResult,
  SettingsData,
  SettingsTheme,
} from '../../types';
import { ALLOWED_THEMES, normalizeTheme } from '../../utils/theme';

let mockThemeValue: SettingsTheme = 'Automatic';

const MOCK_MODULES: ModuleMeta[] = [
  {
    key: 'sales_invoice',
    label: 'Sales Invoice',
    group: 'Sales',
    icon: 'file',
    doctype: 'Sales Invoice',
    columns: [
      { key: 'name', label: 'Nomor', field: 'name', format: 'text' },
      { key: 'posting_date', label: 'Tanggal', field: 'posting_date', format: 'date' },
      { key: 'customer', label: 'Customer', field: 'customer', format: 'text' },
      { key: 'status', label: 'Status', field: 'status', format: 'text' },
      { key: 'base_grand_total', label: 'Total', field: 'base_grand_total', format: 'currency' },
    ],
    filters: [
      { key: 'date_from', label: 'Dari tanggal', type: 'date' },
      { key: 'date_to', label: 'Sampai tanggal', type: 'date' },
      { key: 'status', label: 'Status', type: 'text' },
      { key: 'party', label: 'Customer', type: 'text' },
    ],
    cards: [
      { key: 'submitted_count', label: 'Invoice disetujui', format: 'number', scope: 'company' },
      { key: 'submitted_total', label: 'Total invoice', format: 'currency', scope: 'company' },
    ],
  },
];

const MOCK_ROWS = [
  {
    name: 'MOCK-SINV-0001',
    posting_date: '2026-10-26',
    customer: 'Mock Customer',
    status: 'Paid',
    base_grand_total: 100000,
  },
];

export async function fetchBootstrap(): Promise<BootstrapData> {
  return {
    user: {
      id: 'mock@example.com',
      name: 'Mock Client',
    },
    company: {
      id: 'Mock Company',
      name: 'Mock Company',
      currency: 'IDR',
    },
    agents: [],
    modules: MOCK_MODULES,
    csrf_token: 'mock-csrf-token',
  };
}

export async function fetchModule(
  key: string,
  params: { page?: number; pageSize?: number; filters?: ModuleFilters } = {},
): Promise<ModuleDetailData> {
  const mod = MOCK_MODULES.find((item) => item.key === key) ?? MOCK_MODULES[0];
  const page = Math.max(1, params.page ?? 1);
  const pageSize = Math.max(1, params.pageSize ?? 25);
  return {
    module: mod,
    cards: [
      {
        key: 'submitted_count',
        label: 'Invoice disetujui',
        value: MOCK_ROWS.length,
        format: 'number',
        scope: 'company',
      },
      {
        key: 'submitted_total',
        label: 'Total invoice',
        value: 100000,
        format: 'currency',
        scope: 'company',
        currency: 'IDR',
      },
    ],
    doctypes: [{ doctype: mod.doctype, label: mod.label, columns: mod.columns }],
    rows: MOCK_ROWS,
    pagination: {
      page,
      page_size: pageSize,
      total: MOCK_ROWS.length,
      total_pages: 1,
    },
  };
}

export async function fetchList(
  key: string,
  doctype: string,
  params: { page?: number; pageSize?: number; filters?: ModuleFilters } = {},
): Promise<ModuleListData> {
  const mod = MOCK_MODULES.find((item) => item.key === key) ?? MOCK_MODULES[0];
  const page = Math.max(1, params.page ?? 1);
  const pageSize = Math.max(1, params.pageSize ?? 25);
  return {
    module: mod,
    doctype: doctype || mod.doctype,
    rows: MOCK_ROWS,
    pagination: {
      page,
      page_size: pageSize,
      total: MOCK_ROWS.length,
      total_pages: 1,
    },
  };
}

export async function search(q: string, _limit?: number): Promise<SearchResult[]> {
  if (!q.trim()) return [];
  return [{ kind: 'module', module: MOCK_MODULES[0] }];
}

export async function fetchSettings(): Promise<SettingsData> {
  return {
    profile: {
      name: 'Mock Client',
      persona: 'finance',
      status: 'Active',
    },
    company: {
      id: 'Mock Company',
      name: 'Mock Company',
      currency: 'IDR',
    },
    quota: {
      limit: 100000,
      used: 25000,
      remaining: 75000,
      percent_used: 25,
    },
    reset: {
      at: '2026-10-27T00:00:00',
      at_label: '00:00',
      seconds_remaining: 28800,
      source: 'scheduled',
      scheduler_active: true,
    },
    theme: {
      value: mockThemeValue,
      options: [...ALLOWED_THEMES],
    },
  };
}

export async function saveTheme(theme: SettingsTheme, _csrfToken: string): Promise<void> {
  mockThemeValue = normalizeTheme(theme);
}

export const modulesApi = {
  fetchBootstrap,
  fetchModule,
  fetchList,
  search,
  fetchSettings,
  saveTheme,
} satisfies ModulesApi;
