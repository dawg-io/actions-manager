import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for regenerating docs/ screenshots.
 *
 * Separate from playwright.config.ts (testDir: './e2e') so this never runs
 * as part of `npm run test:e2e` / CI — it's an on-request tool, not a test
 * suite. Run with `npm run docs:screenshots`.
 */
export default defineConfig({
  testDir: "./docs-screenshots",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Approximates the resolution of the existing hand-captured
        // screenshots (~3420px wide @2x). Exact pixel match isn't required.
        // Must come after the devices['Desktop Chrome'] spread — it sets its
        // own viewport/deviceScaleFactor that would otherwise win.
        viewport: { width: 1710, height: 900 },
        deviceScaleFactor: 2,
      },
    },
  ],
  webServer: {
    command: "npm start",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 90_000,
    env: {
      BROWSER: "none",
    },
  },
});
