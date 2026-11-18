import { defineStore } from "pinia";
import { ref } from "vue";
import {
  getOnboardingState,
  markGuideSeen,
  resetGuides,
} from "@/features/onboarding/api";

export const WELCOME_GUIDE_KEY = "welcome";

/**
 * Status wizard panduan per user (disimpan di backend sebagai user default,
 * jadi ikut berpindah perangkat). Bila backend gagal, wizard tidak dipaksa tampil.
 */
export const useOnboardingStore = defineStore("onboarding_store", () => {
  const seen = ref<Set<string>>(new Set());
  const loaded = ref(false);
  /** Diisi TopBar / tombol bantuan untuk membuka ulang panduan halaman aktif. */
  const replayRequest = ref(0);
  let loading: Promise<void> | null = null;

  const ensureLoaded = async () => {
    if (loaded.value) return;
    if (!loading) {
      loading = getOnboardingState()
        .then((state) => {
          seen.value = new Set(state.seen);
          loaded.value = true;
        })
        .catch(() => {
          // gagal memuat: anggap semua sudah dilihat agar wizard tidak mengganggu
          loaded.value = false;
        })
        .finally(() => {
          loading = null;
        });
    }
    await loading;
  };

  const isSeen = (key: string) => seen.value.has(key);

  const markSeen = async (key: string) => {
    seen.value = new Set([...seen.value, key]);
    try {
      const state = await markGuideSeen(key);
      seen.value = new Set(state.seen);
    } catch {
      // status lokal tetap dipakai untuk sesi ini
    }
  };

  const reset = async () => {
    const state = await resetGuides();
    seen.value = new Set(state.seen);
    loaded.value = true;
  };

  const requestReplay = () => {
    replayRequest.value += 1;
  };

  const clear = () => {
    seen.value = new Set();
    loaded.value = false;
  };

  return { seen, loaded, replayRequest, ensureLoaded, isSeen, markSeen, reset, requestReplay, clear };
});
