import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Navigate, useNavigate } from '@tanstack/react-router';
import { useState, type FormEvent } from 'react';
import { Button, Field, Input } from '@/design/primitives';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, setCsrfToken } from '@/lib/api/client';
import { useSession, type Me } from '@/app/session';
import { AuthLayout } from './AuthLayout';
import s from './Auth.module.css';

export function LoginPage() {
  const session = useSession();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [askPassword, setAskPassword] = useState(false);
  const methods = useQuery({ queryKey: ['auth-methods'], queryFn: () => api.get<{ directory: boolean; passwordless: boolean }>('/auth/methods'), staleTime: 60_000 });
  const directory = methods.data?.directory ?? false;
  // Parolasız giriş (ekip içi): yalnız kullanıcı adı; yönetici hesabıysa sunucu PASSWORD_REQUIRED der, parola alanı açılır.
  const passwordless = (methods.data?.passwordless ?? false) && !askPassword;

  if (session.me) return <Navigate to="/" />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const me = await api.post<Me>('/auth/login', { username, password: passwordless ? '' : password });
      setCsrfToken(me.csrf_token);
      qc.setQueryData(['me'], me);
      navigate({ to: me.user.must_change_password ? '/parola' : '/' });
    } catch (err) {
      const code = err instanceof ApiError ? err.code : 'NETWORK';
      if (code === 'PASSWORD_REQUIRED') {
        setAskPassword(true);
        setError(tr.auth.passwordlessAdmin);
      } else setError(errorMessage(code));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout title={tr.auth.loginTitle}>
      <form className={s.form} onSubmit={submit} noValidate>
        {passwordless ? <p className={s.lead}>{tr.auth.passwordlessHint}</p> : directory && <p className={s.lead}>{tr.auth.directoryHint}</p>}
        {error && (
          <p className={s.error} role="alert">
            {error}
          </p>
        )}
        <Field label={tr.auth.username}>
          {({ id }) => <Input id={id} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />}
        </Field>
        {!passwordless && (
          <Field label={tr.auth.password}>
            {({ id }) => <Input id={id} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required autoFocus={askPassword} />}
          </Field>
        )}
        <Button type="submit" variant="primary" loading={busy} disabled={!username || (!passwordless && !password)}>
          {tr.auth.login}
        </Button>
        {passwordless ? (
          <button type="button" className={s.linkButton} onClick={() => setAskPassword(true)}>
            {tr.auth.withPassword}
          </button>
        ) : (
          <p className={s.lead}>{directory ? tr.auth.directoryForgot : tr.auth.forgot}</p>
        )}
      </form>
    </AuthLayout>
  );
}
