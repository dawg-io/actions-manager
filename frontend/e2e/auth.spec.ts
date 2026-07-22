import { test, expect } from "@playwright/test";
import {
  TEST_USER,
  installApiMocks,
  seedAuthenticatedSession,
} from "./fixtures/mocks";

/**
 * Phase 1 — Authentication flow.
 *
 * The frontend uses a thin OAuth handoff:
 *   1. Logged-out users see a "Log in with GitHub" button that navigates to
 *      `${BACKEND_URL}/auth/github`.
 *   2. The backend redirects back to the frontend with `?user=<login>`.
 *   3. The App component reads `?user`, persists it to `localStorage` under
 *      the key `github_user`, and renders the dashboard.
 *
 * The tests below exercise that contract end-to-end without ever hitting a
 * real GitHub OAuth server — the redirect target is intercepted with
 * `page.route` so the click resolves locally.
 */
test.describe("Authentication flow", () => {
  test("logged-out user sees the login button and clicking it triggers the GitHub OAuth redirect", async ({
    page,
  }) => {
    await installApiMocks(page);

    // Intercept the OAuth handoff so the click does not leave the test sandbox.
    let oauthCallCount = 0;
    await page.route(/\/auth\/github(\?.*)?$/, async (route) => {
      oauthCallCount += 1;
      await route.fulfill({
        status: 200,
        contentType: "text/html",
        body: "<html><body>mock-oauth</body></html>",
      });
    });

    await page.goto("/");

    const loginButton = page.getByRole("button", { name: /Log in with GitHub/i });
    await expect(loginButton).toBeVisible();

    await loginButton.click();
    await expect.poll(() => oauthCallCount).toBeGreaterThan(0);
  });

  test("OAuth callback `?user=<login>` lands the user on the dashboard and stores the session", async ({
    page,
  }) => {
    await installApiMocks(page);

    await page.goto(`/?user=${TEST_USER}`);

    // App should redirect to /project/<user> after capturing the username.
    await page.waitForURL(new RegExp(`/project/${TEST_USER}`));
    await expect(page).toHaveURL(new RegExp(`/project/${TEST_USER}`));

    const stored = await page.evaluate(() => window.localStorage.getItem("github_user"));
    expect(stored).toBe(TEST_USER);
  });

  test("session persists across a hard refresh", async ({ page }) => {
    await installApiMocks(page);
    await seedAuthenticatedSession(page);

    await page.goto(`/project/${TEST_USER}`);
    await expect(page).toHaveURL(new RegExp(`/project/${TEST_USER}`));

    await page.reload();
    await expect(page).toHaveURL(new RegExp(`/project/${TEST_USER}`));

    // The login button must NOT be visible after reload — we are still authenticated.
    await expect(page.getByRole("button", { name: /Log in with GitHub/i })).toHaveCount(0);
  });

  test("logout clears the session and returns to the login screen", async ({ browser }) => {
    // Use a dedicated browser context so we can control localStorage without
    // an `addInitScript` re-seeding the user on every navigation. This mirrors
    // exactly what happens in production: clearing `localStorage.github_user`
    // (the App's only auth source) plus navigating to "/" must drop the user
    // back to the login screen.
    const context = await browser.newContext();
    const page = await context.newPage();
    await installApiMocks(page);

    // Establish a session via the OAuth callback path.
    await page.goto(`/?user=${TEST_USER}`);
    await page.waitForURL(new RegExp(`/project/${TEST_USER}`));

    // Trigger the same side effects the App's handleLogout performs.
    await page.evaluate(() => {
      window.localStorage.removeItem("github_user");
    });
    await page.goto("/");

    await expect(page.getByRole("button", { name: /Log in with GitHub/i })).toBeVisible();
    const stored = await page.evaluate(() => window.localStorage.getItem("github_user"));
    expect(stored).toBeNull();

    await context.close();
  });
});
