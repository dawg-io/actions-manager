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
});
