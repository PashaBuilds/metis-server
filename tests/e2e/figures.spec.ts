import { expect, test, type Browser, type Page } from '@playwright/test';
import { BASE, apiCall, apiLogin, PDF_FILE, PNG_FILE } from './helpers';

/**
 * Ekler ve yayın öncesi kontrol (2026-10-19, tek adımda taslak). Yazar taslağa iki ek ekler, birini kaldırır, kaydeder;
 * kayıtta kalan ek görünür. Ardından yayın öncesi kontrol: yayındaki bilgiyle çelişen taslak uyarı penceresi açar,
 * "Yine de yayımla" çelişkiyi Bilgi sağlığına kaydeder. Kullanıcılar önceki testlerden (kurulum, inceleme) gelir.
 */

async function userPage(browser: Browser, username: string, password: string): Promise<Page> {
  const ctx = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await apiLogin(page.request, username, password);
  return page;
}

test('taslağa iki ek → birini kaldır → kaydet → kayıtta kalan ek', async ({ browser }) => {
  const author = await userPage(browser, 'yazar', 'Yazar-Parola-2026-x');
  await author.goto('/katki');
  await author.getByLabel('Başlık').fill('Kart görünümü notu');
  await author.getByRole('textbox', { name: 'Not', exact: true }).fill('Konnektörün yeri 1. görselde işaretli.');
  await author.locator('input[type=file]').setInputFiles([PNG_FILE, PDF_FILE]);
  await expect(author.getByText(PDF_FILE.name)).toBeVisible();
  await author.getByRole('button', { name: `Eki kaldır: ${PDF_FILE.name}` }).click();
  await expect(author.getByText(PDF_FILE.name)).toHaveCount(0);
  // İzin verilmeyen tür seçilirse yüklenmez, açık hata gösterilir.
  await author.locator('input[type=file]').setInputFiles({ name: 'not.docx', mimeType: 'application/octet-stream', buffer: Buffer.from('PK\u0003\u0004') });
  await expect(author.getByText('Bu dosya türü eklenemez: not.docx')).toBeVisible();
  await author.getByRole('button', { name: 'Taslağı kaydet' }).click();
  await expect(author).toHaveURL(/\/kayitlar\/[0-9a-f-]{36}$/);
  await expect(author.getByRole('heading', { name: 'Ekler (1)' })).toBeVisible();
  await expect(author.getByRole('link', { name: PNG_FILE.name })).toBeVisible();
});

type Change = { id: string; hash: string; published_page_ids: string[] };

/** Not tabanlı taslak (API): not kendiliğinden dayanak olur. */
async function apiDraft(page: Page, projectId: string, scope: unknown, title: string, statement: string): Promise<Change> {
  const item = { note: true, title, summary: '', body_md: statement, kind: 'concept', scope };
  return apiCall<Change>(page.request, 'POST', `/projects/${projectId}/changes`, { summary: title, items: [item] });
}

async function existingScope(author: Page): Promise<{ projectId: string; scope: unknown }> {
  const me = await apiCall<{ memberships: { project_id: string }[] }>(author.request, 'GET', '/auth/me');
  const projectId = me.memberships[0]!.project_id;
  const list = await apiCall<{ items: { page_id: string }[] }>(author.request, 'GET', `/projects/${projectId}/pages`);
  const existing = await apiCall<{ revision: { scope: unknown } }>(author.request, 'GET', `/pages/${list.items[0]!.page_id}`);
  return { projectId, scope: existing.revision.scope };
}

test('yayın öncesi kontrol: çelişen taslak uyarır → yine de yayımla → Bilgi sağlığında bulgu', async ({ browser }) => {
  const author = await userPage(browser, 'yazar', 'Yazar-Parola-2026-x');
  const { projectId, scope } = await existingScope(author);

  // Yayında: köprü saati 125 MHz (kurgusal). Taslak: aynı özellik için 250 MHz.
  const first = await apiDraft(author, projectId, scope, 'Köprü saati (eski ölçüm)', 'Köprü saat frekansı 125 MHz değerindedir.');
  const check = await apiCall<{ hash: string; issues: unknown[] }>(author.request, 'POST', `/changes/${first.id}/check`);
  expect(check.issues).toHaveLength(0);
  await apiCall(author.request, 'POST', `/changes/${first.id}/publish-direct`, { hash: first.hash });
  const second = await apiDraft(author, projectId, scope, 'Köprü saati (yeni ölçüm)', 'Köprü saat frekansı 250 MHz değerindedir.');

  await author.goto(`/kayitlar/${second.id}`);
  await author.getByRole('button', { name: 'Yayımla', exact: true }).click();
  const dialog = author.getByRole('dialog', { name: 'Yayımlamadan önce bak' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText('Çelişebilir')).toBeVisible();
  await expect(dialog.getByRole('link', { name: /Köprü saati \(eski ölçüm\)/ })).toBeVisible();
  await expect(dialog.getByText('Köprü saat frekansı 125 MHz değerindedir.')).toBeVisible();
  await expect(dialog.getByText('Köprü saat frekansı 250 MHz değerindedir.')).toBeVisible();
  await expect(dialog.getByText(/yalnız kural kontrolü yapıldı/)).toBeVisible();
  // Taslağa dön: hiçbir şey yayımlanmaz.
  await dialog.getByRole('button', { name: 'Taslağa dön' }).click();
  await expect(dialog).toBeHidden();
  await expect(author.getByText('Taslak', { exact: true }).first()).toBeVisible();
  // Yine de yayımla → yayımlanır, çelişki Bilgi sağlığına düşer.
  await author.getByRole('button', { name: 'Yayımla', exact: true }).click();
  await author.getByRole('dialog', { name: 'Yayımlamadan önce bak' }).getByRole('button', { name: 'Yine de yayımla' }).click();
  await expect(author.getByRole('link', { name: 'Yayımlanan bilgiyi aç' })).toBeVisible();
  await author.goto('/saglik');
  const finding = author.getByRole('listitem').filter({ hasText: 'Köprü saati (yeni ölçüm)' });
  await expect(finding.first()).toBeVisible();
});

test('editörde uyarı → Taslağa dön → düzenle → yeniden yayımla (güncel içerikle yeniden kontrol)', async ({ browser }) => {
  const author = await userPage(browser, 'yazar', 'Yazar-Parola-2026-x');
  const { projectId, scope } = await existingScope(author);
  const draft = await apiDraft(author, projectId, scope, 'Köprü saati (üçüncü ölçüm)', 'Köprü saat frekansı 500 MHz değerindedir.');

  await author.goto(`/katki?change=${draft.id}`);
  await expect(author.getByLabel('Başlık')).toHaveValue('Köprü saati (üçüncü ölçüm)');
  await author.getByRole('button', { name: 'Yayımla', exact: true }).click();
  const dialog = author.getByRole('dialog', { name: 'Yayımlamadan önce bak' });
  await expect(dialog.getByText('Çelişebilir').first()).toBeVisible();
  await dialog.getByRole('button', { name: 'Taslağa dön' }).click();
  await expect(dialog).toBeHidden();
  await expect(author).toHaveURL(new RegExp(`/katki\\?change=${draft.id}`));
  await author.getByText('Diğer alanlar').click();
  await author.getByLabel('Özet').fill('Ölçüm farklı bir kart revizyonunda yapıldı.');
  await author.getByRole('button', { name: 'Yayımla', exact: true }).click();
  await author.getByRole('dialog', { name: 'Yayımlamadan önce bak' }).getByRole('button', { name: 'Yine de yayımla' }).click();
  await expect(author).toHaveURL(/\/bilgi\/[0-9a-f-]{36}/);
  await expect(author.getByText('Ölçüm farklı bir kart revizyonunda yapıldı.')).toBeVisible();
});
