import { ImagePlus, Plus, Send, Table2, Upload, X } from 'lucide-react';
import { useRef, useState, type ClipboardEvent, type DragEvent } from 'react';
import { Button, Field, IconButton, Input, Select, TabPanel, Tabs, Textarea, useToast } from '@/design/primitives';
import { ScopeField } from '@/app/ScopeBar';
import { useSession, type ScopeSel } from '@/app/session';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, newIdempotencyKey, type Schemas } from '@/lib/api/client';
import { Banner } from '@/features/shared/Banner';
import { inlineImageIds, inlineImageMd, INLINE_IMAGE, type AttachmentData } from '@/features/shared/Attachments';
import { useProject } from '@/features/shared/hooks';
import { Markdown } from '@/features/shared/Markdown';
import { usePublishFlow } from '@/features/shared/PublishCheck';
import { PAGE_KINDS } from '@/features/shared/kinds';
import { asBlock, parseTsv, tableAt, tableMarkdown, type Grid } from '@/features/shared/table';
import { AttachmentsField, MAX_ATTACHMENTS, uploadAttachment } from './AttachmentsField';
import { TableDialog } from './TableDialog';
import s from './Contribute.module.css';

export interface NoteValues {
  title: string;
  kind: string;
  summary: string;
  /** Not: bilginin dayanağı. Sunucu her paragrafı kendiliğinden bir iddia yapar. */
  body_md: string;
  scope: ScopeSel;
  unknowns: string[];
  aliases: string[];
  attachments: AttachmentData[];
  /** Kaynaktan al: dış kaynak önizlemesinin kimliği (taslak kaydında köken bağlanır). */
  importId?: string | null;
}

export interface NoteTarget {
  pageId: string | null;
  baseRevisionId: string | null;
  changeId: string | null;
  changeHash: string | null;
  changeSummary: string;
}

interface Props {
  initial: NoteValues;
  target: NoteTarget;
  onDirty: (dirty: boolean) => void;
  onSaved: (changeId: string) => void;
  /** Yazar yayımlar: yayın tamamlandı. */
  onPublished: (change: Schemas['ChangeDetailOut']) => void;
  /** Yayın öncesi uyarıdan "Taslağa dön": kaydedilmiş taslak editörde yeniden açılır. */
  onReopen: (changeId: string) => void;
}

/** Tek adımlı taslak: başlık, kapsam, not ve ekler; kaydet ya da yayımla. Ayrı bir kaynak adımı yok. */
export function NoteEditor({ initial, target, onDirty, onSaved, onPublished, onReopen }: Props) {
  const session = useSession();
  const toast = useToast();
  const [v, setV] = useState<NoteValues>(initial);
  const [bodyTab, setBodyTab] = useState('write');
  const [idemKey] = useState(newIdempotencyKey);
  const [busy, setBusy] = useState<'save' | 'submit' | 'publish' | null>(null);
  const project = useProject(session.projectId);
  const selfPublish = project.data?.review_policy === 'self_publish';
  const flow = usePublishFlow(onPublished);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  // Taslak sayfası ilk kayıtta oluşur; sonraki kayıtlar aynı sayfayı günceller.
  const [pageId, setPageId] = useState(target.pageId);
  const noteEmpty = !v.body_md.trim();
  const area = useRef<HTMLTextAreaElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  // Süren görsel yüklemesi sayısı (yapıştırma yükleme sürerken de yapılabilir); sürerken kaydetme kapalı.
  const [imageBusy, setImageBusy] = useState(0);
  const [toolError, setToolError] = useState<string | null>(null);
  const [table, setTable] = useState<{ grid: Grid | null; start: number; end: number } | null>(null);
  const inline = inlineImageIds(v.body_md);

  const update = (patch: Partial<NoteValues>) => {
    setV((old) => ({ ...old, ...patch }));
    onDirty(true);
  };

  /** Metni verilen aralığa (yoksa imlecin yerine) yazar; tarayıcının geri al (Ctrl+Z) geçmişine girer. */
  function insert(text: string, start?: number, end?: number) {
    const ta = area.current;
    if (!ta) return appendBlock(text);
    ta.focus();
    ta.setSelectionRange(start ?? ta.selectionStart, end ?? ta.selectionEnd);
    // execCommand eskidi ama textarea'da geri al geçmişini koruyan tek yol; desteklemeyen tarayıcıda doğrudan yazılır.
    // Boş metin seçimi silmez; tablo kaldırılırken "delete" kullanılır.
    if (!document.execCommand(text ? 'insertText' : 'delete', false, text)) {
      const a = ta.selectionStart;
      update({ body_md: ta.value.slice(0, a) + text + ta.value.slice(ta.selectionEnd) });
      requestAnimationFrame(() => ta.setSelectionRange(a + text.length, a + text.length));
    }
  }

  /** Bloğu (tablo, görsel) boş satırlarla ayrı paragraf olarak yazar: not blokları boş satırla bölünür. */
  function insertBlock(block: string, start?: number, end?: number) {
    const ta = area.current;
    if (!ta) return appendBlock(block);
    const a = start ?? ta.selectionStart;
    const b = end ?? ta.selectionEnd;
    insert(asBlock(ta.value.slice(0, a), ta.value.slice(b), block), a, b);
  }

  /** Editör görünmüyorken (Önizle sekmesi açıkken yükleme bitti): notun sonuna eklenir. */
  function appendBlock(block: string) {
    setV((old) => ({ ...old, body_md: old.body_md + asBlock(old.body_md, '', block) }));
    onDirty(true);
  }

  async function addImages(files: File[], pasted: boolean) {
    setToolError(null);
    if (!session.projectId || !files.length) return;
    if (files.some((f) => f.type !== 'image/png' && f.type !== 'image/jpeg')) return setToolError(tr.contribute.imageNotAllowed);
    if (v.attachments.length + files.length > MAX_ATTACHMENTS) return setToolError(tr.attachments.tooMany);
    setImageBusy((n) => n + 1);
    try {
      for (const [i, f] of files.entries()) {
        // Panodan gelen görselin adı hep "image.png"dir; ekler listesinde ayırt edilsin diye zamanla adlandırılır.
        const ext = f.type === 'image/png' ? 'png' : 'jpg';
        const stamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '');
        const file = pasted ? new File([f], `yapistirilan-${stamp}${files.length > 1 ? `-${i + 1}` : ''}.${ext}`, { type: f.type }) : f;
        const added = await uploadAttachment(session.projectId, file);
        setV((old) => ({ ...old, attachments: [...old.attachments, ...added] }));
        // Yapıştırılan görselin açıklaması boş başlar (köşeli paranteze yazılır); seçilen dosyada dosya adıdır.
        // Kullanıcı yükleme sürerken başka alana geçtiyse odak çalınmaz: görsel notun sonuna eklenir.
        for (const a of added) {
          const md = inlineImageMd(a.id, pasted ? '' : a.filename.replace(/\.[^.]+$/, ''));
          if (area.current && document.activeElement === area.current) insertBlock(md);
          else appendBlock(md);
        }
      }
    } catch (e) {
      setToolError(e instanceof ApiError ? errorMessage(e.code) : errorMessage('NETWORK'));
    } finally {
      setImageBusy((n) => n - 1);
      if (imageInput.current) imageInput.current.value = '';
    }
  }

  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const text = e.clipboardData.getData('text/plain');
    // Yalnız tablolama programından (Excel, LibreOffice, tarayıcı tablosu) gelen hücreler tabloya çevrilir: bunlar
    // panoya HTML tablosu da koyar. Sekmeli kod ya da günlük metni olduğu gibi yapışır. Excel yanında resim de koyar;
    // metin önceliklidir.
    const fromSheet = /<table[\s>]/i.test(e.clipboardData.getData('text/html'));
    const grid = fromSheet && text ? parseTsv(text) : null;
    if (grid && grid.length >= 2 && (grid[0]?.length ?? 0) >= 2) {
      e.preventDefault();
      insertBlock(tableMarkdown(grid));
      toast.show(tr.contribute.tablePasted);
      return;
    }
    const images = Array.from(e.clipboardData.files).filter((f) => f.type.startsWith('image/'));
    if (images.length && !text.trim()) {
      e.preventDefault();
      void addImages(images, true);
    }
  };

  // Dosya sürüklenirken tarayıcının varsayılanı (dosyayı açmak / yolunu yazmak) engellenir; görsel bırakılınca yüklenir.
  const onDragOver = (e: DragEvent<HTMLTextAreaElement>) => {
    if (e.dataTransfer.types.includes('Files')) e.preventDefault();
  };

  const onDrop = (e: DragEvent<HTMLTextAreaElement>) => {
    const files = Array.from(e.dataTransfer.files);
    if (!files.length) return;
    e.preventDefault();
    void addImages(files, false);
  };

  function openTable() {
    const ta = area.current;
    const at = ta ? tableAt(ta.value, ta.selectionStart) : null;
    setTable(at ?? { grid: null, start: ta?.selectionStart ?? v.body_md.length, end: ta?.selectionEnd ?? v.body_md.length });
  }

  /** Boş tablo (düzenlenen tablonun tüm hücreleri silindi) tabloyu nottan kaldırır. */
  function saveTable(grid: Grid | null) {
    const target = table;
    setTable(null);
    if (!target) return;
    const md = grid ? tableMarkdown(grid) : '';
    // Pencere kapanınca odak editöre döner; düzenlenen tablo yerinde değişir, yeni tablo ayrı paragraf olarak girer.
    requestAnimationFrame(() => (target.grid ? insert(md, target.start, target.end) : insertBlock(md, target.start, target.end)));
  }

  /** Ek kaldırılınca notun içindeki görseli de kalkar (sunucu, eklerde olmayan görseli kabul etmez). En güncel taslak
   * üzerinden: yükleme sürerken yazılan metin ya da yapıştırılan görsel kaybolmaz. */
  function changeAttachments(change: (prev: AttachmentData[]) => AttachmentData[]) {
    setV((old) => {
      const attachments = change(old.attachments);
      const keep = new Set(attachments.map((a) => a.id.toLowerCase()));
      let removed = false;
      const body = old.body_md.replace(INLINE_IMAGE, (m, _alt: string, id: string) => {
        if (keep.has(id.toLowerCase())) return m;
        removed = true;
        return '';
      });
      // Kalkan görselin bıraktığı fazla boş satırlar tek boş satıra iner.
      return { ...old, attachments, body_md: removed ? body.replace(/\n[ \t]*(\n[ \t]*){2,}/g, '\n\n').trim() : old.body_md };
    });
    onDirty(true);
  }

  async function save(mode: 'save' | 'submit' | 'publish') {
    if (busy) return;
    const errs: Record<string, string> = {};
    if (!v.title.trim()) errs.title = tr.contribute.titleRequired;
    if (mode !== 'save' && noteEmpty) errs.body = tr.contribute.noteEmpty;
    setErrors(errs);
    setFormError(null);
    if (Object.keys(errs).length) return;
    setBusy(mode);
    const item = {
      note: true,
      page_id: pageId,
      base_revision_id: target.baseRevisionId,
      title: v.title.trim(),
      summary: v.summary.trim(),
      body_md: v.body_md,
      kind: v.kind,
      scope: v.scope,
      unknowns: v.unknowns.map((u) => u.trim()).filter(Boolean),
      aliases: v.aliases,
      attachments: v.attachments.map((a) => a.id),
      import_id: v.importId ?? null,
    };
    try {
      let id: string;
      const submit = mode === 'submit';
      if (target.changeId) {
        await api.put<Schemas['ChangeDetailOut']>(`/changes/${target.changeId}`, { expected_hash: target.changeHash, items: [item], summary: target.changeSummary });
        if (submit) await api.post(`/changes/${target.changeId}/submit`);
        id = target.changeId;
      } else {
        const res = await api.post<Schemas['ChangeDetailOut']>(`/projects/${session.projectId}/changes`, { items: [item], submit }, { idempotencyKey: idemKey });
        id = res.id;
        setPageId(res.items[0]?.page_id ?? pageId);
      }
      onDirty(false);
      if (mode === 'publish') {
        // Taslak kaydedildi; yayın öncesi kontrol sorun bulursa pencere açılır, aksi hâlde doğrudan yayımlanır.
        const outcome = await flow.start(id);
        if (outcome === 'failed') onSaved(id);
        return;
      }
      toast.show(submit ? tr.contribute.submitted : tr.contribute.saved);
      onSaved(id);
    } catch (e) {
      if (e instanceof ApiError) {
        const fe = e.fieldErrors();
        if (Object.keys(fe).some((k) => k.endsWith('title'))) setErrors({ title: tr.contribute.titleRequired });
        else if (e.code === 'REVISION_CONFLICT' && !target.changeId) setFormError(tr.contribute.baseChanged);
        else setFormError(errorMessage(e.code));
      } else setFormError(errorMessage('NETWORK'));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={s.noteEditor}>
      {formError && <Banner tone="celiski">{formError}</Banner>}
      <Field label={tr.contribute.pTitle} error={errors.title ?? null}>
        {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} invalid={!!errors.title} value={v.title} onChange={(e) => update({ title: e.target.value })} />}
      </Field>

      <section aria-labelledby="pscope-h" className={s.unknownsBox}>
        <h3 id="pscope-h" className={s.subTitle}>
          {tr.contribute.pScope}
        </h3>
        <p className={s.hint}>{tr.contribute.pScopeHint}</p>
        <ScopeField value={v.scope} onChange={(sc) => update({ scope: sc })} allowIndependent />
      </section>

      <div className={s.bodyField}>
        <span className={s.label} id="body-label">
          {tr.contribute.pBody}
        </span>
        <Tabs
          label={tr.contribute.bodyMode}
          value={bodyTab}
          onValueChange={setBodyTab}
          tabs={[
            { value: 'write', label: tr.contribute.write },
            { value: 'preview', label: tr.contribute.preview },
          ]}
        >
          <TabPanel value="write">
            <div className={s.bodyTools} role="group" aria-label={tr.contribute.bodyTools}>
              <Button size="sm" icon={<Table2 size={15} aria-hidden />} onMouseDown={(e) => e.preventDefault()} onClick={openTable}>
                {tr.contribute.tableTool}
              </Button>
              <Button size="sm" icon={<ImagePlus size={15} aria-hidden />} loading={imageBusy > 0} onMouseDown={(e) => e.preventDefault()} onClick={() => imageInput.current?.click()}>
                {tr.contribute.imageTool}
              </Button>
              <input
                ref={imageInput}
                type="file"
                multiple
                accept=".png,.jpg,.jpeg"
                className="sr-only"
                tabIndex={-1}
                aria-hidden
                onChange={(e) => void addImages(Array.from(e.target.files ?? []), false)}
              />
              {/* Canlı bölge hep yerinde: içeriği değişince ekran okuyucu duyurur. */}
              <span className={s.hint} role="status">
                {imageBusy > 0 ? tr.contribute.imageUploading : ''}
              </span>
            </div>
            <Textarea
              ref={area}
              aria-labelledby="body-label"
              aria-describedby={['body-hint', errors.body ? 'body-err' : '', toolError ? 'body-tool-err' : ''].filter(Boolean).join(' ')}
              aria-invalid={!!errors.body || undefined}
              rows={14}
              value={v.body_md}
              onChange={(e) => update({ body_md: e.target.value })}
              onPaste={onPaste}
              onDragOver={onDragOver}
              onDrop={onDrop}
            />
            <p id="body-hint" className={s.hint}>
              {tr.contribute.pBodyHint}
            </p>
            {toolError && (
              <p id="body-tool-err" className={s.error} role="alert">
                {toolError}
              </p>
            )}
            {errors.body && (
              <p id="body-err" className={s.error} role="alert">
                {errors.body}
              </p>
            )}
          </TabPanel>
          <TabPanel value="preview">
            <div className={s.preview}>{v.body_md.trim() ? <Markdown>{v.body_md}</Markdown> : <p className={s.muted}>{tr.contribute.previewEmpty}</p>}</div>
          </TabPanel>
        </Tabs>
      </div>

      {session.projectId && <AttachmentsField projectId={session.projectId} value={v.attachments} onChange={changeAttachments} inline={inline} />}
      <TableDialog open={!!table} initial={table?.grid ?? null} onOpenChange={(o) => !o && setTable(null)} onSave={saveTable} />

      <details className={s.moreFields}>
        <summary>{tr.contribute.moreFields}</summary>
        <div className={s.moreBody}>
          <Field label={tr.contribute.pSummary} hint={tr.contribute.pSummaryHint}>
            {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} rows={2} className={s.shortArea} value={v.summary} onChange={(e) => update({ summary: e.target.value })} />}
          </Field>
          <Field label={tr.contribute.pKind}>
            {({ id }) => (
              <Select id={id} value={v.kind} onChange={(e) => update({ kind: e.target.value })}>
                {PAGE_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {tr.pageKinds[k]}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <section aria-labelledby="unknowns-h" className={s.unknownsBox}>
            <h3 id="unknowns-h" className={s.subTitle}>
              {tr.contribute.unknowns}
            </h3>
            <p className={s.hint}>{tr.contribute.unknownsHint}</p>
            {v.unknowns.map((u, i) => (
              <div key={i} className={s.unknownRow}>
                <Input aria-label={tr.contribute.unknownN(i + 1)} value={u} onChange={(e) => update({ unknowns: v.unknowns.map((x, k) => (k === i ? e.target.value : x)) })} />
                <IconButton label={tr.contribute.unknownRemove(i + 1)} onClick={() => update({ unknowns: v.unknowns.filter((_, k) => k !== i) })}>
                  <X size={16} aria-hidden />
                </IconButton>
              </div>
            ))}
            <div>
              <Button size="sm" icon={<Plus size={15} aria-hidden />} onClick={() => update({ unknowns: [...v.unknowns, ''] })}>
                {tr.contribute.unknownAdd}
              </Button>
            </div>
          </section>
        </div>
      </details>

      <div className={s.saveBar}>
        {selfPublish ? (
          <Button variant="primary" icon={<Upload size={16} aria-hidden />} loading={busy === 'publish'} disabled={!!busy || imageBusy > 0 || !project.data} onClick={() => save('publish')}>
            {tr.publishCheck.publish}
          </Button>
        ) : (
          <Button variant="primary" icon={<Send size={16} aria-hidden />} loading={busy === 'submit'} disabled={!!busy || imageBusy > 0 || !project.data} onClick={() => save('submit')}>
            {tr.contribute.saveSubmit}
          </Button>
        )}
        <Button loading={busy === 'save'} disabled={!!busy || imageBusy > 0} onClick={() => save('save')}>
          {tr.contribute.save}
        </Button>
        {selfPublish && <p className={s.saveHint}>{tr.publishCheck.hint}</p>}
      </div>
      {flow.dialog(onReopen)}
    </div>
  );
}
