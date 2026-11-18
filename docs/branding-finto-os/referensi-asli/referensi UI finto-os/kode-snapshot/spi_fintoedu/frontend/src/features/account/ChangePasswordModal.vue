<template>
  <b-modal
    v-model="passwordModal.open"
    title="Ganti Password"
    :no-close-on-backdrop="passwordModal.required"
    :no-close-on-esc="passwordModal.required"
    :hide-header-close="passwordModal.required"
    ok-title="Simpan Password"
    :ok-only="passwordModal.required"
    cancel-title="Batal"
    :ok-disabled="saving"
    @ok.prevent="submit"
  >
    <div v-if="passwordModal.required" class="alert alert-warning py-2">
      Akun Anda masih memakai <b>password awal</b>. Demi keamanan, silakan buat password baru sebelum melanjutkan.
    </div>
    <b-form @submit.prevent="submit">
      <b-form-group label="Password saat ini" class="mb-3">
        <b-form-input v-model="form.old" type="password" autocomplete="current-password" />
      </b-form-group>
      <b-form-group label="Password baru" description="Gunakan kombinasi huruf, angka, dan simbol agar kuat." class="mb-3">
        <b-form-input v-model="form.new" type="password" autocomplete="new-password" />
      </b-form-group>
      <b-form-group label="Ulangi password baru">
        <b-form-input v-model="form.confirm" type="password" autocomplete="new-password" />
      </b-form-group>
      <div v-if="error" class="text-danger mt-2" style="white-space: pre-line">{{ error }}</div>
    </b-form>
  </b-modal>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { useAuthStore } from "@/stores/auth";
import { changeMyPassword, getPasswordStatus, passwordModal } from "./api";

const auth = useAuthStore();
const form = reactive({ old: "", new: "", confirm: "" });
const saving = ref(false);
const error = ref("");

function message(err: any): string {
  const data = err?.response?.data;
  if (data?._server_messages) {
    try {
      return JSON.parse(data._server_messages).map((m: string) => JSON.parse(m).message).join("\n").replace(/<[^>]+>/g, "");
    } catch {
      /* abaikan */
    }
  }
  return (typeof data?.message === "string" && data.message) || err?.message || "Gagal mengganti password.";
}

async function submit() {
  error.value = "";
  if (!form.old || !form.new) return (error.value = "Isi password saat ini dan password baru.");
  if (form.new !== form.confirm) return (error.value = "Ulangi password baru belum sama.");
  saving.value = true;
  try {
    await changeMyPassword(form.old, form.new);
    Object.assign(form, { old: "", new: "", confirm: "" });
    passwordModal.required = false;
    passwordModal.open = false;
    alert("Password berhasil diganti.");
  } catch (e) {
    error.value = message(e);
  } finally {
    saving.value = false;
  }
}

/** Setelah login: user dengan password awal wajib menggantinya. */
watch(
  () => auth.user?.username,
  async (username) => {
    if (!username || username === "Administrator") return;
    try {
      const { must_change } = await getPasswordStatus();
      if (must_change) Object.assign(passwordModal, { open: true, required: true });
    } catch {
      /* belum login penuh / endpoint tidak tersedia */
    }
  },
  { immediate: true },
);
watch(
  () => passwordModal.open,
  (open) => {
    if (!open && passwordModal.required) passwordModal.open = true; // tidak bisa ditutup sebelum diganti
  },
);
</script>
