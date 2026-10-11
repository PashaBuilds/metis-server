import type { ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import rehypeSanitize from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';
import s from './shared.module.css';

const INLINE: Components = { p: ({ children }: { children?: ReactNode }) => <>{children}</> };

/** Güvenli Markdown: ham HTML yok (skipHtml + sanitize). `inline`: tek paragrafı satır içi işler (via işaretleri arkasına eklenebilsin). */
export function Markdown({ children, inline = false }: { children: string; inline?: boolean }) {
  if (inline)
    return (
      <span className={s.mdInline}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]} skipHtml components={INLINE}>
          {children}
        </ReactMarkdown>
      </span>
    );
  return (
    <div className={s.md}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]} skipHtml>
        {children}
      </ReactMarkdown>
    </div>
  );
}
