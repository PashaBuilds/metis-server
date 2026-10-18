import { expect, test } from '@playwright/test';
import { ADMIN, apiCall, createMember, NOTE, PROJECT, QUOTE, selectInViewer, setupCode, SOURCE_TITLE } from './helpers';

/**
 * Faz 1 kabul: kurulum → giriş → kaynak ekle → taslakta alıntıyı iddiaya bağla →
 * (ikinci kullanıcı) onayla + yayımla → bilgi sayfasında ●1 → İz panelinde kaynak ve vurgulu alıntı.
 */
test('kurulum, kaynak, alıntı-iddia, yayın ve İz paneli', async ({ page, browser }) => {
  // 1) Kurulum (tek kullanımlık kod CLI'dan)
  const code = setupCode();
  await page.goto('/');
  await expect(page).toHaveURL(/\/kurulum$/);
  await page.getByLabel('Kurulum kodu').fill(code);
  await page.getByLabel('Adın').fill(ADMIN.name);
  await page.getByLabel('Kullanıcı adı').fill(ADMIN.username);
  await page.getByLabel('Parola').fill(ADMIN.password);
  await page.getByLabel('İlk proje adı').fill(PROJECT);
  await page.getByRole('button', { name: 'Kurulumu tamamla' }).click();

  // 2) Ana sayfa: boş havuz rehberi
  await expect(page.getByRole('heading', { name: 'Ne öğrenmek istiyorsun?' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'İlk bilgini ekle' })).toBeVisible();
  await page.getByRole('link', { name: 'Kaynak ekle' }).click();

  // 3) Yeni kaynak: projede kaynak yokken form doğrudan açılır
  await expect(page).toHaveURL(/\/katki/);
  await expect(page.getByRole('radio', { name: 'Yeni kaynak' })).toBeChecked();
  await page.getByLabel('Başlık').fill(SOURCE_TITLE);
  await page.getByLabel('Uzman notu').fill(NOTE);
  await page.getByRole('button', { name: 'Kaynağı ekle' }).click();
  await expect(page.getByText('Seçili kaynak')).toBeVisible();
  await expect(page.getByText('Metin çıkarıldı; alıntı seçebilirsin.')).toBeVisible();

  // 4) Kaynağın hemen altında iki yol: Kendim yazayım → alıntı seç → iddiaya bağla
  await page.getByRole('button', { name: 'Yazmaya başla' }).click();
  await page.getByLabel('Başlık').fill('AXI kesme maskesi');
  await page.getByLabel('Özet').fill('Kesme maskesinin hangi kayıtta tutulduğu.');
  await page.getByRole('textbox', { name: 'Açıklama' }).fill(`Maske bilgisi için kaynak nota bakılır.\n\n${QUOTE}`);
  await selectInViewer(page, QUOTE);
  await page.getByRole('button', { name: 'Bu alıntıyı iddiaya bağla' }).click();
  await expect(page.getByRole('textbox', { name: 'İddia 1' })).toHaveValue(QUOTE);
  await expect(page.getByTestId('source-viewer').locator('mark')).toHaveText(QUOTE);
  await page.getByRole('button', { name: 'Taslağı kaydet' }).click();

  // 5) Kayıt detayı: "Yazar yayımlar" — Metis yayın öncesi kontrolü yapar; sorun yoksa doğrudan yayımlanır.
  await expect(page).toHaveURL(/\/kayitlar\/[0-9a-f-]{36}$/);
  await expect(page.getByText('Taslak kaydedildi')).toBeVisible();
  await expect(page.getByRole('button', { name: 'İncelemeye gönder' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Yayımla', exact: true }).click();
  await expect(page.getByText(/^Yayımlandı/).first()).toBeVisible();
  await page.getByRole('link', { name: 'Yayımlanan bilgiyi aç' }).click();
  await expect(page.getByText('Yayımlayan: E2E Yönetici')).toBeVisible();
  const pageUrl = page.url();

  // 6) API ile ikinci kullanıcı (inceleyici)
  const me = await apiCall<{ memberships: { project_id: string }[] }>(page.request, 'GET', '/auth/me');
  const projectId = me.memberships[0]!.project_id;
  await createMember(page.request, projectId, 'inceleyici', 'E2E İnceleyici', ['reviewer'], 'Gecici-Parola-2026');

  // 7) İnceleyici: ilk girişte parola değişimi, yayımlanan bilgiyi açar
  const ctx = await browser.newContext({ baseURL: 'http://localhost:8001', viewport: { width: 1440, height: 900 } });
  const rp = await ctx.newPage();
  await rp.goto('/giris');
  await rp.getByLabel('Kullanıcı adı').fill('inceleyici');
  await rp.getByLabel('Parola').fill('Gecici-Parola-2026');
  await rp.getByRole('button', { name: 'Giriş yap' }).click();
  await expect(rp).toHaveURL(/\/parola$/);
  await rp.getByLabel('Geçici parola').fill('Gecici-Parola-2026');
  await rp.getByLabel('Yeni parola', { exact: true }).fill('Inceleyici-Parola-2026');
  await rp.getByLabel('Yeni parola (tekrar)').fill('Inceleyici-Parola-2026');
  await rp.getByRole('button', { name: 'Parolayı değiştir' }).click();
  await expect(rp.getByRole('heading', { name: 'Ne öğrenmek istiyorsun?' })).toBeVisible();
  await rp.goto(pageUrl);

  // 8) Bilgi sayfası: ●1 → İz paneli; Esc → odak işarete döner
  await expect(rp.getByRole('heading', { level: 1, name: 'AXI kesme maskesi' })).toBeVisible();
  const publishedUrl = rp.url();
  const via = rp.getByRole('button', { name: /^Kaynak 1/ }).first();
  await via.click();
  const panel = rp.locator('#iz-panel');
  await expect(panel).toBeVisible();
  await expect(panel.getByRole('heading', { name: SOURCE_TITLE })).toBeVisible();
  await expect(panel.locator('mark')).toHaveText(QUOTE);
  await expect(rp.getByTestId('iz-trace')).toBeVisible();
  await rp.keyboard.press('Escape');
  await expect(panel).toBeHidden();
  await expect(via).toBeFocused();
  await ctx.close();

  // 9) Yazar: İz panelinden "Yeni kaynak sürümü ekle" → yeni sürüm → bilgi "Kaynak değişti".
  await page.goto(publishedUrl);
  await page.getByRole('button', { name: /^Kaynak 1/ }).first().click();
  await page.locator('#iz-panel').getByRole('link', { name: 'Yeni sürüm ekle' }).click();
  await expect(page).toHaveURL(/\/katki\?source=/);
  await expect(page.getByRole('heading', { name: 'Yeni sürüm ekle' })).toBeVisible();
  await page.getByLabel('Uzman notu').fill(`${NOTE}\nYeni sürümde maske kaydı değişti.`);
  await page.getByRole('button', { name: 'Yeni sürümü ekle' }).click();
  await expect(page.getByText(/Yeni sürüm eklendi/)).toBeVisible();
  await expect(page.getByText('2. sürüm')).toBeVisible();
  await page.goto(publishedUrl);
  await expect(page.getByText(/Bu bilginin dayandığı bir kaynak değişti/)).toBeVisible();
});
