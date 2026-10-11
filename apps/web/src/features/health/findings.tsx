import { StatusBadge, type Tone } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import type { Schemas } from '@/lib/api/client';

export type Finding = Schemas['FindingOut'];
export const KIND_ORDER = ['conflict', 'source_changed', 'review_due', 'broken_ref', 'missing_owner', 'reported'] as const;

type Icon = 'fork' | 'dikkat' | 'clock' | 'celiski' | 'taslak' | 'question';
const KIND: Record<string, { tone: Tone; icon: Icon }> = {
  conflict: { tone: 'celiski', icon: 'fork' },
  source_changed: { tone: 'dikkat', icon: 'dikkat' },
  review_due: { tone: 'dikkat', icon: 'clock' },
  broken_ref: { tone: 'celiski', icon: 'celiski' },
  missing_owner: { tone: 'taslak', icon: 'taslak' },
  reported: { tone: 'inceleme', icon: 'question' },
};

export function FindingKindBadge({ kind, size = 'md' }: { kind: string; size?: 'sm' | 'md' }) {
  const k = KIND[kind] ?? { tone: 'taslak' as Tone, icon: 'taslak' as Icon };
  return <StatusBadge tone={k.tone} icon={k.icon} label={tr.health.kinds[kind] ?? kind} size={size} />;
}

const str = (v: unknown): string => (typeof v === 'string' ? v : '');
const num = (v: unknown): number | null => (typeof v === 'number' ? v : null);

export interface Side {
  page_id: string;
  page_title: string;
  quote: string;
  evidence_id: string;
}

export function conflictSides(f: Finding): Side[] {
  const sides = Array.isArray(f.detail.sides) ? (f.detail.sides as unknown[]) : [];
  return sides
    .filter((x): x is Record<string, unknown> => !!x && typeof x === 'object')
    .map((x) => ({ page_id: str(x.page_id), page_title: str(x.page_title), quote: str(x.quote), evidence_id: str(x.evidence_id) }));
}

/** Bulgunun tek cümlelik açıklaması (detail alanından). */
export function describe(f: Finding): string {
  const d = f.detail;
  switch (f.kind) {
    case 'conflict':
      return tr.health.describe.conflict;
    case 'source_changed':
      return tr.health.describe.source_changed(str(d.source_title), num(d.new_revision_number));
    case 'review_due':
      return tr.health.describe.review_due(num(d.interval_days));
    case 'broken_ref':
      return d.reason === 'relation_target_inactive' ? tr.health.describe.broken_relation(tr.relations[str(d.predicate)] ?? str(d.predicate)) : tr.health.describe.broken_source(str(d.source_title));
    case 'missing_owner':
      return tr.health.describe.missing_owner;
    case 'reported':
      return tr.health.describe.reported;
    default:
      return tr.health.kinds[f.kind] ?? f.kind;
  }
}
