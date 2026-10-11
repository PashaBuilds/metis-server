import { Bot, Cpu, FlaskConical, GraduationCap, Lightbulb, ListOrdered, Scale, Siren, Table2, User, type LucideIcon } from 'lucide-react';
import { StatusBadge, type Tone } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import s from './shared.module.css';

const PAGE_KIND_ICONS: Record<string, LucideIcon> = {
  concept: Lightbulb,
  component: Cpu,
  procedure: ListOrdered,
  decision: Scale,
  incident: Siren,
  validation: FlaskConical,
  table: Table2,
  learning_path: GraduationCap,
};

export const PAGE_KINDS = Object.keys(PAGE_KIND_ICONS);
export const FRESHNESS = ['current', 'review_due', 'dependency_changed', 'unknown'] as const;
export const CLAIM_KINDS = ['expert_statement', 'design_intent', 'observed_behavior', 'tested_result', 'hypothesis', 'derived_calculation'] as const;
export const SOURCE_KINDS = ['note', 'document', 'code', 'table', 'test', 'image'] as const;

export function PageKindIcon({ kind, size = 16 }: { kind: string; size?: number }) {
  const Icon = PAGE_KIND_ICONS[kind] ?? Lightbulb;
  return <Icon size={size} aria-hidden className={s.kindIcon} />;
}

/** Sayfa türü: ikon + etiket (durum değil; nötr). */
export function PageKindLabel({ kind }: { kind: string }) {
  return (
    <span className={s.kindLabel}>
      <PageKindIcon kind={kind} size={14} />
      {tr.pageKinds[kind] ?? kind}
    </span>
  );
}

const FRESHNESS_TONE: Record<string, { tone: Tone; icon?: 'clock' | 'dikkat' }> = {
  current: { tone: 'onay' },
  review_due: { tone: 'dikkat', icon: 'clock' },
  dependency_changed: { tone: 'dikkat' },
  unknown: { tone: 'taslak' },
};

export function FreshnessBadge({ freshness, size = 'md' }: { freshness: string; size?: 'sm' | 'md' }) {
  const t = FRESHNESS_TONE[freshness] ?? FRESHNESS_TONE.unknown!;
  return <StatusBadge tone={t.tone} icon={t.icon} label={tr.freshness[freshness] ?? freshness} size={size} />;
}

const STATE_TONE: Record<string, Tone> = {
  draft: 'taslak',
  in_review: 'inceleme',
  approved: 'onay',
  rejected: 'celiski',
  published: 'onay',
  superseded: 'taslak',
};

export function ChangeStateBadge({ state, size = 'md' }: { state: string; size?: 'sm' | 'md' }) {
  return <StatusBadge tone={STATE_TONE[state] ?? 'taslak'} label={tr.changeStates[state] ?? state} size={size} />;
}

export function OriginBadge({ origin }: { origin: string }) {
  const metis = origin === 'metis';
  const Icon = metis ? Bot : User;
  return (
    <span className={s.origin}>
      <Icon size={14} aria-hidden />
      {metis ? tr.origin.metis : tr.origin.human}
    </span>
  );
}

/** Kanıt sayısı: küçük altın via + sayı (altın yalnız kanıt için). */
export function EvidenceCount({ n }: { n: number }) {
  if (n <= 0) return null;
  return (
    <span className={s.evidenceCount} title={tr.shared.evidenceCount(n)}>
      <span className={s.evidenceDot} aria-hidden />
      <span aria-hidden>{n}</span>
      <span className="sr-only">{tr.shared.evidenceCount(n)}</span>
    </span>
  );
}
