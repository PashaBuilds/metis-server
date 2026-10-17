import { useQuery } from '@tanstack/react-query';
import { ArrowRight, FilePlus2, FileUp, RefreshCw, Search, X } from 'lucide-react';
import { useEffect, useRef, useState, type DragEvent, type FormEvent } from 'react';
import { Button, Field, Input, Segmented, Select, SkeletonRows, Textarea, useToast } from '@/design/primitives';
import { SourceKindIcon } from '@/design/iz';
import { ScopeField } from '@/app/ScopeBar';
import { EMPTY_SCOPE, useSession, type ScopeSel } from '@/app/session';
import { errorMessage, sourceKindLabel, tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { formatBytes, formatDateTime } from '@/lib/format';
import { useDebounced } from '@/lib/hooks';
import { Banner } from '@/features/shared/Banner';
import { SOURCE_KINDS } from '@/features/shared/kinds';
import { messageOf } from '@/features/shared/hooks';
import type { SourceDetail } from './types';
import s from './Contribute.module.css';

const MAX_BYTES = 10 * 1024 * 1024;

export function ExtractionNote({ extraction }: { extraction: string | undefined }) {
  if (!extraction) return null;
  const msg = tr.contribute.extraction[extraction];
  if (!msg) return null;
  if (extraction === 'complete') return <p className={s.extractOk}>{msg}</p>;
  return <Banner tone={extraction === 'annotation_only' ? 'celiski' : 'dikkat'}>{msg}</Banner>;
}

interface Props {
  selected: SourceDetail | null;
  onSelect: (id: string) => Promise<void>;
  onClear: () => void;
  /** Yalnız editör zaten açıkken (kaynağı değiştirmeye dönülünce) gösterilir. */
  onContinue?: () => void;
  onDirty: (dirty: boolean) => void;
  offerRevision: boolean;
  /** Yeni sürüm formu açıkken taslak yolları gizlenir. */
  onRevisionMode?: (open: boolean) => void;
}

export function SourceStep({ selected, onSelect, onClear, onContinue, onDirty, offerRevision, onRevisionMode }: Props) {
  const { projectId } = useSession();
  const [picked, setTab] = useState<'existing' | 'new' | null>(null);
  const [revisionOpen, setRevisionOpen] = useState(offerRevision);
  // Projede hiç kaynak yoksa doğrudan "Yeni kaynak" açılır (ExistingSources ile aynı sorgu, önbellekten gelir).
  const any = useQuery({
    queryKey: ['sources', projectId, ''],
    queryFn: () => api.get<Schemas['SourceListOut']>(`/projects/${projectId}/sources`, { q: '', limit: 50 }),
    enabled: !!projectId && !selected,
  });
  const tab = picked ?? (any.data && any.data.items.length === 0 ? 'new' : 'existing');
  const revisionMode = revisionOpen && !!selected;
  useEffect(() => onRevisionMode?.(revisionMode), [revisionMode, onRevisionMode]);

  if (selected) {
    const rev = selected.current_revision;
    return (
      <div className={s.selected}>
        <div className={s.selectedHead}>
          <SourceKindIcon kind={selected.kind} size={20} />
          <div className={s.selectedText}>
            <span className={s.selectedLabel}>{tr.contribute.selectedSource}</span>
            <strong className={s.selectedTitle}>{selected.title}</strong>
            <span className={s.selectedMeta}>
              <span>{sourceKindLabel(selected.kind)}</span>
              <span>{tr.contribute.revisionNo(selected.current_revision_no)}</span>
              {rev && <time dateTime={rev.created_at}>{formatDateTime(rev.created_at)}</time>}
            </span>
          </div>
        </div>
        <ExtractionNote extraction={rev?.extraction} />
        {revisionOpen ? (
          <RevisionForm
            source={selected}
            onCancel={() => setRevisionOpen(false)}
            onDone={async () => {
              setRevisionOpen(false);
              await onSelect(selected.id);
            }}
            onDirty={onDirty}
          />
        ) : (
          <div className={s.actions}>
            {onContinue && (
              <Button variant="primary" iconEnd={<ArrowRight size={16} aria-hidden />} onClick={onContinue}>
                {tr.contribute.continue}
              </Button>
            )}
            <Button icon={<RefreshCw size={15} aria-hidden />} onClick={() => setRevisionOpen(true)}>
              {tr.contribute.newRevision}
            </Button>
            <Button variant="ghost" onClick={onClear}>
              {tr.contribute.changeSource}
            </Button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={s.sourceStep}>
      <Segmented
        label={tr.contribute.stepSource}
        size="md"
        value={tab}
        onChange={setTab}
        options={[
          { value: 'existing', label: tr.contribute.existing },
          { value: 'new', label: tr.contribute.newSource },
        ]}
      />
      {tab === 'existing' ? <ExistingSources onSelect={onSelect} /> : <NewSourceForm onCreated={onSelect} onDirty={onDirty} />}
    </div>
  );
}

function ExistingSources({ onSelect }: { onSelect: (id: string) => Promise<void> }) {
  const { projectId } = useSession();
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 250);
  const [busy, setBusy] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ['sources', projectId, dq],
    queryFn: () => api.get<Schemas['SourceListOut']>(`/projects/${projectId}/sources`, { q: dq, limit: 50 }),
    enabled: !!projectId,
  });
  const items = list.data?.items ?? [];
  return (
    <div className={s.existing}>
      <div className={s.searchBox}>
        <Search size={16} aria-hidden className={s.searchIcon} />
        <Input type="search" aria-label={tr.contribute.sourceSearch} placeholder={tr.contribute.sourceSearchPlaceholder} value={q} onChange={(e) => setQ(e.target.value)} className={s.searchInput} />
      </div>
      {list.isLoading ? (
        <SkeletonRows rows={3} />
      ) : list.isError ? (
        <p className={s.error}>{messageOf(list.error)}</p>
      ) : items.length === 0 ? (
        <p className={s.muted}>{dq ? tr.contribute.sourceNone : tr.contribute.sourcesEmpty}</p>
      ) : (
        <ul className={s.sourceList}>
          {items.map((src) => (
            <li key={src.id}>
              <button
                type="button"
                className={s.sourceRow}
                disabled={!!busy}
                aria-busy={busy === src.id || undefined}
                onClick={async () => {
                  setBusy(src.id);
                  try {
                    await onSelect(src.id);
                  } finally {
                    setBusy(null);
                  }
                }}
              >
                <SourceKindIcon kind={src.kind} size={18} />
                <span className={s.sourceRowText}>
                  <span className={s.sourceRowTitle}>{src.title}</span>
                  <span className={s.sourceRowMeta}>
                    <span>{sourceKindLabel(src.kind)}</span>
                    <span>{tr.contribute.revisionNo(src.current_revision_no)}</span>
                    <span>{src.owner_name}</span>
                  </span>
                </span>
                <time className={s.time} dateTime={src.created_at}>
                  {formatDateTime(src.current_revision?.created_at ?? src.created_at)}
                </time>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FileDrop({ file, onFile, error }: { file: File | null; onFile: (f: File | null) => void; error: string | null }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    const f = e.dataTransfer.files[0];
    if (f) onFile(f);
  };
  return (
    <div
      className={[s.drop, over ? s.dropOver : '', error ? s.dropError : ''].join(' ')}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
    >
      <input
        ref={input}
        type="file"
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        accept=".pdf,.txt,.md,.markdown,.csv,.tsv,.json,.yaml,.yml,.xml,.c,.h,.cpp,.hpp,.cc,.py,.rs,.go,.js,.ts,.tsx,.vhd,.vhdl,.v,.sv,.tcl,.png,.jpg,.jpeg"
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
      />
      {file ? (
        <div className={s.fileChosen}>
          <FileUp size={18} aria-hidden />
          <span className={s.fileName}>{file.name}</span>
          <span className={s.time}>{formatBytes(file.size)}</span>
          <Button
            size="sm"
            variant="ghost"
            icon={<X size={15} aria-hidden />}
            onClick={() => {
              onFile(null);
              if (input.current) input.current.value = '';
            }}
          >
            {tr.contribute.removeFile}
          </Button>
        </div>
      ) : (
        <div className={s.dropEmpty}>
          <FileUp size={20} aria-hidden />
          <span>{tr.contribute.drop}</span>
          <span className={s.hint}>{tr.contribute.dropHint}</span>
          <Button size="sm" onClick={() => input.current?.click()}>
            {tr.contribute.chooseFile}
          </Button>
        </div>
      )}
      {error && (
        <p className={s.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

function NewSourceForm({ onCreated, onDirty }: { onCreated: (id: string) => Promise<void>; onDirty: (d: boolean) => void }) {
  const session = useSession();
  const toast = useToast();
  const [form, setForm] = useState({ title: '', kind: 'note', source_version: '', repository: '', commit: '', path: '', symbol: '', text: '' });
  const [scope, setScope] = useState<ScopeSel>(EMPTY_SCOPE);
  const [file, setFile] = useState<File | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => {
    setForm((f) => ({ ...f, [k]: e.target.value }));
    onDirty(true);
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const errs: Record<string, string> = {};
    if (!form.title.trim()) errs.title = tr.contribute.titleRequired;
    if (!file && !form.text.trim()) errs.content = tr.contribute.contentRequired;
    if (file && file.size > MAX_BYTES) errs.file = tr.contribute.fileTooLarge;
    setErrors(errs);
    setFormError(null);
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('meta', JSON.stringify({ ...form, title: form.title.trim(), scope }));
      if (file) fd.append('file', file);
      const res = await api.upload<Schemas['SourceRevisionCreated']>(`/projects/${session.projectId}/sources`, fd);
      onDirty(false);
      toast.show(tr.contribute.sourceAdded);
      await onCreated(res.source.id);
    } catch (err) {
      if (err instanceof ApiError) {
        const fe = err.fieldErrors();
        const mapped: Record<string, string> = {};
        for (const k of Object.keys(fe)) {
          if (k.endsWith('title')) mapped.title = errorMessage(err.code);
          if (k.startsWith('scope')) mapped.scope = errorMessage('SCOPE_INVALID');
        }
        if (err.code === 'FILE_TOO_LARGE' || err.code === 'UNSUPPORTED_FILE') mapped.file = errorMessage(err.code);
        if (err.code === 'SCOPE_INVALID') mapped.scope = errorMessage(err.code);
        setErrors(mapped);
        if (!Object.keys(mapped).length) setFormError(errorMessage(err.code));
      } else setFormError(errorMessage('NETWORK'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={s.form} onSubmit={submit} noValidate aria-label={tr.contribute.newSource}>
      {formError && <Banner tone="celiski">{formError}</Banner>}
      <div className={s.formRow}>
        <Field label={tr.contribute.fTitle} error={errors.title ?? null} className={s.grow}>
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} invalid={!!errors.title} value={form.title} onChange={set('title')} />}
        </Field>
        <Field label={tr.contribute.fKind}>
          {({ id }) => (
            <Select id={id} value={form.kind} onChange={set('kind')}>
              {SOURCE_KINDS.map((k) => (
                <option key={k} value={k}>
                  {sourceKindLabel(k)}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      <div className={s.contentPick} role="group" aria-label={tr.contribute.fFile}>
        <FileDrop
          file={file}
          onFile={(f) => {
            setFile(f);
            onDirty(true);
            setErrors((e) => ({ ...e, file: f && f.size > MAX_BYTES ? tr.contribute.fileTooLarge : '', content: '' }));
          }}
          error={errors.file || null}
        />
        <span className={s.or}>{tr.contribute.or}</span>
        <Field label={tr.contribute.fNote} hint={tr.contribute.fNoteHint} error={errors.content || null} className={s.grow}>
          {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} invalid={!!errors.content} rows={8} value={form.text} onChange={set('text')} />}
        </Field>
      </div>
      <section className={s.scopeBlock} aria-labelledby="src-scope-h">
        <h3 id="src-scope-h" className={s.subTitle}>
          {tr.contribute.fScope}
        </h3>
        <p className={s.hint}>{tr.contribute.fScopeHint}</p>
        <ScopeField
          value={scope}
          onChange={(sc) => {
            setScope(sc);
            onDirty(true);
          }}
          allowIndependent
        />
        {errors.scope && (
          <p className={s.error} role="alert">
            {errors.scope}
          </p>
        )}
      </section>
      <details className={s.extra}>
        <summary>{tr.contribute.extra}</summary>
        <div className={s.formRow}>
          <Field label={tr.contribute.fVersion} hint={tr.contribute.fVersionHint} className={s.grow}>
            {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} value={form.source_version} onChange={set('source_version')} />}
          </Field>
          {form.kind === 'code' && (
            <Field label={tr.contribute.fCommit} className={s.grow}>
              {({ id }) => <Input id={id} className="mono" value={form.commit} onChange={set('commit')} />}
            </Field>
          )}
        </div>
        {form.kind === 'code' && (
          <div className={s.formRow}>
            <Field label={tr.contribute.fRepository} className={s.grow}>
              {({ id }) => <Input id={id} value={form.repository} onChange={set('repository')} />}
            </Field>
            <Field label={tr.contribute.fPath} className={s.grow}>
              {({ id }) => <Input id={id} className="mono" value={form.path} onChange={set('path')} />}
            </Field>
            <Field label={tr.contribute.fSymbol} className={s.grow}>
              {({ id }) => <Input id={id} className="mono" value={form.symbol} onChange={set('symbol')} />}
            </Field>
          </div>
        )}
      </details>
      <div className={s.actions}>
        <Button type="submit" variant="primary" icon={<FilePlus2 size={16} aria-hidden />} loading={busy}>
          {tr.contribute.addSource}
        </Button>
      </div>
    </form>
  );
}

function RevisionForm({ source, onCancel, onDone, onDirty }: { source: SourceDetail; onCancel: () => void; onDone: () => Promise<void>; onDirty: (d: boolean) => void }) {
  const toast = useToast();
  const [text, setText] = useState('');
  const [version, setVersion] = useState('');
  const [commit, setCommit] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (!file && !text.trim()) {
      setError(tr.contribute.contentRequired);
      return;
    }
    if (file && file.size > MAX_BYTES) {
      setError(tr.contribute.fileTooLarge);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append('meta', JSON.stringify({ expected_revision: source.current_revision_no, text, source_version: version, commit }));
      if (file) fd.append('file', file);
      const res = await api.upload<Schemas['SourceRevisionCreated']>(`/sources/${source.id}/revisions`, fd);
      onDirty(false);
      toast.show(res.affected_pages.length ? `${tr.contribute.revisionAdded}. ${tr.contribute.affected(res.affected_pages.length)}` : tr.contribute.revisionAdded);
      await onDone();
    } catch (err) {
      if (err instanceof ApiError && err.code === 'REVISION_CONFLICT') setError(tr.contribute.revisionConflict);
      else setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className={s.form} onSubmit={submit} noValidate aria-label={tr.contribute.newRevision}>
      <h3 className={s.subTitle}>{tr.contribute.newRevision}</h3>
      <p className={s.hint}>{tr.contribute.revisionHint}</p>
      {error && <Banner tone="celiski">{error}</Banner>}
      <div className={s.formRow}>
        <Field label={tr.contribute.fVersion} className={s.grow}>
          {({ id }) => <Input id={id} value={version} onChange={(e) => setVersion(e.target.value)} />}
        </Field>
        {source.kind === 'code' && (
          <Field label={tr.contribute.fCommit} className={s.grow}>
            {({ id }) => <Input id={id} className="mono" value={commit} onChange={(e) => setCommit(e.target.value)} />}
          </Field>
        )}
      </div>
      <div className={s.contentPick}>
        <FileDrop
          file={file}
          onFile={(f) => {
            setFile(f);
            onDirty(true);
          }}
          error={null}
        />
        <span className={s.or}>{tr.contribute.or}</span>
        <Field label={tr.contribute.fNote} className={s.grow}>
          {({ id }) => (
            <Textarea
              id={id}
              rows={6}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                onDirty(true);
              }}
            />
          )}
        </Field>
      </div>
      <div className={s.actions}>
        <Button type="submit" variant="primary" loading={busy}>
          {tr.contribute.uploadRevision}
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          {tr.common.cancel}
        </Button>
      </div>
    </form>
  );
}
