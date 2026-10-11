/**
 * SSE okuyucu (fetch tabanlı; POST destekler). Last-Event-ID ile yeniden bağlanma.
 */

export interface SseEvent {
  id: string | null;
  event: string;
  data: string;
}

export async function* readSse(response: Response): AsyncGenerator<SseEvent> {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.search(/\r?\n\r?\n/)) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx).replace(/^\r?\n\r?\n/, '');
      let id: string | null = null;
      let event = 'message';
      const data: string[] = [];
      for (const line of chunk.split(/\r?\n/)) {
        if (line.startsWith(':')) continue;
        const colon = line.indexOf(':');
        const field = colon < 0 ? line : line.slice(0, colon);
        const val = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '');
        if (field === 'id') id = val;
        else if (field === 'event') event = val;
        else if (field === 'data') data.push(val);
      }
      if (data.length || event !== 'message') yield { id, event, data: data.join('\n') };
    }
  }
}

/** GET SSE akışını izler; koparsa Last-Event-ID ile yeniden bağlanır. */
export function subscribeSse(url: string, onEvent: (e: SseEvent) => void, opts: { signal: AbortSignal; isDone?: (e: SseEvent) => boolean }) {
  let lastId: string | null = null;
  let stopped = false;
  (async () => {
    let backoff = 500;
    while (!stopped && !opts.signal.aborted) {
      try {
        const res = await fetch(url, {
          headers: { Accept: 'text/event-stream', ...(lastId ? { 'Last-Event-ID': lastId } : {}) },
          credentials: 'same-origin',
          signal: opts.signal,
        });
        if (!res.ok) throw new Error(String(res.status));
        backoff = 500;
        for await (const ev of readSse(res)) {
          if (ev.id) lastId = ev.id;
          if (ev.event === 'heartbeat') continue;
          onEvent(ev);
          if (opts.isDone?.(ev)) {
            stopped = true;
            return;
          }
        }
      } catch {
        if (opts.signal.aborted) return;
      }
      await new Promise((r) => setTimeout(r, backoff));
      backoff = Math.min(backoff * 2, 8000);
    }
  })();
}
