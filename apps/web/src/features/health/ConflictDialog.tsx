import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { Archive, ShieldCheck } from 'lucide-react';
import { useEffect, useId, useState } from 'react';
import { Button, Checkbox, Dialog, Field, SkeletonRows, Textarea } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { Banner } from '@/features/shared/Banner';
import { messageOf } from '@/features/shared/hooks';
import s from './Health.module.css';

type Case = Schemas['CaseOut'];

interface Ev {
  evidence_id: string;
  quote: string;
  page_title: string;
}
const asEv = (x: Record<string, unknown>): Ev => ({ evidence_id: String(x.evidence_id ?? ''), quote: String(x.quote ?? ''), page_title: String(x.page_title ?? '') });

const MIN_REASON = 16;

/** "Çelişkiden çözüme": deterministik seçenekler, iki tarafın kanıtı, gerekçe + onay → incelemeye giden kayıt. */
export function ConflictDialog({ findingId, open, onOpenChange }: { findingId: string | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const groupId = useId();
  const [option, setOption] = useState('');
  const [reason, setReason] = useState('');
  const [ack, setAck] = useState(false);
  const [errors, setErrors] = useState<{ option?: string; reason?: string; ack?: string; form?: string }>({});

  const caseQ = useMutation({ mutationFn: (id: string) => api.post<Case>(`/findings/${id}/case`) });
  const choose = useMutation({
    mutationFn: (c: Case) => api.post<Case>(`/conflict-cases/${c.id}/choose`, { option_id: option, reason: reason.trim(), acknowledge_whole_pages: ack }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['findings'] });
      void qc.invalidateQueries({ queryKey: ['inbox'] });
    },
    onError: (e) => setErrors({ form: messageOf(e) }),
  });

  const { mutate: openCase, reset: resetCase } = caseQ;
  const { reset: resetChoose } = choose;
  useEffect(() => {
    if (open && findingId) {
      setOption('');
      setReason('');
      setAck(false);
      setErrors({});
      resetChoose();
      openCase(findingId);
    }
    if (!open) resetCase();
  }, [open, findingId, openCase, resetCase, resetChoose]);

  const c = choose.data ?? caseQ.data;
  const doneId = choose.data?.resolution_change_id ?? null;
  const alreadyId = !choose.data ? (caseQ.data?.resolution_change_id ?? null) : null;

  function submit() {
    if (!c) return;
    const next: typeof errors = {};
    if (!option) next.option = tr.conflict.optionRequired;
    if (reason.trim().length < MIN_REASON) next.reason = tr.health.reasonShort(MIN_REASON);
    if (!ack) next.ack = tr.conflict.acknowledgeRequired;
    setErrors(next);
    if (Object.keys(next).length) return;
    choose.mutate(c);
  }

  const finished = !!doneId || !!alreadyId;
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={tr.conflict.title}
      width={760}
      footer={
        finished ? (
          <Button onClick={() => onOpenChange(false)}>{tr.common.close}</Button>
        ) : (
          <>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              {tr.common.cancel}
            </Button>
            <Button variant="primary" onClick={submit} loading={choose.isPending} disabled={!c}>
              {tr.conflict.submit}
            </Button>
          </>
        )
      }
    >
      {caseQ.isPending && (
        <div role="status" aria-label={tr.conflict.loading}>
          <SkeletonRows rows={4} />
        </div>
      )}
      {caseQ.isError && <Banner tone="celiski">{messageOf(caseQ.error)}</Banner>}
      {finished && (
        <Banner tone={doneId ? 'bilgi' : 'dikkat'} actions={
          <Link to="/kayitlar/$changeId" params={{ changeId: (doneId ?? alreadyId)! }} className={s.primaryLink}>
            {tr.conflict.openRecord}
          </Link>
        }>
          {doneId ? tr.conflict.done : tr.conflict.already}
        </Banner>
      )}
      {c && !finished && (
        <div className={s.case}>
          <section className={s.caseBlock}>
            <h3 className={s.caseTitle}>{tr.conflict.summary}</h3>
            <p>{c.summary}</p>
          </section>
          {c.questions.length > 0 && (
            <section className={s.caseBlock}>
              <h3 className={s.caseTitle}>{tr.conflict.questions}</h3>
              <ul className={s.caseList}>
                {c.questions.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
            </section>
          )}
          <fieldset className={s.options} aria-describedby={errors.option ? `${groupId}-err` : undefined}>
            <legend className={s.caseTitle}>{tr.conflict.options}</legend>
            {c.options.map((o) => (
              <label key={o.id} className={[s.option, option === o.id ? s.optionOn : ''].join(' ')}>
                <input type="radio" name={`${groupId}-opt`} value={o.id} checked={option === o.id} onChange={() => setOption(o.id)} />
                <span className={s.optionBody}>
                  <span className={s.optionTitle}>{o.title}</span>
                  <span className={s.optionText}>{o.rationale}</span>
                  <span className={s.optionPages}>
                    {o.keep.map((p) => (
                      <span key={p.page_id} className={s.keep}>
                        <ShieldCheck size={14} aria-hidden />
                        {tr.conflict.keep}: {p.title}
                      </span>
                    ))}
                    {o.retire.map((p) => (
                      <span key={p.page_id} className={s.retire}>
                        <Archive size={14} aria-hidden />
                        {tr.conflict.retire}: {p.title}
                      </span>
                    ))}
                  </span>
                  {o.prerequisite && (
                    <span className={s.optionText}>
                      <strong>{tr.conflict.prerequisite}:</strong> {o.prerequisite}
                    </span>
                  )}
                  <span className={s.optionEvidence}>
                    {o.evidence.map(asEv).map((e, i) => (
                      <span key={e.evidence_id + i} className={s.evRow}>
                        <span className={s.evPage}>{e.page_title}</span>
                        <mark className={s.evQuote}>{e.quote}</mark>
                      </span>
                    ))}
                  </span>
                </span>
              </label>
            ))}
            {errors.option && (
              <p id={`${groupId}-err`} className={s.error} role="alert">
                {errors.option}
              </p>
            )}
          </fieldset>
          <Field label={tr.conflict.reason} hint={tr.conflict.reasonHint} error={errors.reason}>
            {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} value={reason} onChange={(e) => setReason(e.target.value)} rows={3} maxLength={2000} invalid={!!errors.reason} />}
          </Field>
          <div>
            <Checkbox label={tr.conflict.acknowledge} checked={ack} onChange={setAck} />
            {errors.ack && (
              <p className={s.error} role="alert">
                {errors.ack}
              </p>
            )}
          </div>
          {errors.form && <Banner tone="celiski">{errors.form}</Banner>}
        </div>
      )}
    </Dialog>
  );
}
