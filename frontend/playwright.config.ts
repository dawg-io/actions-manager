import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for the Actions Manager frontend.
 *
 * The `webServer` block boots the React dev server on port 3000 so the e2e
 * tests have something to hit. In CI we don't reuse an existing server.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  // chromium runs on every PR (fast, catches most real bugs). firefox/webkit
  // exist to cover engine-divergent behavior (WebSocket reconnect, Clipboard
  // API, CodeMirror/IME) but only run in CI on push to develop - see the
  // `playwright-cross-browser-tests` job in .github/workflows/docker-build-and-test.yml
  // - selected explicitly via `--project`, so adding them here doesn't slow
  // down the PR-triggered `playwright-tests` job (issue #1551).
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],
  webServer: {
    command: 'npm start',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 90_000,
    env: {
      BROWSER: 'none',
    },
  },
});
