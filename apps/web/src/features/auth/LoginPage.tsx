import { useQueryClient } from '@tanstack/react-query';
import { Navigate, useNavigate } from '@tanstack/react-router';
import { useState, type FormEvent } from 'react';
import { Button, Field, Input } from '@/design/primitives';
import { errorMessage } from '@/i18n/tr';
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

  if (session.me) return <Navigate to="/" />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const me = await api.post<Me>('/auth/login', { username, password });
      setCsrfToken(me.csrf_token);
      qc.setQueryData(['me'], me);
      navigate({ to: me.user.must_change_password ? '/parola' : '/' });
    } catch (err) {
      setError(errorMessage(err instanceof ApiError ? err.code : 'NETWORK'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout title="Giriş yap">
      <form className={s.form} onSubmit={submit} noValidate>
        {error && (
          <p className={s.error} role="alert">
            {error}
          </p>
        )}
        <Field label="Kullanıcı adı">
          {({ id }) => <Input id={id} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />}
        </Field>
        <Field label="Parola">
          {({ id }) => <Input id={id} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />}
        </Field>
        <Button type="submit" variant="primary" loading={busy} disabled={!username || !password}>
          Giriş yap
        </Button>
        <p className={s.lead}>Parolanı unuttuysan yöneticinden geçici parola iste.</p>
      </form>
    </AuthLayout>
  );
}
