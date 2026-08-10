import { test } from "@playwright/test";
import {
  createMockState,
  installApiMocks,
  makeProject,
  makeWorkflow,
  mockDriftResponse,
  seedAuthenticatedSession,
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

test.describe("docs screenshots", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page, DOCS_USER);
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
    });
    await installApiMocks(page, state);
    await seedDocsUserProfile(page);

    await page.goto(`/project/${DOCS_USER}/${encodeURIComponent("Payments Platform")}`);
    await page.getByRole("button", { name: "PR Campaigns" }).click();
    await page
      .getByText("Update build-and-test.yml", { exact: false })
      .first()
      .waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({ path: "../docs/assets/screenshots/pr-campaigns/pr-campaign.png" });
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

  test("drift detection — automatic checks paused", async ({ page }) => {
    const project = makeProject({
      ...DOCS_DRIFT_PROJECT,
      workflows: [makeWorkflow({ name: "build-and-test.yml", lastModifiedBy: DOCS_USER })],
    });
    await mockDriftResponse(page, {
      lastChecked: DOCS_LAST_CHECKED,
      driftedWorkflows: [],
      staleReason:
        "Automatic drift checks are paused: this project's owner has no saved " +
        "GitHub token. Save a personal access token, or use Check Now.",
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
});
