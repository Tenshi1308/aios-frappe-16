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
