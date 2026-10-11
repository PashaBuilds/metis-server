import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import path from 'node:path';

const OUT = path.resolve(__dirname, '../../docs/design');
const VIEWPORTS = [
  { name: '1366', width: 1366, height: 768 },
  { name: '1920', width: 1920, height: 1080 },
  { name: '390', width: 390, height: 844 },
];

test.describe('Faz 0 — tasarım vitrini', () => {
  for (const vp of VIEWPORTS) {
    test(`ekran görüntüsü ${vp.name}px, yatay kaydırma yok`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto('/_vitrin');
      await expect(page.getByRole('heading', { name: 'İz tasarım vitrini' })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      await page.screenshot({ path: `${OUT}/vitrin-${vp.name}.png`, fullPage: true });
    });
  }

  for (const scheme of ['light', 'dark'] as const) {
    test(`axe WCAG AA temiz (${scheme} sistem teması)`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize({ width: 1366, height: 900 });
      await page.goto('/_vitrin');
      await page.evaluate(() => document.fonts.ready);
      const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      const summary = result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).slice(0, 3).join(' | ')}`);
      expect(summary).toEqual([]);
    });
  }

  test('Türkçe glifler IBM Plex Sans/Mono ile yükleniyor', async ({ page }) => {
    await page.goto('/_vitrin');
    await page.evaluate(() => document.fonts.ready);
    const ok = await page.evaluate(async () => {
      await document.fonts.load('16px "IBM Plex Sans"', 'ğşıİĞŞ');
      await document.fonts.load('16px "IBM Plex Mono"', 'ğşıİ');
      return {
        sans: document.fonts.check('16px "IBM Plex Sans"', 'ğşıİĞŞüöçÜÖÇ'),
        mono: document.fonts.check('16px "IBM Plex Mono"', 'ğşıİ'),
        family: getComputedStyle(document.body).fontFamily,
      };
    });
    expect(ok.sans).toBe(true);
    expect(ok.mono).toBe(true);
    expect(ok.family).toContain('IBM Plex Sans');
  });

  test('12 px altında yazı yok', async ({ page }) => {
    await page.goto('/_vitrin');
    // Vitrin tembel yüklenir: içerik gelmeden taranırsa test boş listeyle yanlışlıkla geçer.
    await expect(page.getByRole('heading', { name: 'İz tasarım vitrini' })).toBeVisible();
    await expect(page.locator('li code').first()).toBeVisible();
    const small = await page.evaluate(() => {
      const bad: string[] = [];
      for (const el of Array.from(document.querySelectorAll<HTMLElement>('body *'))) {
        if (!el.childNodes.length || ![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent?.trim())) continue;
        const size = parseFloat(getComputedStyle(el).fontSize);
        if (size < 12) bad.push(`${el.tagName}.${el.className}:${size}`);
      }
      return bad;
    });
    expect(small).toEqual([]);
  });

  test('İz: tık → panel + iz çizgisi; Esc → kapanır ve odak işarete döner', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/_vitrin');
    const via = page.getByRole('button', { name: /^Kaynak 2/ });
    await via.click();
    const panel = page.locator('#iz-panel');
    await expect(panel).toBeVisible();
    await expect(panel.getByRole('heading', { name: /AXI PCIe kesme notu/ })).toBeVisible();
    await expect(panel.locator('mark')).toContainText('IMR kaydında');
    await expect(page.getByTestId('iz-trace')).toBeVisible();
    await page.screenshot({ path: `${OUT}/iz-prototip-1440.png` });
    await page.keyboard.press('Escape');
    await expect(panel).toBeHidden();
    await expect(via).toBeFocused();
  });

  test('İz: klavye ile (Tab + Enter)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/_vitrin');
    const via = page.getByRole('button', { name: /^Kaynak 1/ });
    await via.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('#iz-panel')).toBeVisible();
    await expect(via).toHaveAttribute('aria-expanded', 'true');
    await expect(page.getByTestId('iz-trace')).toBeVisible();
  });

  test('İz: reduced-motion iken çizgi animasyonsuz anında görünür', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/_vitrin');
    await page.getByRole('button', { name: /^Kaynak 3/ }).click();
    const trace = page.getByTestId('iz-trace').locator('path');
    await expect(trace).toBeVisible();
    const anim = await trace.evaluate((el) => getComputedStyle(el).animationName);
    expect(anim).toBe('none');
  });

  test('İz: dar ekranda panel çekmece olarak açılır', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/_vitrin');
    await page.getByRole('button', { name: /^Kaynak 1/ }).click();
    const panel = page.locator('#iz-panel');
    await expect(panel).toBeVisible();
    await page.screenshot({ path: `${OUT}/iz-prototip-390.png` });
    await page.keyboard.press('Escape');
    await expect(panel).toBeHidden();
  });
});
