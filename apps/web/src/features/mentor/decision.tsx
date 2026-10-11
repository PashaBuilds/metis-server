import { StatusBadge, type Tone } from '@/design/primitives';
import { tr } from '@/i18n/tr';

type Icon = 'onay' | 'dikkat' | 'celiski' | 'fork' | 'searchx' | 'taslak';

const DECISION: Record<string, { tone: Tone; icon?: Icon }> = {
  SUPPORTED: { tone: 'onay' },
  PARTIAL: { tone: 'dikkat' },
  NEEDS_SCOPE: { tone: 'dikkat' },
  CONFLICTING: { tone: 'celiski', icon: 'fork' },
  NO_EVIDENCE: { tone: 'taslak', icon: 'searchx' },
  RETRIEVAL_UNAVAILABLE: { tone: 'celiski' },
  MODEL_UNAVAILABLE: { tone: 'celiski' },
  VALIDATION_FAILED: { tone: 'celiski' },
};

export const ANSWERED = new Set(['SUPPORTED', 'PARTIAL']);

/** Karar rozeti: ikon + Türkçe etiket (renk tek başına sinyal değil). */
export function DecisionBadge({ decision, size = 'md' }: { decision: string; size?: 'sm' | 'md' }) {
  const d = DECISION[decision] ?? { tone: 'taslak' as Tone };
  return <StatusBadge tone={d.tone} icon={d.icon} label={tr.decisions[decision] ?? decision} size={size} />;
}
