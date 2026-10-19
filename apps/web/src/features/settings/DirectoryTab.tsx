import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Button, Checkbox, Field, Input, SkeletonRows, useToast } from '@/design/primitives';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { messageOf } from '@/features/shared/hooks';
import s from './Settings.module.css';

type SettingsIn = Schemas['DirectorySettingsIn'];
type TestOut = Schemas['DirectoryTestOut'];

const EMPTY: SettingsIn = { enabled: false, server_url: '', domain: '', base_dn: '', group_dn: '', new_user_role: 'reader' };

/** Şirket hesabıyla giriş (Active Directory / LDAPS). Yalnız yönetici; parolalar saklanmaz. */
export function DirectoryTab() {
  const qc = useQueryClient();
  const toast = useToast();
  const current = useQuery({ queryKey: ['directory'], queryFn: () => api.get<Schemas['DirectorySettingsOut']>('/directory') });
  const [form, setForm] = useState<SettingsIn>(EMPTY);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [testUser, setTestUser] = useState('');
  const [testPassword, setTestPassword] = useState('');
  const [result, setResult] = useState<TestOut | null>(null);

  useEffect(() => {
    if (current.data) {
      const { enabled, server_url, domain, base_dn, group_dn, new_user_role } = current.data;
      setForm({ enabled, server_url, domain, base_dn, group_dn, new_user_role });
    }
  }, [current.data]);

  const save = useMutation({
    mutationFn: () => api.put<Schemas['DirectorySettingsOut']>('/directory', form),
    onSuccess: (d) => {
      qc.setQueryData(['directory'], d);
      void qc.invalidateQueries({ queryKey: ['auth-methods'] });
      setFields({});
      setError(null);
      toast.show(tr.directory.saved);
    },
    onError: (e) => {
      setFields(e instanceof ApiError ? e.fieldErrors() : {});
      setError(messageOf(e));
    },
  });

  const test = useMutation({
    // Parola yalnız bu istekte gider; kaydedilmez. Deneme bitince alan temizlenir.
    mutationFn: () => api.post<TestOut>('/directory/test', { settings: { ...form, enabled: true }, username: testUser, password: testPassword }),
    onSuccess: (r) => setResult(r),
    onError: (e) => setResult({ ok: false, error: e instanceof ApiError ? e.code : 'NETWORK' }),
    onSettled: () => setTestPassword(''),
  });

  if (current.isLoading) return <SkeletonRows rows={4} />;
  if (current.isError) return <p className={s.error}>{messageOf(current.error)}</p>;
  const httpsOk = current.data?.https_ok ?? false;
  const set = (patch: Partial<SettingsIn>) => setForm((f) => ({ ...f, ...patch }));

  return (
    <div className={s.stack}>
      <section className={s.block} aria-labelledby="dir-h">
        <h2 id="dir-h" className={s.blockTitle}>
          {tr.directory.title}
        </h2>
        <p className={s.hint}>{tr.directory.lead}</p>
        {!httpsOk && (
          <p className={s.error} role="note">
            {tr.directory.httpsMissing}
          </p>
        )}
        {error && (
          <p className={s.error} role="alert">
            {error}
          </p>
        )}
        <form
          className={s.stack}
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <Checkbox label={tr.directory.enabled} description={tr.directory.enabledHint} checked={form.enabled} disabled={!httpsOk && !form.enabled} onChange={(v) => set({ enabled: v })} />
          <Field label={tr.directory.serverUrl} hint={tr.directory.serverUrlHint} error={fields.server_url ? tr.directory.serverUrlHint : null}>
            {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={form.server_url} onChange={(e) => set({ server_url: e.target.value })} placeholder="ldaps://dc1.sirket.local" spellCheck={false} autoComplete="off" />}
          </Field>
          <Field label={tr.directory.domain} hint={tr.directory.domainHint} error={fields.domain ? tr.directory.domainHint : null}>
            {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={form.domain} onChange={(e) => set({ domain: e.target.value })} placeholder="sirket.com.tr" spellCheck={false} autoComplete="off" />}
          </Field>
          <Field label={tr.directory.baseDn} hint={tr.directory.baseDnHint} error={fields.base_dn ? tr.directory.baseDnHint : null}>
            {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={form.base_dn} onChange={(e) => set({ base_dn: e.target.value })} spellCheck={false} autoComplete="off" />}
          </Field>
          <Field label={tr.directory.groupDn} hint={tr.directory.groupDnHint}>
            {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={form.group_dn} onChange={(e) => set({ group_dn: e.target.value })} spellCheck={false} autoComplete="off" />}
          </Field>
          <fieldset className={s.radios}>
            <legend className={s.radioLabel}>{tr.directory.newUserRole}</legend>
            {(['reader', 'none'] as const).map((r) => (
              <label key={r} className={[s.radio, form.new_user_role === r ? s.radioOn : ''].join(' ')}>
                <input type="radio" name="dir-role" checked={form.new_user_role === r} onChange={() => set({ new_user_role: r })} />
                <span className={s.radioText}>
                  <span className={s.radioLabel}>{r === 'none' ? tr.directory.roleNone : tr.directory.roleReader}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <div>
            <Button type="submit" variant="primary" loading={save.isPending}>
              {tr.directory.save}
            </Button>
          </div>
        </form>
      </section>

      <section className={s.block} aria-labelledby="dir-test-h">
        <h2 id="dir-test-h" className={s.blockTitle}>
          {tr.directory.testTitle}
        </h2>
        <p className={s.hint}>{tr.directory.testLead}</p>
        <form
          className={s.stack}
          onSubmit={(e) => {
            e.preventDefault();
            setResult(null);
            test.mutate();
          }}
        >
          <Field label={tr.directory.testUser}>
            {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={testUser} onChange={(e) => setTestUser(e.target.value)} autoComplete="off" spellCheck={false} />}
          </Field>
          <Field label={tr.directory.testPassword}>
            {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} type="password" value={testPassword} onChange={(e) => setTestPassword(e.target.value)} autoComplete="off" />}
          </Field>
          <div>
            <Button type="submit" loading={test.isPending} disabled={!testUser.trim() || !testPassword}>
              {tr.directory.testRun}
            </Button>
          </div>
        </form>
        {result && (
          <p className={result.ok ? s.hint : s.error} role="status">
            {result.ok
              ? `${tr.directory.testOk(`${result.display_name ?? ''} (${result.username ?? ''})`)}${result.in_group === true ? ` ${tr.directory.testGroupOk}` : result.in_group === false ? ` ${tr.directory.testGroupNo}` : ''}`
              : errorMessage(result.error ?? 'INTERNAL')}
          </p>
        )}
      </section>
    </div>
  );
}
