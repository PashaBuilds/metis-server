import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from 'react';
import { api, ApiError, setCsrfToken, type Schemas } from '@/lib/api/client';

export type Me = Schemas['MeOut'];
export type ScopeSel = { domain: string[]; yatt: string[]; kart: string[]; proje: string[] };
export const EMPTY_SCOPE: ScopeSel = { domain: [], yatt: [], kart: [], proje: [] };

interface SessionState {
  me: Me | null;
  loading: boolean;
  projectId: string | null;
  project: Me['memberships'][number] | null;
  roles: Set<string>;
  isAdmin: boolean;
  scope: ScopeSel;
  setProject: (id: string) => void;
  setScope: (scope: ScopeSel) => void;
  pref: <T>(key: string, fallback: T) => T;
  setPref: (key: string, value: unknown) => void;
  refresh: () => Promise<unknown>;
}

const Ctx = createContext<SessionState | null>(null);

export function useMeQuery() {
  return useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      try {
        const me = await api.get<Me>('/auth/me');
        setCsrfToken(me.csrf_token);
        return me;
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
    retry: (count, e) => !(e instanceof ApiError) && count < 2,
  });
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useMeQuery();
  const me = q.data ?? null;

  useEffect(() => {
    const onUnauth = () => qc.setQueryData(['me'], null);
    const onPw = () => qc.invalidateQueries({ queryKey: ['me'] });
    window.addEventListener('metis:unauthenticated', onUnauth);
    window.addEventListener('metis:password-change', onPw);
    return () => {
      window.removeEventListener('metis:unauthenticated', onUnauth);
      window.removeEventListener('metis:password-change', onPw);
    };
  }, [qc]);

  const prefMutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) => api.put(`/preferences/${key}`, { value }),
  });

  const setPref = useCallback(
    (key: string, value: unknown) => {
      qc.setQueryData<Me | null>(['me'], (old) => (old ? { ...old, preferences: { ...old.preferences, [key]: value } } : old));
      prefMutation.mutate({ key, value });
    },
    [qc, prefMutation],
  );

  const pref = useCallback(<T,>(key: string, fallback: T): T => {
    const v = me?.preferences?.[key];
    return (v === undefined || v === null ? fallback : v) as T;
  }, [me]);

  const value = useMemo<SessionState>(() => {
    const memberships = me?.memberships ?? [];
    const preferred = (me?.preferences?.active_project_id as string | undefined) ?? null;
    const project = memberships.find((m) => m.project_id === preferred) ?? memberships[0] ?? null;
    const scopes = (me?.preferences?.active_scope as Record<string, ScopeSel> | undefined) ?? {};
    const scope = (project && scopes[project.project_id]) || EMPTY_SCOPE;
    const isAdmin = !!me?.user.is_admin;
    const roles = new Set<string>(project?.roles ?? []);
    if (isAdmin) ['reader', 'contributor', 'reviewer', 'steward'].forEach((r) => roles.add(r));
    if (roles.has('steward')) ['reviewer', 'contributor', 'reader'].forEach((r) => roles.add(r));
    if (roles.has('contributor') || roles.has('reviewer')) roles.add('reader');
    return {
      me,
      loading: q.isLoading,
      projectId: project?.project_id ?? null,
      project,
      roles,
      isAdmin,
      scope,
      setProject: (id) => setPref('active_project_id', id),
      setScope: (next) => {
        if (!project) return;
        setPref('active_scope', { ...scopes, [project.project_id]: next });
      },
      pref,
      setPref,
      refresh: () => qc.invalidateQueries({ queryKey: ['me'] }),
    };
  }, [me, q.isLoading, setPref, pref, qc]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('SessionProvider eksik');
  return ctx;
}

export function scopeIsEmpty(scope: ScopeSel): boolean {
  return Object.values(scope).every((v) => v.length === 0);
}
