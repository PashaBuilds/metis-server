import { expect, test } from '@playwright/test';
import { ADMIN, apiCall, apiLogin, PROJECT } from './helpers';

/**
 * Faz 4/8 kabul (arayüz): yönetici Model laboratuvarında kurgusal model sunucusunu (:9102) ekler,
 * bağlantı testini ve ortak benchmark'ı çalıştırır (worker) → model "Kaynaklı kısa cevap için uygun" olur →
 * mentor kaynaklı cevap verir (karar rozeti, ●n işaretli açıklama, alıntı kartı, İz paneli).
 * Ardından kurgusal model gerçek (kurgusal olmayan) projede seçilince sessiz geçiş yerine nedeni yazılır.
 */

const MOCK_URL = 'http://127.0.0.1:9102/v1';
const SPI_QUOTE = "SPI denetleyicisi 100 MHz referans saatini 8 bölücü ile 12.5 MHz SCLK'ye indirir.";

interface Me {
  memberships: { project_id: string; project_name: string; is_demo?: boolean }[];
}

test('Lab: sağlayıcı ekle, test et, benchmark → mentor kaynaklı cevap ve İz paneli', async ({ page }) => {
  test.setTimeout(180_000);
  await apiLogin(page.request, ADMIN.username, ADMIN.password);
  // Kurgusal model yalnız kurgusal çalışma alanında uygundur: geliştirme profilinde /demo ile oluştur.
  const demo = await apiCall<{ project_id: string }>(page.request, 'POST', '/demo');
  await apiCall(page.request, 'PUT', '/preferences/active_project_id', { value: demo.project_id });

  // 1) Lab: 3 alanlı ekleme formu (anahtar boş: kurgusal sunucu anahtar istemez). Adres sunucu ayarında yok
  //    (scripts/e2e-server.sh): yönetici uyarıyı görür ve "İzin ver ve ekle" ile metis.env'e dokunmadan izin verir.
  await page.goto('/lab');
  await expect(page.getByRole('heading', { level: 1, name: 'Model laboratuvarı' })).toBeVisible();
  await page.getByRole('button', { name: 'Sağlayıcı ekle' }).click();
  const dialog = page.getByRole('dialog', { name: 'Sağlayıcı ekle' });
  await dialog.getByLabel('Sunucu adresi').fill(MOCK_URL);
  await dialog.getByLabel('Model kimlikleri').fill('fixture-reference');
  await dialog.getByRole('button', { name: 'Sağlayıcı ekle' }).click();
  await expect(dialog.getByRole('alert').filter({ hasText: 'Bu adrese henüz izin verilmedi' })).toBeVisible();
  await expect(page.getByText('Sağlayıcı eklendi')).toHaveCount(0);
  await dialog.getByRole('button', { name: 'İzin ver ve ekle' }).click();
  await expect(page.getByText('Adrese izin verildi')).toBeVisible();
  await expect(page.getByText('Sağlayıcı eklendi')).toBeVisible();
  await expect(page.getByText(MOCK_URL).first()).toBeVisible();
  await expect(page.getByText('Anahtar tanımlı değil')).toBeVisible();
  const row = page.getByRole('row').filter({ hasText: 'fixture-reference' });
  await expect(row).toBeVisible();
  await expect(row.getByText('Test edilmedi')).toBeVisible();
  await expect(row.getByText('Çalıştırılmadı')).toBeVisible();

  // 2) Test et (bağlantı + kanıt sözleşmesi probe'u, eşzamanlı).
  await row.getByRole('button', { name: 'İşlemler: fixture-reference' }).click();
  await page.getByRole('menuitem', { name: 'Test et' }).click();
  await expect(page.getByText('fixture-reference test edildi')).toBeVisible({ timeout: 30_000 });
  await expect(row.getByText('Testi geçti')).toBeVisible();

  // 3) Seçim asla otomatik değil: kutuyu işaretle → Benchmark çalıştır (worker işi, 3 sn yoklama).
  await expect(page.getByRole('button', { name: 'Benchmark çalıştır' })).toBeDisabled();
  await row.getByRole('checkbox', { name: 'Seç: fixture-reference' }).check();
  await page.getByRole('button', { name: 'Benchmark çalıştır' }).click();
  await expect(page.getByText('1 benchmark sıraya alındı')).toBeVisible();
  await expect(row.getByText('Geçti', { exact: true })).toBeVisible({ timeout: 90_000 });
  await expect(row.getByText('Kaynaklı kısa cevap için uygun')).toBeVisible();
  await expect(row.getByText('0 kritik hata')).toBeVisible();
  await expect(page.getByRole('img', { name: /fixture-reference: doğruluk/ })).toBeVisible(); // kalite–gecikme grafiği

  // 4) Ana sayfa model seçicisi: Otomatik + uygun model.
  await page.goto('/');
  const homeModel = page.getByLabel('Model');
  await expect(homeModel.locator('option', { hasText: 'Otomatik (önerilen)' })).toHaveCount(1);
  await expect(homeModel.locator('option', { hasText: 'fixture-reference (kurgusal test modeli)' })).toBeEnabled();

  // 5) Mentor: akışlı cevap → karar rozeti, ●n işaretli açıklama, alıntı kartı.
  await page.getByLabel('Ne öğrenmek istiyorsun?').fill('SPI saat bölücü kaç?');
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/mentor\?/);
  const answer = page.getByRole('article');
  await expect(answer.getByText('Kanıtla destekli')).toBeVisible({ timeout: 30_000 });
  await expect(page).toHaveURL(/answer=/);
  const marks = answer.locator('[data-iz-marker^="ans:"]');
  expect(await marks.count()).toBeGreaterThanOrEqual(1);
  await expect(answer.getByRole('heading', { name: 'Kaynak alıntıları' })).toBeVisible();
  await expect(answer.locator('blockquote', { hasText: SPI_QUOTE })).toBeVisible();

  // 6) ●1 → İz paneli: kaynak başlığı ve vurgulu alıntı.
  await marks.first().click();
  const panel = page.locator('#iz-panel');
  await expect(panel).toBeVisible();
  await expect(panel.locator('mark[data-iz-target]')).toContainText('SPI denetleyicisi');
  await page.keyboard.press('Escape');
  await expect(panel).toBeHidden();

  // 7) Üretim kaydı katlı: model ve prompt sürümü yalnız orada.
  await answer.getByText('Teknik ayrıntılar').click();
  await expect(answer.getByText('evidence-explain-v1')).toBeVisible();
  await expect(answer.getByText('fixture-reference', { exact: true })).toBeVisible();

  // 8) Cevaptan taslak önerisi 2026-10-19'da kalktı: model metni uzman notu olamaz.
  await expect(answer.getByRole('button', { name: 'Bu cevaptan bilgi taslağı öner' })).toHaveCount(0);
});

test('Uygun olmayan model seçilince sessiz geçiş yok: neden yazılır, alternatif önerilmez', async ({ page }) => {
  const me = (await apiLogin(page.request, ADMIN.username, ADMIN.password)) as unknown as Me;
  const demo = me.memberships.find((m) => m.is_demo)!;
  const real = me.memberships.find((m) => m.project_name === PROJECT)!;
  const models = await apiCall<{ id: string; remote_id: string }[]>(page.request, 'GET', '/models');
  const fixture = models.find((m) => m.remote_id === 'fixture-reference')!;

  // a) Kurgusal olmayan projede kurgusal model listede devre dışı ve nedeniyle görünür.
  await apiCall(page.request, 'PUT', '/preferences/active_project_id', { value: real.project_id });
  await page.goto('/');
  await expect(page.getByLabel('Model').locator('option', { hasText: 'fixture-reference — Kurgusal test modeli; şirket verisiyle kullanılamaz.' })).toBeDisabled();

  // b) Kurgusal projede modeli Lab'dan devre dışı bırak; açıkça seçilmiş model yine istenirse
  //    mentor otomatik başka modele geçmez: "Model servisi kullanılamıyor" + neden.
  await apiCall(page.request, 'PUT', '/preferences/active_project_id', { value: demo.project_id });
  await page.goto('/lab');
  const row = page.getByRole('row').filter({ hasText: 'fixture-reference' });
  await row.getByRole('button', { name: 'İşlemler: fixture-reference' }).click();
  await page.getByRole('menuitem', { name: 'Devre dışı bırak' }).click();
  await expect(row.getByText('Devre dışı', { exact: true })).toBeVisible();
  try {
    await page.goto(`/mentor?q=${encodeURIComponent('SPI saat bölücü kaç?')}&model=${fixture.id}`);
    const answer = page.getByRole('article');
    await expect(answer.getByText('Model servisi kullanılamıyor')).toBeVisible({ timeout: 30_000 });
    await expect(answer.getByText('Neden: Model devre dışı bırakılmış.')).toBeVisible();
    await expect(answer.getByText(/Şu an kullanılabilir başka model yok/)).toBeVisible();
    await expect(answer.getByRole('button', { name: 'Tekrar sor' })).toBeVisible();
    // Kaynaklar yine görünür; teknik iddia yok.
    await expect(answer.getByRole('link', { name: 'SPI saat bölücü ayarı' })).toBeVisible();
    await expect(answer.locator('[data-iz-marker]')).toHaveCount(0);
  } finally {
    await apiCall(page.request, 'PATCH', `/models/${fixture.id}`, { enabled: true });
  }
});
