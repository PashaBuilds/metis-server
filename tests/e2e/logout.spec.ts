import { expect, test } from '@playwright/test';
import { ADMIN, apiLogin } from './helpers';

/**
 * Çıkış yap → sayfa yenilenmeden giriş ekranı (2026-10-19 hatası: önbellek temizlenince oturum sorgusu açık sayfadan
 * kopuyordu; giriş sayfası eski oturumu görüp ana sayfaya geri yönlendiriyordu, ancak F5 ile giriş ekranı geliyordu).
 */
test('Çıkış yap: yenilemeden giriş ekranına geçer, korunan sayfa açılmaz', async ({ page }) => {
  await apiLogin(page.request, ADMIN.username, ADMIN.password);
  await page.goto('/');
  await expect(page.getByLabel('Ne öğrenmek istiyorsun?')).toBeVisible();

  await page.getByRole('button', { name: /^Hesap: / }).click();
  await page.getByRole('menuitem', { name: 'Çıkış yap' }).click();

  await expect(page).toHaveURL(/\/giris$/);
  await expect(page.getByLabel('Kullanıcı adı')).toBeVisible();
  await expect(page.getByLabel('Ne öğrenmek istiyorsun?')).toHaveCount(0);

  // Geri tuşu ya da doğrudan adres korunan sayfayı açmaz.
  await page.goto('/kayitlar');
  await expect(page).toHaveURL(/\/giris$/);
});
