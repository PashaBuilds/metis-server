import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { StatusBadge, type Tone } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import { subscribeSse } from '@/lib/api/sse';
import { apiUrl } from '@/lib/api/base';

export const ACTIVE_STATES = new Set(['queued', 'running', 'awaiting_input']);

type Icon = 'clock' | 'spin' | 'question' | 'onay' | 'celiski' | 'ban' | 'dikkat';
const STATE: Record<string, { tone: Tone; icon: Icon }> = {
  queued: { tone: 'taslak', icon: 'clock' },
  running: { tone: 'inceleme', icon: 'spin' },
  awaiting_input: { tone: 'dikkat', icon: 'question' },
  completed: { tone: 'onay', icon: 'onay' },
  failed: { tone: 'celiski', icon: 'celiski' },
  cancelled: { tone: 'taslak', icon: 'ban' },
  budget_exceeded: { tone: 'dikkat', icon: 'dikkat' },
};

export function JobStateBadge({ state, size = 'md' }: { state: string; size?: 'sm' | 'md' }) {
  const st = STATE[state] ?? { tone: 'taslak' as Tone, icon: 'clock' as Icon };
  return <StatusBadge tone={st.tone} icon={st.icon} label={tr.jobs.states[state] ?? state} size={size} />;
}

export function jobErrorText(code: string | null | undefined): string | null {
  if (!code) return null;
  return tr.jobs.errors[code] ?? tr.jobs.errorGeneric;
}

/**
 * Görev olaylarını SSE ile izler; her olayda ilgili sorguları tazeler (polling yok).
 * `end` olayı ya da bileşen kapanınca bağlantı kapanır.
 */
export function useJobEvents(jobIds: string[], invalidate: readonly (readonly unknown[])[]) {
  const qc = useQueryClient();
  const key = jobIds.join(',');
  const invKey = JSON.stringify(invalidate);
  useEffect(() => {
    if (!key) return;
    const ctrl = new AbortController();
    const keys = JSON.parse(invKey) as unknown[][];
    for (const id of key.split(',')) {
      subscribeSse(
        apiUrl(`/jobs/${id}/events`),
        () => {
          for (const k of keys) void qc.invalidateQueries({ queryKey: k });
        },
        { signal: ctrl.signal, isDone: (e) => e.event === 'end' },
      );
    }
    return () => ctrl.abort();
  }, [key, invKey, qc]);
}
