import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from '@tanstack/react-router';
import { GitCompare, ScanSearch, Sparkles } from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';
import { Button, EmptyState, Field, Select, SkeletonRows, Textarea, useToast } from '@/design/primitives';
import { PageHeader } from '@/app/Shell';
import { useSession } from '@/app/session';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { Banner } from '@/features/shared/Banner';
import { messageOf } from '@/features/shared/hooks';
import { ModelSelect, modelReason, useAvailableModels, type AvailableModel } from '@/features/shared/models';
import { ACTIVE_STATES, JobStateBadge, useJobEvents } from './jobs';
import s from './Tasks.module.css';

type JobRow = Schemas['JobRow'];

const timeOnly = new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit' });
const dateShort = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: '2-digit' });

/** Başlangıç saati ss:dd; bugün değilse gün.ay ss:dd. */
export function startTime(value: unknown): string {
  if (typeof value !== 'string') return tr.common.none;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return tr.common.none;
  return d.toDateString() === new Date().toDateString() ? timeOnly.format(d) : `${dateShort.format(d)} ${timeOnly.format(d)}`;
}

function startError(e: unknown): string {
  if (!(e instanceof ApiError)) return errorMessage('NETWORK');
  const reason = typeof e.details.reason === 'string' ? modelReason(e.details.reason) : '';
  return reason ? `${errorMessage(e.code)} ${reason}` : errorMessage(e.code);
}

export function useJobs(pid: string | null) {
  return useQuery({
    queryKey: ['jobs', pid],
    queryFn: () => api.get<JobRow[]>(`/projects/${pid}/jobs`),
    enabled: !!pid,
    // SSE asıl kaynak; yalnız yavaş bir yedek yenileme.
    refetchInterval: 30_000,
  });
}

export function TasksPage() {
  const session = useSession();
  const pid = session.projectId;
  const jobs = useJobs(pid);
  const models = useAvailableModels(pid);
  const canStart = session.roles.has('contributor');
  const active = (jobs.data ?? []).filter((j) => ACTIVE_STATES.has(j.state)).map((j) => j.id).slice(0, 6);
  useJobEvents(active, [['jobs', pid], ['inbox', pid]]);

  return (
    <div className={s.page}>
      <PageHeader title={tr.jobs.title} />
      <div className={s.stack}>
      {!canStart && <Banner tone="bilgi">{tr.jobs.contributorOnly}</Banner>}
      {canStart && (
        <div className={s.kinds}>
          <RefineCard models={models.data ?? []} modelsError={models.isError ? messageOf(models.error) : null} />
          <AuditCard models={models.data ?? []} modelsError={models.isError ? messageOf(models.error) : null} />
        </div>
      )}

      <section className={s.section} aria-labelledby="jobs-h">
        <h2 id="jobs-h" className={s.sectionTitle}>
          {tr.jobs.list}
        </h2>
        {jobs.isLoading ? (
          <SkeletonRows rows={4} />
        ) : jobs.isError ? (
          <EmptyState title={tr.shared.loadError} actions={<Button onClick={() => jobs.refetch()}>{tr.common.retry}</Button>}>
            {messageOf(jobs.error)}
          </EmptyState>
        ) : !jobs.data?.length ? (
          <EmptyState icon={<Sparkles size={24} />} title={tr.jobs.empty} />
        ) : (
          <ul className={s.rows}>
            {jobs.data.map((j) => (
              <li key={j.id} className={s.row}>
                <div className={s.rowState}>
                  <JobStateBadge state={j.state} size="sm" />
                </div>
                <div className={s.rowMain}>
                  <Link to="/gorevler/$jobId" params={{ jobId: j.id }} className={s.rowTitle}>
                    {j.title}
                  </Link>
                  <p className={s.rowSummary}>{j.result_summary || (j.state === 'queued' ? tr.jobs.queuedResult : j.state === 'running' ? tr.jobs.waitingResult : tr.jobs.noSummary)}</p>
                </div>
                <div className={s.rowSide}>
                  <time className={s.time} title={tr.jobs.startedAt} dateTime={typeof (j.started_at ?? j.created_at) === 'string' ? String(j.started_at ?? j.created_at) : undefined}>
                    {startTime(j.started_at ?? j.created_at)}
                  </time>
                  {j.model_name && <span className={s.model}>{tr.jobs.model(j.model_name)}</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
      </div>
    </div>
  );
}

function KindCard({ icon, title, text, children }: { icon: ReactNode; title: string; text: string; children: ReactNode }) {
  return (
    <section className={s.kind} aria-label={title}>
      <div className={s.kindHead}>
        {icon}
        <h2 className={s.kindTitle}>{title}</h2>
      </div>
      <p className={s.kindText}>{text}</p>
      {children}
    </section>
  );
}

function useStart(onDone: (id: string) => void) {
  const session = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function start(body: Record<string, unknown>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<JobRow>(`/projects/${session.projectId}/jobs`, body);
      void qc.invalidateQueries({ queryKey: ['jobs', session.projectId] });
      toast.show(tr.jobs.started);
      onDone(res.id);
    } catch (e) {
      setError(startError(e));
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, start };
}

function RefineCard({ models, modelsError }: { models: AvailableModel[]; modelsError: string | null }) {
  const session = useSession();
  const pid = session.projectId;
  const navigate = useNavigate();
  const [draft, setDraft] = useState('');
  const [model, setModel] = useState('');
  const [notes, setNotes] = useState('');
  const reasonId = useId();
  const drafts = useQuery({
    queryKey: ['changes', pid, 'drafts', 'all'],
    queryFn: () => api.get<Schemas['ChangeListOut']>(`/projects/${pid}/changes`, { tab: 'drafts' }),
    enabled: !!pid,
  });
  const meId = session.me?.user.id;
  const mine = (drafts.data?.items ?? []).filter((c) => (c.author_id === meId || c.requester_id === meId) && (c.state === 'draft' || c.state === 'in_review'));
  const { busy, error, start } = useStart((id) => navigate({ to: '/gorevler/$jobId', params: { jobId: id } }));
  const reason = modelsError ?? (drafts.data && mine.length === 0 ? tr.jobs.refineNoDrafts : !draft ? tr.jobs.draftRequired : !model ? tr.jobs.modelRequired : null);
  return (
    <KindCard icon={<GitCompare size={20} aria-hidden />} title={tr.jobs.refineTitle} text={tr.jobs.refineText}>
      <Field label={tr.jobs.refineDraft}>
        {({ id }) => (
          <Select id={id} value={draft} onChange={(e) => setDraft(e.target.value)} disabled={!mine.length}>
            <option value="">{tr.jobs.refineDraftPick}</option>
            {mine.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label={tr.models.label}>
        {({ id }) => <ModelSelect id={id} value={model} onChange={setModel} models={models} emptyLabel={tr.models.pick} />}
      </Field>
      <Field label={tr.jobs.instructions} hint={tr.jobs.instructionsHint}>
        {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} maxLength={2000} />}
      </Field>
      <div className={s.kindAction}>
        <Button variant="primary" loading={busy} disabled={!!reason} aria-describedby={reason || error ? reasonId : undefined} onClick={() => start({ kind: 'refine_draft', draft_change_id: draft, model_id: model, instructions: notes.trim() })}>
          {tr.jobs.start}
        </Button>
        {(error || reason) && (
          <p id={reasonId} className={error ? s.error : s.reason} role={error ? 'alert' : undefined}>
            {error ?? reason}
          </p>
        )}
      </div>
    </KindCard>
  );
}

function AuditCard({ models, modelsError }: { models: AvailableModel[]; modelsError: string | null }) {
  const navigate = useNavigate();
  const [model, setModel] = useState('');
  const reasonId = useId();
  const { busy, error, start } = useStart((id) => navigate({ to: '/gorevler/$jobId', params: { jobId: id } }));
  const reason = modelsError ?? (!model ? tr.jobs.modelRequired : null);
  return (
    <KindCard icon={<ScanSearch size={20} aria-hidden />} title={tr.jobs.auditTitle} text={tr.jobs.auditText}>
      <Field label={tr.models.label}>
        {({ id }) => <ModelSelect id={id} value={model} onChange={setModel} models={models} emptyLabel={tr.models.pick} />}
      </Field>
      <div className={s.kindAction}>
        <Button variant="primary" loading={busy} disabled={!!reason} aria-describedby={reason || error ? reasonId : undefined} onClick={() => start({ kind: 'audit_pool', model_id: model })}>
          {tr.jobs.start}
        </Button>
        {(error || reason) && (
          <p id={reasonId} className={error ? s.error : s.reason} role={error ? 'alert' : undefined}>
            {error ?? reason}
          </p>
        )}
      </div>
    </KindCard>
  );
}
