import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { SkeletonRows, useToast } from '@/design/primitives';
import { useSession } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { messageOf, useProject } from '@/features/shared/hooks';
import s from './Settings.module.css';

type Policy = 'independent' | 'owner_review';

export function PolicyTab() {
  const session = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const project = useProject(session.projectId);
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: (p: Policy) => api.patch<Schemas['ProjectOut']>(`/projects/${session.projectId}`, { review_policy: p }),
    onSuccess: (d) => {
      qc.setQueryData(['project', session.projectId], d);
      toast.show(tr.settings.policySaved);
      setError(null);
    },
    onError: (e) => setError(messageOf(e)),
  });
  if (project.isLoading) return <SkeletonRows rows={2} />;
  if (!project.data) return <p className={s.error}>{messageOf(project.error)}</p>;
  const value = (m.isPending ? m.variables : project.data.review_policy) as Policy;
  const options: { value: Policy; label: string; text: string }[] = [
    { value: 'independent', label: tr.settings.policyIndependent, text: tr.settings.policyIndependentText },
    { value: 'owner_review', label: tr.settings.policyOwner, text: tr.settings.policyOwnerText },
  ];
  return (
    <section className={s.block} aria-labelledby="policy-h">
      <h2 id="policy-h" className={s.blockTitle}>
        {tr.settings.policy}
      </h2>
      {!session.isAdmin && <p className={s.hint}>{tr.settings.policyAdminOnly}</p>}
      {error && (
        <p className={s.error} role="alert">
          {error}
        </p>
      )}
      <div role="radiogroup" aria-labelledby="policy-h" className={s.radios}>
        {options.map((o) => (
          <label key={o.value} className={[s.radio, value === o.value ? s.radioOn : ''].join(' ')}>
            <input
              type="radio"
              name="review-policy"
              value={o.value}
              checked={value === o.value}
              disabled={!session.isAdmin || m.isPending}
              onChange={() => m.mutate(o.value)}
            />
            <span className={s.radioText}>
              <span className={s.radioLabel}>{o.label}</span>
              <span className={s.hint}>{o.text}</span>
            </span>
          </label>
        ))}
      </div>
    </section>
  );
}
