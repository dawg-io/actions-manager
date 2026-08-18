import type { Page } from "@playwright/test";

/**
 * Shared seed data for docs-screenshots specs. Deliberately separate from
 * e2e/fixtures/mocks' TEST_USER/TEST_USER_DETAILS — docs assets published in
 * the public docs site use doc-friendly usernames/projects, never the shared
 * e2e fixtures' "octocat"/"demo-project".
 */
export const DOCS_USER = "acme-corp";

/** Repositories shown in docs screenshots. The shared e2e fixtures use
 *  octocat/hello-world, which must never appear in published documentation. */
export const DOCS_REPOS = [
  { id: 1, name: "payments-service", full_name: `${DOCS_USER}/payments-service`, private: false, default_branch: "main" },
  { id: 2, name: "payments-worker", full_name: `${DOCS_USER}/payments-worker`, private: false, default_branch: "main" },
  { id: 3, name: "checkout-web", full_name: `${DOCS_USER}/checkout-web`, private: false, default_branch: "main" },
];

/** Replaces the shared fixtures' repository list with doc-friendly names.
 *  Register after installApiMocks (routes are LIFO). */
export async function seedDocsRepos(page: Page) {
  await page.route(
    (url) => url.pathname === "/api/repos",
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(DOCS_REPOS),
      })
  );
}

/** Overrides the /api/user/:username mock so the UI shows DOCS_USER instead
 *  of the shared fixtures' TEST_USER_DETAILS. Must be registered after
 *  installApiMocks (Playwright routes are LIFO) — same pattern as
 *  overrideUserAccountType in e2e/fixtures/mocks.ts. */
export interface DocsOnboarding {
  completed: boolean;
  completed_at: string | null;
  step: string | null;
}

export async function seedDocsUserProfile(page: Page, onboarding?: DocsOnboarding) {
  // The onboarding write the tour makes when a step advances; screenshots
  // never assert on it, they just must not 404.
  await page.route(
    (url) => /^\/api\/user\/[^/]+\/onboarding$/.test(url.pathname),
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(onboarding ?? { completed: true, completed_at: null, step: null }),
      })
  );

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
          // Omitted by default so the welcome screen and tour never appear in
          // screenshots that are documenting something else.
          ...(onboarding ? { onboarding } : {}),
        }),
      })
  );
}
