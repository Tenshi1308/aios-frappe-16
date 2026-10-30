import { defineStore } from 'pinia';
import { fetchSessionContext, login as apiLogin, registerAccount } from '../api/session';
import { apiFetch } from '../api/client';
import type { SessionContext } from '../types';

export type SessionPhase = 'boot' | 'lock' | 'register' | 'pending' | 'desktop';

export const useSessionStore = defineStore('session', {
  state: () => ({
    phase: 'boot' as SessionPhase,
    context: null as SessionContext | null,
    bootProgress: 0,
    bootLog: [] as string[],
    online: false,
    lockError: '',
    registerError: '',
    registering: false,
    loggingIn: false,
    /** Pesan aman saat status akun memblokir akses desktop (fail-closed). */
    blockedMessage: '',
  }),
  getters: {
    csrfToken: (s) => s.context?.csrf_token ?? '',
    firstName: (s) => {
      const name = s.context?.full_name ?? '';
      const first = name.trim().split(/\s+/)[0];
      return first || '';
    },
    initials: (s) => {
      const name = (s.context?.full_name ?? '').trim();
      if (!name) return 'AI';
      return name
        .split(/\s+/)
        .slice(0, 2)
        .map((w) => w[0]?.toUpperCase() ?? '')
        .join('');
    },
  },
  actions: {
    pushBoot(label: string) {
      if (!this.bootLog.includes(label)) this.bootLog.push(label);
    },
    setProgress(value: number) {
      this.bootProgress = Math.max(this.bootProgress, Math.min(100, Math.round(value)));
    },
    async boot() {
      this.phase = 'boot';
      this.bootProgress = 0;
      this.bootLog = [];
      this.setProgress(10);
      this.pushBoot('Menghubungkan ke server');
      try {
        const ctx = await fetchSessionContext();
        this.setProgress(55);
        this.pushBoot('Memulihkan sesi');
        this.applyContext(ctx);
        this.setProgress(88);
        this.pushBoot('Menyiapkan desktop');
        this.online = true;
        this.setProgress(100);
      } catch {
        this.setProgress(55);
        this.pushBoot('Sesi tidak ditemukan — menyiapkan layar masuk');
        this.context = null;
        this.online = true;
        this.setProgress(100);
        this.phase = 'lock';
      }
    },
    applyContext(ctx: SessionContext) {
      this.context = ctx;
      this.online = true;
      // Urutan wajib (keputusan owner, fail-closed):
      // 1. Admin-like → desktop apa pun statusnya (C12).
      // 2. Pending Provisioning → layar pending.
      // 3. Active → desktop.
      // 4. Sisanya (Suspended/kosong/tak dikenal, non-admin) → blocked.
      const roles = ctx.roles ?? [];
      const adminLike =
        ctx.user === 'Administrator' || roles.includes('System Manager') || roles.includes('AIOS Admin');
      if (adminLike) {
        this.blockedMessage = '';
        this.phase = 'desktop';
        return;
      }
      if (ctx.aios_status === 'Pending Provisioning') {
        this.blockedMessage = '';
        this.phase = 'pending';
        return;
      }
      if (ctx.aios_status === 'Active') {
        this.blockedMessage = '';
        this.phase = 'desktop';
        return;
      }
      this.blockedMessage = 'Akun belum aktif. Hubungi administrator untuk mengaktifkan aksesmu.';
      this.phase = 'pending';
    },
    async login(usr: string, pwd: string) {
      this.loggingIn = true;
      this.lockError = '';
      try {
        await apiLogin(usr, pwd);
        const ctx = await fetchSessionContext();
        this.applyContext(ctx);
      } catch (err) {
        this.lockError = err instanceof Error ? err.message : 'Gagal masuk.';
        throw err;
      } finally {
        this.loggingIn = false;
      }
    },
    async register(payload: { full_name: string; email: string; company_name: string }) {
      this.registering = true;
      this.registerError = '';
      try {
        await registerAccount(payload);
        this.phase = 'pending';
      } catch (err) {
        this.registerError = err instanceof Error ? err.message : 'Pendaftaran gagal.';
        throw err;
      } finally {
        this.registering = false;
      }
    },
    async logout() {
      try {
        // Wajib membawa CSRF: tanpa ini Frappe menolak POST ber-sesi (403
        // "Invalid Request") sebelum sampai dispatcher, dan sesi server
        // tidak pernah benar-benar dihapus.
        await apiFetch('/api/auth/logout', {
          method: 'POST',
          headers: { 'X-Frappe-CSRF-Token': this.csrfToken },
        });
      } finally {
        this.context = null;
        this.phase = 'lock';
      }
    },
    lock() {
      this.phase = 'lock';
    },
    restart() {
      void this.boot();
    },
  },
});
