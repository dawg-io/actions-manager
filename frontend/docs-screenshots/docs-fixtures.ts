import type { Page } from "@playwright/test";

/**
 * Shared seed data for docs-screenshots specs. Deliberately separate from
 * e2e/fixtures/mocks' TEST_USER/TEST_USER_DETAILS — docs assets published in
 * the public docs site use doc-friendly usernames/projects, never the shared
 * e2e fixtures' "octocat"/"demo-project".
 */
export const DOCS_USER = "acme-corp";

/** Overrides the /api/user/:username mock so the UI shows DOCS_USER instead
 *  of the shared fixtures' TEST_USER_DETAILS. Must be registered after
 *  installApiMocks (Playwright routes are LIFO) — same pattern as
 *  overrideUserAccountType in e2e/fixtures/mocks.ts. */
export async function seedDocsUserProfile(page: Page) {
  await page.route(
    (url) => /^\/api\/user\/[^/]+$/.test(url.pathname),
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          username: DOCS_USER,
          github_user: DOCS_USER,
          avatar_url: "",
          account_type: "Professional",
          github_account_type: "Organization",
          workspace_role: "admin",
        }),
      })
  );
}
