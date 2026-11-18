/**
 * Gaya ikon aplikasi mode desktop: setiap menu punya warna & ikon berbeda agar mudah dibedakan.
 * Kunci = id hub / id fitur (menu-catalog.ts) / id khusus (dashboard, faq, admin-*).
 */
export type AppStyle = { icon?: string; from: string; to: string };

export const APP_STYLES: Record<string, AppStyle> = {
  dashboard: { icon: "iconoir-home-simple", from: "#38bdf8", to: "#2563eb" },
  faq: { icon: "iconoir-help-circle", from: "#fb7185", to: "#be123c" },
  calendar: { icon: "iconoir-calendar", from: "#f87171", to: "#b91c1c" },
  // hub
  "tindak-lanjut": { icon: "iconoir-warning-triangle", from: "#fb923c", to: "#dc2626" },
  admisi: { icon: "iconoir-user-plus", from: "#34d399", to: "#059669" },
  murid: { icon: "iconoir-user", from: "#818cf8", to: "#4338ca" },
  kelas: { icon: "iconoir-community", from: "#2dd4bf", to: "#0f766e" },
  penilaian: { icon: "iconoir-graduation-cap", from: "#c084fc", to: "#7c3aed" },
  spp: { icon: "iconoir-hand-cash", from: "#4ade80", to: "#15803d" },
  honor: { icon: "iconoir-wallet", from: "#facc15", to: "#ca8a04" },
  laporan: { icon: "iconoir-stats-report", from: "#22d3ee", to: "#0e7490" },
  master: { icon: "iconoir-database", from: "#94a3b8", to: "#334155" },
  // fitur yang berdiri sendiri / satu-satunya bagian hub untuk role tsb
  lms: { icon: "iconoir-open-book", from: "#f472b6", to: "#be185d" },
  "student-lms": { icon: "iconoir-open-book", from: "#f472b6", to: "#be185d" },
  "parent-portal": { icon: "iconoir-user-star", from: "#38bdf8", to: "#0369a1" },
  "student-portal": { icon: "iconoir-bookmark-book", from: "#a3e635", to: "#4d7c0f" },
  students: { icon: "iconoir-user", from: "#818cf8", to: "#4338ca" },
  "trial-schedule": { icon: "iconoir-calendar", from: "#34d399", to: "#059669" },
  sessions: { icon: "iconoir-calendar", from: "#2dd4bf", to: "#0f766e" },
  "academic-progress": { icon: "iconoir-graduation-cap", from: "#c084fc", to: "#7c3aed" },
  "spp-payments": { icon: "iconoir-wallet", from: "#4ade80", to: "#15803d" },
  reports: { icon: "iconoir-stats-report", from: "#22d3ee", to: "#0e7490" },
  "teacher-fees": { icon: "iconoir-hand-cash", from: "#facc15", to: "#ca8a04" },
  "my-slip": { icon: "iconoir-page", from: "#fbbf24", to: "#b45309" },
  // Super Administrator
  "admin-users": { icon: "iconoir-group", from: "#60a5fa", to: "#1d4ed8" },
  "admin-institutions": { icon: "iconoir-building", from: "#a78bfa", to: "#6d28d9" },
  "admin-ai": { icon: "iconoir-cpu", from: "#475569", to: "#0f172a" },
  "admin-desk": { icon: "iconoir-open-new-window", from: "#94a3b8", to: "#475569" },
  "admin-activity": { icon: "iconoir-activity", from: "#2dd4bf", to: "#0f766e" },
  "admin-replay": { icon: "iconoir-play", from: "#f87171", to: "#b91c1c" },
};

const FALLBACK: AppStyle[] = [
  { from: "#38bdf8", to: "#1d4ed8" },
  { from: "#34d399", to: "#047857" },
  { from: "#f472b6", to: "#9d174d" },
  { from: "#fb923c", to: "#c2410c" },
  { from: "#a78bfa", to: "#5b21b6" },
  { from: "#2dd4bf", to: "#0f766e" },
];

export function appStyle(id: string): AppStyle {
  if (APP_STYLES[id]) return APP_STYLES[id];
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return FALLBACK[h % FALLBACK.length];
}
