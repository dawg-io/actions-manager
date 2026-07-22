import { test, expect } from '@playwright/test';

/**
 * Smoke test that confirms the React app boots and serves the root document.
 * Intentionally backend-independent so it can run as a CI gate without
 * spinning up the Python API.
 */
test('app shell loads and exposes the ActionsManager title', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/ActionsManager/i);
});
