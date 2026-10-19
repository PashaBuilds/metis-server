import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { Button, EmptyState, Skeleton, useToast } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { formatDateTime } from '@/lib/format';
import { lineDiff } from '@/lib/diff';
import { useReducedMotion } from '@/lib/hooks';
import { Banner } from '@/features/shared/Banner';
import { BodyDiff, ClaimDiffTable } from '@/features/shared/Diff';
import { Figure } from '@/features/shared/Figure';
import { Attachments } from '@/features/shared/Attachments';
import { ChangeStateBadge, OriginBadge } from '@/features/shared/kinds';
import { messageOf } from '@/features/shared/hooks';
import { DecisionPanel } from './DecisionPanel';
import s from './RecordDetail.module.css';

const route = getRouteApi('/app/kayitlar/$changeId');
type Change = Schemas['ChangeDetailOut'];
type Item = Schemas['ItemView'];

export function RecordDetailPage() {
  const { changeId } = route.useParams();
  const query = useQuery({
    queryKey: ['change', changeId],
    queryFn: () => api.get<Change>(`/changes/${changeId}`),
  });
  if (query.isLoading)
    return (
      <div className={s.loading} aria-busy="true">
        <Skeleton width="50%" height={30} />
        <Skeleton width="30%" height={20} />
        <Skeleton height={160} />
      </div>
    );
  if (query.isError || !query.data) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <EmptyState title={notFound ? tr.errors.NOT_FOUND! : tr.shared.loadError} actions={<Link to="/kayitlar">{tr.records.title}</Link>}>
        {!notFound && messageOf(query.error)}
      </EmptyState>
    );
  }
  return <RecordView change={query.data} />;
}

function StateChip({ state }: { state: string }) {
  const reduce = useReducedMotion();
  return (
    <span className={s.stateSlot} aria-live="polite">
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={state}
          className={s.stateInner}
          initial={reduce ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduce ? { opacity: 0, transition: { duration: 0 } } : { opacity: 0, y: -6 }}
          transition={{ duration: 0.18, ease: [0.2, 0.7, 0.2, 1] }}
        >
          <ChangeStateBadge state={state} />
        </motion.span>
      </AnimatePresence>
    </span>
  );
}

function RecordView({ change }: { change: Change }) {
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const open = ['draft', 'in_review', 'approved'].includes(change.state);
  const outdated = open && change.items.some((i) => i.base && !i.base_is_current);
  const rebase = useMutation({
    mutationFn: () => api.post<Change>(`/changes/${change.id}/rebase`),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ['changes', change.project_id] });
      toast.show(tr.record.rebased);
      navigate({ to: '/kayitlar/$changeId', params: { changeId: d.id } });
    },
    onError: (e) => toast.show(messageOf(e), { tone: 'error' }),
  });
  const contextCount = change.reviews.length + (change.predecessor_id ? 1 : 0) + (change.successor_id ? 1 : 0) + change.relations.length;

  return (
    <div className={s.layout}>
      <div className={s.main}>
        <Link to="/kayitlar" className={s.back}>
          <ChevronLeft size={16} aria-hidden />
          {tr.records.title}
        </Link>
        <header className={s.header}>
          <h1 className={s.title}>{change.title}</h1>
          <div className={s.badges}>
            <OriginBadge origin={change.origin} />
            <StateChip state={change.state} />
            {change.reviews.some((r) => r.policy === 'owner_review' && r.decision === 'approve') && <span className={s.ownerBadge}>{tr.shared.ownerReview}</span>}
          </div>
          <p className={s.people}>
            <span>{tr.records.by(change.author_name)}</span>
            {change.requester_name && <span>{tr.records.requestedBy(change.requester_name)}</span>}
            <time dateTime={change.updated_at}>{formatDateTime(change.updated_at)}</time>
          </p>
        </header>

        {outdated && (
          <Banner
            actions={
              <Button size="sm" onClick={() => rebase.mutate()} loading={rebase.isPending}>
                {tr.record.rebase}
              </Button>
            }
          >
            {tr.record.baseOutdated}
          </Banner>
        )}
        {change.kind === 'withdrawal' && <Banner tone="bilgi">{tr.record.withdrawalNote}</Banner>}
        {change.summary && <p className={s.changeNote}>{change.summary}</p>}

        {change.items.map((item) => (
          <ItemDiff key={item.id} item={item} />
        ))}

        <details className={s.context}>
          <summary>
            <ChevronRight size={16} aria-hidden className={s.chev} />
            {tr.record.context}
            <span className={s.countBadge}>{contextCount + 1}</span>
          </summary>
          <div className={s.contextBody}>
            <ol className={s.timeline}>
              <li>
                <span className={s.tlDot} aria-hidden />
                <div>
                  <p>{tr.record.created(change.author_name)}</p>
                  <time className={s.time} dateTime={change.created_at}>
                    {formatDateTime(change.created_at)}
                  </time>
                </div>
              </li>
              {change.reviews.map((r) => (
                <li key={r.id}>
                  <span className={s.tlDot} aria-hidden />
                  <div>
                    <p>
                      <strong>{r.reviewer_name}</strong> {tr.record.reviewDecisions[r.decision] ?? r.decision}
                    </p>
                    {r.reason && <p className={s.reviewReason}>{r.reason}</p>}
                    {!r.hash_matches && r.decision === 'approve' && <p className={s.stale}>{tr.record.staleApproval}</p>}
                    <time className={s.time} dateTime={r.created_at}>
                      {formatDateTime(r.created_at)}
                    </time>
                  </div>
                </li>
              ))}
            </ol>
            {(change.predecessor_id || change.successor_id) && (
              <div className={s.links}>
                {change.predecessor_id && (
                  <Link to="/kayitlar/$changeId" params={{ changeId: change.predecessor_id }}>
                    {tr.record.predecessor}
                  </Link>
                )}
                {change.successor_id && (
                  <Link to="/kayitlar/$changeId" params={{ changeId: change.successor_id }}>
                    {tr.record.successor}
                  </Link>
                )}
              </div>
            )}
            {change.relations.length > 0 && (
              <div>
                <h3 className={s.subTitle}>{tr.record.relations}</h3>
                <ul className={s.relList}>
                  {change.relations.map((r) => (
                    <li key={r.relation_id}>
                      <span>{r.subject_title}</span> <span className={s.pred}>{tr.relations[r.predicate] ?? r.predicate}</span> <span>{r.object_title}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </details>
      </div>
      <div className={s.side}>
        <DecisionPanel change={change} />
      </div>
    </div>
  );
}

function ItemDiff({ item }: { item: Item }) {
  const c = item.summary_counts;
  const counts = [
    c.added ? tr.record.summaryAdded(c.added) : null,
    c.changed ? tr.record.summaryChanged(c.changed) : null,
    c.removed ? tr.record.summaryRemoved(c.removed) : null,
  ].filter((x): x is string => !!x);
  const lines = lineDiff(item.base?.body_md ?? '', item.proposed?.body_md ?? '');
  const bodyChanged = lines.some((l) => l.op !== 'same');
  const target = item.action === 'withdraw' ? tr.record.withdrawPage : !item.base ? tr.record.newPage : null;
  const figs = item.proposed?.figures ?? [];
  const figKey = (fs: typeof figs) => fs.map((f) => `${f.source_revision_id}|${f.caption}`).join(';');
  const figsChanged = figKey(item.base?.figures ?? []) !== figKey(figs);
  return (
    <section className={s.item} aria-label={item.proposed?.title ?? item.base?.title ?? ''}>
      <ul className={s.summary}>
        <li>{counts.length ? counts.join(', ') : tr.record.summaryNone}</li>
        <li>{item.scope_changed ? tr.record.scopeChanged : tr.record.scopeSame}</li>
        <li>
          {target ?? (
            <Link to="/bilgi/$pageId" params={{ pageId: item.page_id }} search={{}}>
              {item.base?.title}
            </Link>
          )}
        </li>
      </ul>
      {item.checks.map((ch) => (
        <Banner key={ch}>{tr.record.checks[ch] ?? ch}</Banner>
      ))}
      <ClaimDiffTable diff={item.claim_diff} proposedClaims={item.proposed?.claims} beforeLabel={tr.record.before} afterLabel={tr.record.proposed} />
      {figs.length > 0 && (
        <section className={s.figures} aria-label={tr.figures.title}>
          <h3 className={s.figuresTitle}>
            {tr.figures.title}
            {figsChanged && item.base && <span className={s.countBadge}>{tr.diff.changed}</span>}
          </h3>
          <div className={s.figuresGrid}>
            {figs.map((f) => (
              <Figure key={f.ord} figure={f} n={f.ord} />
            ))}
          </div>
        </section>
      )}
      <Attachments items={item.proposed?.attachments ?? []} headingLevel={3} />
      {bodyChanged && (
        <details className={s.bodyDetails}>
          <summary>
            <ChevronRight size={16} aria-hidden className={s.chev} />
            {tr.record.bodyDiff}
          </summary>
          <BodyDiff lines={lines} />
        </details>
      )}
    </section>
  );
}
