import path from 'node:path';
import { expect, test, type Browser, type Page } from '@playwright/test';
import { BASE, apiLogin, QUOTE, selectInViewer, SOURCE_TITLE } from './helpers';

/**
 * Açıklayıcı görsel: yazar taslakta görsel yükler (kaynak olarak saklanır), açıklama yazar; yer tutucu metne girer,
 * önizlemede görünür. İnceleyici kayıtta görseli görür, onaylayıp yayımlar; bilgi sayfasında görsel metnin içindedir.
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

test('taslağa görsel ekle → önizle → incele → yayımla → bilgi sayfasında metin içinde', async ({ browser }) => {
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

  await author.getByRole('button', { name: 'Kaydet ve incelemeye gönder' }).click();
  await expect(author).toHaveURL(/\/kayitlar\/[0-9a-f-]{36}$/);
  const recordUrl = author.url();

  // İnceleyici görseli kayıtta görür; onaylar ve yayımlar.
  await reviewer.goto(recordUrl);
  await expect(reviewer.getByRole('region', { name: 'Görseller' }).getByRole('img', { name: CAPTION })).toBeVisible();
  await reviewer.getByLabel('İddiaları ve kaynak desteğini kontrol ettim').check();
  await reviewer.getByRole('button', { name: 'Onayla ve yayımla' }).click();
  await reviewer.getByRole('link', { name: 'Yayımlanan bilgiyi aç' }).click();

  // Bilgi sayfası: görsel gerçekten yüklenir, açıklaması altında; tıklayınca büyük hâli açılır.
  await expect(reviewer.getByRole('heading', { level: 1, name: 'Kesme maskesi ve kart görünümü' })).toBeVisible();
  const img = reviewer.getByRole('img', { name: CAPTION }).first();
  await expect(img).toBeVisible();
  await expect.poll(() => img.evaluate((el) => (el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  await expect(reviewer.locator('figcaption').filter({ hasText: CAPTION })).toBeVisible();
  await reviewer.getByRole('button', { name: `Büyüt: ${CAPTION}` }).click();
  await expect(reviewer.getByRole('dialog', { name: CAPTION })).toBeVisible();
});
