import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.METIS_E2E_URL ?? 'http://localhost:8000';

export default defineConfig({
  testDir: '../../tests',
  // Yalnız görsel/axe/performans testleri (geliştirme sunucusu :8000). E2E akışları ayrı config'te, kendi geçici DB'siyle.
  testMatch: ['visual/**/*.spec.ts'],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  outputDir: 'test-results',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    launchOptions: { executablePath: process.env.PW_CHROMIUM ?? undefined },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
