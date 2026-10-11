/** Tarih/sayı biçimleri. Zaman UTC saklanır; UI yerel saat:dakika gösterir. */

const dateTime = new Intl.DateTimeFormat('tr-TR', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

const timeOnly = new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit' });
const dateOnly = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' });

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : dateTime.format(d).replace(',', '');
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : dateOnly.format(d);
}

/** Bugünse yalnız ss:dd, değilse gün.ay.yıl ss:dd. */
export function formatWhen(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  const now = new Date();
  if (d.toDateString() === now.toDateString()) return `Bugün ${timeOnly.format(d)}`;
  return formatDateTime(value);
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'ölçülmedi';
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1).replace('.', ',')} sn`;
}

export function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'ölçülmedi';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = value;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i ? 1 : 0).replace('.', ',')} ${units[i]}`;
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'ölçülmedi';
  return `%${(value * 100).toFixed(1).replace('.', ',')}`;
}
