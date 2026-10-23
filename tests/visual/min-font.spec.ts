import { expect, test, type Page } from '@playwright/test';

/**
 * Brief 6: 12 px altında yazı yok — yalnız vitrin değil, tüm ana ekranlar (kurgusal çalışma alanı, geliştirme yığını :8000).
 * Her ekran içeriği yüklendikten sonra taranır (boş sayfada yanlışlıkla geçmesin diye en az 20 metin öğesi beklenir).
 */

const BASE = process.env.METIS_E2E_URL ?? 'http://localhost:8000';
const ROUTES = ['/', '/bilgi', '/mentor', '/katki', '/kayitlar', '/gorevler', '/saglik', '/harita', '/lab', '/geri-bildirim', '/ayarlar', '/ayarlar?tab=sistem', '/ayarlar?tab=bakim'];

async function smallText(page: Page) {
  return page.evaluate(() => {
    const bad: string[] = [];
    let checked = 0;
    for (const el of Array.from(document.querySelectorAll<HTMLElement>('body *'))) {
      if (![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent?.trim())) continue;
      const style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') continue;
      checked += 1;
      const size = parseFloat(style.fontSize);
      if (size < 12) bad.push(`${el.tagName.toLowerCase()} "${el.textContent?.trim().slice(0, 30)}": ${size}px`);
    }
    return { bad, checked };
  });
}

test.describe('12 px altında yazı yok — ana ekranlar', () => {
  test.beforeEach(async ({ page }) => {
    const res = await page.request.post(`${BASE}/api/v1/auth/login`, { data: { username: 'ayse', password: 'Kurgusal-Parola-2026' }, headers: { Origin: BASE } });
    expect(res.ok(), await res.text()).toBeTruthy();
  });

  test('bilgi sayfası (satır içi kod içerir)', async ({ page }) => {
    const me = await (await page.request.get(`${BASE}/api/v1/auth/me`)).json();
    const pid = me.preferences.active_project_id ?? me.memberships[0].project_id;
    const pages = await (await page.request.get(`${BASE}/api/v1/projects/${pid}/pages?limit=50`)).json();
    const target = pages.items.find((p: { title: string }) => p.title.includes('PCIe')) ?? pages.items[0];
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto(`/bilgi/${target.page_id}`);
    await expect(page.locator('main h1').first()).toBeVisible({ timeout: 20_000 });
    await page.waitForLoadState('networkidle').catch(() => undefined);
    const { bad, checked } = await smallText(page);
    expect(checked).toBeGreaterThan(20);
    expect(bad).toEqual([]);
  });

  for (const route of ROUTES) {
    test(route, async ({ page }) => {
      await page.setViewportSize({ width: 1366, height: 900 });
      await page.goto(route);
      await expect(page.locator('main h1').first()).toBeVisible({ timeout: 20_000 });
      await page.waitForLoadState('networkidle').catch(() => undefined);
      const { bad, checked } = await smallText(page);
      expect(checked).toBeGreaterThan(20);
      expect(bad).toEqual([]);
    });
  }
});
