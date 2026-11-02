/** Format tanggal waktu lokal id-ID untuk field creation/expires_at dari API. */
export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return '';
  const d = value instanceof Date ? value : new Date(String(value).replace(' ', 'T'));
  if (Number.isNaN(d.getTime())) return String(value ?? '');
  return d.toLocaleString('id-ID', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Durasi milidetik → teks ringkas detik. */
export function formatDurationMs(ms: number | undefined): string {
  if (!ms || ms < 0) return '0 dtk';
  return `${(ms / 1000).toFixed(1)} dtk`;
}

/** Format jumlah token ringkas (contoh: 2700 -> 2.7K, 18300 -> 18.3K, 128000 -> 128K, 1M). */
export function formatTokenCount(n: number | undefined): string {
  if (!n || n < 0) return '0';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
  if (n >= 100_000) return `${Math.round(n / 1_000)}K`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, '')}K`;
  return String(Math.round(n));
}

/** Teks JSON rapi untuk panel detail; gagal parse → string apa adanya. */
export function prettyJson(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** Label ringkas satu langkah trace untuk UI (ringkasan & jendela detail). */
export function traceStepLabel(event: { type: string; [key: string]: unknown }): string {
  switch (event.type) {
    case 'trace_delegate_start':
      return `Delegasi ke ${(event as { to?: string }).to ?? ''}`;
    case 'trace_subagent_prompt':
      return `${(event as { agent?: string }).agent ?? ''}: tugas diterima`;
    case 'trace_subagent_tool':
      return `${(event as { agent?: string }).agent ?? ''} menjalankan ${(event as { tool?: string }).tool ?? ''}`;
    case 'trace_subagent_result':
      return `${(event as { agent?: string }).agent ?? ''}: ${(event as { status?: string }).status ?? ''}`;
    case 'trace_cross_branch':
      return `Konsultasi lintas cabang${(event as { to_branch?: string }).to_branch ? ` → ${(event as { to_branch?: string }).to_branch}` : ''}`;
    default:
      return event.type;
  }
}

/** Ikon kategori untuk item activity feed trace. */
export function traceStepIcon(event: { type: string }): string {
  switch (event.type) {
    case 'trace_delegate_start':
    case 'trace_subagent_prompt':
      return 'users';
    case 'trace_subagent_tool':
      return 'wrench';
    case 'trace_subagent_result':
      return 'check';
    case 'trace_cross_branch':
      return 'arrow-right';
    default:
      return 'sparkle';
  }
}

/** Subteks satu baris dari isi event (args/summary/instrusi), tanpa key internal. */
export function traceStepSubtext(event: { type: string; [key: string]: unknown }): string {
  let raw = '';
  if (event.type === 'trace_delegate_start') raw = String(event.instruction ?? '');
  else if (event.type === 'trace_subagent_prompt') raw = String(event.task_prompt ?? '');
  else if (event.type === 'trace_subagent_tool') {
    const args = (event.args ?? {}) as Record<string, unknown>;
    raw = Object.entries(args)
      .filter(([, v]) => typeof v === 'string' || typeof v === 'number')
      .map(([, v]) => String(v))
      .join(' · ');
  } else if (event.type === 'trace_subagent_result') raw = String(event.summary ?? '');
  else if (event.type === 'trace_cross_branch') {
    const payload = (event.payload ?? {}) as Record<string, unknown>;
    raw = Object.values(payload)
      .filter((v) => typeof v === 'string' || typeof v === 'number')
      .map((v) => String(v))
      .join(' · ');
  }
  const clean = raw.replace(/\s+/g, ' ').trim();
  return clean.length > 80 ? `${clean.slice(0, 77)}…` : clean;
}

/** Ukuran berkas manusiawi (B/KB/MB). */
export function formatBytes(bytes: number | undefined): string {
  if (!bytes || bytes <= 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Format angka tampilan untuk kartu/sel modul (tidak menghitung ulang). */
export function formatNumber(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '0';
  const num = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(num)) return String(value);
  return num.toLocaleString('id-ID');
}

/** Format mata uang tampilan dari server currency (tanpa kalkulasi klien). */
export function formatCurrency(
  value: number | string | null | undefined,
  currency?: string,
): string {
  if (value === null || value === undefined || value === '') return '—';
  const num = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(num)) return String(value);
  const code = (currency || '').trim().toUpperCase();
  if (code) {
    try {
      return new Intl.NumberFormat('id-ID', {
        style: 'currency',
        currency: code,
        maximumFractionDigits: 0,
      }).format(num);
    } catch {
      return `${code} ${num.toLocaleString('id-ID')}`;
    }
  }
  return num.toLocaleString('id-ID');
}

/** Format tanggal YYYY-MM-DD dari server menjadi tampilan lokal ringkas. */
export function formatShortDate(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  const str = String(value);
  const d = new Date(str.includes('T') ? str : `${str}T00:00:00`);
  if (Number.isNaN(d.getTime())) return str;
  return d.toLocaleDateString('id-ID', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}
