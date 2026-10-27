import { defineStore } from 'pinia';
import { fetchBranches } from '../api/branches';
import type { Branch } from '../types';

export const useBranchesStore = defineStore('branches', {
  state: () => ({
    branches: [] as Branch[],
    loaded: false,
    loading: false,
    selectedKey: null as string | null,
  }),
  getters: {
    byKey: (s) => (key: string) => s.branches.find((b) => b.key === key),
    /** Branch aktif: pilihan pengguna, fallback branch enabled pertama. */
    selected: (s) => s.branches.find((b) => b.key === s.selectedKey) ?? s.branches[0] ?? null,
    /** Saran pertanyaan: contoh pertanyaan milik worker cabang (data backend). */
    suggestions: (s) => (key: string, limit = 4) => {
      const branch = s.branches.find((b) => b.key === key);
      if (!branch) return [];
      const out: string[] = [];
      for (const worker of branch.workers) {
        for (const question of worker.exampleQuestions) {
          if (!out.includes(question)) out.push(question);
          if (out.length >= limit) return out;
        }
      }
      return out;
    },
  },
  actions: {
    selectBranch(key: string) {
      if (this.branches.some((b) => b.key === key)) this.selectedKey = key;
    },
    async load() {
      if (this.loaded || this.loading) return;
      this.loading = true;
      try {
        this.branches = await fetchBranches();
        if (!this.selectedKey && this.branches.length) this.selectedKey = this.branches[0].key;
        this.loaded = true;
      } finally {
        this.loading = false;
      }
    },
  },
});
