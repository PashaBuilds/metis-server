import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router';
import { Activity, Archive, ChevronDown, CircleCheck, FilePen, GitFork, ScanSearch } from 'lucide-react';
import { useEffect, useId, useState } from 'react';
import { Button, Dialog, EmptyState, Field, Select, SkeletonRows, TabPanel, Tabs, Textarea, useToast } from '@/design/primitives';
import { PageHeader } from '@/app/Shell';
import { useSession } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { formatDateTime } from '@/lib/format';
import { Banner } from '@/features/shared/Banner';
import { messageOf } from '@/features/shared/hooks';
import { ModelSelect, useAvailableModels } from '@/features/shared/models';
import { ConflictDialog } from './ConflictDialog';
import { conflictSides, describe, FindingKindBadge, KIND_ORDER, type Finding } from './findings';
import s from './Health.module.css';

const route = getRouteApi('/app/saglik');
type Tab = 'open' | 'resolved';

export function HealthPage() {
  const session = useSession();
  const pid = session.projectId;
  const search = route.useSearch();
  const navigate = useNavigate({ from: '/saglik' });
  const tab: Tab = search.tab === 'resolved' ? 'resolved' : 'open';
  const kind = search.kind && (KIND_ORDER as readonly string[]).includes(search.kind) ? search.kind : undefined;
  const [scanOpen, setScanOpen] = useState(false);
  const [scanJob, setScanJob] = useState<string | null>(null);
  const [closing, setClosing] = useState<Finding | null>(null);
  const [withdrawing, setWithdrawing] = useState<Finding | null>(null);
  const [conflict, setConflict] = useState<string | null>(search.finding ?? null);
  useEffect(() => {
    if (search.finding) setConflict(search.finding);
  }, [search.finding]);

  const findings = useQuery({
    queryKey: ['findings', pid, tab, kind ?? null],
    queryFn: () => api.get<Schemas['FindingListOut']>(`/projects/${pid}/findings`, { state: tab, kind }),
    enabled: !!pid,
  });
  const counts = findings.data?.counts ?? {};
  const items = findings.data?.items ?? [];
  const canScan = session.roles.has('contributor') || session.roles.has('reviewer');
  const setSearch = (patch: Record<string, string | undefined>) => navigate({ search: (old) => ({ ...old, ...patch }), replace: true });

  const list = (rows: Finding[]) => (
    <ul className={s.rows}>
      {rows.map((f) => (
        <FindingRow key={f.id} f={f} onClose={() => setClosing(f)} onWithdraw={() => setWithdrawing(f)} onConflict={() => setConflict(f.id)} />
      ))}
    </ul>
  );

  return (
    <div className={s.page}>
      <PageHeader
        title={tr.health.title}
        actions={
          canScan ? (
            <Button icon={<ScanSearch size={16} aria-hidden />} onClick={() => setScanOpen(true)}>
              {tr.health.scan}
            </Button>
          ) : undefined
        }
      />
      {scanJob && (
        <div className={s.notice}>
          <Banner
            tone="bilgi"
            actions={
              <Link to="/gorevler/$jobId" params={{ jobId: scanJob }} className={s.textLink}>
                {tr.health.openJob}
              </Link>
            }
          >
            {tr.health.scanJob}
          </Banner>
        </div>
      )}
      <Tabs
        label={tr.health.title}
        value={tab}
        onValueChange={(v) => setSearch({ tab: v === 'resolved' ? 'resolved' : undefined })}
        tabs={(['open', 'resolved'] as const).map((t) => ({ value: t, label: tr.health.tabs[t], count: counts[t] ?? null }))}
      >
        {(['open', 'resolved'] as const).map((t) => (
          <TabPanel key={t} value={t}>
            <div className={s.toolbar}>
              <KindFilter value={kind ?? ''} onChange={(v) => setSearch({ kind: v || undefined })} />
            </div>
            {t !== tab ? null : findings.isLoading ? (
              <SkeletonRows rows={4} />
            ) : findings.isError ? (
              <EmptyState title={tr.shared.loadError} actions={<Button onClick={() => findings.refetch()}>{tr.common.retry}</Button>}>
                {messageOf(findings.error)}
              </EmptyState>
            ) : items.length === 0 ? (
              <EmptyState icon={<Activity size={24} />} title={tr.health.emptyTitle[t]!}>
                {tr.health.empty[t]}
              </EmptyState>
            ) : (
              list(items)
            )}
          </TabPanel>
        ))}
      </Tabs>

      <ScanDialog open={scanOpen} onOpenChange={setScanOpen} onStarted={setScanJob} />
      <CloseDialog finding={closing} onOpenChange={(o) => !o && setClosing(null)} />
      <WithdrawDialog finding={withdrawing} onOpenChange={(o) => !o && setWithdrawing(null)} />
      <ConflictDialog
        findingId={conflict}
        open={!!conflict}
        onOpenChange={(o) => {
          if (!o) {
            setConflict(null);
            if (search.finding) setSearch({ finding: undefined });
          }
        }}
      />
    </div>
  );
}

function KindFilter({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const id = useId();
  return (
    <span className={s.kindFilter}>
      <label htmlFor={id} className={s.toolLabel}>
        {tr.health.kindFilter}
      </label>
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{tr.health.allKinds}</option>
        {KIND_ORDER.map((k) => (
          <option key={k} value={k}>
            {tr.health.kinds[k]}
          </option>
        ))}
      </Select>
    </span>
  );
}

function FindingRow({ f, onClose, onWithdraw, onConflict }: { f: Finding; onClose: () => void; onWithdraw: () => void; onConflict: () => void }) {
  const session = useSession();
  const [open, setOpen] = useState(false);
  const detailId = useId();
  const isOpen = f.state === 'open';
  const canReview = session.roles.has('reviewer') || session.roles.has('steward');
  const canContribute = session.roles.has('contributor');
  const activePages = f.pages.filter((p) => p.lifecycle === 'active');
  const sides = f.kind === 'conflict' ? conflictSides(f) : [];
  const created = typeof f.created_at === 'string' ? f.created_at : null;
  const resolved = typeof f.resolved_at === 'string' ? f.resolved_at : null;
  return (
    <li className={s.row}>
      <div className={s.rowHead}>
        <div className={s.rowBadges}>
          <FindingKindBadge kind={f.kind} size="sm" />
          <span className={s.severity}>{tr.health.severity[f.severity] ?? f.severity}</span>
        </div>
        <div className={s.rowMain}>
          <p className={s.rowText}>{describe(f)}</p>
          {f.pages.length > 0 ? (
            <ul className={s.pages} aria-label={tr.health.pages}>
              {f.pages.map((p) => (
                <li key={p.page_id}>
                  <Link to="/bilgi/$pageId" params={{ pageId: p.page_id }} search={{}} className={s.pageLink}>
                    {p.title}
                  </Link>
                  {p.lifecycle !== 'active' && <span className={s.lifecycle}>{tr.lifecycle[p.lifecycle] ?? p.lifecycle}</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className={s.muted}>{tr.health.noPages}</p>
          )}
        </div>
        <time className={s.time} dateTime={(resolved ?? created) ?? undefined} title={resolved ? tr.health.resolvedAt : tr.health.createdAt}>
          {formatDateTime(resolved ?? created)}
        </time>
      </div>

      {!isOpen && (
        <p className={s.resolution}>
          <CircleCheck size={15} aria-hidden />
          <span>
            {f.resolved_by_name ? tr.health.resolvedBy(f.resolved_by_name) : tr.health.resolvedAuto}
            {f.resolution_reason && (
              <>
                {' — '}
                {f.resolution_reason}
              </>
            )}
          </span>
        </p>
      )}

      <div className={s.actions}>
        <button type="button" className={s.expand} aria-expanded={open} aria-controls={detailId} onClick={() => setOpen((o) => !o)}>
          <ChevronDown size={15} aria-hidden className={open ? s.chevOpen : undefined} />
          {open ? tr.health.hideDetails : tr.health.details}
        </button>
        {isOpen && f.kind === 'conflict' && canContribute && (
          <Button size="sm" variant="primary" icon={<GitFork size={15} aria-hidden />} onClick={onConflict}>
            {tr.health.resolve}
          </Button>
        )}
        {isOpen && canContribute && activePages[0] && (
          <Link to="/katki" search={{ page: activePages[0].page_id }} className={s.actionLink}>
            <FilePen size={15} aria-hidden />
            {tr.health.fixDraft}
          </Link>
        )}
        {isOpen && canReview && activePages.length > 0 && (
          <Button size="sm" variant="ghost" icon={<Archive size={15} aria-hidden />} onClick={onWithdraw}>
            {tr.health.withdraw}
          </Button>
        )}
        {isOpen && canReview && (
          <Button size="sm" variant="ghost" icon={<CircleCheck size={15} aria-hidden />} onClick={onClose}>
            {tr.health.close}
          </Button>
        )}
      </div>

      <div id={detailId} hidden={!open} className={s.detail}>
        {sides.length > 0 && (
          <div className={s.sides}>
            {sides.map((side, i) => (
              <div key={i} className={s.side}>
                <span className={s.sideLabel}>
                  <GitFork size={14} aria-hidden />
                  {tr.mentor.conflictSide(i + 1)}
                </span>
                <span className={s.sideTitle}>{side.page_title}</span>
                <blockquote className={s.quote}>
                  <mark>{side.quote}</mark>
                </blockquote>
              </div>
            ))}
          </div>
        )}
        {f.kind === 'reported' && typeof f.detail.text === 'string' && (
          <p>
            <strong>{tr.health.reportedText}:</strong> {f.detail.text}
          </p>
        )}
        {f.kind === 'review_due' && typeof f.detail.reviewed_at === 'string' && (
          <p>
            {tr.health.reviewedAt}: {formatDateTime(f.detail.reviewed_at)}
          </p>
        )}
        {typeof f.detail.detected_by === 'string' && <p className={s.muted}>{tr.health.detectedBy[f.detail.detected_by] ?? ''}</p>}
        <p className={s.muted}>
          {tr.health.createdAt}: {formatDateTime(created)}
        </p>
      </div>
    </li>
  );
}

function ScanDialog({ open, onOpenChange, onStarted }: { open: boolean; onOpenChange: (o: boolean) => void; onStarted: (jobId: string) => void }) {
  const session = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const models = useAvailableModels(session.projectId);
  const [model, setModel] = useState('');
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => api.post<{ job_id: string }>(`/projects/${session.projectId}/health/scan`, { model_id: model || null }),
    onSuccess: (res) => {
      onStarted(res.job_id);
      toast.show(tr.health.scanStarted);
      void qc.invalidateQueries({ queryKey: ['jobs', session.projectId] });
      onOpenChange(false);
    },
    onError: (e) => setError(messageOf(e)),
  });
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setError(null);
        onOpenChange(o);
      }}
      title={tr.health.scanTitle}
      description={tr.health.scanDesc}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {tr.common.cancel}
          </Button>
          <Button variant="primary" loading={m.isPending} onClick={() => m.mutate()}>
            {tr.health.scanStart}
          </Button>
        </>
      }
    >
      <Field label={tr.health.scanModel} error={error}>
        {({ id }) => <ModelSelect id={id} value={model} onChange={setModel} models={models.data ?? []} emptyLabel={tr.health.scanNoModel} />}
      </Field>
    </Dialog>
  );
}

const MIN_CLOSE = 8;

function CloseDialog({ finding, onOpenChange }: { finding: Finding | null; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setReason('');
    setError(null);
  }, [finding?.id]);
  const m = useMutation({
    mutationFn: () => api.post(`/findings/${finding!.id}/resolve`, { reason: reason.trim() }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['findings'] });
      void qc.invalidateQueries({ queryKey: ['inbox'] });
      toast.show(tr.health.closed);
      onOpenChange(false);
    },
    onError: (e) => setError(messageOf(e)),
  });
  return (
    <Dialog
      open={!!finding}
      onOpenChange={onOpenChange}
      title={tr.health.closeTitle}
      description={tr.health.closeDesc}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {tr.common.cancel}
          </Button>
          <Button
            variant="primary"
            loading={m.isPending}
            onClick={() => {
              if (reason.trim().length < MIN_CLOSE) return setError(tr.health.reasonShort(MIN_CLOSE));
              m.mutate();
            }}
          >
            {tr.health.close}
          </Button>
        </>
      }
    >
      <Field label={tr.health.closeReason} hint={tr.health.closeReasonHint} error={error}>
        {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} value={reason} onChange={(e) => setReason(e.target.value)} rows={3} maxLength={2000} invalid={!!error} />}
      </Field>
    </Dialog>
  );
}

function WithdrawDialog({ finding, onOpenChange }: { finding: Finding | null; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const pages = (finding?.pages ?? []).filter((p) => p.lifecycle === 'active');
  const [pageId, setPageId] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setPageId('');
    setReason('');
    setError(null);
  }, [finding?.id]);
  const target = pageId || pages[0]?.page_id || '';
  const m = useMutation({
    mutationFn: () => api.post(`/pages/${target}/withdraw`, { reason: reason.trim() }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['findings'] });
      void qc.invalidateQueries({ queryKey: ['pages'] });
      toast.show(tr.health.withdrawn);
      onOpenChange(false);
    },
    onError: (e) => setError(messageOf(e)),
  });
  return (
    <Dialog
      open={!!finding}
      onOpenChange={onOpenChange}
      title={tr.health.withdrawTitle}
      description={tr.health.withdrawDesc}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {tr.common.cancel}
          </Button>
          <Button
            variant="danger"
            loading={m.isPending}
            onClick={() => {
              if (!reason.trim()) return setError(tr.errors.REASON_REQUIRED!);
              m.mutate();
            }}
          >
            {tr.health.withdraw}
          </Button>
        </>
      }
    >
      <div className={s.dialogStack}>
        {pages.length > 1 && (
          <Field label={tr.health.withdrawPage}>
            {({ id }) => (
              <Select id={id} value={target} onChange={(e) => setPageId(e.target.value)}>
                {pages.map((p) => (
                  <option key={p.page_id} value={p.page_id}>
                    {p.title}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}
        {pages.length === 1 && (
          <p>
            <strong>{tr.health.withdrawPage}:</strong> {pages[0]!.title}
          </p>
        )}
        <Field label={tr.health.withdrawReason} error={error}>
          {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} value={reason} onChange={(e) => setReason(e.target.value)} rows={3} maxLength={2000} invalid={!!error} />}
        </Field>
      </div>
    </Dialog>
  );
}
