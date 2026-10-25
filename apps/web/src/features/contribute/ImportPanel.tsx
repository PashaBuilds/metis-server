import { useMutation, useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { Download, Search } from 'lucide-react';
import { useState } from 'react';
import { Button, Field, Input, Select } from '@/design/primitives';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { Banner } from '@/features/shared/Banner';
import { Markdown } from '@/features/shared/Markdown';
import s from './Contribute.module.css';

type Conn = Schemas['ConnectionOut'];
export type Preview = Schemas['PreviewOut'];
type Hit = Schemas['SearchItemOut'];

interface Props {
  projectId: string;
  /** Önizleme taslağa çevrilir. `pageId` doluysa var olan bilginin güncelleme taslağı. */
  onUse: (preview: Preview, pageId: string | null) => void;
}

/** Yeni katkı → Kaynaktan al: Confluence sayfası ya da GitLab issue'su bağlantıdan veya aramadan önizlenir. */
export function ImportPanel({ projectId, onUse }: Props) {
  const conns = useQuery({ queryKey: ['external-connections'], queryFn: () => api.get<Conn[]>('/external/connections') });
  const [connId, setConnId] = useState('');
  const [url, setUrl] = useState('');
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [pv, setPv] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const active = conns.data?.find((c) => c.id === connId) ?? conns.data?.[0];

  const fail = (e: unknown) => setError(errorMessage(e instanceof ApiError ? e.code : 'NETWORK'));
  const preview = useMutation({
    mutationFn: (target: string) => api.post<Preview>(`/projects/${projectId}/external/preview`, { connection_id: active?.id, url: target }),
    onMutate: () => (setError(null), setPv(null)),
    onSuccess: setPv,
    onError: fail,
  });
  const search = useMutation({
    mutationFn: () => api.get<Hit[]>(`/projects/${projectId}/external/search`, { connection_id: active?.id ?? '', q: q.trim() }),
    onMutate: () => (setError(null), setHits(null)),
    onSuccess: setHits,
    onError: fail,
  });

  if (conns.isLoading) return null;
  const list = conns.data ?? [];
  return (
    <details className={s.moreFields}>
      <summary>{tr.external.importTitle}</summary>
      <div className={s.moreBody}>
        <p className={s.hint}>{tr.external.importLead}</p>
        {list.length === 0 ? (
          <p className={s.muted}>{tr.external.noConnections}</p>
        ) : (
          <>
            {list.length > 1 && (
              <Field label={tr.external.connection}>
                {({ id }) => (
                  <Select id={id} value={active?.id ?? ''} onChange={(e) => (setConnId(e.target.value), setHits(null), setPv(null))}>
                    {list.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({tr.external.kinds[c.kind]})
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            )}
            <form
              className={s.formRow}
              onSubmit={(e) => {
                e.preventDefault();
                if (url.trim()) preview.mutate(url.trim());
              }}
            >
              <Field label={tr.external.url} hint={tr.external.urlHint}>
                {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={url} onChange={(e) => setUrl(e.target.value)} spellCheck={false} autoComplete="off" />}
              </Field>
              <div>
                <Button type="submit" icon={<Download size={15} aria-hidden />} loading={preview.isPending} disabled={!url.trim()}>
                  {tr.external.previewBtn}
                </Button>
              </div>
            </form>
            <form
              className={s.formRow}
              onSubmit={(e) => {
                e.preventDefault();
                if (q.trim().length >= 2) search.mutate();
              }}
            >
              <Field label={tr.external.searchLabel}>{({ id }) => <Input id={id} value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" />}</Field>
              <div>
                <Button type="submit" icon={<Search size={15} aria-hidden />} loading={search.isPending} disabled={q.trim().length < 2}>
                  {tr.external.searchBtn}
                </Button>
              </div>
            </form>
            {hits && (
              <ul className={s.sourceList} aria-label={tr.external.searchLabel}>
                {hits.length === 0 && <li className={s.muted}>{tr.external.searchEmpty}</li>}
                {hits.map((h) => (
                  <li key={h.url}>
                    <button type="button" className={s.sourceRow} onClick={() => (setUrl(h.url), preview.mutate(h.url))}>
                      <span className={s.sourceRowTitle}>{h.title}</span>
                      <span className={s.sourceRowMeta}>{h.container}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        {error && <Banner tone="celiski">{error}</Banner>}
        {pv && (
          <section aria-labelledby="import-pv-h" className={s.panel}>
            <h3 id="import-pv-h" className={s.subTitle}>
              {tr.external.previewTitle}: {pv.title}
            </h3>
            <p className={s.hint}>
              {tr.external.kinds[pv.kind]} · {pv.origin.url} · {tr.external.attachmentsN(pv.attachments.length)}
            </p>
            {pv.skipped.length > 0 && (
              <div>
                <p className={s.label}>{tr.external.skippedTitle}</p>
                <ul className={s.hint}>
                  {pv.skipped.map((k, i) => (
                    <li key={`${k.name}-${i}`}>
                      {k.name} — {tr.external.skippedReasons[k.reason] ?? k.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className={s.preview}>
              <Markdown>{pv.body_md}</Markdown>
            </div>
            {pv.existing_page_id ? (
              <Banner
                tone="dikkat"
                actions={
                  <>
                    <Link to="/bilgi/$pageId" params={{ pageId: pv.existing_page_id }} search={{}}>
                      {tr.external.openExisting}
                    </Link>
                    <Button size="sm" onClick={() => onUse(pv, pv.existing_page_id ?? null)}>
                      {tr.external.updateDraft}
                    </Button>
                  </>
                }
              >
                {tr.external.existing(pv.existing_title ?? pv.title)}
                {pv.edited_since_import && ` ${tr.external.editedWarning}`}
              </Banner>
            ) : (
              <div>
                <Button variant="primary" onClick={() => onUse(pv, null)}>
                  {tr.external.toDraft}
                </Button>
              </div>
            )}
          </section>
        )}
      </div>
    </details>
  );
}
