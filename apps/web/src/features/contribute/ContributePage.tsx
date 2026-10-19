import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getRouteApi, Link, useBlocker, useNavigate } from '@tanstack/react-router';
import { useRef, useState } from 'react';
import { Button, Dialog, EmptyState, SkeletonRows } from '@/design/primitives';
import { PageHeader } from '@/app/Shell';
import { EMPTY_SCOPE } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { useUnsavedWarning } from '@/lib/hooks';
import { Banner } from '@/features/shared/Banner';
import { messageOf } from '@/features/shared/hooks';
import { asScope } from '@/features/shared/scope';
import { NoteEditor, type NoteTarget, type NoteValues } from './NoteEditor';
import s from './Contribute.module.css';

const route = getRouteApi('/app/katki');

type RevisionView = Schemas['RevisionView'];

/** Yayımlanmış ya da taslak revizyondan editör değerleri. Not = gövde; ekler korunur. */
function valuesFromRevision(r: RevisionView): NoteValues {
  return {
    title: r.title,
    kind: r.kind,
    summary: r.summary,
    body_md: r.body_md,
    scope: asScope(r.scope),
    unknowns: r.unknowns.filter((u): u is string => typeof u === 'string'),
    aliases: r.aliases.filter((u): u is string => typeof u === 'string'),
    attachments: r.attachments ?? [],
  };
}

const EMPTY_VALUES: NoteValues = { title: '', kind: 'concept', summary: '', body_md: '', scope: EMPTY_SCOPE, unknowns: [], aliases: [], attachments: [] };

/** Tek adımda taslak hazırla (2026-10-19): ayrı kaynak adımı yok; taslağın notu bilginin dayanağıdır. */
export function ContributePage() {
  const search = route.useSearch();
  const navigate = useNavigate();
  const qc = useQueryClient();

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

  const dirtyRef = useRef(false);
  const allowNav = useRef(false);
  const [dirty, setDirtyState] = useState(false);
  const setDirty = (d: boolean) => {
    dirtyRef.current = d;
    setDirtyState(d);
  };
  useUnsavedWarning(dirty);
  const blocker = useBlocker({ shouldBlockFn: () => !allowNav.current && dirtyRef.current, withResolver: true });
  const go = (fn: () => void) => {
    allowNav.current = true;
    fn();
  };

  let initial: NoteValues | null = EMPTY_VALUES;
  let target: NoteTarget = { pageId: null, baseRevisionId: null, changeId: null, changeHash: null, changeSummary: '' };
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
  }
  const loadError = (search.change && change.isError && change.error) || (search.page && !search.change && page.isError && page.error);
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
          {notice && <Banner tone="bilgi">{notice}</Banner>}
          {initial ? (
            <NoteEditor
              key={target.changeId ?? target.pageId ?? 'new'}
              initial={initial}
              target={target}
              onDirty={setDirty}
              onSaved={(id) => go(() => navigate({ to: '/kayitlar/$changeId', params: { changeId: id } }))}
              onPublished={(d) => {
                const pageId = d.published_page_ids[0];
                go(() => (pageId ? navigate({ to: '/bilgi/$pageId', params: { pageId }, search: {} }) : navigate({ to: '/kayitlar/$changeId', params: { changeId: d.id } })));
              }}
              onReopen={(id) => {
                // Aynı sayfada kalınır: kaydedilmiş taslak (güncel hash ile) editörde yeniden açılır.
                void qc.invalidateQueries({ queryKey: ['change', id] });
                allowNav.current = true;
                void navigate({ to: '/katki', search: { change: id } }).finally(() => {
                  allowNav.current = false;
                });
              }}
            />
          ) : (
            <SkeletonRows rows={5} />
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
