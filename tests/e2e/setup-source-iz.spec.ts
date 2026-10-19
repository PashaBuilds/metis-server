import { expect, test } from '@playwright/test';
import { ADMIN, apiCall, createMember, NOTE_TITLE, PDF_FILE, PNG_FILE, PROJECT, QUOTE, setupCode } from './helpers';

/**
 * Kabul (2026-10-19, tek adımda taslak): kurulum → giriş → "Taslak hazırla": not + iki ek (görsel, PDF) →
 * taslağı kaydet → yayımla → (ikinci kullanıcı) bilgi sayfasında ●1 → İz panelinde "Uzman notu" ve vurgulu paragraf,
 * Ekler bölümünde dosyalar → yazar bilgiyi düzenleyip yeniden yayımlar (kendi notu "kaynak değişti" sayılmaz).
 */
test('kurulum, not + ekler, yayın, İz ve düzenleme', async ({ page, browser }) => {
  // 1) Kurulum (tek kullanımlık kod CLI'dan)
  const code = setupCode();
  await page.goto('/');
  await expect(page).toHaveURL(/\/kurulum$/);
  // Başlatıcı (METIS-Baslat.exe) kodu adresin # kısmında verir: alan dolu gelir, adres temizlenir.
  await page.goto(`/kurulum#kod=${code}`);
  await expect(page.getByLabel('Kurulum kodu')).toHaveValue(code);
  await expect(page).toHaveURL(/\/kurulum$/);
  await page.getByLabel('Adın').fill(ADMIN.name);
  await page.getByLabel('Kullanıcı adı').fill(ADMIN.username);
  await page.getByLabel('Parola').fill(ADMIN.password);
  await page.getByLabel('İlk proje adı').fill(PROJECT);
  await page.getByRole('button', { name: 'Kurulumu tamamla' }).click();

  // 2) Ana sayfa: boş havuz rehberi → Taslak hazırla
  await expect(page.getByRole('heading', { name: 'Ne öğrenmek istiyorsun?' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'İlk bilgini ekle' })).toBeVisible();
  await page.getByRole('link', { name: 'Taslak hazırla' }).click();

  // 3) Tek adım: başlık + not + iki ek (çoklu seçim). Ayrı kaynak adımı yok.
  await expect(page).toHaveURL(/\/katki/);
  await expect(page.getByRole('heading', { level: 1, name: 'Taslak hazırla' })).toBeVisible();
  await page.getByLabel('Başlık').fill(NOTE_TITLE);
  await page.getByRole('textbox', { name: 'Not', exact: true }).fill(`${QUOTE}\n\nISR içinde yalnız durum bitleri temizlenir; 1. görselde zamanlama var.`);
  await page.locator('input[type=file]').setInputFiles([PNG_FILE, PDF_FILE]);
  await expect(page.getByText(PNG_FILE.name)).toBeVisible();
  await expect(page.getByText(PDF_FILE.name)).toBeVisible();
  await page.getByRole('button', { name: 'Taslağı kaydet' }).click();

  // 4) Kayıt detayı: "Yazar yayımlar" — yayın öncesi kontrol sorun bulmazsa doğrudan yayımlanır.
  await expect(page).toHaveURL(/\/kayitlar\/[0-9a-f-]{36}$/);
  await expect(page.getByText('Taslak kaydedildi')).toBeVisible();
  await page.getByRole('button', { name: 'Yayımla', exact: true }).click();
  await expect(page.getByText(/^Yayımlandı/).first()).toBeVisible();
  await page.getByRole('link', { name: 'Yayımlanan bilgiyi aç' }).click();
  await expect(page.getByText('Yayımlayan: E2E Yönetici')).toBeVisible();
  const publishedUrl = page.url();

  // 5) API ile ikinci kullanıcı (inceleyici)
  const me = await apiCall<{ memberships: { project_id: string }[] }>(page.request, 'GET', '/auth/me');
  const projectId = me.memberships[0]!.project_id;
  await createMember(page.request, projectId, 'inceleyici', 'E2E İnceleyici', ['reviewer'], 'Gecici-Parola-2026');

  // 6) İnceleyici: ilk girişte parola değişimi, yayımlanan bilgiyi açar
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
  await rp.goto(publishedUrl);

  // 7) Bilgi sayfası: Ekler bölümü; ayrı iddia listesi yok; ●1 → İz paneli "Uzman notu" + vurgulu paragraf + ekler.
  await expect(rp.getByRole('heading', { level: 1, name: NOTE_TITLE })).toBeVisible();
  await expect(rp.getByRole('heading', { name: 'Ekler (2)' })).toBeVisible();
  await expect(rp.getByRole('link', { name: PDF_FILE.name })).toHaveAttribute('href', /\/api\/v1\/attachments\/[0-9a-f-]{36}\/download$/);
  await expect(rp.getByRole('heading', { name: 'Doğrulanabilir iddialar' })).toHaveCount(0);
  await rp.getByRole('button', { name: `Büyük göster: ${PNG_FILE.name}` }).click();
  await expect(rp.getByRole('dialog', { name: PNG_FILE.name })).toBeVisible();
  await rp.keyboard.press('Escape');
  const via = rp.getByRole('button', { name: /^Kaynak 1/ }).first();
  await via.click();
  const panel = rp.locator('#iz-panel');
  await expect(panel).toBeVisible();
  await expect(panel.getByText('Uzman notu')).toBeVisible();
  await expect(panel.getByRole('heading', { name: NOTE_TITLE })).toBeVisible();
  await expect(panel.locator('mark')).toHaveText(QUOTE);
  await expect(panel.getByRole('heading', { name: 'Ekler (2)' })).toBeVisible();
  await expect(rp.getByTestId('iz-trace')).toBeVisible();
  await rp.keyboard.press('Escape');
  await expect(panel).toBeHidden();
  await expect(via).toBeFocused();
  await ctx.close();

  // 8) Yazar: "Bilgiyi düzenle" → not değişir, ekler korunur → Yayımla. Kendi notunun yeni sürümü uyarı üretmez.
  await page.goto(publishedUrl);
  await page.getByRole('link', { name: 'Bilgiyi düzenle' }).first().click();
  await expect(page).toHaveURL(/\/katki\?page=/);
  await expect(page.getByText(PDF_FILE.name)).toBeVisible();
  await page.getByRole('textbox', { name: 'Not', exact: true }).fill(`${QUOTE}\n\nYeni sürümde ISR yalnız bayrağı temizler.`);
  await page.getByRole('button', { name: 'Yayımla', exact: true }).click();
  await expect(page).toHaveURL(/\/bilgi\/[0-9a-f-]{36}/);
  await expect(page.getByText('Yeni sürümde ISR yalnız bayrağı temizler.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Ekler (2)' })).toBeVisible();
  await expect(page.getByText(/Bu bilginin dayandığı bir kaynak değişti/)).toHaveCount(0);
});
