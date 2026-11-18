import { defineStore } from "pinia";
import { ref } from "vue";
import HttpClient from "@/helpers/http-client";

export type UiMode = "web" | "desktop";

const API = "/api/method/spi_fintoedu.api.ui_settings";
/** Dibaca index.html sebelum aplikasi dimuat: mode desktop tidak menampilkan splash logo SPI. */
const MODE_CACHE_KEY = "spi_ui_mode";

function cacheMode(mode: UiMode) {
  try {
    localStorage.setItem(MODE_CACHE_KEY, mode);
  } catch {
    // abaikan
  }
  document.documentElement.classList.toggle("os-mode", mode === "desktop");
  if (mode === "desktop") document.getElementById("splash-screen")?.remove();
}

/**
 * Mode tampilan global (diatur Super Administrator): "web" (sidebar) atau "desktop" (seperti sistem operasi).
 * Dibaca sebelum login karena mode desktop menampilkan animasi booting sebelum layar login.
 */
export const useUiStore = defineStore("ui_store", () => {
  const mode = ref<UiMode>("desktop");
  const loaded = ref(false);
  let loading: Promise<void> | null = null;

  const ensureLoaded = async () => {
    if (loaded.value) return;
    loading ??= HttpClient.get<{ message: { mode: UiMode } }>(`${API}.get_ui_settings`)
      .then((res) => {
        mode.value = res.data.message.mode === "web" ? "web" : "desktop";
        cacheMode(mode.value);
      })
      .catch(() => {
        mode.value = "desktop";
      })
      .finally(() => {
        loaded.value = true;
        loading = null;
      });
    await loading;
  };

  const setMode = async (next: UiMode) => {
    const res = await HttpClient.post<{ message: { mode: UiMode } }>(`${API}.set_ui_mode`, { mode: next });
    mode.value = res.data.message.mode;
    cacheMode(mode.value);
  };

  /**
   * Animasi booting tampil setiap kali halaman dimuat (buka tab / refresh = "restart" Finto OS), tetapi tidak
   * saat berpindah di dalam aplikasi (mis. logout -> layar login). Status disimpan di memori, bukan storage.
   */
  let booted = false;
  const hasBooted = () => booted;
  const markBooted = () => {
    booted = true;
  };

  return { mode, loaded, ensureLoaded, setMode, hasBooted, markBooted };
});
