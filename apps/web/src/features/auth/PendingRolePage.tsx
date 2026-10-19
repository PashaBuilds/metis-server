import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { Button } from '@/design/primitives';
import { useSession } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api } from '@/lib/api/client';
import { AuthLayout } from './AuthLayout';
import s from './Auth.module.css';

/** Şirket hesabıyla ilk kez giren, henüz hiçbir projede rolü olmayan kullanıcı. */
export function PendingRolePage() {
  const session = useSession();
  const qc = useQueryClient();
  const navigate = useNavigate();
  return (
    <AuthLayout title={tr.auth.pendingTitle}>
      <div className={s.form}>
        <p className={s.lead}>
          <strong>{session.me?.user.display_name}</strong>
        </p>
        <p className={s.lead}>{tr.auth.pendingText}</p>
        <Button variant="primary" onClick={() => void session.refresh()}>
          {tr.auth.pendingRefresh}
        </Button>
        <Button
          variant="ghost"
          onClick={async () => {
            await api.post('/auth/logout').catch(() => undefined);
            qc.setQueryData(['me'], null);
            qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' });
            navigate({ to: '/giris' });
          }}
        >
          {tr.nav.logout}
        </Button>
      </div>
    </AuthLayout>
  );
}
