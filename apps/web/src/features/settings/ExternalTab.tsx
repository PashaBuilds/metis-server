import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Button, Checkbox, ConfirmDialog, Field, Input, Select, SkeletonRows, StatusBadge, useToast } from '@/design/primitives';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { messageOf } from '@/features/shared/hooks';
import s from './Settings.module.css';

type Conn = Schemas['ConnectionOut'];
type ConnIn = Schemas['ConnectionIn'];
type Kind = ConnIn['kind'];
type TestOut = Schemas['ConnectionTestOut'];

interface FormState {
  id: string | null;
  kind: Kind;
  name: string;
  base_url: string;
  token: string;
  scopes: string;
  enabled: boolean;
  hasToken: boolean;
}

const EMPTY: FormState = { id: null, kind: 'confluence', name: '', base_url: '', token: '', scopes: '', enabled: true, hasToken: false };

function toForm(c: Conn): FormState {
  return { id: c.id, kind: c.kind, name: c.name, base_url: c.base_url ?? '', token: '', scopes: c.allowed_scopes.join(', '), enabled: c.enabled ?? true, hasToken: !!c.secret_configured };
}

/** Dış kaynaklar (Confluence, GitLab): yalnız yönetici. Token şifreli saklanır ve hiçbir yanıtta dönmez. */
export function ExternalTab() {
  const qc = useQueryClient();
  const toast = useToast();
  const list = useQuery({ queryKey: ['external-connections'], queryFn: () => api.get<Conn[]>('/external/connections') });
  const [form, setForm] = useState<FormState | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TestOut | null>(null);
  const [removing, setRemoving] = useState<Conn | null>(null);

  const payload = (f: FormState): ConnIn => ({
    kind: f.kind,
    name: f.name.trim(),
    base_url: f.base_url.trim(),
    token: f.token,
    allowed_scopes: f.scopes
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean),
    enabled: f.enabled,
  });

  const save = useMutation({
    mutationFn: (f: FormState) => (f.id ? api.put<Conn>(`/external/connections/${f.id}`, payload(f)) : api.post<Conn>('/external/connections', payload(f))),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['external-connections'] });
      setForm(null);
      setFields({});
      setError(null);
      setResult(null);
      toast.show(tr.external.saved);
    },
    onError: (e) => {
      setFields(e instanceof ApiError ? e.fieldErrors() : {});
      setError(messageOf(e));
    },
  });
  const test = useMutation({
    mutationFn: (f: FormState) => api.post<TestOut>('/external/connections/test', { kind: f.kind, base_url: f.base_url.trim(), token: f.token, connection_id: f.id }),
    onSuccess: (r) => setResult(r),
    onError: (e) => setResult({ ok: false, error: e instanceof ApiError ? e.code : 'NETWORK' }),
  });
  const remove = useMutation({
    mutationFn: (c: Conn) => api.del(`/external/connections/${c.id}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['external-connections'] });
      toast.show(tr.external.removed);
    },
    onError: (e) => toast.show(messageOf(e), { tone: 'error' }),
  });

  if (list.isLoading) return <SkeletonRows rows={3} />;
  if (list.isError) return <p className={s.error}>{messageOf(list.error)}</p>;
  const set = (patch: Partial<FormState>) => setForm((f) => (f ? { ...f, ...patch } : f));

  return (
    <div className={s.stack}>
      <section className={s.block} aria-labelledby="ext-h">
        <div className={s.blockHead}>
          <h2 id="ext-h" className={s.blockTitle}>
            {tr.external.title}
          </h2>
          {!form && (
            <Button size="sm" onClick={() => setForm(EMPTY)}>
              {tr.external.add}
            </Button>
          )}
        </div>
        <p className={s.hint}>{tr.external.lead}</p>
        {list.data && list.data.length === 0 && !form && <p className={s.hint}>{tr.external.empty}</p>}
        <div className={s.opsRows}>
          {list.data?.map((c) => (
            <div key={c.id} className={s.opsRow}>
              <div className={s.grow}>
                <div className={s.opsName}>
                  {c.name} <StatusBadge size="sm" tone={c.enabled ? 'onay' : 'taslak'} label={c.enabled ? tr.external.enabled : tr.external.off} />
                </div>
                <div className={s.hint}>
                  {tr.external.kinds[c.kind]} · {c.base_url} · {c.allowed_scopes.join(', ')}
                </div>
              </div>
              <Button size="sm" variant="ghost" onClick={() => (setForm(toForm(c)), setResult(null), setError(null))}>
                {tr.external.edit}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setRemoving(c)}>
                {tr.external.remove}
              </Button>
            </div>
          ))}
        </div>
      </section>

      {form && (
        <section className={s.block} aria-labelledby="ext-form-h">
          <h2 id="ext-form-h" className={s.blockTitle}>
            {form.id ? tr.external.edit : tr.external.add}
          </h2>
          {error && (
            <p className={s.error} role="alert">
              {error}
            </p>
          )}
          <form
            className={s.stack}
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate(form);
            }}
          >
            <Field label={tr.external.kind}>
              {({ id }) => (
                <Select id={id} value={form.kind} onChange={(e) => set({ kind: e.target.value as Kind })}>
                  <option value="confluence">{tr.external.kinds.confluence}</option>
                  <option value="gitlab">{tr.external.kinds.gitlab}</option>
                </Select>
              )}
            </Field>
            <Field label={tr.external.name}>{({ id }) => <Input id={id} value={form.name} onChange={(e) => set({ name: e.target.value })} autoComplete="off" />}</Field>
            <Field label={tr.external.baseUrl} hint={tr.external.baseUrlHint[form.kind]} error={fields.base_url ? tr.external.baseUrlHint[form.kind] : null}>
              {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={form.base_url} onChange={(e) => set({ base_url: e.target.value })} spellCheck={false} autoComplete="off" />}
            </Field>
            <Field label={tr.external.token} hint={form.hasToken ? tr.external.tokenKept : tr.external.tokenHint[form.kind]}>
              {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} type="password" value={form.token} onChange={(e) => set({ token: e.target.value })} autoComplete="new-password" />}
            </Field>
            <Field label={tr.external.scopes[form.kind]!} hint={tr.external.scopesHint[form.kind]} error={fields.allowed_scopes ? tr.external.scopesHint[form.kind] : null}>
              {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={form.scopes} onChange={(e) => set({ scopes: e.target.value })} spellCheck={false} autoComplete="off" />}
            </Field>
            <Checkbox label={tr.external.enabled} checked={form.enabled} onChange={(v) => set({ enabled: v })} />
            <div className={s.pwRow}>
              <Button type="submit" variant="primary" loading={save.isPending}>
                {tr.external.save}
              </Button>
              <Button type="button" loading={test.isPending} disabled={!form.base_url.trim() || (!form.token && !form.hasToken)} onClick={() => (setResult(null), test.mutate(form))}>
                {tr.external.test}
              </Button>
              <Button type="button" variant="ghost" onClick={() => (setForm(null), setError(null), setFields({}), setResult(null))}>
                {tr.external.cancel}
              </Button>
            </div>
          </form>
          {result && (
            <p className={result.ok ? s.hint : s.error} role="status">
              {result.ok ? tr.external.testOk(result.user ?? '') : errorMessage(result.error ?? 'INTERNAL')}
            </p>
          )}
        </section>
      )}

      <ConfirmDialog
        open={!!removing}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={tr.external.removeTitle}
        description={tr.external.removeDesc}
        confirmLabel={tr.external.remove}
        danger
        onConfirm={() => {
          if (removing) remove.mutate(removing);
          setRemoving(null);
        }}
      />
    </div>
  );
}
