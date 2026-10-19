import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { Sparkles } from 'lucide-react';
import { Button, EmptyState, SkeletonRows } from '@/design/primitives';
import { PageHeader } from '@/app/Shell';
import { useSession } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { messageOf } from '@/features/shared/hooks';
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
  const active = (jobs.data ?? []).filter((j) => ACTIVE_STATES.has(j.state)).map((j) => j.id).slice(0, 6);
  useJobEvents(active, [['jobs', pid], ['inbox', pid]]);

  return (
    <div className={s.page}>
      <PageHeader title={tr.jobs.title} />
      <div className={s.stack}>
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
