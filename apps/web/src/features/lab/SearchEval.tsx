import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, Plus, Search, X } from 'lucide-react';
import { useState } from 'react';
import { Button, Field, IconButton, Input, Select, SkeletonRows, useToast } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { formatDateTime } from '@/lib/format';
import { messageOf } from '@/features/shared/hooks';
import s from './Lab.module.css';

type Question = Schemas['QuestionOut'];
type Run = Schemas['RunOut'];
type Kind = Schemas['QuestionIn']['kind'];
type Hit = Schemas['SearchHit'];

const KINDS: Kind[] = ['tanimlayici', 'kavram', 'nasil', 'issue', 'karisik'];
const METRICS = ['recall_at_5', 'recall_at_10', 'mrr', 'ndcg_at_10', 'quote_at_5'] as const;

function fmt(v: unknown): string {
  return typeof v === 'number' ? v.toFixed(3) : tr.searchEval.notMeasured;
}

/** Arama ölçümü (yönetici, proje sorumlusu): soru seti + deterministik koşu; önceki koşuyla yan yana. Modelsiz. */
export function SearchEval({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const base = `/projects/${projectId}/search-eval`;
  const questions = useQuery({ queryKey: ['search-eval-questions', projectId], queryFn: () => api.get<Question[]>(`${base}/questions`) });
  const runs = useQuery({ queryKey: ['search-eval-runs', projectId], queryFn: () => api.get<Run[]>(`${base}/runs`) });
  const [question, setQuestion] = useState('');
  const [quote, setQuote] = useState('');
  const [kind, setKind] = useState<Kind>('kavram');
  const [pages, setPages] = useState<{ id: string; title: string }[]>([]);
  const [find, setFind] = useState('');
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [note, setNote] = useState('');

  const add = useMutation({
    mutationFn: () => api.post<Question>(`${base}/questions`, { question, expected_page_ids: pages.map((p) => p.id), expected_quote: quote, kind }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['search-eval-questions', projectId] });
      setQuestion('');
      setQuote('');
      setPages([]);
      setHits(null);
      setFind('');
    },
    onError: (e) => toast.show(messageOf(e), { tone: 'error' }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.del(`${base}/questions/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['search-eval-questions', projectId] }),
    onError: (e) => toast.show(messageOf(e), { tone: 'error' }),
  });
  const run = useMutation({
    mutationFn: () => api.post<Run>(`${base}/runs`, { note }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['search-eval-runs', projectId] });
      setNote('');
    },
    onError: (e) => toast.show(messageOf(e), { tone: 'error' }),
  });
  const search = useMutation({
    mutationFn: () => api.get<Schemas['SearchOut']>(`/projects/${projectId}/search`, { q: find.trim(), limit: 8 }),
    onSuccess: (r) => setHits(r.hits),
    onError: (e) => toast.show(messageOf(e), { tone: 'error' }),
  });

  const qs = questions.data ?? [];
  const [latest, previous] = runs.data ?? [];
  const titleOf = new Map((latest?.per_question ?? []).map((r) => [String(r.id), r]));

  return (
    <section className={s.section} aria-labelledby="search-eval-h">
      <div className={s.sectionHead}>
        <h2 id="search-eval-h" className={s.sectionTitle}>
          {tr.searchEval.title}
        </h2>
      </div>
      <p className={s.hint}>{tr.searchEval.lead}</p>

      <form
        className={s.form}
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim().length >= 2 && pages.length) add.mutate();
        }}
      >
        <Field label={tr.searchEval.question}>{({ id }) => <Input id={id} value={question} onChange={(e) => setQuestion(e.target.value)} autoComplete="off" />}</Field>
        <Field label={tr.searchEval.expected} hint={tr.searchEval.expectedHint}>
          {({ id, describedBy }) => (
            <div className={s.stack}>
              <div className={s.toolbar}>
                <Input id={id} aria-describedby={describedBy} value={find} onChange={(e) => setFind(e.target.value)} autoComplete="off" />
                <Button type="button" icon={<Search size={15} aria-hidden />} loading={search.isPending} disabled={find.trim().length < 2} onClick={() => search.mutate()}>
                  {tr.searchEval.find}
                </Button>
              </div>
              {hits && (
                <ul className={s.rows}>
                  {hits.length === 0 && <li className={s.muted}>{tr.searchEval.findEmpty}</li>}
                  {hits.map((h) => (
                    <li key={h.page_id}>
                      <Button type="button" size="sm" variant="ghost" icon={<Plus size={14} aria-hidden />} onClick={() => setPages((p) => (p.some((x) => x.id === h.page_id) ? p : [...p, { id: h.page_id, title: h.title }]))}>
                        {h.title}
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
              {pages.length > 0 && (
                <ul className={s.rows} aria-label={tr.searchEval.selected}>
                  {pages.map((p) => (
                    <li key={p.id} className={s.toolbar}>
                      <span>{p.title}</span>
                      <IconButton label={tr.searchEval.unselect(p.title)} onClick={() => setPages((x) => x.filter((y) => y.id !== p.id))}>
                        <X size={14} aria-hidden />
                      </IconButton>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </Field>
        <Field label={tr.searchEval.quote} hint={tr.searchEval.quoteHint}>{({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={quote} onChange={(e) => setQuote(e.target.value)} autoComplete="off" />}</Field>
        <Field label={tr.searchEval.kind}>
          {({ id }) => (
            <Select id={id} value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {tr.searchEval.kinds[k]}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <div>
          <Button type="submit" icon={<Plus size={15} aria-hidden />} loading={add.isPending} disabled={question.trim().length < 2 || !pages.length}>
            {tr.searchEval.add}
          </Button>
        </div>
      </form>

      {questions.isLoading ? (
        <SkeletonRows rows={3} />
      ) : (
        <div className={s.tableWrap}>
          <table className={s.table}>
            <caption className="sr-only">{tr.searchEval.questions(qs.length)}</caption>
            <thead>
              <tr>
                <th scope="col">{tr.searchEval.question}</th>
                <th scope="col">{tr.searchEval.kind}</th>
                <th scope="col">{tr.searchEval.rank}</th>
                <th scope="col">
                  <span className="sr-only">{tr.common.delete}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {qs.length === 0 && (
                <tr>
                  <td colSpan={4} className={s.muted}>
                    {tr.searchEval.empty}
                  </td>
                </tr>
              )}
              {qs.map((q) => {
                const r = titleOf.get(q.id);
                return (
                  <tr key={q.id}>
                    <td>{q.question}</td>
                    <td>{tr.searchEval.kinds[q.kind]}</td>
                    <td className={s.mono}>{r ? (typeof r.rank === 'number' ? r.rank : tr.searchEval.notFound) : '—'}</td>
                    <td>
                      <IconButton label={tr.searchEval.remove(q.question)} onClick={() => remove.mutate(q.id)}>
                        <X size={14} aria-hidden />
                      </IconButton>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className={s.toolbar}>
        <Input aria-label={tr.searchEval.note} placeholder={tr.searchEval.note} value={note} onChange={(e) => setNote(e.target.value)} autoComplete="off" />
        <Button variant="primary" icon={<Play size={15} aria-hidden />} loading={run.isPending} disabled={!qs.length} onClick={() => run.mutate()}>
          {tr.searchEval.run}
        </Button>
      </div>

      {latest && (
        <div className={s.tableWrap}>
          <table className={s.table}>
            <caption className="sr-only">{tr.searchEval.results}</caption>
            <thead>
              <tr>
                <th scope="col">{tr.searchEval.metric}</th>
                <th scope="col">
                  {tr.searchEval.latest} · {formatDateTime(latest.created_at)}
                  {latest.note ? ` · ${latest.note}` : ''}
                </th>
                {previous && (
                  <th scope="col">
                    {tr.searchEval.previous} · {formatDateTime(previous.created_at)}
                    {previous.note ? ` · ${previous.note}` : ''}
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">{tr.searchEval.metrics.n}</th>
                <td className={s.mono}>{String(latest.metrics.n ?? 0)}</td>
                {previous && <td className={s.mono}>{String(previous.metrics.n ?? 0)}</td>}
              </tr>
              {METRICS.map((m) => (
                <tr key={m}>
                  <th scope="row">{tr.searchEval.metrics[m]}</th>
                  <td className={s.mono}>{fmt(latest.metrics[m])}</td>
                  {previous && <td className={s.mono}>{fmt(previous.metrics[m])}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
