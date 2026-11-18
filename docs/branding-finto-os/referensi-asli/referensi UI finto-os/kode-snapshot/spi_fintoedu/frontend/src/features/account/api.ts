import { reactive } from "vue";
import HttpClient from "@/helpers/http-client";

/** Ganti password sendiri (spi_fintoedu.api.account). User hasil migrasi wajib mengganti password awal. */
const API = "/api/method/spi_fintoedu.api.account";

/** Status global jendela Ganti Password (dibuka dari menu profil, atau otomatis bila wajib). */
export const passwordModal = reactive({ open: false, required: false });

export async function getPasswordStatus(): Promise<{ must_change: boolean }> {
  return (await HttpClient.get<{ message: { must_change: boolean } }>(`${API}.get_password_status`)).data.message;
}

export async function changeMyPassword(oldPassword: string, newPassword: string): Promise<void> {
  await HttpClient.post(`${API}.change_my_password`, { old_password: oldPassword, new_password: newPassword });
}
