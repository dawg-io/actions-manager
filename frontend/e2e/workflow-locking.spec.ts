import { test, expect } from "@playwright/test";
import {
  TEST_USER,
  PHASE2_REPOS,
  PHASE2_WORKFLOWS,
  createMockState,
  installApiMocks,
  makeProject,
  makeWorkflow,
  seedAuthenticatedSession,
} from "./fixtures/mocks";

/**
 * Phase 2 — Workflow locking behavior when a PR is open.
 *
 * Validates:
 *   1. A workflow with `workflowStatus: "under_review"` shows the lock overlay.
 *   2. The lock overlay has the unlock button.
 *   3. Clicking unlock and confirming removes the lock overlay.
 *   4. After unlock, the primary action becomes "Commit and Update PR".
 *   5. Cancelling the unlock dialog keeps the overlay visible.
 *
 * Note: The full "update PR then re-lock on success" flow requires a live API
 * round-trip which is not simulated here; instead the happy-path UI state
 * is verified through the mock state transitions.
 */
test.describe("Workflow lock overlay with open PR", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("workflow under review shows the lock overlay", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "locked-project",
      project_code: "LCKD",
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
            pr_number: 42,
            pr_url: `https://github.com/${PHASE2_REPOS.SERVICE_A}/pull/42`,
            pr_state: "open",
            branch_name: "actions-manager/locked-project",
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
    await page.goto(`/project/${TEST_USER}/locked-project`);

    // Select the workflow to open the editor
    await page.getByText(PHASE2_WORKFLOWS.CI, { exact: false }).first().click();

    // Lock overlay should be visible on the editor
    await expect(page.getByTestId("workflow-lock-overlay")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("unlock-workflow-button")).toBeVisible();
  });

  test("unlock button opens the confirmation modal", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "locked-project",
      project_code: "LCKD",
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
            pr_number: 42,
            pr_url: `https://github.com/${PHASE2_REPOS.SERVICE_A}/pull/42`,
            pr_state: "open",
            branch_name: "actions-manager/locked-project",
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
    await page.goto(`/project/${TEST_USER}/locked-project`);

    await page.getByText(PHASE2_WORKFLOWS.CI, { exact: false }).first().click();
    await expect(page.getByTestId("workflow-lock-overlay")).toBeVisible({ timeout: 15_000 });

    await page.getByTestId("unlock-workflow-button").click();

    // Unlock confirmation modal should appear
    await expect(
      page.getByText(/Open Pull Request Detected/i),
    ).toBeVisible({ timeout: 5_000 });
  });

  test("confirming unlock removes the lock overlay", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "locked-project",
      project_code: "LCKD",
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
            pr_number: 42,
            pr_url: `https://github.com/${PHASE2_REPOS.SERVICE_A}/pull/42`,
            pr_state: "open",
            branch_name: "actions-manager/locked-project",
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
    await page.goto(`/project/${TEST_USER}/locked-project`);

    await page.getByText(PHASE2_WORKFLOWS.CI, { exact: false }).first().click();
    await expect(page.getByTestId("workflow-lock-overlay")).toBeVisible({ timeout: 15_000 });

    await page.getByTestId("unlock-workflow-button").click();
    await expect(page.getByText(/Open Pull Request Detected/i)).toBeVisible();

    // Confirm unlock
    await page.getByRole("button", { name: /Unlock and Edit/i }).click();

    // Lock overlay should be gone
    await expect(page.getByTestId("workflow-lock-overlay")).toHaveCount(0);
  });

  test("after unlock the primary action becomes Commit and Update PR", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "locked-project",
      project_code: "LCKD",
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
            pr_number: 42,
            pr_url: `https://github.com/${PHASE2_REPOS.SERVICE_A}/pull/42`,
            pr_state: "open",
            branch_name: "actions-manager/locked-project",
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
    await page.goto(`/project/${TEST_USER}/locked-project`);

    await page.getByText(PHASE2_WORKFLOWS.CI, { exact: false }).first().click();
    await expect(page.getByTestId("workflow-lock-overlay")).toBeVisible({ timeout: 15_000 });

    await page.getByTestId("unlock-workflow-button").click();
    await page.getByRole("button", { name: /Unlock and Edit/i }).click();
    await expect(page.getByTestId("workflow-lock-overlay")).toHaveCount(0);

    // The update-PR button should now be present
    await expect(page.getByTestId("update-pr-button")).toBeVisible();
    await expect(page.getByTestId("update-pr-button")).toContainText(/Update PR/i);
  });

  test("cancelling the unlock dialog keeps the lock overlay", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "locked-project",
      project_code: "LCKD",
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
            pr_number: 42,
            pr_url: `https://github.com/${PHASE2_REPOS.SERVICE_A}/pull/42`,
            pr_state: "open",
            branch_name: "actions-manager/locked-project",
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
    await page.goto(`/project/${TEST_USER}/locked-project`);

    await page.getByText(PHASE2_WORKFLOWS.CI, { exact: false }).first().click();
    await expect(page.getByTestId("workflow-lock-overlay")).toBeVisible({ timeout: 15_000 });

    await page.getByTestId("unlock-workflow-button").click();
    await expect(page.getByText(/Open Pull Request Detected/i)).toBeVisible();

    // Click Cancel (exact match to avoid the "🔙 Cancel" button in the editor toolbar)
    await page.getByRole("button", { name: "Cancel", exact: true }).click();

    // Lock overlay must still be visible
    await expect(page.getByTestId("workflow-lock-overlay")).toBeVisible();
    await expect(page.getByTestId("update-pr-button")).toHaveCount(0);
  });
});

test.describe("Workflow locking – synced workflow is not locked", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("a synced workflow does not show the lock overlay", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "synced-project",
      project_code: "SYN",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      pr_state: "synced",
      workflows: [
        makeWorkflow({
          name: PHASE2_WORKFLOWS.CI,
          workflowStatus: "synced_with_github",
        }),
      ],
    });

    await installApiMocks(
      page,
      createMockState({
        projects: [project],
        prStatus: {
          project_state: "synced",
          pull_requests: [],
          total_prs: 0,
          open_prs: 0,
          merged_prs: 1,
          closed_prs: 0,
        },
      }),
    );

    await page.goto(`/project/${TEST_USER}/synced-project`);

    await page.getByText(PHASE2_WORKFLOWS.CI, { exact: false }).first().click();

    // Clicking the workflow opens the editor header, which adds a second
    // workflow-status-badge alongside the one already visible in the list.
    // Waiting for count = 2 proves the editor panel has fully rendered.
    await expect(page.getByTestId("workflow-status-badge")).toHaveCount(2, { timeout: 15_000 });
    await expect(page.getByTestId("workflow-lock-overlay")).toHaveCount(0);
    await expect(page.getByTestId("update-pr-button")).toHaveCount(0);
  });
});
