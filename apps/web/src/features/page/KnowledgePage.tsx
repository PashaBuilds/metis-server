import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router';
import { ArrowLeft, Flag, History, MessagesSquare, MoreHorizontal, PencilLine, Trash2, Undo2 } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Button, ConfirmDialog, Dialog, EmptyState, Field, Skeleton, StatusBadge, Textarea, useToast } from '@/design/primitives';
import { EvidenceStripe, SourceKindIcon, ViaMark, useIz } from '@/design/iz';
import { ScopeChips } from '@/app/ScopeBar';
import { useSession } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { formatDateTime } from '@/lib/format';
import { Banner } from '@/features/shared/Banner';
import { FreshnessBadge, PageKindIcon, PageKindLabel } from '@/features/shared/kinds';
import { Markdown } from '@/features/shared/Markdown';
import { RowMenu } from '@/features/shared/RowMenu';
import { messageOf, useUndoableDelete } from '@/features/shared/hooks';
import { asScope } from '@/features/shared/scope';
import { HistoryDrawer } from './HistoryDrawer';
import s from './Knowledge.module.css';

const route = getRouteApi('/app/bilgi/$pageId');
type PageDetail = Schemas['PageDetailOut'];
type ClaimView = Schemas['ClaimView'];

const SECTIONS = [
  { id: 'aciklama', label: tr.page.body },
  { id: 'iddialar', label: tr.page.claims },
  { id: 'sinirlar', label: tr.page.unknowns },
  { id: 'ilgili', label: tr.page.relations },
] as const;

export function KnowledgePage() {
  const { pageId } = route.useParams();
  const { rev } = route.useSearch();
  const query = useQuery({
    queryKey: ['page', pageId, rev ?? null],
    queryFn: () => api.get<PageDetail>(`/pages/${pageId}`, { rev }),
  });
  if (query.isLoading)
    return (
      <div className={s.loading} aria-busy="true">
        <Skeleton width={180} height={24} />
        <Skeleton width="60%" height={34} />
        <Skeleton width="80%" height={16} />
        <Skeleton height={120} />
      </div>
    );
  if (query.isError || !query.data) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <EmptyState title={notFound ? tr.errors.NOT_FOUND! : tr.shared.loadError} actions={<Link to="/bilgi">{tr.library.title}</Link>}>
        {!notFound && messageOf(query.error)}
      </EmptyState>
    );
  }
  return <PageView page={query.data} />;
}

function PageView({ page }: { page: PageDetail }) {
  const session = useSession();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const undoableDelete = useUndoableDelete();
  const r = page.revision;
  const claimsByOrd = useMemo(() => new Map(r.claims.map((c) => [c.ord, c])), [r.claims]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const canModerate = session.roles.has('reviewer') || session.roles.has('steward');
  const canContribute = session.roles.has('contributor');
  const withdrawn = page.lifecycle === 'withdrawn';
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['page', page.page_id] });
    qc.invalidateQueries({ queryKey: ['pages', page.project_id] });
    qc.invalidateQueries({ queryKey: ['domains', page.project_id] });
  };
  const unknowns = r.unknowns.filter((u): u is string => typeof u === 'string');
  const tocSections = SECTIONS.filter(
    (x) => x.id === 'aciklama' || (x.id === 'iddialar' && r.claims.length > 0) || (x.id === 'sinirlar' && unknowns.length > 0) || (x.id === 'ilgili' && page.relations.length > 0),
  );

  return (
    <div className={s.wrap}>
    <div className={s.layout}>
      <article className={s.article} aria-labelledby="page-title">
        <div className={s.banners}>
          {!page.is_published_revision && (
            <Banner
              tone="bilgi"
              actions={
                <Link to="/bilgi/$pageId" params={{ pageId: page.page_id }} search={{}} className={s.bannerLink}>
                  {tr.page.backToCurrent}
                </Link>
              }
            >
              {tr.page.bannerOldRevision}
            </Banner>
          )}
          {withdrawn && (
            <Banner
              tone="celiski"
              actions={
                canContribute ? (
                  <Link to="/katki" search={{ page: page.page_id }} className={s.bannerLink}>
                    {tr.shared.suggestEdit}
                  </Link>
                ) : undefined
              }
            >
              {tr.page.bannerWithdrawn}
            </Banner>
          )}
          {!withdrawn && page.freshness === 'dependency_changed' && (
            <Banner
              actions={
                canContribute ? (
                  <Link to="/katki" search={{ page: page.page_id }} className={s.bannerLink}>
                    {tr.shared.suggestEdit}
                  </Link>
                ) : undefined
              }
            >
              {tr.page.bannerDependency}
            </Banner>
          )}
          {page.findings.length > 0 && (
            <Banner
              actions={
                <Link to="/saglik" search={{}} className={s.bannerLink}>
                  {tr.page.openHealth}
                </Link>
              }
            >
              {tr.page.bannerFindings(page.findings.length)}
            </Banner>
          )}
          {page.open_change_ids.length > 0 && (
            <Banner
              tone="bilgi"
              actions={
                <Link to="/kayitlar/$changeId" params={{ changeId: page.open_change_ids[0]! }} className={s.bannerLink}>
                  {tr.page.openChange}
                </Link>
              }
            >
              {tr.page.openChanges(page.open_change_ids.length)}
            </Banner>
          )}
        </div>

        <header className={s.header}>
          <div className={s.badges}>
            <PageKindLabel kind={r.kind} />
            {withdrawn ? <StatusBadge tone="celiski" label={tr.shared.withdrawnBadge} /> : <FreshnessBadge freshness={page.freshness} />}
          </div>
          <h1 id="page-title" className={s.title}>
            {r.title}
          </h1>
          {r.summary && <p className={s.summary}>{r.summary}</p>}
          <ScopeChips scope={asScope(r.scope)} />
          {page.approved_by && (
            <p className={s.approved}>
              <span>{tr.shared.approvedBy(page.approved_by)}</span>
              <time dateTime={page.approved_at ?? undefined} className={s.time}>
                {formatDateTime(page.approved_at)}
              </time>
              {page.review_policy_badge === 'owner_review' && <span className={s.ownerBadge}>{tr.shared.ownerReview}</span>}
            </p>
          )}
        </header>

        <section id="aciklama" className={s.section} aria-labelledby="aciklama-h">
          <h2 id="aciklama-h" className={s.sectionTitle}>
            {tr.page.body}
          </h2>
          <div className={s.reading}>
            {page.paragraphs.map((p, i) => (
              <EvidenceStripe key={i} count={p.claim_ords.length}>
                <Paragraph text={p.text} marks={p.claim_ords.map((ord) => claimsByOrd.get(ord)).filter((c): c is ClaimView => !!c)} />
              </EvidenceStripe>
            ))}
          </div>
        </section>

        {r.claims.length > 0 && (
        <section id="iddialar" className={s.section} aria-labelledby="iddialar-h">
          <h2 id="iddialar-h" className={s.sectionTitle}>
            {tr.page.claims}
          </h2>
            <ol className={s.claims}>
              {r.claims.map((c) => (
                <li key={c.id} className={s.claim}>
                  <span className={s.claimOrd} aria-hidden>
                    {c.ord}
                  </span>
                  <div className={s.claimBody}>
                    <p className={s.claimText}>
                      {c.statement}
                      {c.evidence.map((ev) => (
                        <ViaMark key={ev.evidence_id} n={c.ord} target={{ key: `list:${c.id}:${ev.evidence_id}`, evidenceId: ev.evidence_id, claimId: c.id, label: ev.source_title }} />
                      ))}
                    </p>
                    <span className={s.claimKind}>{tr.claimKinds[c.kind] ?? c.kind}</span>
                  </div>
                </li>
              ))}
            </ol>
        </section>
        )}

        {unknowns.length > 0 && (
        <section id="sinirlar" className={s.section} aria-labelledby="sinirlar-h">
          <h2 id="sinirlar-h" className={s.sectionTitle}>
            {tr.page.unknowns}
          </h2>
            <ul className={s.unknowns}>
              {unknowns.map((u, i) => (
                <li key={i}>{u}</li>
              ))}
            </ul>
        </section>
        )}

        {page.relations.length > 0 && (
        <section id="ilgili" className={s.section} aria-labelledby="ilgili-h">
          <h2 id="ilgili-h" className={s.sectionTitle}>
            {tr.page.relations}
          </h2>
            <ul className={s.relations}>
              {page.relations.map((rel) => {
                const label = (rel.direction === 'in' ? tr.relationsIn : tr.relations)[rel.predicate] ?? rel.predicate;
                return (
                  <li key={rel.relation_id} className={s.relation}>
                    <span className={s.predicate}>
                      {rel.direction === 'in' && <ArrowLeft size={14} aria-hidden />}
                      {label}
                    </span>
                    <Link to="/bilgi/$pageId" params={{ pageId: rel.other_page_id }} search={{}} className={s.relLink}>
                      <PageKindIcon kind={rel.other_kind} size={15} />
                      <span>{rel.other_title}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
        </section>
        )}

        <div className={s.actionBar} role="toolbar" aria-label={tr.common.more}>
          <Link to="/mentor" search={{ q: r.title }} className={s.actionLink}>
            <MessagesSquare size={16} aria-hidden />
            {tr.page.askTopic}
          </Link>
          {canContribute && (
            <Link to="/katki" search={{ page: page.page_id }} className={s.actionLink}>
              <PencilLine size={16} aria-hidden />
              {tr.shared.suggestEdit}
            </Link>
          )}
          <Button variant="ghost" icon={<History size={16} aria-hidden />} onClick={() => setHistoryOpen(true)}>
            {tr.page.history}
          </Button>
          <RowMenu
            label={tr.common.more}
            trigger={
              <button type="button" className={s.moreBtn} aria-label={tr.common.more}>
                <MoreHorizontal size={18} aria-hidden />
              </button>
            }
            actions={[
              { label: tr.page.report, icon: <Flag size={15} />, onSelect: () => setReportOpen(true) },
              ...(canModerate && !withdrawn ? [{ label: tr.page.withdraw, icon: <Undo2 size={15} />, onSelect: () => setWithdrawOpen(true) }] : []),
              ...(canModerate ? [{ label: tr.common.delete, icon: <Trash2 size={15} />, danger: true, separatorBefore: true, onSelect: () => setDeleteOpen(true) }] : []),
            ]}
          />
        </div>
      </article>

      <aside className={s.aside} aria-label={tr.page.toc}>
        {tocSections.length > 1 && <Toc sections={tocSections} />}
        {page.sources.length > 0 && <SourceList sources={page.sources} />}
      </aside>

      <HistoryDrawer open={historyOpen} onOpenChange={setHistoryOpen} pageId={page.page_id} />
      <ReportDialog open={reportOpen} onOpenChange={setReportOpen} pageId={page.page_id} onDone={invalidate} />
      <WithdrawDialog
        open={withdrawOpen}
        onOpenChange={setWithdrawOpen}
        pageId={page.page_id}
        onDone={() => {
          invalidate();
          toast.show(tr.page.withdrawn);
        }}
      />
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={tr.shared.deletePageTitle}
        description={tr.shared.deletePageDesc}
        confirmLabel={tr.common.delete}
        danger
        onConfirm={async () => {
          await undoableDelete({
            del: () => api.del(`/pages/${page.page_id}`),
            restore: () => api.post(`/pages/${page.page_id}/restore`),
            onDone: () => {
              invalidate();
              navigate({ to: '/bilgi' });
            },
            onRestored: () => {
              invalidate();
              navigate({ to: '/bilgi/$pageId', params: { pageId: page.page_id }, search: {} });
            },
          }).catch(() => undefined);
        }}
      />
    </div>
    </div>
  );
}

/** Son blok paragraf ise via işaretleri paragrafın içine, değilse ardına eklenir. */
function Paragraph({ text, marks }: { text: string; marks: ClaimView[] }) {
  const viaMarks: ReactNode = marks.map((c) => {
    const ev = c.evidence[0];
    if (!ev) return null;
    return <ViaMark key={c.id} n={c.ord} target={{ key: `${c.id}:${ev.evidence_id}`, evidenceId: ev.evidence_id, claimId: c.id, label: ev.source_title }} />;
  });
  const lastBlock = text.trim().split(/\n\s*\n/).pop() ?? '';
  const isPara = !/^\s*([-*+]\s|\d+\.\s|```|#|>|\|)/.test(lastBlock);
  return (
    <div className={s.para}>
      {isPara ? (
        <p className={s.p}>
          <Markdown inline>{text}</Markdown>
          {viaMarks}
        </p>
      ) : (
        <>
          <Markdown>{text}</Markdown>
          {marks.length > 0 && <p className={s.p}>{viaMarks}</p>}
        </>
      )}
    </div>
  );
}

type TocSection = (typeof SECTIONS)[number];

function Toc({ sections }: { sections: TocSection[] }) {
  const [active, setActive] = useState<string>(SECTIONS[0].id);
  const key = sections.map((x) => x.id).join(',');
  useEffect(() => {
    const els = sections.map((x) => document.getElementById(x.id)).filter((e): e is HTMLElement => !!e);
    const visible = new Map<string, boolean>();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) visible.set(e.target.id, e.isIntersecting);
        const first = sections.find((x) => visible.get(x.id));
        if (first) setActive(first.id);
      },
      { rootMargin: '-64px 0px -55% 0px', threshold: 0 },
    );
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return (
    <nav className={s.toc} aria-labelledby="toc-h">
      <h2 id="toc-h" className={s.asideTitle}>
        {tr.page.toc}
      </h2>
      <ul>
        {sections.map((x) => (
          <li key={x.id}>
            <a
              href={`#${x.id}`}
              className={[s.tocLink, active === x.id ? s.tocActive : ''].join(' ')}
              aria-current={active === x.id ? 'location' : undefined}
              onClick={(e) => {
                e.preventDefault();
                const el = document.getElementById(x.id);
                el?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
                el?.querySelector<HTMLElement>('h2')?.focus({ preventScroll: true });
                setActive(x.id);
              }}
            >
              {x.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function SourceList({ sources }: { sources: Schemas['SourceRow'][] }) {
  const iz = useIz();
  return (
    <section aria-labelledby="sources-h">
      <h2 id="sources-h" className={s.asideTitle}>
        {tr.page.sources}
      </h2>
      <ul className={s.sources}>
        {sources.map((src) => {
          const key = `src:${src.source_id}`;
          return (
            <li key={src.source_id}>
              <button
                type="button"
                className={[s.sourceBtn, iz.active?.key === key ? s.sourceActive : ''].join(' ')}
                data-iz-marker={key}
                aria-expanded={iz.active?.key === key}
                aria-controls="iz-panel"
                onClick={(e) => (iz.active?.key === key ? iz.close() : iz.open({ key, evidenceId: src.first_evidence_id, label: src.title }, e.currentTarget))}
              >
                <span className={s.sourceDot} data-via-dot aria-hidden />
                <SourceKindIcon kind={src.kind} size={15} />
                <span className={s.sourceTitle}>{src.title}</span>
                {!src.is_current && <span className={s.sourceOld}>{tr.page.sourceNotCurrent}</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function ReportDialog({ open, onOpenChange, pageId, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; pageId: string; onDone: () => void }) {
  const toast = useToast();
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => api.post(`/pages/${pageId}/report`, { text: text.trim() }),
    onSuccess: () => {
      toast.show(tr.page.reported);
      setText('');
      onOpenChange(false);
      onDone();
    },
    onError: (e) => setError(messageOf(e)),
  });
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) setError(null);
      }}
      title={tr.page.report}
      description={tr.page.reportDesc}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {tr.common.cancel}
          </Button>
          <Button
            variant="primary"
            loading={m.isPending}
            onClick={() => {
              if (!text.trim()) {
                setError(tr.errors.REASON_REQUIRED!);
                return;
              }
              m.mutate();
            }}
          >
            {tr.page.reportSend}
          </Button>
        </>
      }
    >
      <Field label={tr.page.reportField} error={error}>
        {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} invalid={!!error} value={text} onChange={(e) => setText(e.target.value)} />}
      </Field>
    </Dialog>
  );
}

function WithdrawDialog({ open, onOpenChange, pageId, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; pageId: string; onDone: () => void }) {
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => api.post(`/pages/${pageId}/withdraw`, { reason: reason.trim() }),
    onSuccess: () => {
      setReason('');
      onOpenChange(false);
      onDone();
    },
    onError: (e) => setError(messageOf(e)),
  });
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) setError(null);
      }}
      title={tr.page.withdrawTitle}
      description={tr.page.withdrawDesc}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {tr.common.cancel}
          </Button>
          <Button
            variant="danger"
            loading={m.isPending}
            onClick={() => {
              if (!reason.trim()) {
                setError(tr.errors.REASON_REQUIRED!);
                return;
              }
              m.mutate();
            }}
          >
            {tr.page.withdraw}
          </Button>
        </>
      }
    >
      <Field label={tr.page.withdrawReason} hint={tr.page.withdrawReasonHint} error={error}>
        {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} invalid={!!error} value={reason} onChange={(e) => setReason(e.target.value)} required />}
      </Field>
    </Dialog>
  );
}

