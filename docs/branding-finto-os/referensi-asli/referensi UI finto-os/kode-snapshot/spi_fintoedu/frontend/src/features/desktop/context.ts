import type { InjectionKey, Ref } from "vue";
import type { LocationQueryRaw } from "vue-router";

/**
 * Konteks jendela mode desktop. Halaman yang dirender di dalam jendela dapat meng-inject ini:
 * DefaultLayout menyembunyikan TopBar/sidebar/footer, HubTabs berpindah bagian di jendela yang sama.
 */
export type DesktopWindowContext = {
  id: string;
  routeName: Ref<string>;
  query: Ref<LocationQueryRaw>;
  /** Ganti isi jendela ini ke rute lain (mis. tab hub). */
  navigate: (routeName: string, query?: LocationQueryRaw) => void;
  close: () => void;
};

export const DESKTOP_WINDOW: InjectionKey<DesktopWindowContext> = Symbol("spi-desktop-window");
