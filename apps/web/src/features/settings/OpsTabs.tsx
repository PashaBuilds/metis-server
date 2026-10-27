import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, DatabaseBackup, Trash2 } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { Button, Checkbox, ConfirmDialog, Field, Input, SkeletonRows, StatusBadge, useToast } from '@/design/primitives';
import { useSession } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { formatBytes, formatDateTime, formatPercent } from '@/lib/format';
import { Banner } from '@/features/shared/Banner';
import { messageOf } from '@/features/shared/hooks';
import { ModelSelect, useAvailableModels } from '@/features/shared/models';
import s from './Settings.module.css';
import { apiUrl } from '@/lib/api/base';

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
          <Fact label={x.vector}>
            <VectorStatus v={d.vector_search ?? {}} />
          </Fact>
          <Fact label={x.reranker}>
            <RerankerStatus v={d.reranker ?? {}} />
          </Fact>
          <Fact label={x.enrichment}>{x.enrichmentProgress(Number(d.enrichment?.blocks_enriched ?? 0), Number(d.enrichment?.blocks_eligible ?? 0))}</Fact>
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
      <AllowedEndpoints />
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

/** İzinli model adresleri: sunucu ayarındakiler (metis.env) salt okunur; arayüzden izin verilenler kaldırılabilir. */
function AllowedEndpoints() {
  const qc = useQueryClient();
  const toast = useToast();
  const x = tr.settingsExtra;
  const list = useQuery({ queryKey: ['allowed-endpoints'], queryFn: () => api.get<Schemas['AllowedEndpointRow'][]>('/allowed-endpoints'), retry: false });
  const [remove, setRemove] = useState<Schemas['AllowedEndpointRow'] | null>(null);
  const [error, setError] = useState<string | null>(null);
  return (
    <section className={s.block} aria-labelledby="sys-allow">
      <h2 id="sys-allow" className={s.blockTitle}>
        {x.allowed}
      </h2>
      <p className={s.hint}>{x.allowedLead}</p>
      {list.isLoading ? (
        <SkeletonRows rows={2} />
      ) : !list.data ? (
        <LoadError error={list.error} />
      ) : list.data.length === 0 ? (
        <p className={s.hint}>{x.allowedEmpty}</p>
      ) : (
        <ul className={s.opsRows}>
          {list.data.map((e) => (
            <li key={e.url} className={s.opsRow}>
              <span className={`${s.opsName} mono`}>{e.url}</span>
              {e.source === 'config' ? (
                <span title={x.allowedConfigHint}>
                  <StatusBadge tone="taslak" icon="lock" size="sm" label={x.allowedConfig} />
                </span>
              ) : (
                e.created_by && e.created_at && <span className={s.hintInline}>{x.allowedBy(e.created_by, formatDateTime(e.created_at))}</span>
              )}
              <span className={s.hintInline}>{x.allowedProviders(e.providers)}</span>
              {/* Kullanımdaki adresin izni kaldırılamaz (sunucu da reddeder): önce sağlayıcı silinir. */}
              {e.source === 'ui' && e.providers === 0 && (
                <Button variant="ghost" size="sm" icon={<Trash2 size={14} />} onClick={() => setRemove(e)} aria-label={`${x.disallow}: ${e.url}`}>
                  {x.disallow}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p className={s.error} role="alert">
          {error}
        </p>
      )}
      <ConfirmDialog
        open={!!remove}
        onOpenChange={(o) => !o && setRemove(null)}
        title={remove ? x.disallowTitle(remove.url) : ''}
        description={x.disallowDesc}
        confirmLabel={x.disallow}
        danger
        onConfirm={async () => {
          try {
            await api.del(`/allowed-endpoints/${remove!.id}`);
            toast.show(x.disallowed);
            setError(null);
          } catch (err) {
            setError(messageOf(err));
          } finally {
            setRemove(null);
            void qc.invalidateQueries({ queryKey: ['allowed-endpoints'] });
          }
        }}
      />
    </section>
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
        <a className={s.downloadLink} href={apiUrl(`/projects/${projectId}/export.zip`)} download>
          <Download size={16} aria-hidden />
          {tr.settingsExtra.exportButton}
          {project && <span className={s.downloadName}>{project.project_name}</span>}
        </a>
      )}
      <p className={s.hint}>{tr.settingsExtra.exportNote}</p>
    </section>
  );
}

/** Mentor yeniden sıralayıcısı: kurulu mu, yüklenebildi mi. Yoksa Mentor arama sırasıyla çalışır. */
function RerankerStatus({ v }: { v: Record<string, unknown> }) {
  const x = tr.settingsExtra;
  const state = typeof v.state === 'string' ? v.state : 'absent';
  if (state === 'ready') return <StatusBadge tone="onay" size="sm" label={x.rerankerReady(String(v.model_id ?? ''))} />;
  if (state === 'loading') return <StatusBadge tone="inceleme" size="sm" label={x.rerankerLoading} />;
  if (state === 'error') return <StatusBadge tone="celiski" size="sm" label={x.vectorError(String(v.reason ?? ''))} />;
  return <StatusBadge tone="taslak" size="sm" label={x.rerankerAbsent} />;
}

/** Vektör arama: model kurulu mu, kaç bölümün vektörü hazır. Model yoksa METIS yalnız kelime aramasıyla çalışır. */
function VectorStatus({ v }: { v: Record<string, unknown> }) {
  const x = tr.settingsExtra;
  const state = typeof v.state === 'string' ? v.state : 'absent';
  const total = typeof v.blocks_total === 'number' ? v.blocks_total : 0;
  const done = typeof v.blocks_embedded === 'number' ? v.blocks_embedded : 0;
  if (state === 'ready') {
    return done >= total ? <StatusBadge tone="onay" size="sm" label={x.vectorReady(String(v.model_id ?? ''))} /> : <StatusBadge tone="inceleme" size="sm" label={x.vectorPartial(done, total)} />;
  }
  if (state === 'error') return <StatusBadge tone="celiski" size="sm" label={x.vectorError(String(v.reason ?? ''))} />;
  return <StatusBadge tone="taslak" size="sm" label={x.vectorAbsent} />;
}
