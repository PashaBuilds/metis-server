import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';

export interface IzTarget {
  /** Benzersiz işaret anahtarı (ör. `${claimId}:${evidenceId}`). */
  key: string;
  evidenceId: string;
  label?: string;
  quote?: string;
  /** İddia kimliği: verilirse İz paneli iddianın tam alıntısını vurgular. */
  claimId?: string;
}

export interface EvidenceView {
  evidence_id: string;
  source: { id: string; title: string; kind: string };
  revision: {
    id: string;
    number: number;
    created_at: string;
    author_name: string | null;
    filename: string;
    media_type: string;
    sha256: string;
    extraction: string;
    is_current: boolean;
  };
  locator: Record<string, unknown>;
  locator_label: string;
  excerpt: string;
  text: string;
  highlight: { start: number; end: number } | null;
  can_download: boolean;
  project_id: string;
}

export type EvidenceResolver = (target: IzTarget) => Promise<EvidenceView>;

interface IzState {
  active: (IzTarget & { marker: HTMLElement | null }) | null;
  open: (target: IzTarget, marker: HTMLElement | null) => void;
  close: () => void;
  resolver: EvidenceResolver | null;
  setResolver: (r: EvidenceResolver | null) => void;
}

const Ctx = createContext<IzState | null>(null);

export function IzProvider({ children, resolver: initial = null }: { children: ReactNode; resolver?: EvidenceResolver | null }) {
  const [active, setActive] = useState<IzState['active']>(null);
  const [resolver, setResolverState] = useState<EvidenceResolver | null>(() => initial);
  const lastMarker = useRef<HTMLElement | null>(null);
  const open = useCallback((target: IzTarget, marker: HTMLElement | null) => {
    lastMarker.current = marker;
    setActive({ ...target, marker });
  }, []);
  const close = useCallback(() => {
    setActive(null);
    // Esc/kapatma odağı işarete döndürür.
    const marker = lastMarker.current;
    if (marker && document.contains(marker)) window.requestAnimationFrame(() => marker.focus());
  }, []);
  const setResolver = useCallback((r: EvidenceResolver | null) => setResolverState(() => r), []);
  const value = useMemo(() => ({ active, open, close, resolver, setResolver }), [active, open, close, resolver, setResolver]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useIz(): IzState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('IzProvider eksik');
  return ctx;
}
