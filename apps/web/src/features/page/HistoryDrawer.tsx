import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { ArrowLeft, GitCompare } from 'lucide-react';
import { useState } from 'react';
import { Button, Drawer, SkeletonRows, StatusBadge } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { formatDateTime } from '@/lib/format';
import type { DiffLine } from '@/lib/diff';
import { BodyDiff, ClaimDiffTable } from '@/features/shared/Diff';
import { messageOf } from '@/features/shared/hooks';
import s from './Knowledge.module.css';

type HistoryRow = Schemas['HistoryRow'];

export function HistoryDrawer({ open, onOpenChange, pageId }: { open: boolean; onOpenChange: (o: boolean) => void; pageId: string }) {
  const [picked, setPicked] = useState<string[]>([]);
  const [comparing, setComparing] = useState<[string, string] | null>(null);
  const history = useQuery({
    queryKey: ['page-history', pageId],
    queryFn: () => api.get<HistoryRow[]>(`/pages/${pageId}/history`),
    enabled: open,
  });
  const rows = history.data ?? [];
  const toggle = (id: string, on: boolean) => setPicked((p) => (on ? [...p.filter((x) => x !== id), id].slice(-2) : p.filter((x) => x !== id)));
  const startCompare = () => {
    const sel = rows.filter((r) => picked.includes(r.revision_id)).sort((a, b) => a.number - b.number);
    if (sel.length === 2) setComparing([sel[0]!.revision_id, sel[1]!.revision_id]);
  };
  return (
    <Drawer
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) setComparing(null);
      }}
      title={tr.page.history}
      width={comparing ? 860 : 440}
    >
      {comparing ? (
        <CompareView pageId={pageId} a={comparing[0]} b={comparing[1]} onBack={() => setComparing(null)} />
      ) : history.isLoading ? (
        <SkeletonRows rows={4} />
      ) : history.isError ? (
        <p className={s.error}>{messageOf(history.error)}</p>
      ) : rows.length === 0 ? (
        <p className={s.muted}>{tr.page.historyEmpty}</p>
      ) : (
        <div className={s.history}>
          <p className={s.muted}>{tr.page.pickTwo}</p>
          <ol className={s.timeline}>
            {rows.map((r) => (
              <li key={r.revision_id} className={s.tlItem}>
                <span className={s.tlDot} aria-hidden />
                <div className={s.tlBody}>
                  <div className={s.tlHead}>
                    <input
                      type="checkbox"
                      className={s.tlCheck}
                      checked={picked.includes(r.revision_id)}
                      onChange={(e) => toggle(r.revision_id, e.target.checked)}
                      aria-label={tr.page.compareSelect(r.number)}
                    />
                    <strong>{tr.page.revision(r.number)}</strong>
                    {r.is_current && <StatusBadge tone="onay" label={tr.page.current} size="sm" />}
                  </div>
                  <p className={s.tlTitle}>{r.title}</p>
                  <p className={s.tlMeta}>
                    <span>{tr.page.pubKinds[r.publication_kind] ?? tr.page.pubKinds.publish}</span>
                    <time dateTime={r.published_at} className={s.time}>
                      {formatDateTime(r.published_at)}
                    </time>
                  </p>
                  <div className={s.tlLinks}>
                    <Link to="/bilgi/$pageId" params={{ pageId }} search={r.is_current ? {} : { rev: r.revision_id }} onClick={() => onOpenChange(false)}>
                      {tr.page.viewRevision}
                    </Link>
                    {r.change_set_id && (
                      <Link to="/kayitlar/$changeId" params={{ changeId: r.change_set_id }} onClick={() => onOpenChange(false)}>
                        {tr.page.openChange}
                      </Link>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ol>
          <div className={s.drawerFoot}>
            <Button variant="primary" icon={<GitCompare size={16} aria-hidden />} disabled={picked.length !== 2} onClick={startCompare}>
              {tr.page.compare}
            </Button>
          </div>
        </div>
      )}
    </Drawer>
  );
}

function CompareView({ pageId, a, b, onBack }: { pageId: string; a: string; b: string; onBack: () => void }) {
  const q = useQuery({
    queryKey: ['page-compare', pageId, a, b],
    queryFn: () => api.get<Schemas['CompareOut']>(`/pages/${pageId}/compare`, { a, b }),
  });
  const lines: DiffLine[] = (q.data?.body_diff ?? []).map((l) => ({
    op: l.op === 'add' ? 'add' : l.op === 'del' ? 'del' : 'same',
    text: typeof l.text === 'string' ? l.text : '',
  }));
  const changed = lines.some((l) => l.op !== 'same');
  return (
    <div className={s.compare}>
      <Button variant="ghost" size="sm" icon={<ArrowLeft size={15} aria-hidden />} onClick={onBack}>
        {tr.page.backToHistory}
      </Button>
      {q.isLoading && <SkeletonRows rows={4} />}
      {q.isError && <p className={s.error}>{messageOf(q.error)}</p>}
      {q.data && (
        <>
          <h3>{tr.page.compareTitle(q.data.a.number, q.data.b.number)}</h3>
          <section className={s.compareSection} aria-label={tr.page.claimDiff}>
            <h4>{tr.page.claimDiff}</h4>
            <ClaimDiffTable diff={q.data.claim_diff} proposedClaims={q.data.b.claims} beforeLabel={tr.page.revision(q.data.a.number)} afterLabel={tr.page.revision(q.data.b.number)} />
          </section>
          <section className={s.compareSection} aria-label={tr.page.bodyDiff}>
            <h4>{tr.page.bodyDiff}</h4>
            {changed ? <BodyDiff lines={lines} /> : <p className={s.muted}>{tr.page.noBodyChange}</p>}
          </section>
        </>
      )}
    </div>
  );
}
