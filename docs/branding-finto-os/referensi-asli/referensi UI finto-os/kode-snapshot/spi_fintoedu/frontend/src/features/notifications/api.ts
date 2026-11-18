import HttpClient from "@/helpers/http-client";

const API_BASE = "/api/method/spi_fintoedu.api.notifications";

export interface AppNotification {
  name: string;
  subject: string;
  email_content: string | null;
  document_type: string | null;
  document_name: string | null;
  read: number;
  creation: string;
}

export async function getMyNotifications(limit = 20) {
  const res = await HttpClient.get<{ message: { items: AppNotification[]; unread: number } }>(`${API_BASE}.get_my_notifications`, {
    params: { limit },
  });
  return res.data.message;
}

export async function markNotificationsRead(names?: string[]) {
  const res = await HttpClient.post<{ message: { unread: number } }>(`${API_BASE}.mark_notifications_read`, { names });
  return res.data.message;
}
