import { useQuery } from '@tanstack/react-query';
import { Select } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';

export type AvailableModel = Schemas['AvailableModel'];

export function useAvailableModels(projectId: string | null) {
  return useQuery({
    queryKey: ['models-available', projectId],
    queryFn: () => api.get<AvailableModel[]>('/models/available', { project_id: projectId }),
    enabled: !!projectId,
    retry: false,
    staleTime: 30_000,
  });
}

export function modelReason(code: string | null | undefined): string {
  if (!code) return '';
  return tr.modelReasons[code] ?? code;
}

export function modelOptionLabel(m: AvailableModel): string {
  if (!m.eligible) return tr.models.ineligible(m.display_name, modelReason(m.reason));
  return m.is_fixture ? tr.models.fixture(m.display_name) : m.display_name;
}

interface Props {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  models: AvailableModel[];
  /** Boş değerin etiketi: "Otomatik", "Model kullanma" ya da "Model seç" (yer tutucu). */
  emptyLabel: string;
  disabled?: boolean;
  className?: string;
  'aria-describedby'?: string;
  'aria-label'?: string;
}

/**
 * Açık model seçimi: uygun olmayan modeller devre dışı ve nedeniyle listelenir.
 * Sessiz seçim yok: boş değer her zaman açıkça etiketlenir.
 */
export function ModelSelect({ id, value, onChange, models, emptyLabel, disabled, className, ...aria }: Props) {
  const known = !value || models.some((m) => m.id === value);
  return (
    <Select id={id} value={known ? value : ''} onChange={(e) => onChange(e.target.value)} disabled={disabled} className={className} {...aria}>
      <option value="">{emptyLabel}</option>
      {models.map((m) => (
        <option key={m.id} value={m.id} disabled={!m.eligible}>
          {modelOptionLabel(m)}
        </option>
      ))}
    </Select>
  );
}
