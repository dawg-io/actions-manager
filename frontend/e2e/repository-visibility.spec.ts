/**
 * Repository visibility E2E tests.
 *
 * Regression coverage for the bug where a project created with private
 * repositories was incorrectly displayed with a "Public Repos" badge in
 * the project list.
 *
 * All backend calls are mocked — no real GitHub access is needed.
 *
 * Optional env vars (fall back to predictable mock values if unset):
 *   PLAYWRIGHT_PUBLIC_TEST_REPO   – full_name of a public mock repo
 *   PLAYWRIGHT_PRIVATE_TEST_REPO  – full_name of a private mock repo
 *   PLAYWRIGHT_TEST_GITHUB_USER   – GitHub username (defaults to TEST_USER)
 */
import { test, expect } from "@playwright/test";
import {
  TEST_USER,
  createMockState,
  installApiMocks,
  makeProject,
  overrideUserAccountType,
  seedAuthenticatedSession,
} from "./fixtures/mocks";

// ---- Test repo constants -------------------------------------------------------
// The mock /api/repos response (installed by installApiMocks) always contains:
//   "octocat/hello-world"    (private: false)
//   "octocat/spoon-knife"    (private: false)
//   "octocat/secret-project" (private: true)
//
// Override PLAYWRIGHT_PUBLIC_TEST_REPO / PLAYWRIGHT_PRIVATE_TEST_REPO to point
// at different repositories without touching the test code.

const PUBLIC_REPO = process.env.PLAYWRIGHT_PUBLIC_TEST_REPO ?? "octocat/hello-world";
const PRIVATE_REPO = process.env.PLAYWRIGHT_PRIVATE_TEST_REPO ?? "octocat/secret-project";
const TEST_GITHUB_USER = process.env.PLAYWRIGHT_TEST_GITHUB_USER ?? TEST_USER;

// ---- Helpers -------------------------------------------------------------------

/**
 * Fill in the new-project form and submit it.  Returns the project name used.
 *
 * Prerequisites
 * - Mocks must already be installed (installApiMocks called).
 * - For private projects, the Professional account-type override must be
 *   registered (overrideUserAccountType called after installApiMocks).
 */
async function fillAndSubmitNewProject(
  page: import("@playwright/test").Page,
  options: {
    projectName: string;
    visibility: "public" | "private";
    repo: string;
  },
): Promise<void> {
  const { projectName, visibility, repo } = options;

  await page.goto(`/project/${TEST_GITHUB_USER}/new`);

  // Caller Workflow Project (standard) is selected by default — verify it.
  await expect(page.locator('input[name="projectType"][value="standard"]')).toBeChecked();

  // Step 1: fill in basics before moving to repository visibility.
  await page.getByLabel(/Project Name:/i).fill(projectName);
  await page.getByRole("button", { name: "Continue" }).click();

  // Select the desired visibility scope.
  await page.getByTestId(`visibility-option-${visibility}`).click();

  // Pick the repository from the unified RepositoryBranchSelector by
  // toggling its checkbox row. The data-testid is keyed on the repo's
  // full_name so we don't depend on row ordering.
  await page.getByTestId(`available-checkbox-${repo}`).click();

  // Step 2: continue to review, then explicitly select Resource Naming Mode.
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("radio", { name: "Prefix Mode - Recommended" }).check();

  // Submit – shows a success toast then navigates.
  await page.getByRole("button", { name: /Create Project/i }).click();
}

/**
 * Clean up a project created during a test by issuing a DELETE against the
 * mocked /api/projects/{name} route.
 *
 * The DELETE is issued via `page.evaluate` so it runs inside the browser
 * context and is intercepted by the `page.route()` mock handlers — unlike
 * `page.request.delete()` which bypasses those handlers entirely. Errors are
 * swallowed and logged so a cleanup failure never causes a test to fail.
 */
async function deleteProject(
  page: import("@playwright/test").Page,
  projectName: string,
): Promise<void> {
  try {
    await page.evaluate(
      async ([name, user]) => {
        const backendUrl =
          (window as any).__env?.REACT_APP_BACKEND_URL ??
          process.env.REACT_APP_BACKEND_URL ??
          "http://localhost:8000";
        const url = `${backendUrl}/api/projects/${encodeURIComponent(name)}`;
        await fetch(url, {
          method: "DELETE",
          headers: { "X-GitHub-User": user },
        });
      },
      [projectName, TEST_GITHUB_USER] as [string, string],
    );
  } catch {
    console.warn(
      `[cleanup] Could not delete project "${projectName}" — remove manually if needed.`,
    );
  }
}

// ---- Tests ---------------------------------------------------------------------

test.describe("Repository visibility – project creation and display", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page, TEST_GITHUB_USER);
  });

  // ---------------------------------------------------------------------------
  // Regression test — this test MUST fail against the original bug (where the
  // mock POST handler omitted repository_visibility_scope from the created
  // project stub) and pass after the fix.
  // ---------------------------------------------------------------------------
  test("creates a private repository project with a Private Repos badge", async ({ page }) => {
    const projectName = `private-visibility-test-${crypto.randomUUID()}`;
    const state = createMockState({ projects: [] });

    // installApiMocks first, then override — LIFO ensures the override wins.
    await installApiMocks(page, state);
    await overrideUserAccountType(page, "Professional", TEST_GITHUB_USER);

    await fillAndSubmitNewProject(page, {
      projectName,
      visibility: "private",
      repo: PRIVATE_REPO,
    });

    // The success notification is now a toast (not a browser dialog).
    // Wait for navigation to the project list which happens immediately after.
    await page.waitForURL(new RegExp(`/project/${TEST_GITHUB_USER}$`));

    // --- Key regression assertions ---
    // Scope assertions to the specific project row (never a page-level match).
    const row = page.getByTestId(`project-row-${projectName}`);
    await expect(row).toBeVisible();
    await expect(row).toContainText(/\bPrivate\b/i);
    await expect(row).not.toContainText(/\bPublic\b/i);

    await deleteProject(page, projectName);
  });

  // ---------------------------------------------------------------------------
  test("creates a public repository project with a Public Repos badge", async ({ page }) => {
    const projectName = `public-visibility-test-${crypto.randomUUID()}`;
    const state = createMockState({ projects: [] });

    await installApiMocks(page, state);
    // No account-type override needed — public repos work for all tiers.

    await fillAndSubmitNewProject(page, {
      projectName,
      visibility: "public",
      repo: PUBLIC_REPO,
    });

    // The success notification is now a toast (not a browser dialog).
    // Wait for navigation to the project list which happens immediately after.
    await page.waitForURL(new RegExp(`/project/${TEST_GITHUB_USER}$`));

    const row = page.getByTestId(`project-row-${projectName}`);
    await expect(row).toBeVisible();
    await expect(row).toContainText(/\bPublic\b/i);
    await expect(row).not.toContainText(/\bPrivate\b/i);

    await deleteProject(page, projectName);
  });

  // ---------------------------------------------------------------------------
  // Persistence check — the badge must survive a full page reload because the
  // project list re-fetches from the mocked API on mount.
  // ---------------------------------------------------------------------------
  test("private project visibility badge persists after page reload", async ({ page }) => {
    const projectName = `private-persist-test-${crypto.randomUUID()}`;

    // Pre-seed the state directly (faster than going through the form).
    const state = createMockState({
      projects: [
        makeProject({
          project_id: 1,
          project_name: projectName,
          project_type: "standard",
          repository_visibility_scope: "private",
          selected_repos: [PRIVATE_REPO],
        }),
      ],
    });
    await installApiMocks(page, state);
    await overrideUserAccountType(page, "Professional", TEST_GITHUB_USER);

    await page.goto(`/project/${TEST_GITHUB_USER}`);

    // First load
    const row = page.getByTestId(`project-row-${projectName}`);
    await expect(row).toBeVisible();
    await expect(row).toContainText(/\bPrivate\b/i);
    await expect(row).not.toContainText(/\bPublic\b/i);

    // Reload — the mocked routes persist across navigation events.
    await page.reload();

    const reloadedRow = page.getByTestId(`project-row-${projectName}`);
    await expect(reloadedRow).toBeVisible();
    await expect(reloadedRow).toContainText(/\bPrivate\b/i);
    await expect(reloadedRow).not.toContainText(/\bPublic\b/i);

    await deleteProject(page, projectName);
  });

  // ---------------------------------------------------------------------------
  // Sidebar consistency check — when the project is open, the sidebar badge
  // must also read "Private Repos".
  // ---------------------------------------------------------------------------
  test("private project shows Private Repos in the sidebar", async ({ page }) => {
    const projectName = `private-sidebar-test-${crypto.randomUUID()}`;

    const state = createMockState({
      projects: [
        makeProject({
          project_id: 1,
          project_name: projectName,
          project_type: "standard",
          project_code: "PRIV",
          repository_visibility_scope: "private",
          selected_repos: [PRIVATE_REPO],
        }),
      ],
    });
    await installApiMocks(page, state);
    await overrideUserAccountType(page, "Professional", TEST_GITHUB_USER);

    // Navigate directly to the project management page.
    await page.goto(`/project/${TEST_GITHUB_USER}/${encodeURIComponent(projectName)}`);

    // The sidebar shows the badge only when the project is not collapsed and
    // repositoryVisibilityScope is truthy (set from the API response).
    const sidebarBadge = page.getByTestId("sidebar-project-visibility-badge");
    await expect(sidebarBadge).toBeVisible();
    await expect(sidebarBadge).toHaveText(/Private Repos/i);
    await expect(sidebarBadge).not.toHaveText(/Public Repos/i);

    await deleteProject(page, projectName);
  });
});
