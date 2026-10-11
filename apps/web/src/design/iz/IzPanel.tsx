import { useQuery } from '@tanstack/react-query';
import { ChevronRight, Download, FilePlus2, LocateFixed, X } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { Link } from '@tanstack/react-router';
import { Button, IconButton } from '../primitives';
import { tr, sourceKindLabel } from '@/i18n/tr';
import { formatDateTime } from '@/lib/format';
import { useIz } from './IzContext';
import { SourceKindIcon } from './SourceKindIcon';
import s from './Iz.module.css';

const WINDOW = 4000;

/** Sağdaki İz paneli: kaynağın doğru revizyonunu açar, alıntıyı vurgular ve oraya kaydırır. */
export function IzPanel({ mode }: { mode: 'docked' | 'overlay' }) {
  const iz = useIz();
  const active = iz.active;
  const headingRef = useRef<HTMLHeadingElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const query = useQuery({
    queryKey: ['evidence', active?.evidenceId, active?.claimId ?? null],
    queryFn: () => iz.resolver!(active!),
    enabled: !!active && !!iz.resolver,
    retry: false,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!active) return;
    headingRef.current?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        iz.close();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [active, iz]);

  useEffect(() => {
    if (query.data) scrollToMark();
  }, [query.data]);

  function scrollToMark() {
    const mark = bodyRef.current?.querySelector<HTMLElement>('[data-iz-target]');
    if (mark && bodyRef.current) {
      const top = mark.offsetTop - bodyRef.current.clientHeight / 3;
      bodyRef.current.scrollTo({ top: Math.max(0, top), behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    }
  }

  if (!active) return null;
  const data = query.data;
  return (
    <>
      {mode === 'overlay' && <div className={s.panelScrim} onClick={iz.close} aria-hidden />}
      <aside id="iz-panel" className={[s.panel, s[mode]].join(' ')} aria-labelledby="iz-panel-title" data-iz-panel>
        <div className={s.panelHead}>
          <div className={s.panelKind}>
            {data ? (
              <>
                <SourceKindIcon kind={data.source.kind} />
                <span>{sourceKindLabel(data.source.kind)}</span>
              </>
            ) : (
              <span>{tr.iz.source}</span>
            )}
          </div>
          <IconButton label={tr.iz.close} size="sm" onClick={iz.close}>
            <X size={18} aria-hidden />
          </IconButton>
        </div>
        <h2 id="iz-panel-title" ref={headingRef} tabIndex={-1} className={s.panelTitle}>
          {data?.source.title ?? active.label ?? tr.iz.loading}
        </h2>
        {query.isError && <p className={s.panelError}>{tr.iz.unavailable}</p>}
        {data && (
          <>
            <dl className={s.meta}>
              <div>
                <dt>{tr.iz.revision}</dt>
                <dd className="tabular">
                  {data.revision.number}. sürüm{!data.revision.is_current && <span className={s.oldRev}> · {tr.iz.notCurrent}</span>}
                </dd>
              </div>
              <div>
                <dt>{tr.iz.date}</dt>
                <dd className="tabular">{formatDateTime(data.revision.created_at)}</dd>
              </div>
              {data.revision.author_name && (
                <div>
                  <dt>{tr.iz.author}</dt>
                  <dd>{data.revision.author_name}</dd>
                </div>
              )}
              <div>
                <dt>{tr.iz.location}</dt>
                <dd className={s.locator}>{data.locator_label}</dd>
              </div>
            </dl>
            <div className={s.panelActions}>
              <Button size="sm" variant="secondary" icon={<LocateFixed size={15} aria-hidden />} onClick={scrollToMark} disabled={!data.highlight}>
                {tr.iz.goToHighlight}
              </Button>
              {data.can_download && (
                <a className={s.linkButton} href={`/api/v1/source-revisions/${data.revision.id}/download`} download>
                  <Download size={15} aria-hidden />
                  {tr.iz.download}
                </a>
              )}
              <Link className={s.linkButton} to="/katki" search={{ source: data.source.id }}>
                <FilePlus2 size={15} aria-hidden />
                {tr.iz.newRevision}
              </Link>
            </div>
            <div ref={bodyRef} className={s.sourceText} tabIndex={0} aria-label={tr.iz.fullText}>
              <SourceText text={data.text} highlight={data.highlight} />
            </div>
            <details className={s.tech}>
              <summary>
                <ChevronRight size={14} aria-hidden className={s.techChevron} />
                {tr.common.technicalDetails}
              </summary>
              <dl className={s.techList}>
                <dt>SHA-256</dt>
                <dd className="mono">{data.revision.sha256}</dd>
                <dt>Dosya</dt>
                <dd className="mono">{data.revision.filename}</dd>
                <dt>Tür</dt>
                <dd className="mono">{data.revision.media_type}</dd>
                <dt>Çıkarım</dt>
                <dd>{data.revision.extraction}</dd>
                <dt>Kanıt</dt>
                <dd className="mono">{data.evidence_id}</dd>
              </dl>
            </details>
          </>
        )}
      </aside>
    </>
  );
}

function SourceText({ text, highlight }: { text: string; highlight: { start: number; end: number } | null }) {
  if (!highlight) return <pre className={s.pre}>{text.length > WINDOW * 2 ? text.slice(0, WINDOW * 2) + '\n…' : text}</pre>;
  const from = Math.max(0, highlight.start - WINDOW);
  const to = Math.min(text.length, highlight.end + WINDOW);
  return (
    <pre className={s.pre}>
      {from > 0 && '…\n'}
      {text.slice(from, highlight.start)}
      <mark data-iz-target>{text.slice(highlight.start, highlight.end)}</mark>
      {text.slice(highlight.end, to)}
      {to < text.length && '\n…'}
    </pre>
  );
}
