import { expect, test } from '@playwright/test';
import { ADMIN, apiLogin } from './helpers';

/**
 * Şirket içi http adresi (https değil, localhost değil) "güvenli olmayan bağlam"dır: tarayıcı crypto.randomUUID'i
 * vermez. 2.0.12'de Taslak hazırla sayfası açılırken onu çağırıp "Something went wrong!" ile çöküyordu (yalnız
 * localhost'ta denendiği için görünmemişti). Test, işlevi kaldırarak aynı ortamı kurar.
 */
test('güvenli olmayan bağlamda Taslak hazırla açılır ve taslak kaydedilir', async ({ page }) => {
  await page.addInitScript(() => {
    delete (Crypto.prototype as { randomUUID?: unknown }).randomUUID;
  });
  await apiLogin(page.request, ADMIN.username, ADMIN.password);
  await page.goto('/katki');
  expect(await page.evaluate(() => typeof crypto.randomUUID)).toBe('undefined');
  await expect(page.getByRole('heading', { level: 1, name: 'Taslak hazırla' })).toBeVisible();
  await page.getByLabel('Başlık').fill('Güvensiz bağlam notu');
  await page.getByRole('textbox', { name: 'Not', exact: true }).fill('Kurgusal kartta besleme 3,3 V.');
  await page.getByRole('button', { name: 'Taslağı kaydet' }).click();
  await expect(page).toHaveURL(/\/kayitlar\/[0-9a-f-]{36}$/);
});
