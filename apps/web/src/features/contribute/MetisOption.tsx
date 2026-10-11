import { useQuery } from '@tanstack/react-query';
import { Sparkles } from 'lucide-react';
import { useId, useState } from 'react';
import { Button, Field, Select } from '@/design/primitives';
import { useSession } from '@/app/session';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import type { ModelOption, SourceDetail } from './types';
import s from './Contribute.module.css';

const unavailable = (e: unknown) => e instanceof ApiError && (e.status === 404 || e.status === 405);
const reasonText = (code: string | null | undefined) => (code ? tr.modelReasons[code] ?? code : '');

/** Görev başlatma hatası: MODEL_NOT_ELIGIBLE / MODEL_REQUIRED ayrıntıdaki nedenle birlikte. */
function jobError(e: unknown): string {
  if (unavailable(e)) return tr.errors.JOBS_UNAVAILABLE!;
  if (!(e instanceof ApiError)) return errorMessage('NETWORK');
  const reason = typeof e.details.reason === 'string' ? reasonText(e.details.reason) : '';
  return reason ? `${errorMessage(e.code)} ${reason}` : errorMessage(e.code);
}

/** "Metis hazırlasın": açık model seçimi (sessiz seçim yok) → görev başlar → /gorevler/{id}. */
export function MetisOption({ source, onStarted }: { source: SourceDetail | null; onStarted: (jobId: string) => void }) {
  const { projectId } = useSession();
  const [modelId, setModelId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reasonId = useId();
  const models = useQuery({
    queryKey: ['models-available', projectId],
    queryFn: () => api.get<ModelOption[]>('/models/available', { project_id: projectId }),
    enabled: !!projectId,
    retry: false,
  });
  const list = models.data ?? [];
  const eligible = list.filter((m) => m.eligible);
  const revisionId = source?.current_revision?.id;

  let reason: string | null = null;
  if (models.isError) reason = unavailable(models.error) ? tr.errors.JOBS_UNAVAILABLE! : errorMessage(models.error instanceof ApiError ? models.error.code : 'NETWORK');
  else if (models.data && list.length === 0) reason = tr.modelReasons.no_models!;
  else if (models.data && eligible.length === 0) reason = [...new Set(list.map((m) => reasonText(m.reason)).filter(Boolean))].join(' ') || tr.contribute.modelsEmpty;
  else if (!revisionId) reason = tr.contribute.needSource;
  else if (!modelId) reason = tr.contribute.modelRequired;

  async function start() {
    if (busy || !revisionId || !modelId) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<Schemas['JobRow']>(`/projects/${projectId}/jobs`, { kind: 'prepare_draft', source_revision_ids: [revisionId], model_id: modelId });
      onStarted(res.id);
    } catch (e) {
      setError(jobError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={s.option}>
      <div className={s.optionHead}>
        <Sparkles size={20} aria-hidden />
        <h3 className={s.optionTitle}>{tr.contribute.metisTitle}</h3>
      </div>
      <p className={s.optionText}>{tr.contribute.metisText}</p>
      {list.length > 0 && (
        <Field label={tr.contribute.model}>
          {({ id }) => (
            <Select id={id} value={modelId} onChange={(e) => setModelId(e.target.value)}>
              <option value="">{tr.contribute.modelPlaceholder}</option>
              {list.map((m) => (
                <option key={m.id} value={m.id} disabled={!m.eligible}>
                  {m.eligible ? (m.is_fixture ? tr.contribute.fixtureModel(m.display_name) : m.display_name) : tr.contribute.modelIneligible(m.display_name, reasonText(m.reason))}
                </option>
              ))}
            </Select>
          )}
        </Field>
      )}
      <div className={s.optionAction}>
        <Button variant="primary" onClick={start} loading={busy} disabled={!!reason || models.isLoading} aria-describedby={reason || error ? reasonId : undefined}>
          {tr.contribute.startJob}
        </Button>
        {(error || reason) && (
          <p id={reasonId} className={error ? s.error : s.reason} role={error ? 'alert' : undefined}>
            {error ?? reason}
          </p>
        )}
      </div>
    </div>
  );
}
