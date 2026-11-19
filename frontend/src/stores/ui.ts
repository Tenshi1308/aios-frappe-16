import { defineStore } from 'pinia';

export type Flyout = 'start' | 'search' | null;

interface Toast {
  id: number;
  text: string;
}

let toastSeq = 0;

export const AGENT_PANEL_DEFAULT_W = 410;
export const AGENT_PANEL_MIN_W = 340;
export const AGENT_PANEL_MAX_W = 960;

function clampAgentWidth(width: number): number {
  return Math.max(AGENT_PANEL_MIN_W, Math.min(AGENT_PANEL_MAX_W, Math.round(width)));
}

export const useUiStore = defineStore('ui', {
  state: () => ({
    flyout: null as Flyout,
    agentOpen: false,
    agentWidth: AGENT_PANEL_DEFAULT_W,
    agentFullscreen: false,
    agentSidebarOpen: true,
    toasts: [] as Toast[],
  }),
  actions: {
    setAgentWidth(width: number) {
      this.agentWidth = clampAgentWidth(width);
    },
    toggleAgentFullscreen() {
      this.agentFullscreen = !this.agentFullscreen;
      if (this.agentFullscreen) {
        this.agentSidebarOpen = true;
      }
    },
    setAgentFullscreen(value: boolean) {
      this.agentFullscreen = value;
      if (value) {
        this.agentSidebarOpen = true;
      }
    },
    toggleAgentSidebar() {
      this.agentSidebarOpen = !this.agentSidebarOpen;
    },
    setAgentSidebarOpen(value: boolean) {
      this.agentSidebarOpen = value;
    },
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
