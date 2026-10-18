import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button, Dialog, Field, Input, Segmented, SkeletonRows, Textarea } from '@/design/primitives';
import { EMPTY_SCOPE, useSession } from '@/app/session';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { figureUrl, type FigureData } from '@/features/shared/Figure';
import s from './Contribute.module.css';

const MAX_BYTES = 10 * 1024 * 1024;

/** "Görsel ekle": var olan bir görsel kaynağı seç ya da yenisini yükle (kaynak olarak saklanır), açıklama yaz. */
export function FigurePicker({ open, onOpenChange, onAdd }: { open: boolean; onOpenChange: (o: boolean) => void; onAdd: (f: FigureData) => void }) {
  const { projectId } = useSession();
  const [tab, setTab] = useState<'existing' | 'upload' | null>(null);
  const [picked, setPicked] = useState<{ id: string; title: string } | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [caption, setCaption] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const list = useQuery({
    queryKey: ['sources', projectId, 'images'],
    queryFn: () => api.get<Schemas['SourceListOut']>(`/projects/${projectId}/sources`, { kind: 'image', limit: 100 }),
    enabled: open && !!projectId,
  });
  const images = (list.data?.items ?? []).filter((x) => x.current_revision?.media_type.startsWith('image/'));
  const current = tab ?? (list.data && images.length === 0 ? 'upload' : 'existing');

  useEffect(() => {
    if (!open) {
      setTab(null);
      setPicked(null);
      setFile(null);
      setTitle('');
      setCaption('');
      setError(null);
    }
  }, [open]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setError(null);
    if (current === 'existing') {
      if (!picked) return;
      onAdd({ source_revision_id: picked.id, caption: caption.trim(), source_title: picked.title });
      onOpenChange(false);
      return;
    }
    if (!file) return setError(tr.figures.fileRequired);
    if (file.size > MAX_BYTES) return setError(tr.errors.FILE_TOO_LARGE!);
    if (!/\.(png|jpe?g)$/i.test(file.name)) return setError(tr.figures.notImage);
    setBusy(true);
    try {
      const name = title.trim() || file.name.replace(/\.[^.]+$/, '');
      const fd = new FormData();
      fd.append('meta', JSON.stringify({ title: name, kind: 'image', text: '', scope: EMPTY_SCOPE }));
      fd.append('file', file);
      const res = await api.upload<Schemas['SourceRevisionCreated']>(`/projects/${projectId}/sources`, fd);
      onAdd({ source_revision_id: res.revision.id, caption: caption.trim(), source_title: name });
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof ApiError ? errorMessage(err.code) : errorMessage('NETWORK'));
    } finally {
      setBusy(false);
    }
  }

  const canAdd = current === 'existing' ? !!picked : !!file;
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={tr.figures.addTitle}
      width={720}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {tr.common.cancel}
          </Button>
          <Button variant="primary" type="submit" form="figure-picker" loading={busy} disabled={!canAdd}>
            {tr.figures.insert}
          </Button>
        </>
      }
    >
      <form id="figure-picker" className={s.figPicker} onSubmit={submit} noValidate>
        <Segmented
          label={tr.figures.addTitle}
          size="md"
          value={current}
          onChange={setTab}
          options={[
            { value: 'existing', label: tr.figures.existing },
            { value: 'upload', label: tr.figures.upload },
          ]}
        />
        {current === 'existing' ? (
          list.isLoading ? (
            <SkeletonRows rows={2} />
          ) : images.length === 0 ? (
            <p className={s.muted}>{tr.figures.none}</p>
          ) : (
            <ul className={s.figGrid}>
              {images.map((img) => {
                const rid = img.current_revision!.id;
                return (
                  <li key={img.id}>
                    <button
                      type="button"
                      className={[s.figChoice, picked?.id === rid ? s.figChoiceOn : ''].join(' ')}
                      aria-pressed={picked?.id === rid}
                      aria-label={tr.figures.pick(img.title)}
                      onClick={() => setPicked({ id: rid, title: img.title })}
                    >
                      <img src={figureUrl(rid)} alt="" loading="lazy" />
                      <span>{img.title}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )
        ) : (
          <div className={s.figUpload}>
            <input ref={fileInput} type="file" accept=".png,.jpg,.jpeg" className="sr-only" tabIndex={-1} aria-hidden onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <Field label={tr.figures.file} hint={tr.figures.fileHint}>
              {({ id, describedBy }) => (
                <div className={s.figFileRow}>
                  <Button id={id} aria-describedby={describedBy} onClick={() => fileInput.current?.click()}>
                    {tr.contribute.chooseFile}
                  </Button>
                  <span className={s.fileName}>{file?.name}</span>
                </div>
              )}
            </Field>
            <Field label={tr.figures.fileTitle}>{({ id }) => <Input id={id} value={title} placeholder={file?.name.replace(/\.[^.]+$/, '')} onChange={(e) => setTitle(e.target.value)} />}</Field>
          </div>
        )}
        <Field label={tr.figures.caption} hint={tr.figures.captionHint}>
          {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} rows={2} maxLength={500} value={caption} onChange={(e) => setCaption(e.target.value)} />}
        </Field>
        {error && (
          <p className={s.error} role="alert">
            {error}
          </p>
        )}
      </form>
    </Dialog>
  );
}
