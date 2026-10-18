import path from 'node:path';
import { expect, test, type Browser, type Page } from '@playwright/test';
import { BASE, apiCall, apiLogin, QUOTE, selectInViewer, SOURCE_TITLE } from './helpers';

/**
 * Açıklayıcı görsel: yazar taslakta görsel yükler (kaynak olarak saklanır), açıklama yazar; yer tutucu metne girer,
 * önizlemede görünür. Yazar yayımlar; bilgi sayfasında görsel metnin içindedir. Ardından yayın öncesi kontrol:
 * yayındaki bilgiyle çelişen taslak uyarı penceresi açar, "Yine de yayımla" çelişkiyi Bilgi sağlığına kaydeder.
 * Kullanıcılar ve kaynak önceki projelerden (kurulum, inceleme) gelir.
 */

const IMAGE = path.join(__dirname, 'fixtures', 'kurgusal-kart.png');
const CAPTION = 'Kurgusal kartın üstten görünümü';

async function userPage(browser: Browser, username: string, password: string): Promise<Page> {
  const ctx = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await apiLogin(page.request, username, password);
  return page;
}

test('taslağa görsel ekle → önizle → yayımla → bilgi sayfasında metin içinde', async ({ browser }) => {
  const author = await userPage(browser, 'yazar', 'Yazar-Parola-2026-x');
  const reviewer = await userPage(browser, 'denetci', 'Denetci-Parola-2026-x');

  await author.goto('/katki');
  await author.getByRole('button', { name: new RegExp(SOURCE_TITLE) }).click();
  await author.getByRole('button', { name: 'Yazmaya başla' }).click();
  await author.getByLabel('Başlık').fill('Kesme maskesi ve kart görünümü');
  await author.getByRole('textbox', { name: 'Açıklama', exact: true }).fill(`${QUOTE}\n\nKonnektörün yeri için görsele bak.`);
  await selectInViewer(author, QUOTE);
  await author.getByRole('button', { name: 'Bu alıntıyı iddiaya bağla' }).click();
  await expect(author.getByRole('textbox', { name: 'İddia 1' })).toHaveValue(QUOTE);

  // Görsel ekle: yeni görsel yükle + açıklama.
  await author.getByRole('button', { name: 'Görsel ekle' }).click();
  const dialog = author.getByRole('dialog', { name: 'Görsel ekle' });
  await dialog.getByRole('radio', { name: 'Yeni görsel yükle' }).click();
  await dialog.locator('input[type=file]').setInputFiles(IMAGE);
  await dialog.getByLabel('Açıklama').fill(CAPTION);
  await dialog.getByRole('button', { name: 'Görseli ekle' }).click();
  await expect(dialog).toBeHidden();
  await expect(author.getByRole('textbox', { name: 'Açıklama', exact: true })).toHaveValue(/görsele bak\.\n\n\{\{görsel 1\}\}$/);
  await expect(author.getByLabel('Görsel 1 · Açıklama')).toHaveValue(CAPTION);

  // Önizleme: görsel metnin içinde, açıklamasıyla.
  await author.getByRole('tab', { name: 'Önizle' }).click();
  await expect(author.getByRole('button', { name: `Büyüt: ${CAPTION}` })).toBeVisible();

  // Yazar yayımlar: yayın öncesi kontrol sorun bulmaz → bilgi sayfası açılır. Diğer üye de görseli görür.
  await author.getByRole('button', { name: 'Yayımla', exact: true }).click();
  await expect(author).toHaveURL(/\/bilgi\/[0-9a-f-]{36}/);
  await reviewer.goto(author.url());

  // Bilgi sayfası: görsel gerçekten yüklenir, açıklaması altında; tıklayınca büyük hâli açılır.
  await expect(reviewer.getByRole('heading', { level: 1, name: 'Kesme maskesi ve kart görünümü' })).toBeVisible();
  const img = reviewer.getByRole('img', { name: CAPTION }).first();
  await expect(img).toBeVisible();
  await expect.poll(() => img.evaluate((el) => (el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  await expect(reviewer.locator('figcaption').filter({ hasText: CAPTION })).toBeVisible();
  await reviewer.getByRole('button', { name: `Büyüt: ${CAPTION}` }).click();
  await expect(reviewer.getByRole('dialog', { name: CAPTION })).toBeVisible();
});

type Change = { id: string; hash: string; published_page_ids: string[] };

/** Kurgusal not + alıntı + taslak (API). */
async function apiDraft(page: Page, projectId: string, scope: unknown, title: string, statement: string): Promise<Change> {
  const me = await apiCall<{ csrf_token: string }>(page.request, 'GET', '/auth/me');
  const res = await page.request.post(`${BASE}/api/v1/projects/${projectId}/sources`, {
    multipart: { meta: JSON.stringify({ title: `${title} notu`, kind: 'note', text: statement, scope, acl: [] }) },
    headers: { Origin: BASE, 'X-CSRF-Token': me.csrf_token },
  });
  expect(res.status()).toBe(201);
  const src = (await res.json()) as { revision: { id: string } };
  const ev = await apiCall<{ id: string }>(page.request, 'POST', `/source-revisions/${src.revision.id}/evidence`, { excerpt: statement });
  const item = { title, summary: '', body_md: statement, kind: 'concept', scope, claims: [{ statement, evidence: [{ evidence_id: ev.id, quote: statement }] }] };
  return apiCall<Change>(page.request, 'POST', `/projects/${projectId}/changes`, { summary: title, items: [item] });
}

test('yayın öncesi kontrol: çelişen taslak uyarır → yine de yayımla → Bilgi sağlığında bulgu', async ({ browser }) => {
  const author = await userPage(browser, 'yazar', 'Yazar-Parola-2026-x');
  const me = await apiCall<{ memberships: { project_id: string }[] }>(author.request, 'GET', '/auth/me');
  const projectId = me.memberships[0]!.project_id;
  const list = await apiCall<{ items: { page_id: string }[] }>(author.request, 'GET', `/projects/${projectId}/pages`);
  const existing = await apiCall<{ revision: { scope: unknown } }>(author.request, 'GET', `/pages/${list.items[0]!.page_id}`);
  const scope = existing.revision.scope;

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
  const me = await apiCall<{ memberships: { project_id: string }[] }>(author.request, 'GET', '/auth/me');
  const projectId = me.memberships[0]!.project_id;
  const list = await apiCall<{ items: { page_id: string }[] }>(author.request, 'GET', `/projects/${projectId}/pages`);
  const existing = await apiCall<{ revision: { scope: unknown } }>(author.request, 'GET', `/pages/${list.items[0]!.page_id}`);
  const draft = await apiDraft(author, projectId, existing.revision.scope, 'Köprü saati (üçüncü ölçüm)', 'Köprü saat frekansı 500 MHz değerindedir.');

  await author.goto(`/katki?change=${draft.id}`);
  await expect(author.getByLabel('Başlık')).toHaveValue('Köprü saati (üçüncü ölçüm)');
  await author.getByRole('button', { name: 'Yayımla', exact: true }).click();
  const dialog = author.getByRole('dialog', { name: 'Yayımlamadan önce bak' });
  await expect(dialog.getByText('Çelişebilir').first()).toBeVisible();
  await dialog.getByRole('button', { name: 'Taslağa dön' }).click();
  await expect(dialog).toBeHidden();
  await expect(author).toHaveURL(new RegExp(`/katki\\?change=${draft.id}`));
  await author.getByLabel('Özet').fill('Ölçüm farklı bir kart revizyonunda yapıldı.');
  await author.getByRole('button', { name: 'Yayımla', exact: true }).click();
  await author.getByRole('dialog', { name: 'Yayımlamadan önce bak' }).getByRole('button', { name: 'Yine de yayımla' }).click();
  await expect(author).toHaveURL(/\/bilgi\/[0-9a-f-]{36}/);
  await expect(author.getByText('Ölçüm farklı bir kart revizyonunda yapıldı.')).toBeVisible();
});
