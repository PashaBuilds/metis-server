import { FileText, Paperclip, Trash2 } from 'lucide-react';
import { useRef, useState, type DragEvent } from 'react';
import { Button, IconButton } from '@/design/primitives';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError } from '@/lib/api/client';
import { formatBytes } from '@/lib/format';
import { attachmentUrl, type AttachmentData } from '@/features/shared/Attachments';
import s from './Contribute.module.css';

const MAX = 30;
const ALLOWED = /\.(png|jpe?g|pdf)$/i;

interface Props {
  projectId: string;
  value: AttachmentData[];
  onChange: (next: AttachmentData[]) => void;
}

/** Taslağın ekleri: birden çok görsel/PDF seçilir ya da bırakılır, hemen yüklenir; kaldırılabilir. */
export function AttachmentsField({ projectId, value, onChange }: Props) {
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
    const fd = new FormData();
    files.forEach((f) => fd.append('files', f));
    setBusy(true);
    try {
      const added = await api.upload<AttachmentData[]>(`/projects/${projectId}/attachments`, fd);
      onChange([...value, ...added]);
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
                  <span className={s.attName}>{a.filename}</span>
                  <span className={s.hint}>{formatBytes(a.size_bytes)}</span>
                </div>
                <IconButton label={tr.attachments.remove(a.filename)} onClick={() => onChange(value.filter((x) => x.id !== a.id))}>
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
