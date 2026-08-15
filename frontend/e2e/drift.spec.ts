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
  mockDriftResponse,
  mockResolveDrift,
  seedAuthenticatedSession,
  NO_CREDENTIAL_REASON,
} from "./fixtures/mocks";

/**
 * Phase 2 — Drift detection and resolution.
 *
 * Validates:
 *   1. Drift banner appears when the backend reports drift.
 *   2. Clean repos do not show the drift banner.
 *   3. Drift modal lists the affected repo and workflow.
 *   4. "Adopt GitHub Version" resolves drift and clears the banner.
 *   5. "Keep Local / Restore via PR" creates a PR and shows pr_pending state.
 *   6. A failed resolution keeps the drift banner visible and shows an error.
 *   7. New workflows are not treated as drifted.
 */
test.describe("Drift detection – UI display", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("drift banner is shown when the backend reports drift for a workflow", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "drift-demo",
      project_code: "DRFT",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI })],
    });

    await mockDriftResponse(page, {
      driftedWorkflows: [
        {
          workflow_name: PHASE2_WORKFLOWS.CI,
          workflow_filename: PHASE2_WORKFLOWS.CI,
          repo: PHASE2_REPOS.SERVICE_A,
          has_drift: true,
        },
      ],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));

    await page.goto(`/project/${TEST_USER}/drift-demo`);

    await expect(page.getByTestId("drift-banner")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("drift-banner")).toContainText(/workflow changed in GitHub/i);
  });

  test("drift banner is NOT shown when there is no drift", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "clean-project",
      project_code: "CLEAN",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI })],
    });

    await mockDriftResponse(page, { driftedWorkflows: [] });
    await installApiMocks(page, createMockState({ projects: [project] }));

    await page.goto(`/project/${TEST_USER}/clean-project`);

    // Wait for the project page to load (workflow list visible), then assert no drift banner.
    await expect(page.getByText(PHASE2_WORKFLOWS.CI, { exact: false }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("drift-banner")).toHaveCount(0);
  });

  test("drift banner renders from persisted state before the live check resolves", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "drift-seeded",
      project_code: "SEED",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI })],
      // Persisted by the last check and returned by the project load.
      drifted_workflow_names: [PHASE2_WORKFLOWS.CI],
    });

    // Hold the live check open well past first paint, so the banner can only
    // come from the persisted state, not from this response.
    await mockDriftResponse(page, {
      driftedWorkflows: [
        {
          workflow_name: PHASE2_WORKFLOWS.CI,
          workflow_filename: PHASE2_WORKFLOWS.CI,
          repo: PHASE2_REPOS.SERVICE_A,
          has_drift: true,
        },
      ],
      delayMs: 10_000,
    });
    await installApiMocks(page, createMockState({ projects: [project] }));

    await page.goto(`/project/${TEST_USER}/drift-seeded`);

    await expect(page.getByTestId("drift-banner")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId("drift-banner")).toContainText("1 workflow changed in GitHub");
    // Rows aren't available until the live check lands, so resolving is gated.
    await expect(page.getByTestId("review-drift-button")).toBeDisabled();
  });

  test("a project the sweep cannot check explains why, instead of freezing silently", async ({ page }) => {
    // The background sweep skips a project whose owner has no saved token. It
    // deliberately does not advance the last-checked time, so without this
    // message the timestamp just stops moving and the feature reads as broken.
    const project = makeProject({
      project_id: 1,
      project_name: "drift-notoken",
      project_code: "NOTK",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI })],
    });

    await mockDriftResponse(page, {
      driftedWorkflows: [
        {
          workflow_name: PHASE2_WORKFLOWS.CI,
          workflow_filename: PHASE2_WORKFLOWS.CI,
          repo: PHASE2_REPOS.SERVICE_A,
          has_drift: true,
        },
      ],
      staleReason: NO_CREDENTIAL_REASON,
    });
    await installApiMocks(page, createMockState({ projects: [project] }));

    await page.goto(`/project/${TEST_USER}/drift-notoken`);
    await expect(page.getByTestId("drift-banner")).toBeVisible({ timeout: 15_000 });
    await page.getByTestId("review-drift-button").click();

    await expect(page.getByTestId("drift-stale-reason")).toBeVisible();
    await expect(page.getByTestId("drift-stale-reason")).toContainText(
      /no saved GitHub token/i,
    );
  });

  test("a healthy project shows no stale-state warning", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "drift-healthy",
      project_code: "HLTH",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI })],
    });

    await mockDriftResponse(page, {
      driftedWorkflows: [
        {
          workflow_name: PHASE2_WORKFLOWS.CI,
          workflow_filename: PHASE2_WORKFLOWS.CI,
          repo: PHASE2_REPOS.SERVICE_A,
          has_drift: true,
        },
      ],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));

    await page.goto(`/project/${TEST_USER}/drift-healthy`);
    await expect(page.getByTestId("drift-banner")).toBeVisible({ timeout: 15_000 });
    await page.getByTestId("review-drift-button").click();

    await expect(page.getByTestId("drift-modal")).toBeVisible();
    await expect(page.getByTestId("drift-stale-reason")).toHaveCount(0);
  });

  test("seeded banner clears once the live check reports the drift is resolved", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "drift-stale",
      project_code: "STAL",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI })],
      // Stale persisted drift: already fixed in GitHub since the last check.
      drifted_workflow_names: [PHASE2_WORKFLOWS.CI],
    });

    await mockDriftResponse(page, { driftedWorkflows: [], delayMs: 1_000 });
    await installApiMocks(page, createMockState({ projects: [project] }));

    await page.goto(`/project/${TEST_USER}/drift-stale`);

    await expect(page.getByTestId("drift-banner")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId("drift-banner")).toHaveCount(0, { timeout: 15_000 });
  });

  test("drift modal shows the affected repo and workflow", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "drift-demo",
      project_code: "DRFT",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI })],
    });

    await mockDriftResponse(page, {
      driftedWorkflows: [
        {
          workflow_name: PHASE2_WORKFLOWS.CI,
          workflow_filename: PHASE2_WORKFLOWS.CI,
          repo: PHASE2_REPOS.SERVICE_A,
          has_drift: true,
        },
      ],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));

    await page.goto(`/project/${TEST_USER}/drift-demo`);

    await expect(page.getByTestId("drift-banner")).toBeVisible({ timeout: 15_000 });
    await page.getByTestId("review-drift-button").click();
    await expect(page.getByTestId("drift-modal")).toBeVisible();

    // Modal should list the affected repo and workflow
    await expect(page.getByTestId("drift-modal")).toContainText(PHASE2_REPOS.SERVICE_A);
    await expect(page.getByTestId("drift-modal")).toContainText(PHASE2_WORKFLOWS.CI);
  });

  test("workflow list shows drift badge for drifted workflow", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "drift-demo",
      project_code: "DRFT",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI })],
    });

    await mockDriftResponse(page, {
      driftedWorkflows: [
        {
          workflow_name: PHASE2_WORKFLOWS.CI,
          workflow_filename: PHASE2_WORKFLOWS.CI,
          repo: PHASE2_REPOS.SERVICE_A,
          has_drift: true,
        },
      ],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));

    await page.goto(`/project/${TEST_USER}/drift-demo`);

    // Wait for drift to load and the workflow list to render
    await expect(page.getByTestId("drift-banner")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("drift-badge")).toBeVisible();
  });
});

test.describe("Drift resolution – Adopt GitHub version", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("adopting GitHub version clears the drift banner and shows success", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "drift-demo",
      project_code: "DRFT",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI })],
    });

    // Drifted until the adoption actually happens, then clean. Keyed on the
    // resolve call rather than a fetch count: the panel legitimately fetches
    // drift more than once before the user acts (cached state first, then a
    // live re-check when that state is stale), and counting calls made this
    // test depend on how many of those happen to fire.
    let resolved = false;
    await page.route(/\/api\/projects\/[^/]+\/drift(\?.*)?$/, (route) => {
      const drifted =
        !resolved
          ? [
              {
                workflow_id: 1,
                workflow_name: PHASE2_WORKFLOWS.CI,
                workflow_filename: PHASE2_WORKFLOWS.CI,
                repo: PHASE2_REPOS.SERVICE_A,
                branch: "main",
                has_drift: true,
                actionsmanager_yaml: "name: CI\n",
                github_yaml: "name: CI\n# changed\n",
                actionsmanager_sha: "abc123",
                github_sha: "def456",
                last_checked: "2025-01-01T00:00:00Z",
                message: "Drift detected",
                is_shared_workflow: false,
                has_repo_override: false,
                project_id: 1,
                repo_id: 1,
                affected_repo_count: 0,
                affected_repos: [],
              },
            ]
          : [];

      return route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: corsHeaders(route),
        body: JSON.stringify({
          project_id: 1,
          project_name: "drift-demo",
          drift_count: drifted.length,
          drifted_workflows: drifted,
          last_checked: "2025-01-01T00:00:00Z",
        }),
      });
    });

    await mockResolveDrift(page, { responseState: "synced" });
    await installApiMocks(page, createMockState({ projects: [project] }));
    // Observed rather than routed: another mock already serves this endpoint,
    // and whichever page.route wins the match would swallow a second handler.
    // A request listener fires no matter who fulfils it.
    page.on("request", (req) => {
      if (req.url().includes("/api/drift/adopt-github-version")) resolved = true;
    });

    await page.goto(`/project/${TEST_USER}/drift-demo`);
    await expect(page.getByTestId("drift-banner")).toBeVisible({ timeout: 15_000 });

    // Open drift modal
    await page.getByTestId("review-drift-button").click();
    await expect(page.getByTestId("drift-modal")).toBeVisible();

    // Expand the diff view first (adopt button is inside the diff view)
    await page.getByRole("button", { name: /View Diff/i }).first().click();
    await expect(page.getByTestId("adopt-github-version-button").first()).toBeVisible();

    // Click adopt button
    await page.getByTestId("adopt-github-version-button").first().click();

    // Adopt mode modal should appear
    await expect(page.getByTestId("adopt-github-version-modal")).toBeVisible({ timeout: 5_000 });

    // Confirm adoption (default mode is already selected)
    await page.getByTestId("adopt-confirm-button").click();

    // Success message should appear somewhere in the modal or drift area
    await expect(page.getByTestId("drift-modal")).toContainText(/resolved|adopted|success/i, {
      timeout: 10_000,
    });
    // The drift banner must also disappear — the second drift-check call returns
    // clean state, so the banner should clear automatically after adoption.
    await expect(page.getByTestId("drift-banner")).toHaveCount(0, { timeout: 15_000 });
  });

  test("failed resolution keeps the drift banner visible and shows an error", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "drift-demo",
      project_code: "DRFT",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI })],
    });

    // Base mocks first so the specific failure mock takes priority (LIFO: last registered = first checked)
    await installApiMocks(page, createMockState({ projects: [project] }));
    await mockDriftResponse(page, {
      driftedWorkflows: [
        {
          workflow_name: PHASE2_WORKFLOWS.CI,
          workflow_filename: PHASE2_WORKFLOWS.CI,
          repo: PHASE2_REPOS.SERVICE_A,
          has_drift: true,
        },
      ],
    });
    await mockResolveDrift(page, { failWithStatus: 500 });

    await page.goto(`/project/${TEST_USER}/drift-demo`);
    await expect(page.getByTestId("drift-banner")).toBeVisible({ timeout: 15_000 });

    // Open modal and attempt View Diff + resolve
    await page.getByTestId("review-drift-button").click();
    await expect(page.getByTestId("drift-modal")).toBeVisible();

    // Click View Diff to expand a row, then try to resolve via direct restore.
    // The "Restore ActionsManager Version (Direct)" button appears in the diff view
    // when the adopt-github modal is not open. Click it and expect an error.
    await page.getByRole("button", { name: /View Diff/i }).first().click();
    await page.getByTestId("adopt-github-version-button").first().click();

    // Confirm adopt — backend returns 500
    await expect(page.getByTestId("adopt-github-version-modal")).toBeVisible({ timeout: 5_000 });
    await page.getByTestId("adopt-confirm-button").click();

    // Error should appear in modal (adoption failed)
    await expect(page.getByTestId("adopt-github-version-modal")).toContainText(/failed|error/i, {
      timeout: 10_000,
    });
    // Drift banner must still be visible since resolution failed
    await expect(page.getByTestId("drift-banner")).toBeVisible();
  });
});

test.describe("Drift resolution – workflow status badge stays in sync without reload", () => {
  // Regression for: after "Create Fix Pull Request", the workflow status
  // badge kept showing "Synced" until the page was reloaded, even though
  // the backend had already moved workflow_status to "under_review". Root
  // cause: DriftDetection only refreshed its own drift list afterward -
  // ProjectMgmt.tsx's workflows/rxworkflows state (which the badge reads
  // from) was never patched. Fixed via the onWorkflowStatusesChanged
  // callback. These tests must NOT call page.goto/reload between the
  // resolve action and the assertion - that's the whole point.
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("status badge updates to Under Review immediately after creating a fix PR", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "drift-pr-badge",
      project_code: "DPRB",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      workflows: [
        makeWorkflow({ name: PHASE2_WORKFLOWS.CI, workflowStatus: "synced_with_github" }),
      ],
    });

    await mockDriftResponse(page, {
      driftedWorkflows: [
        {
          workflow_id: 1,
          workflow_name: PHASE2_WORKFLOWS.CI,
          workflow_filename: PHASE2_WORKFLOWS.CI,
          repo: PHASE2_REPOS.SERVICE_A,
          has_drift: true,
        },
      ],
    });
    await mockResolveDrift(page, { responseState: "pr_pending" });
    await installApiMocks(page, createMockState({ projects: [project] }));

    await page.goto(`/project/${TEST_USER}/drift-pr-badge`);

    // The status badge lives in the editor header; the Project Files row carries
    // only a status dot. Select the workflow so the header is rendered.
    await page.getByText(PHASE2_WORKFLOWS.CI, { exact: false }).first().click();

    // Starting state: Synced - makes the transition below meaningful.
    await expect(page.getByTestId("workflow-status-badge").first()).toContainText(/Synced/i, {
      timeout: 15_000,
    });

    await expect(page.getByTestId("drift-banner")).toBeVisible({ timeout: 15_000 });
    await page.getByTestId("review-drift-button").click();
    await expect(page.getByTestId("drift-modal")).toBeVisible();
    await page.getByRole("button", { name: /View Diff/i }).first().click();
    await page.getByTestId("restore-pr-button").click();

    await expect(page.getByTestId("drift-modal")).toContainText(/pull request/i, { timeout: 10_000 });
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByTestId("drift-modal")).toHaveCount(0);

    // No page.goto/reload between the action above and this assertion.
    await expect(page.getByTestId("workflow-status-badge").first()).toContainText(/Under Review/i, {
      timeout: 10_000,
    });
  });

  test("status badge updates to Synced immediately after Restore Directly", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "drift-direct-badge",
      project_code: "DDRB",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      workflows: [
        makeWorkflow({ name: PHASE2_WORKFLOWS.CI, workflowStatus: "under_review" }),
      ],
    });

    await mockDriftResponse(page, {
      driftedWorkflows: [
        {
          workflow_id: 1,
          workflow_name: PHASE2_WORKFLOWS.CI,
          workflow_filename: PHASE2_WORKFLOWS.CI,
          repo: PHASE2_REPOS.SERVICE_A,
          has_drift: true,
        },
      ],
    });
    await mockResolveDrift(page, { responseState: "synced" });
    await installApiMocks(page, createMockState({ projects: [project] }));

    await page.goto(`/project/${TEST_USER}/drift-direct-badge`);

    // The status badge lives in the editor header; the Project Files row carries
    // only a status dot. Select the workflow so the header is rendered.
    await page.getByText(PHASE2_WORKFLOWS.CI, { exact: false }).first().click();

    await expect(page.getByTestId("workflow-status-badge").first()).toContainText(/Under Review/i, {
      timeout: 15_000,
    });

    await expect(page.getByTestId("drift-banner")).toBeVisible({ timeout: 15_000 });
    await page.getByTestId("review-drift-button").click();
    await expect(page.getByTestId("drift-modal")).toBeVisible();
    await page.getByRole("button", { name: /View Diff/i }).first().click();
    await page.getByTestId("restore-direct-button").click();
    await page.getByRole("button", { name: "Overwrite directly" }).click();

    await expect(page.getByTestId("drift-modal")).toContainText(/resolved|restored|success/i, {
      timeout: 10_000,
    });
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByTestId("drift-modal")).toHaveCount(0);

    // No page.goto/reload between the action above and this assertion.
    await expect(page.getByTestId("workflow-status-badge").first()).toContainText(/Synced/i, {
      timeout: 10_000,
    });
  });
});

test.describe("Drift regression – new workflows not treated as drift", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("a new workflow is shown as committed locally, not drifted", async ({ page }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "new-wf-project",
      project_code: "NWFP",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      pr_state: "draft",
      workflows: [
        makeWorkflow({
          name: PHASE2_WORKFLOWS.CI,
          workflowStatus: "committed_locally",
        }),
      ],
    });

    await mockDriftResponse(page, { driftedWorkflows: [] });
    await installApiMocks(page, createMockState({ projects: [project] }));

    await page.goto(`/project/${TEST_USER}/new-wf-project`);

    // The workflow should be visible
    await expect(
      page.getByText(PHASE2_WORKFLOWS.CI, { exact: false }).first(),
    ).toBeVisible({ timeout: 15_000 });

    // No drift badge should appear
    await expect(page.getByTestId("drift-badge")).toHaveCount(0);
    // No drift banner either
    await expect(page.getByTestId("drift-banner")).toHaveCount(0);
  });

  test("workflow stays Under Review after PR creation — not incorrectly treated as drift", async ({
    page,
  }) => {
    const project = makeProject({
      project_id: 1,
      project_name: "review-project",
      project_code: "RVWP",
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
            branch_name: "actions-manager/review-project",
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

    // Return no drift — the open PR should NOT be confused with drift
    await mockDriftResponse(page, { driftedWorkflows: [] });
    await installApiMocks(page, state);

    await page.goto(`/project/${TEST_USER}/review-project`);

    // Wait for the project page to load, then assert no drift-related elements.
    await expect(page.getByText(PHASE2_WORKFLOWS.CI, { exact: false }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("drift-banner")).toHaveCount(0);
    await expect(page.getByTestId("drift-badge")).toHaveCount(0);

    // Navigate to project list to check the project-level status badge
    await page.goto(`/project/${TEST_USER}`);
    await expect(page.getByTestId("project-status-1")).toContainText(/Under Review/i, {
      timeout: 15_000,
    });
  });
});
