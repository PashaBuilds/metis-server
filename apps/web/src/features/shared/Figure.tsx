import { useState } from 'react';
import { Dialog } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import { Markdown } from './Markdown';
import s from './shared.module.css';

/** Gövdede görselin yeri: kendi satırında `{{görsel N}}` (N = 1'den başlayan sıra). Sunucudaki desenle aynı. */
export const FIGURE_LINE = /^[ \t]*\{\{\s*görsel\s+(\d+)\s*\}\}[ \t]*$/i;

export const figureToken = (n: number) => `{{görsel ${n}}}`;
export const figureUrl = (sourceRevisionId: string) => `/api/v1/source-revisions/${sourceRevisionId}/download`;

export interface FigureData {
  source_revision_id: string;
  caption: string;
  source_title?: string;
}

/** `{{görsel N}}` satırının sayısı (yoksa null). */
export function figureRef(text: string): number | null {
  const m = FIGURE_LINE.exec(text.trim());
  return m ? Number(m[1]) : null;
}

/** N. görsel kaldırılınca: o satırı siler, sonrakileri bir azaltır. */
export function removeFigureFromBody(body: string, n: number): string {
  const out: string[] = [];
  for (const line of body.split('\n')) {
    const k = figureRef(line);
    if (k === n) continue;
    out.push(k !== null && k > n ? figureToken(k - 1) : line);
  }
  return out.join('\n').replace(/\n{3,}/g, '\n\n');
}

/** Açıklayıcı görsel: kanıt değildir (altın işaret almaz). Tıklayınca büyük hâli açılır. */
export function Figure({ figure, n }: { figure: FigureData; n: number }) {
  const [open, setOpen] = useState(false);
  const label = figure.caption || tr.figures.figureN(n);
  return (
    <figure className={s.figure}>
      <button type="button" className={s.figureBtn} onClick={() => setOpen(true)} aria-label={tr.figures.enlarge(label)}>
        <img src={figureUrl(figure.source_revision_id)} alt={figure.caption || tr.figures.figureN(n)} loading="lazy" />
      </button>
      <figcaption className={s.figcaption}>
        <span className={s.figNo}>{tr.figures.figureN(n)}</span>
        {figure.caption && <span>{figure.caption}</span>}
      </figcaption>
      <Dialog open={open} onOpenChange={setOpen} title={label} width={1100}>
        <img className={s.figureLarge} src={figureUrl(figure.source_revision_id)} alt={figure.caption || tr.figures.figureN(n)} />
        {figure.source_title && <p className={s.figSource}>{tr.figures.source(figure.source_title)}</p>}
      </Dialog>
    </figure>
  );
}

/** Önizleme: Markdown gövdesini görsel satırlarında böler. */
export function BodyWithFigures({ body, figures }: { body: string; figures: FigureData[] }) {
  const parts: { md?: string; n?: number }[] = [];
  let buf: string[] = [];
  for (const line of body.split('\n')) {
    const n = figureRef(line);
    if (n === null) {
      buf.push(line);
      continue;
    }
    if (buf.join('').trim()) parts.push({ md: buf.join('\n') });
    buf = [];
    parts.push({ n });
  }
  if (buf.join('').trim()) parts.push({ md: buf.join('\n') });
  return (
    <>
      {parts.map((p, i) =>
        p.md !== undefined ? <Markdown key={i}>{p.md}</Markdown> : figures[p.n! - 1] ? <Figure key={i} figure={figures[p.n! - 1]!} n={p.n!} /> : <p key={i} className={s.figMissing}>{tr.figures.missing(p.n!)}</p>,
      )}
    </>
  );
}
