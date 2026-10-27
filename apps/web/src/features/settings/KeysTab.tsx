import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Button, ConfirmDialog, Field, Input, SkeletonRows, StatusBadge, useToast } from '@/design/primitives';
import { useSession } from '@/app/session';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { formatDateTime } from '@/lib/format';
import { messageOf } from '@/features/shared/hooks';
import s from './Settings.module.css';

type MyKey = Schemas['MyKeyOut'];
type Check = Schemas['KeyCheckOut'];

const fmt = (n: number) => n.toLocaleString('tr-TR');

/** Anahtarım (2.0.28): herkes modelleri kendi API anahtarıyla kullanır. Anahtar şifreli saklanır, hiçbir yerde gösterilmez. */
export function KeysTab() {
  const { isAdmin } = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const keys = useQuery({ queryKey: ['me-keys'], queryFn: () => api.get<MyKey[]>('/me/keys') });
  const [editing, setEditing] = useState<string | null>(null);
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<MyKey | null>(null);
  const [checks, setChecks] = useState<Record<string, Check | string>>({});

  const refresh = () => void qc.invalidateQueries({ queryKey: ['me-keys'] });
  const save = useMutation({
    mutationFn: ({ provider, key }: { provider: string; key: string }) => api.put(`/me/keys/${provider}`, { api_key: key }),
    onSuccess: (_r, { provider }) => {
      refresh();
      void qc.invalidateQueries({ queryKey: ['models-available'] });
      setEditing(null);
      setValue('');
      setError(null);
      toast.show(tr.keys.saved);
      check.mutate(provider);
    },
    onError: (e) => {
      const kind = e instanceof ApiError ? e.fieldErrors().api_key : undefined;
      setError(kind === 'invalid_chars' ? tr.keys.invalidChars : e instanceof ApiError && e.code === 'VALIDATION_ERROR' ? tr.keys.tooShort : messageOf(e));
    },
  });
  const check = useMutation({
    mutationFn: (provider: string) => api.post<Check>(`/me/keys/${provider}/check`),
    onSuccess: (r, provider) => {
      setChecks((c) => ({ ...c, [provider]: r }));
      refresh();
      void qc.invalidateQueries({ queryKey: ['me-usage'] });
      void qc.invalidateQueries({ queryKey: ['usage-users'] });
    },
    onError: (e, provider) => setChecks((c) => ({ ...c, [provider]: messageOf(e) })),
  });
  const remove = useMutation({
    mutationFn: (k: MyKey) => api.del(`/me/keys/${k.provider_id}`),
    onSuccess: () => {
      refresh();
      void qc.invalidateQueries({ queryKey: ['models-available'] });
      toast.show(tr.keys.removed);
    },
    onError: (e) => toast.show(messageOf(e), { tone: 'error' }),
  });

  if (keys.isLoading) return <SkeletonRows rows={3} />;
  if (keys.isError) return <p className={s.error}>{messageOf(keys.error)}</p>;

  return (
    <div className={s.stack}>
      <section className={s.block} aria-labelledby="keys-h">
        <h2 id="keys-h" className={s.blockTitle}>
          {tr.keys.title}
        </h2>
        <p className={s.hint}>{tr.keys.lead}</p>
        {keys.data?.length === 0 && <p className={s.hint}>{tr.keys.noProviders}</p>}
        <div className={s.opsRows}>
          {keys.data?.map((k) => {
            const result = checks[k.provider_id];
            return (
              <div key={k.provider_id} className={s.keyRow}>
                <div className={s.opsRow}>
                  <div className={s.grow}>
                    <div className={s.opsName}>
                      {k.provider_name || tr.keys.unnamed} <KeyBadge k={k} />
                    </div>
                    <div className={s.hint}>
                      {k.models.length ? tr.keys.models(k.models.join(', ')) : tr.keys.noModels}
                      {k.updated_at && ` · ${tr.keys.updated(formatDateTime(k.updated_at))}`}
                    </div>
                    {k.uses_shared && <div className={s.hint}>{k.key_required ? tr.keys.adminShared : tr.keys.notRequired}</div>}
                  </div>
                  {k.has_key && (
                    <Button size="sm" variant="ghost" loading={check.isPending && check.variables === k.provider_id} onClick={() => check.mutate(k.provider_id)}>
                      {tr.keys.test}
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => (setEditing(k.provider_id), setValue(''), setError(null))}>
                    {k.has_key ? tr.keys.change : tr.keys.add}
                  </Button>
                  {k.has_key && (
                    <Button size="sm" variant="ghost" onClick={() => setRemoving(k)}>
                      {tr.keys.remove}
                    </Button>
                  )}
                </div>
                {result && (
                  <p className={typeof result !== 'string' && result.ok ? s.hint : s.error} role="status">
                    {typeof result === 'string' ? result : result.ok ? tr.keys.checkOk(result.model) : tr.keys.checkFailed(keyError(result.error))}
                  </p>
                )}
                {editing === k.provider_id && (
                  <form
                    className={s.keyForm}
                    onSubmit={(e) => {
                      e.preventDefault();
                      save.mutate({ provider: k.provider_id, key: value });
                    }}
                  >
                    <Field label={tr.keys.field(k.provider_name || tr.keys.unnamed)} hint={tr.keys.fieldHint} error={error}>
                      {({ id, describedBy }) => (
                        <Input id={id} aria-describedby={describedBy} type="password" value={value} onChange={(e) => setValue(e.target.value)} autoComplete="new-password" spellCheck={false} autoFocus />
                      )}
                    </Field>
                    <div className={s.pwRow}>
                      <Button type="submit" variant="primary" loading={save.isPending} disabled={!value.trim()}>
                        {tr.keys.save}
                      </Button>
                      <Button type="button" variant="ghost" onClick={() => (setEditing(null), setValue(''), setError(null))}>
                        {tr.keys.cancel}
                      </Button>
                    </div>
                  </form>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <MyUsage />
      {isAdmin && <UsageByUser />}

      <ConfirmDialog
        open={!!removing}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={tr.keys.removeTitle}
        description={tr.keys.removeDesc}
        confirmLabel={tr.keys.remove}
        danger
        onConfirm={() => {
          if (removing) remove.mutate(removing);
          setRemoving(null);
        }}
      />
    </div>
  );
}

function keyError(code: string | null | undefined): string {
  if (code === 'HTTP_401' || code === 'HTTP_403') return tr.keys.rejected;
  if (code === 'CONNECTION_FAILED' || code === 'TLS_FAILED' || code === 'TIMEOUT' || code === 'PROVIDER_BUSY') return tr.keys.unreachable;
  return code ? tr.keys.otherError(code) : errorMessage('INTERNAL');
}

function KeyBadge({ k }: { k: MyKey }) {
  if (!k.has_key && !k.key_required) return <StatusBadge size="sm" tone="onay" label={tr.keys.notRequiredBadge} />;
  if (!k.has_key) return <StatusBadge size="sm" tone={k.uses_shared ? 'onay' : 'taslak'} label={k.uses_shared ? tr.keys.sharedBadge : tr.keys.noneBadge} />;
  if (k.check_ok === false && (k.check_error === 'HTTP_401' || k.check_error === 'HTTP_403')) return <StatusBadge size="sm" tone="celiski" label={tr.keys.rejectedBadge} />;
  // Bağlantı sorunu anahtarın geçersiz olduğunu göstermez.
  if (k.check_ok === false) return <StatusBadge size="sm" tone="dikkat" label={tr.keys.failedBadge} />;
  return <StatusBadge size="sm" tone="onay" label={k.check_ok ? tr.keys.okBadge : tr.keys.savedBadge} />;
}

function MyUsage() {
  const usage = useQuery({ queryKey: ['me-usage'], queryFn: () => api.get<Schemas['MyUsageOut']>('/me/usage') });
  return (
    <section className={s.block} aria-labelledby="usage-h">
      <h2 id="usage-h" className={s.blockTitle}>
        {tr.keys.myUsage(usage.data?.days ?? 30)}
      </h2>
      {usage.isLoading ? (
        <SkeletonRows rows={2} />
      ) : usage.data && usage.data.rows.length ? (
        <div className={s.tableScroll}>
          <table className={s.usageTable}>
            <thead>
              <tr>
                <th scope="col">{tr.keys.purpose}</th>
                <th scope="col">{tr.keys.keySource}</th>
                <th scope="col">{tr.keys.calls}</th>
                <th scope="col">{tr.keys.inTokens}</th>
                <th scope="col">{tr.keys.outTokens}</th>
              </tr>
            </thead>
            <tbody>
              {usage.data.rows.map((r) => (
                <tr key={`${r.purpose}:${r.key_source}`}>
                  <td>{tr.keys.purposes[r.purpose] ?? r.purpose}</td>
                  <td>{tr.keys.sources[r.key_source] ?? r.key_source}</td>
                  <td>
                    {fmt(r.calls)}
                    {r.cached > 0 && <span className={s.hintInline}> {tr.keys.cached(fmt(r.cached))}</span>}
                  </td>
                  <td>{fmt(r.prompt_tokens)}</td>
                  <td>{fmt(r.completion_tokens)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className={s.hint}>{tr.keys.noUsage}</p>
      )}
    </section>
  );
}

function UsageByUser() {
  const usage = useQuery({ queryKey: ['usage-users'], queryFn: () => api.get<Schemas['UsageByUserOut']>('/usage/users') });
  return (
    <section className={s.block} aria-labelledby="usage-users-h">
      <h2 id="usage-users-h" className={s.blockTitle}>
        {tr.keys.byUser(usage.data?.days ?? 30)}
      </h2>
      <p className={s.hint}>{tr.keys.byUserLead}</p>
      {usage.isLoading ? (
        <SkeletonRows rows={3} />
      ) : usage.data && usage.data.rows.length ? (
        <div className={s.tableScroll}>
          <table className={s.usageTable}>
            <thead>
              <tr>
                <th scope="col">{tr.keys.person}</th>
                <th scope="col">{tr.keys.keySource}</th>
                <th scope="col">{tr.keys.calls}</th>
                <th scope="col">{tr.keys.inTokens}</th>
                <th scope="col">{tr.keys.outTokens}</th>
              </tr>
            </thead>
            <tbody>
              {usage.data.rows.map((r) => (
                <tr key={`${r.user_id ?? 'system'}:${r.key_source}`}>
                  <td>{r.name ?? tr.keys.system}</td>
                  <td>{tr.keys.sources[r.key_source] ?? r.key_source}</td>
                  <td>{fmt(r.calls)}</td>
                  <td>{fmt(r.prompt_tokens)}</td>
                  <td>{fmt(r.completion_tokens)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className={s.hint}>{tr.keys.noUsage}</p>
      )}
    </section>
  );
}
