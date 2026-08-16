import { test } from "@playwright/test";
import {
  createMockState,
  installApiMocks,
  makeProject,
  makeWorkflow,
  mockBuildMetricsResponse,
  mockDriftResponse,
  seedAuthenticatedSession,
  NO_CREDENTIAL_REASON,
} from "../e2e/fixtures/mocks";
import { DOCS_USER, seedDocsUserProfile } from "./docs-fixtures";

/**
 * Regenerates the screenshots embedded in docs/**\/*.md
 * (docs/assets/screenshots/<feature>/<name>.png). Run with
 * `npm run docs:screenshots`.
 *
 * Each test drives the real app against mocked API routes (no real backend,
 * no real GitHub session — see e2e/fixtures/mocks.ts) and overwrites the
 * existing PNG at the same path the corresponding doc page already
 * references. To add a new doc screenshot: add a test() below following the
 * same shape, using DOCS_USER and doc-friendly project/workflow names —
 * never the shared e2e fixtures' "octocat"/"demo-project" (those are fine
 * for functional tests, not for images published in the public docs site).
 *
 * The projects-dashboard scene lives in ./projects-video.spec.ts instead —
 * that doc asset is a recorded video, not a screenshot.
 */

/** Keeps every drift scene's "last checked" plausible for a published doc,
 *  instead of the shared fixtures' 2025-01-01 placeholder. */
const DOCS_LAST_CHECKED = "2026-07-24T09:12:00Z";

const DOCS_DRIFT_PROJECT = {
  project_name: "Payments Platform",
  project_code: "PAY",
  github_user: DOCS_USER,
  last_modified_by: DOCS_USER,
  updated_at: "2026-07-24T00:00:00Z",
  pr_state: "draft",
  selected_repos: ["acme-corp/payments-service", "acme-corp/payments-worker"],
} as const;

const DOCS_BUILD_METRICS_PROJECT = {
  project_name: "Payments Platform",
  project_code: "PAY",
  github_user: DOCS_USER,
  last_modified_by: DOCS_USER,
  updated_at: "2026-07-24T00:00:00Z",
  pr_state: "synced",
  selected_repos: ["acme-corp/payments-service", "acme-corp/payments-worker"],
} as const;

/** A fortnight of plausible build history: mostly green, with a bad Tuesday
 *  on deploy-production so the trend and the failures view have something
 *  real to show. */
const DOCS_BUILD_METRICS = (() => {
  // Relative to capture time, not a fixed date: this panel renders *relative*
  // times ("synced 4 minutes ago"), so a pinned fixture would publish a
  // screenshot reading "3 weeks ago" the moment it was committed.
  const DAY_MS = 24 * 60 * 60 * 1000;
  const day = (offset: number) => new Date(Date.now() - offset * DAY_MS).toISOString();
  const trend = Array.from({ length: 14 }, (_, i) => {
    const offset = 13 - i;
    const total = [6, 8, 7, 9, 6, 4, 3, 8, 11, 9, 7, 8, 6, 9][i];
    const failure = offset === 8 ? 4 : [0, 1, 0, 0, 1, 0, 0, 0, 2, 0, 1, 0, 0, 1][i];
    return { date: day(offset).slice(0, 10), total, success: total - failure, failure };
  });

  return {
    summary: {
      window_days: 30,
      last_synced: new Date(Date.now() - 4 * 60 * 1000).toISOString(),
      total_runs: 101,
      decided_runs: 98,
      conclusion_counts: { success: 86, failure: 12, cancelled: 3 },
      success_rate: 87.8,
      avg_duration_seconds: 268,
      p50_duration_seconds: 241,
      p95_duration_seconds: 612,
      avg_queue_seconds: 14,
      trend,
    },
    workflows: [
      {
        workflow_name: "build-and-test",
        workflow_filename: "build-and-test.yml",
        total: 68,
        success_rate: 94.1,
        avg_duration_seconds: 214,
        actions_url:
          "https://github.com/acme-corp/payments-service/actions/workflows/build-and-test.yml",
      },
      {
        workflow_name: "deploy-production",
        workflow_filename: "deploy-production.yml",
        total: 33,
        success_rate: 75.8,
        avg_duration_seconds: 379,
        actions_url:
          "https://github.com/acme-corp/payments-service/actions/workflows/deploy-production.yml",
      },
    ],
    recentRuns: [
      { github_run_id: 4821, run_number: 214, workflow_name: "build-and-test", repo: "acme-corp/payments-service", branch: "main", conclusion: "success", duration_seconds: 203, created_at: day(0) },
      { github_run_id: 4820, run_number: 96, workflow_name: "deploy-production", repo: "acme-corp/payments-service", branch: "main", conclusion: "failure", duration_seconds: 412, created_at: day(0) },
      { github_run_id: 4816, run_number: 213, workflow_name: "build-and-test", repo: "acme-corp/payments-worker", branch: "main", conclusion: "success", duration_seconds: 188, created_at: day(1) },
      { github_run_id: 4810, run_number: 95, workflow_name: "deploy-production", repo: "acme-corp/payments-service", branch: "release/4.2", conclusion: "success", duration_seconds: 366, created_at: day(1) },
      { github_run_id: 4804, run_number: 212, workflow_name: "build-and-test", repo: "acme-corp/payments-service", branch: "main", conclusion: "success", duration_seconds: 221, created_at: day(2) },
    ],
    scoped: {
      "deploy-production.yml": {
        total_runs: 33,
        decided_runs: 33,
        conclusion_counts: { success: 25, failure: 8 },
        success_rate: 75.8,
        avg_duration_seconds: 379,
        p50_duration_seconds: 361,
        p95_duration_seconds: 640,
        avg_queue_seconds: 22,
        // The real endpoint scopes the trend too. Without this the published
        // image would show the project-wide chart under a scoped heading.
        trend: Array.from({ length: 14 }, (_, i) => {
          const total = [2, 3, 2, 3, 2, 1, 1, 2, 4, 3, 2, 3, 2, 3][i];
          const failure = [0, 1, 0, 0, 1, 0, 0, 0, 3, 0, 1, 0, 0, 2][i];
          return { date: day(13 - i).slice(0, 10), total, success: total - failure, failure };
        }),
        recent_runs: [
          { github_run_id: 4820, run_number: 96, workflow_name: "deploy-production", repo: "acme-corp/payments-service", branch: "main", event: "push", status: "completed", conclusion: "failure", duration_seconds: 412, created_at: day(0), html_url: "https://github.com/acme-corp/payments-service/actions/runs/4820" },
          { github_run_id: 4810, run_number: 95, workflow_name: "deploy-production", repo: "acme-corp/payments-service", branch: "release/4.2", event: "push", status: "completed", conclusion: "success", duration_seconds: 366, created_at: day(1), html_url: "https://github.com/acme-corp/payments-service/actions/runs/4810" },
          { github_run_id: 4795, run_number: 94, workflow_name: "deploy-production", repo: "acme-corp/payments-service", branch: "main", event: "workflow_dispatch", status: "completed", conclusion: "success", duration_seconds: 344, created_at: day(3), html_url: "https://github.com/acme-corp/payments-service/actions/runs/4795" },
        ],
      },
    },
  };
})();

test.describe("docs screenshots", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page, DOCS_USER);
  });

  test("workspace backup page", async ({ page }) => {
    await installApiMocks(page, createMockState());
    await seedDocsUserProfile(page);
    await page.route("**/api/workspace/backup/info", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          backup_format_version: "1.0",
          table_count: 31,
          total_rows: 1284,
          tables: {
            accounts: 12,
            projects: 8,
            repos: 46,
            workflows: 122,
            workflow_versions: 940,
            project_workflows: 122,
            rulesets: 6,
            codeowners: 8,
            custom_files: 14,
            project_pull_requests: 6,
          },
          excluded_tables: ["auth_sessions"],
        }),
      })
    );

    await page.goto("/workspace/backup");
    await page.getByText(/1284 row\(s\)/).waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({ path: "../docs/assets/screenshots/backup-restore/workspace-backup.png" });
  });

  test("workspace drift settings page", async ({ page }) => {
    await installApiMocks(page, createMockState());
    await seedDocsUserProfile(page);
    await page.route("**/api/drift/settings", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          sweep_enabled: true,
          recheck_interval_minutes: 30,
          batch_size: 5,
          poll_interval_seconds: 60,
        }),
      })
    );

    await page.goto("/workspace/drift");
    await page.getByTestId("drift-settings-form").waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({ path: "../docs/assets/screenshots/drift-detection/drift-settings.png" });
  });

  test("workflow editor page view", async ({ page }) => {
    const project = makeProject({
      project_name: "Payments Platform",
      project_code: "PAY",
      github_user: DOCS_USER,
      last_modified_by: DOCS_USER,
      updated_at: "2026-07-24T00:00:00Z",
      pr_state: "draft",
      selected_repos: ["acme-corp/payments-service", "acme-corp/payments-worker"],
      workflows: [
        makeWorkflow({ name: "build-and-test.yml", lastModifiedBy: DOCS_USER }),
        makeWorkflow({ name: "deploy-production.yml", lastModifiedBy: DOCS_USER }),
      ],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));
    await seedDocsUserProfile(page);

    await page.goto(`/project/${DOCS_USER}/${encodeURIComponent("Payments Platform")}`);
    await page
      .getByText("build-and-test.yml", { exact: false })
      .first()
      .waitFor({ timeout: 15000 });
    await page.getByText("build-and-test.yml", { exact: false }).first().click();
    await page.waitForTimeout(500);

    await page.screenshot({ path: "../docs/assets/screenshots/workflows/workflow-page-view.png" });

    // Expanded editor, in GUI mode: that's where the extra room actually
    // shows - the job list and step panel stop being a column of a column.
    await page.getByRole("button", { name: "GUI", exact: true }).click();
    await page.waitForTimeout(300);
    await page.getByRole("button", { name: /Expand/ }).click();
    await page.getByRole("dialog").waitFor({ timeout: 5000 });
    await page.waitForTimeout(500);
    await page.screenshot({ path: "../docs/assets/screenshots/workflows/workflow-editor-expanded.png" });
  });

  test("PR campaign dashboard", async ({ page }) => {
    const project = makeProject({
      project_name: "Payments Platform",
      project_code: "PAY",
      github_user: DOCS_USER,
      last_modified_by: DOCS_USER,
      updated_at: "2026-07-24T00:00:00Z",
      pr_state: "open",
      selected_repos: ["acme-corp/payments-service", "acme-corp/payments-worker"],
      workflows: [makeWorkflow({ name: "build-and-test.yml", lastModifiedBy: DOCS_USER })],
    });
    const state = createMockState({
      projects: [project],
      prStatus: {
        project_state: "open",
        pull_requests: [
          {
            repo_name: "acme-corp/payments-service",
            pr_number: 128,
            pr_url: "https://github.com/acme-corp/payments-service/pull/128",
            pr_state: "open",
            branch_name: "actions-manager/payments-platform",
            target_branch: "main",
            title: "Update build-and-test.yml",
            author: DOCS_USER,
            workflow_names: "build-and-test.yml",
            created_at: "2026-07-18T00:00:00Z",
            updated_at: "2026-07-24T00:00:00Z",
          },
          {
            repo_name: "acme-corp/payments-worker",
            pr_number: 74,
            pr_url: "https://github.com/acme-corp/payments-worker/pull/74",
            pr_state: "merged",
            branch_name: "actions-manager/payments-platform",
            target_branch: "main",
            title: "Update build-and-test.yml",
            author: DOCS_USER,
            workflow_names: "build-and-test.yml",
            created_at: "2026-07-01T00:00:00Z",
            updated_at: "2026-07-24T00:00:00Z",
            merged_at: "2026-07-24T00:00:00Z",
          },
        ],
        total_prs: 2,
        open_prs: 1,
        merged_prs: 1,
        closed_prs: 0,
      },
      // The creation-time snapshot the card reads: which branch mode the
      // project is on, and per target the base branch + commit, the PR that
      // opened against it, and what branch protection was in force. Without
      // these the card falls back to its bare form and the screenshot stops
      // matching what the docs describe.
      campaignExtras: {
        branch_option: "default",
        target_repos: ["acme-corp/payments-service", "acme-corp/payments-worker"],
        base_commits: {
          "acme-corp/payments-service on main": "9c41f7ab26d3e5108b7c4f0da2e6913d5f8a0b47",
          "acme-corp/payments-worker on main": "4e83d0c9157fa62b8d0e391c47a5b8206fd1e93c",
        },
        target_pr_urls: {
          "acme-corp/payments-service on main": "https://github.com/acme-corp/payments-service/pull/128",
          "acme-corp/payments-worker on main": "https://github.com/acme-corp/payments-worker/pull/74",
        },
        branch_protection: {
          "acme-corp/payments-service on main": {
            status: "protected",
            required_reviews: 2,
            required_status_checks: ["ci/build", "ci/test"],
            enforce_admins: true,
          },
          "acme-corp/payments-worker on main": { status: "none" },
        },
      },
    });
    await installApiMocks(page, state);
    await seedDocsUserProfile(page);

    // Taller than the shared viewport: the expanded card runs well past 900px,
    // and the parts the docs describe sit at both ends of it — header tiles and
    // the rollback control at the top, per-repository base commits and the
    // bulk-operation buttons at the bottom. `fullPage` cannot reach them, since
    // the app scrolls an inner container rather than the document.
    await page.setViewportSize({ width: 1710, height: 1500 });

    await page.goto(`/project/${DOCS_USER}/${encodeURIComponent("Payments Platform")}`);
    await page.getByRole("button", { name: "PR Campaigns" }).click();
    await page
      .getByText("Update build-and-test.yml", { exact: false })
      .first()
      .waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    // fullPage: the expanded card is taller than the viewport, and the parts
    // the docs describe sit at both ends of it — the header tiles and rollback
    // control at the top, the per-repository base commits and bulk-operation
    // buttons at the bottom. A viewport shot can only ever show one end.
    await page.screenshot({
      path: "../docs/assets/screenshots/pr-campaigns/pr-campaign.png",
      fullPage: true,
    });
  });

  test("PR campaign rollback review", async ({ page }) => {
    const project = makeProject({
      project_name: "Payments Platform",
      project_code: "PAY",
      github_user: DOCS_USER,
      last_modified_by: DOCS_USER,
      updated_at: "2026-07-24T00:00:00Z",
      pr_state: "open",
      selected_repos: ["acme-corp/payments-service", "acme-corp/payments-worker"],
      workflows: [makeWorkflow({ name: "build-and-test.yml", lastModifiedBy: DOCS_USER })],
    });
    // The campaign bumped the runner image everywhere. payments-service can be
    // inverted cleanly; payments-worker was edited by hand after the merge, so it
    // is flagged rather than clobbered — the two cases the docs describe.
    const beforeRollback = [
      "name: Build and Test",
      "on:",
      "  push:",
      "    branches: [main]",
      "jobs:",
      "  build:",
      "    runs-on: ubuntu-24.04",
      "    steps:",
      "      - uses: actions/checkout@v4",
      "      - run: npm ci",
      "      - run: npm test",
      "",
    ].join("\n");
    const afterRollback = beforeRollback.replace("ubuntu-24.04", "ubuntu-latest");

    const state = createMockState({
      projects: [project],
      prStatus: {
        project_state: "open",
        pull_requests: [
          {
            repo_name: "acme-corp/payments-service",
            pr_number: 128,
            pr_url: "https://github.com/acme-corp/payments-service/pull/128",
            pr_state: "merged",
            branch_name: "actions-manager/payments-platform",
            target_branch: "main",
            title: "Update build-and-test.yml",
            author: DOCS_USER,
            workflow_names: "build-and-test.yml",
            created_at: "2026-07-01T00:00:00Z",
            updated_at: "2026-07-24T00:00:00Z",
            merged_at: "2026-07-24T00:00:00Z",
          },
        ],
        total_prs: 1,
        open_prs: 0,
        merged_prs: 1,
        closed_prs: 0,
      },
      rollbackPreview: {
        campaign_id: 1,
        campaign_name: "Update build-and-test.yml",
        invertible_count: 1,
        targets: [
          {
            repo_name: "acme-corp/payments-service",
            target_branch: "main",
            pr_number: 128,
            pr_url: "https://github.com/acme-corp/payments-service/pull/128",
            workflow_names: "build-and-test.yml",
            invertible: true,
            reason: null,
            files: [
              {
                path: ".github/workflows/build-and-test.yml",
                action: "restore",
                before: beforeRollback,
                after: afterRollback,
              },
            ],
          },
          {
            repo_name: "acme-corp/payments-worker",
            target_branch: "main",
            pr_number: 74,
            pr_url: "https://github.com/acme-corp/payments-worker/pull/74",
            workflow_names: "build-and-test.yml",
            invertible: false,
            reason:
              ".github/workflows/build-and-test.yml changed on main after this campaign merged — rolling back would discard that change.",
            files: [],
          },
        ],
      },
    });
    await installApiMocks(page, state);
    await seedDocsUserProfile(page);

    // Tall enough for the whole dialog: at 900px it cut off mid-way through the
    // "once the rollback merges" choice, which the docs walk through as a step.
    await page.setViewportSize({ width: 1710, height: 1200 });

    await page.goto(`/project/${DOCS_USER}/${encodeURIComponent("Payments Platform")}`);
    await page.getByRole("button", { name: "PR Campaigns" }).click();
    // Every PR merged, so the campaign lives in Completed and starts collapsed.
    await page.getByRole("button", { name: /Completed Campaigns/i }).click();
    await page.getByText("Campaign: Update build-and-test.yml").click();
    await page.getByTestId("rollback-campaign-button").first().click();
    await page.getByTestId("rollback-summary").waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({ path: "../docs/assets/screenshots/pr-campaigns/pr-campaign-rollback.png" });
  });

  test("drift detection — bulk resolve", async ({ page }) => {
    const project = makeProject({
      project_name: "Payments Platform",
      project_code: "PAY",
      github_user: DOCS_USER,
      last_modified_by: DOCS_USER,
      updated_at: "2026-07-24T00:00:00Z",
      pr_state: "draft",
      selected_repos: ["acme-corp/payments-service", "acme-corp/payments-worker"],
      workflows: [makeWorkflow({ name: "build-and-test.yml", lastModifiedBy: DOCS_USER })],
    });
    // Realistic managed vs. GitHub content so the diff view screenshot shows
    // an actual, readable drift - someone added a lint step directly in
    // GitHub, bypassing ActionsManager.
    const managedYaml = [
      "name: Build and Test",
      "on:",
      "  push:",
      "    branches: [main]",
      "jobs:",
      "  build:",
      "    runs-on: ubuntu-latest",
      "    steps:",
      "      - uses: actions/checkout@v4",
      "      - run: npm ci",
      "      - run: npm test",
      "",
    ].join("\n");
    const githubYaml = [
      "name: Build and Test",
      "on:",
      "  push:",
      "    branches: [main]",
      "jobs:",
      "  build:",
      "    runs-on: ubuntu-latest",
      "    steps:",
      "      - uses: actions/checkout@v4",
      "      - run: npm ci",
      "      - run: npm test",
      "      - run: npm run lint",
      "",
    ].join("\n");

    // Same workflow, same github_sha, drifted identically in both repos -
    // this is what triggers the "N identical - select all" grouping link.
    await mockDriftResponse(page, {
      lastChecked: DOCS_LAST_CHECKED,
      driftedWorkflows: [
        {
          workflow_name: "build-and-test.yml",
          workflow_filename: "build-and-test.yml",
          repo: "acme-corp/payments-service",
          has_drift: true,
          github_sha: "f4a1c9e",
          actionsmanager_yaml: managedYaml,
          github_yaml: githubYaml,
        },
        {
          workflow_name: "build-and-test.yml",
          workflow_filename: "build-and-test.yml",
          repo: "acme-corp/payments-worker",
          has_drift: true,
          github_sha: "f4a1c9e",
          actionsmanager_yaml: managedYaml,
          github_yaml: githubYaml,
        },
      ],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));
    await seedDocsUserProfile(page);

    await page.goto(`/project/${DOCS_USER}/${encodeURIComponent("Payments Platform")}`);
    await page.getByTestId("drift-banner").waitFor({ timeout: 15000 });
    await page.getByTestId("review-drift-button").click();
    await page.getByTestId("drift-modal").waitFor();
    await page.waitForTimeout(300);

    await page.screenshot({ path: "../docs/assets/screenshots/drift-detection/drift-bulk-select.png" });

    // Expand one row's diff to show what an actual drift looks like -
    // managed version on the left, current GitHub version (with the extra
    // lint step) on the right.
    await page.getByRole("button", { name: /View Diff/i }).first().click();
    await page.getByText("npm run lint", { exact: false }).waitFor({ timeout: 5000 });
    await page.waitForTimeout(300);

    await page.screenshot({ path: "../docs/assets/screenshots/drift-detection/drift-diff-view.png" });

    await page.getByRole("button", { name: /Hide Diff/i }).first().click();
    await page.waitForTimeout(300);

    await page.getByTestId("select-all-drifts").click();
    await page.waitForTimeout(300);

    await page.screenshot({ path: "../docs/assets/screenshots/drift-detection/drift-bulk-toolbar.png" });
  });

  test("drift detection — status row with no drift", async ({ page }) => {
    const project = makeProject({
      ...DOCS_DRIFT_PROJECT,
      workflows: [makeWorkflow({ name: "build-and-test.yml", lastModifiedBy: DOCS_USER })],
    });
    await mockDriftResponse(page, { lastChecked: DOCS_LAST_CHECKED, driftedWorkflows: [] });
    await installApiMocks(page, createMockState({ projects: [project] }));
    await seedDocsUserProfile(page);

    await page.goto(`/project/${DOCS_USER}/${encodeURIComponent("Payments Platform")}`);
    const statusRow = page.getByTestId("drift-status-row");
    await statusRow.waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    // The row itself, not the whole page: it is one thin strip near the top,
    // and a full-page capture would bury the thing the doc is pointing at.
    await statusRow.screenshot({
      path: "../docs/assets/screenshots/drift-detection/drift-status-row.png",
    });
  });

  test("drift detection — per-project schedule", async ({ page }) => {
    const project = makeProject({
      ...DOCS_DRIFT_PROJECT,
      workflows: [makeWorkflow({ name: "build-and-test.yml", lastModifiedBy: DOCS_USER })],
    });
    await mockDriftResponse(page, { lastChecked: DOCS_LAST_CHECKED, driftedWorkflows: [] });
    await installApiMocks(page, createMockState({ projects: [project] }));
    await seedDocsUserProfile(page);
    await page.route("**/api/drift/settings", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          sweep_enabled: true,
          recheck_interval_minutes: 30,
          batch_size: 5,
          poll_interval_seconds: 60,
        }),
      })
    );

    await page.goto(`/project/${DOCS_USER}/${encodeURIComponent("Payments Platform")}`);
    // The Project Configs group is collapsed until opened.
    await page.getByRole("button", { name: "Project Configs" }).click();
    await page.getByRole("button", { name: /Drift Detection/i }).click();
    await page.getByTestId("project-drift-interval").waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "../docs/assets/screenshots/drift-detection/project-drift-schedule.png",
    });
  });

  test("drift detection — automatic checks paused", async ({ page }) => {
    const project = makeProject({
      ...DOCS_DRIFT_PROJECT,
      workflows: [makeWorkflow({ name: "build-and-test.yml", lastModifiedBy: DOCS_USER })],
    });
    await mockDriftResponse(page, {
      lastChecked: DOCS_LAST_CHECKED,
      driftedWorkflows: [],
      staleReason: NO_CREDENTIAL_REASON,
    });
    await installApiMocks(page, createMockState({ projects: [project] }));
    await seedDocsUserProfile(page);

    await page.goto(`/project/${DOCS_USER}/${encodeURIComponent("Payments Platform")}`);
    const statusRow = page.getByTestId("drift-status-row");
    await statusRow.waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await statusRow.screenshot({
      path: "../docs/assets/screenshots/drift-detection/drift-checks-paused.png",
    });
  });

  test("drift detection — workflow deleted in GitHub", async ({ page }) => {
    const project = makeProject({
      ...DOCS_DRIFT_PROJECT,
      workflows: [makeWorkflow({ name: "deploy-production.yml", lastModifiedBy: DOCS_USER })],
    });
    await mockDriftResponse(page, {
      lastChecked: DOCS_LAST_CHECKED,
      driftedWorkflows: [
        {
          workflow_name: "deploy-production.yml",
          workflow_filename: "deploy-production.yml",
          repo: "acme-corp/payments-worker",
          has_drift: true,
          deleted_in_github: true,
          // Empty rather than absent: the panel replaces the diff either way,
          // but a null here makes the row fetch GitHub's side on expand.
          github_yaml: "",
          message: "Workflow was deleted from acme-corp/payments-worker",
        },
      ],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));
    await seedDocsUserProfile(page);

    await page.goto(`/project/${DOCS_USER}/${encodeURIComponent("Payments Platform")}`);
    await page.getByTestId("drift-banner").waitFor({ timeout: 15000 });
    await page.getByTestId("review-drift-button").click();
    await page.getByTestId("drift-modal").waitFor();
    await page.getByRole("button", { name: /View Diff/i }).first().click();
    await page.getByTestId("deleted-in-github-panel").waitFor({ timeout: 5000 });
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "../docs/assets/screenshots/drift-detection/drift-deleted-in-github.png",
    });
  });

  test("notifications settings page", async ({ page }) => {
    const project = makeProject({
      project_name: "Payments Platform",
      project_code: "PAY",
      github_user: DOCS_USER,
      last_modified_by: DOCS_USER,
      updated_at: "2026-07-24T00:00:00Z",
      pr_state: "synced",
      selected_repos: ["acme-corp/payments-service"],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));
    await seedDocsUserProfile(page);

    // Override the default empty-state mocks with example data so the
    // screenshot shows what a configured installation looks like.
    await page.route("**/api/notifications/subscriptions", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            subscription_id: 1,
            recipient_email: "platform-team@acme-corp.example",
            project_id: null,
            project_name: null,
            event_types: ["drift.detected", "drift.resolved"],
            notify_on_resolved: true,
          },
        ]),
      }),
    );
    await page.route("**/api/notifications/deliveries", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            delivery_id: 1,
            event_type: "drift.detected",
            project_id: 1,
            project_name: "Payments Platform",
            recipient_email: "platform-team@acme-corp.example",
            status: "sent",
            attempt_count: 1,
            last_error: null,
            created_at: "2026-07-24T09:00:00Z",
            sent_at: "2026-07-24T09:00:02Z",
          },
        ]),
      }),
    );

    await page.goto(`/workspace/notifications`);
    await page.getByText("platform-team@acme-corp.example").first().waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({ path: "../docs/assets/screenshots/notifications/notifications-settings.png" });
  });

  test("build metrics — project overview", async ({ page }) => {
    const project = makeProject({
      ...DOCS_BUILD_METRICS_PROJECT,
      workflows: [
        makeWorkflow({ name: "build-and-test.yml", lastModifiedBy: DOCS_USER }),
        makeWorkflow({ name: "deploy-production.yml", lastModifiedBy: DOCS_USER }),
      ],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));
    await seedDocsUserProfile(page);
    await mockDriftResponse(page, { lastChecked: DOCS_LAST_CHECKED });
    await mockBuildMetricsResponse(page, DOCS_BUILD_METRICS);

    await page.goto(`/project/${DOCS_USER}/${encodeURIComponent("Payments Platform")}`);
    await page.getByRole("button", { name: "Build Metrics" }).click();
    await page.getByTestId("build-metrics-trend").waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({ path: "../docs/assets/screenshots/build-metrics/build-metrics-overview.png" });
  });

  test("build metrics — scoped to one workflow", async ({ page }) => {
    const project = makeProject({
      ...DOCS_BUILD_METRICS_PROJECT,
      workflows: [makeWorkflow({ name: "deploy-production.yml", lastModifiedBy: DOCS_USER })],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));
    await seedDocsUserProfile(page);
    await mockDriftResponse(page, { lastChecked: DOCS_LAST_CHECKED });
    await mockBuildMetricsResponse(page, DOCS_BUILD_METRICS);

    await page.goto(`/project/${DOCS_USER}/${encodeURIComponent("Payments Platform")}`);
    await page.getByRole("button", { name: "Build Metrics" }).click();
    await page.getByTestId("build-metrics-workflow-filter").waitFor({ timeout: 15000 });
    await page
      .getByTestId("build-metrics-workflow-filter")
      .selectOption("deploy-production.yml");
    await page.getByText("Last 30 days · deploy-production").waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({ path: "../docs/assets/screenshots/build-metrics/build-metrics-by-workflow.png" });
  });
});

/**
 * First-boot restore scenes.
 *
 * Deliberately outside the describe above: that block seeds an authenticated
 * session in beforeEach, and these shots are of the sign-in screen, before any
 * account exists.
 */
test.describe("docs screenshots — first-boot restore", () => {
  const REPORT_BODY = {
    upload_token: "docs",
    ok: true,
    errors: [],
    warnings: [],
    total_rows: 1284,
    tables: {
      accounts: 12,
      projects: 8,
      repos: 46,
      workflows: 122,
      workflow_versions: 940,
      project_workflows: 122,
      rulesets: 6,
      codeowners: 8,
      custom_files: 14,
      project_pull_requests: 6,
    },
    app_version: "1.0.0",
    created_at: "2026-08-11T18:30:00+00:00",
    dialect: "postgresql",
  };

  const backupFile = {
    name: "actionsmanager-backup-2026-08-11.tar.gz",
    mimeType: "application/gzip",
    buffer: Buffer.from("archive-bytes"),
  };

  async function uninitialisedInstall(page: import("@playwright/test").Page) {
    await installApiMocks(page, createMockState());
    await page.route("**/api/setup/status", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ uninitialized: true }),
      })
    );
  }

  async function mockReport(page: import("@playwright/test").Page, warnings: string[]) {
    await page.route("**/api/setup/restore/validate", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...REPORT_BODY, warnings }),
      })
    );
  }


  test("sign-in screen offering restore", async ({ page }) => {
    await uninitialisedInstall(page);

    await page.goto("/");
    await page.getByRole("button", { name: /restore from a backup/i }).waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "../docs/assets/screenshots/backup-restore/first-boot-restore-prompt.png",
    });
  });

  test("restore report before confirming", async ({ page }) => {
    await uninitialisedInstall(page);
    await mockReport(page, []);

    await page.goto("/");
    await page.getByRole("button", { name: /restore from a backup/i }).click();
    await page.getByLabel(/backup archive/i).setInputFiles(backupFile);
    await page.getByText(/1284 row\(s\)/).waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "../docs/assets/screenshots/backup-restore/first-boot-restore-report.png",
    });
  });

  test("restore report warning about a different SECRET_KEY", async ({ page }) => {
    await uninitialisedInstall(page);
    await mockReport(page, [
      "SECRET_KEY differs from the one this backup was written under. Saved personal access tokens will not decrypt and must be re-entered after restoring.",
    ]);

    await page.goto("/");
    await page.getByRole("button", { name: /restore from a backup/i }).click();
    await page.getByLabel(/backup archive/i).setInputFiles(backupFile);
    await page.getByText(/SECRET_KEY differs/).waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "../docs/assets/screenshots/backup-restore/first-boot-restore-warning.png",
    });
  });

  test("restore complete", async ({ page }) => {
    await uninitialisedInstall(page);
    await mockReport(page, []);
    await page.route("**/api/setup/restore/apply", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          restored_rows: 1284,
          restored_tables: 31,
          skipped_tables: [],
          warnings: [],
          migrations_ran: true,
        }),
      })
    );

    await page.goto("/");
    await page.getByRole("button", { name: /restore from a backup/i }).click();
    await page.getByLabel(/backup archive/i).setInputFiles(backupFile);
    await page.getByText(/1284 row\(s\)/).waitFor({ timeout: 15000 });
    await page.getByLabel(/type restore to confirm/i).fill("restore");
    await page.getByRole("button", { name: /restore this backup/i }).click();
    await page.getByText(/restore complete/i).waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "../docs/assets/screenshots/backup-restore/first-boot-restore-complete.png",
    });
  });
});
