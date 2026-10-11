import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router';
import { ArrowRight, Bot, ChevronRight, Radio, RotateCcw, Trash2, User, XCircle } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Button, ConfirmDialog, EmptyState, Field, SkeletonRows, Textarea, useToast } from '@/design/primitives';
import { PageHeader } from '@/app/Shell';
import { ScopePicker } from '@/app/ScopeBar';
import { EMPTY_SCOPE, useSession, type ScopeSel } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { formatDateTime } from '@/lib/format';
import { Banner } from '@/features/shared/Banner';
import { messageOf } from '@/features/shared/hooks';
import { ACTIVE_STATES, JobStateBadge, jobErrorText, useJobEvents } from './jobs';
import { startTime } from './TasksPage';
import s from './Tasks.module.css';

const route = getRouteApi('/app/gorevler/$jobId');
type Job = Schemas['JobDetail'];

interface Message {
  id: string;
  role: string;
  body: string;
  detail: { kind?: string; source_revision_id?: string; scope?: unknown } | null;
  created_at: string;
  answered: boolean;
}

const asMessage = (x: Record<string, unknown>): Message => ({
  id: String(x.id ?? ''),
  role: String(x.role ?? ''),
  body: String(x.body ?? ''),
  detail: x.detail && typeof x.detail === 'object' ? (x.detail as Message['detail']) : null,
  created_at: String(x.created_at ?? ''),
  answered: !!x.answered,
});

const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const rec = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {});
const text = (v: unknown): string => (typeof v === 'string' ? v : typeof v === 'number' || typeof v === 'boolean' ? String(v) : '');

export function TaskDetailPage() {
  const { jobId } = route.useParams();
  const session = useSession();
  const pid = session.projectId;
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => api.get<Job>(`/jobs/${jobId}`),
    refetchInterval: (q) => (q.state.data && ACTIVE_STATES.has(q.state.data.state) ? 30_000 : false),
  });
  const live = !!job.data && ACTIVE_STATES.has(job.data.state);
  useJobEvents(live ? [jobId] : [], [['job', jobId], ['jobs', pid], ['inbox', pid]]);

  const act = useMutation({
    mutationFn: (action: 'cancel' | 'retry') => api.post<Job>(`/jobs/${jobId}/${action}`),
    onSuccess: (d, action) => {
      qc.setQueryData(['job', jobId], d);
      void qc.invalidateQueries({ queryKey: ['jobs', pid] });
      toast.show(action === 'cancel' ? tr.jobs.cancelled : tr.jobs.retried);
    },
    onError: (e) => toast.show(messageOf(e), { tone: 'error' }),
  });

  if (job.isLoading) return <SkeletonRows rows={6} />;
  if (!job.data) return <EmptyState title={tr.shared.loadError}>{messageOf(job.error)}</EmptyState>;
  const j = job.data;
  // Bitiş özeti (Metis'in kapanış mesajı) zaten "Sonuç"ta; soru listesinde tekrarlanmaz.
  const messages = j.messages.map(asMessage).filter((m) => !(m.role === 'metis' && m.answered && !m.detail?.kind && m.body === j.result_summary));
  const err = j.state === 'failed' || j.state === 'budget_exceeded' ? jobErrorText(j.error_code) : null;

  return (
    <div className={s.page}>
      <PageHeader
        title={j.title}
        actions={
          <>
            {j.can_cancel && (
              <Button icon={<XCircle size={16} aria-hidden />} onClick={() => act.mutate('cancel')} loading={act.isPending && act.variables === 'cancel'}>
                {tr.jobs.cancel}
              </Button>
            )}
            {j.can_retry && (
              <Button icon={<RotateCcw size={16} aria-hidden />} onClick={() => act.mutate('retry')} loading={act.isPending && act.variables === 'retry'}>
                {tr.jobs.retry}
              </Button>
            )}
            {j.state !== 'running' && (
              <Button variant="ghost" icon={<Trash2 size={16} aria-hidden />} onClick={() => setConfirmDelete(true)}>
                {tr.jobs.delete}
              </Button>
            )}
          </>
        }
      >
        <div className={s.headMeta}>
          <JobStateBadge state={j.state} />
          {live && (
            <span className={s.live}>
              <Radio size={14} aria-hidden />
              {tr.jobs.live}
            </span>
          )}
          <span className={s.metaText}>
            {tr.jobs.startedAt} {startTime(j.started_at ?? j.created_at)}
          </span>
          {j.model_name && <span className={s.metaText}>{tr.jobs.model(j.model_name)}</span>}
          {j.legacy && <span className={s.metaText}>{tr.jobs.legacy}</span>}
        </div>
      </PageHeader>
      <div className={s.stack}>

      <section className={s.result} aria-labelledby="job-result" aria-live="polite">
        <h2 id="job-result" className={s.sectionTitle}>
          {tr.jobs.result}
        </h2>
        <p className={s.resultText}>{j.result_summary || (j.state === 'queued' ? tr.jobs.queuedResult : j.state === 'running' ? tr.jobs.waitingResult : tr.jobs.noSummary)}</p>
        {err && <Banner tone={j.state === 'failed' ? 'celiski' : 'dikkat'}>{err}</Banner>}
        {j.output_change_ids.length > 0 && (
          <div className={s.outputs}>
            {j.output_change_ids.map((id, i) => (
              <Link key={id} to="/kayitlar/$changeId" params={{ changeId: id }} className={s.primaryLink}>
                {j.output_change_ids.length > 1 ? tr.jobs.reviewDraftN(i + 1) : tr.jobs.reviewDraft}
                <ArrowRight size={16} aria-hidden />
              </Link>
            ))}
          </div>
        )}
        <Report job={j} />
      </section>

      <section className={s.section} aria-labelledby="job-q">
        <h2 id="job-q" className={s.sectionTitle}>
          {tr.jobs.questions}
        </h2>
        {messages.length === 0 ? (
          <p className={s.hint}>{tr.jobs.noQuestions}</p>
        ) : (
          <ol className={s.messages}>
            {messages.map((m) => (
              <li key={m.id} className={[s.message, m.role === 'metis' ? s.fromMetis : s.fromUser].join(' ')}>
                <span className={s.msgWho}>
                  {m.role === 'metis' ? <Bot size={15} aria-hidden /> : <User size={15} aria-hidden />}
                  {m.role === 'metis' ? tr.jobs.metis : tr.jobs.you}
                </span>
                <p className={s.msgBody}>{m.body}</p>
                <time className={s.time} dateTime={m.created_at}>
                  {formatDateTime(m.created_at)}
                </time>
              </li>
            ))}
          </ol>
        )}
        {j.can_answer && <AnswerForm job={j} question={[...messages].reverse().find((m) => m.role === 'metis' && !m.answered) ?? null} />}
      </section>

      <TechDetails job={j} />
      </div>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={tr.jobs.deleteTitle}
        description={tr.jobs.deleteDesc}
        confirmLabel={tr.common.delete}
        danger
        onConfirm={async () => {
          try {
            await api.del(`/jobs/${jobId}`);
            void qc.invalidateQueries({ queryKey: ['jobs', pid] });
            toast.show(tr.common.deleted);
            navigate({ to: '/gorevler' });
          } catch (e) {
            toast.show(messageOf(e), { tone: 'error' });
          }
        }}
      />
    </div>
  );
}

function AnswerForm({ job, question }: { job: Job; question: Message | null }) {
  const qc = useQueryClient();
  const toast = useToast();
  const isScope = question?.detail?.kind === 'scope';
  const [value, setValue] = useState('');
  const [scope, setScope] = useState<ScopeSel>(EMPTY_SCOPE);
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => api.post<Job>(`/jobs/${job.id}/answer`, { text: value.trim(), scope: isScope ? scope : null }),
    onSuccess: (d) => {
      qc.setQueryData(['job', job.id], d);
      void qc.invalidateQueries({ queryKey: ['inbox'] });
      toast.show(tr.jobs.answered);
      setValue('');
    },
    onError: (e) => setError(messageOf(e)),
  });
  const empty = isScope ? Object.values(scope).every((v) => v.length === 0) && !value.trim() : !value.trim();
  function submit(e: FormEvent) {
    e.preventDefault();
    if (empty) {
      setError(tr.jobs.answerRequired);
      return;
    }
    setError(null);
    m.mutate();
  }
  return (
    <form className={s.answerForm} onSubmit={submit}>
      {isScope && (
        <fieldset className={s.scopeBox}>
          <legend className={s.label}>{tr.jobs.answerScope}</legend>
          <p className={s.hint}>{tr.jobs.answerScopeHint}</p>
          <ScopePicker value={scope} onChange={setScope} allowIndependent />
        </fieldset>
      )}
      <Field label={tr.jobs.answer} error={error}>
        {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} value={value} onChange={(e) => setValue(e.target.value)} rows={3} maxLength={4000} invalid={!!error} />}
      </Field>
      <div>
        <Button type="submit" variant="primary" loading={m.isPending}>
          {tr.jobs.sendAnswer}
        </Button>
      </div>
    </form>
  );
}

function Report({ job }: { job: Job }) {
  const r = rec(job.report);
  const conflicts = arr(r.conflicts).map(rec).filter((c) => !c.verdict || c.verdict === 'conflict');
  const relations = arr(r.relations).map(rec);
  const decisions = arr(r.open_decisions).map(rec);
  const pages = arr(r.pages).map(rec);
  const counts = Object.entries(rec(r.counts)).filter(([, n]) => typeof n === 'number' && n > 0) as [string, number][];
  if (!conflicts.length && !relations.length && !decisions.length && !pages.length && !counts.length) return null;
  return (
    <div className={s.report}>
      <h3 className={s.reportTitle}>{tr.jobs.report}</h3>
      <ul className={s.reportList}>
        {conflicts.length > 0 && (
          <li>
            <span className={s.reportHead}>{tr.jobs.reportConflicts(conflicts.length)}</span>
            <ul>
              {conflicts.map((c, i) => (
                <li key={i}>{text(c.page_title)}</li>
              ))}
            </ul>
          </li>
        )}
        {relations.length > 0 && (
          <li>
            <span className={s.reportHead}>{tr.jobs.reportRelations(relations.length)}</span>
            <ul>
              {relations.map((c, i) => (
                <li key={i}>
                  {tr.relations[text(c.predicate)] ?? text(c.predicate)} {text(c.page_title)}
                </li>
              ))}
            </ul>
          </li>
        )}
        {decisions.length > 0 && (
          <li>
            <span className={s.reportHead}>{tr.jobs.reportDecisions(decisions.length)}</span>
            <ul>
              {decisions.map((c, i) => (
                <li key={i}>{text(c.description)}</li>
              ))}
            </ul>
          </li>
        )}
        {pages.length > 0 && (
          <li>
            <span className={s.reportHead}>{tr.jobs.reportPages(pages.length)}</span>
            <ul>
              {pages.map((c, i) => (
                <li key={i}>{text(c.title)}</li>
              ))}
            </ul>
          </li>
        )}
        {counts.length > 0 && (
          <li>
            <span className={s.reportHead}>{tr.jobs.reportCounts}</span>
            <ul>
              {counts.map(([k, n]) => (
                <li key={k}>
                  {tr.health.kinds[k] ?? k}: <span className="tabular">{n}</span>
                </li>
              ))}
            </ul>
            <Link to="/saglik" className={s.textLink}>
              {tr.jobs.openHealth}
            </Link>
          </li>
        )}
      </ul>
    </div>
  );
}

function TechDetails({ job }: { job: Job }) {
  const t = rec(job.technical);
  const steps = arr(t.steps).map(rec);
  const calls = arr(t.model_call_ids).map(text).filter(Boolean);
  const budget = Object.entries(rec(t.budget));
  return (
    <details className={s.tech}>
      <summary>
        <ChevronRight size={14} aria-hidden className={s.techChevron} />
        {tr.common.technicalDetails}
      </summary>
      <div className={s.techBody}>
        <div>
          <h3 className={s.techTitle}>{tr.jobs.techSteps}</h3>
          {steps.length === 0 ? (
            <p className={s.hint}>{tr.jobs.techStepsEmpty}</p>
          ) : (
            <ol className={s.steps}>
              {steps.map((st, i) => (
                <li key={i}>
                  <span className="mono">{text(st.name)}</span>
                  <span className={s.stepExtra}>
                    {Object.entries(st)
                      .filter(([k]) => k !== 'name' && k !== 'at')
                      .map(([k, v]) => `${k}=${text(v)}`)
                      .join(' ')}
                  </span>
                  <time className={s.time}>{formatDateTime(text(st.at))}</time>
                </li>
              ))}
            </ol>
          )}
        </div>
        <div>
          <h3 className={s.techTitle}>{tr.jobs.techCalls}</h3>
          {calls.length === 0 ? (
            <p className={s.hint}>{tr.jobs.techCallsEmpty}</p>
          ) : (
            <ul className={s.monoList}>
              {calls.map((c) => (
                <li key={c} className="mono">
                  {c}
                </li>
              ))}
            </ul>
          )}
        </div>
        <dl className={s.techList}>
          <dt>{tr.jobs.techRun}</dt>
          <dd className="mono">
            fence={text(t.fence)} attempt={text(t.attempt)}
            {t.lease_until ? ` lease_until=${text(t.lease_until)}` : ''}
            {t.worker_id ? ` worker=${text(t.worker_id)}` : ''}
          </dd>
          <dt>{tr.jobs.techBudget}</dt>
          <dd className="mono">{budget.length ? budget.map(([k, v]) => `${k}=${text(v)}`).join(' ') : tr.common.none}</dd>
          <dt>{tr.jobs.techInputs}</dt>
          <dd>
            <pre className={s.pre}>{JSON.stringify(t.inputs ?? {}, null, 2)}</pre>
          </dd>
          <dt>ID</dt>
          <dd className="mono">{job.id}</dd>
        </dl>
      </div>
    </details>
  );
}
