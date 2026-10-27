// Teslim ekran görüntüleri: docs/design/final/<ekran>-<tema>.png (1440×900) + 390 px mobil.
// Önkoşul: scripts/dev-up.sh --demo (API :8000, worker, kurgusal model). Kullanım: node scripts/final-screenshots.mjs
import { mkdirSync } from 'node:fs';
import { chromium } from 'playwright';

const BASE = process.env.METIS_URL ?? 'http://localhost:8000';
const OUT = new URL('../docs/design/final/', import.meta.url).pathname;
const USER = { username: 'ayse', password: 'Kurgusal-Parola-2026' };
mkdirSync(OUT, { recursive: true });

async function api(ctx, method, path, data, csrf) {
  const res = await ctx.request.fetch(`${BASE}${path}`, { method, data, headers: { Origin: BASE, ...(csrf ? { 'X-CSRF-Token': csrf } : {}) } });
  if (!res.ok()) throw new Error(`${method} ${path}: ${res.status()} ${await res.text()}`);
  const body = await res.text();
  return body ? JSON.parse(body) : null;
}

async function setup(ctx) {
  const me = await api(ctx, 'POST', '/api/v1/auth/login', USER);
  const demo = me.memberships.find((m) => m.project_name.startsWith('Kurgusal çalışma alanı')) ?? me.memberships[0];
  await api(ctx, 'PUT', '/api/v1/preferences/active_project_id', { value: demo.project_id }, me.csrf_token);
  await api(ctx, 'PUT', '/api/v1/preferences/theme', { value: 'system' }, me.csrf_token);
  const pages = await api(ctx, 'GET', `/api/v1/projects/${demo.project_id}/pages?limit=50`);
  const page = pages.items.find((p) => p.title.includes('UART')) ?? pages.items[0];
  const review = await api(ctx, 'GET', `/api/v1/projects/${demo.project_id}/changes?tab=review`);
  const reviewItems = review.items ?? review;
  return { pid: demo.project_id, pageId: page.page_id, reviewId: reviewItems[0]?.id };
}

async function settle(page, ms = 600) {
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(ms);
}

const shots = (ids) => [
  ['01-ana-sayfa', '/'],
  ['02-bilgi-havuzu', '/bilgi'],
  ['03-bilgi-sayfasi-iz', `/bilgi/${ids.pageId}`, async (p) => { await p.locator('[data-iz-marker]').first().click(); await p.waitForTimeout(1200); }],
  ['04-mentor-cevabi', `/mentor?q=${encodeURIComponent('SPI saat bölücü kaç?')}`, async (p) => { await p.getByText('Bilgi havuzundan birebir alıntılar').first().waitFor({ timeout: 30_000 }); await p.waitForTimeout(1500); }],
  ['05-yeni-katki', '/katki'],
  ['06-inceleme', ids.reviewId ? `/kayitlar/${ids.reviewId}` : '/kayitlar?tab=review'],
  ['07-gorevler', '/gorevler'],
  ['08-bilgi-sagligi', '/saglik'],
  ['09-kavram-haritasi', '/harita', async (p) => { await p.locator('.react-flow__node').first().waitFor({ timeout: 30_000 }); await p.waitForTimeout(1500); }],
  ['10-model-laboratuvari', '/lab'],
  ['11-ayarlar', '/ayarlar'],
];

const browser = await chromium.launch({ executablePath: process.env.PW_CHROMIUM || undefined });
for (const scheme of ['light', 'dark']) {
  const tema = scheme === 'light' ? 'acik' : 'koyu';
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: scheme, deviceScaleFactor: 1 });
  const ids = await setup(ctx);
  const page = await ctx.newPage();
  for (const [name, path, act] of shots(ids)) {
    await page.goto(`${BASE}${path}`);
    await settle(page);
    if (act) await act(page);
    await page.screenshot({ path: `${OUT}${name}-${tema}.png` });
    console.log(`${name}-${tema}.png`);
  }
  await ctx.close();
  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: scheme, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const mids = await setup(mobile);
  const mp = await mobile.newPage();
  for (const [name, path, act] of [shots(mids)[0], shots(mids)[2], shots(mids)[3]]) {
    await mp.goto(`${BASE}${path}`);
    await settle(mp);
    if (act) await act(mp);
    await mp.screenshot({ path: `${OUT}12-mobil-390-${name.slice(3)}-${tema}.png` });
    console.log(`12-mobil-390-${name.slice(3)}-${tema}.png`);
  }
  await mobile.close();
}
await browser.close();
