import AxeBuilder from '@axe-core/playwright';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

/**
 * Kavram haritası: 200 düğümlük kurgusal projede ("Kurgusal harita testi (200 düğüm)") tüm grafı yükler,
 * 3 saniyelik programatik kaydırma + yakınlaştırma sırasında requestAnimationFrame ile kare hızını ölçer.
 * Ölçülen medyan fps test çıktısına yazılır; eşik 30 (hedef 60). Liste görünümü axe ile denetlenir.
 * Geliştirme veritabanı gerekir (scripts/dev-up.sh; harita test projesi `metis demo` ile oluşur).
 */

const BASE = process.env.METIS_E2E_URL ?? 'http://localhost:8000';
const USER = { username: 'ayse', password: 'Kurgusal-Parola-2026' };
const MAP_PROJECT = 'Kurgusal harita testi (200 düğüm)';

interface Me {
  csrf_token: string;
  preferences: Record<string, unknown>;
  memberships: { project_id: string; project_name: string }[];
}

async function login(request: APIRequestContext): Promise<Me> {
  const res = await request.post(`${BASE}/api/v1/auth/login`, { data: USER, headers: { Origin: BASE } });
  expect(res.ok(), await res.text()).toBeTruthy();
  return (await res.json()) as Me;
}

async function setProject(request: APIRequestContext, me: Me, projectId: string | null) {
  const res = await request.put(`${BASE}/api/v1/preferences/active_project_id`, { data: { value: projectId }, headers: { Origin: BASE, 'X-CSRF-Token': me.csrf_token } });
  expect(res.ok()).toBeTruthy();
}

async function withMapProject(page: Page, fn: () => Promise<void>) {
  const me = await login(page.request);
  const project = me.memberships.find((m) => m.project_name === MAP_PROJECT);
  test.skip(!project, `"${MAP_PROJECT}" projesi geliştirme veritabanında yok`);
  const previous = (me.preferences.active_project_id as string | undefined) ?? null;
  await setProject(page.request, me, project!.project_id);
  try {
    await fn();
  } finally {
    await setProject(page.request, me, previous);
  }
}

test.describe('Faz 7 — kavram haritası', () => {
  test('200 düğüm: kaydırma/yakınlaştırma sırasında kare hızı ≥ 30 fps', async ({ page }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await withMapProject(page, async () => {
      await page.goto('/harita?all=1');
      await expect(page.getByRole('button', { name: 'Tümünü göster' })).toHaveAttribute('aria-pressed', 'true');
      await expect(page.locator('.react-flow__node')).toHaveCount(200, { timeout: 60_000 });
      await expect(page.getByText('200 / 200 bilgi')).toBeVisible();
      const canvas = page.getByTestId('concept-map');
      const box = (await canvas.boundingBox())!;
      const cx = box.x + box.width / 2;
      const cy = box.y + box.height / 2;
      await page.waitForTimeout(800); // fitView animasyonu bitsin

      await page.evaluate(() => {
        const w = window as unknown as { __frames: number[]; __stop: boolean };
        w.__frames = [];
        w.__stop = false;
        const tick = (t: number) => {
          w.__frames.push(t);
          if (!w.__stop) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      });

      // 3 sn: sürükleyerek kaydır ve tekerlekle yakınlaştır/uzaklaştır (gerçek kullanıcı girdisi gibi).
      const started = Date.now();
      let i = 0;
      await page.mouse.move(cx, cy);
      while (Date.now() - started < 3000) {
        const phase = Math.floor((Date.now() - started) / 750) % 2;
        if (phase === 0) {
          await page.mouse.down();
          for (let k = 0; k < 12; k++) await page.mouse.move(cx + Math.sin((i + k) / 4) * 220, cy + Math.cos((i + k) / 5) * 140);
          await page.mouse.up();
        } else {
          for (let k = 0; k < 6; k++) await page.mouse.wheel(0, (i + k) % 12 < 6 ? -120 : 120);
        }
        i += 12;
      }

      const frames = await page.evaluate(() => {
        const w = window as unknown as { __frames: number[]; __stop: boolean };
        w.__stop = true;
        return w.__frames;
      });
      const deltas = frames.slice(1).map((t, k) => t - frames[k]!).sort((a, b) => a - b);
      const median = deltas[Math.floor(deltas.length / 2)]!;
      const p90 = deltas[Math.floor(deltas.length * 0.9)]!;
      const medianFps = Math.round((1000 / median) * 10) / 10;
      const p10Fps = Math.round((1000 / p90) * 10) / 10;
      const avgFps = Math.round(((frames.length - 1) / ((frames[frames.length - 1]! - frames[0]!) / 1000)) * 10) / 10;
      const report = `kavram haritası 200 düğüm: medyan ${medianFps} fps, ortalama ${avgFps} fps, en yavaş %10 ${p10Fps} fps (${frames.length} kare, hedef 60, eşik 30)`;
      console.log(report);
      test.info().annotations.push({ type: 'fps', description: report });
      expect(frames.length).toBeGreaterThan(30);
      expect(medianFps).toBeGreaterThanOrEqual(30);
    });
  });

  for (const scheme of ['light', 'dark'] as const) {
    test(`liste görünümü axe WCAG AA temiz (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize({ width: 1366, height: 900 });
      await withMapProject(page, async () => {
        await page.goto('/harita?view=list');
        await expect(page.getByRole('table', { name: 'İlişkiler tablosu' })).toBeVisible({ timeout: 30_000 });
        await expect(page.getByRole('columnheader', { name: 'Konu' })).toBeVisible();
        await expect(page.getByRole('columnheader', { name: 'İlişki' })).toBeVisible();
        await expect(page.getByRole('columnheader', { name: 'Hedef' })).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        // Kontrast durağan hâlde ölçülür: giriş/geçiş animasyonları (yük altında uzayabilir) bitmeden axe çalışmaz.
        await page.evaluate(() =>
          Promise.all(
            document
              .getAnimations()
              .filter((a) => a.effect?.getTiming().iterations !== Infinity)
              .map((a) => a.finished.catch(() => undefined)),
          ),
        );
        const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
        const summary = result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).slice(0, 3).join(' | ')}`);
        expect(summary).toEqual([]);
      });
    });
  }
});
