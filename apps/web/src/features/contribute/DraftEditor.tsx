import { AlertTriangle, Plus, Send, Trash2, X } from 'lucide-react';
import { useState } from 'react';
import { Button, Field, IconButton, Input, Select, TabPanel, Tabs, Textarea, useToast } from '@/design/primitives';
import { ScopeField } from '@/app/ScopeBar';
import { useSession, type ScopeSel } from '@/app/session';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, newIdempotencyKey, type Schemas } from '@/lib/api/client';
import { Banner } from '@/features/shared/Banner';
import { CLAIM_KINDS, PAGE_KINDS } from '@/features/shared/kinds';
import { Markdown } from '@/features/shared/Markdown';
import { ExtractionNote } from './SourceStep';
import { SourceViewer, toCodePoints } from './SourceViewer';
import { isVerbatim, type DraftClaim, type SourceDetail } from './types';
import s from './Contribute.module.css';

export interface DraftValues {
  title: string;
  kind: string;
  summary: string;
  body_md: string;
  scope: ScopeSel;
  unknowns: string[];
  aliases: string[];
  claims: DraftClaim[];
}

export interface DraftTarget {
  pageId: string | null;
  baseRevisionId: string | null;
  changeId: string | null;
  changeHash: string | null;
  changeSummary: string;
  /** "Bu cevaptan bilgi taslağı öner": taslağın dayandığı mentor cevabı (kanıt değildir). */
  sourceAnswerId?: string | null;
}

interface Props {
  initial: DraftValues;
  target: DraftTarget;
  source: SourceDetail | null;
  onPickSource: () => void;
  onDirty: (dirty: boolean) => void;
  onSaved: (changeId: string) => void;
}

let keySeq = 0;
export const claimKey = () => `c${++keySeq}`;

export function DraftEditor({ initial, target, source, onPickSource, onDirty, onSaved }: Props) {
  const session = useSession();
  const toast = useToast();
  const [v, setV] = useState<DraftValues>(initial);
  const [bodyTab, setBodyTab] = useState('write');
  const [idemKey] = useState(newIdempotencyKey);
  const [busy, setBusy] = useState<'save' | 'submit' | null>(null);
  const [linking, setLinking] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const update = (patch: Partial<DraftValues>) => {
    setV((old) => ({ ...old, ...patch }));
    onDirty(true);
  };
  const updateClaim = (key: string, patch: Partial<DraftClaim>) => update({ claims: v.claims.map((c) => (c.key === key ? { ...c, ...patch } : c)) });

  const text = source?.text ?? '';
  const revisionId = source?.current_revision?.id ?? null;
  const linked = text
    ? v.claims.flatMap((c) => c.evidence.map((e) => text.indexOf(e.quote)).map((start, i) => ({ start, end: start + (c.evidence[i]?.quote.length ?? 0) }))).filter((r) => r.start >= 0)
    : [];

  async function link(start: number, end: number) {
    if (!revisionId || linking) return;
    setLinking(true);
    try {
      const ev = await api.post<Schemas['EvidenceOut']>(`/source-revisions/${revisionId}/evidence`, {
        char_start: toCodePoints(text, start),
        char_end: toCodePoints(text, end),
      });
      const quote = ev.excerpt;
      update({ claims: [...v.claims, { key: claimKey(), statement: quote, kind: 'expert_statement', evidence: [{ evidence_id: ev.id, quote, label: source?.title }] }] });
      toast.show(tr.contribute.linked);
    } catch (e) {
      toast.show(e instanceof ApiError ? errorMessage(e.code) : errorMessage('NETWORK'), { tone: 'error' });
    } finally {
      setLinking(false);
    }
  }

  async function save(submit: boolean) {
    if (busy) return;
    const errs: Record<string, string> = {};
    if (!v.title.trim()) errs.title = tr.contribute.titleRequired;
    v.claims.forEach((c) => {
      if (!c.statement.trim()) errs[`claim-${c.key}`] = tr.contribute.claimEmpty;
    });
    setErrors(errs);
    setFormError(null);
    if (Object.keys(errs).length) return;
    setBusy(submit ? 'submit' : 'save');
    const item = {
      page_id: target.pageId,
      base_revision_id: target.baseRevisionId,
      title: v.title.trim(),
      summary: v.summary.trim(),
      body_md: v.body_md,
      kind: v.kind,
      scope: v.scope,
      unknowns: v.unknowns.map((u) => u.trim()).filter(Boolean),
      aliases: v.aliases,
      claims: v.claims.map((c) => ({ statement: c.statement.trim(), kind: c.kind, evidence: c.evidence.map((e) => ({ evidence_id: e.evidence_id, quote: e.quote })) })),
    };
    try {
      let id: string;
      if (target.changeId) {
        await api.put<Schemas['ChangeDetailOut']>(`/changes/${target.changeId}`, { expected_hash: target.changeHash, items: [item], summary: target.changeSummary });
        if (submit) await api.post(`/changes/${target.changeId}/submit`);
        id = target.changeId;
      } else {
        const res = await api.post<Schemas['ChangeDetailOut']>(`/projects/${session.projectId}/changes`, { items: [item], submit, source_answer_id: target.sourceAnswerId ?? null }, { idempotencyKey: idemKey });
        id = res.id;
      }
      onDirty(false);
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
    <div className={s.editor}>
      <div className={s.edMeta}>
        {formError && <Banner tone="celiski">{formError}</Banner>}
        <div className={s.formRow}>
          <Field label={tr.contribute.pTitle} error={errors.title ?? null} className={s.grow}>
            {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} invalid={!!errors.title} value={v.title} onChange={(e) => update({ title: e.target.value })} />}
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
        </div>
        <Field label={tr.contribute.pSummary} hint={tr.contribute.pSummaryHint}>
          {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} rows={2} className={s.shortArea} value={v.summary} onChange={(e) => update({ summary: e.target.value })} />}
        </Field>
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
              <Textarea aria-labelledby="body-label" aria-describedby="body-hint" rows={10} value={v.body_md} onChange={(e) => update({ body_md: e.target.value })} className="mono" />
              <p id="body-hint" className={s.hint}>
                {tr.contribute.pBodyHint}
              </p>
            </TabPanel>
            <TabPanel value="preview">
              <div className={s.preview}>{v.body_md.trim() ? <Markdown>{v.body_md}</Markdown> : <p className={s.muted}>{tr.contribute.previewEmpty}</p>}</div>
            </TabPanel>
          </Tabs>
        </div>
      </div>

      <section className={s.edSource} aria-labelledby="src-text-h">
        <div className={s.edSourceHead}>
          <h3 id="src-text-h" className={s.subTitle}>
            {tr.contribute.sourceText}
          </h3>
          <Button size="sm" variant="ghost" onClick={onPickSource}>
            {source ? tr.contribute.changeSource : tr.contribute.pickSource}
          </Button>
        </div>
        {source ? (
          <>
            <p className={s.viewerSource}>{source.title}</p>
            {source.current_revision?.extraction !== 'complete' && <ExtractionNote extraction={source.current_revision?.extraction} />}
            {text ? (
              <>
                <p className={s.hint}>{tr.contribute.sourceTextHint}</p>
                <SourceViewer text={text} linked={linked} onLink={link} busy={linking} />
              </>
            ) : (
              <p className={s.muted}>{tr.contribute.sourceTextEmpty}</p>
            )}
          </>
        ) : (
          <p className={s.muted}>{tr.contribute.sourceTextEmpty}</p>
        )}
      </section>

      <section className={s.edClaims} aria-labelledby="claims-h">
        <h3 id="claims-h" className={s.subTitle}>
          {tr.contribute.claims}
        </h3>
        {v.claims.length === 0 ? (
          <p className={s.muted}>{tr.contribute.claimsEmpty}</p>
        ) : (
          <ol className={s.claimList}>
            {v.claims.map((c, i) => {
              const verbatim = isVerbatim(c);
              const err = errors[`claim-${c.key}`];
              return (
                <li key={c.key} className={s.claimItem}>
                  <div className={s.claimTop}>
                    <span className={s.claimNo} aria-hidden>
                      {i + 1}
                    </span>
                    <Field label={tr.contribute.claimN(i + 1)} error={err ?? null} className={s.grow}>
                      {({ id, describedBy }) => (
                        <Textarea
                          id={id}
                          rows={2}
                          className={s.shortArea}
                          invalid={!!err}
                          aria-describedby={[describedBy, !verbatim ? `nv-${c.key}` : ''].filter(Boolean).join(' ') || undefined}
                          value={c.statement}
                          onChange={(e) => updateClaim(c.key, { statement: e.target.value })}
                        />
                      )}
                    </Field>
                    <IconButton label={tr.contribute.removeClaim(i + 1)} onClick={() => update({ claims: v.claims.filter((x) => x.key !== c.key) })}>
                      <Trash2 size={16} aria-hidden />
                    </IconButton>
                  </div>
                  {!verbatim && c.statement.trim() && (
                    <p id={`nv-${c.key}`} className={s.warn}>
                      <AlertTriangle size={15} aria-hidden />
                      {tr.contribute.notVerbatim}
                    </p>
                  )}
                  {c.evidence.map((e) => (
                    <blockquote key={e.evidence_id} className={s.quote}>
                      <span className={s.quoteLabel}>
                        {tr.contribute.quote}
                        {e.label ? `: ${e.label}` : ''}
                      </span>
                      <span className={s.quoteText}>{e.quote}</span>
                    </blockquote>
                  ))}
                  {/* İddia türü varsayılanla gelir ("Uzman beyanı"); gerekirse açılıp değiştirilir. */}
                  <details className={s.claimKind}>
                    <summary>
                      {tr.contribute.claimKind}: {tr.claimKinds[c.kind] ?? c.kind}
                    </summary>
                    <Select aria-label={tr.contribute.claimKind} value={c.kind} onChange={(e) => updateClaim(c.key, { kind: e.target.value })}>
                      {CLAIM_KINDS.map((k) => (
                        <option key={k} value={k}>
                          {tr.claimKinds[k]}
                        </option>
                      ))}
                    </Select>
                  </details>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <div className={s.edRest}>
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

        <section aria-labelledby="pscope-h" className={s.unknownsBox}>
          <h3 id="pscope-h" className={s.subTitle}>
            {tr.contribute.pScope}
          </h3>
          <p className={s.hint}>{tr.contribute.pScopeHint}</p>
          <ScopeField value={v.scope} onChange={(sc) => update({ scope: sc })} allowIndependent />
        </section>
      </div>

      <div className={s.saveBar}>
        <Button variant="primary" icon={<Send size={16} aria-hidden />} loading={busy === 'submit'} disabled={!!busy} onClick={() => save(true)}>
          {tr.contribute.saveSubmit}
        </Button>
        <Button loading={busy === 'save'} disabled={!!busy} onClick={() => save(false)}>
          {tr.contribute.save}
        </Button>
      </div>
    </div>
  );
}
