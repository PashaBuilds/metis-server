import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Navigate, useNavigate } from '@tanstack/react-router';
import { useState, type FormEvent } from 'react';
import { Button, Field, Input } from '@/design/primitives';
import { errorMessage } from '@/i18n/tr';
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
      <AuthLayout title="Yönetici hesabın hazır">
        <div className={s.form}>
          <p className={s.lead}>v0.5.5 yedeğini sunucuda şu komutla aktar. Parola komut satırına yazılmaz; komut sorar.</p>
          <pre className={s.codeBlock}>metis import-v1 C:\yedek\metis-yedek.metisbak --dry-run{'\n'}metis import-v1 C:\yedek\metis-yedek.metisbak</pre>
          <p className={s.lead}>Önce --dry-run ile raporu incele. Aktarım tamamlanınca rapor Ayarlar › v0.5.5 aktarımı bölümünde görünür.</p>
          <Button variant="primary" onClick={() => navigate({ to: '/ayarlar', search: { tab: 'aktarim' } })}>
            Aktarım raporunu aç
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="İlk kurulum">
      <form className={s.form} onSubmit={submit} noValidate>
        <p className={s.lead}>Kurulum betiğinin ekrana bastığı tek kullanımlık kodu gir. Kod 24 saat geçerlidir.</p>
        {error && (
          <p className={s.error} role="alert">
            {error}
          </p>
        )}
        <Field label="Kurulum kodu" error={fields.code ? errorMessage('SETUP_CODE_INVALID') : null}>
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={form.code} onChange={set('code')} autoComplete="off" className="mono" placeholder="XXXX-XXXX-XXXX-XXXX" />}
        </Field>
        <Field label="Adın">{({ id }) => <Input id={id} value={form.display_name} onChange={set('display_name')} autoComplete="name" />}</Field>
        <Field label="Kullanıcı adı" hint="Harf, rakam, nokta, tire" error={fields.username ? 'Kullanıcı adını kontrol et.' : null}>
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={form.username} onChange={set('username')} autoComplete="username" />}
        </Field>
        <Field label="Parola" hint="En az 12 karakter" error={fields.password ? errorMessage('WEAK_PASSWORD') : null}>
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} type="password" value={form.password} onChange={set('password')} autoComplete="new-password" />}
        </Field>
        <div className={s.choice} role="group" aria-label="Başlangıç">
          <button type="button" className={s.choiceBtn} aria-pressed={mode === 'empty'} onClick={() => setMode('empty')}>
            <span>Boş başla</span>
            <span>İlk projeyi oluştur</span>
          </button>
          <button type="button" className={s.choiceBtn} aria-pressed={mode === 'import'} onClick={() => setMode('import')}>
            <span>v0.5.5 yedeğinden aktar</span>
            <span>Önceki bilgileri taşı</span>
          </button>
        </div>
        {mode === 'empty' && (
          <Field label="İlk proje adı" error={fields.project_name ? 'Proje adı gerekli.' : null}>
            {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={form.project_name} onChange={set('project_name')} />}
          </Field>
        )}
        <Button type="submit" variant="primary" loading={busy}>
          Kurulumu tamamla
        </Button>
      </form>
    </AuthLayout>
  );
}
