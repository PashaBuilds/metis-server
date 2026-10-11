import { useQuery } from '@tanstack/react-query';
import { useToast } from '@/design/primitives';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';

export function messageOf(e: unknown): string {
  return e instanceof ApiError ? errorMessage(e.code) : errorMessage('NETWORK');
}

export function useProject(projectId: string | null) {
  return useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.get<Schemas['ProjectOut']>(`/projects/${projectId}`),
    enabled: !!projectId,
    staleTime: 60_000,
  });
}

export interface InboxCounts {
  reviews_waiting: number;
  questions_waiting: number;
  open_findings: number;
}

export function useInbox(projectId: string | null) {
  return useQuery({
    queryKey: ['inbox', projectId],
    queryFn: () => api.get<InboxCounts>(`/projects/${projectId}/inbox`),
    enabled: !!projectId,
    refetchInterval: 30_000,
  });
}

/** Sil → "Silindi" toast'u, 8 sn "Geri al" (geri yükleme uç noktası). */
export function useUndoableDelete() {
  const toast = useToast();
  return async function run(opts: { del: () => Promise<unknown>; restore: () => Promise<unknown>; onDone?: () => void; onRestored?: () => void }) {
    try {
      await opts.del();
    } catch (e) {
      toast.show(messageOf(e), { tone: 'error' });
      throw e;
    }
    opts.onDone?.();
    toast.show(tr.common.deleted, {
      undo: async () => {
        try {
          await opts.restore();
          opts.onRestored?.();
        } catch (e) {
          toast.show(messageOf(e), { tone: 'error' });
        }
      },
    });
  };
}
