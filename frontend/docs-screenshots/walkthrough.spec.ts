import { test } from "@playwright/test";
import {
  createMockState,
  installApiMocks,
  makeProject,
  seedAuthenticatedSession,
} from "../e2e/fixtures/mocks";
import { DOCS_USER, seedDocsRepos, seedDocsUserProfile } from "./docs-fixtures";

/**
 * Regenerates the "First Workflow Walkthrough" screenshots
 * (docs/assets/screenshots/walkthrough/*.png), covering the images that go
 * stale as the Projects dashboard / project workspace / workflow creation UI
 * changes. Run with `npm run docs:screenshots`.
 *
 * Not every walkthrough image is regenerated here — 01/02 (login screen) and
 * 04/06/09/14 aren't driven by this suite; add a test for them the same
 * way if they ever need a refresh. 13-save-draft-confirmation.png is no
 * longer referenced by the walkthrough doc and is left alone.
 *
 * The 03a/03b/05a images cover the first-login welcome screen and guided
 * tour. They seed onboarding state explicitly; every other test here leaves
 * it out so the tour never intrudes on a screenshot documenting something
 * else.
 */

test.describe("docs screenshots — walkthrough", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page, DOCS_USER);
  });

  test("empty projects dashboard", async ({ page }) => {
    await installApiMocks(page, createMockState({ projects: [] }));
    await seedDocsUserProfile(page);

    await page.goto(`/project/${DOCS_USER}`);
    await page.getByText("No saved projects yet.").waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "../docs/assets/screenshots/walkthrough/03-empty-project-dashboard.png",
    });
  });

  test("projects dashboard after creation", async ({ page }) => {
    const project = makeProject({
      project_name: "Payments Platform",
      project_code: "PAY",
      github_user: DOCS_USER,
      last_modified_by: DOCS_USER,
      updated_at: "2026-07-24T00:00:00Z",
      pr_state: "new",
      selected_repos: ["acme-corp/payments-service", "acme-corp/payments-worker"],
      workflows: [],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));
    await seedDocsUserProfile(page);

    await page.goto(`/project/${DOCS_USER}`);
    await page.getByText("Payments Platform", { exact: true }).waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "../docs/assets/screenshots/walkthrough/07-project-dashboard-created.png",
    });
  });

  test("project workspace empty state, then the add-workflow flow", async ({ page }) => {
    const project = makeProject({
      project_name: "Payments Platform",
      project_code: "PAY",
      github_user: DOCS_USER,
      last_modified_by: DOCS_USER,
      updated_at: "2026-07-24T00:00:00Z",
      pr_state: "new",
      selected_repos: ["acme-corp/payments-service", "acme-corp/payments-worker"],
      workflows: [],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));
    await seedDocsUserProfile(page);

    await page.goto(`/project/${DOCS_USER}/${encodeURIComponent("Payments Platform")}`);
    await page.getByRole("button", { name: "Add Workflow" }).waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "../docs/assets/screenshots/walkthrough/08-project-workspace-empty.png",
    });

    // Step 10 — Add Project File: choose type
    await page.getByRole("button", { name: "Add Workflow" }).click();
    await page.getByText("Add Project File", { exact: true }).waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "../docs/assets/screenshots/walkthrough/10-create-workflow-type.png",
    });

    // Step 11 — Workflow Options
    await page
      .getByRole("button")
      .filter({ has: page.getByRole("heading", { name: "Workflow", exact: true }) })
      .click();
    await page.getByText("Workflow Options", { exact: false }).waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "../docs/assets/screenshots/walkthrough/11-regular-workflow-options.png",
    });

    // Step 12 — Workflow editor, unsaved
    await page.getByLabel("Workflow Name").fill("build-and-test");
    await page.getByText("Open Blank Workflow", { exact: true }).click();
    await page.getByText("Unsaved", { exact: true }).waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "../docs/assets/screenshots/walkthrough/12-workflow-editor-unsaved.png",
    });
  });

  test("first-login welcome screen", async ({ page }) => {
    await installApiMocks(page, createMockState({ projects: [] }));
    await seedDocsUserProfile(page, { completed: false, completed_at: null, step: null });

    await page.goto(`/project/${DOCS_USER}`);
    await page.getByTestId("onboarding-welcome").waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "../docs/assets/screenshots/walkthrough/03a-welcome-screen.png",
    });
  });

  test("guided tour pointing at New Project", async ({ page }) => {
    await installApiMocks(page, createMockState({ projects: [] }));
    await seedDocsUserProfile(page, {
      completed: false,
      completed_at: null,
      step: "open-wizard",
    });

    await page.goto(`/project/${DOCS_USER}`);
    await page.getByTestId("tour-callout").waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "../docs/assets/screenshots/walkthrough/03b-tour-new-project.png",
    });
  });

  test("create a demo repository during the tour", async ({ page }) => {
    await installApiMocks(page, createMockState({ projects: [] }));
    await seedDocsUserProfile(page, {
      completed: false,
      completed_at: null,
      step: "pick-repos",
    });
    await seedDocsRepos(page);

    await page.goto(`/project/${DOCS_USER}/new`);
    await page.getByTestId("wizard-continue").click();
    await page.getByTestId("create-demo-repo-button").waitFor({ timeout: 15000 });
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "../docs/assets/screenshots/walkthrough/05a-create-demo-repository.png",
    });
  });
});
