import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ImagePlus, MessageSquareWarning, Trash2 } from 'lucide-react';
import { useRef, useState, type ClipboardEvent, type DragEvent } from 'react';
import { PageHeader } from '@/app/Shell';
import { useSession } from '@/app/session';
import { Button, ConfirmDialog, Dialog, EmptyState, Field, IconButton, Segmented, Select, SkeletonRows, StatusBadge, Textarea, useToast, type Tone } from '@/design/primitives';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { apiUrl } from '@/lib/api/base';
import { formatDateTime } from '@/lib/format';
import { messageOf } from '@/features/shared/hooks';
import s from './Feedback.module.css';

type Item = Schemas['FeedbackOut'];
type Image = Schemas['FeedbackImageOut'];
type Kind = Item['kind'];
type Status = Item['status'];

const MAX_IMAGES = 5;
const IMAGE_NAME = /\.(png|jpe?g)$/i;
const imageUrl = (id: string) => apiUrl(`/feedback/images/${id}`);

const STATUS_TONE: Record<Status, { tone: Tone; icon?: 'clock' | 'ban' }> = {
  new: { tone: 'taslak', icon: 'clock' },
  in_progress: { tone: 'inceleme' },
  done: { tone: 'onay' },
  wontfix: { tone: 'dikkat', icon: 'ban' },
};
const STATUSES: Status[] = ['new', 'in_progress', 'done', 'wontfix'];

/** Geri bildirim: herkes hata ya da istek yazar (ekran görüntüsüyle); herkes hepsini görür; durumu yönetici verir. */
export function FeedbackPage() {
  const list = useQuery({ queryKey: ['feedback'], queryFn: () => api.get<Item[]>('/feedback') });
  const [kind, setKind] = useState<'all' | Kind>('all');
  const [status, setStatus] = useState<'all' | 'open' | Status>('all');
  const rows = (list.data ?? []).filter(
    (f) => (kind === 'all' || f.kind === kind) && (status === 'all' || (status === 'open' ? f.status === 'new' || f.status === 'in_progress' : f.status === status)),
  );

  return (
    <div className={s.page}>
      <PageHeader title={tr.feedback.title}>
        <p className={s.lead}>{tr.feedback.lead}</p>
      </PageHeader>
      <div className={s.stack}>
        <NewFeedback />
        <section className={s.section} aria-labelledby="fb-list-h">
          <div className={s.listHead}>
            <h2 id="fb-list-h" className={s.sectionTitle}>
              {tr.feedback.listTitle}
            </h2>
            <div className={s.filters}>
              <Segmented
                label={tr.feedback.filterKind}
                value={kind}
                onChange={setKind}
                options={[
                  { value: 'all', label: tr.feedback.all },
                  { value: 'bug', label: tr.feedback.kinds.bug },
                  { value: 'request', label: tr.feedback.kinds.request },
                ]}
              />
              <Select aria-label={tr.feedback.filterStatus} value={status} onChange={(e) => setStatus(e.target.value as typeof status)}>
                <option value="all">{tr.feedback.all}</option>
                <option value="open">{tr.feedback.open}</option>
                {STATUSES.map((st) => (
                  <option key={st} value={st}>
                    {tr.feedback.statuses[st]}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          {list.isLoading ? (
            <SkeletonRows rows={3} />
          ) : list.isError ? (
            <EmptyState title={tr.shared.loadError} actions={<Button onClick={() => list.refetch()}>{tr.common.retry}</Button>}>
              {messageOf(list.error)}
            </EmptyState>
          ) : !rows.length ? (
            <EmptyState icon={<MessageSquareWarning size={24} />} title={list.data?.length ? tr.feedback.emptyFiltered : tr.feedback.empty} />
          ) : (
            <ul className={s.items}>
              {rows.map((f) => (
                <FeedbackItem key={f.id} item={f} />
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function NewFeedback() {
  const qc = useQueryClient();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<Kind>('bug');
  const [text, setText] = useState('');
  const [images, setImages] = useState<Image[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);

  async function add(files: File[]) {
    setError(null);
    if (!files.length) return;
    const bad = files.find((f) => !IMAGE_NAME.test(f.name) && f.type !== 'image/png' && f.type !== 'image/jpeg');
    if (bad) return setError(tr.feedback.imageNotAllowed(bad.name));
    if (images.length + files.length > MAX_IMAGES) return setError(tr.feedback.tooManyImages);
    setUploading(true);
    // Her görsel ayrı istekle: sunucu önündeki vekilin (IIS) istek boyutu sınırı dosya başına sınırla aynı kalır.
    let next = images;
    try {
      for (const f of files) {
        const fd = new FormData();
        // Yapıştırılan ekran görüntüsünün adı çoğu tarayıcıda "image.png"; yoksa türüne göre ad verilir.
        const name = IMAGE_NAME.test(f.name) ? f.name : `ekran-goruntusu.${f.type === 'image/jpeg' ? 'jpg' : 'png'}`;
        fd.append('files', f, name);
        const added = await api.upload<Image[]>('/feedback/images', fd);
        next = [...next, ...added];
        setImages(next);
      }
    } catch (e) {
      setError(e instanceof ApiError ? errorMessage(e.code) : errorMessage('NETWORK'));
    } finally {
      setUploading(false);
      if (input.current) input.current.value = '';
    }
  }

  const send = useMutation({
    mutationFn: () => api.post<Item>('/feedback', { kind, text, image_ids: images.map((i) => i.id) }),
    onSuccess: (item) => {
      qc.setQueryData<Item[]>(['feedback'], (old) => [item, ...(old ?? [])]);
      setText('');
      setImages([]);
      setError(null);
      toast.show(tr.feedback.sent);
    },
    onError: (e) => setError(messageOf(e)),
  });

  const onPaste = (e: ClipboardEvent) => {
    const files = Array.from(e.clipboardData.files).filter((f) => f.type.startsWith('image/'));
    if (files.length) {
      e.preventDefault();
      void add(files);
    }
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    void add(Array.from(e.dataTransfer.files));
  };

  return (
    <section className={s.section} aria-labelledby="fb-new-h">
      <h2 id="fb-new-h" className={s.sectionTitle}>
        {tr.feedback.newTitle}
      </h2>
      <form
        className={s.form}
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim() && !uploading) send.mutate();
        }}
      >
        <Segmented
          label={tr.feedback.kindLabel}
          size="md"
          value={kind}
          onChange={setKind}
          options={[
            { value: 'bug', label: tr.feedback.kinds.bug },
            { value: 'request', label: tr.feedback.kinds.request },
          ]}
        />
        <Field label={tr.feedback.textLabel} hint={tr.feedback.textHint}>
          {({ id, describedBy }) => (
            <Textarea
              id={id}
              aria-describedby={describedBy}
              value={text}
              maxLength={5000}
              rows={5}
              placeholder={tr.feedback.textPlaceholder}
              onChange={(e) => setText(e.target.value)}
              onPaste={onPaste}
            />
          )}
        </Field>
        <div
          className={[s.drop, over ? s.dropOver : ''].join(' ')}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
        >
          <div className={s.dropHead}>
            <span className={s.dropTitle}>{tr.feedback.images}</span>
            <Button size="sm" icon={<ImagePlus size={15} aria-hidden />} loading={uploading} disabled={uploading || images.length >= MAX_IMAGES} onClick={() => input.current?.click()}>
              {tr.feedback.addImage}
            </Button>
            <input
              ref={input}
              type="file"
              multiple
              accept=".png,.jpg,.jpeg"
              className="sr-only"
              tabIndex={-1}
              aria-hidden
              onChange={(e) => void add(Array.from(e.target.files ?? []))}
            />
          </div>
          <p className={s.hint}>{uploading ? tr.feedback.uploading : tr.feedback.imagesHint}</p>
          {images.length > 0 && (
            <ul className={s.thumbs}>
              {images.map((img) => (
                <li key={img.id} className={s.thumbItem}>
                  <img className={s.thumb} src={imageUrl(img.id)} alt={img.filename} />
                  <IconButton label={tr.feedback.removeImage(img.filename)} onClick={() => setImages(images.filter((x) => x.id !== img.id))}>
                    <Trash2 size={15} aria-hidden />
                  </IconButton>
                </li>
              ))}
            </ul>
          )}
        </div>
        {error && (
          <p className={s.error} role="alert">
            {error}
          </p>
        )}
        <div>
          <Button type="submit" variant="primary" loading={send.isPending} disabled={!text.trim() || uploading}>
            {tr.feedback.send}
          </Button>
        </div>
      </form>
    </section>
  );
}

function FeedbackItem({ item }: { item: Item }) {
  const session = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const [preview, setPreview] = useState<Image | null>(null);
  const [managing, setManaging] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [status, setStatus] = useState<Status>(item.status);
  const [reply, setReply] = useState(item.reply);
  const badge = STATUS_TONE[item.status];

  const save = useMutation({
    mutationFn: () => api.patch<Item>(`/feedback/${item.id}`, { status, reply }),
    onSuccess: (updated) => {
      qc.setQueryData<Item[]>(['feedback'], (old) => (old ?? []).map((f) => (f.id === updated.id ? updated : f)));
      setManaging(false);
      toast.show(tr.feedback.statusSaved);
    },
    onError: (e) => toast.show(messageOf(e), { tone: 'error' }),
  });

  return (
    <li className={s.item}>
      <div className={s.itemHead}>
        <span className={[s.kind, item.kind === 'bug' ? s.kindBug : s.kindRequest].join(' ')}>{tr.feedback.kinds[item.kind]}</span>
        <StatusBadge tone={badge.tone} icon={badge.icon} label={tr.feedback.statuses[item.status]} size="sm" />
        <span className={s.meta}>{tr.feedback.by(item.author_name, formatDateTime(item.created_at))}</span>
        <span className={s.grow} />
        {session.isAdmin && !managing && (
          <Button size="sm" variant="ghost" onClick={() => setManaging(true)}>
            {tr.feedback.manage}
          </Button>
        )}
        {item.can_delete && (
          <IconButton label={tr.common.delete} onClick={() => setConfirm(true)}>
            <Trash2 size={16} aria-hidden />
          </IconButton>
        )}
      </div>
      <p className={s.text}>{item.text}</p>
      {item.images.length > 0 && (
        <ul className={s.thumbs}>
          {item.images.map((img) => (
            <li key={img.id}>
              <button type="button" className={s.thumbBtn} onClick={() => setPreview(img)} aria-label={tr.feedback.preview(img.filename)}>
                <img className={s.thumb} src={imageUrl(img.id)} alt="" loading="lazy" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {item.reply && !managing && (
        <div className={s.reply}>
          <span className={s.replyBy}>{tr.feedback.reply(item.reply_by_name ?? '')}</span>
          <p className={s.text}>{item.reply}</p>
        </div>
      )}
      {managing && (
        <form
          className={s.manage}
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <Field label={tr.feedback.filterStatus}>
            {({ id }) => (
              <Select id={id} value={status} onChange={(e) => setStatus(e.target.value as Status)}>
                {STATUSES.map((st) => (
                  <option key={st} value={st}>
                    {tr.feedback.statuses[st]}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={tr.feedback.replyLabel}>
            {({ id }) => <Textarea id={id} value={reply} maxLength={2000} rows={2} placeholder={tr.feedback.replyPlaceholder} onChange={(e) => setReply(e.target.value)} />}
          </Field>
          <div className={s.manageActions}>
            <Button type="submit" variant="primary" size="sm" loading={save.isPending}>
              {tr.common.save}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setStatus(item.status);
                setReply(item.reply);
                setManaging(false);
              }}
            >
              {tr.common.cancel}
            </Button>
          </div>
        </form>
      )}
      <Dialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)} title={preview?.filename ?? ''}>
        {preview && <img className={s.large} src={imageUrl(preview.id)} alt={preview.filename} />}
      </Dialog>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={tr.feedback.deleteTitle}
        description={tr.feedback.deleteDesc}
        confirmLabel={tr.common.delete}
        danger
        onConfirm={async () => {
          try {
            await api.del(`/feedback/${item.id}`);
            qc.setQueryData<Item[]>(['feedback'], (old) => (old ?? []).filter((f) => f.id !== item.id));
            setConfirm(false);
            toast.show(tr.feedback.deleted);
          } catch (e) {
            toast.show(messageOf(e), { tone: 'error' });
          }
        }}
      />
    </li>
  );
}
