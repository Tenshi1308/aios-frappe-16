import { defineStore } from "pinia";
import router from "@/router";
import { computed, ref, watch } from "vue";
import {
  getCurrentSession,
  login as loginToFrappe,
  logout as logoutFromFrappe,
} from "@/features/auth/api";
import type { LoginCredentials, RoleProfile, User } from "@/types/auth";
import { useOnboardingStore } from "@/stores/onboarding";
import { getMyEmployment, type MyEmployment } from "@/features/auth/employment";
import type { MenuUserContext } from "@/helpers/menu";
import { setViewAsHeader } from "@/helpers/http-client";
import { startActivityTracker, stopActivityTracker } from "@/features/activity-monitor/tracker";

export const useAuthStore = defineStore("auth_store", () => {
  const user = ref<User | null>(null);

  /**
   * Hanya Super Administrator (user "Administrator") yang boleh berpindah melihat dashboard role lain.
   * Data tetap diambil dengan hak Super Administrator; ini hanya mengganti menu & tampilan.
   */
  const VIEW_AS_KEY = "spi_view_as_role";
  const readViewAs = (): RoleProfile | null => {
    try {
      return (sessionStorage.getItem(VIEW_AS_KEY) as RoleProfile | null) || null;
    } catch {
      return null;
    }
  };
  const viewAsRole = ref<RoleProfile | null>(readViewAs());
  const isSuperAdministrator = computed(() => user.value?.username === "Administrator");
  // Header "Lihat sebagai" hanya untuk Super Administrator (backend juga mengabaikannya untuk user lain).
  watch(
    [isSuperAdministrator, viewAsRole],
    ([isSuper, role]) => setViewAsHeader(isSuper ? role : null),
    { immediate: true },
  );
  /** Role yang dipakai untuk menu/halaman: role user, atau role pilihan Super Administrator. */
  const effectiveRoleProfile = computed<RoleProfile | null>(() =>
    isSuperAdministrator.value ? viewAsRole.value : user.value?.roleProfile ?? null,
  );
  /** Kategori kepegawaian (Tetap/Freelance) untuk menyaring menu Honor Saya / Slip Gaji Saya. */
  const employment = ref<MyEmployment | null>(null);
  const loadEmployment = async () => {
    if (!user.value) {
      employment.value = null;
      return;
    }
    try {
      employment.value = await getMyEmployment();
    } catch {
      employment.value = null;
    }
  };

  const menuContext = computed<MenuUserContext>(() => ({
    roleProfile: user.value?.roleProfile ?? null,
    isSystemManager: user.value?.isSystemManager ?? false,
    username: user.value?.username ?? null,
    viewAsRole: isSuperAdministrator.value ? viewAsRole.value : null,
    employmentCategory: employment.value?.category ?? null,
  }));

  const setViewAsRole = (role: RoleProfile | null) => {
    if (!isSuperAdministrator.value) return;
    viewAsRole.value = role;
    try {
      if (role) sessionStorage.setItem(VIEW_AS_KEY, role);
      else sessionStorage.removeItem(VIEW_AS_KEY);
    } catch {
      // abaikan
    }
  };
  const initialized = ref(false);
  const isLoading = ref(false);

  const initializeSession = async (force = false) => {
    if (initialized.value && !force) {
      return user.value;
    }

    isLoading.value = true;
    try {
      user.value = await getCurrentSession();
      await loadEmployment();
      // Activity Monitoring: hanya aktif bila diaktifkan admin & role direkam (dicek server). Tidak ditunggu.
      void startActivityTracker(user.value?.username);
    } catch {
      user.value = null;
    } finally {
      initialized.value = true;
      isLoading.value = false;
    }

    return user.value;
  };

  const login = async (credentials: LoginCredentials) => {
    isLoading.value = true;
    try {
      user.value = await loginToFrappe(credentials);
      await loadEmployment();
      void startActivityTracker(user.value?.username);
      initialized.value = true;
      return user.value;
    } finally {
      isLoading.value = false;
    }
  };

  const logout = async () => {
    isLoading.value = true;
    try {
      // Kirim sisa event monitoring sebelum sesi berakhir (best-effort, tidak menghalangi logout).
      await Promise.race([stopActivityTracker("logout"), new Promise((r) => setTimeout(r, 1500))]);
      await logoutFromFrappe();
      user.value = null;
      employment.value = null;
      viewAsRole.value = null;
      try {
        sessionStorage.removeItem(VIEW_AS_KEY);
        // jendela desktop & penanda "dashboard sudah dibuka otomatis" milik sesi user sebelumnya
        sessionStorage.removeItem("spi_desktop_windows");
        sessionStorage.removeItem("spi_dashboard_autoopened");
      } catch {
        // abaikan
      }
      useOnboardingStore().clear();
      initialized.value = true;
      await router.replace({ name: "auth.sign-in" });
    } finally {
      isLoading.value = false;
    }
  };

  return {
    user,
    viewAsRole,
    isSuperAdministrator,
    effectiveRoleProfile,
    setViewAsRole,
    employment,
    menuContext,
    initialized,
    isLoading,
    initializeSession,
    login,
    logout,
  };
});
