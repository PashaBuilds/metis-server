import { Download, FileText, Paperclip } from 'lucide-react';
import { useState } from 'react';
import { Dialog } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import type { Schemas } from '@/lib/api/client';
import { formatBytes } from '@/lib/format';
import s from './Attachments.module.css';
import { apiUrl } from '@/lib/api/base';

export type AttachmentData = Schemas['AttachmentOut'];

export const attachmentUrl = (id: string) => apiUrl(`/attachments/${id}/download`);

/** Notta satır içi görsel: taslağın görsel ekine bağlantı, `![açıklama](ek:<ek kimliği>)` (sunucu: knowledge.figures.INLINE_IMAGE). */
export const INLINE_IMAGE = /!\[([^\]\n]*)\]\(ek:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\)/g;
const ONLY_IMAGE = new RegExp(`^\\s*${INLINE_IMAGE.source}\\s*$`);
const UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

export const inlineImageMd = (id: string, alt: string) => `![${alt.replace(/[[\]\\\n]/g, ' ').trim()}](ek:${id})`;

/** Paragraf yalnız bir satır içi görselse kimliği ve açıklaması. */
export function inlineImage(text: string): { id: string; alt: string } | null {
  const m = ONLY_IMAGE.exec(text);
  return m ? { alt: m[1]!, id: m[2]!.toLowerCase() } : null;
}

export function inlineImageIds(text: string): Set<string> {
  return new Set([...text.matchAll(INLINE_IMAGE)].map((m) => m[2]!.toLowerCase()));
}

/** `ek:` bağlantısı → ek kimliği (Markdown görüntüleyicisi için); geçersizse null. */
export function attachmentRef(src: unknown): string | null {
  return typeof src === 'string' && src.startsWith('ek:') && UUID.test(src.slice(3)) ? src.slice(3).toLowerCase() : null;
}

/** Görseli büyük gösterir; indirme bağlantısıyla (indirme ucu dosyayı hep ek olarak verir, yeni sekmede açmaz). */
export function ImageViewer({ id, title, open, onOpenChange }: { id: string; title: string; open: boolean; onOpenChange: (open: boolean) => void }) {
  const url = attachmentUrl(id);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      width={1100}
      footer={
        <span className={s.viewerLinks}>
          <a href={url} download>
            <Download size={15} aria-hidden /> {tr.attachments.download}
          </a>
        </span>
      }
    >
      {open && <img className={s.large} src={url} alt={title} />}
    </Dialog>
  );
}

/** Notun içindeki görsel: metin genişliğinde, tıklayınca büyür. Kanıt değildir (altın yok). */
export function InlineImage({ id, alt }: { id: string; alt: string }) {
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);
  const title = alt.trim() || tr.attachments.untitledImage;
  if (failed) return <span className={s.inlineMissing}>{tr.attachments.imageMissing}</span>;
  return (
    <span className={s.inline}>
      <button type="button" className={s.inlineBtn} onClick={() => setOpen(true)} aria-label={tr.attachments.preview(title)}>
        <img className={s.inlineImg} src={attachmentUrl(id)} alt="" loading="lazy" onError={() => setFailed(true)} />
      </button>
      {alt.trim() && <span className={s.inlineCaption}>{alt.trim()}</span>}
      <ImageViewer id={id} title={title} open={open} onOpenChange={setOpen} />
    </span>
  );
}

/** Bilginin ekleri: görseller küçük önizlemeyle (tıklayınca büyür), PDF'ler adıyla açılır/indirilir. Kanıt değildir. */
export function Attachments({ items, headingLevel = 2 }: { items: AttachmentData[]; headingLevel?: 2 | 3 }) {
  const [open, setOpen] = useState<AttachmentData | null>(null);
  if (!items.length) return null;
  const H = headingLevel === 2 ? 'h2' : 'h3';
  return (
    <section className={s.block} aria-labelledby="attachments-h">
      <H id="attachments-h" className={s.title}>
        <Paperclip size={16} aria-hidden />
        {tr.attachments.count(items.length)}
      </H>
      <ul className={s.list}>
        {items.map((a) => (
          <li key={a.id} className={s.item}>
            {a.is_image ? (
              <button type="button" className={s.thumbBtn} onClick={() => setOpen(a)} aria-label={tr.attachments.preview(a.filename)}>
                <img className={s.thumb} src={attachmentUrl(a.id)} alt="" loading="lazy" />
              </button>
            ) : (
              <span className={s.fileIcon} aria-hidden>
                <FileText size={22} />
              </span>
            )}
            <span className={s.meta}>
              <a className={s.name} href={attachmentUrl(a.id)} download={a.filename}>
                {a.filename}
              </a>
              <span className={s.size}>{formatBytes(a.size_bytes)}</span>
            </span>
          </li>
        ))}
      </ul>
      {open && <ImageViewer id={open.id} title={open.filename} open onOpenChange={(o) => !o && setOpen(null)} />}
    </section>
  );
}
