import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, Download, DatabaseBackup, FileArchive } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { Button, Checkbox, EmptyState, Field, Input, SkeletonRows, StatusBadge, useToast } from '@/design/primitives';
import { useSession } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { formatBytes, formatDateTime, formatPercent } from '@/lib/format';
import { Banner } from '@/features/shared/Banner';
import { messageOf } from '@/features/shared/hooks';
import { Markdown } from '@/features/shared/Markdown';
import { ModelSelect, useAvailableModels } from '@/features/shared/models';
import s from './Settings.module.css';

const notDeployed = (e: unknown) => e instanceof ApiError && (e.status === 404 || e.status === 405) && e.code !== 'NOT_FOUND';
const asDate = (v: unknown): string | null => (typeof v === 'string' ? v : null);

function LoadError({ error }: { error: unknown }) {
  return <Banner tone={notDeployed(error) ? 'bilgi' : 'celiski'}>{notDeployed(error) ? tr.settingsExtra.notDeployed : messageOf(error)}</Banner>;
}

/* ---------------------------------------------------------------- Bakım planı */

export function ScheduleTab() {
  const session = useSession();
  const pid = session.projectId;
  const qc = useQueryClient();
  const toast = useToast();
  const canEdit = session.roles.has('steward');
  const models = useAvailableModels(pid);
  const schedule = useQuery({ queryKey: ['schedule', pid], queryFn: () => api.get<Schemas['ScheduleOut']>(`/projects/${pid}/schedule`), enabled: !!pid, retry: false });
  const [enabled, setEnabled] = useState(false);
  const [interval, setInterval] = useState('7');
  const [model, setModel] = useState('');
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!schedule.data) return;
    setEnabled(schedule.data.enabled);
    setInterval(String(schedule.data.interval_days));
    setModel(schedule.data.model_id ?? '');
  }, [schedule.data]);
  const save = useMutation({
    mutationFn: () => api.put<Schemas['ScheduleOut']>(`/projects/${pid}/schedule`, { enabled, interval_days: Number(interval), model_id: model || null }),
    onSuccess: (d) => {
      qc.setQueryData(['schedule', pid], d);
      toast.show(tr.settingsExtra.scheduleSaved);
      setError(null);
    },
    onError: (e) => setError(messageOf(e)),
  });
  if (schedule.isLoading) return <SkeletonRows rows={3} />;
  if (!schedule.data) return <LoadError error={schedule.error} />;
  const n = Number(interval);
  const invalid = !Number.isInteger(n) || n < 1 || n > 90;
  return (
    <section className={s.block} aria-labelledby="schedule-h">
      <h2 id="schedule-h" className={s.blockTitle}>
        {tr.settings.tabs.bakim}
      </h2>
      <p className={s.hint}>{tr.settingsExtra.scheduleLead}</p>
      {!canEdit && <p className={s.hint}>{tr.settingsExtra.scheduleStewardOnly}</p>}
      <div className={s.opsForm}>
        <Checkbox label={tr.settingsExtra.scheduleEnabled} checked={enabled} onChange={setEnabled} disabled={!canEdit} />
        <Field label={tr.settingsExtra.scheduleInterval} hint={tr.settingsExtra.scheduleIntervalHint} error={invalid ? tr.settingsExtra.intervalInvalid : null}>
          {({ id, describedBy }) => (
            <Input id={id} aria-describedby={describedBy} type="number" min={1} max={90} step={1} inputMode="numeric" value={interval} onChange={(e) => setInterval(e.target.value)} disabled={!canEdit} invalid={invalid} className={s.narrow} />
          )}
        </Field>
        <Field label={tr.settingsExtra.scheduleModel}>
          {({ id }) => <ModelSelect id={id} value={model} onChange={setModel} models={models.data ?? []} emptyLabel={tr.settingsExtra.scheduleNoModel} disabled={!canEdit} />}
        </Field>
        <dl className={s.facts}>
          <div>
            <dt>{tr.settingsExtra.scheduleNext}</dt>
            <dd className="tabular">{schedule.data.enabled ? formatDateTime(asDate(schedule.data.next_run_at)) : tr.common.none}</dd>
          </div>
          <div>
            <dt>{tr.settingsExtra.scheduleLast}</dt>
            <dd className="tabular">{asDate(schedule.data.last_run_at) ? formatDateTime(asDate(schedule.data.last_run_at)) : tr.settingsExtra.scheduleNever}</dd>
          </div>
        </dl>
        {error && (
          <p className={s.error} role="alert">
            {error}
          </p>
        )}
        {canEdit && (
          <div>
            <Button variant="primary" loading={save.isPending} disabled={invalid} onClick={() => save.mutate()}>
              {tr.common.save}
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------- Sistem durumu */

function duration(sec: number | null): string {
  if (sec == null) return tr.common.none;
  if (sec < 60) return tr.settingsExtra.seconds(Math.round(sec));
  if (sec < 3600) return tr.settingsExtra.minutes(Math.round(sec / 60));
  return tr.settingsExtra.hours(Math.round(sec / 3600));
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={s.factRow}>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function SystemTab() {
  const session = useSession();
  const status = useQuery({
    queryKey: ['system-status'],
    queryFn: () => api.get<Schemas['SystemStatus']>('/system/status'),
    enabled: session.isAdmin,
    retry: false,
    refetchInterval: 30_000,
  });
  if (!session.isAdmin) return <p className={s.hint}>{tr.settingsExtra.systemAdminOnly}</p>;
  if (status.isLoading) return <SkeletonRows rows={6} />;
  if (!status.data) return <LoadError error={status.error} />;
  const d = status.data;
  const x = tr.settingsExtra;
  const migrationOk = d.migration_revision === d.migration_expected;
  const backup = d.last_backup as Record<string, unknown> | null;
  const backupAt = backup ? asDate(backup.at) : null;
  const backupSize = backup && typeof backup.bytes === 'number' ? backup.bytes : null;
  return (
    <div className={s.stack}>
      <section className={s.block} aria-labelledby="sys-h">
        <h2 id="sys-h" className={s.blockTitle}>
          {x.system}
        </h2>
        <dl className={s.factList}>
          <Fact label={x.version}>
            <span className="mono">{d.version}</span>
          </Fact>
          <Fact label={x.profile}>
            <span className="mono">{d.profile}</span>
          </Fact>
          <Fact label={x.migration}>
            <StatusBadge tone={migrationOk ? 'onay' : 'celiski'} size="sm" label={migrationOk ? x.migrationOk(d.migration_revision) : x.migrationBehind(d.migration_revision, d.migration_expected)} />
          </Fact>
          <Fact label={x.queue}>
            <span className="tabular">
              {x.queueWaiting(d.queue_waiting)}
              {d.queue_oldest_wait_s != null && <span className={s.hintInline}>{x.queueOldest(duration(d.queue_oldest_wait_s))}</span>}
            </span>
          </Fact>
          <Fact label={x.running}>
            <span className="tabular">{d.running_jobs}</span>
          </Fact>
          <Fact label={x.expired}>{d.expired_leases > 0 ? <StatusBadge tone="dikkat" size="sm" label={String(d.expired_leases)} /> : <span className="tabular">0</span>}</Fact>
          <Fact label={x.failed24}>{d.failed_jobs_24h > 0 ? <StatusBadge tone="celiski" size="sm" label={String(d.failed_jobs_24h)} /> : <span className="tabular">0</span>}</Fact>
          <Fact label={x.calls24}>
            <span className="tabular">
              {d.model_calls_24h}
              <span className={s.hintInline}>{x.errorRate(formatPercent(d.model_error_rate_24h))}</span>
            </span>
          </Fact>
          <Fact label={x.disk}>
            <span className="tabular">{d.disk_free_bytes == null || d.disk_total_bytes == null ? tr.common.notMeasured : x.diskFree(formatBytes(d.disk_free_bytes), formatBytes(d.disk_total_bytes))}</span>
          </Fact>
          <Fact label={x.backup}>{backup ? <span className="tabular">
                {backupAt ? formatDateTime(backupAt) : tr.common.none}
                {backupSize != null && <span className={s.hintInline}>{formatBytes(backupSize)}</span>}
              </span> : <StatusBadge tone="dikkat" size="sm" label={x.backupNone} />}</Fact>
          <Fact label={x.fuzzy}>{d.fuzzy_search_available ? <StatusBadge tone="onay" size="sm" label={x.fuzzyOn} /> : <StatusBadge tone="dikkat" size="sm" label={x.fuzzyOff} />}</Fact>
        </dl>
      </section>
      <section className={s.block} aria-labelledby="sys-ep">
        <h2 id="sys-ep" className={s.blockTitle}>
          {x.endpoints}
        </h2>
        {d.model_endpoints.length === 0 ? (
          <p className={s.hint}>{x.endpointsEmpty}</p>
        ) : (
          <ul className={s.opsRows}>
            {d.model_endpoints.map((m) => (
              <li key={m.model_id} className={s.opsRow}>
                <span className={s.opsName}>{m.display_name}</span>
                <StatusBadge
                  tone={m.connection === 'tested_pass' ? 'onay' : m.connection === 'tested_fail' ? 'celiski' : 'taslak'}
                  icon={m.connection === 'tested_pass' ? 'onay' : m.connection === 'tested_fail' ? 'celiski' : 'taslak'}
                  size="sm"
                  label={x.connection[m.connection] ?? m.connection}
                />
                {m.checked_at && <span className={s.hintInline}>{x.checkedAt(formatDateTime(m.checked_at))}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className={s.block} aria-labelledby="sys-bk">
        <h2 id="sys-bk" className={s.blockTitle}>
          <DatabaseBackup size={16} aria-hidden className={s.titleIcon} />
          {x.backup}
        </h2>
        <p className={s.hint}>{x.backupLead}</p>
        <dl className={s.cmdList}>
          <dt>{x.backupCmd}</dt>
          <dd>
            <pre className={s.cmd}>metis backup</pre>
          </dd>
          <dt>{x.restoreCmd}</dt>
          <dd>
            <pre className={s.cmd}>metis restore --rehearsal &lt;arşiv&gt;</pre>
          </dd>
        </dl>
      </section>
    </div>
  );
}

/* ---------------------------------------------------------------- Dışa aktar */

export function ExportTab() {
  const { projectId, project } = useSession();
  return (
    <section className={s.block} aria-labelledby="export-h">
      <h2 id="export-h" className={s.blockTitle}>
        {tr.settings.tabs['disa-aktar']}
      </h2>
      <p className={s.hint}>{tr.settingsExtra.exportLead}</p>
      {projectId && (
        <a className={s.downloadLink} href={`/api/v1/projects/${projectId}/export.zip`} download>
          <Download size={16} aria-hidden />
          {tr.settingsExtra.exportButton}
          {project && <span className={s.downloadName}>{project.project_name}</span>}
        </a>
      )}
      <p className={s.hint}>{tr.settingsExtra.exportNote}</p>
    </section>
  );
}

/* ---------------------------------------------------------- v0.5.5 aktarımı */

type RunRow = Schemas['LegacyRunRow'];
type RunDetail = Schemas['LegacyRunDetail'];

export function ImportTab() {
  const session = useSession();
  const runs = useQuery({ queryKey: ['legacy-runs'], queryFn: () => api.get<RunRow[]>('/legacy-import/runs'), enabled: session.isAdmin, retry: false });
  const [open, setOpen] = useState<string | null>(null);
  if (!session.isAdmin) return <p className={s.hint}>{tr.settingsExtra.importAdminOnly}</p>;
  if (runs.isLoading) return <SkeletonRows rows={3} />;
  if (!runs.data) return <LoadError error={runs.error} />;
  const x = tr.settingsExtra;
  if (runs.data.length === 0)
    return (
      <EmptyState icon={<FileArchive size={24} />} title={x.importEmptyTitle}>
        <p>{x.importEmpty}</p>
        <pre className={s.cmd}>{'metis import-v1 <yedek> --dry-run\nmetis import-v1 <yedek>'}</pre>
      </EmptyState>
    );
  return (
    <section className={s.block} aria-labelledby="import-h">
      <h2 id="import-h" className={s.blockTitle}>
        {x.importRuns}
      </h2>
      <p className={s.hint}>{x.importLead}</p>
      <ul className={s.opsRows}>
        {runs.data.map((r) => {
          const sum = r.summary;
          const verified = typeof sum.verification_ok === 'boolean' ? sum.verification_ok : null;
          const active = typeof sum.active_pages === 'number' ? sum.active_pages : null;
          const isOpen = open === r.id;
          return (
            <li key={r.id} className={s.importRow}>
              <div className={s.importHead}>
                <span className={s.opsName}>{x.importMode[r.mode] ?? r.mode}</span>
                <StatusBadge
                  tone={r.state === 'completed' ? 'onay' : r.state === 'failed' ? 'celiski' : 'inceleme'}
                  icon={r.state === 'running' ? 'spin' : undefined}
                  size="sm"
                  label={x.importStates[r.state] ?? r.state}
                />
                {verified !== null && <StatusBadge tone={verified ? 'onay' : 'celiski'} size="sm" label={verified ? x.importVerified : x.importUnverified} />}
                {active !== null && <span className={s.hintInline}>{x.importActivePages(active)}</span>}
                <span className={s.hintInline}>
                  {x.importStarted}: {formatDateTime(r.started_at)}
                </span>
                {r.finished_at && (
                  <span className={s.hintInline}>
                    {x.importFinished}: {formatDateTime(r.finished_at)}
                  </span>
                )}
                <button type="button" className={s.expand} aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : r.id)}>
                  <ChevronDown size={15} aria-hidden className={isOpen ? s.chevOpen : undefined} />
                  {isOpen ? x.importHide : x.importOpen}
                </button>
              </div>
              {isOpen && <ImportReport id={r.id} sha={r.source_sha256} />}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function ImportReport({ id, sha }: { id: string; sha: string }) {
  const q = useQuery({ queryKey: ['legacy-run', id], queryFn: () => api.get<RunDetail>(`/legacy-import/runs/${id}`) });
  if (q.isLoading) return <SkeletonRows rows={4} />;
  if (!q.data) return <LoadError error={q.error} />;
  return (
    <div className={s.report}>
      {q.data.report_md ? <Markdown>{q.data.report_md}</Markdown> : <p className={s.hint}>{tr.common.none}</p>}
      <details className={s.techDetails}>
        <summary>{tr.common.technicalDetails}</summary>
        <dl className={s.factList}>
          <Fact label="SHA-256">
            <span className="mono">{sha}</span>
          </Fact>
          <Fact label="ID">
            <span className="mono">{id}</span>
          </Fact>
        </dl>
      </details>
    </div>
  );
}
