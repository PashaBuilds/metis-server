import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getRouteApi, useNavigate } from '@tanstack/react-router';
import { Check, CornerDownLeft, Loader2, MessagesSquare, SlidersHorizontal, Trash2 } from 'lucide-react';
import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { Button, ConfirmDialog, EmptyState, IconButton, Segmented, SkeletonRows, useToast } from '@/design/primitives';
import { PageHeader } from '@/app/Shell';
import { ScopeChips } from '@/app/ScopeBar';
import { scopeIsEmpty, useSession } from '@/app/session';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, postStream, type Schemas } from '@/lib/api/client';
import { readSse } from '@/lib/api/sse';
import { formatWhen } from '@/lib/format';
import { Banner } from '@/features/shared/Banner';
import { messageOf } from '@/features/shared/hooks';
import { ModelSelect, useAvailableModels } from '@/features/shared/models';
import { AnswerView, type Answer } from './AnswerView';
import { DecisionBadge } from './decision';
import s from './Mentor.module.css';

const route = getRouteApi('/app/mentor');
type Level = 'short' | 'steps' | 'detailed';
const LEVELS: Level[] = ['short', 'steps', 'detailed'];
const asLevel = (v: string | undefined): Level => (LEVELS as string[]).includes(v ?? '') ? (v as Level) : 'short';

type Related = Schemas['RelatedPage'];
type Step = 'searching' | 'ranking' | 'generating' | 'verifying';
const STEPS: Step[] = ['searching', 'ranking', 'generating', 'verifying'];
type Run =
  | { phase: 'idle' }
  /** `ranked`: yeniden sıralanan aday sayısı (sıralayıcı kurulu değilse null); `stepAt`: adımın başladığı an (ms). */
  | { phase: 'streaming'; step: Step; related: Related[] | null; ranked: number | null; generating: boolean; stepAt: number }
  | { phase: 'done'; answer: Answer; related: Related[] | null; verified: boolean; ranked: number | null; generating: boolean }
  | { phase: 'error'; message: string };

export function MentorPage() {
  const session = useSession();
  const pid = session.projectId;
  const search = route.useSearch();
  const navigate = useNavigate({ from: '/mentor' });
  const qc = useQueryClient();
  const toast = useToast();
  const models = useAvailableModels(pid);
  const modelList = models.data ?? [];
  const savedModel = session.pref<string | null>('mentor_model_id', null);
  const questionId = useId();
  const modelFieldId = useId();

  const [question, setQuestion] = useState(search.q ?? '');
  const [level, setLevel] = useState<Level>(asLevel(search.level));
  const [run, setRun] = useState<Run>({ phase: 'idle' });
  const [toDelete, setToDelete] = useState<Schemas['AnswerListItem'] | null>(null);
  const modelId = search.model ?? savedModel ?? '';

  /* ---------------------------------------------------------------- akış */
  const askKey = search.q && pid ? [pid, search.q, search.model ?? '', search.level ?? '', search.n ?? ''].join('|') : null;
  const runRef = useRef(0);
  useEffect(() => {
    if (!askKey || !search.q || !pid) return;
    const ctrl = new AbortController();
    const runId = ++runRef.current;
    const body = {
      question: search.q,
      level: asLevel(search.level),
      model_id: search.model || null,
      scope: scopeIsEmpty(session.scope) ? null : session.scope,
    };
    setQuestion(search.q);
    setLevel(asLevel(search.level));
    setRun({ phase: 'streaming', step: 'searching', related: null, ranked: null, generating: false, stepAt: Date.now() });
    (async () => {
      let related: Related[] | null = null;
      let verified = false;
      let ranked: number | null = null;
      let generating = false;
      try {
        const res = await postStream(`/projects/${pid}/mentor/stream`, body, ctrl.signal);
        for await (const ev of readSse(res)) {
          if (runId !== runRef.current) return;
          if (ev.event === 'progress') {
            const data = JSON.parse(ev.data) as { step: string; candidates?: number };
            const step = (STEPS as string[]).includes(data.step) ? (data.step as Step) : null;
            if (!step) continue;
            if (step === 'verifying') verified = true;
            if (step === 'generating') generating = true;
            if (step === 'ranking') ranked = typeof data.candidates === 'number' ? data.candidates : 0;
            setRun((r) => (r.phase === 'streaming' ? { ...r, step, ranked, generating, stepAt: Date.now() } : r));
          } else if (ev.event === 'sources') {
            related = (JSON.parse(ev.data) as { related: Related[] }).related;
            setRun((r) => (r.phase === 'streaming' ? { ...r, related } : r));
          } else if (ev.event === 'result') {
            const answer = JSON.parse(ev.data) as Answer;
            qc.setQueryData(['answer', answer.id], answer);
            void qc.invalidateQueries({ queryKey: ['answers', pid] });
            setRun({ phase: 'done', answer, related, verified, ranked, generating });
            navigate({ search: { answer: answer.id }, replace: true });
            return;
          } else if (ev.event === 'error') {
            const err = JSON.parse(ev.data) as { code?: string };
            setRun({ phase: 'error', message: errorMessage(err.code) });
            return;
          }
        }
        if (runId === runRef.current) setRun((r) => (r.phase === 'streaming' ? { phase: 'error', message: tr.mentor.streamError } : r));
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') return;
        if (runId === runRef.current) setRun({ phase: 'error', message: e instanceof ApiError ? errorMessage(e.code) : errorMessage('NETWORK') });
      }
    })();
    return () => ctrl.abort();
    // Kapsam soruyla birlikte gönderilir; kapsam değişince otomatik yeniden sorulmaz.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [askKey]);

  /* --------------------------------------------------------- kayıtlı cevap */
  const liveAnswer = run.phase === 'done' && run.answer.id === search.answer ? run.answer : null;
  const stored = useQuery({
    queryKey: ['answer', search.answer],
    queryFn: () => api.get<Answer>(`/answers/${search.answer}`),
    enabled: !!search.answer && !liveAnswer,
  });
  const shown = liveAnswer ?? (search.answer ? stored.data : undefined);
  const lastShown = useRef<string | null>(null);
  useEffect(() => {
    if (shown && lastShown.current !== shown.id) {
      lastShown.current = shown.id;
      setQuestion(shown.question);
      setLevel(asLevel(shown.level));
    }
  }, [shown]);

  const recent = useQuery({
    queryKey: ['answers', pid],
    queryFn: () => api.get<Schemas['AnswerListItem'][]>(`/projects/${pid}/answers`),
    enabled: !!pid,
  });

  function ask(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (q.length < 2) return;
    navigate({ search: { q, model: modelId || undefined, level: level === 'short' ? undefined : level, n: String(Date.now()) } });
  }

  function reask(model: string | null) {
    if (!shown) return;
    navigate({ search: { q: shown.question, model: model ?? undefined, level: shown.level === 'short' ? undefined : shown.level, n: String(Date.now()) } });
  }

  async function confirmDelete() {
    if (!toDelete) return;
    try {
      await api.del(`/answers/${toDelete.id}`);
      void qc.invalidateQueries({ queryKey: ['answers', pid] });
      if (search.answer === toDelete.id) navigate({ search: {}, replace: true });
      toast.show(tr.common.deleted);
    } catch (e) {
      toast.show(messageOf(e), { tone: 'error' });
    }
  }

  const streaming = run.phase === 'streaming';
  const closing = liveAnswer && run.phase === 'done' ? run : null;
  const scope = session.scope;

  return (
    <div className={s.wrap}>
      <PageHeader title={tr.mentor.title} />
      <div className={s.page}>
      <div className={s.main}>
        <form className={s.form} onSubmit={ask}>
          <label htmlFor={questionId} className={s.label}>
            {tr.mentor.question}
          </label>
          <div className={s.askField}>
            <textarea
              id={questionId}
              className={s.askInput}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder={tr.mentor.questionPlaceholder}
              rows={2}
              maxLength={2000}
            />
            <Button type="submit" variant="primary" icon={<CornerDownLeft size={16} aria-hidden />} disabled={question.trim().length < 2} loading={streaming}>
              {tr.mentor.ask}
            </Button>
          </div>
          <div className={s.controls}>
            <div className={s.control}>
              <span className={s.label}>{tr.mentor.scope}</span>
              <span className={s.scopeValue}>{scopeIsEmpty(scope) ? <span className={s.scopeAll}>{tr.mentor.scopeAll}</span> : <ScopeChips scope={scope} />}</span>
              <Button size="sm" variant="ghost" icon={<SlidersHorizontal size={15} aria-hidden />} onClick={() => window.dispatchEvent(new CustomEvent('metis:open-scope'))}>
                {tr.mentor.changeScope}
              </Button>
            </div>
            <div className={s.control}>
              <span className={s.label} id={`${modelFieldId}-l`}>
                {tr.mentor.level}
              </span>
              <Segmented<Level> label={tr.mentor.level} value={level} onChange={setLevel} options={LEVELS.map((l) => ({ value: l, label: tr.mentor.levels[l] }))} />
            </div>
            {modelList.length > 0 && (
              <div className={s.control}>
                <label htmlFor={modelFieldId} className={s.label}>
                  {tr.models.label}
                </label>
                <ModelSelect
                  id={modelFieldId}
                  className={s.modelSelect}
                  value={modelId}
                  onChange={(v) => {
                    session.setPref('mentor_model_id', v || null);
                    if (search.model !== undefined) navigate({ search: (old) => ({ ...old, model: v || undefined }), replace: true });
                  }}
                  models={modelList}
                  emptyLabel={tr.models.auto}
                />
              </div>
            )}
          </div>
        </form>

        <div className={s.result} aria-live="polite">
          {(streaming || closing) && <Progress run={streaming ? run : closing!} closing={!!closing} />}
          {run.phase === 'error' && !shown && (
            <Banner tone="celiski" actions={<Button size="sm" onClick={() => navigate({ search: (old) => ({ ...old, n: String(Date.now()) }) })}>{tr.mentor.askAgain}</Button>}>
              {run.message}
            </Banner>
          )}
          {!streaming && shown && <AnswerView key={shown.id} answer={shown} live={!!liveAnswer} onReask={reask} />}
          {!streaming && search.answer && !shown && stored.isLoading && <SkeletonRows rows={4} />}
          {!streaming && search.answer && stored.isError && <Banner tone="dikkat">{tr.mentor.answerMissing}</Banner>}
          {!streaming && !search.answer && run.phase === 'idle' && !search.q && (
            <EmptyState icon={<MessagesSquare size={24} />} title={tr.mentor.emptyTitle}>
              {tr.mentor.emptyText}
            </EmptyState>
          )}
        </div>
      </div>

      <aside className={s.rail} aria-labelledby="recent-h">
        <h2 id="recent-h" className={s.railTitle}>
          {tr.mentor.recent}
        </h2>
        {recent.isLoading ? (
          <SkeletonRows rows={4} />
        ) : !recent.data?.length ? (
          <p className={s.hint}>{tr.mentor.recentEmpty}</p>
        ) : (
          <ul className={s.recent}>
            {recent.data.map((a) => (
              <li key={a.id} className={[s.recentRow, a.id === search.answer ? s.recentActive : ''].join(' ')}>
                <button type="button" className={s.recentOpen} onClick={() => navigate({ search: { answer: a.id } })} aria-current={a.id === search.answer ? 'true' : undefined}>
                  <span className={s.recentQ}>{a.question}</span>
                  <span className={s.recentMeta}>
                    <DecisionBadge decision={a.decision} size="sm" />
                    <time className={s.time} dateTime={a.created_at}>
                      {formatWhen(a.created_at)}
                    </time>
                  </span>
                </button>
                <IconButton label={tr.mentor.deleteAnswer(a.question)} size="sm" onClick={() => setToDelete(a)}>
                  <Trash2 size={15} aria-hidden />
                </IconButton>
              </li>
            ))}
          </ul>
        )}
      </aside>
      </div>

      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title={tr.mentor.deleteTitle}
        description={tr.mentor.deleteDesc}
        confirmLabel={tr.common.delete}
        danger
        onConfirm={confirmDelete}
      />
    </div>
  );
}

function Progress({ run, closing }: { run: Extract<Run, { phase: 'streaming' } | { phase: 'done' }>; closing: boolean }) {
  const related = run.related;
  const step = run.phase === 'streaming' ? run.step : 'done';
  const sourcesDone = related !== null;
  const after = (k: Step) => step === 'done' || STEPS.indexOf(step as Step) > STEPS.indexOf(k);
  type Row = { key: string; label: string; state: 'active' | 'done' | 'pending' };
  const steps: Row[] = [
    { key: 'searching', label: tr.mentor.steps.searching!, state: sourcesDone || step !== 'searching' ? 'done' : 'active' },
    ...(run.ranked !== null
      ? [{ key: 'ranking', label: tr.mentor.steps.ranking!, state: (sourcesDone || after('ranking') ? 'done' : 'active') as Row['state'] }]
      : []),
    {
      key: 'sources',
      label: related && related.length === 0 ? tr.mentor.steps.sourcesNone! : tr.mentor.steps.sources!,
      state: sourcesDone ? 'done' : 'pending',
    },
    ...(run.generating
      ? [{ key: 'generating', label: tr.mentor.steps.generating!, state: (after('generating') ? 'done' : step === 'generating' ? 'active' : 'pending') as Row['state'] }]
      : []),
    { key: 'verifying', label: tr.mentor.steps.verifying!, state: run.phase === 'done' ? (run.verified ? 'done' : 'pending') : step === 'verifying' ? 'active' : 'pending' },
  ];
  return (
    <div className={[s.progress, closing ? s.progressClosing : ''].join(' ')} role="status" aria-label={tr.mentor.progressLabel} aria-hidden={closing || undefined}>
      <ol className={s.progressSteps}>
        {steps.map((st) => (
          <li key={st.key} className={[s.progressStep, s[`ps-${st.state}`]].join(' ')}>
            <span className={s.progressIcon} aria-hidden>
              {st.state === 'done' ? <Check size={14} /> : st.state === 'active' ? <Loader2 size={14} className={s.spin} /> : null}
            </span>
            <span>
              {st.label}
              {st.key === 'sources' && related && related.length > 0 && <span className={s.progressCount}>{tr.mentor.foundSources(related.length)}</span>}
            </span>
          </li>
        ))}
      </ol>
      {run.phase === 'streaming' && !closing && <Activity step={run.step} ranked={run.ranked} stepAt={run.stepAt} />}
      {related && related.length > 0 && !closing && (
        <ul className={s.progressSources}>
          {related.slice(0, 6).map((r) => (
            <li key={r.page_id}>{r.title}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Şu an ne yapıldığı + adımda geçen süre; uzun süren model çağrısında kullanıcı neyi beklediğini bilir. */
function Activity({ step, ranked, stepAt }: { step: Step; ranked: number | null; stepAt: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const seconds = Math.max(0, Math.floor((now - stepAt) / 1000));
  const hint = step === 'ranking' ? tr.mentor.activity.ranking(ranked ?? 0) : tr.mentor.activity[step];
  return (
    <div className={s.activity}>
      <div className={s.activityBar} aria-hidden />
      <p className={s.activityText}>
        <span>{hint}</span>
        {/* Ekran okuyucu her saniye bölgeyi yeniden okumasın: süre yalnız görsel. */}
        {seconds >= 2 && <span className={s.activityTime} aria-hidden>{tr.mentor.elapsed(seconds)}</span>}
      </p>
    </div>
  );
}
