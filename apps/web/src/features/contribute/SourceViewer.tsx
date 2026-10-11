import { Link2 } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { tr } from '@/i18n/tr';
import s from './Contribute.module.css';

interface Selection {
  /** UTF-16 ofsetleri (JS) */
  start: number;
  end: number;
  top: number;
  left: number;
}

/** JS (UTF-16) ofsetini Python kod noktası ofsetine çevirir. */
export function toCodePoints(text: string, offset: number): number {
  return Array.from(text.slice(0, offset)).length;
}

function offsetWithin(root: Node, node: Node, offset: number): number {
  const range = document.createRange();
  range.setStart(root, 0);
  range.setEnd(node, offset);
  return range.toString().length;
}

/**
 * Kaynak metni görüntüleyici: seçim → yüzen "Bu alıntıyı iddiaya bağla" düğmesi.
 * Ofsetler kaynağın tam metnine göre hesaplanır; bağlı alıntılar altınla işaretlenir (kanıt).
 */
export function SourceViewer({ text, linked, onLink, busy }: { text: string; linked: { start: number; end: number }[]; onLink: (start: number, end: number) => void; busy: boolean }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const preRef = useRef<HTMLPreElement>(null);
  const [sel, setSel] = useState<Selection | null>(null);

  const read = useCallback(() => {
    const pre = preRef.current;
    const box = boxRef.current;
    const selection = window.getSelection();
    if (!pre || !box || !selection || selection.rangeCount === 0 || selection.isCollapsed) {
      setSel(null);
      return;
    }
    const range = selection.getRangeAt(0);
    if (!pre.contains(range.startContainer) || !pre.contains(range.endContainer)) {
      setSel(null);
      return;
    }
    let start = offsetWithin(pre, range.startContainer, range.startOffset);
    let end = offsetWithin(pre, range.endContainer, range.endOffset);
    while (start < end && /\s/.test(text[start] ?? '')) start++;
    while (end > start && /\s/.test(text[end - 1] ?? '')) end--;
    if (end <= start) {
      setSel(null);
      return;
    }
    const rect = range.getBoundingClientRect();
    const b = box.getBoundingClientRect();
    setSel({ start, end, top: rect.bottom - b.top + box.scrollTop + 6, left: Math.max(8, Math.min(rect.left - b.left, b.width - 260)) });
  }, [text]);

  useEffect(() => {
    let t = 0;
    const onChange = () => {
      window.clearTimeout(t);
      t = window.setTimeout(read, 120);
    };
    document.addEventListener('selectionchange', onChange);
    return () => {
      document.removeEventListener('selectionchange', onChange);
      window.clearTimeout(t);
    };
  }, [read]);

  const parts: { text: string; mark: boolean }[] = [];
  const sorted = [...linked].filter((r) => r.end > r.start).sort((a, b) => a.start - b.start);
  let pos = 0;
  for (const r of sorted) {
    if (r.start < pos) continue;
    if (r.start > pos) parts.push({ text: text.slice(pos, r.start), mark: false });
    parts.push({ text: text.slice(r.start, r.end), mark: true });
    pos = r.end;
  }
  if (pos < text.length) parts.push({ text: text.slice(pos), mark: false });

  return (
    <div ref={boxRef} className={s.viewer} tabIndex={0} aria-label={tr.contribute.sourceText} data-testid="source-viewer">
      <pre ref={preRef} className={s.viewerPre}>
        {parts.map((p, i) => (p.mark ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}
      </pre>
      {sel && (
        <button
          type="button"
          className={s.linkQuote}
          style={{ top: sel.top, left: sel.left }}
          disabled={busy}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => {
            onLink(sel.start, sel.end);
            window.getSelection()?.removeAllRanges();
            setSel(null);
          }}
        >
          <Link2 size={15} aria-hidden />
          {tr.contribute.linkQuote}
        </button>
      )}
    </div>
  );
}
