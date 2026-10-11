import { Equal, Minus, PencilLine, Plus } from 'lucide-react';
import { ViaMark } from '@/design/iz';
import { tr } from '@/i18n/tr';
import type { Schemas } from '@/lib/api/client';
import type { DiffLine } from '@/lib/diff';
import s from './shared.module.css';

type ClaimDiff = Schemas['ClaimDiff'];
type ClaimView = Schemas['ClaimView'];

const STATUS_ICON = { added: Plus, removed: Minus, changed: PencilLine, unchanged: Equal } as const;

export function DiffStatus({ status }: { status: ClaimDiff['status'] }) {
  const Icon = STATUS_ICON[status];
  return (
    <span className={[s.diffStatus, s[`ds-${status}`]].join(' ')}>
      <Icon size={13} aria-hidden />
      {tr.diff[status]}
    </span>
  );
}

/** İddia bazlı fark: iki sütun (Önceki / Önerilen), her satırda durum işareti; önerilen iddialarda via işaretleri. */
export function ClaimDiffTable({
  diff,
  proposedClaims,
  beforeLabel,
  afterLabel,
}: {
  diff: ClaimDiff[];
  proposedClaims?: ClaimView[];
  beforeLabel: string;
  afterLabel: string;
}) {
  const byOrd = new Map((proposedClaims ?? []).map((c) => [c.ord, c]));
  const order: Record<ClaimDiff['status'], number> = { added: 1, changed: 0, removed: 2, unchanged: 3 };
  const rows = [...diff].sort((x, y) => (x.after_ord ?? 999) - (y.after_ord ?? 999) || order[x.status] - order[y.status]);
  return (
    <div className={s.claimDiff} role="table" aria-label={tr.page.claimDiff}>
      <div className={s.cdHead} role="row">
        <span role="columnheader">{beforeLabel}</span>
        <span role="columnheader">{afterLabel}</span>
      </div>
      {rows.map((d, i) => {
        const claim = d.after_ord != null ? byOrd.get(d.after_ord) : undefined;
        return (
          <div key={`${d.claim_id ?? 'x'}-${i}`} className={[s.cdRow, s[`cd-${d.status}`]].join(' ')} role="row">
            <div className={s.cdCell} role="cell" data-label={beforeLabel}>
              {d.before != null ? (
                <>
                  {d.before_ord != null && <span className={s.cdOrd}>{d.before_ord}.</span>}
                  <span className={d.status === 'removed' ? s.cdRemoved : undefined}>{d.before}</span>
                </>
              ) : (
                <span className={s.cdEmpty} aria-label={tr.diff.added}>
                  —
                </span>
              )}
            </div>
            <div className={s.cdCell} role="cell" data-label={afterLabel}>
              {d.after != null ? (
                <>
                  {d.after_ord != null && <span className={s.cdOrd}>{d.after_ord}.</span>}
                  <span>
                    {d.after}
                    {claim?.evidence.map((ev, k) => (
                      <ViaMark
                        key={ev.evidence_id + k}
                        n={claim.ord}
                        target={{ key: `diff:${claim.id}:${ev.evidence_id}`, evidenceId: ev.evidence_id, claimId: claim.id, label: ev.source_title }}
                      />
                    ))}
                  </span>
                </>
              ) : (
                <span className={s.cdEmpty}>—</span>
              )}
              <DiffStatus status={d.status} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function BodyDiff({ lines }: { lines: DiffLine[] }) {
  return (
    <div className={s.bodyDiff}>
      {lines.map((l, i) => (
        <div key={i} className={[s.bdLine, s[`bd-${l.op}`]].join(' ')}>
          <span className={s.bdSign} aria-label={l.op === 'add' ? tr.diff.addedLine : l.op === 'del' ? tr.diff.removedLine : undefined}>
            {l.op === 'add' ? '+' : l.op === 'del' ? '−' : ' '}
          </span>
          <span className={s.bdText}>{l.text || ' '}</span>
        </div>
      ))}
    </div>
  );
}
