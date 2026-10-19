import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckSquare, ChevronRight, FlaskConical, KeyRound, Play, Plus, ShieldCheck, Square, Trash2, Zap, ZapOff } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Button, ConfirmDialog, Dialog, Drawer, EmptyState, Field, Input, SkeletonRows, StatusBadge, Textarea, useToast, type Tone } from '@/design/primitives';
import { PageHeader } from '@/app/Shell';
import { useSession } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { formatDate, formatDateTime, formatMs, formatPercent } from '@/lib/format';
import { messageOf } from '@/features/shared/hooks';
import { modelReason } from '@/features/shared/models';
import { RowMenu } from '@/features/shared/RowMenu';
import { QualityChart, type ChartPoint } from './QualityChart';
import s from './Lab.module.css';

type ModelRow = Schemas['ModelRow'];
type RunRow = Schemas['RunRow'];

interface Provider {
  id: string;
  name: string;
  base_url: string;
  secret_configured: boolean;
  secret_updated_at: string | null;
  max_concurrency: number;
  timeout_s: number;
}

interface Probe {
  status: string;
  at: string | null;
  error: string | null;
}

interface Bench {
  n: number;
  passed: number;
  critical_errors: number;
  critical_kinds: string[];
  /** Model kapsam dışı cevap verdi; deterministik kapsam koruması durdurdu (geçti sayılır, ayrıca gösterilir). */
  scope_guarded?: number;
  errors: number;
  accuracy: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  p95_notice: string | null;
  pass_rule?: string;
  run_id?: string;
  current_fingerprint?: boolean;
  at?: string;
}

interface RunDetail {
  id: string;
  state: string;
  metrics: Partial<Bench>;
  results: { case: string; task: string; expected: string | null; decision: string | null; passed: boolean; critical: boolean; critical_kind: string | null; latency_ms: number | null; error: string | null }[];
}

const CAPS = ['connection', 'auth', 'json_schema', 'thinking_disabled', 'evidence_contract'] as const;
const PASS_RATIO = 0.9;

const probesOf = (m: ModelRow): Record<string, Probe> =>
  Object.fromEntries(
    Object.entries(m.probes).map(([k, v]) => [
      k,
      { status: typeof v.status === 'string' ? v.status : 'unknown', at: typeof v.at === 'string' ? v.at : null, error: typeof v.error === 'string' ? v.error : null },
    ]),
  );
const benchOf = (m: ModelRow): Bench | null => (m.benchmark as Bench | null) ?? null;
const latencyOf = (m: ModelRow) => m.latency as { n: number; p50_ms: number | null; p95_ms: number | null };
const benchPassed = (b: Bench) => b.critical_errors === 0 && (b.errors ?? 0) === 0 && b.n > 0 && (b.accuracy ?? 0) >= PASS_RATIO;

function probeSummary(m: ModelRow): { tone: Tone; label: string; icon?: 'onay' | 'celiski' | 'dikkat' | 'taslak' } {
  const p = probesOf(m);
  const st = CAPS.map((c) => p[c]?.status ?? 'unknown');
  if (st.every((x) => x === 'tested_pass')) return { tone: 'onay', label: tr.lab.probe.pass! };
  if (st.every((x) => x === 'unknown')) return { tone: 'taslak', label: tr.lab.probe.unknown!, icon: 'taslak' };
  if (p.connection?.status === 'tested_pass' && p.evidence_contract?.status === 'tested_pass') return { tone: 'dikkat', label: tr.lab.probe.partial! };
  return { tone: 'celiski', label: tr.lab.probe.fail! };
}

function useRuns() {
  return useQuery({
    queryKey: ['benchmark-runs'],
    queryFn: () => api.get<RunRow[]>('/benchmark-runs', { limit: 50 }),
    // Çalışan benchmark varken 3 sn'de bir; yoksa yoklama yok.
    refetchInterval: (q) => ((q.state.data ?? []).some((r) => r.state === 'queued' || r.state === 'running') ? 3000 : false),
  });
}

export default function LabPage() {
  const session = useSession();
  if (!session.isAdmin)
    return (
      <div className={s.page}>
        <PageHeader title={tr.lab.title} />
        <EmptyState icon={<FlaskConical size={24} />} title={tr.lab.adminOnly} />
      </div>
    );
  return <Lab />;
}

function Lab() {
  const qc = useQueryClient();
  const toast = useToast();
  const providers = useQuery({ queryKey: ['providers'], queryFn: () => api.get<Provider[]>('/providers') });
  const models = useQuery({ queryKey: ['models'], queryFn: () => api.get<ModelRow[]>('/models') });
  const runs = useRuns();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [testing, setTesting] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [keyFor, setKeyFor] = useState<Provider | null>(null);
  const [modelsFor, setModelsFor] = useState<Provider | null>(null);
  const [delProvider, setDelProvider] = useState<Provider | null>(null);
  const [delModel, setDelModel] = useState<ModelRow | null>(null);
  const [clearAll, setClearAll] = useState(false);
  const [result, setResult] = useState<{ model: ModelRow | null; runId: string | null; name: string } | null>(null);

  const list = models.data ?? [];
  const activeRuns = new Map((runs.data ?? []).filter((r) => r.state === 'queued' || r.state === 'running').map((r) => [r.model_id, r.state]));

  // Benchmark bitince model satırları (yeterlilik, gecikme) tazelenir.
  const lastActive = useRef(0);
  useEffect(() => {
    if (activeRuns.size < lastActive.current) {
      void qc.invalidateQueries({ queryKey: ['models'] });
      void qc.invalidateQueries({ queryKey: ['models-available'] });
    }
    lastActive.current = activeRuns.size;
  }, [activeRuns.size, qc]);

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['models'] });
    void qc.invalidateQueries({ queryKey: ['models-available'] });
    void qc.invalidateQueries({ queryKey: ['benchmark-runs'] });
  };

  async function probe(ids: string[]) {
    for (const id of ids) {
      const m = list.find((x) => x.id === id);
      setTesting((t) => new Set(t).add(id));
      try {
        const res = await api.post<{ evidence_contract: boolean }>(`/models/${id}/probe`);
        toast.show(res.evidence_contract ? tr.lab.tested(m?.display_name ?? '') : tr.lab.testFailed(m?.display_name ?? ''), { tone: res.evidence_contract ? 'ok' : 'error' });
      } catch (e) {
        toast.show(messageOf(e), { tone: 'error' });
      } finally {
        setTesting((t) => {
          const n = new Set(t);
          n.delete(id);
          return n;
        });
      }
    }
    refresh();
  }

  const bench = useMutation({
    mutationFn: (ids: string[]) => api.post<{ run_ids: string[] }>('/models/benchmark', { model_ids: ids }),
    onSuccess: (r) => {
      toast.show(tr.lab.benchStarted(r.run_ids.length));
      void qc.invalidateQueries({ queryKey: ['benchmark-runs'] });
    },
    onError: (e) => toast.show(messageOf(e), { tone: 'error' }),
  });

  async function clearResults(modelId: string | null) {
    try {
      await api.post('/models/clear-results', { model_id: modelId });
      toast.show(tr.lab.cleared);
      refresh();
    } catch (e) {
      toast.show(messageOf(e), { tone: 'error' });
    }
  }

  async function toggleEnabled(m: ModelRow) {
    try {
      await api.patch(`/models/${m.id}`, { enabled: !m.enabled });
      refresh();
    } catch (e) {
      toast.show(messageOf(e), { tone: 'error' });
    }
  }

  const allSelected = list.length > 0 && list.every((m) => selected.has(m.id));
  const sel = [...selected].filter((id) => list.some((m) => m.id === id));
  const points: ChartPoint[] = list.flatMap((m) => {
    const b = benchOf(m);
    return b && b.accuracy != null && b.p50_ms != null ? [{ id: m.id, name: m.display_name, accuracy: b.accuracy, p50: b.p50_ms, critical: b.critical_errors, n: b.n }] : [];
  });

  return (
    <div className={s.page}>
      <PageHeader title={tr.lab.title} />
      <div className={s.stack}>
        {/* ---------------------------------------------------------- sağlayıcılar */}
        <section className={s.section} aria-labelledby="lab-providers">
          <div className={s.sectionHead}>
            <h2 id="lab-providers" className={s.sectionTitle}>
              {tr.lab.providers}
            </h2>
            <Button icon={<Plus size={16} aria-hidden />} onClick={() => setAdding(true)}>
              {tr.lab.addProvider}
            </Button>
          </div>
          {providers.isLoading ? (
            <SkeletonRows rows={2} />
          ) : providers.isError ? (
            <p className={s.error}>{messageOf(providers.error)}</p>
          ) : !providers.data?.length ? (
            <p className={s.hint}>{tr.lab.providersEmpty}</p>
          ) : (
            <ul className={s.rows}>
              {providers.data.map((p) => (
                <li key={p.id} className={s.providerRow}>
                  <div className={s.providerMain}>
                    <span className={s.providerName}>{p.name}</span>
                    <span className={s.mono}>{p.base_url}</span>
                  </div>
                  <span className={s.keyState}>
                    <KeyRound size={15} aria-hidden />
                    {p.secret_configured ? tr.lab.keySet(formatDate(p.secret_updated_at)) : tr.lab.keyNone}
                  </span>
                  <Button size="sm" onClick={() => setKeyFor(p)}>
                    {tr.lab.changeKey}
                  </Button>
                  <RowMenu
                    label={tr.lab.providerActions(p.name)}
                    actions={[
                      { label: tr.lab.addModels, icon: <Plus size={15} />, onSelect: () => setModelsFor(p) },
                      { label: tr.lab.deleteProvider, icon: <Trash2 size={15} />, danger: true, separatorBefore: true, onSelect: () => setDelProvider(p) },
                    ]}
                  />
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* --------------------------------------------------------------- modeller */}
        <section className={s.section} aria-labelledby="lab-models">
          <div className={s.sectionHead}>
            <h2 id="lab-models" className={s.sectionTitle}>
              {tr.lab.models}
            </h2>
          </div>
          <div className={s.toolbar} role="toolbar" aria-label={tr.lab.models}>
            <Button size="sm" icon={allSelected ? <CheckSquare size={15} aria-hidden /> : <Square size={15} aria-hidden />} onClick={() => setSelected(allSelected ? new Set() : new Set(list.map((m) => m.id)))} disabled={!list.length}>
              {allSelected ? tr.lab.clearSelection : tr.lab.selectAll}
            </Button>
            <Button size="sm" icon={<Zap size={15} aria-hidden />} disabled={!sel.length || testing.size > 0} onClick={() => void probe(sel)}>
              {tr.lab.testSelected}
            </Button>
            <Button size="sm" icon={<Play size={15} aria-hidden />} disabled={!sel.length} loading={bench.isPending} onClick={() => bench.mutate(sel)}>
              {tr.lab.runBenchmark}
            </Button>
            <Button size="sm" variant="ghost" icon={<Trash2 size={15} aria-hidden />} disabled={!list.length} onClick={() => setClearAll(true)}>
              {tr.lab.clearAll}
            </Button>
            {sel.length > 0 && <span className={s.selCount}>{tr.lab.selected(sel.length)}</span>}
          </div>
          {models.isLoading ? (
            <SkeletonRows rows={3} />
          ) : models.isError ? (
            <p className={s.error}>{messageOf(models.error)}</p>
          ) : !list.length ? (
            <p className={s.hint}>{tr.lab.modelsEmpty}</p>
          ) : (
            <div className={s.tableWrap}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th scope="col" className={s.colSel}>
                      <span className="sr-only">{tr.lab.colSelect}</span>
                      <span aria-hidden>{tr.lab.colSelect}</span>
                    </th>
                    <th scope="col">{tr.lab.colModel}</th>
                    <th scope="col">{tr.lab.colConnection}</th>
                    <th scope="col">{tr.lab.colBenchmark}</th>
                    <th scope="col">{tr.lab.colLatency}</th>
                    <th scope="col" className={s.colMenu}>
                      <span className="sr-only">{tr.common.more}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((m) => (
                    <ModelTr
                      key={m.id}
                      m={m}
                      checked={selected.has(m.id)}
                      onCheck={(on) =>
                        setSelected((old) => {
                          const n = new Set(old);
                          if (on) n.add(m.id);
                          else n.delete(m.id);
                          return n;
                        })
                      }
                      testing={testing.has(m.id)}
                      runState={activeRuns.get(m.id) ?? null}
                      onTest={() => void probe([m.id])}
                      onOpen={() => setResult({ model: m, runId: benchOf(m)?.run_id ?? null, name: m.display_name })}
                      onClear={() => void clearResults(m.id)}
                      onToggle={() => void toggleEnabled(m)}
                      onDelete={() => setDelModel(m)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* ----------------------------------------------------------- karşılaştırma */}
        <section className={s.section} aria-labelledby="lab-chart">
          <h2 id="lab-chart" className={s.sectionTitle}>
            {tr.lab.chart}
          </h2>
          <QualityChart points={points} />
        </section>

        {/* -------------------------------------------------------------- geçmiş */}
        <section className={s.section} aria-labelledby="lab-history">
          <h2 id="lab-history" className={s.sectionTitle}>
            {tr.lab.history}
          </h2>
          {runs.isLoading ? (
            <SkeletonRows rows={3} />
          ) : !runs.data?.length ? (
            <p className={s.hint}>{tr.lab.historyEmpty}</p>
          ) : (
            <ul className={s.rows}>
              {runs.data.map((r) => {
                const b = r.metrics as Partial<Bench>;
                return (
                  <li key={r.id} className={s.runRow}>
                    <RunStateBadge state={r.state} />
                    <button type="button" className={s.runName} onClick={() => setResult({ model: list.find((m) => m.id === r.model_id) ?? null, runId: r.id, name: r.model_name })}>
                      {r.model_name}
                    </button>
                    <span className={s.runMetrics}>
                      {r.state === 'completed' && b.n != null ? (
                        <>
                          <span>{tr.lab.benchAccuracy(formatPercent(b.accuracy ?? null))}</span>
                          <span>{tr.lab.benchN(b.n)}</span>
                          <span className={b.critical_errors ? s.criticalText : undefined}>{tr.lab.benchCritical(b.critical_errors ?? 0)}</span>
                          {!!b.scope_guarded && <span title={tr.lab.benchScopeGuardedHint}>{tr.lab.benchScopeGuarded(b.scope_guarded)}</span>}
                          <span>p50 {formatMs(b.p50_ms ?? null)}</span>
                        </>
                      ) : null}
                      {!r.current_fingerprint && <span className={s.stale}>{tr.lab.staleRun}</span>}
                    </span>
                    <time className={s.time} dateTime={r.created_at}>
                      {formatDateTime(r.created_at)}
                    </time>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>

      <AddProviderDialog open={adding} onOpenChange={setAdding} onDone={refresh} />
      <KeyDialog provider={keyFor} onOpenChange={(o) => !o && setKeyFor(null)} />
      <ModelsDialog provider={modelsFor} onOpenChange={(o) => !o && setModelsFor(null)} onDone={refresh} />
      <ConfirmDialog
        open={!!delProvider}
        onOpenChange={(o) => !o && setDelProvider(null)}
        title={tr.lab.deleteProviderTitle(delProvider?.name ?? '')}
        description={tr.lab.deleteProviderDesc}
        confirmLabel={tr.common.delete}
        danger
        onConfirm={async () => {
          try {
            await api.del(`/providers/${delProvider!.id}`);
            toast.show(tr.lab.providerDeleted);
            void qc.invalidateQueries({ queryKey: ['providers'] });
            refresh();
          } catch (e) {
            toast.show(messageOf(e), { tone: 'error' });
          }
        }}
      />
      <ConfirmDialog
        open={!!delModel}
        onOpenChange={(o) => !o && setDelModel(null)}
        title={tr.lab.deleteModelTitle(delModel?.display_name ?? '')}
        description={tr.lab.deleteModelDesc}
        confirmLabel={tr.common.delete}
        danger
        onConfirm={async () => {
          try {
            await api.del(`/models/${delModel!.id}`);
            toast.show(tr.lab.modelDeleted);
            refresh();
          } catch (e) {
            toast.show(messageOf(e), { tone: 'error' });
          }
        }}
      />
      <ConfirmDialog open={clearAll} onOpenChange={setClearAll} title={tr.lab.clearAllTitle} description={tr.lab.clearAllDesc} confirmLabel={tr.lab.clearAll} danger onConfirm={() => clearResults(null)} />
      <ResultDrawer target={result} onOpenChange={(o) => !o && setResult(null)} />
    </div>
  );
}

function RunStateBadge({ state }: { state: string }) {
  const map: Record<string, { tone: Tone; icon?: 'spin' | 'clock' | 'onay' | 'ban' | 'celiski' }> = {
    queued: { tone: 'taslak', icon: 'clock' },
    running: { tone: 'inceleme', icon: 'spin' },
    completed: { tone: 'onay', icon: 'onay' },
    cancelled: { tone: 'taslak', icon: 'ban' },
    failed: { tone: 'celiski', icon: 'celiski' },
  };
  const st = map[state] ?? { tone: 'taslak' as Tone };
  return <StatusBadge tone={st.tone} icon={st.icon} label={tr.lab.runStates[state] ?? state} size="sm" />;
}

interface ModelTrProps {
  m: ModelRow;
  checked: boolean;
  onCheck: (on: boolean) => void;
  testing: boolean;
  runState: string | null;
  onTest: () => void;
  onOpen: () => void;
  onClear: () => void;
  onToggle: () => void;
  onDelete: () => void;
}

function ModelTr({ m, checked, onCheck, testing, runState, onTest, onOpen, onClear, onToggle, onDelete }: ModelTrProps) {
  const probe = probeSummary(m);
  const b = benchOf(m);
  const lat = latencyOf(m);
  return (
    <tr>
      <td className={s.colSel}>
        <input type="checkbox" className={s.check} checked={checked} onChange={(e) => onCheck(e.target.checked)} aria-label={tr.lab.selectModel(m.display_name)} />
      </td>
      <td>
        <div className={s.modelCell}>
          <span className={s.modelName}>{m.display_name}</span>
          <span className={s.mono}>
            {m.provider_name} / {m.remote_id}
          </span>
          <span className={s.modelTags}>
            {m.is_fixture && <span className={s.tag}>{tr.lab.fixture}</span>}
            {!m.enabled && <span className={s.tag}>{tr.lab.disabled}</span>}
          </span>
          {m.eligible && m.task_label ? (
            <span className={s.taskLabel}>
              <ShieldCheck size={14} aria-hidden />
              {m.task_label}
            </span>
          ) : (
            <span className={s.reason}>{(m.eligibility_reason && tr.labReasons[m.eligibility_reason]) || modelReason(m.eligibility_reason)}</span>
          )}
        </div>
      </td>
      <td data-label={tr.lab.colConnection}>{testing ? <StatusBadge tone="inceleme" icon="spin" label={tr.lab.testing} size="sm" /> : <StatusBadge tone={probe.tone} icon={probe.icon} label={probe.label} size="sm" />}</td>
      <td data-label={tr.lab.colBenchmark}>
        {runState ? (
          <StatusBadge tone={runState === 'running' ? 'inceleme' : 'taslak'} icon={runState === 'running' ? 'spin' : 'clock'} label={runState === 'running' ? tr.lab.benchRunning : tr.lab.benchQueued} size="sm" />
        ) : !b ? (
          <span className={s.muted}>{tr.lab.benchNone}</span>
        ) : (
          <div className={s.benchCell}>
            {benchPassed(b) ? <StatusBadge tone="onay" label={tr.lab.benchPassed} size="sm" /> : <StatusBadge tone="celiski" label={tr.lab.benchFailed} size="sm" />}
            <span className={s.benchMeta}>
              <span className="tabular">{tr.lab.benchN(b.n)}</span>
              <span className={b.critical_errors ? s.criticalText : 'tabular'}>{tr.lab.benchCritical(b.critical_errors)}</span>
            </span>
            {b.current_fingerprint === false && <span className={s.stale}>{tr.lab.benchStale}</span>}
          </div>
        )}
      </td>
      <td className="tabular" data-label={tr.lab.colLatency}>
        <span className={s.latency}>
          <span>{formatMs(lat.p50_ms)}</span>
          <span className={s.slash}>/</span>
          <span className={lat.p95_ms == null ? s.muted : undefined}>{lat.p95_ms == null ? tr.lab.insufficient : formatMs(lat.p95_ms)}</span>
        </span>
      </td>
      <td className={s.colMenu}>
        <RowMenu
          label={tr.lab.modelActions(m.display_name)}
          actions={[
            { label: tr.lab.test, icon: <Zap size={15} />, onSelect: onTest },
            { label: tr.lab.openResult, icon: <ChevronRight size={15} />, onSelect: onOpen },
            { label: tr.lab.clearResult, icon: <Trash2 size={15} />, onSelect: onClear },
            { label: m.enabled ? tr.lab.disable : tr.lab.enable, icon: m.enabled ? <ZapOff size={15} /> : <Zap size={15} />, onSelect: onToggle, separatorBefore: true },
            { label: tr.lab.deleteModel, icon: <Trash2 size={15} />, onSelect: onDelete, danger: true },
          ]}
        />
      </td>
    </tr>
  );
}

function fieldErr(e: unknown): Record<string, string> {
  return e instanceof ApiError ? e.fieldErrors() : {};
}

function AddProviderDialog({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [url, setUrl] = useState('');
  const [key, setKey] = useState('');
  const [ids, setIds] = useState('');
  const [errors, setErrors] = useState<{ url?: string; ids?: string; form?: string }>({});
  // Sunucu izin listesinde olmayan adres: yönetici açık bir onayla izin verir (metis.env'e dokunmadan; 2026-10-19).
  const [notAllowed, setNotAllowed] = useState<string | null>(null);
  const parsed = [...new Set(ids.split(/[\n,]+/).map((x) => x.trim()).filter(Boolean))];
  const m = useMutation({
    mutationFn: async (allow: boolean) => {
      if (allow) {
        await api.post('/allowed-endpoints', { url: url.trim() });
        toast.show(tr.lab.endpointAllowed);
        void qc.invalidateQueries({ queryKey: ['allowed-endpoints'] });
      }
      return api.post<Provider>('/providers', { base_url: url.trim(), api_key: key, model_ids: parsed });
    },
    onSuccess: () => {
      toast.show(tr.lab.providerAdded);
      void qc.invalidateQueries({ queryKey: ['providers'] });
      void qc.invalidateQueries({ queryKey: ['allowed-endpoints'] });
      onDone();
      setUrl('');
      setKey('');
      setIds('');
      setNotAllowed(null);
      onOpenChange(false);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === 'ENDPOINT_NOT_ALLOWED') {
        setErrors({});
        setNotAllowed(url.trim().replace(/\/+$/, ''));
        return;
      }
      setNotAllowed(null);
      const f = fieldErr(e);
      setErrors({ url: f.base_url ? messageOf(e) : undefined, ids: f.model_ids ? messageOf(e) : undefined, form: f.base_url || f.model_ids ? undefined : messageOf(e) });
    },
  });
  function submit(allow: boolean) {
    const next: typeof errors = {};
    if (!url.trim()) next.url = tr.lab.baseUrlRequired;
    if (!parsed.length) next.ids = tr.lab.modelIdsRequired;
    setErrors(next);
    if (!Object.keys(next).length) m.mutate(allow);
  }
  const askAllow = notAllowed !== null && notAllowed === url.trim().replace(/\/+$/, '');
  const allowRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (askAllow) allowRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [askAllow]);
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setErrors({});
        setNotAllowed(null);
        onOpenChange(o);
      }}
      title={tr.lab.addProvider}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {tr.common.cancel}
          </Button>
          <Button variant="primary" loading={m.isPending} onClick={() => submit(askAllow)}>
            {askAllow ? tr.lab.allowAndAdd : tr.lab.addProvider}
          </Button>
        </>
      }
    >
      <div className={s.form}>
        <Field label={tr.lab.baseUrl} hint={tr.lab.baseUrlHint} error={errors.url}>
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://127.0.0.1:8000/v1" invalid={!!errors.url} autoComplete="off" spellCheck={false} />}
        </Field>
        <Field label={tr.lab.apiKey} hint={tr.lab.apiKeyHint}>
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} type="password" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="new-password" />}
        </Field>
        <Field label={tr.lab.modelIds} hint={tr.lab.modelIdsHint} error={errors.ids}>
          {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} value={ids} onChange={(e) => setIds(e.target.value)} rows={4} invalid={!!errors.ids} spellCheck={false} className={s.monoInput} />}
        </Field>
        {askAllow && (
          <div ref={allowRef} className={s.allowBox} role="alert">
            <strong>{tr.lab.allowTitle}</strong>
            <span>{tr.lab.allowBody(notAllowed)}</span>
          </div>
        )}
        {errors.form && (
          <p className={s.error} role="alert">
            {errors.form}
          </p>
        )}
      </div>
    </Dialog>
  );
}

function KeyDialog({ provider, onOpenChange }: { provider: Provider | null; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [key, setKey] = useState('');
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => api.post(`/providers/${provider!.id}/key`, { api_key: key }),
    onSuccess: () => {
      toast.show(tr.lab.keyChanged);
      void qc.invalidateQueries({ queryKey: ['providers'] });
      void qc.invalidateQueries({ queryKey: ['models'] });
      setKey('');
      onOpenChange(false);
    },
    onError: (e) => setError(messageOf(e)),
  });
  return (
    <Dialog
      open={!!provider}
      onOpenChange={(o) => {
        setError(null);
        setKey('');
        onOpenChange(o);
      }}
      title={tr.lab.changeKeyTitle(provider?.name ?? '')}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {tr.common.cancel}
          </Button>
          <Button variant="primary" loading={m.isPending} onClick={() => m.mutate()}>
            {tr.common.save}
          </Button>
        </>
      }
    >
      <Field label={tr.lab.apiKey} hint={tr.lab.apiKeyHint} error={error}>
        {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} type="password" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="new-password" />}
      </Field>
    </Dialog>
  );
}

function ModelsDialog({ provider, onOpenChange, onDone }: { provider: Provider | null; onOpenChange: (o: boolean) => void; onDone: () => void }) {
  const toast = useToast();
  const [ids, setIds] = useState('');
  const [error, setError] = useState<string | null>(null);
  const parsed = [...new Set(ids.split(/[\n,]+/).map((x) => x.trim()).filter(Boolean))];
  const m = useMutation({
    mutationFn: () => api.post<{ added: string[] }>(`/providers/${provider!.id}/models`, { model_ids: parsed }),
    onSuccess: (r) => {
      toast.show(tr.lab.modelsAdded(r.added.length));
      onDone();
      setIds('');
      onOpenChange(false);
    },
    onError: (e) => setError(messageOf(e)),
  });
  return (
    <Dialog
      open={!!provider}
      onOpenChange={(o) => {
        setError(null);
        onOpenChange(o);
      }}
      title={tr.lab.addModelsTitle(provider?.name ?? '')}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {tr.common.cancel}
          </Button>
          <Button variant="primary" loading={m.isPending} onClick={() => (parsed.length ? m.mutate() : setError(tr.lab.modelIdsRequired))}>
            {tr.lab.addModels}
          </Button>
        </>
      }
    >
      <Field label={tr.lab.modelIds} hint={tr.lab.modelIdsHint} error={error}>
        {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} value={ids} onChange={(e) => setIds(e.target.value)} rows={4} spellCheck={false} className={s.monoInput} />}
      </Field>
    </Dialog>
  );
}

function ResultDrawer({ target, onOpenChange }: { target: { model: ModelRow | null; runId: string | null; name: string } | null; onOpenChange: (o: boolean) => void }) {
  const run = useQuery({
    queryKey: ['benchmark-run', target?.runId],
    queryFn: () => api.get<RunDetail>(`/benchmark-runs/${target!.runId}`),
    enabled: !!target?.runId,
  });
  const m = target?.model ?? null;
  const probes = m ? probesOf(m) : null;
  const metrics = run.data?.metrics;
  return (
    <Drawer open={!!target} onOpenChange={onOpenChange} title={tr.lab.resultTitle(target?.name ?? '')} width={640}>
      <div className={s.drawer}>
        {probes && (
          <section className={s.drawerBlock}>
            <h3 className={s.drawerTitle}>{tr.lab.probeDetail}</h3>
            <dl className={s.kv}>
              {CAPS.map((c) => {
                const p = probes[c];
                return (
                  <div key={c} className={s.kvRow}>
                    <dt>{tr.lab.probeCaps[c]}</dt>
                    <dd>
                      <StatusBadge
                        tone={p?.status === 'tested_pass' ? 'onay' : p?.status === 'tested_fail' ? 'celiski' : 'taslak'}
                        icon={p?.status === 'tested_pass' ? 'onay' : p?.status === 'tested_fail' ? 'celiski' : 'taslak'}
                        label={tr.lab.probeStatus[p?.status ?? 'unknown'] ?? p?.status ?? ''}
                        size="sm"
                      />
                      {p?.at && <span className={s.time}>{formatDateTime(p.at)}</span>}
                      {p?.error && <span className={s.mono}>{p.error}</span>}
                    </dd>
                  </div>
                );
              })}
            </dl>
            <details className={s.tech}>
              <summary>
                <ChevronRight size={14} aria-hidden className={s.chev} />
                {tr.common.technicalDetails}
              </summary>
              <p className={s.drawerTitle}>{tr.lab.transport}</p>
              <pre className={s.pre}>{JSON.stringify(m?.transport_profile ?? {}, null, 2)}</pre>
            </details>
          </section>
        )}
        <section className={s.drawerBlock}>
          <h3 className={s.drawerTitle}>{tr.lab.colBenchmark}</h3>
          {!target?.runId ? (
            <p className={s.hint}>{tr.lab.noResult}</p>
          ) : run.isLoading ? (
            <SkeletonRows rows={4} />
          ) : !run.data ? (
            <p className={s.error}>{messageOf(run.error)}</p>
          ) : (
            <>
              <p className={s.benchSummary}>
                <RunStateBadge state={run.data.state} />
                {metrics?.n != null && (
                  <>
                    <span>{tr.lab.benchAccuracy(formatPercent(metrics.accuracy ?? null))}</span>
                    <span>{tr.lab.benchN(metrics.n)}</span>
                    <span className={metrics.critical_errors ? s.criticalText : undefined}>{tr.lab.benchCritical(metrics.critical_errors ?? 0)}</span>
                  </>
                )}
              </p>
              {metrics?.pass_rule && (
                <p className={s.hint}>
                  {tr.lab.passRule}: {metrics.pass_rule}
                </p>
              )}
              <div className={s.tableWrap}>
                <table className={s.miniTable}>
                  <thead>
                    <tr>
                      <th scope="col">{tr.lab.resultCase}</th>
                      <th scope="col">{tr.lab.resultExpected}</th>
                      <th scope="col">{tr.lab.resultDecision}</th>
                      <th scope="col">{tr.lab.resultPassed}</th>
                      <th scope="col">{tr.lab.resultLatency}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {run.data.results.map((r) => (
                      <tr key={r.case}>
                        <td className={s.mono}>{r.case}</td>
                        <td>{r.expected ? (tr.decisions[r.expected] ?? r.expected) : tr.common.none}</td>
                        <td>{r.decision ? (tr.decisions[r.decision] ?? r.decision) : (r.error ?? tr.common.none)}</td>
                        <td>
                          <StatusBadge tone={r.passed ? 'onay' : 'celiski'} label={r.passed ? tr.lab.resultPass : tr.lab.resultFail} size="sm" />
                          {r.critical_kind && <span className={s.criticalText}> {tr.lab.resultCriticalKind(r.critical_kind)}</span>}
                        </td>
                        <td className="tabular">{formatMs(r.latency_ms)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      </div>
    </Drawer>
  );
}

