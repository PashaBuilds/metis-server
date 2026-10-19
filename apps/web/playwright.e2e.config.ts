import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';

/** Uçtan uca (Faz 1-2 kabul) testleri: izole metis_e2e veritabanıyla port 8001'de kendi sunucusunu başlatır. */
const root = path.resolve(import.meta.dirname, '../..');

export default defineConfig({
  testDir: '../../tests',
  testMatch: ['e2e/**/*.spec.ts'],
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  outputDir: 'test-results/e2e',
  use: {
    baseURL: 'http://localhost:8001',
    trace: 'retain-on-failure',
    launchOptions: { executablePath: process.env.PW_CHROMIUM ?? undefined },
  },
  // Kurulum testi ilk çalışmalı (boş veritabanında /kurulum); inceleme akışı onun oluşturduğu projeyi kullanır.
  projects: [
    { name: 'kurulum', testMatch: ['e2e/setup-source-iz.spec.ts'], use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'inceleme', testMatch: ['e2e/review-flow.spec.ts'], dependencies: ['kurulum'], use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    // Mentor akışı: Lab'da kurgusal model eklenir/test edilir/benchmark (worker + mock-llm :9102), sonra kaynaklı cevap.
    { name: 'mentor', testMatch: ['e2e/mentor-flow.spec.ts'], dependencies: ['inceleme'], use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    // Görevler ve bilgi sağlığı: mentor projesinin uygun modelini kullanır.
    { name: 'gorev-saglik', testMatch: ['e2e/tasks-health.spec.ts'], dependencies: ['mentor'], use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'gorsel', testMatch: ['e2e/figures.spec.ts'], dependencies: ['gorev-saglik'], use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    // Çıkış en sonda: yalnız kendi bağlamındaki oturumu kapatır.
    { name: 'cikis', testMatch: ['e2e/logout.spec.ts'], dependencies: ['gorsel'], use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
  ],
  webServer: {
    command: `bash ${path.join(root, 'scripts/e2e-server.sh')}`,
    cwd: root,
    url: 'http://localhost:8001/api/v1/health/ready',
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
});
