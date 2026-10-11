import { useQueryClient } from '@tanstack/react-query';
import { Navigate } from '@tanstack/react-router';
import { useState, type FormEvent } from 'react';
import { Button, Field, Input } from '@/design/primitives';
import { errorMessage } from '@/i18n/tr';
import { api, ApiError, setCsrfToken } from '@/lib/api/client';
import { useSession, type Me } from '@/app/session';
import { AuthLayout } from './AuthLayout';
import s from './Auth.module.css';

export function PasswordPage() {
  const session = useSession();
  const qc = useQueryClient();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!session.loading && !session.me) return <Navigate to="/giris" />;
  // Oturum güncellenince (React Query bildirimi asenkron) ana sayfaya geç; hemen navigate etmek eski durumu görüp geri döner.
  if (session.me && !session.me.user.must_change_password) return <Navigate to="/" />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (next !== again) {
      setError('Yeni parolalar eşleşmiyor.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const me = await api.post<Me>('/auth/password', { current_password: current, new_password: next });
      setCsrfToken(me.csrf_token);
      qc.setQueryData(['me'], me);
    } catch (err) {
      setError(errorMessage(err instanceof ApiError ? err.code : 'NETWORK'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout title="Parolanı değiştir">
      <form className={s.form} onSubmit={submit} noValidate>
        <p className={s.lead}>Yöneticinin verdiği geçici parolayı kendi parolanla değiştir.</p>
        {error && (
          <p className={s.error} role="alert">
            {error}
          </p>
        )}
        <Field label="Geçici parola">{({ id }) => <Input id={id} type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" />}</Field>
        <Field label="Yeni parola" hint="En az 12 karakter">
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />}
        </Field>
        <Field label="Yeni parola (tekrar)">{({ id }) => <Input id={id} type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" />}</Field>
        <Button type="submit" variant="primary" loading={busy} disabled={!current || !next}>
          Parolayı değiştir
        </Button>
      </form>
    </AuthLayout>
  );
}
