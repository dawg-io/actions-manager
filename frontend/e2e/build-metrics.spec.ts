import { test, expect } from "@playwright/test";
import {
  TEST_USER,
  PHASE2_REPOS,
  PHASE2_WORKFLOWS,
  createMockState,
  installApiMocks,
  makeProject,
  makeWorkflow,
  mockBuildMetricsResponse,
  seedAuthenticatedSession,
} from "./fixtures/mocks";

/**
 * Build metrics (issue #689) — the panel end to end.
 *
 * The unit tests cover rendering in isolation; these drive the real app, so
 * they cover what only integration can: that the sidebar entry reaches the
 * panel, that the query the panel sends matches what the backend contract
 * expects, and that switching scope actually re-requests rather than filtering
 * whatever was already on screen.
 *
 * Validates:
 *   1. The panel loads from the sidebar and renders the headline figures.
 *   2. Scoping by dropdown and by clicking a workflow row both re-request
 *      server-side with ?workflow=.
 *   3. Scoping narrows the numbers but never collapses the workflow list, so
 *      there is always a way back.
 *   4. A scope with no runs still leaves the switcher reachable.
 *   5. "Failures only" re-requests and leaves the aggregates alone.
 *   6. Runs link to GitHub in a new tab.
 *   7. Refresh asks for a live sync.
 *   8. A failed sync shows the stale-data warning alongside the numbers.
 *   9. An empty project says so instead of reporting 0%.
 */

const PROJECT_NAME = "metrics-demo";

const WORKFLOWS = [
  {
    workflow_name: "ci",
    workflow_filename: "ci.yml",
    total: 8,
    success_rate: 87.5,
    avg_duration_seconds: 120,
    actions_url: `https://github.com/${PHASE2_REPOS.SERVICE_A}/actions/workflows/ci.yml`,
  },
  {
    workflow_name: "release",
    workflow_filename: "release.yml",
    total: 2,
    success_rate: 50,
    avg_duration_seconds: 300,
    actions_url: null,
  },
];

const RECENT_RUNS = [
  {
    github_run_id: 991,
    run_number: 42,
    workflow_name: "ci",
    repo: PHASE2_REPOS.SERVICE_A,
    branch: "main",
    conclusion: "success",
    duration_seconds: 118,
    created_at: new Date().toISOString(),
  },
  {
    github_run_id: 990,
    run_number: 12,
    workflow_name: "release",
    repo: PHASE2_REPOS.SERVICE_A,
    branch: "main",
    conclusion: "failure",
    duration_seconds: 305,
    created_at: new Date().toISOString(),
  },
];

const PROJECT_SUMMARY = {
  total_runs: 10,
  decided_runs: 10,
  conclusion_counts: { success: 8, failure: 2 },
  success_rate: 80,
  avg_duration_seconds: 150,
  p95_duration_seconds: 420,
  avg_queue_seconds: 9,
  trend: [
    { date: "2026-08-10", total: 4, success: 4, failure: 0 },
    { date: "2026-08-11", total: 6, success: 4, failure: 2 },
  ],
};

function metricsProject() {
  return makeProject({
    project_id: 1,
    project_name: PROJECT_NAME,
    project_code: "MTRC",
    selected_repos: [PHASE2_REPOS.SERVICE_A],
    workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI })],
  });
}

/** Records the build-metrics requests the panel actually makes, so a test can
 *  prove a control re-queried the server rather than filtering locally. */
async function trackMetricsRequests(page: import("@playwright/test").Page): Promise<URL[]> {
  const seen: URL[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.includes("/build-metrics")) {
      seen.push(url);
    }
  });
  return seen;
}

async function openBuildMetrics(page: import("@playwright/test").Page) {
  await page.goto(`/project/${TEST_USER}/${PROJECT_NAME}`);
  await page.getByRole("button", { name: "Build Metrics" }).click();
}

test.describe("Build metrics – panel", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("opens from the sidebar and shows the project's figures", async ({ page }) => {
    await installApiMocks(page, createMockState({ projects: [metricsProject()] }));
    await mockBuildMetricsResponse(page, {
      summary: PROJECT_SUMMARY,
      workflows: WORKFLOWS,
      recentRuns: RECENT_RUNS,
    });

    await openBuildMetrics(page);

    await expect(page.getByTestId("build-metrics-panel")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("build-metrics-success-rate")).toHaveText("80%");
    await expect(page.getByText("10 decided of 10 runs")).toBeVisible();
    await expect(page.getByText(/Last 30 days · all workflows/)).toBeVisible();
    await expect(page.getByTestId("build-metrics-run")).toHaveCount(2);
  });

  test("a project with no runs says so rather than reporting 0%", async ({ page }) => {
    await installApiMocks(page, createMockState({ projects: [metricsProject()] }));
    await mockBuildMetricsResponse(page, { summary: { total_runs: 0, success_rate: null } });

    await openBuildMetrics(page);

    await expect(page.getByTestId("build-metrics-empty")).toContainText(/No runs recorded/i);
    await expect(page.getByText("0%")).toHaveCount(0);
  });

  test("a failed sync warns but keeps the last known numbers", async ({ page }) => {
    await installApiMocks(page, createMockState({ projects: [metricsProject()] }));
    await mockBuildMetricsResponse(page, {
      summary: {
        ...PROJECT_SUMMARY,
        sync_failed: true,
        sync_message: "GitHub API rate limit reached",
      },
      workflows: WORKFLOWS,
      recentRuns: RECENT_RUNS,
    });

    await openBuildMetrics(page);

    await expect(page.getByTestId("build-metrics-sync-warning")).toContainText(/rate limit/i);
    await expect(page.getByTestId("build-metrics-success-rate")).toHaveText("80%");
  });

  test("refresh asks the backend for a live sync", async ({ page }) => {
    await installApiMocks(page, createMockState({ projects: [metricsProject()] }));
    await mockBuildMetricsResponse(page, {
      summary: PROJECT_SUMMARY,
      workflows: WORKFLOWS,
      recentRuns: RECENT_RUNS,
    });
    const requests = await trackMetricsRequests(page);

    await openBuildMetrics(page);
    await expect(page.getByTestId("build-metrics-panel")).toBeVisible({ timeout: 15_000 });
    await page.getByTestId("build-metrics-refresh").click();

    await expect
      .poll(() => requests.some((url) => url.searchParams.get("refresh") === "true"))
      .toBe(true);
  });

  test("a run links to itself on GitHub in a new tab", async ({ page }) => {
    await installApiMocks(page, createMockState({ projects: [metricsProject()] }));
    await mockBuildMetricsResponse(page, {
      summary: PROJECT_SUMMARY,
      workflows: WORKFLOWS,
      recentRuns: RECENT_RUNS,
    });

    await openBuildMetrics(page);

    const run = page.getByTestId("build-metrics-run").first();
    await expect(run).toHaveAttribute(
      "href",
      `https://github.com/${PHASE2_REPOS.SERVICE_A}/actions/runs/991`,
    );
    await expect(run).toHaveAttribute("target", "_blank");
    await expect(run).toHaveAttribute("rel", "noopener noreferrer");
  });
});

test.describe("Build metrics – scoping to one workflow", () => {
  const SCOPED = {
    "release.yml": {
      total_runs: 2,
      decided_runs: 2,
      conclusion_counts: { success: 1, failure: 1 },
      success_rate: 50,
      recent_runs: [
        {
          github_run_id: 990,
          run_number: 12,
          workflow_name: "release",
          repo: PHASE2_REPOS.SERVICE_A,
          branch: "main",
          event: "push",
          status: "completed",
          conclusion: "failure",
          duration_seconds: 305,
          created_at: new Date().toISOString(),
          html_url: `https://github.com/${PHASE2_REPOS.SERVICE_A}/actions/runs/990`,
        },
      ],
    },
  };

  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
    await installApiMocks(page, createMockState({ projects: [metricsProject()] }));
  });

  test("the dropdown re-requests scoped to the chosen workflow", async ({ page }) => {
    await mockBuildMetricsResponse(page, {
      summary: PROJECT_SUMMARY,
      workflows: WORKFLOWS,
      recentRuns: RECENT_RUNS,
      scoped: SCOPED,
    });
    const requests = await trackMetricsRequests(page);

    await openBuildMetrics(page);
    await expect(page.getByTestId("build-metrics-success-rate")).toHaveText("80%", { timeout: 15_000 });

    await page.getByTestId("build-metrics-workflow-filter").selectOption("release.yml");

    await expect(page.getByTestId("build-metrics-success-rate")).toHaveText("50%");
    await expect(page.getByText(/Last 30 days · release/)).toBeVisible();
    // Server-side, not a local filter over rows already fetched.
    await expect
      .poll(() => requests.some((url) => url.searchParams.get("workflow") === "release.yml"))
      .toBe(true);
  });

  test("clicking a workflow row scopes to it, and clicking again clears", async ({ page }) => {
    await mockBuildMetricsResponse(page, {
      summary: PROJECT_SUMMARY,
      workflows: WORKFLOWS,
      recentRuns: RECENT_RUNS,
      scoped: SCOPED,
    });

    await openBuildMetrics(page);
    await expect(page.getByTestId("build-metrics-success-rate")).toHaveText("80%", { timeout: 15_000 });

    await page.getByTestId("build-metrics-workflow-row-release.yml").click();
    await expect(page.getByTestId("build-metrics-success-rate")).toHaveText("50%");
    await expect(page.getByTestId("build-metrics-workflow-row-release.yml"))
      .toHaveAttribute("aria-current", "true");

    await page.getByTestId("build-metrics-workflow-row-release.yml").click();
    await expect(page.getByTestId("build-metrics-success-rate")).toHaveText("80%");
  });

  test("the workflow list stays complete while scoped, so another can be chosen", async ({ page }) => {
    await mockBuildMetricsResponse(page, {
      summary: PROJECT_SUMMARY,
      workflows: WORKFLOWS,
      recentRuns: RECENT_RUNS,
      scoped: SCOPED,
    });

    await openBuildMetrics(page);
    await page.getByTestId("build-metrics-workflow-filter").selectOption("release.yml");
    await expect(page.getByTestId("build-metrics-success-rate")).toHaveText("50%", { timeout: 15_000 });

    await expect(page.getByTestId("build-metrics-workflow-row-ci.yml")).toBeVisible();
    await expect(page.getByTestId("build-metrics-workflow-row-release.yml")).toBeVisible();
  });

  test("scoping to a workflow with no runs still leaves a way back", async ({ page }) => {
    await mockBuildMetricsResponse(page, {
      summary: PROJECT_SUMMARY,
      workflows: WORKFLOWS,
      recentRuns: RECENT_RUNS,
      scoped: {
        "release.yml": {
          total_runs: 0,
          decided_runs: 0,
          success_rate: null,
          recent_runs: [],
        },
      },
    });

    await openBuildMetrics(page);
    await page.getByTestId("build-metrics-workflow-filter").selectOption("release.yml");

    await expect(page.getByTestId("build-metrics-empty")).toContainText(/No runs for release/i);
    // The regression this guards: an empty scope must not hide its own switcher.
    await expect(page.getByTestId("build-metrics-workflow-filter")).toBeVisible();
    await expect(page.getByTestId("build-metrics-workflow-row-ci.yml")).toBeVisible();
  });

  test("failures only re-requests and leaves the headline number alone", async ({ page }) => {
    await mockBuildMetricsResponse(page, {
      summary: PROJECT_SUMMARY,
      workflows: WORKFLOWS,
      recentRuns: RECENT_RUNS,
    });
    const requests = await trackMetricsRequests(page);

    await openBuildMetrics(page);
    await expect(page.getByTestId("build-metrics-success-rate")).toHaveText("80%", { timeout: 15_000 });

    await page.getByTestId("build-metrics-failures-toggle").click();

    await expect
      .poll(() => requests.some((url) => url.searchParams.get("only_failures") === "true"))
      .toBe(true);
    await expect(page.getByTestId("build-metrics-success-rate")).toHaveText("80%");
  });
});
