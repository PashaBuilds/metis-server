import { expect, test, type Browser, type Page } from '@playwright/test';
import { ADMIN, apiCall, apiLogin, BASE, createMember, selectInViewer, SOURCE_TITLE } from './helpers';

/**
 * Faz 2 kabul (tam akış): yazar taslak yazıp incelemeye gönderir → inceleyici düzeltme ister →
 * yazar düzenleyip yeniden gönderir → inceleyici onaylar ve yayımlar → bilgi silinir ve geri alınır.
 */

async function userPage(browser: Browser, username: string, password: string): Promise<Page> {
  const ctx = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await apiLogin(page.request, username, password);
  return page;
}

test('taslak → düzeltme iste → düzenle → yeniden gönder → onayla → yayımla → sil ve geri al', async ({ page, browser }) => {
  // Hazırlık: yönetici yazar ve inceleyici oluşturur (ilk girişte parola değiştirilir).
  const me = await apiLogin(page.request, ADMIN.username, ADMIN.password);
  const projectId = me.memberships[0]!.project_id;
  await createMember(page.request, projectId, 'yazar', 'E2E Yazar', ['contributor'], 'Yazar-Gecici-2026');
  await createMember(page.request, projectId, 'denetci', 'E2E Denetçi', ['reviewer'], 'Denetci-Gecici-2026');
  const seed = await browser.newContext({ baseURL: BASE });
  await apiLogin(seed.request, 'yazar', 'Yazar-Gecici-2026', 'Yazar-Parola-2026-x');
  await apiLogin(seed.request, 'denetci', 'Denetci-Gecici-2026', 'Denetci-Parola-2026-x');
  await seed.close();

  const author = await userPage(browser, 'yazar', 'Yazar-Parola-2026-x');
  const reviewer = await userPage(browser, 'denetci', 'Denetci-Parola-2026-x');

  // 1) Yazar: var olan kaynağı seçer, iki alıntıyı iddiaya bağlar, kaydedip incelemeye gönderir.
  await author.goto('/katki');
  await author.getByRole('button', { name: new RegExp(SOURCE_TITLE) }).click();
  await author.getByRole('button', { name: 'Yazmaya başla' }).click();
  await author.getByLabel('Başlık').fill('ISR temizleme kuralı');
  await author.getByRole('textbox', { name: 'Açıklama' }).fill('ISR içinde yalnız durum bitleri temizlenir.');
  await selectInViewer(author, 'ISR içinde yalnız durum bitleri temizlenir.');
  await author.getByRole('button', { name: 'Bu alıntıyı iddiaya bağla' }).click();
  await expect(author.getByRole('textbox', { name: 'İddia 1' })).toHaveValue('ISR içinde yalnız durum bitleri temizlenir.');
  // İddia alıntıdan saparsa uyarı görünür, düzeltince kaybolur.
  await author.getByRole('textbox', { name: 'İddia 1' }).fill('ISR her şeyi yapar.');
  await expect(author.getByText('İddia metni seçtiğin alıntıda birebir geçmiyor; mentor bu iddiayı kullanamaz. Alıntıdaki ifadeyi kullan.')).toBeVisible();
  await author.getByRole('textbox', { name: 'İddia 1' }).fill('ISR içinde yalnız durum bitleri temizlenir.');
  await expect(author.getByText('İddia metni seçtiğin alıntıda birebir geçmiyor; mentor bu iddiayı kullanamaz. Alıntıdaki ifadeyi kullan.')).toBeHidden();
  await author.getByRole('button', { name: 'Kaydet ve incelemeye gönder' }).click();
  await expect(author).toHaveURL(/\/kayitlar\/[0-9a-f-]{36}$/);
  const recordUrl = author.url();
  await expect(author.getByText('İncelemede', { exact: true })).toBeVisible();
  await expect(author.getByText('İnceleyici kararı bekleniyor.')).toBeVisible();

  // 2) İnceleyici: gerekçesiz düzeltme isteği reddedilir; gerekçeyle "Düzeltme iste".
  await reviewer.goto(recordUrl);
  await reviewer.getByRole('button', { name: 'Düzeltme iste' }).click();
  await expect(reviewer.getByText('Gerekçe yaz.')).toBeVisible();
  await reviewer.getByLabel('Gerekçe').fill('Özet eksik; tek cümlelik özet ekle.');
  await reviewer.getByRole('button', { name: 'Düzeltme iste' }).click();
  await expect(reviewer.getByText('Düzeltme istendi')).toBeVisible();
  await expect(reviewer.getByText('Taslak', { exact: true })).toBeVisible();

  // 3) Yazar: kaydı açar, "Düzenle" ile özeti ekler ve yeniden gönderir.
  await author.reload();
  await expect(author.getByText('Taslak', { exact: true })).toBeVisible();
  await author.getByRole('link', { name: 'Düzenle' }).click();
  await expect(author).toHaveURL(/\/katki\?change=/);
  await expect(author.getByLabel('Başlık')).toHaveValue('ISR temizleme kuralı');
  await author.getByLabel('Özet').fill('Kesme işleyicisinde yalnız durum bitlerinin temizlenmesi.');
  await author.getByRole('button', { name: 'Kaydet ve incelemeye gönder' }).click();
  await expect(author).toHaveURL(recordUrl);
  await expect(author.getByText('İncelemede', { exact: true })).toBeVisible();

  // 4) İnceleyici: kontrol kutusu → Onayla ve yayımla (tek adım).
  await reviewer.reload();
  await expect(reviewer.getByText('İncelemede', { exact: true })).toBeVisible();
  await reviewer.getByText('Geçmiş ve bağlam').click();
  await expect(reviewer.getByText('Özet eksik; tek cümlelik özet ekle.')).toBeVisible();
  await reviewer.getByLabel('İddiaları ve kaynak desteğini kontrol ettim').check();
  await reviewer.getByRole('button', { name: 'Onayla ve yayımla' }).click();
  await expect(reviewer.getByText('Yayımlandı', { exact: true }).first()).toBeVisible();
  await reviewer.getByRole('link', { name: 'Yayımlanan bilgiyi aç' }).click();
  await expect(reviewer.getByRole('heading', { level: 1, name: 'ISR temizleme kuralı' })).toBeVisible();
  const pageUrl = reviewer.url();
  const pageId = pageUrl.split('/bilgi/')[1]!.split('?')[0]!;

  // Havuzda görünür.
  await reviewer.goto('/bilgi?q=ISR');
  await expect(reviewer.getByRole('link', { name: 'ISR temizleme kuralı' })).toBeVisible();

  // 5) Sil → "Silindi" → Geri al → bilgi geri gelir.
  await reviewer.goto(pageUrl);
  await reviewer.getByRole('button', { name: 'Diğer işlemler' }).click();
  await reviewer.getByRole('menuitem', { name: 'Sil' }).click();
  await reviewer.getByRole('dialog').getByRole('button', { name: 'Sil' }).click();
  await expect(reviewer).toHaveURL(/\/bilgi(\?.*)?$/); // son filtreler (q=ISR) tercihten geri yüklenir
  const toast = reviewer.getByRole('status').filter({ hasText: 'Silindi' });
  await expect(toast).toBeVisible();
  const gone = await reviewer.request.get(`${BASE}/api/v1/pages/${pageId}`);
  expect(gone.status()).toBe(404);
  await toast.getByRole('button', { name: 'Geri al' }).click();
  await expect(reviewer.getByRole('heading', { level: 1, name: 'ISR temizleme kuralı' })).toBeVisible();
  const back = await apiCall<{ page_id: string }>(reviewer.request, 'GET', `/pages/${pageId}`);
  expect(back.page_id).toBe(pageId);

  // 6) Sorun bildir → bulgu bandı görünür.
  await reviewer.getByRole('button', { name: 'Diğer işlemler' }).click();
  await reviewer.getByRole('menuitem', { name: 'Sorun bildir' }).click();
  await reviewer.getByRole('dialog').getByRole('textbox', { name: 'Açıklama' }).fill('ISR kuralı yeni sürücüde değişmiş olabilir.');
  await reviewer.getByRole('dialog').getByRole('button', { name: 'Bildir' }).click();
  await expect(reviewer.getByText('Bildirildi', { exact: true })).toBeVisible();
  await expect(reviewer.getByText(/Bu bilgi hakkında 1 açık bulgu var/)).toBeVisible();

  // 7) Geri çek: gerekçe zorunlu; sonra geri çekildi bandı.
  await reviewer.getByRole('button', { name: 'Diğer işlemler' }).click();
  await reviewer.getByRole('menuitem', { name: 'Geri çek' }).click();
  const dialog = reviewer.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Geri çek' }).click();
  await expect(dialog.getByText('Gerekçe yaz.')).toBeVisible();
  await dialog.getByRole('textbox', { name: 'Gerekçe' }).fill('Sürücü yeniden yazıldı.');
  await dialog.getByRole('button', { name: 'Geri çek' }).click();
  await expect(reviewer.getByText(/Bu bilgi geri çekildi; mentor onu kullanmıyor/)).toBeVisible();
});
