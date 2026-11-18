/**
 * Tata letak ikon desktop (keputusan pemilik 12 Nov 2026):
 * - Ikon berada di grid (kolom × baris) dan dapat dipindah dengan seret & lepas; posisi disimpan per user & peran
 *   (spi_fintoedu.api.desktop_prefs.set_icon_layout).
 * - Susunan bawaan: kategori **Master Data dulu**, lalu Utama, Murid & Admisi, Akademik, Keuangan (transaksi), Laporan,
 *   Portal, Pengaturan Sistem, Bantuan. Setiap kategori mulai di kolom baru (jarak antar kategori); bila layar terlalu
 *   sempit, kategori dipisah satu sel kosong.
 */
export const CELL_W = 108;
export const CELL_H = 100;

export const DESKTOP_GROUP_ORDER = [
  "Master Data",
  "Utama",
  "Murid & Admisi",
  "Akademik",
  "Keuangan",
  "Laporan",
  "Portal",
  "Pengaturan Sistem",
  "Bantuan",
];

export type Pos = [number, number]; // [kolom, baris]
export type LayoutApp = { key: string; group: string };

/** Urutkan aplikasi per kategori (urutan bawaan), urutan menu di dalam kategori dipertahankan. */
export function groupApps(apps: LayoutApp[]): LayoutApp[][] {
  const groups = new Map<string, LayoutApp[]>();
  for (const a of apps) {
    if (!groups.has(a.group)) groups.set(a.group, []);
    groups.get(a.group)!.push(a);
  }
  const rank = (g: string) => {
    const i = DESKTOP_GROUP_ORDER.indexOf(g);
    return i === -1 ? DESKTOP_GROUP_ORDER.length : i;
  };
  return [...groups.entries()].sort((a, b) => rank(a[0]) - rank(b[0])).map(([, list]) => list);
}

export function defaultLayout(apps: LayoutApp[], rows: number, cols: number): Record<string, Pos> {
  rows = Math.max(rows, 1);
  const groups = groupApps(apps);
  // Kolom yang dibutuhkan bila tiap kategori mulai di kolom baru
  const needed = groups.reduce((n, g) => n + Math.ceil(g.length / rows), 0);
  const columnPerGroup = needed <= Math.max(cols, 1);
  const out: Record<string, Pos> = {};
  let col = 0;
  let row = 0;
  groups.forEach((group, gi) => {
    if (gi > 0) {
      if (columnPerGroup) {
        if (row > 0) {
          col += 1;
          row = 0;
        }
      } else if (row > 0) {
        row += 1; // satu sel kosong sebagai jarak
        if (row >= rows) {
          col += 1;
          row = 0;
        }
      }
    }
    for (const app of group) {
      out[app.key] = [col, row];
      row += 1;
      if (row >= rows) {
        col += 1;
        row = 0;
      }
    }
  });
  return out;
}

/**
 * Posisi akhir: posisi tersimpan yang masih valid (muat di grid, tidak bertumpuk) dipakai; aplikasi baru / yang posisinya
 * tidak muat mengikuti susunan bawaan bila selnya kosong, selain itu sel kosong pertama (urut kolom).
 */
export function resolveLayout(apps: LayoutApp[], saved: Record<string, Pos> | undefined, rows: number, cols: number): Record<string, Pos> {
  rows = Math.max(rows, 1);
  const out: Record<string, Pos> = {};
  const used = new Set<string>();
  const id = (p: Pos) => `${p[0]},${p[1]}`;
  for (const a of apps) {
    const p = saved?.[a.key];
    if (p && p[1] < rows && p[0] >= 0 && p[1] >= 0 && !used.has(id(p))) {
      out[a.key] = [p[0], p[1]];
      used.add(id(p));
    }
  }
  const fallback = defaultLayout(apps, rows, cols);
  // Sel kosong pertama mulai dari posisi bawaan (urut kolom), agar ikon tetap dekat kategorinya.
  const free = (start: Pos = [0, 0]) => {
    for (let c = start[0]; ; c++) for (let r = c === start[0] ? start[1] : 0; r < rows; r++) if (!used.has(`${c},${r}`)) return [c, r] as Pos;
  };
  for (const a of apps) {
    if (out[a.key]) continue;
    const want = fallback[a.key];
    const p = want && !used.has(id(want)) ? want : free(want);
    out[a.key] = p;
    used.add(id(p));
  }
  return out;
}

/** Pindahkan ikon ke sel tujuan; bila sel terisi, ikon di sana bertukar tempat. */
export function moveIcon(layout: Record<string, Pos>, key: string, target: Pos): Record<string, Pos> {
  const next = { ...layout };
  const from = next[key];
  const occupant = Object.keys(next).find((k) => k !== key && next[k][0] === target[0] && next[k][1] === target[1]);
  if (occupant && from) next[occupant] = [from[0], from[1]];
  next[key] = [target[0], target[1]];
  return next;
}
