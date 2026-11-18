/**
 * Tujuan klik notifikasi lonceng. Notifikasi (Notification Log) membawa `document_type` /
 * `document_name`; halaman tujuan diambil dari katalog menu (`documentTypes`) sesuai role user,
 * jadi user tidak pernah diarahkan ke halaman yang tidak boleh ia buka.
 */
import type { RouteLocationRaw } from "vue-router";
import { MENU_FEATURES } from "@/assets/data/menu-catalog";
import type { AppNotification } from "@/features/notifications/api";
import type { RoleProfile } from "@/types/auth";

/** Notifikasi tanpa dokumen: tebak dari subjek (mis. pengingat harian follow-up). */
const SUBJECT_HINTS: { pattern: RegExp; featureId: string }[] = [
  { pattern: /follow-up/i, featureId: "follow-ups" },
  { pattern: /pembayaran|spp/i, featureId: "spp-payments" },
];

const routeForFeature = (featureId: string, role: RoleProfile | null) => {
  if (!role) return null;
  return MENU_FEATURES.find((f) => f.id === featureId)?.routes[role] ?? null;
};

export function resolveNotificationRoute(
  notification: Pick<AppNotification, "document_type" | "document_name" | "subject">,
  role: RoleProfile | null,
): RouteLocationRaw | null {
  // Pengingat kalender (api/calendar.py) & kegiatan → halaman Kalender (tersedia untuk semua role, termasuk admin).
  if (notification.document_type === "Event" || /^pengingat:/i.test(notification.subject || "")) {
    return { name: "calendar" };
  }
  if (!role) return null;
  const query = notification.document_name ? { doc: notification.document_name } : undefined;

  if (notification.document_type) {
    // Fitur pertama yang menangani doctype ini DAN tersedia untuk role user.
    for (const feature of MENU_FEATURES) {
      if (!feature.documentTypes?.includes(notification.document_type)) continue;
      const name = feature.routes[role];
      if (name) return { name, query };
    }
  }

  for (const hint of SUBJECT_HINTS) {
    if (!hint.pattern.test(notification.subject || "")) continue;
    const name = routeForFeature(hint.featureId, role);
    if (name) return { name };
  }

  // Cadangan: Perlu Tindakan (bila ada) memuat semua pekerjaan terbuka.
  const fallback = routeForFeature("action-center", role);
  return fallback ? { name: fallback } : null;
}
