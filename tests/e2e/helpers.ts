import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { expect, type APIRequestContext, type Page } from '@playwright/test';

export const ROOT = path.resolve(__dirname, '../..');
export const BASE = 'http://localhost:8001';
export const ADMIN = { username: 'yonetici', password: 'E2e-Yonetici-Parola-2026', name: 'E2E Yönetici' };
export const PROJECT = 'E2E projesi';
export const SOURCE_TITLE = 'E2E kesme notu';
export const QUOTE = 'Kesme maskesi IMR kaydında tutulur.';
export const NOTE = `AXI kesme yönetimi — kurgusal uzman notu\n\nKöprü MSI kesmelerini IntrEnable çağrısıyla etkinleştirir.\n${QUOTE}\nISR içinde yalnız durum bitleri temizlenir.`;

/** e2e-server.sh'in yazdığı ortam (aynı veritabanı) ile metis setup-code çalıştırır. */
export function setupCode(): string {
  const file = process.env.METIS_E2E_ENV_FILE ?? '/tmp/metis-e2e.env';
  const env: Record<string, string> = { ...process.env } as Record<string, string>;
  for (const line of fs.readFileSync(file, 'utf8').split('\n')) {
    const i = line.indexOf('=');
    if (i > 0) env[line.slice(0, i)] = line.slice(i + 1);
  }
  const out = execFileSync(path.join(ROOT, '.venv/bin/metis'), ['setup-code'], { cwd: ROOT, env, encoding: 'utf8' });
  const lines = out.trim().split('\n');
  return lines[lines.length - 1]!.trim();
}

interface Me {
  csrf_token: string;
  user: { id: string; must_change_password: boolean };
  memberships: { project_id: string; project_name: string }[];
}

/** Bağlamın çerezleriyle API çağrısı (CSRF + Origin başlıklarıyla). */
export async function apiCall<T>(request: APIRequestContext, method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE', url: string, data?: unknown): Promise<T> {
  const me = method === 'GET' ? null : await request.get(`${BASE}/api/v1/auth/me`).then((r) => r.json() as Promise<Me>);
  const res = await request.fetch(`${BASE}/api/v1${url}`, {
    method,
    data,
    headers: { Origin: BASE, ...(me ? { 'X-CSRF-Token': me.csrf_token } : {}) },
  });
  if (!res.ok()) throw new Error(`${method} ${url} → ${res.status()} ${await res.text()}`);
  return (res.status() === 204 ? undefined : await res.json()) as T;
}

export async function apiLogin(request: APIRequestContext, username: string, password: string, newPassword?: string): Promise<Me> {
  const res = await request.post(`${BASE}/api/v1/auth/login`, { data: { username, password }, headers: { Origin: BASE } });
  expect(res.ok(), await res.text()).toBeTruthy();
  let me = (await res.json()) as Me;
  if (me.user.must_change_password && newPassword) {
    me = await apiCall<Me>(request, 'POST', '/auth/password', { current_password: password, new_password: newPassword });
  }
  return me;
}

/** Yönetici olarak yeni kullanıcı oluşturur ve projede rol verir. */
export async function createMember(adminRequest: APIRequestContext, projectId: string, username: string, displayName: string, roles: string[], tempPassword: string) {
  const user = await apiCall<{ id: string }>(adminRequest, 'POST', '/users', { username, display_name: displayName, temporary_password: tempPassword, is_admin: false });
  await apiCall(adminRequest, 'PUT', `/projects/${projectId}/members`, { user_id: user.id, roles });
  return user;
}

/** Kaynak görüntüleyicide verilen metni seçer (gerçek kullanıcı seçimi gibi Selection API ile). */
export async function selectInViewer(page: Page, text: string) {
  const viewer = page.getByTestId('source-viewer');
  await expect(viewer).toContainText(text);
  await viewer.evaluate((el, needle) => {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node: Node | null;
    while ((node = walker.nextNode())) {
      const idx = node.textContent?.indexOf(needle) ?? -1;
      if (idx >= 0) {
        const range = document.createRange();
        range.setStart(node, idx);
        range.setEnd(node, idx + needle.length);
        const sel = window.getSelection()!;
        sel.removeAllRanges();
        sel.addRange(range);
        return;
      }
    }
    throw new Error('metin bulunamadı');
  }, text);
}
