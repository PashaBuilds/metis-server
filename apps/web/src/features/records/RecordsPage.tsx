import { useQuery } from '@tanstack/react-query';
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router';
import { ClipboardList } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { Button, EmptyState, Segmented, SkeletonRows, TabPanel, Tabs } from '@/design/primitives';
import { PageHeader } from '@/app/Shell';
import { useSession } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { formatWhen } from '@/lib/format';
import { ChangeStateBadge, OriginBadge } from '@/features/shared/kinds';
import { messageOf } from '@/features/shared/hooks';
import s from './Records.module.css';

const route = getRouteApi('/app/kayitlar');
const TABS = ['review', 'drafts', 'published'] as const;
type Tab = (typeof TABS)[number];
type Origin = 'all' | 'human' | 'metis';
interface RecordsPref {
  tab?: string;
  origin?: string;
}

const asTab = (v: string | undefined): Tab | undefined => (TABS as readonly string[]).includes(v ?? '') ? (v as Tab) : undefined;
const asOrigin = (v: string | undefined): Origin => (v === 'human' || v === 'metis' ? v : 'all');

export function RecordsPage() {
  const session = useSession();
  const pid = session.projectId;
  const search = route.useSearch();
  const navigate = useNavigate({ from: '/kayitlar' });
  const isReviewer = session.roles.has('reviewer');
  const tab: Tab = asTab(search.tab) ?? (isReviewer ? 'review' : 'drafts');
  const origin = asOrigin(search.origin);

  /* URL boşsa son seçim tercihten gelir; URL'deki her değişiklik tercihe yazılır. */
  const restored = useRef(false);
  const skipSave = useRef(false);
  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    if (!search.tab && !search.origin) {
      const saved = session.pref<RecordsPref | null>('filters.records', null);
      if (saved && (saved.tab || saved.origin)) {
        skipSave.current = true;
        navigate({ search: { tab: asTab(saved.tab), origin: saved.origin === 'all' ? undefined : saved.origin }, replace: true });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (skipSave.current) {
      skipSave.current = false;
      return;
    }
    if (!search.tab && !search.origin) return;
    const saved = session.pref<RecordsPref | null>('filters.records', null);
    if (saved?.tab !== tab || (saved?.origin ?? 'all') !== origin) session.setPref('filters.records', { tab, origin });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, origin, search.tab, search.origin]);
  const setFilters = (next: { tab: Tab; origin: Origin }) => navigate({ search: { tab: next.tab, origin: next.origin === 'all' ? undefined : next.origin }, replace: true });

  const query = useQuery({
    queryKey: ['changes', pid, tab, origin],
    queryFn: () => api.get<Schemas['ChangeListOut']>(`/projects/${pid}/changes`, { tab, origin: origin === 'all' ? undefined : origin }),
    enabled: !!pid,
  });
  const counts = query.data?.counts ?? {};

  return (
    <div className={s.page}>
      <PageHeader title={tr.records.title} />
      <Tabs
        label={tr.records.title}
        value={tab}
        onValueChange={(v) => setFilters({ tab: asTab(v) ?? 'drafts', origin })}
        tabs={TABS.map((t) => ({ value: t, label: tr.records.tabs[t], count: counts[t] ?? null }))}
      >
        {TABS.map((t) => (
          <TabPanel key={t} value={t}>
            <div className={s.toolbar}>
              <span className={s.toolLabel} id="origin-label">
                {tr.records.origin}
              </span>
              <Segmented<Origin>
                label={tr.records.origin}
                value={origin}
                onChange={(o) => setFilters({ tab, origin: o })}
                options={[
                  { value: 'all', label: tr.records.originAll },
                  { value: 'human', label: tr.records.originHuman },
                  { value: 'metis', label: tr.records.originMetis },
                ]}
              />
            </div>
            {t !== tab ? null : query.isLoading ? (
              <SkeletonRows rows={5} />
            ) : query.isError ? (
              <EmptyState title={tr.shared.loadError} actions={<Button onClick={() => query.refetch()}>{tr.common.retry}</Button>}>
                {messageOf(query.error)}
              </EmptyState>
            ) : !query.data?.items.length ? (
              <EmptyState
                icon={<ClipboardList size={24} />}
                title={tr.records.empty[t]!}
                actions={
                  t === 'drafts' && session.roles.has('contributor') ? (
                    <Link to="/katki" className={s.ctaLink}>
                      {tr.nav.newContribution}
                    </Link>
                  ) : undefined
                }
              />
            ) : (
              <ul className={s.rows}>
                {query.data.items.map((c) => (
                  <li key={c.id} className={s.row}>
                    <div className={s.main}>
                      <Link to="/kayitlar/$changeId" params={{ changeId: c.id }} className={s.title}>
                        {c.title}
                      </Link>
                      <div className={s.meta}>
                        <OriginBadge origin={c.origin} />
                        <span className={s.people}>
                          {tr.records.by(c.author_name)}
                          {c.origin === 'metis' && c.requester_name ? <span>{tr.records.requestedBy(c.requester_name)}</span> : null}
                        </span>
                      </div>
                    </div>
                    <div className={s.side}>
                      <ChangeStateBadge state={c.state} size="sm" />
                      <time className={s.time} dateTime={c.updated_at} title={tr.records.updated}>
                        {formatWhen(c.updated_at)}
                      </time>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </TabPanel>
        ))}
      </Tabs>
    </div>
  );
}
