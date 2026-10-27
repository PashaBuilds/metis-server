import { FileText, Paperclip, Trash2 } from 'lucide-react';
import { useRef, useState, type DragEvent } from 'react';
import { Button, IconButton } from '@/design/primitives';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError } from '@/lib/api/client';
import { formatBytes } from '@/lib/format';
import { attachmentUrl, type AttachmentData } from '@/features/shared/Attachments';
import s from './Contribute.module.css';

export const MAX_ATTACHMENTS = 30;
const MAX = MAX_ATTACHMENTS;
const ALLOWED = /\.(png|jpe?g|pdf)$/i;

/** Tek dosya yükler. Her dosya ayrı istekle: sunucu önündeki vekilin (IIS) istek boyutu sınırı dosya başına sınırla
 * aynı kalır; toplu tek istek birkaç büyük fotoğrafta vekilde reddediliyordu. */
export async function uploadAttachment(projectId: string, file: File): Promise<AttachmentData[]> {
  const fd = new FormData();
  fd.append('files', file);
  return api.upload<AttachmentData[]>(`/projects/${projectId}/attachments`, fd);
}

interface Props {
  projectId: string;
  value: AttachmentData[];
  /** Güncelleyici: yükleme sürerken başka yoldan (notun içine yapıştırma) eklenen ekler kaybolmasın. */
  onChange: (update: (prev: AttachmentData[]) => AttachmentData[]) => void;
  /** Notun içinde gösterilen görsellerin kimlikleri (listede "Notta" işareti). */
  inline?: Set<string>;
}

/** Taslağın ekleri: birden çok görsel/PDF seçilir ya da bırakılır, hemen yüklenir; kaldırılabilir. */
export function AttachmentsField({ projectId, value, onChange, inline }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);

  async function add(files: File[]) {
    setError(null);
    if (!files.length) return;
    const bad = files.find((f) => !ALLOWED.test(f.name));
    if (bad) return setError(tr.attachments.notAllowed(bad.name));
    if (value.length + files.length > MAX) return setError(tr.attachments.tooMany);
    setBusy(true);
    // Biri başarısız olursa öncekiler kalır.
    try {
      for (const f of files) {
        const added = await uploadAttachment(projectId, f);
        onChange((prev) => [...prev, ...added]);
      }
    } catch (e) {
      setError(e instanceof ApiError ? errorMessage(e.code) : errorMessage('NETWORK'));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    void add(Array.from(e.dataTransfer.files));
  };

  return (
    <section className={s.figBlock} aria-labelledby="att-h">
      <div className={s.figHead}>
        <h3 id="att-h" className={s.subTitle}>
          {tr.attachments.title}
        </h3>
        <Button size="sm" icon={<Paperclip size={15} aria-hidden />} loading={busy} disabled={busy || value.length >= MAX} onClick={() => input.current?.click()}>
          {tr.attachments.add}
        </Button>
        <input
          ref={input}
          type="file"
          multiple
          accept=".png,.jpg,.jpeg,.pdf"
          className="sr-only"
          tabIndex={-1}
          aria-hidden
          onChange={(e) => void add(Array.from(e.target.files ?? []))}
        />
      </div>
      <div
        className={[s.dropZone, over ? s.dropOver : ''].join(' ')}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        <p className={s.hint}>{busy ? tr.attachments.uploading : tr.attachments.hint}</p>
        {value.length > 0 && (
          <ol className={s.figList}>
            {value.map((a) => (
              <li key={a.id} className={s.figRow}>
                {a.is_image ? (
                  <img className={s.figThumb} src={attachmentUrl(a.id)} alt="" />
                ) : (
                  <span className={s.figThumb} aria-hidden>
                    <FileText size={22} />
                  </span>
                )}
                <div className={s.grow}>
                  <span className={s.attName}>
                    {a.filename}
                    {inline?.has(a.id.toLowerCase()) && <span className={s.inlineTag}>{tr.attachments.inNote}</span>}
                  </span>
                  <span className={s.hint}>{formatBytes(a.size_bytes)}</span>
                </div>
                <IconButton label={tr.attachments.remove(a.filename)} onClick={() => onChange((prev) => prev.filter((x) => x.id !== a.id))}>
                  <Trash2 size={16} aria-hidden />
                </IconButton>
              </li>
            ))}
          </ol>
        )}
      </div>
      {error && (
        <p className={s.error} role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
