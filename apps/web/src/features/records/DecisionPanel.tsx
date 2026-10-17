import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from '@tanstack/react-router';
import { Check, ExternalLink, PencilLine, Send, Trash2, Upload, X } from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';
import { Button, Checkbox, ConfirmDialog, Field, Textarea, useToast } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { formatDateTime } from '@/lib/format';
import { messageOf, useUndoableDelete } from '@/features/shared/hooks';
import s from './RecordDetail.module.css';

type Change = Schemas['ChangeDetailOut'];
type Decision = 'approve' | 'request_changes' | 'reject';

export function DecisionPanel({ change }: { change: Change }) {
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const undoableDelete = useUndoableDelete();
  const [reason, setReason] = useState('');
  const [checked, setChecked] = useState(false);
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const blockersId = useId();

  const apply = (d: Change) => {
    qc.setQueryData(['change', change.id], d);
    qc.invalidateQueries({ queryKey: ['changes', change.project_id] });
    qc.invalidateQueries({ queryKey: ['inbox', change.project_id] });
  };
  const onError = (e: unknown) => {
    if (e instanceof ApiError && e.code === 'REASON_REQUIRED') setReasonError(tr.errors.REASON_REQUIRED!);
    else setError(messageOf(e));
    if (e instanceof ApiError && (e.code === 'HASH_MISMATCH' || e.code === 'INVALID_STATE')) qc.invalidateQueries({ queryKey: ['change', change.id] });
  };

  const review = useMutation({
    mutationFn: (decision: Decision) =>
      api.post<Change>(`/changes/${change.id}/reviews`, { decision, reason: reason.trim(), evidence_checked: checked, hash: change.hash }),
    onSuccess: (d, decision) => {
      apply(d);
      setReason('');
      setChecked(false);
      // Onay ve yayın tek adım: onaylayan yayımlayabiliyorsa hemen yayımlanır. Yayın başarısız olursa kayıt
      // onaylı kalır ve panel "Yayımla" düğmesini gösterir.
      if (decision === 'approve' && d.state === 'approved' && d.can_publish) publish.mutate();
      else toast.show(decision === 'approve' ? tr.record.approved : decision === 'reject' ? tr.record.rejected : tr.record.changesRequested);
    },
    onError,
  });
  const publish = useMutation({
    mutationFn: () => api.post<Change>(`/changes/${change.id}/publish`),
    onSuccess: (d) => {
      apply(d);
      qc.invalidateQueries({ queryKey: ['pages', change.project_id] });
      qc.invalidateQueries({ queryKey: ['domains', change.project_id] });
      for (const pid of d.page_ids) qc.invalidateQueries({ queryKey: ['page', pid] });
      toast.show(tr.record.published);
    },
    onError: (e) => {
      // Onay geçerli; yalnız yayın tamamlanamadı. Panel güncel durumu göstersin.
      qc.invalidateQueries({ queryKey: ['change', change.id] });
      onError(e);
    },
  });
  const submit = useMutation({
    mutationFn: () => api.post<Change>(`/changes/${change.id}/submit`),
    onSuccess: (d) => {
      apply(d);
      toast.show(tr.record.submitted);
    },
    onError,
  });

  const busy = review.isPending || publish.isPending || submit.isPending;
  const decide = (decision: Decision) => {
    setError(null);
    setReasonError(null);
    if (decision !== 'approve' && !reason.trim()) {
      setReasonError(tr.errors.REASON_REQUIRED!);
      return;
    }
    review.mutate(decision);
  };

  const blockers = change.approve_blockers.filter((b) => b !== 'not_in_review').map((b) => tr.record.blockers[b] ?? b);
  const approveReasons = [...blockers, ...(checked ? [] : [tr.record.checkRequired])];
  const publishedPage = change.published_page_ids[0];

  let body: ReactNode = null;
  if (change.state === 'draft') {
    body = change.can_edit ? (
      <div className={s.panelActions}>
        <Button variant="primary" icon={<Send size={16} aria-hidden />} loading={submit.isPending} disabled={busy} onClick={() => submit.mutate()}>
          {tr.record.submit}
        </Button>
        <Link to="/katki" search={{ change: change.id }} className={s.linkBtn}>
          <PencilLine size={16} aria-hidden />
          {tr.record.edit}
        </Link>
      </div>
    ) : (
      <p className={s.note}>{tr.record.draftNote}</p>
    );
  } else if (change.state === 'in_review') {
    body = change.can_review ? (
      <div className={s.decision}>
        <Field label={tr.record.reason} hint={tr.record.reasonHint} error={reasonError}>
          {({ id, describedBy }) => (
            <Textarea
              id={id}
              aria-describedby={describedBy}
              invalid={!!reasonError}
              rows={4}
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
                setReasonError(null);
              }}
            />
          )}
        </Field>
        <Checkbox label={tr.record.checked} checked={checked} onChange={setChecked} />
        {change.review_policy === 'owner_review' && change.self_review && <span className={s.ownerBadge}>{tr.shared.ownerReview}</span>}
        <div className={s.decisionButtons}>
          <Button
            variant="primary"
            icon={<Check size={16} aria-hidden />}
            disabled={approveReasons.length > 0 || busy}
            loading={(review.isPending && review.variables === 'approve') || publish.isPending}
            aria-describedby={approveReasons.length ? blockersId : undefined}
            onClick={() => decide('approve')}
          >
            {tr.record.approvePublish}
          </Button>
          {approveReasons.length > 0 && (
            <ul id={blockersId} className={s.blockers}>
              {approveReasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
          <Button icon={<PencilLine size={16} aria-hidden />} disabled={busy} loading={review.isPending && review.variables === 'request_changes'} onClick={() => decide('request_changes')}>
            {tr.record.requestChanges}
          </Button>
          <Button variant="danger" icon={<X size={16} aria-hidden />} disabled={busy} loading={review.isPending && review.variables === 'reject'} onClick={() => decide('reject')}>
            {tr.record.reject}
          </Button>
        </div>
      </div>
    ) : (
      <p className={s.note}>{change.self_review ? tr.record.waitingReview : tr.record.noRights}</p>
    );
  } else if (change.state === 'approved') {
    body = change.can_publish ? (
      <div className={s.decision}>
        <p className={s.note}>{tr.record.publishHint}</p>
        <Button variant="primary" icon={<Upload size={16} aria-hidden />} loading={publish.isPending} disabled={busy} onClick={() => publish.mutate()}>
          {tr.record.publish}
        </Button>
      </div>
    ) : (
      <p className={s.note}>{tr.record.approvedWaitPublish}</p>
    );
  } else if (change.state === 'published') {
    body = (
      <div className={s.decision}>
        <p className={s.note}>{tr.record.publishedNote(formatDateTime(change.published_at))}</p>
        {publishedPage && (
          <Link to="/bilgi/$pageId" params={{ pageId: publishedPage }} search={{}} className={s.linkBtnPrimary}>
            <ExternalLink size={16} aria-hidden />
            {tr.record.openPublished}
          </Link>
        )}
      </div>
    );
  } else if (change.state === 'rejected') {
    body = <p className={s.note}>{tr.record.rejectedNote}</p>;
  } else if (change.state === 'superseded') {
    body = (
      <div className={s.decision}>
        <p className={s.note}>{tr.record.supersededNote}</p>
        {change.successor_id && (
          <Link to="/kayitlar/$changeId" params={{ changeId: change.successor_id }}>
            {tr.record.openSuccessor}
          </Link>
        )}
      </div>
    );
  }

  return (
    <aside className={s.panel} aria-labelledby="decision-h">
      <h2 id="decision-h" className={s.panelTitle}>
        {tr.record.decision}
      </h2>
      {error && (
        <p className={s.panelError} role="alert">
          {error}
        </p>
      )}
      {body}
      {change.can_delete && (
        <div className={s.panelFoot}>
          <Button variant="ghost" size="sm" icon={<Trash2 size={15} aria-hidden />} onClick={() => setConfirmDelete(true)} disabled={busy}>
            {tr.record.deleteRecord}
          </Button>
        </div>
      )}
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={tr.record.deleteTitle}
        description={tr.record.deleteDesc}
        confirmLabel={tr.common.delete}
        danger
        onConfirm={async () => {
          await undoableDelete({
            del: () => api.del(`/changes/${change.id}`),
            restore: () => api.post(`/changes/${change.id}/restore`),
            onDone: () => {
              qc.invalidateQueries({ queryKey: ['changes', change.project_id] });
              qc.invalidateQueries({ queryKey: ['pages', change.project_id] });
              navigate({ to: '/kayitlar' });
            },
            onRestored: () => {
              qc.invalidateQueries({ queryKey: ['changes', change.project_id] });
              qc.invalidateQueries({ queryKey: ['change', change.id] });
              navigate({ to: '/kayitlar/$changeId', params: { changeId: change.id } });
            },
          }).catch(() => undefined);
        }}
      />
    </aside>
  );
}
