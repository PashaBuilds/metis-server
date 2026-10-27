import type { ReactNode } from 'react';
import ReactMarkdown, { defaultUrlTransform, type Components } from 'react-markdown';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';
import { tr } from '@/i18n/tr';
import { attachmentRef, InlineImage } from './Attachments';
import s from './shared.module.css';

// `ek:<kimlik>` görsel bağlantısı taslağın kendi ekidir; başka görsel adresi gösterilmez (CSP de dış adresi engeller),
// yalnız açıklaması yazılır.
const SCHEMA = { ...defaultSchema, protocols: { ...defaultSchema.protocols, src: [...(defaultSchema.protocols?.src ?? []), 'ek'] } };
const urlTransform = (url: string) => (url.startsWith('ek:') ? url : defaultUrlTransform(url));
const img: Components['img'] = ({ src, alt }) => {
  const id = attachmentRef(src);
  if (id) return <InlineImage id={id} alt={alt ?? ''} />;
  return alt ? <span>{tr.attachments.externalImage(alt)}</span> : null;
};
const BLOCK: Components = { img };
const INLINE: Components = { img, p: ({ children }: { children?: ReactNode }) => <>{children}</> };

/** Güvenli Markdown: ham HTML yok (skipHtml + sanitize). `inline`: tek paragrafı satır içi işler (via işaretleri arkasına eklenebilsin). */
export function Markdown({ children, inline = false }: { children: string; inline?: boolean }) {
  const md = (
    <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[[rehypeSanitize, SCHEMA]]} skipHtml urlTransform={urlTransform} components={inline ? INLINE : BLOCK}>
      {children}
    </ReactMarkdown>
  );
  return inline ? <span className={s.mdInline}>{md}</span> : <div className={s.md}>{md}</div>;
}
