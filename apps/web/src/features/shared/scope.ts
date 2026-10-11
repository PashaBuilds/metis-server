import type { ScopeSel } from '@/app/session';

const DIMS = ['domain', 'yatt', 'kart', 'proje'] as const;

/** API'nin serbest `scope` nesnesini tipli kapsam seçimine çevirir. */
export function asScope(obj: Record<string, unknown> | null | undefined): ScopeSel {
  const out: ScopeSel = { domain: [], yatt: [], kart: [], proje: [] };
  if (!obj) return out;
  for (const d of DIMS) {
    const v = obj[d];
    if (Array.isArray(v)) out[d] = v.filter((x): x is string => typeof x === 'string');
  }
  return out;
}

export function sameScope(a: ScopeSel, b: ScopeSel): boolean {
  return DIMS.every((d) => [...a[d]].sort().join('|') === [...b[d]].sort().join('|'));
}
