import { test } from "@playwright/test";
import {
  createMockState,
  installApiMocks,
  makeProject,
  makeWorkflow,
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
});
