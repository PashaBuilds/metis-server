import { useMutation, useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from '@tanstack/react-router';
import { Activity, ArrowRight, ClipboardList, CornerDownLeft, FilePlus2, Plus, Sparkles } from 'lucide-react';
import { useId, useState, type FormEvent } from 'react';
import { Button, Chip, ChipButton, SkeletonRows, useToast } from '@/design/primitives';
import { DIMS } from '@/app/ScopeBar';
import { useSession } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { formatDateTime, formatWhen } from '@/lib/format';
import { ChangeStateBadge, EvidenceCount, PageKindIcon } from '@/features/shared/kinds';
import { messageOf, useInbox } from '@/features/shared/hooks';
import { ModelSelect, useAvailableModels } from '@/features/shared/models';
import s from './Home.module.css';

export function HomePage() {
  const session = useSession();
  const pid = session.projectId;
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const inbox = useInbox(pid);
  const models = useAvailableModels(pid);
  const modelFieldId = useId();
  const savedModel = session.pref<string | null>('mentor_model_id', null);
  const modelList = models.data ?? [];
  // Kayıtlı seçim uygun olmasa bile korunur; mentor nedenini yazar ve alternatif önerir (sessiz geçiş yok).
  const modelId = savedModel && modelList.some((m) => m.id === savedModel) ? savedModel : '';
  const pages = useQuery({
    queryKey: ['pages', pid, 'recent'],
    queryFn: () => api.get<Schemas['PageListOut']>(`/projects/${pid}/pages`, { limit: 6 }),
    enabled: !!pid,
  });
  const drafts = useQuery({
    queryKey: ['changes', pid, 'drafts', 'all'],
    queryFn: () => api.get<Schemas['ChangeListOut']>(`/projects/${pid}/changes`, { tab: 'drafts' }),
    enabled: !!pid && session.roles.has('contributor'),
  });

  const meId = session.me?.user.id;
  const myDrafts = (drafts.data?.items ?? []).filter((c) => c.author_id === meId || c.requester_id === meId).slice(0, 5);
  const waiting = (inbox.data?.reviews_waiting ?? 0) + (inbox.data?.questions_waiting ?? 0);
  const emptyPool = pages.data?.total === 0;

  function ask(e: FormEvent) {
    e.preventDefault();
    const text = q.trim();
    if (!text) return;
    navigate({ to: '/mentor', search: { q: text, model: modelId || undefined } });
  }

  const scope = session.scope;
  const chips = DIMS.flatMap((d) => scope[d].map((v) => ({ d, v })));

  return (
    <div className={s.page}>
      <form className={s.ask} onSubmit={ask} role="search">
        <h1 className={s.askLabel}>
          <label htmlFor="home-question">{tr.home.questionLabel}</label>
        </h1>
        <div className={s.askField}>
          <input
            id="home-question"
            className={s.askInput}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={tr.home.questionPlaceholder}
            autoComplete="off"
            enterKeyHint="send"
          />
          <button type="submit" className={s.askSubmit} aria-label={tr.home.ask} title={tr.home.ask} disabled={!q.trim()}>
            <CornerDownLeft size={20} aria-hidden />
          </button>
        </div>
        <div className={s.scopeRow}>
          <span className={s.scopeLabel}>{tr.home.scope}</span>
          {chips.length === 0 && <span className={s.scopeAll}>{tr.scope.all}</span>}
          {chips.map(({ d, v }) => (
            <Chip key={d + v} label={tr.scope.dims[d]} onRemove={() => session.setScope({ ...scope, [d]: scope[d].filter((x) => x !== v) })}>
              {v === '*' ? tr.scope.independent : v}
            </Chip>
          ))}
          <ChipButton onClick={() => window.dispatchEvent(new CustomEvent('metis:open-scope'))} aria-label={tr.scope.pick}>
            <Plus size={14} aria-hidden />
            {tr.scope.add}
          </ChipButton>
          {modelList.length > 0 && (
            <span className={s.modelBox}>
              <label htmlFor={modelFieldId} className={s.scopeLabel}>
                {tr.models.label}
              </label>
              <ModelSelect
                id={modelFieldId}
                className={s.modelSelect}
                value={modelId}
                onChange={(v) => session.setPref('mentor_model_id', v || null)}
                models={modelList}
                emptyLabel={tr.models.auto}
              />
            </span>
          )}
        </div>
      </form>

      <div className={[s.grid, waiting > 0 || !!inbox.data?.open_findings ? '' : s.gridSingle].join(' ')}>
        <div className={s.mainCol}>
          {session.roles.has('contributor') && !(emptyPool && myDrafts.length === 0) && (
            <section className={s.section} aria-labelledby="home-resume">
              <div className={s.sectionHead}>
                <h2 id="home-resume">{tr.home.resume}</h2>
                {myDrafts.length > 0 && (
                  <Link to="/kayitlar" search={{ tab: 'drafts' }} className={s.more}>
                    {tr.home.allRecords}
                  </Link>
                )}
              </div>
              {drafts.isLoading ? (
                <SkeletonRows rows={3} />
              ) : myDrafts.length === 0 ? (
                <p className={s.emptyLine}>
                  {tr.home.resumeEmpty}{' '}
                  <Link to="/katki" className={s.inlineLink}>
                    {tr.nav.newContribution}
                  </Link>
                </p>
              ) : (
                <ul className={s.rows}>
                  {myDrafts.map((c) => (
                    <li key={c.id} className={s.row}>
                      <Link to="/kayitlar/$changeId" params={{ changeId: c.id }} className={s.rowLink}>
                        <span className={s.rowTitle}>{c.title}</span>
                      </Link>
                      <span className={s.rowMeta}>
                        <ChangeStateBadge state={c.state} size="sm" />
                        <time className={s.time} dateTime={c.updated_at}>
                          {formatWhen(c.updated_at)}
                        </time>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {emptyPool ? (
            <FirstSteps />
          ) : (
            <section className={s.section} aria-labelledby="home-recent">
              <div className={s.sectionHead}>
                <h2 id="home-recent">{tr.home.recent}</h2>
                <Link to="/bilgi" className={s.more}>
                  {tr.home.seeAll}
                </Link>
              </div>
              {pages.isLoading ? (
                <SkeletonRows rows={4} />
              ) : pages.isError ? (
                <p className={s.emptyLine}>{tr.shared.loadError}</p>
              ) : (
                <ul className={s.rows}>
                  {pages.data?.items.map((p) => (
                    <li key={p.page_id} className={[s.row, s.pageRow].join(' ')}>
                      <PageKindIcon kind={p.kind} />
                      <div className={s.pageText}>
                        <Link to="/bilgi/$pageId" params={{ pageId: p.page_id }} search={{}} className={s.rowLink}>
                          <span className={s.rowTitle}>{p.title}</span>
                        </Link>
                        {p.summary && <p className={s.summary}>{p.summary}</p>}
                      </div>
                      <span className={s.rowMeta}>
                        <EvidenceCount n={p.evidence_count} />
                        <time className={s.time} dateTime={p.published_at ?? undefined} title={tr.shared.publishedAt}>
                          {formatDateTime(p.published_at)}
                        </time>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </div>

        <aside className={s.sideCol} aria-label={tr.home.waiting}>
          {waiting > 0 && (
            <section className={s.section} aria-labelledby="home-waiting">
              <h2 id="home-waiting">{tr.home.waiting}</h2>
              <ul className={s.waitList}>
                {!!inbox.data?.reviews_waiting && (
                  <li>
                    <Link to="/kayitlar" search={{ tab: 'review' }} className={s.waitItem}>
                      <ClipboardList size={18} aria-hidden />
                      <span>{tr.home.reviewsWaiting(inbox.data.reviews_waiting)}</span>
                      <ArrowRight size={16} aria-hidden className={s.waitArrow} />
                    </Link>
                  </li>
                )}
                {!!inbox.data?.questions_waiting && (
                  <li>
                    <Link to="/gorevler" className={s.waitItem}>
                      <Sparkles size={18} aria-hidden />
                      <span>{tr.home.questionsWaiting(inbox.data.questions_waiting)}</span>
                      <ArrowRight size={16} aria-hidden className={s.waitArrow} />
                    </Link>
                  </li>
                )}
              </ul>
            </section>
          )}
          {!!inbox.data?.open_findings && (
            <Link to="/saglik" className={s.healthLine}>
              <Activity size={16} aria-hidden />
              <span>{tr.home.health(inbox.data.open_findings)}</span>
            </Link>
          )}
        </aside>
      </div>
    </div>
  );
}

function FirstSteps() {
  const session = useSession();
  const toast = useToast();
  const canContribute = session.roles.has('contributor');
  const canDemo = session.me?.profile === 'development' && session.isAdmin;
  const demo = useMutation({
    mutationFn: () => api.post<{ project_id: string; created: boolean }>('/demo'),
    onSuccess: async (res) => {
      await session.refresh();
      session.setProject(res.project_id);
      toast.show(tr.home.demoDone);
    },
    onError: (e) => toast.show(messageOf(e), { tone: 'error' }),
  });
  return (
    <section className={[s.section, s.first].join(' ')} aria-labelledby="home-first">
      <h2 id="home-first">{tr.home.firstTitle}</h2>
      {canContribute ? (
        <>
          <p className={s.firstLead}>{tr.home.firstLead}</p>
          <ol className={s.steps}>
            {tr.home.steps.map((step, i) => (
              <li key={step.title} className={s.step}>
                <span className={s.stepNo} aria-hidden>
                  {i + 1}
                </span>
                <div>
                  <h3 className={s.stepTitle}>{step.title}</h3>
                  <p className={s.stepText}>{step.text}</p>
                </div>
              </li>
            ))}
          </ol>
          <div className={s.firstActions}>
            <Link to="/katki" className={s.primaryLink}>
              <FilePlus2 size={16} aria-hidden />
              {tr.home.startCta}
            </Link>
            {canDemo && (
              <Button variant="secondary" onClick={() => demo.mutate()} loading={demo.isPending}>
                {tr.home.demoCta}
              </Button>
            )}
          </div>
          {canDemo && <p className={s.demoHint}>{tr.home.demoHint}</p>}
        </>
      ) : (
        <p className={s.firstLead}>{tr.home.readerEmpty}</p>
      )}
    </section>
  );
}
