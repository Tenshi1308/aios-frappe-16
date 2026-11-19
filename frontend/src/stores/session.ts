import { defineStore } from 'pinia';
import { fetchRegistrationStatus, fetchSessionContext, login as apiLogin, registerAccount } from '../api/session';
import { apiFetch } from '../api/client';
import { currentBrand } from '../utils/theme';
import type { SessionContext } from '../types';

export type SessionPhase = 'boot' | 'lock' | 'register' | 'pending' | 'desktop';

let bootSkipResolve: (() => void) | null = null;
let bootSeq = 0;

function sleepBoot(ms: number, seq: number): Promise<void> {
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => {
      if (bootSkipResolve === done) bootSkipResolve = null;
      resolve();
    }, ms);
    const done = () => {
      window.clearTimeout(timer);
      if (bootSkipResolve === done) bootSkipResolve = null;
      resolve();
    };
    if (seq === bootSeq) {
      bootSkipResolve = done;
    }
  });
}

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
    /** Default false (fail-closed): tombol Daftar hanya aktif di site developer. */
    canRegister: false,
    siteRole: 'client',
    /** Pesan aman saat status akun memblokir akses desktop (fail-closed). */
    blockedMessage: '',
    bootSkipped: false,
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
    skipBoot() {
      this.bootSkipped = true;
      this.setProgress(100);
      bootSkipResolve?.();
    },
    async waitBootStep(targetElapsedMs: number, startMs: number, seq: number) {
      if (this.bootSkipped || seq !== bootSeq) return;
      const isFinto = currentBrand.value === 'finto';
      if (!isFinto) return;
      const reduced =
        typeof window !== 'undefined' &&
        typeof window.matchMedia === 'function' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const scaledTarget = reduced ? Math.round(targetElapsedMs * 0.3) : targetElapsedMs;
      const remaining = scaledTarget - (Date.now() - startMs);
      if (remaining > 0) {
        await sleepBoot(remaining, seq);
      }
    },
    async boot() {
      const seq = ++bootSeq;
      const startMs = Date.now();
      this.phase = 'boot';
      this.bootSkipped = false;
      this.bootProgress = 0;
      this.bootLog = [];
      this.setProgress(10);
      this.pushBoot('Menghubungkan ke server');
      try {
        const regStatus = await fetchRegistrationStatus();
        this.canRegister = regStatus.can_register;
        this.siteRole = regStatus.site_role;
      } catch (err) {
        console.warn('Gagal memuat status registrasi site (fail-closed):', err);
        this.canRegister = false;
        this.siteRole = 'client';
      }
      try {
        const ctx = await fetchSessionContext();
        if (seq !== bootSeq) return;
        await this.waitBootStep(1600, startMs, seq);
        if (seq !== bootSeq) return;
        this.setProgress(55);
        this.pushBoot('Memulihkan sesi');
        await this.waitBootStep(3200, startMs, seq);
        if (seq !== bootSeq) return;
        this.setProgress(88);
        this.pushBoot('Menyiapkan desktop');
        this.online = true;
        await this.waitBootStep(4600, startMs, seq);
        if (seq !== bootSeq) return;
        this.setProgress(100);
        await this.waitBootStep(5100, startMs, seq);
        if (seq !== bootSeq) return;
        this.applyContext(ctx);
      } catch (err) {
        console.warn('Boot session check failed or no active session:', err);
        if (seq !== bootSeq) return;
        await this.waitBootStep(1800, startMs, seq);
        if (seq !== bootSeq) return;
        this.setProgress(55);
        this.pushBoot('Sesi tidak ditemukan — menyiapkan layar masuk');
        this.context = null;
        this.online = true;
        await this.waitBootStep(4600, startMs, seq);
        if (seq !== bootSeq) return;
        this.setProgress(100);
        await this.waitBootStep(5100, startMs, seq);
        if (seq !== bootSeq) return;
        this.phase = 'lock';
      }
    },
    setPhase(phase: SessionPhase) {
      if (phase === 'register' && !this.canRegister) {
        this.phase = 'lock';
        return;
      }
      this.phase = phase;
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
      if (!this.canRegister) {
        this.registerError = 'Pendaftaran mandiri hanya dapat dilakukan melalui portal pengembang.';
        this.phase = 'lock';
        throw new Error(this.registerError);
      }
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
        await apiFetch('/api/method/logout', {
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
