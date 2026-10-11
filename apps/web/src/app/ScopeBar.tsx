import * as Popover from '@radix-ui/react-popover';
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { Plus, SlidersHorizontal } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Button, Checkbox, Chip } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { useMediaQuery } from '@/lib/hooks';
import { EMPTY_SCOPE, scopeIsEmpty, useSession, type ScopeSel } from './session';
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

/** Üst çubuktaki aktif kapsam chip'leri; tıklayınca kapsam seçici açılır. */
export function ScopeBar() {
  const session = useSession();
  const mobile = useMediaQuery('(max-width: 759px)');
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener('metis:open-scope', onOpen);
    return () => window.removeEventListener('metis:open-scope', onOpen);
  }, []);
  if (!session.projectId) return null;
  const scope = session.scope;
  const chips = DIMS.flatMap((d) => scope[d].map((v) => ({ d, v })));
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <div className={s.bar}>
        {!mobile &&
          chips.slice(0, 4).map(({ d, v }) => (
            <Chip
              key={d + v}
              label={tr.scope.dims[d]}
              onRemove={() => session.setScope({ ...scope, [d]: scope[d].filter((x) => x !== v) })}
            >
              {v}
            </Chip>
          ))}
        {!mobile && chips.length > 4 && <span className={s.more}>+{chips.length - 4}</span>}
        <Popover.Trigger asChild>
          <button type="button" className={s.trigger} aria-label={tr.scope.pick}>
            {scopeIsEmpty(scope) ? <SlidersHorizontal size={15} aria-hidden /> : <Plus size={15} aria-hidden />}
            <span className={mobile ? 'sr-only' : undefined}>{scopeIsEmpty(scope) ? tr.scope.all : tr.scope.label}</span>
            {mobile && chips.length > 0 && <span className={s.count}>{chips.length}</span>}
          </button>
        </Popover.Trigger>
      </div>
      <Popover.Portal>
        <Popover.Content className={s.popover} sideOffset={8} align="start" collisionPadding={12}>
          <ScopePicker value={scope} onChange={session.setScope} onDone={() => setOpen(false)} />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
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
              Tamam
            </Button>
          )}
        </div>
      </div>
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
