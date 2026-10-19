import { Plus, Send, Upload, X } from 'lucide-react';
import { useState } from 'react';
import { Button, Field, IconButton, Input, Select, TabPanel, Tabs, Textarea, useToast } from '@/design/primitives';
import { ScopeField } from '@/app/ScopeBar';
import { useSession, type ScopeSel } from '@/app/session';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, newIdempotencyKey, type Schemas } from '@/lib/api/client';
import { Banner } from '@/features/shared/Banner';
import type { AttachmentData } from '@/features/shared/Attachments';
import { useProject } from '@/features/shared/hooks';
import { Markdown } from '@/features/shared/Markdown';
import { usePublishFlow } from '@/features/shared/PublishCheck';
import { PAGE_KINDS } from '@/features/shared/kinds';
import { AttachmentsField } from './AttachmentsField';
import s from './Contribute.module.css';

export interface NoteValues {
  title: string;
  kind: string;
  summary: string;
  /** Not: bilginin dayanağı. Sunucu her paragrafı kendiliğinden bir iddia yapar. */
  body_md: string;
  scope: ScopeSel;
  unknowns: string[];
  aliases: string[];
  attachments: AttachmentData[];
}

export interface NoteTarget {
  pageId: string | null;
  baseRevisionId: string | null;
  changeId: string | null;
  changeHash: string | null;
  changeSummary: string;
}

interface Props {
  initial: NoteValues;
  target: NoteTarget;
  onDirty: (dirty: boolean) => void;
  onSaved: (changeId: string) => void;
  /** Yazar yayımlar: yayın tamamlandı. */
  onPublished: (change: Schemas['ChangeDetailOut']) => void;
  /** Yayın öncesi uyarıdan "Taslağa dön": kaydedilmiş taslak editörde yeniden açılır. */
  onReopen: (changeId: string) => void;
}

/** Tek adımlı taslak: başlık, kapsam, not ve ekler; kaydet ya da yayımla. Ayrı bir kaynak adımı yok. */
export function NoteEditor({ initial, target, onDirty, onSaved, onPublished, onReopen }: Props) {
  const session = useSession();
  const toast = useToast();
  const [v, setV] = useState<NoteValues>(initial);
  const [bodyTab, setBodyTab] = useState('write');
  const [idemKey] = useState(newIdempotencyKey);
  const [busy, setBusy] = useState<'save' | 'submit' | 'publish' | null>(null);
  const project = useProject(session.projectId);
  const selfPublish = project.data?.review_policy === 'self_publish';
  const flow = usePublishFlow(onPublished);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  // Taslak sayfası ilk kayıtta oluşur; sonraki kayıtlar aynı sayfayı günceller.
  const [pageId, setPageId] = useState(target.pageId);
  const noteEmpty = !v.body_md.trim();

  const update = (patch: Partial<NoteValues>) => {
    setV((old) => ({ ...old, ...patch }));
    onDirty(true);
  };

  async function save(mode: 'save' | 'submit' | 'publish') {
    if (busy) return;
    const errs: Record<string, string> = {};
    if (!v.title.trim()) errs.title = tr.contribute.titleRequired;
    if (mode !== 'save' && noteEmpty) errs.body = tr.contribute.noteEmpty;
    setErrors(errs);
    setFormError(null);
    if (Object.keys(errs).length) return;
    setBusy(mode);
    const item = {
      note: true,
      page_id: pageId,
      base_revision_id: target.baseRevisionId,
      title: v.title.trim(),
      summary: v.summary.trim(),
      body_md: v.body_md,
      kind: v.kind,
      scope: v.scope,
      unknowns: v.unknowns.map((u) => u.trim()).filter(Boolean),
      aliases: v.aliases,
      attachments: v.attachments.map((a) => a.id),
    };
    try {
      let id: string;
      const submit = mode === 'submit';
      if (target.changeId) {
        await api.put<Schemas['ChangeDetailOut']>(`/changes/${target.changeId}`, { expected_hash: target.changeHash, items: [item], summary: target.changeSummary });
        if (submit) await api.post(`/changes/${target.changeId}/submit`);
        id = target.changeId;
      } else {
        const res = await api.post<Schemas['ChangeDetailOut']>(`/projects/${session.projectId}/changes`, { items: [item], submit }, { idempotencyKey: idemKey });
        id = res.id;
        setPageId(res.items[0]?.page_id ?? pageId);
      }
      onDirty(false);
      if (mode === 'publish') {
        // Taslak kaydedildi; yayın öncesi kontrol sorun bulursa pencere açılır, aksi hâlde doğrudan yayımlanır.
        const outcome = await flow.start(id);
        if (outcome === 'failed') onSaved(id);
        return;
      }
      toast.show(submit ? tr.contribute.submitted : tr.contribute.saved);
      onSaved(id);
    } catch (e) {
      if (e instanceof ApiError) {
        const fe = e.fieldErrors();
        if (Object.keys(fe).some((k) => k.endsWith('title'))) setErrors({ title: tr.contribute.titleRequired });
        else if (e.code === 'REVISION_CONFLICT' && !target.changeId) setFormError(tr.contribute.baseChanged);
        else setFormError(errorMessage(e.code));
      } else setFormError(errorMessage('NETWORK'));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={s.noteEditor}>
      {formError && <Banner tone="celiski">{formError}</Banner>}
      <Field label={tr.contribute.pTitle} error={errors.title ?? null}>
        {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} invalid={!!errors.title} value={v.title} onChange={(e) => update({ title: e.target.value })} />}
      </Field>

      <section aria-labelledby="pscope-h" className={s.unknownsBox}>
        <h3 id="pscope-h" className={s.subTitle}>
          {tr.contribute.pScope}
        </h3>
        <p className={s.hint}>{tr.contribute.pScopeHint}</p>
        <ScopeField value={v.scope} onChange={(sc) => update({ scope: sc })} allowIndependent />
      </section>

      <div className={s.bodyField}>
        <span className={s.label} id="body-label">
          {tr.contribute.pBody}
        </span>
        <Tabs
          label={tr.contribute.bodyMode}
          value={bodyTab}
          onValueChange={setBodyTab}
          tabs={[
            { value: 'write', label: tr.contribute.write },
            { value: 'preview', label: tr.contribute.preview },
          ]}
        >
          <TabPanel value="write">
            <Textarea
              aria-labelledby="body-label"
              aria-describedby={['body-hint', errors.body ? 'body-err' : ''].filter(Boolean).join(' ')}
              aria-invalid={!!errors.body || undefined}
              rows={14}
              value={v.body_md}
              onChange={(e) => update({ body_md: e.target.value })}
            />
            <p id="body-hint" className={s.hint}>
              {tr.contribute.pBodyHint}
            </p>
            {errors.body && (
              <p id="body-err" className={s.error} role="alert">
                {errors.body}
              </p>
            )}
          </TabPanel>
          <TabPanel value="preview">
            <div className={s.preview}>{v.body_md.trim() ? <Markdown>{v.body_md}</Markdown> : <p className={s.muted}>{tr.contribute.previewEmpty}</p>}</div>
          </TabPanel>
        </Tabs>
      </div>

      {session.projectId && <AttachmentsField projectId={session.projectId} value={v.attachments} onChange={(attachments) => update({ attachments })} />}

      <details className={s.moreFields}>
        <summary>{tr.contribute.moreFields}</summary>
        <div className={s.moreBody}>
          <Field label={tr.contribute.pSummary} hint={tr.contribute.pSummaryHint}>
            {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} rows={2} className={s.shortArea} value={v.summary} onChange={(e) => update({ summary: e.target.value })} />}
          </Field>
          <Field label={tr.contribute.pKind}>
            {({ id }) => (
              <Select id={id} value={v.kind} onChange={(e) => update({ kind: e.target.value })}>
                {PAGE_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {tr.pageKinds[k]}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <section aria-labelledby="unknowns-h" className={s.unknownsBox}>
            <h3 id="unknowns-h" className={s.subTitle}>
              {tr.contribute.unknowns}
            </h3>
            <p className={s.hint}>{tr.contribute.unknownsHint}</p>
            {v.unknowns.map((u, i) => (
              <div key={i} className={s.unknownRow}>
                <Input aria-label={tr.contribute.unknownN(i + 1)} value={u} onChange={(e) => update({ unknowns: v.unknowns.map((x, k) => (k === i ? e.target.value : x)) })} />
                <IconButton label={tr.contribute.unknownRemove(i + 1)} onClick={() => update({ unknowns: v.unknowns.filter((_, k) => k !== i) })}>
                  <X size={16} aria-hidden />
                </IconButton>
              </div>
            ))}
            <div>
              <Button size="sm" icon={<Plus size={15} aria-hidden />} onClick={() => update({ unknowns: [...v.unknowns, ''] })}>
                {tr.contribute.unknownAdd}
              </Button>
            </div>
          </section>
        </div>
      </details>

      <div className={s.saveBar}>
        {selfPublish ? (
          <Button variant="primary" icon={<Upload size={16} aria-hidden />} loading={busy === 'publish'} disabled={!!busy || !project.data} onClick={() => save('publish')}>
            {tr.publishCheck.publish}
          </Button>
        ) : (
          <Button variant="primary" icon={<Send size={16} aria-hidden />} loading={busy === 'submit'} disabled={!!busy || !project.data} onClick={() => save('submit')}>
            {tr.contribute.saveSubmit}
          </Button>
        )}
        <Button loading={busy === 'save'} disabled={!!busy} onClick={() => save('save')}>
          {tr.contribute.save}
        </Button>
        {selfPublish && <p className={s.saveHint}>{tr.publishCheck.hint}</p>}
      </div>
      {flow.dialog(onReopen)}
    </div>
  );
}
