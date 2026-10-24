import { defineStore } from 'pinia';

export type Flyout = 'start' | 'search' | null;

interface Toast {
  id: number;
  text: string;
}

let toastSeq = 0;

export const useUiStore = defineStore('ui', {
  state: () => ({
    flyout: null as Flyout,
    agentOpen: false,
    toasts: [] as Toast[],
  }),
  actions: {
    closeFlyouts() {
      this.flyout = null;
    },
    toggleFlyout(name: Exclude<Flyout, null>) {
      this.flyout = this.flyout === name ? null : name;
    },
    openSearch() {
      this.flyout = 'search';
    },
    openAgent() {
      this.flyout = null;
      this.agentOpen = true;
    },
    toggleAgent() {
      if (this.agentOpen) this.agentOpen = false;
      else this.openAgent();
    },
    closeAgent() {
      this.agentOpen = false;
    },
    toast(text: string) {
      const id = ++toastSeq;
      this.toasts.push({ id, text });
      setTimeout(() => {
        this.toasts = this.toasts.filter((t) => t.id !== id);
      }, 3600);
    },
  },
});
