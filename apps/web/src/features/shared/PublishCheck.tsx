import { useQueryClient } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { AlertTriangle, ExternalLink, Upload } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Button, Dialog, useToast } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { messageOf } from './hooks';
import s from './PublishCheck.module.css';

type Change = Schemas['ChangeDetailOut'];
type Check = Schemas['PrepublishCheckOut'];
export type PublishOutcome = 'published' | 'warned' | 'failed';

/**
 * "Yazar yayımlar": yayından hemen önce Metis taslağı yayındaki bilgilerle karşılaştırır (kural + yapay zekâ).
 * Sorun yoksa doğrudan yayımlar; olası çelişki/tekrar varsa pencere açılır, kullanıcı karar verir.
 */
export function usePublishFlow(onPublished: (change: Change) => void) {
  const qc = useQueryClient();
  const toast = useToast();
  const [pending, setPending] = useState<{ changeId: string; check: Check } | null>(null);
  const [busy, setBusy] = useState<'check' | 'publish' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = (d: Change) => {
    qc.setQueryData(['change', d.id], d);
    qc.invalidateQueries({ queryKey: ['changes', d.project_id] });
    qc.invalidateQueries({ queryKey: ['inbox', d.project_id] });
    qc.invalidateQueries({ queryKey: ['pages', d.project_id] });
    qc.invalidateQueries({ queryKey: ['domains', d.project_id] });
    qc.invalidateQueries({ queryKey: ['findings', d.project_id] });
    for (const pid of d.page_ids) qc.invalidateQueries({ queryKey: ['page', pid] });
  };

  async function publish(changeId: string, check: Check, acknowledge: boolean): Promise<PublishOutcome> {
    setBusy('publish');
    setError(null);
    try {
      const d = await api.post<Change>(`/changes/${changeId}/publish-direct`, { hash: check.hash, acknowledge_issues: acknowledge });
      refresh(d);
      setPending(null);
      toast.show(check.model_status === 'ok' ? tr.publishCheck.published : tr.publishCheck.publishedRuleOnly);
      onPublished(d);
      return 'published';
    } catch (e) {
      qc.invalidateQueries({ queryKey: ['change', changeId] });
      if (pending) setError(messageOf(e));
      else toast.show(messageOf(e), { tone: 'error' });
      return 'failed';
    } finally {
      setBusy(null);
    }
  }

  async function start(changeId: string): Promise<PublishOutcome> {
    setBusy('check');
    setError(null);
    let check: Check;
    try {
      check = await api.post<Check>(`/changes/${changeId}/check`);
    } catch (e) {
      setBusy(null);
      qc.invalidateQueries({ queryKey: ['change', changeId] });
      toast.show(messageOf(e), { tone: 'error' });
      return 'failed';
    }
    if (check.issues.length === 0) return publish(changeId, check, false);
    setBusy(null);
    setPending({ changeId, check });
    return 'warned';
  }

  const dialog = (onBack?: (changeId: string) => void): ReactNode => (
    <PublishCheckDialog
      check={pending?.check ?? null}
      error={error}
      busy={busy === 'publish'}
      onBack={() => {
        const id = pending?.changeId;
        setPending(null);
        setError(null);
        if (id) onBack?.(id);
      }}
      onPublish={() => pending && void publish(pending.changeId, pending.check, true)}
    />
  );
  return { start, busy, dialog };
}

const KIND_ORDER = { conflict: 0, duplicate: 1, overlap: 2 } as const;

function PublishCheckDialog({ check, error, busy, onBack, onPublish }: { check: Check | null; error: string | null; busy: boolean; onBack: () => void; onPublish: () => void }) {
  const issues = [...(check?.issues ?? [])].sort((a, b) => KIND_ORDER[a.kind] - KIND_ORDER[b.kind]);
  const modelNote =
    check?.model_status === 'ok' ? tr.publishCheck.modelOk(check.model_name ?? '') : check?.model_status === 'failed' ? tr.publishCheck.modelFailed : tr.publishCheck.modelMissing;
  return (
    <Dialog
      open={!!check}
      onOpenChange={(o) => !o && onBack()}
      title={tr.publishCheck.title}
      description={tr.publishCheck.lead(issues.length)}
      width={720}
      footer={
        <>
          <Button variant="ghost" onClick={onBack} disabled={busy}>
            {tr.publishCheck.back}
          </Button>
          <Button variant="primary" icon={<Upload size={16} aria-hidden />} loading={busy} onClick={onPublish}>
            {tr.publishCheck.publishAnyway}
          </Button>
        </>
      }
    >
      <ul className={s.issues}>
        {issues.map((i, n) => (
          <li key={`${i.page_id}-${i.kind}-${n}`} className={[s.issue, i.kind === 'conflict' ? s.conflict : ''].join(' ')}>
            <div className={s.issueHead}>
              <span className={s.kind}>
                <AlertTriangle size={15} aria-hidden />
                {tr.publishCheck.kinds[i.kind]}
              </span>
              <Link to="/bilgi/$pageId" params={{ pageId: i.page_id }} search={{}} target="_blank" className={s.pageLink}>
                {i.page_title}
                <ExternalLink size={14} aria-hidden />
                <span className="sr-only">{tr.publishCheck.newTab}</span>
              </Link>
            </div>
            {(i.ours || i.theirs) && (
              <div className={s.sides}>
                <div>
                  <span className={s.sideLabel}>{tr.publishCheck.ours}</span>
                  <p className={s.quote}>{i.ours}</p>
                </div>
                <div>
                  <span className={s.sideLabel}>{tr.publishCheck.theirs}</span>
                  <p className={s.quote}>{i.theirs}</p>
                </div>
              </div>
            )}
            {i.reason && <p className={s.reason}>{i.reason}</p>}
          </li>
        ))}
      </ul>
      <p className={s.note}>{modelNote}</p>
      {issues.some((i) => i.kind === 'conflict') && <p className={s.note}>{tr.publishCheck.ackNote}</p>}
      {error && (
        <p className={s.error} role="alert">
          {error}
        </p>
      )}
    </Dialog>
  );
}
