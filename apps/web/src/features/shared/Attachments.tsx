import { FileText, Paperclip } from 'lucide-react';
import { useState } from 'react';
import { Dialog } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import type { Schemas } from '@/lib/api/client';
import { formatBytes } from '@/lib/format';
import s from './Attachments.module.css';

export type AttachmentData = Schemas['AttachmentOut'];

export const attachmentUrl = (id: string) => `/api/v1/attachments/${id}/download`;

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
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)} title={open?.filename ?? ''}>
        {open && <img className={s.large} src={attachmentUrl(open.id)} alt={open.filename} />}
      </Dialog>
    </section>
  );
}
