import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for ATRIO demo video recording.
 *
 * Differs from `frontend/playwright.config.ts` in three ways:
 *   1. Records video at 1440×900 for high-quality demo capture.
 *   2. slowMo=180ms so viewers can follow the UI; no parallelism.
 *   3. webServer is NEVER spawned — assumes docker compose stack is already up
 *      at WEB_BASE_URL + API_BASE_URL.
 */
export default defineConfig({
  testDir: './specs',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'line',
  timeout: 15 * 60_000,
  outputDir: 'test-results-demo',
  use: {
    baseURL: process.env.WEB_BASE_URL ?? 'http://localhost:8080',
    viewport: { width: 1440, height: 900 },
    video: 'on',
    screenshot: 'only-on-failure',
    launchOptions: { slowMo: 180 },
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
