/** Periode default daftar/laporan: tahun & bulan berjalan (keputusan pemilik 11 Nov 2026). */
export function defaultPeriod(): { year: number; month: number } {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

/** Rentang tanggal (YYYY-MM-DD) untuk tahun/bulan; month 0 = setahun penuh; year 0 = tanpa batas (null). */
export function periodRange(year: number, month: number): { from_date: string | null; to_date: string | null } {
  if (!year) return { from_date: null, to_date: null };
  const pad = (n: number) => String(n).padStart(2, "0");
  if (!month) return { from_date: `${year}-01-01`, to_date: `${year}-12-31` };
  const last = new Date(year, month, 0).getDate();
  return { from_date: `${year}-${pad(month)}-01`, to_date: `${year}-${pad(month)}-${pad(last)}` };
}
