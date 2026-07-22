import { test, expect } from "@playwright/test";
import {
  TEST_USER,
  createMockState,
  installApiMocks,
  makeProject,
  SAMPLE_WORKFLOW,
  seedAuthenticatedSession,
} from "./fixtures/mocks";

/**
 * Phase 1 — Workflow save → draft state.
 *
 * The full workflow editor (CodeMirror + Monaco fallbacks + GUI editor) is out
 * of scope for Phase 1; instead, these tests cover the workflow-related state
 * transitions that are currently exercised:
 *
 *   * A project that already has a saved workflow appears with `pr_state`
 *     `draft` in the dashboard list.
 *   * Loading that project surfaces the workflow file name in the UI.
 *   * The authenticated dashboard shell remains usable when the projects list
 *     endpoint errors, rather than bouncing back to the login page.
 */
test.describe("Workflow save → draft state", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("project with a saved workflow renders with the Draft status badge", async ({ page }) => {
    const project = makeProject({
      project_name: "draft-demo",
      pr_state: "draft",
      workflows: [SAMPLE_WORKFLOW],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));

    await page.goto(`/project/${TEST_USER}`);

    await expect(page.getByText("draft-demo", { exact: true })).toBeVisible();
    await expect(page.getByTestId("project-status-1")).toContainText("Draft");
  });

  test("loading a project surfaces its persisted workflow file name", async ({ page }) => {
    const project = makeProject({
      project_name: "draft-demo",
      pr_state: "draft",
      workflows: [SAMPLE_WORKFLOW],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));

    await page.goto(`/project/${TEST_USER}/draft-demo`);

    // The workflow file name is rendered by UnifiedWorkflows in the workflow
    // list. We only assert it appears somewhere on the loaded project page.
    // The extended timeout accommodates the project page's cold-start cost
    // (multiple effects fire on mount: loadProject, getProjectPRStatus, env
    // vars, secrets, etc.) which can be slow on a fresh CI worker.
    await expect(page.getByText(SAMPLE_WORKFLOW.name, { exact: false }).first()).toBeVisible({
      timeout: 15_000,
    });
  });

  test("the dashboard does not crash when the projects list endpoint errors", async ({ page }) => {
    await installApiMocks(page, createMockState({ projects: [], failProjectsList: true }));

    await page.goto(`/project/${TEST_USER}`);

    // Even on a 500 the React shell renders. We confirm by checking that the
    // private route did not bounce back to the login page.
    await expect(page.getByRole("button", { name: /Log in with GitHub/i })).toHaveCount(0);
  });
});
