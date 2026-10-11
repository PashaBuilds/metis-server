/**
 * İnce fetch sarmalayıcı. Tipler `schema.d.ts`'ten (openapi-typescript, backend OpenAPI'sinden üretilir).
 * CSRF belirteci /auth/me cevabından alınır; mutasyonlarda X-CSRF-Token başlığıyla gönderilir.
 */

import type { components } from './schema';

export type Schemas = components['schemas'];

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public correlationId: string,
    public details: Record<string, unknown> = {},
    public retryable = false,
  ) {
    super(message);
  }

  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    const fields = (this.details.fields as { field: string; type: string }[] | undefined) ?? [];
    for (const f of fields) out[f.field] = f.type;
    if (typeof this.details.field === 'string') out[this.details.field] = this.code;
    return out;
  }
}

let csrfToken = '';
export function setCsrfToken(token: string) {
  csrfToken = token;
}

type Query = Record<string, string | number | boolean | null | undefined | string[]>;

function buildUrl(path: string, query?: Query): string {
  const url = new URL(`/api/v1${path}`, window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === '') continue;
      if (Array.isArray(v)) v.forEach((x) => url.searchParams.append(k, x));
      else url.searchParams.set(k, String(v));
    }
  }
  return url.pathname + url.search;
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as { error?: { code: string; message: string; correlation_id: string; details: Record<string, unknown>; retryable: boolean } };
    if (body.error) return new ApiError(res.status, body.error.code, body.error.message, body.error.correlation_id, body.error.details, body.error.retryable);
  } catch {
    /* JSON değil */
  }
  return new ApiError(res.status, res.status >= 500 ? 'INTERNAL' : 'VALIDATION_ERROR', res.statusText, res.headers.get('x-request-id') ?? '');
}

export interface RequestOptions {
  query?: Query;
  body?: unknown;
  form?: FormData;
  idempotencyKey?: string;
  signal?: AbortSignal;
}

export async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (method !== 'GET' && method !== 'HEAD') headers['X-CSRF-Token'] = csrfToken;
  if (opts.idempotencyKey) headers['Idempotency-Key'] = opts.idempotencyKey;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), { method, headers, body, credentials: 'same-origin', signal: opts.signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    throw new ApiError(0, 'NETWORK', 'network error', '');
  }
  if (!res.ok) {
    const err = await parseError(res);
    if (err.code === 'UNAUTHENTICATED') window.dispatchEvent(new CustomEvent('metis:unauthenticated'));
    if (err.code === 'PASSWORD_CHANGE_REQUIRED') window.dispatchEvent(new CustomEvent('metis:password-change'));
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** POST + text/event-stream (mentor akışı). Hata cevabı ApiError olarak fırlatılır. */
export async function postStream(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(buildUrl(path), {
      method: 'POST',
      headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
      body: JSON.stringify(body),
      credentials: 'same-origin',
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    throw new ApiError(0, 'NETWORK', 'network error', '');
  }
  if (!res.ok) {
    const err = await parseError(res);
    if (err.code === 'UNAUTHENTICATED') window.dispatchEvent(new CustomEvent('metis:unauthenticated'));
    throw err;
  }
  return res;
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>('GET', path, { query, signal }),
  post: <T>(path: string, body?: unknown, opts: Omit<RequestOptions, 'body'> = {}) => request<T>('POST', path, { ...opts, body }),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, { body }),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, { body }),
  del: <T = void>(path: string) => request<T>('DELETE', path),
  upload: <T>(path: string, form: FormData) => request<T>('POST', path, { form }),
};

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
