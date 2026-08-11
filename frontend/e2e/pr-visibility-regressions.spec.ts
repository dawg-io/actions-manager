import { test, expect } from "@playwright/test";
import {
  TEST_USER,
  PHASE2_REPOS,
  PHASE2_WORKFLOWS,
  corsHeaders,
  createMockState,
  installApiMocks,
  makeProject,
  makeWorkflow,
  seedAuthenticatedSession,
} from "./fixtures/mocks";

/**
 * Phase 2 — PR visibility regressions.
 *
 * Validates known regressions around PR state and cross-project PR leakage:
 *
 *   1. Open PR for project A does not appear in project B's view.
 *   2. Merged PRs do not appear in the active Open PRs area.
 *   3. Merged PRs leave the project in Synced state, not Open.
 *   4. Under-review state persists across a reload (not reverted to "Committed Locally").
 *   5. A workflow that was synced after PR merge does NOT appear as drift on
 *      a subsequent page load.
 *   6. A local commit after PR merge shows "Committed Locally" locally, not drift.
 */
test.describe("Open PR visibility isolation", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("open PR for project A does not appear in project B's PR panel", async ({ page }) => {
    const projectA = makeProject({
      project_id: 1,
      project_name: "project-a",
      project_code: "PRJA",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      pr_state: "open",
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI, workflowStatus: "under_review" })],
    });
    const projectB = makeProject({
      project_id: 2,
      project_name: "project-b",
      project_code: "PRJB",
      selected_repos: [PHASE2_REPOS.SERVICE_B],
      pr_state: "new",
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI, workflowStatus: "committed_locally" })],
    });

    // Base mocks first, then override the project-pr-status handler
    // (Playwright uses LIFO order: last registered = first checked)
    const state = createMockState({ projects: [projectA, projectB] });
    await installApiMocks(page, state);

    // Override the project-pr-status endpoint per-project
    await page.route(/\/api\/project-pr-status(\?.*)?$/, (route) => {
      const url = new URL(route.request().url());
      const projectName = url.searchParams.get("project_name") ?? "";

      if (projectName === "project-a") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          headers: corsHeaders(route),
          body: JSON.stringify({
            project_state: "open",
            pull_requests: [
              {
                repo_name: PHASE2_REPOS.SERVICE_A,
                pr_number: 42,
                pr_url: `https://github.com/${PHASE2_REPOS.SERVICE_A}/pull/42`,
                pr_state: "open",
                branch_name: "actions-manager/project-a",
                target_branch: "main",
                created_at: "2025-01-02T00:00:00Z",
                updated_at: "2025-01-02T00:00:00Z",
              },
            ],
            total_prs: 1,
            open_prs: 1,
            merged_prs: 0,
            closed_prs: 0,
          }),
        });
      }

      // project-b has no PRs
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: corsHeaders(route),
        body: JSON.stringify({
          project_state: "new",
          pull_requests: [],
          total_prs: 0,
          open_prs: 0,
          merged_prs: 0,
          closed_prs: 0,
        }),
      });
    });

    // Navigate to project-b
    await page.goto(`/project/${TEST_USER}/project-b`);

    // Wait for project page to load.
    await expect(page.getByText("Project Key: PRJB", { exact: false })).toBeVisible({ timeout: 15_000 });
    // If project-A's open PR leaked into project-B's state, the "Pull Requests
    // Open" banner and its "View PR Status" button would be rendered. Assert
    // they are absent — that is what proves cross-project isolation.
    await expect(
      page.getByRole("button", { name: /View pull request status/i }),
    ).toHaveCount(0);

    // project-b status should NOT say "Under Review"
    await page.goto(`/project/${TEST_USER}`);
    await expect(page.getByTestId("project-status-2")).not.toContainText(/Under Review/i, {
      timeout: 15_000,
    });
  });

  test("project list shows each project's own state independently", async ({ page }) => {
    const projects = [
      makeProject({ project_id: 1, project_name: "alpha", pr_state: "open" }),
      makeProject({ project_id: 2, project_name: "beta", pr_state: "draft" }),
      makeProject({ project_id: 3, project_name: "gamma", pr_state: "synced" }),
    ];
    await installApiMocks(page, createMockState({ projects }));
    await page.goto(`/project/${TEST_USER}`);

    await expect(page.getByTestId("project-status-1")).toContainText(/Under Review/i, { timeout: 15_000 });
    await expect(page.getByTestId("project-status-2")).toContainText(/Draft/i);
    await expect(page.getByTestId("project-status-3")).toContainText(/Synced/i);
  });
});

test.describe("Merged PR visibility regression", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("merged PRs do NOT appear in the active open PR list", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "merged-pr-project",
      project_code: "MPR",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      pr_state: "synced",
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI, workflowStatus: "synced_with_github" })],
    });

    const state = createMockState({
      projects: [project],
      prStatus: {
        project_state: "synced",
        pull_requests: [
          {
            repo_name: PHASE2_REPOS.SERVICE_A,
            pr_number: 42,
            pr_url: `https://github.com/${PHASE2_REPOS.SERVICE_A}/pull/42`,
            pr_state: "merged",
            branch_name: "actions-manager/merged-pr-project",
            target_branch: "main",
            created_at: "2025-01-02T00:00:00Z",
            updated_at: "2025-01-03T00:00:00Z",
          },
        ],
        total_prs: 1,
        open_prs: 0,
        merged_prs: 1,
        closed_prs: 0,
      },
    });

    await installApiMocks(page, state);
    await page.goto(`/project/${TEST_USER}/merged-pr-project`);

    // Wait for project page to load.
    await expect(page.getByText("Project Key: MPR", { exact: false })).toBeVisible({ timeout: 15_000 });
    // The project is synced: all PRs are merged and open_prs = 0. The
    // "Pull Requests Open" banner — and its "View PR Status" button — must
    // NOT be rendered, which proves merged PRs are not leaking into the
    // active open-PR area.
    await expect(
      page.getByRole("button", { name: /View pull request status/i }),
    ).toHaveCount(0);
  });

  test("project shows Synced (not Open) after all PRs are merged", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "post-merge",
      project_code: "POM",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      pr_state: "synced",
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI, workflowStatus: "synced_with_github" })],
    });

    await installApiMocks(
      page,
      createMockState({
        projects: [project],
        prStatus: {
          project_state: "synced",
          pull_requests: [],
          total_prs: 1,
          open_prs: 0,
          merged_prs: 1,
          closed_prs: 0,
        },
      }),
    );

    await page.goto(`/project/${TEST_USER}`);
    await expect(page.getByTestId("project-status-1")).toContainText(/Synced/i, {
      timeout: 15_000,
    });
    await expect(page.getByTestId("project-status-1")).not.toContainText(/Under Review/i);
  });
});

test.describe("Under-review state persistence regression", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("workflow initially under review stays Under Review after a page reload", async ({
    page,
  }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "persist-review",
      project_code: "PREV",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      pr_state: "open",
      workflows: [
        makeWorkflow({
          name: PHASE2_WORKFLOWS.CI,
          workflowStatus: "under_review",
        }),
      ],
    });

    const state = createMockState({
      projects: [project],
      prStatus: {
        project_state: "open",
        pull_requests: [
          {
            repo_name: PHASE2_REPOS.SERVICE_A,
            pr_number: 55,
            pr_url: `https://github.com/${PHASE2_REPOS.SERVICE_A}/pull/55`,
            pr_state: "open",
            branch_name: "actions-manager/persist-review",
            target_branch: "main",
            created_at: "2025-01-02T00:00:00Z",
            updated_at: "2025-01-02T00:00:00Z",
          },
        ],
        total_prs: 1,
        open_prs: 1,
        merged_prs: 0,
        closed_prs: 0,
      },
    });

    await installApiMocks(page, state);
    await page.goto(`/project/${TEST_USER}/persist-review`);

    // The workflow should be visible in the list
    await expect(
      page.getByText(PHASE2_WORKFLOWS.CI, { exact: false }).first(),
    ).toBeVisible({ timeout: 15_000 });

    // Verify the project-level status is "Under Review"
    await page.goto(`/project/${TEST_USER}`);
    await expect(page.getByTestId("project-status-1")).toContainText(/Under Review/i, {
      timeout: 15_000,
    });

    // Reload and verify it doesn't flip to Draft/Committed
    await page.reload();
    await expect(page.getByTestId("project-status-1")).toContainText(/Under Review/i);
    await expect(page.getByTestId("project-status-1")).not.toContainText(/Draft/i);
    await expect(page.getByTestId("project-status-1")).not.toContainText(/Committed/i);
  });

  test("workflow under review shows Under Review badge in the workflow list", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "badge-review",
      project_code: "BREV",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      pr_state: "open",
      workflows: [
        makeWorkflow({
          name: PHASE2_WORKFLOWS.CI,
          workflowStatus: "under_review",
        }),
      ],
    });

    const state = createMockState({
      projects: [project],
      prStatus: {
        project_state: "open",
        pull_requests: [
          {
            repo_name: PHASE2_REPOS.SERVICE_A,
            pr_number: 55,
            pr_url: `https://github.com/${PHASE2_REPOS.SERVICE_A}/pull/55`,
            pr_state: "open",
            branch_name: "actions-manager/badge-review",
            target_branch: "main",
            created_at: "2025-01-02T00:00:00Z",
            updated_at: "2025-01-02T00:00:00Z",
          },
        ],
        total_prs: 1,
        open_prs: 1,
        merged_prs: 0,
        closed_prs: 0,
      },
    });

    await installApiMocks(page, state);
    await page.goto(`/project/${TEST_USER}/badge-review`);

    // In the compact Project Files list the status is a dot, not a badge; the
    // full label is carried on the row for hover/assistive tech.
    await expect(page.locator(".pf-row-dot.status-review").first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page.locator('.pf-row[aria-label*="Under Review"]').first(),
    ).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("Local commit after merge does not show drift", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("local edit after merge shows committed locally, not drift", async ({ page }) => {
    // Simulate: workflow was synced after PR merge, then user edited locally
    const project = makeProject({
      project_id: 1,
      project_name: "post-merge-edit",
      project_code: "PME",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      pr_state: "draft",
      workflows: [
        makeWorkflow({
          name: PHASE2_WORKFLOWS.CI,
          workflowStatus: "committed_locally",
        }),
      ],
    });

    const state = createMockState({
      projects: [project],
      prStatus: {
        project_state: "draft",
        pull_requests: [],
        total_prs: 0,
        open_prs: 0,
        merged_prs: 1,
        closed_prs: 0,
      },
    });

    // No drift – backend confirms local changes are not drift
    await page.route(/\/api\/projects\/[^/]+\/drift(\?.*)?$/, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: corsHeaders(route),
        body: JSON.stringify({
          project_id: 1,
          project_name: "post-merge-edit",
          drift_count: 0,
          drifted_workflows: [],
          last_checked: "2025-01-01T00:00:00Z",
        }),
      }),
    );
    await installApiMocks(page, state);

    await page.goto(`/project/${TEST_USER}/post-merge-edit`);

    // Wait for project page to load, then assert no drift-related elements.
    await expect(page.getByText("Project Key: PME", { exact: false })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("drift-banner")).toHaveCount(0);

    // Workflow badge should reflect local changes, not drift
    await expect(page.getByTestId("drift-badge")).toHaveCount(0);

    // Project badge should be Draft (local edits after merge)
    await page.goto(`/project/${TEST_USER}`);
    await expect(page.getByTestId("project-status-1")).toContainText(/Draft/i, {
      timeout: 15_000,
    });
  });
});
