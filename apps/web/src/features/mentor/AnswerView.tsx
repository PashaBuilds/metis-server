import { useMutation } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { ChevronRight, GitFork, RotateCcw, SlidersHorizontal, ThumbsDown, ThumbsUp } from 'lucide-react';
import { Fragment, useState } from 'react';
import { Button } from '@/design/primitives';
import { EvidenceStripe, ViaMark, type IzTarget } from '@/design/iz';
import { ScopeChips } from '@/app/ScopeBar';
import { useSession, type ScopeSel } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { formatDateTime, formatMs } from '@/lib/format';
import { Banner } from '@/features/shared/Banner';
import { Markdown } from '@/features/shared/Markdown';
import { parseTable } from '@/features/shared/table';
import { FreshnessBadge } from '@/features/shared/kinds';
import { messageOf } from '@/features/shared/hooks';
import { modelReason } from '@/features/shared/models';
import { asScope } from '@/features/shared/scope';
import { ANSWERED, DecisionBadge } from './decision';
import s from './Mentor.module.css';

export type Answer = Schemas['AnswerOut'];
type Citation = Schemas['Citation'];

type Alternative = {
  id: string;
  display_name: string;
};

const isAlt = (x: unknown): x is Alternative =>
  !!x && typeof x === 'object' && typeof (x as Alternative).id === 'string' && typeof (x as Alternative).display_name === 'string';

type Dropped = {
  text: string;
  reasons: string[];
};
const isDropped = (x: unknown): x is Dropped => !!x && typeof x === 'object' && typeof (x as Dropped).text === 'string' && Array.isArray((x as Dropped).reasons);

const TIMING_KEYS = ['retrieval_ms', 'selection_ms', 'generation_ms', 'validation_ms', 'total_ms'] as const;
const DIM_ORDER = ['domain', 'yatt', 'kart', 'proje'] as const;

/** Via işaretlerinin yanma başlangıcı: ilerleme adımları kapandıktan ve cevap belirdikten sonra. */
const IGNITE_START = 360;
const IGNITE_STEP = 40;

function targetFor(answerId: string, c: Citation): IzTarget {
  return { key: `ans:${answerId}:${c.n}`, evidenceId: c.evidence_id, claimId: c.claim_id, label: c.source_title, quote: c.quote };
}

function unionScope(citations: Citation[]): ScopeSel {
  const out: ScopeSel = { domain: [], yatt: [], kart: [], proje: [] };
  for (const c of citations) {
    const sc = asScope(c.scope);
    for (const d of DIM_ORDER) for (const v of sc[d]) if (!out[d].includes(v)) out[d].push(v);
  }
  return out;
}

interface Props {
  answer: Answer;
  /** Akıştan yeni geldiyse orkestre an (via'lar sırayla yanar). */
  live: boolean;
  onReask: (modelId: string | null) => void;
}

export function AnswerView({ answer, live, onReask }: Props) {
  const answered = ANSWERED.has(answer.decision) && answer.citations.length > 0;
  const byN = new Map(answer.citations.map((c) => [c.n, c]));
  let ignite = 0;
  const nextDelay = () => (live ? IGNITE_START + IGNITE_STEP * ignite++ : undefined);

  const marks = (refs: number[]) =>
    refs.map((n) => {
      const c = byN.get(n);
      return c ? <ViaMark key={n} n={n} target={targetFor(answer.id, c)} igniteDelay={nextDelay()} /> : null;
    });

  const steps = answer.level === 'steps';
  const explanation = answer.explanation.length ? (
    steps ? (
      <ol className={s.explSteps}>
        {answer.explanation.map((sen, i) => (
          <li key={i}>
            <EvidenceStripe count={sen.refs.length}>
              <span>{sen.text}</span>
              {marks(sen.refs)}
            </EvidenceStripe>
          </li>
        ))}
      </ol>
    ) : (
      <EvidenceStripe count={answer.citations.length}>
        <p className={s.explText}>
          {answer.explanation.map((sen, i) => (
            <Fragment key={i}>
              {i > 0 && ' '}
              <span>{sen.text}</span>
              {marks(sen.refs)}
            </Fragment>
          ))}
        </p>
      </EvidenceStripe>
    )
  ) : null;

  return (
    <article className={[s.answer, live ? s.answerLive : ''].join(' ')} aria-labelledby="answer-q">
      <header className={s.answerHead}>
        <div className={s.badges}>
          <DecisionBadge decision={answer.decision} />
          {answer.legacy && <span className={s.legacy}>{tr.mentor.legacy}</span>}
        </div>
        <h2 id="answer-q" className={s.answerQ}>
          {answer.question}
        </h2>
      </header>

      {answered ? (
        <>
          {explanation && (
            <section className={s.block} aria-label={tr.mentor.explanation}>
              <div className="reading">{explanation}</div>
            </section>
          )}
          <section className={s.block} aria-labelledby="answer-quotes">
            <h3 id="answer-quotes" className={s.blockTitle}>
              {tr.mentor.quotes}
            </h3>
            <ol className={s.quotes}>
              {answer.citations.map((c) => (
                <li key={c.n} className={s.quote}>
                  <div className={s.quoteHead}>
                    <ViaMark n={c.n} target={{ ...targetFor(answer.id, c), key: `ansq:${answer.id}:${c.n}` }} igniteDelay={nextDelay()} />
                    <span className={s.quoteSource}>{c.source_title}</span>
                    {c.locator_label && <span className={s.quoteLoc}>{c.locator_label}</span>}
                  </div>
                  <blockquote className={s.quoteText}>{parseTable(c.quote) ? <Markdown>{c.quote}</Markdown> : c.quote}</blockquote>
                  {c.page_title && (
                    <Link to="/bilgi/$pageId" params={{ pageId: c.page_id }} search={{}} className={s.quotePage}>
                      {tr.mentor.openPage}: {c.page_title}
                    </Link>
                  )}
                </li>
              ))}
            </ol>
          </section>
          <section className={s.block} aria-labelledby="answer-scope">
            <h3 id="answer-scope" className={s.blockTitle}>
              {tr.mentor.applicableScope}
            </h3>
            <ScopeChips scope={unionScope(answer.citations)} />
          </section>
        </>
      ) : (
        <Abstain answer={answer} onReask={onReask} />
      )}

      {answer.unknowns.length > 0 && (
        <section className={s.block} aria-labelledby="answer-unknowns">
          <h3 id="answer-unknowns" className={s.blockTitle}>
            {tr.mentor.unknowns}
          </h3>
          <ul className={s.bullets}>
            {answer.unknowns.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        </section>
      )}

      {answer.dense_note && <p className={s.hint}>{tr.mentor.denseNote[answer.dense_note] ?? ''}</p>}
      {answered && <RelatedList answer={answer} title={tr.mentor.related} />}

      <div className={s.answerFoot}>
        <Feedback answerId={answer.id} />
      </div>

      <ProductionRecord answer={answer} />
    </article>
  );
}

function Abstain({ answer, onReask }: { answer: Answer; onReask: (modelId: string | null) => void }) {
  const session = useSession();
  const d = answer.decision;
  const alternatives = answer.alternatives.filter(isAlt);
  let message = tr.decisionMessages[d] ?? '';
  if (d === 'NEEDS_SCOPE') {
    const dims = answer.needs_scope_dimensions.map((x) => tr.scope.dims[x] ?? x);
    message = dims.length ? tr.mentor.needsScope(dims.join(', ')) : tr.mentor.needsScopeGeneric;
  }
  const tone = d === 'NO_EVIDENCE' ? 'bilgi' : d === 'NEEDS_SCOPE' ? 'dikkat' : 'celiski';
  return (
    <div className={s.abstain}>
      <Banner
        tone={tone}
        actions={
          d === 'NEEDS_SCOPE' ? (
            <Button size="sm" icon={<SlidersHorizontal size={15} aria-hidden />} onClick={() => window.dispatchEvent(new CustomEvent('metis:open-scope'))}>
              {tr.mentor.changeScope}
            </Button>
          ) : d === 'RETRIEVAL_UNAVAILABLE' || d === 'MODEL_UNAVAILABLE' || d === 'VALIDATION_FAILED' ? (
            <Button size="sm" icon={<RotateCcw size={15} aria-hidden />} onClick={() => onReask(answer.model && typeof answer.model.id === 'string' ? answer.model.id : null)}>
              {tr.mentor.askAgain}
            </Button>
          ) : undefined
        }
      >
        <p>{message}</p>
        {d === 'MODEL_UNAVAILABLE' && answer.model_unavailable_reason && <p className={s.reason}>{tr.mentor.modelReason(modelReason(answer.model_unavailable_reason))}</p>}
      </Banner>

      {d === 'MODEL_UNAVAILABLE' && (answer.related_passages ?? []).length > 0 && (
        <section className={s.block} aria-labelledby="answer-passages">
          <h3 id="answer-passages" className={s.blockTitle}>
            {tr.mentor.passagesTitle}
          </h3>
          <p className={s.hint}>{tr.mentor.passagesLead}</p>
          <ol className={s.passages}>
            {(answer.related_passages ?? []).map((p) => (
              <li key={p.claim_id}>
                <Link to="/bilgi/$pageId" params={{ pageId: p.page_id }} search={{}} className={s.relatedTitle}>
                  {p.heading_path ? `${p.title} › ${p.heading_path}` : p.title}
                </Link>
                {parseTable(p.text) ? (
                  <div className={s.passageText}>
                    <Markdown>{p.text}</Markdown>
                  </div>
                ) : (
                  <p className={s.passageText}>{p.text}</p>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      {d === 'MODEL_UNAVAILABLE' && (
        <section className={s.block} aria-labelledby="answer-alts">
          <h3 id="answer-alts" className={s.blockTitle}>
            {tr.mentor.alternatives}
          </h3>
          {alternatives.length ? (
            <div className={s.altRow}>
              {alternatives.map((a) => (
                <Button key={a.id} size="sm" onClick={() => onReask(a.id)}>
                  {tr.mentor.askWith(a.display_name)}
                </Button>
              ))}
            </div>
          ) : (
            <p className={s.hint}>{tr.mentor.noAlternatives}</p>
          )}
        </section>
      )}

      {d === 'CONFLICTING' && answer.conflict_sides.length > 0 && (
        <section className={s.block} aria-labelledby="answer-sides">
          <h3 id="answer-sides" className={s.blockTitle}>
            {tr.mentor.conflictSides}
          </h3>
          <div className={s.sides}>
            {answer.conflict_sides.map((side, i) => (
              <div key={i} className={s.side}>
                <span className={s.sideLabel}>
                  <GitFork size={14} aria-hidden />
                  {tr.mentor.conflictSide(i + 1)}
                </span>
                {side.page_id ? (
                  <Link to="/bilgi/$pageId" params={{ pageId: side.page_id }} search={{}} className={s.sideTitle}>
                    {side.page_title}
                  </Link>
                ) : (
                  <span className={s.sideTitle}>{side.page_title}</span>
                )}
                <blockquote className={s.quoteText}>
                  <mark>{side.quote}</mark>
                </blockquote>
              </div>
            ))}
          </div>
          {answer.conflict_finding_id && session.roles.has('contributor') && (
            <div>
              <Link to="/saglik" search={{ finding: answer.conflict_finding_id }} className={s.primaryLink}>
                {tr.mentor.resolveConflict}
              </Link>
            </div>
          )}
        </section>
      )}

      <RelatedList answer={answer} title={tr.mentor.abstainKnown} showEmpty />
      <div className={s.abstainFoot}>
        <p className={s.hint}>{tr.mentor.abstainSaved}</p>
        {session.roles.has('contributor') && (
          <Link to="/katki" className={s.textLink}>
            {tr.mentor.contribute}
          </Link>
        )}
      </div>
    </div>
  );
}

function RelatedList({ answer, title, showEmpty }: { answer: Answer; title: string; showEmpty?: boolean }) {
  const rows = answer.related;
  if (!rows.length && !showEmpty) return null;
  return (
    <section className={s.block} aria-labelledby={`rel-${answer.id}`}>
      <h3 id={`rel-${answer.id}`} className={s.blockTitle}>
        {title}
      </h3>
      {rows.length === 0 ? (
        <p className={s.hint}>{tr.mentor.abstainNoneRelated}</p>
      ) : (
        <ul className={s.related}>
          {rows.map((r) => (
            <li key={r.page_id} className={s.relatedRow}>
              <Link to="/bilgi/$pageId" params={{ pageId: r.page_id }} search={{}} className={s.relatedTitle}>
                {r.title}
              </Link>
              <span className={s.relatedMeta}>
                <FreshnessBadge freshness={r.freshness} size="sm" />
                {r.open_conflict && (
                  <span className={s.conflictTag}>
                    <GitFork size={13} aria-hidden />
                    {tr.mentor.openConflict}
                  </span>
                )}
              </span>
              {r.excluded && <span className={s.excluded}>{tr.mentor.relatedExcluded[r.excluded] ?? r.excluded}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Feedback({ answerId }: { answerId: string }) {
  const [sent, setSent] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: (rating: 'helpful' | 'not_helpful') => api.post(`/answers/${answerId}/feedback`, { rating, comment: '' }),
    onSuccess: (_d, rating) => setSent(rating),
  });
  if (sent)
    return (
      <p className={s.hint} role="status">
        {tr.mentor.feedbackThanks}
      </p>
    );
  return (
    <div className={s.feedback} role="group" aria-label={tr.mentor.feedback}>
      <span className={s.feedbackLabel}>{tr.mentor.feedback}</span>
      <Button size="sm" variant="ghost" icon={<ThumbsUp size={15} aria-hidden />} onClick={() => m.mutate('helpful')} disabled={m.isPending}>
        {tr.mentor.helpful}
      </Button>
      <Button size="sm" variant="ghost" icon={<ThumbsDown size={15} aria-hidden />} onClick={() => m.mutate('not_helpful')} disabled={m.isPending}>
        {tr.mentor.notHelpful}
      </Button>
      {m.isError && (
        <span className={s.error} role="alert">
          {messageOf(m.error)}
        </span>
      )}
    </div>
  );
}

function ProductionRecord({ answer }: { answer: Answer }) {
  const model = answer.model && typeof answer.model.display_name === 'string' ? answer.model.display_name : null;
  const timings = answer.timings as Record<string, number | null | undefined>;
  const dropped = answer.dropped_sentences.filter(isDropped);
  const scope = asScope(answer.scope);
  const scopeEmpty = DIM_ORDER.every((d) => scope[d].length === 0);
  return (
    <details className={s.record}>
      <summary>
        <ChevronRight size={14} aria-hidden className={s.recordChevron} />
        {tr.mentor.record}
      </summary>
      <dl className={s.recordList}>
        <dt>{tr.mentor.recModel}</dt>
        <dd>{model ?? tr.mentor.recNoModel}</dd>
        <dt>{tr.mentor.recPrompt}</dt>
        <dd className="mono">{answer.prompt_version || tr.common.none}</dd>
        <dt>{tr.mentor.recPublication}</dt>
        <dd className="mono">{answer.publication_id ?? tr.common.none}</dd>
        <dt>{tr.mentor.recScope}</dt>
        <dd>{scopeEmpty ? tr.scope.all : <ScopeChips scope={scope} />}</dd>
        <dt>{tr.mentor.recLevel}</dt>
        <dd>{tr.mentor.levels[answer.level] ?? answer.level}</dd>
        <dt>{tr.mentor.recTimings}</dt>
        <dd>
          <ul className={s.timings}>
            {TIMING_KEYS.map((k) => (
              <li key={k}>
                <span>{tr.mentor.timings[k]}</span>
                <span className="tabular">{formatMs(timings[k] ?? null)}</span>
              </li>
            ))}
          </ul>
        </dd>
        <dt>{tr.mentor.recDropped}</dt>
        <dd>
          {answer.explanation_dropped > 0 || dropped.length > 0 ? (
            <>
              <p>{tr.mentor.recDroppedCount(Math.max(answer.explanation_dropped, dropped.length))}</p>
              {dropped.length > 0 && (
                <ul className={s.dropped}>
                  {dropped.map((x, i) => (
                    <li key={i}>
                      <span>{x.text}</span>
                      <span className={s.dropReason}>{x.reasons.map((r) => tr.mentor.dropReasons[r] ?? r).join(', ')}</span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            tr.mentor.recDroppedNone
          )}
        </dd>
        <dt>{tr.mentor.recCreated}</dt>
        <dd className="tabular">{formatDateTime(answer.created_at)}</dd>
        <dt>{tr.mentor.recAnswerId}</dt>
        <dd className="mono">{answer.id}</dd>
      </dl>
    </details>
  );
}
