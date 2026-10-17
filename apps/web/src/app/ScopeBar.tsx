import * as Popover from '@radix-ui/react-popover';
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { SlidersHorizontal } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Button, Checkbox, Chip, Dialog } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { EMPTY_SCOPE, useSession, type ScopeSel } from './session';
import s from './ScopeBar.module.css';

export const DIMS = ['domain', 'yatt', 'kart', 'proje'] as const;
export type Dim = (typeof DIMS)[number];

export function useCatalog(projectId: string | null) {
  return useQuery({
    queryKey: ['scopes', projectId],
    queryFn: () => api.get<Schemas['CatalogOut']>(`/projects/${projectId}/scopes`),
    enabled: !!projectId,
    staleTime: 60_000,
  });
}

/**
 * Kapsam seçici penceresi. Kabukta bir kez bağlanır; kapsamı kullanan ekranlar (soru kutusu, Mentor,
 * Harita, komut paleti) `metis:open-scope` olayıyla açar. Üst çubukta ayrıca kapsam gösterilmez:
 * kapsam yalnız onu kullanan ekranlarda görünür.
 */
export function ScopeDialog() {
  const session = useSession();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener('metis:open-scope', onOpen);
    return () => window.removeEventListener('metis:open-scope', onOpen);
  }, []);
  if (!session.projectId) return null;
  return (
    <Dialog open={open} onOpenChange={setOpen} title={tr.scope.pick} width={640}>
      <ScopePicker value={session.scope} onChange={session.setScope} onDone={() => setOpen(false)} />
    </Dialog>
  );
}

export function ScopePicker({ value, onChange, onDone, allowIndependent = false }: { value: ScopeSel; onChange: (s: ScopeSel) => void; onDone?: () => void; allowIndependent?: boolean }) {
  const session = useSession();
  const catalog = useCatalog(session.projectId);
  const toggle = (d: Dim, v: string, on: boolean) => {
    let next = value[d].filter((x) => x !== v && (v === '*' ? false : x !== '*'));
    if (on) next = v === '*' ? ['*'] : [...next, v];
    onChange({ ...value, [d]: next });
  };
  return (
    <div className={s.picker}>
      <div className={s.grid}>
        {DIMS.map((d) => {
          const values = catalog.data?.[d] ?? [];
          return (
            <fieldset key={d} className={s.dim}>
              <legend className={s.legend}>{tr.scope.dims[d]}</legend>
              {allowIndependent && (
                <Checkbox label={tr.scope.independent} checked={value[d].includes('*')} onChange={(on) => toggle(d, '*', on)} />
              )}
              {values.length === 0 && <p className={s.none}>{tr.scope.noValues}</p>}
              {values.map((v) => (
                <Checkbox key={v.id} label={v.value} checked={value[d].includes(v.value)} disabled={value[d].includes('*')} onChange={(on) => toggle(d, v.value, on)} />
              ))}
            </fieldset>
          );
        })}
      </div>
      <div className={s.footer}>
        <Link to="/ayarlar" search={{ tab: 'kapsam' }} className={s.manage} onClick={onDone}>
          {tr.scope.manage}
        </Link>
        <div className={s.footerActions}>
          <Button size="sm" variant="ghost" onClick={() => onChange(EMPTY_SCOPE)}>
            {tr.scope.clear}
          </Button>
          {onDone && (
            <Button size="sm" variant="primary" onClick={onDone}>
              {tr.common.done}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Formlarda kapsam: seçili değerler çip olarak görünür, seçim açılır panelde yapılır. */
export function ScopeField({ value, onChange, allowIndependent = false }: { value: ScopeSel; onChange: (s: ScopeSel) => void; allowIndependent?: boolean }) {
  const [open, setOpen] = useState(false);
  const empty = DIMS.every((d) => value[d].length === 0);
  return (
    <div className={s.fieldLine}>
      {empty ? <span className={s.fieldEmpty}>{tr.scope.unspecified}</span> : <ScopeChips scope={value} />}
      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger asChild>
          <Button size="sm" icon={<SlidersHorizontal size={15} aria-hidden />}>
            {tr.scope.pick}
          </Button>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content className={s.fieldPop} sideOffset={6} align="start" collisionPadding={12}>
            <ScopePicker value={value} onChange={onChange} onDone={() => setOpen(false)} allowIndependent={allowIndependent} />
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </div>
  );
}

export function ScopeChips({ scope, empty = 'unspecified' }: { scope: Partial<ScopeSel> | null | undefined; empty?: 'unspecified' | 'hide' }) {
  const items = DIMS.map((d) => ({ d, vals: scope?.[d] ?? [] }));
  return (
    <span className={s.chips}>
      {items.map(({ d, vals }) =>
        vals.length === 0 ? (
          empty === 'hide' ? null : null
        ) : (
          <Chip key={d} label={tr.scope.dims[d]} tone="muted">
            {vals.includes('*') ? tr.scope.independent : vals.join(', ')}
          </Chip>
        ),
      )}
    </span>
  );
}
