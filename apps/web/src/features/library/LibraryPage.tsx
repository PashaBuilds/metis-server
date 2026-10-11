import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useSearch } from '@tanstack/react-router';
import { ChevronLeft, ExternalLink, FolderTree, MessagesSquare, PencilLine, Search, Trash2, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Button, ConfirmDialog, EmptyState, Input, Select, SkeletonRows, StatusBadge } from '@/design/primitives';
import { ScopeChips, useCatalog } from '@/app/ScopeBar';
import type { LibrarySearch } from '@/app/router';
import { useSession } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { formatDateTime } from '@/lib/format';
import { useDebounced } from '@/lib/hooks';
import { EvidenceCount, FRESHNESS, FreshnessBadge, PAGE_KINDS, PageKindIcon } from '@/features/shared/kinds';
import { RowMenu } from '@/features/shared/RowMenu';
import { useUndoableDelete } from '@/features/shared/hooks';
import { asScope } from '@/features/shared/scope';
import { MultiFilter } from './MultiFilter';
import s from './Library.module.css';

const UNSPECIFIED = '__belirlenmemis';
const FILTER_KEYS = ['yatt', 'kart', 'proje', 'kind', 'freshness', 'q'] as const;

function clean(search: LibrarySearch): LibrarySearch {
  const out: LibrarySearch = {};
  if (search.domain) out.domain = search.domain;
  if (search.yatt?.length) out.yatt = search.yatt;
  if (search.kart?.length) out.kart = search.kart;
  if (search.proje?.length) out.proje = search.proje;
  if (search.kind) out.kind = search.kind;
  if (search.freshness) out.freshness = search.freshness;
  if (search.q) out.q = search.q;
  return out;
}

const isEmpty = (search: LibrarySearch) => Object.keys(clean(search)).length === 0;
const hasFilters = (search: LibrarySearch) => FILTER_KEYS.some((k) => (Array.isArray(search[k]) ? (search[k] as string[]).length > 0 : !!search[k]));

export function LibraryPage() {
  const session = useSession();
  const pid = session.projectId;
  const search = useSearch({ from: '/app/bilgi' });
  const navigate = useNavigate({ from: '/bilgi' });
  const catalog = useCatalog(pid);

  /* URL ↔ kullanıcı tercihi: URL boşsa son filtreler geri yüklenir; değişiklikler kaydedilir. */
  const restored = useRef(false);
  const skipSave = useRef(false);
  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    if (isEmpty(search)) {
      const saved = session.pref<LibrarySearch | null>('filters.library', null);
      if (saved && !isEmpty(saved)) {
        skipSave.current = true;
        navigate({ search: clean(saved), replace: true });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const searchKey = JSON.stringify(clean(search));
  useEffect(() => {
    if (!restored.current) return;
    if (skipSave.current) {
      skipSave.current = false;
      return;
    }
    const saved = session.pref<LibrarySearch | null>('filters.library', null);
    if (JSON.stringify(clean(saved ?? {})) !== searchKey) session.setPref('filters.library', JSON.parse(searchKey) as LibrarySearch);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchKey]);

  const setSearch = (patch: Partial<LibrarySearch>) => navigate({ search: (prev) => clean({ ...prev, ...patch }), replace: true });

  const [text, setText] = useState(search.q ?? '');
  const debounced = useDebounced(text, 300);
  useEffect(() => {
    if ((debounced || undefined) !== search.q) setSearch({ q: debounced || undefined });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);
  useEffect(() => {
    setText(search.q ?? '');
  }, [search.q]);

  const filtered = hasFilters(search);
  const showRows = !!search.domain || filtered;
  const domains = useQuery({
    queryKey: ['domains', pid],
    queryFn: () => api.get<Schemas['DomainRow'][]>(`/projects/${pid}/domains`),
    enabled: !!pid,
  });
  const domainLabel = (key: string) => (key === UNSPECIFIED ? tr.scope.unspecified : domains.data?.find((d) => d.key === key)?.label ?? key);

  const clearAll = () => {
    setText('');
    navigate({ search: search.domain ? { domain: search.domain } : {}, replace: true });
  };

  return (
    <div className={s.page}>
      {search.domain ? (
        <div className={s.crumbs}>
          <Link to="/bilgi" search={clean({ ...search, domain: undefined })} className={s.back}>
            <ChevronLeft size={16} aria-hidden />
            {tr.library.allDomains}
          </Link>
          <h1>{domainLabel(search.domain)}</h1>
        </div>
      ) : (
        <h1>{tr.library.title}</h1>
      )}

      <div className={s.filters} role="search" aria-label={tr.library.filters}>
        <div className={s.searchBox}>
          <Search size={16} aria-hidden className={s.searchIcon} />
          <Input
            type="search"
            aria-label={tr.library.searchLabel}
            placeholder={tr.library.searchPlaceholder}
            value={text}
            onChange={(e) => setText(e.target.value)}
            className={s.searchInput}
          />
        </div>
        <div className={s.filterRow}>
          {(['yatt', 'kart', 'proje'] as const).map((d) => (
            <MultiFilter
              key={d}
              label={tr.scope.dims[d]!}
              options={(catalog.data?.[d] ?? []).map((v) => v.value)}
              value={search[d] ?? []}
              onChange={(v) => setSearch({ [d]: v })}
            />
          ))}
          <Select aria-label={tr.library.kind} value={search.kind ?? ''} onChange={(e) => setSearch({ kind: e.target.value || undefined })} className={s.select}>
            <option value="">{tr.library.allKinds}</option>
            {PAGE_KINDS.map((k) => (
              <option key={k} value={k}>
                {tr.pageKinds[k]}
              </option>
            ))}
          </Select>
          <Select aria-label={tr.library.freshness} value={search.freshness ?? ''} onChange={(e) => setSearch({ freshness: e.target.value || undefined })} className={s.select}>
            <option value="">{tr.library.allFreshness}</option>
            {FRESHNESS.map((k) => (
              <option key={k} value={k}>
                {tr.freshness[k]}
              </option>
            ))}
          </Select>
          {filtered && (
            <Button variant="ghost" size="sm" icon={<X size={15} aria-hidden />} onClick={clearAll}>
              {tr.common.clearFilters}
            </Button>
          )}
        </div>
      </div>

      {showRows ? (
        <PageRows search={search} onClear={clearAll} />
      ) : domains.isLoading ? (
        <SkeletonRows rows={4} />
      ) : !domains.data?.length ? (
        <EmptyState icon={<FolderTree size={24} />} title={tr.library.emptyPoolTitle} actions={session.roles.has('contributor') ? <Link to="/katki" className={s.ctaLink}>{tr.library.addFirst}</Link> : undefined}>
          {tr.library.emptyPool}
        </EmptyState>
      ) : (
        <section aria-labelledby="lib-domains">
          <h2 id="lib-domains" className="sr-only">
            {tr.library.domains}
          </h2>
          <ul className={s.rows}>
            {domains.data.map((d) => (
              <li key={d.key} className={s.domainRow}>
                <Link to="/bilgi" search={{ domain: d.key }} className={s.domainLink}>
                  <FolderTree size={18} aria-hidden className={s.domainIcon} />
                  <span className={s.domainName}>{d.key === UNSPECIFIED ? tr.scope.unspecified : d.label}</span>
                </Link>
                <span className={s.domainCount}>{tr.library.pageCount(d.page_count)}</span>
                <span className={s.time}>{d.last_published_at ? tr.library.lastUpdate(formatDateTime(d.last_published_at)) : ''}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function PageRows({ search, onClear }: { search: LibrarySearch; onClear: () => void }) {
  const session = useSession();
  const pid = session.projectId;
  const qc = useQueryClient();
  const navigate = useNavigate();
  const undoableDelete = useUndoableDelete();
  const [confirm, setConfirm] = useState<Schemas['PageRow'] | null>(null);
  const query = useInfiniteQuery({
    queryKey: ['pages', pid, 'list', clean(search)],
    queryFn: ({ pageParam }) =>
      api.get<Schemas['PageListOut']>(`/projects/${pid}/pages`, {
        domain: search.domain,
        yatt: search.yatt,
        kart: search.kart,
        proje: search.proje,
        kind: search.kind,
        freshness: search.freshness,
        q: search.q,
        cursor: pageParam ?? undefined,
        limit: 50,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled: !!pid,
  });
  const canDelete = session.roles.has('reviewer') || session.roles.has('steward');
  const canContribute = session.roles.has('contributor');
  const rows = query.data?.pages.flatMap((p) => p.items) ?? [];
  const total = query.data?.pages[0]?.total ?? 0;
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['pages', pid] });
    qc.invalidateQueries({ queryKey: ['domains', pid] });
  };

  if (query.isLoading) return <SkeletonRows rows={6} />;
  if (query.isError)
    return (
      <EmptyState title={tr.shared.loadError} actions={<Button onClick={() => query.refetch()}>{tr.common.retry}</Button>} />
    );
  if (rows.length === 0)
    return (
      <EmptyState
        icon={<Search size={24} />}
        title={tr.library.emptyFilteredTitle}
        actions={
          <>
            <Button onClick={onClear}>{tr.common.clearFilters}</Button>
            {canContribute && (
              <Link to="/katki" className={s.ctaLink}>
                {tr.library.addFirst}
              </Link>
            )}
          </>
        }
      >
        {tr.library.emptyFiltered}
      </EmptyState>
    );

  return (
    <section aria-label={tr.library.total(total)} className={s.results}>
      <p className={s.total} aria-live="polite">
        {tr.library.total(total)}
      </p>
      <ul className={s.rows}>
        {rows.map((p) => (
          <li key={p.page_id} className={s.pageRow}>
            <PageKindIcon kind={p.kind} size={18} />
            <div className={s.pageMain}>
              <Link to="/bilgi/$pageId" params={{ pageId: p.page_id }} search={{}} className={s.pageTitle}>
                {p.title}
              </Link>
              {p.summary && <p className={s.summary}>{p.summary}</p>}
              <div className={s.pageMeta}>
                <span className={s.kindText}>{tr.pageKinds[p.kind] ?? p.kind}</span>
                <ScopeChips scope={{ ...asScope(p.scope), domain: search.domain ? [] : asScope(p.scope).domain }} />
              </div>
            </div>
            <div className={s.pageSide}>
              {p.lifecycle === 'withdrawn' ? <StatusBadge tone="celiski" label={tr.shared.withdrawnBadge} size="sm" /> : <FreshnessBadge freshness={p.freshness} size="sm" />}
              <EvidenceCount n={p.evidence_count} />
              <time className={s.time} dateTime={p.published_at ?? undefined} title={tr.shared.publishedAt}>
                {formatDateTime(p.published_at)}
              </time>
            </div>
            <RowMenu
              label={tr.shared.rowMenu(p.title)}
              actions={[
                { label: tr.common.open, icon: <ExternalLink size={15} />, onSelect: () => navigate({ to: '/bilgi/$pageId', params: { pageId: p.page_id }, search: {} }) },
                { label: tr.shared.askMentor, icon: <MessagesSquare size={15} />, onSelect: () => navigate({ to: '/mentor', search: { q: p.title } }) },
                ...(canContribute ? [{ label: tr.shared.suggestEdit, icon: <PencilLine size={15} />, onSelect: () => navigate({ to: '/katki', search: { page: p.page_id } }) }] : []),
                ...(canDelete ? [{ label: tr.common.delete, icon: <Trash2 size={15} />, danger: true, separatorBefore: true, onSelect: () => setConfirm(p) }] : []),
              ]}
            />
          </li>
        ))}
      </ul>
      {query.hasNextPage && (
        <div className={s.moreRow}>
          <Button onClick={() => query.fetchNextPage()} loading={query.isFetchingNextPage}>
            {tr.library.loadMore}
          </Button>
        </div>
      )}
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={tr.shared.deletePageTitle}
        description={confirm ? `${confirm.title}. ${tr.shared.deletePageDesc}` : ''}
        confirmLabel={tr.common.delete}
        danger
        onConfirm={async () => {
          const page = confirm;
          if (!page) return;
          await undoableDelete({
            del: () => api.del(`/pages/${page.page_id}`),
            restore: () => api.post(`/pages/${page.page_id}/restore`),
            onDone: invalidate,
            onRestored: invalidate,
          }).catch(() => undefined);
        }}
      />
    </section>
  );
}
