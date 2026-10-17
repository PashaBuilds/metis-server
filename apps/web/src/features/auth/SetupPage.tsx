import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Navigate, useNavigate } from '@tanstack/react-router';
import { useState, type FormEvent } from 'react';
import { Button, Field, Input } from '@/design/primitives';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, setCsrfToken } from '@/lib/api/client';
import type { Me } from '@/app/session';
import { AuthLayout } from './AuthLayout';
import s from './Auth.module.css';

export function SetupPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const status = useQuery({ queryKey: ['setup-status'], queryFn: () => api.get<{ needs_setup: boolean }>('/setup/status') });
  const [form, setForm] = useState({ code: '', display_name: '', username: '', password: '', project_name: '' });
  const [mode, setMode] = useState<'empty' | 'import'>('empty');
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  if (status.data && !status.data.needs_setup && !done) return <Navigate to="/giris" />;

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    setFields({});
    try {
      const me = await api.post<Me>('/setup', { ...form, mode });
      setCsrfToken(me.csrf_token);
      qc.setQueryData(['me'], me);
      qc.setQueryData(['setup-status'], { needs_setup: false });
      if (mode === 'empty') navigate({ to: '/' });
      else setDone(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(errorMessage(err.code));
        setFields(err.fieldErrors());
      } else setError(errorMessage('NETWORK'));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <AuthLayout title={tr.auth.importTitle}>
        <div className={s.form}>
          <p className={s.lead}>{tr.auth.importLead}</p>
          <pre className={s.codeBlock}>metis import-v1 C:\yedek\metis-yedek.metisbak --dry-run{'\n'}metis import-v1 C:\yedek\metis-yedek.metisbak</pre>
          <p className={s.lead}>{tr.auth.importAfter}</p>
          <Button variant="primary" onClick={() => navigate({ to: '/ayarlar', search: { tab: 'aktarim' } })}>
            {tr.auth.importOpen}
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title={tr.auth.setupTitle}>
      <form className={s.form} onSubmit={submit} noValidate>
        <p className={s.lead}>{tr.auth.setupLead}</p>
        {error && (
          <p className={s.error} role="alert">
            {error}
          </p>
        )}
        <Field label={tr.auth.setupCode} error={fields.code ? errorMessage('SETUP_CODE_INVALID') : null}>
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={form.code} onChange={set('code')} autoComplete="off" className="mono" placeholder="XXXX-XXXX-XXXX-XXXX" />}
        </Field>
        <Field label={tr.auth.displayName}>{({ id }) => <Input id={id} value={form.display_name} onChange={set('display_name')} autoComplete="name" />}</Field>
        <Field label={tr.auth.username} hint={tr.auth.usernameHint} error={fields.username ? tr.auth.usernameInvalid : null}>
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={form.username} onChange={set('username')} autoComplete="username" />}
        </Field>
        <Field label={tr.auth.password} hint={tr.auth.pwHint} error={fields.password ? errorMessage('WEAK_PASSWORD') : null}>
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} type="password" value={form.password} onChange={set('password')} autoComplete="new-password" />}
        </Field>
        <div className={s.choice} role="group" aria-label={tr.auth.start}>
          <button type="button" className={s.choiceBtn} aria-pressed={mode === 'empty'} onClick={() => setMode('empty')}>
            <span>{tr.auth.startEmpty}</span>
            <span>{tr.auth.startEmptyText}</span>
          </button>
          <button type="button" className={s.choiceBtn} aria-pressed={mode === 'import'} onClick={() => setMode('import')}>
            <span>{tr.auth.startImport}</span>
            <span>{tr.auth.startImportText}</span>
          </button>
        </div>
        {mode === 'empty' && (
          <Field label={tr.auth.projectName} error={fields.project_name ? tr.auth.projectNameRequired : null}>
            {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={form.project_name} onChange={set('project_name')} />}
          </Field>
        )}
        <Button type="submit" variant="primary" loading={busy}>
          {tr.auth.finish}
        </Button>
      </form>
    </AuthLayout>
  );
}
