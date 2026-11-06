import { defineStore } from 'pinia';
import {
  fetchBootstrap,
  fetchDomain,
  fetchList,
  fetchModule,
  fetchSettings,
  saveTheme,
  saveCompanyPersona,
  search as apiSearch,
  fetchClientStaffAndRecipients,
  setChannelReceiver as apiSetChannelReceiver,
  createClientStaff as apiCreateClientStaff,
  setClientStaffStatus as apiSetClientStaffStatus,
  regenerateClientStaffInvite as apiRegenerateClientStaffInvite,
} from '@modules-api';
import { useWindowManager } from '../composables/useWindowManager';
import { useSessionStore } from './session';
import { reportClientError } from '../api/client';
import {
  fetchTelegramStatus,
  createTelegramLinkToken,
  unlinkTelegramAccount,
  type TelegramLinkStatus,
} from '../api/connector';
import type {
  ClientStaffAndRecipientsData,
  CreateClientStaffResponse,
  DomainDetailData,
  DomainMeta,
  ModuleDetailData,
  ModuleFilters,
  ModuleMeta,
  RegenerateStaffInviteResponse,
  SearchResult,
  SettingsData,
  SettingsTheme,
} from '../types';
import { applyTheme } from '../utils/theme';

export interface ModuleEntryState extends ModuleDetailData {
  filters: ModuleFilters;
}

export const useModulesStore = defineStore('modules', {
  state: () => ({
    domains: [] as DomainMeta[],
    domainData: {} as Record<string, DomainDetailData>,
    domainLoadingByKey: {} as Record<string, boolean>,
    domainErrorByKey: {} as Record<string, string>,
    modules: [] as ModuleMeta[],
    activeKey: null as string | null,
    moduleData: {} as Record<string, ModuleEntryState>,
    searchResults: [] as SearchResult[],
    loading: false,
    loadingByKey: {} as Record<string, boolean>,
    searchLoading: false,
    error: '',
    errorByKey: {} as Record<string, string>,
    searchError: '',
    settings: null as SettingsData | null,
    settingsLoading: false,
    settingsError: '',
    themeSaving: false,
    telegramStatus: null as TelegramLinkStatus | null,
    telegramDeepLink: '' as string,
    telegramExpiresIn: null as number | null,
    telegramLoading: false,
    telegramError: '',
    staffData: null as ClientStaffAndRecipientsData | null,
    staffLoading: false,
    staffError: '',
    bootstrapped: false,
    bootstrapError: '',
    _reqSeq: {} as Record<string, number>,
    _domainSeq: {} as Record<string, number>,
    _searchSeq: 0,
    _settingsSeq: 0,
  }),
  getters: {
    domainByKey: (s) => (key: string) => s.domains.find((d) => d.key === key),
    domainDataFor: (s) => (key: string) => s.domainData[key] ?? null,
    isDomainLoadingKey: (s) => (key: string) => s.domainLoadingByKey[key] ?? false,
    domainErrorFor: (s) => (key: string) => s.domainErrorByKey[key] ?? '',
    byKey: (s) => (key: string) => s.modules.find((m) => m.key === key),
    grouped: (s) => {
      const map = new Map<string, ModuleMeta[]>();
      for (const m of s.modules) {
        const group = m.group || 'Lainnya';
        const list = map.get(group);
        if (list) list.push(m);
        else map.set(group, [m]);
      }
      return [...map.entries()].map(([group, items]) => ({ group, items }));
    },
    dataFor: (s) => (key: string) => s.moduleData[key] ?? null,
    isLoadingKey: (s) => (key: string) => s.loadingByKey[key] ?? false,
    errorFor: (s) => (key: string) => s.errorByKey[key] ?? '',
    bootstrapFailed: (s) => !s.bootstrapped && !!s.bootstrapError,
  },
  actions: {
    async loadBootstrap(force = false) {
      if ((this.bootstrapped && !force) || this.loading) return;
      this.loading = true;
      try {
        const data = await fetchBootstrap();
        this.domains = data.domains ?? [];
        this.modules = data.modules;
        this.bootstrapped = true;
        this.bootstrapError = '';
      } catch (err) {
        // Bootstrap modul tidak boleh menjatuhkan shell (mis. Administrator ditolak _require_active_client).
        if (!this.bootstrapped) {
          this.domains = [];
          this.modules = [];
        }
        const message =
          err instanceof Error && err.message.trim()
            ? err.message
            : 'Katalog modul tidak dapat dimuat.';
        this.bootstrapError = message;
        const session = useSessionStore();
        void reportClientError(
          {
            message,
            context: 'loadBootstrap',
            stack: err instanceof Error ? (err.stack ?? '') : '',
          },
          session.csrfToken,
        );
      } finally {
        this.loading = false;
      }
    },

    async refreshModule(key: string, opts: { page?: number; filters?: ModuleFilters } = {}) {
      const seq = (this._reqSeq[key] ?? 0) + 1;
      this._reqSeq[key] = seq;
      this.loadingByKey[key] = true;
      this.loading = true;
      this.errorByKey[key] = '';
      this.error = '';

      const existing = this.moduleData[key];
      const filters: ModuleFilters = opts.filters ?? existing?.filters ?? {};
      const page = opts.page ?? existing?.pagination.page ?? 1;

      try {
        const detail = await fetchModule(key, { page, filters });
        if (this._reqSeq[key] !== seq) return;
        this.moduleData[key] = {
          ...detail,
          filters: { ...filters },
        };
        if (!this.modules.some((m) => m.key === detail.module.key)) {
          this.modules = [...this.modules, detail.module];
        }
      } catch (err) {
        if (this._reqSeq[key] !== seq) return;
        const msg = err instanceof Error && err.message.trim() ? err.message : 'Modul tidak dapat dimuat.';
        this.errorByKey[key] = msg;
        this.error = msg;
      } finally {
        if (this._reqSeq[key] === seq) {
          this.loadingByKey[key] = false;
          this.loading = Object.values(this.loadingByKey).some(Boolean);
        }
      }
    },

    async refreshDomain(key: string) {
      if (!key || this.domainLoadingByKey[key]) return;
      const seq = (this._domainSeq[key] ?? 0) + 1;
      this._domainSeq[key] = seq;
      this.domainLoadingByKey[key] = true;
      this.domainErrorByKey[key] = '';

      try {
        const detail = await fetchDomain(key);
        if (this._domainSeq[key] !== seq) return;
        this.domainData[key] = detail;
        if (!this.domains.some((d) => d.key === detail.domain.key)) {
          this.domains = [...this.domains, detail.domain];
        }
      } catch (err) {
        if (this._domainSeq[key] !== seq) return;
        const msg = err instanceof Error && err.message.trim() ? err.message : 'Bidang tidak dapat dimuat.';
        this.domainErrorByKey[key] = msg;
      } finally {
        if (this._domainSeq[key] === seq) {
          this.domainLoadingByKey[key] = false;
        }
      }
    },

    async openDomain(key: string) {
      if (!key) return;
      const meta = this.domainByKey(key) ?? this.domainDataFor(key)?.domain;
      const title = meta?.label ?? key;
      const win = useWindowManager().open(`domain:${key}`, title);
      if (!this.domainDataFor(key)) {
        await this.refreshDomain(key);
        const loadedTitle = this.domainDataFor(key)?.domain.label;
        if (loadedTitle && win.title !== loadedTitle) {
          win.title = loadedTitle;
        }
      }
    },

    async openModule(key: string) {
      if (!key) return;
      this.activeKey = key;
      const meta = this.byKey(key) ?? this.dataFor(key)?.module;
      const title = meta?.label ?? key;
      const win = useWindowManager().open(`module:${key}`, title);
      if (!this.dataFor(key)) {
        await this.refreshModule(key, { page: 1, filters: {} });
        const loadedTitle = this.dataFor(key)?.module.label;
        if (loadedTitle && win.title !== loadedTitle) {
          win.title = loadedTitle;
        }
      }
    },

    async loadPage(key: string, page: number) {
      const targetPage = Math.max(1, Math.trunc(page));
      const existing = this.moduleData[key];
      if (!existing) {
        await this.refreshModule(key, { page: targetPage, filters: {} });
        return;
      }
      const seq = (this._reqSeq[key] ?? 0) + 1;
      this._reqSeq[key] = seq;
      this.loadingByKey[key] = true;
      this.loading = true;
      this.errorByKey[key] = '';
      this.error = '';

      const doctype = existing.doctypes[0]?.doctype ?? existing.module.doctype;
      try {
        const listed = await fetchList(key, doctype, {
          page: targetPage,
          pageSize: existing.pagination.page_size,
          filters: existing.filters,
        });
        if (this._reqSeq[key] !== seq) return;
        const current = this.moduleData[key];
        if (current) {
          this.moduleData[key] = {
            ...current,
            module: listed.module,
            rows: listed.rows,
            pagination: listed.pagination,
            cards: listed.cards ?? current.cards,
          };
        }
      } catch (err) {
        if (this._reqSeq[key] !== seq) return;
        const msg = err instanceof Error && err.message.trim() ? err.message : 'Halaman tidak dapat dimuat.';
        this.errorByKey[key] = msg;
        this.error = msg;
      } finally {
        if (this._reqSeq[key] === seq) {
          this.loadingByKey[key] = false;
          this.loading = Object.values(this.loadingByKey).some(Boolean);
        }
      }
    },

    async applyFilter(key: string, filters: ModuleFilters) {
      const existing = this.moduleData[key];
      if (!existing) {
        await this.refreshModule(key, { page: 1, filters });
        return;
      }
      const seq = (this._reqSeq[key] ?? 0) + 1;
      this._reqSeq[key] = seq;
      this.loadingByKey[key] = true;
      this.loading = true;
      this.errorByKey[key] = '';
      this.error = '';

      const doctype = existing.doctypes[0]?.doctype ?? existing.module.doctype;
      try {
        const listed = await fetchList(key, doctype, {
          page: 1,
          pageSize: existing.pagination.page_size,
          filters,
        });
        if (this._reqSeq[key] !== seq) return;
        const current = this.moduleData[key];
        if (current) {
          this.moduleData[key] = {
            ...current,
            module: listed.module,
            rows: listed.rows,
            pagination: listed.pagination,
            filters: { ...filters },
            cards: listed.cards ?? current.cards,
          };
        }
      } catch (err) {
        if (this._reqSeq[key] !== seq) return;
        const msg = err instanceof Error && err.message.trim() ? err.message : 'Filter tidak dapat diterapkan.';
        this.errorByKey[key] = msg;
        this.error = msg;
      } finally {
        if (this._reqSeq[key] === seq) {
          this.loadingByKey[key] = false;
          this.loading = Object.values(this.loadingByKey).some(Boolean);
        }
      }
    },

    async runSearch(q: string) {
      const trimmed = q.trim();
      const seq = ++this._searchSeq;
      if (!trimmed) {
        this.searchResults = [];
        this.searchLoading = false;
        this.searchError = '';
        return;
      }
      this.searchLoading = true;
      this.searchError = '';
      try {
        const results = await apiSearch(trimmed);
        if (this._searchSeq !== seq) return;
        this.searchResults = results;
      } catch (err) {
        if (this._searchSeq !== seq) return;
        this.searchResults = [];
        this.searchError = err instanceof Error && err.message.trim() ? err.message : 'Pencarian gagal.';
      } finally {
        if (this._searchSeq === seq) {
          this.searchLoading = false;
        }
      }
    },

    async loadSettings(force = false) {
      if (this.settingsLoading && !force) return;
      const seq = ++this._settingsSeq;
      this.settingsLoading = true;
      this.settingsError = '';
      try {
        const data = await fetchSettings();
        if (this._settingsSeq !== seq) return;
        this.settings = data;
      } catch (err) {
        if (this._settingsSeq !== seq) return;
        this.settingsError =
          err instanceof Error && err.message.trim()
            ? err.message
            : 'Data pengaturan tidak dapat dimuat.';
      } finally {
        if (this._settingsSeq === seq) {
          this.settingsLoading = false;
        }
      }
    },

    async openSettings() {
      useWindowManager().open('settings', 'Pengaturan');
      await this.loadSettings(true);
    },

    async setTheme(value: SettingsTheme) {
      if (this.themeSaving) return;
      this.themeSaving = true;
      this.settingsError = '';
      try {
        const session = useSessionStore();
        await saveTheme(value, session.csrfToken);
        applyTheme(value);
        if (this.settings) {
          this.settings.theme.value = value;
        }
      } catch (err) {
        this.settingsError =
          err instanceof Error && err.message.trim()
            ? err.message
            : 'Tema tidak dapat disimpan.';
      } finally {
        this.themeSaving = false;
      }
    },
    async saveCompanyPersona(persona: string): Promise<string> {
      const session = useSessionStore();
      const cleaned = await saveCompanyPersona(persona, session.csrfToken);
      if (this.settings) {
        this.settings.company_context_persona = cleaned;
      }
      return cleaned;
    },
    async loadTelegramStatus() {
      try {
        this.telegramLoading = true;
        this.telegramError = '';
        this.telegramStatus = await fetchTelegramStatus();
      } catch (err: unknown) {
        this.telegramError = err instanceof Error ? err.message : 'Gagal memuat status Telegram.';
      } finally {
        this.telegramLoading = false;
      }
    },
    async generateTelegramLink() {
      const session = useSessionStore();
      try {
        this.telegramLoading = true;
        this.telegramError = '';
        const res = await createTelegramLinkToken(session.csrfToken);
        this.telegramDeepLink = res.deep_link;
        this.telegramExpiresIn = res.expires_in_seconds;
      } catch (err: unknown) {
        this.telegramError = err instanceof Error ? err.message : 'Gagal membuat tautan Telegram.';
      } finally {
        this.telegramLoading = false;
      }
    },
    async unlinkTelegram() {
      const session = useSessionStore();
      try {
        this.telegramLoading = true;
        this.telegramError = '';
        await unlinkTelegramAccount(session.csrfToken);
        this.telegramStatus = { linked: false };
        this.telegramDeepLink = '';
        this.telegramExpiresIn = null;
      } catch (err: unknown) {
        this.telegramError = err instanceof Error ? err.message : 'Gagal memutuskan tautan Telegram.';
      } finally {
        this.telegramLoading = false;
      }
    },
    async loadClientStaffAndRecipients() {
      const session = useSessionStore();
      if (!(session.context?.roles ?? []).includes('AIOS Client Owner')) return;
      try {
        this.staffLoading = true;
        this.staffError = '';
        this.staffData = await fetchClientStaffAndRecipients();
      } catch (err: unknown) {
        this.staffError =
          err instanceof Error ? err.message : 'Gagal memuat daftar staf dan penerima.';
      } finally {
        this.staffLoading = false;
      }
    },
    async toggleChannelReceiver(targetUser: string, enabled: boolean) {
      const session = useSessionStore();
      try {
        this.staffLoading = true;
        this.staffError = '';
        this.staffData = await apiSetChannelReceiver(targetUser, enabled, session.csrfToken);
      } catch (err: unknown) {
        this.staffError =
          err instanceof Error ? err.message : 'Gagal memperbarui penerima notifikasi.';
        throw err;
      } finally {
        this.staffLoading = false;
      }
    },
    async addClientStaff(payload: {
      email: string;
      full_name: string;
      persona: string;
    }): Promise<CreateClientStaffResponse> {
      const session = useSessionStore();
      this.staffLoading = true;
      this.staffError = '';
      try {
        const res = await apiCreateClientStaff(payload, session.csrfToken);
        await this.loadClientStaffAndRecipients();
        return res;
      } catch (err: unknown) {
        this.staffError = err instanceof Error ? err.message : 'Gagal menambahkan staf baru.';
        throw err;
      } finally {
        this.staffLoading = false;
      }
    },
    async changeClientStaffStatus(targetUser: string, status: 'Active' | 'Suspended') {
      const session = useSessionStore();
      try {
        this.staffLoading = true;
        this.staffError = '';
        this.staffData = await apiSetClientStaffStatus(targetUser, status, session.csrfToken);
      } catch (err: unknown) {
        this.staffError = err instanceof Error ? err.message : 'Gagal mengubah status staf.';
        throw err;
      } finally {
        this.staffLoading = false;
      }
    },
    async regenerateStaffInvite(targetUser: string): Promise<RegenerateStaffInviteResponse> {
      const session = useSessionStore();
      this.staffLoading = true;
      this.staffError = '';
      try {
        return await apiRegenerateClientStaffInvite(targetUser, session.csrfToken);
      } catch (err: unknown) {
        this.staffError =
          err instanceof Error ? err.message : 'Gagal membuat ulang tautan undangan.';
        throw err;
      } finally {
        this.staffLoading = false;
      }
    },
  },
});
