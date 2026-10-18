import { expect, test } from '@playwright/test';
import { ADMIN, apiCall, apiLogin } from './helpers';

/**
 * Faz 5/6 kabul (arayüz): kurgusal çalışma alanındaki açık çelişki "Çelişkiden çözüme" akışıyla
 * incelemeye giden bir kayda dönüşür; model destekli tarama görevi başlatılır ve SSE ile canlı tamamlanır.
 * Önkoşul: mentor-flow (kurgusal model eklendi ve benchmark'ı geçti).
 */

interface Me {
  memberships: { project_id: string; project_name: string; is_demo: boolean }[];
}

test('Çelişkiden çözüme → kayıt incelemede; havuz denetimi SSE ile tamamlanır', async ({ page }) => {
  test.setTimeout(150_000);
  const me = (await apiLogin(page.request, ADMIN.username, ADMIN.password)) as unknown as Me;
  const demo = me.memberships.find((m) => m.is_demo)!;
  await apiCall(page.request, 'PUT', '/preferences/active_project_id', { value: demo.project_id });

  // 1) Bilgi sağlığı: açık çelişki bulgusu ve iki tarafın alıntısı.
  await page.goto('/saglik');
  await expect(page.getByRole('heading', { level: 1, name: 'Bilgi sağlığı' })).toBeVisible();
  const finding = page.getByRole('listitem').filter({ hasText: 'İki onaylı bilgi aynı özellik için farklı değer veriyor.' });
  await expect(finding).toBeVisible();
  await expect(finding.getByRole('link', { name: 'Hata ayıklama UART hızı' })).toBeVisible();
  await finding.getByRole('button', { name: 'Ayrıntılar' }).click();
  await expect(finding.locator('mark', { hasText: '115200 baud' })).toBeVisible();
  await expect(finding.locator('mark', { hasText: '921600 baud' })).toBeVisible();

  // 2) Çelişkiden çözüme: seçenek + gerekçe + onay kutusu zorunlu.
  await finding.getByRole('button', { name: 'Çelişkiden çözüme' }).click();
  const dialog = page.getByRole('dialog', { name: 'Çelişkiden çözüme' });
  await expect(dialog.getByText('Seçenekler')).toBeVisible();
  await dialog.getByRole('button', { name: 'Çözüm kaydını oluştur' }).click();
  await expect(dialog.getByText('Bir seçenek seç.')).toBeVisible();
  await dialog.getByRole('radio', { name: /«Hata ayıklama UART hızı» korunsun/ }).check();
  await dialog.getByLabel('Gerekçe').fill('Test kaydı 115200 baud değerini doğruluyor; saha notu eski kart revizyonuna ait.');
  await dialog.getByRole('button', { name: 'Çözüm kaydını oluştur' }).click();
  await expect(dialog.getByText('Devam etmek için onay kutusunu işaretle.')).toBeVisible();
  await dialog.getByLabel(/Geri çekilecek bilginin tamamının yayından kalkacağını anladım/).check();
  await dialog.getByRole('button', { name: 'Çözüm kaydını oluştur' }).click();
  await expect(dialog.getByText(/Çözüm kaydı oluşturuldu/)).toBeVisible();
  await dialog.getByRole('link', { name: 'Kaydı aç' }).click();
  await expect(page).toHaveURL(/\/kayitlar\/[0-9a-f-]{36}$/);
  await expect(page.getByText('İncelemede', { exact: true }).first()).toBeVisible();

  // 3) Şimdi denetle (model seçmeden: hızlı tarama) → görev bağlantısı.
  await page.goto('/saglik');
  await page.getByRole('button', { name: 'Şimdi denetle' }).click();
  const scan = page.getByRole('dialog', { name: 'Bilgi havuzunu şimdi denetle' });
  await expect(scan.getByLabel('Model (isteğe bağlı)')).toHaveValue('');
  await scan.getByRole('button', { name: 'Taramayı başlat' }).click();
  await expect(page.getByText('Tarama görevi sıraya alındı.')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Görevi aç' })).toBeVisible();

  // 4) Model destekli tarama: model açıkça seçilir (sessiz seçim yok); görev sayfasına geçilir.
  await page.reload();
  await page.getByRole('button', { name: 'Şimdi denetle' }).click();
  const scan2 = page.getByRole('dialog', { name: 'Bilgi havuzunu şimdi denetle' });
  await scan2.getByLabel('Model (isteğe bağlı)').selectOption({ label: 'fixture-reference (kurgusal test modeli)' });
  await scan2.getByRole('button', { name: 'Taramayı başlat' }).click();
  await page.getByRole('link', { name: 'Görevi aç' }).click();
  await expect(page).toHaveURL(/\/gorevler\/[0-9a-f-]{36}$/);

  // 5) Canlı (SSE): sırada/çalışıyor → tamamlandı; önce sonuç, en altta katlı teknik ayrıntılar.
  await expect(page.getByText('Tamamlandı', { exact: true }).first()).toBeVisible({ timeout: 90_000 });
  const result = page.getByRole('region', { name: 'Sonuç' });
  await expect(result).toContainText(/bulgu/i);
  await page.getByText('Teknik ayrıntılar').click();
  await expect(page.getByText(/fence=\d+ attempt=\d+/)).toBeVisible();

  // 6) Liste: satırda durum ve tek cümlelik sonuç.
  await page.goto('/gorevler');
  const jobRow = page.getByRole('listitem').filter({ hasText: 'Bakım taraması' }).first();
  await expect(jobRow.getByText('Tamamlandı')).toBeVisible();
});
