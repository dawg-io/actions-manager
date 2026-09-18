import { test, expect } from "@playwright/test";
import {
  TEST_USER,
  RENAME_IMPACT,
  createMockState,
  installApiMocks,
  makeProject,
  makeWorkflow,
  seedAuthenticatedSession,
} from "./fixtures/mocks";

/**
 * Renaming a workflow, through the control that renames it.
 *
 * The unit tests for this flow mock `getRenameImpact` and hand the dialog a
 * payload built from the frontend's own `RenameImpact` interface. That proved
 * nothing about the interface being right: it said `override_repos` while the
 * server sends `overrides`, so `impact.override_repos.length` ran against
 * `undefined` and threw *during render*. React unmounts the whole tree on an
 * uncaught render error, so the user got a blank page instead of a dialog.
 *
 * These drive the real editor against a fixture written from the backend's
 * response model, so the dialog has to survive the shape the server actually
 * sends — and the assertions below fail loudly if the app blanks.
 */
const WORKFLOW = makeWorkflow({ name: "ci", workflowStatus: "committed_locally" });

// The sidebar's project-name control is the same component, so every locator
// here is scoped by its aria-label rather than by the shared test id.
const filename = (page: import("@playwright/test").Page) =>
  page.getByLabel("workflow filename", { exact: true });

const openEditor = async (page: import("@playwright/test").Page) => {
  await page.goto(`/project/${TEST_USER}/rename-demo`);
  await page.getByText("ci.yml", { exact: false }).first().click({ timeout: 15_000 });
  await expect(filename(page)).toBeVisible({ timeout: 15_000 });
};

const typeNewName = async (page: import("@playwright/test").Page, name: string) => {
  await page.getByRole("button", { name: "Edit workflow filename" }).click();
  await filename(page).fill(name);
  await page.getByRole("button", { name: "Save workflow filename" }).click();
};

test.describe("Renaming a workflow asks first", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("the name field's Save opens the impact dialog and the app stays up", async ({ page }) => {
    const state = createMockState({
      projects: [makeProject({ project_name: "rename-demo", pr_state: "draft", workflows: [WORKFLOW] })],
    });
    await installApiMocks(page, state);

    await openEditor(page);
    await typeNewName(page, "ci-v2");

    await expect(page.getByText("Rename this workflow?")).toBeVisible();
    // The whole point: a render throw here would leave an empty <body>, so
    // assert something outside the dialog is still mounted.
    await expect(filename(page)).toBeVisible();
    await expect(page.getByTestId("rename-targets")).toContainText("octocat/hello-world @ main");

    expect(state.lastSaveWorkflowsRequest).toBeUndefined();

    await page.getByRole("button", { name: "Rename" }).click();
    await expect(page.getByText("Rename this workflow?")).toBeHidden();
    await expect(filename(page)).toHaveText("ci-v2.yml");

    // Agreeing to the rename is the commit — no separate Commit Locally. And
    // the committed name is the one confirmed, not the one it replaced: the
    // state update applying it is not readable from the same render, so the
    // save is handed the new name explicitly.
    await expect
      .poll(() => state.lastSaveWorkflowsRequest?.workflows?.[0])
      .toMatchObject({ name: "ci-v2", original_name: "ci" });
  });

  test("the committed name survives the save resolving", async ({ page }) => {
    // markWorkflowAsSaved runs after the save returns and rebuilds the list. It
    // used to rebuild from the array captured before the rename, which reverted
    // the name in the UI a moment after it was confirmed.
    await installApiMocks(page, createMockState({
      projects: [makeProject({ project_name: "rename-demo", pr_state: "draft", workflows: [WORKFLOW] })],
    }));

    await openEditor(page);
    await typeNewName(page, "ci-v2");
    await page.getByRole("button", { name: "Rename" }).click();

    await expect(filename(page)).toHaveText("ci-v2.yml");
    // Held, not just reached: the revert landed on the save's completion.
    await page.waitForTimeout(1_000);
    await expect(filename(page)).toHaveText("ci-v2.yml");
  });

  test("cancelling leaves the old name in place", async ({ page }) => {
    await installApiMocks(page, createMockState({
      projects: [makeProject({ project_name: "rename-demo", pr_state: "draft", workflows: [WORKFLOW] })],
    }));

    await openEditor(page);
    await typeNewName(page, "ci-v2");

    await expect(page.getByText("Rename this workflow?")).toBeVisible();
    await page.getByTestId("rename-dismiss").click();

    await expect(filename(page)).toHaveText("ci.yml");
  });

  test("a blocked rename offers no way to take the new name", async ({ page }) => {
    await installApiMocks(page, createMockState({
      projects: [makeProject({ project_name: "rename-demo", pr_state: "draft", workflows: [WORKFLOW] })],
      renameImpact: {
        ...RENAME_IMPACT,
        classification: "blocked",
        blocked_reason: "This workflow is under review. Merge or close its pull request before renaming.",
      },
    }));

    await openEditor(page);
    await typeNewName(page, "ci-v2");

    await expect(page.getByText("This save cannot be applied")).toBeVisible();
    await expect(page.getByTestId("rename-blocked-reason")).toContainText("under review");
    await expect(page.getByRole("button", { name: "Rename" })).toHaveCount(0);

    await page.getByTestId("rename-dismiss").click();
    await expect(filename(page)).toHaveText("ci.yml");
  });
});
