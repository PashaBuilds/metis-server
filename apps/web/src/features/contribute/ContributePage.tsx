import { useQuery } from '@tanstack/react-query';
import { getRouteApi, Link, useBlocker, useNavigate } from '@tanstack/react-router';
import { PenLine } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Button, Dialog, EmptyState, SkeletonRows } from '@/design/primitives';
import { SourceKindIcon } from '@/design/iz';
import { PageHeader } from '@/app/Shell';
import { EMPTY_SCOPE } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { useUnsavedWarning } from '@/lib/hooks';
import { Banner } from '@/features/shared/Banner';
import { messageOf } from '@/features/shared/hooks';
import { asScope } from '@/features/shared/scope';
import { claimKey, DraftEditor, type DraftTarget, type DraftValues } from './DraftEditor';
import { MetisOption } from './MetisOption';
import { SourceStep } from './SourceStep';
import type { SourceDetail } from './types';
import s from './Contribute.module.css';

const route = getRouteApi('/app/katki');

type RevisionView = Schemas['RevisionView'];

function valuesFromRevision(r: RevisionView): DraftValues {
  return {
    title: r.title,
    kind: r.kind,
    summary: r.summary,
    body_md: r.body_md,
    scope: asScope(r.scope),
    unknowns: r.unknowns.filter((u): u is string => typeof u === 'string'),
    aliases: r.aliases.filter((u): u is string => typeof u === 'string'),
    claims: r.claims.map((c) => ({
      key: claimKey(),
      statement: c.statement,
      kind: c.kind,
      evidence: c.evidence.map((e) => ({ evidence_id: e.evidence_id, quote: e.quote, label: e.source_title })),
    })),
  };
}

type PrefillClaim = {
  statement: string;
  evidence_id: string;
  quote: string;
  page_title?: string;
};
const isPrefillClaim = (x: unknown): x is PrefillClaim =>
  !!x && typeof x === 'object' && typeof (x as PrefillClaim).statement === 'string' && typeof (x as PrefillClaim).evidence_id === 'string' && typeof (x as PrefillClaim).quote === 'string';

/** Mentor cevabından taslak: iddialar cevabın kaynak alıntılarıdır, kanıt bağları önceden seçilidir. */
function valuesFromPrefill(p: Schemas['DraftPrefill']): DraftValues {
  return {
    ...EMPTY_VALUES,
    title: p.title,
    body_md: p.body_md,
    scope: asScope(p.scope),
    claims: p.claims.filter(isPrefillClaim).map((c) => ({
      key: claimKey(),
      statement: c.statement,
      kind: 'expert_statement',
      evidence: [{ evidence_id: c.evidence_id, quote: c.quote, label: c.page_title }],
    })),
  };
}

const EMPTY_VALUES: DraftValues = { title: '', kind: 'concept', summary: '', body_md: '', scope: EMPTY_SCOPE, unknowns: [], aliases: [], claims: [] };

export function ContributePage() {
  const search = route.useSearch();
  const navigate = useNavigate();
  const answerMode = !!search.answer && !search.change && !search.page;
  const editMode = !!search.change || !!search.page || answerMode;

  const change = useQuery({
    queryKey: ['change', search.change],
    queryFn: () => api.get<Schemas['ChangeDetailOut']>(`/changes/${search.change}`),
    enabled: !!search.change,
    staleTime: 0,
  });
  const page = useQuery({
    queryKey: ['page', search.page, null],
    queryFn: () => api.get<Schemas['PageDetailOut']>(`/pages/${search.page}`),
    enabled: !!search.page && !search.change,
  });

  const prefill = useQuery({
    queryKey: ['draft-prefill', search.answer],
    queryFn: () => api.get<Schemas['DraftPrefill']>(`/answers/${search.answer}/draft-prefill`),
    enabled: answerMode,
    staleTime: Infinity,
  });

  const [step, setStep] = useState<'source' | 'draft'>(editMode ? 'draft' : 'source');
  const [path, setPath] = useState<'choose' | 'self'>(editMode ? 'self' : 'choose');
  const [source, setSource] = useState<SourceDetail | null>(null);
  const [sourceError, setSourceError] = useState<string | null>(null);

  const dirtyRef = useRef({ source: false, editor: false });
  const allowNav = useRef(false);
  const [dirty, setDirtyState] = useState(false);
  const setDirty = (part: 'source' | 'editor', d: boolean) => {
    dirtyRef.current[part] = d;
    setDirtyState(dirtyRef.current.source || dirtyRef.current.editor);
  };
  useUnsavedWarning(dirty);
  const blocker = useBlocker({
    shouldBlockFn: () => !allowNav.current && (dirtyRef.current.source || dirtyRef.current.editor),
    withResolver: true,
  });

  async function selectSource(id: string) {
    setSourceError(null);
    try {
      const detail = await api.get<SourceDetail>(`/sources/${id}`);
      setSource(detail);
    } catch (e) {
      setSourceError(messageOf(e));
    }
  }

  const preselected = useRef(false);
  useEffect(() => {
    if (search.source && !preselected.current) {
      preselected.current = true;
      void selectSource(search.source);
    }
  }, [search.source]);

  const go = (fn: () => void) => {
    allowNav.current = true;
    fn();
  };

  let initial: DraftValues | null = EMPTY_VALUES;
  let target: DraftTarget = { pageId: null, baseRevisionId: null, changeId: null, changeHash: null, changeSummary: '' };
  let notice: string | null = null;
  let blocked: string | null = null;
  if (search.change) {
    initial = null;
    if (change.data) {
      const item = change.data.items[0];
      if (!change.data.can_edit || !item?.proposed) blocked = tr.contribute.notEditable;
      else {
        initial = valuesFromRevision(item.proposed);
        target = { pageId: item.page_id, baseRevisionId: item.base?.id ?? null, changeId: change.data.id, changeHash: change.data.hash, changeSummary: change.data.summary };
        notice = tr.contribute.fromChange;
      }
    }
  } else if (search.page) {
    initial = null;
    if (page.data) {
      initial = valuesFromRevision(page.data.revision);
      target = { pageId: page.data.page_id, baseRevisionId: page.data.published_revision_id, changeId: null, changeHash: null, changeSummary: '' };
      notice = tr.contribute.fromPage;
    }
  } else if (answerMode) {
    initial = null;
    if (prefill.data) {
      initial = valuesFromPrefill(prefill.data);
      target = { ...target, sourceAnswerId: prefill.data.source_answer_id };
      notice = tr.contribute.fromAnswer;
    }
  } else if (source?.current_revision) {
    initial = { ...EMPTY_VALUES, scope: asScope(source.current_revision.scope) };
  }
  const loadError =
    (search.change && change.isError && change.error) || (search.page && !search.change && page.isError && page.error) || (answerMode && prefill.isError && prefill.error);
  const title = search.change ? tr.contribute.titleDraft : search.page ? tr.contribute.titleEdit : tr.contribute.title;

  return (
    <div className={s.page}>
      <PageHeader title={title} />
      {loadError ? (
        <EmptyState title={tr.shared.loadError}>{messageOf(loadError)}</EmptyState>
      ) : blocked ? (
        <EmptyState
          title={blocked}
          actions={
            search.change ? (
              <Link to="/kayitlar/$changeId" params={{ changeId: search.change }}>
                {tr.page.openChange}
              </Link>
            ) : undefined
          }
        />
      ) : (
        <>
          <ol className={s.steps} aria-label={title}>
            <li className={[s.stepItem, step === 'source' ? s.stepCurrent : s.stepDone].join(' ')} aria-current={step === 'source' ? 'step' : undefined}>
              {step === 'draft' ? (
                <button type="button" className={s.stepBtn} onClick={() => setStep('source')}>
                  <span className={s.stepNo}>1</span>
                  {tr.contribute.stepSource}
                  {source && <span className={s.stepValue}>{source.title}</span>}
                </button>
              ) : (
                <span className={s.stepBtn}>
                  <span className={s.stepNo}>1</span>
                  {tr.contribute.stepSource}
                </span>
              )}
            </li>
            <li className={[s.stepItem, step === 'draft' ? s.stepCurrent : ''].join(' ')} aria-current={step === 'draft' ? 'step' : undefined}>
              <span className={s.stepBtn}>
                <span className={s.stepNo}>2</span>
                {tr.contribute.stepDraft}
              </span>
            </li>
          </ol>

          {notice && <Banner tone="bilgi">{notice}</Banner>}

          {step === 'source' && (
            <section className={s.panel} aria-label={tr.contribute.stepSource}>
              {sourceError && <Banner tone="celiski">{sourceError}</Banner>}
              <SourceStep
                selected={source}
                onSelect={selectSource}
                onClear={() => setSource(null)}
                onContinue={() => setStep('draft')}
                onDirty={(d) => setDirty('source', d)}
                offerRevision={!!search.source}
              />
              {!source && editMode && (
                <div>
                  <Button variant="ghost" onClick={() => setStep('draft')}>
                    {tr.contribute.skipSource}
                  </Button>
                </div>
              )}
            </section>
          )}
          {step === 'draft' && path === 'choose' && (
            <div className={s.options}>
              <MetisOption source={source} onStarted={(id) => go(() => navigate({ to: '/gorevler/$jobId', params: { jobId: id } }))} />
              <div className={s.option}>
                <div className={s.optionHead}>
                  <PenLine size={20} aria-hidden />
                  <h3 className={s.optionTitle}>{tr.contribute.selfTitle}</h3>
                </div>
                <p className={s.optionText}>{tr.contribute.selfText}</p>
                {source && (
                  <p className={s.optionSource}>
                    <SourceKindIcon kind={source.kind} size={15} />
                    {source.title}
                  </p>
                )}
                <div className={s.optionAction}>
                  <Button variant="primary" onClick={() => setPath('self')}>
                    {tr.contribute.openEditor}
                  </Button>
                </div>
              </div>
            </div>
          )}
          {path === 'self' && (
            <div hidden={step !== 'draft'}>
              {initial ? (
                <DraftEditor
                  key={target.changeId ?? target.pageId ?? target.sourceAnswerId ?? 'new'}
                  initial={initial}
                  target={target}
                  source={source}
                  onPickSource={() => setStep('source')}
                  onDirty={(d) => setDirty('editor', d)}
                  onSaved={(id) => go(() => navigate({ to: '/kayitlar/$changeId', params: { changeId: id } }))}
                />
              ) : (
                <SkeletonRows rows={5} />
              )}
            </div>
          )}
        </>
      )}

      <Dialog
        open={blocker.status === 'blocked'}
        onOpenChange={(o) => !o && blocker.reset?.()}
        title={tr.contribute.unsavedTitle}
        description={tr.contribute.unsavedDesc}
        footer={
          <>
            <Button variant="ghost" onClick={() => blocker.reset?.()}>
              {tr.contribute.stay}
            </Button>
            <Button variant="danger" onClick={() => blocker.proceed?.()}>
              {tr.contribute.leave}
            </Button>
          </>
        }
      />
    </div>
  );
}
