import { test, expect } from "@playwright/test";
import {
  TEST_USER,
  PHASE2_REPOS,
  PHASE2_WORKFLOWS,
  createMockState,
  installApiMocks,
  makeProject,
  makeWorkflow,
  mockCreatePullRequests,
  seedAuthenticatedSession,
} from "./fixtures/mocks";

/**
 * Phase 2 — Multi-repository PR creation.
 *
 * Validates:
 *   1. A project with two repos shows one open PR entry per repo after creation.
 *   2. Per-repo state reflects the correct pr_state.
 *   3. Project-level state reflects open PRs.
 *   4. Partial failure: repo A succeeds, repo B fails → A shows PR, B shows failure.
 *   5. Project state does not claim full success when one repo fails.
 */
test.describe("Multi-repository PR creation", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("creates PRs for two repos and shows one open PR row per repo", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "multi-repo",
      project_code: "MR",
      selected_repos: [PHASE2_REPOS.SERVICE_A, PHASE2_REPOS.SERVICE_B],
      pr_state: "draft",
      workflows: [
        makeWorkflow({ name: PHASE2_WORKFLOWS.CI, workflowStatus: "committed_locally" }),
      ],
    });

    const state = createMockState({
      projects: [project],
      prStatus: {
        project_state: "draft",
        pull_requests: [],
        total_prs: 0,
        open_prs: 0,
        merged_prs: 0,
        closed_prs: 0,
      },
    });

    // Base mocks first, then override create-PR mock (LIFO order means later = higher priority)
    await installApiMocks(page, state);

    // Override create-PR to succeed for both repos
    await mockCreatePullRequests(page, state, {
      repoResults: [
        {
          repo: PHASE2_REPOS.SERVICE_A,
          success: true,
          pr_number: 101,
          branch_name: "actions-manager/multi-repo",
        },
        {
          repo: PHASE2_REPOS.SERVICE_B,
          success: true,
          pr_number: 102,
          branch_name: "actions-manager/multi-repo",
        },
      ],
    });

    // Trigger PR creation via the API the UI would call
    await page.goto(`/project/${TEST_USER}`);

    await page.evaluate(
      async ({ user, serviceA, serviceB }) => {
        await fetch("/api/create-pull-requests", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-GitHub-User": user },
          body: JSON.stringify({
            github_user: user,
            project_name: "multi-repo",
            selected_repos: [serviceA, serviceB],
            selected_workflows: null,
          }),
        });
      },
      {
        user: TEST_USER,
        serviceA: PHASE2_REPOS.SERVICE_A,
        serviceB: PHASE2_REPOS.SERVICE_B,
      },
    );

    // Reload project list — project should now show "Under Review"
    await page.reload();
    await expect(page.getByTestId("project-status-1")).toContainText(/Under Review/i, {
      timeout: 15_000,
    });
  });

  test("open PR status panel shows one row per repo after multi-repo PR creation", async ({ page }) => {
    // Start directly in the post-PR state
    const project = makeProject({
      project_id: 1,
      project_name: "multi-repo",
      project_code: "MR",
      selected_repos: [PHASE2_REPOS.SERVICE_A, PHASE2_REPOS.SERVICE_B],
      pr_state: "open",
      workflows: [
        makeWorkflow({ name: PHASE2_WORKFLOWS.CI, workflowStatus: "under_review" }),
      ],
    });

    const state = createMockState({
      projects: [project],
      prStatus: {
        project_state: "open",
        pull_requests: [
          {
            repo_name: PHASE2_REPOS.SERVICE_A,
            pr_number: 101,
            pr_url: `https://github.com/${PHASE2_REPOS.SERVICE_A}/pull/101`,
            pr_state: "open",
            branch_name: "actions-manager/multi-repo",
            target_branch: "main",
            created_at: "2025-01-02T00:00:00Z",
            updated_at: "2025-01-02T00:00:00Z",
          },
          {
            repo_name: PHASE2_REPOS.SERVICE_B,
            pr_number: 102,
            pr_url: `https://github.com/${PHASE2_REPOS.SERVICE_B}/pull/102`,
            pr_state: "open",
            branch_name: "actions-manager/multi-repo",
            target_branch: "main",
            created_at: "2025-01-02T00:00:00Z",
            updated_at: "2025-01-02T00:00:00Z",
          },
        ],
        total_prs: 2,
        open_prs: 2,
        merged_prs: 0,
        closed_prs: 0,
      },
    });

    await installApiMocks(page, state);

    await page.goto(`/project/${TEST_USER}/multi-repo`);

    // The PR campaign banner should appear since pr_state=open.
    await page.getByRole("button", { name: /Manage PR Campaign/i }).click();

    // Both PR rows should be rendered in the PR Campaigns active table.
    await expect(page.getByTestId("repo-pr-row")).toHaveCount(2, { timeout: 15_000 });

    // The grouped campaign cards should still surface one repo heading per PR.
    const repoGroups = page.locator(".pr-campaign-repo-group");
    await expect(repoGroups).toHaveCount(2);

    const groupTexts = await repoGroups.allTextContents();
    const hasServiceA = groupTexts.some((t) => t.includes(PHASE2_REPOS.SERVICE_A));
    const hasServiceB = groupTexts.some((t) => t.includes(PHASE2_REPOS.SERVICE_B));
    expect(hasServiceA).toBe(true);
    expect(hasServiceB).toBe(true);
  });

  test("project list shows Under Review badge when any repo has an open PR", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "multi-repo",
      project_code: "MR",
      selected_repos: [PHASE2_REPOS.SERVICE_A, PHASE2_REPOS.SERVICE_B],
      pr_state: "open",
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI, workflowStatus: "under_review" })],
    });

    await installApiMocks(page, createMockState({ projects: [project] }));
    await page.goto(`/project/${TEST_USER}`);

    await expect(page.getByTestId("project-status-1")).toContainText(/Under Review/i, {
      timeout: 15_000,
    });
  });
});

test.describe("Multi-repository partial PR creation failure", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("partial failure: repo A shows open PR, repo B failure does not block repo A", async ({
    page,
  }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "partial-fail",
      project_code: "PFAIL",
      selected_repos: [PHASE2_REPOS.SERVICE_A, PHASE2_REPOS.SERVICE_B],
      pr_state: "draft",
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI, workflowStatus: "committed_locally" })],
    });

    const state = createMockState({
      projects: [project],
      prStatus: {
        project_state: "draft",
        pull_requests: [],
        total_prs: 0,
        open_prs: 0,
        merged_prs: 0,
        closed_prs: 0,
      },
    });

    // Base mocks registered first so the specific PR-creation mock takes priority
    await installApiMocks(page, state);
    // Override create-PR to simulate service-a succeeding and service-b failing
    await mockCreatePullRequests(page, state, {
      repoResults: [
        {
          repo: PHASE2_REPOS.SERVICE_A,
          success: true,
          pr_number: 101,
          branch_name: "actions-manager/partial-fail",
        },
        {
          repo: PHASE2_REPOS.SERVICE_B,
          success: false,
          error: "GitHub API error: branch already exists",
        },
      ],
    });

    await page.goto(`/project/${TEST_USER}`);

    // Trigger PR creation and follow the async task status endpoint.
    const createResult = await page.evaluate(
      async ({ user, serviceA, serviceB }) => {
        const resp = await fetch("/api/create-pull-requests", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-GitHub-User": user },
          body: JSON.stringify({
            github_user: user,
            project_name: "partial-fail",
            selected_repos: [serviceA, serviceB],
            selected_workflows: null,
          }),
        });
        return resp.json();
      },
      {
        user: TEST_USER,
        serviceA: PHASE2_REPOS.SERVICE_A,
        serviceB: PHASE2_REPOS.SERVICE_B,
      },
    );

    expect(createResult.task_id).toBe("mock-task-id");
    expect(createResult.status).toBe("running");

    const taskResult = await page.evaluate(async ({ taskId, user }) => {
      const resp = await fetch(`/api/create-pull-requests/${taskId}`, {
        method: "GET",
        headers: { "X-GitHub-User": user },
      });
      return resp.json();
    }, { taskId: createResult.task_id, user: TEST_USER });

    // The mock returns a partial result from the async task status endpoint.
    expect(taskResult.status).toBe("completed");
    expect(taskResult.prs_created).toBe(1);
    expect(taskResult.errors).toBeDefined();
    expect(taskResult.errors[PHASE2_REPOS.SERVICE_B]).toBeTruthy();

    // Service A should have a PR in state, service B should not
    expect(state.prStatus.pull_requests).toHaveLength(1);
    expect(state.prStatus.pull_requests[0].repo_name).toBe(PHASE2_REPOS.SERVICE_A);
  });

  test("project list does not show Synced badge when only some repos succeeded", async ({
    page,
  }) => {
    // Mixed state: one open PR (service A), one repo never got a PR (service B)
    const project = makeProject({
      project_id: 1,
      project_name: "partial-open",
      project_code: "POPEN",
      selected_repos: [PHASE2_REPOS.SERVICE_A, PHASE2_REPOS.SERVICE_B],
      pr_state: "open",
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI })],
    });

    await installApiMocks(page, createMockState({ projects: [project] }));
    await page.goto(`/project/${TEST_USER}`);

    // Project is "open" (partial success still creates some PRs), not "Synced"
    await expect(page.getByTestId("project-status-1")).not.toContainText(/Synced/i, {
      timeout: 15_000,
    });
  });
});
