import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Button, ConfirmDialog, IconButton, Input, SkeletonRows, useToast } from '@/design/primitives';
import { DIMS, useCatalog, type Dim } from '@/app/ScopeBar';
import { useSession } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { messageOf } from '@/features/shared/hooks';
import s from './Settings.module.css';

export function ScopesTab() {
  const session = useSession();
  const catalog = useCatalog(session.projectId);
  const canEdit = session.roles.has('contributor') || session.roles.has('steward');
  const [confirm, setConfirm] = useState<Schemas['ScopeValueOut'] | null>(null);
  const qc = useQueryClient();
  const toast = useToast();
  if (catalog.isLoading) return <SkeletonRows rows={4} />;
  if (!catalog.data) return <p className={s.error}>{messageOf(catalog.error)}</p>;
  return (
    <div className={s.stack}>
      <p className={s.hint}>{tr.settings.scopesLead}</p>
      {!canEdit && <p className={s.hint}>{tr.settings.scopesReadOnly}</p>}
      <div className={s.dimGrid}>
        {DIMS.map((d) => (
          <section key={d} className={s.dim} aria-labelledby={`dim-${d}`}>
            <h2 id={`dim-${d}`} className={s.blockTitle}>
              {tr.scope.dims[d]}
            </h2>
            {catalog.data[d].length === 0 ? (
              <p className={s.hint}>{tr.scope.noValues}</p>
            ) : (
              <ul className={s.values}>
                {catalog.data[d].map((v) => (
                  <li key={v.id} className={s.value}>
                    <span className={s.valueText}>{v.value}</span>
                    {canEdit && (
                      <IconButton label={tr.settings.deleteValue(v.value)} size="sm" onClick={() => setConfirm(v)}>
                        <Trash2 size={15} aria-hidden />
                      </IconButton>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {canEdit && <AddValue dim={d} />}
          </section>
        ))}
      </div>
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm ? tr.settings.deleteValueTitle(confirm.value) : ''}
        description={tr.settings.deleteValueDesc}
        confirmLabel={tr.common.delete}
        danger
        onConfirm={async () => {
          if (!confirm) return;
          try {
            await api.del(`/projects/${session.projectId}/scopes/${confirm.id}`);
            qc.invalidateQueries({ queryKey: ['scopes', session.projectId] });
            toast.show(tr.settings.valueDeleted);
          } catch (e) {
            toast.show(messageOf(e), { tone: 'error' });
          }
        }}
      />
    </div>
  );
}

function AddValue({ dim }: { dim: Dim }) {
  const session = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => api.post(`/projects/${session.projectId}/scopes`, { dimension: dim, value: value.trim() }),
    onSuccess: () => {
      setValue('');
      setError(null);
      qc.invalidateQueries({ queryKey: ['scopes', session.projectId] });
      toast.show(tr.settings.valueAdded);
    },
    onError: (e) => setError(messageOf(e)),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!value.trim() || m.isPending) return;
    m.mutate();
  };
  const errId = `add-${dim}-err`;
  return (
    <form className={s.addValue} onSubmit={submit}>
      <Input
        aria-label={tr.settings.newValue(tr.scope.dims[dim]!)}
        placeholder={tr.settings.newValue(tr.scope.dims[dim]!)}
        value={value}
        invalid={!!error}
        aria-describedby={error ? errId : undefined}
        onChange={(e) => setValue(e.target.value)}
      />
      <Button type="submit" size="sm" icon={<Plus size={15} aria-hidden />} loading={m.isPending} disabled={!value.trim()}>
        {tr.settings.addValue}
      </Button>
      {error && (
        <p id={errId} className={s.error} role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
