import { test, expect, Page } from "@playwright/test";
import {
  TEST_USER,
  createMockState,
  installApiMocks,
  makeProject,
  makeActionsProject,
  SAMPLE_WORKFLOW,
  seedAuthenticatedSession,
} from "./fixtures/mocks";

/**
 * GUI workflow editor — the form-based alternative to the YAML pane.
 *
 *   * Trigger buttons behave as toggles rather than appending duplicates.
 *   * A Managed Action's required inputs show up front, the optional ones
 *     behind a disclosure, and a user-set optional input stays visible.
 *   * Steps are rows; the selected one is edited in the docked detail panel,
 *     which is the only place a step can be edited.
 */

const PROJECT = "gui-editor-e2e";

/** Opens the project's sample workflow and switches the editor into GUI mode. */
async function openGuiEditor(page: Page): Promise<void> {
  await page.goto(`/project/${TEST_USER}/${PROJECT}`);
  await expect(page.getByText(SAMPLE_WORKFLOW.name, { exact: false }).first()).toBeVisible({
    timeout: 15_000,
  });
  await page.getByRole("button", { name: new RegExp(SAMPLE_WORKFLOW.name) }).click();
  await page.getByRole("button", { name: "GUI", exact: true }).click();
}

const stepRows = (page: Page) => page.locator('[id^="step-row-"]');
const panel = (page: Page) => page.getByRole("complementary");
const stepNameField = (page: Page) => page.getByLabel("Step Name (optional)");

test.describe("GUI workflow editor — triggers", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
    await installApiMocks(
      page,
      createMockState({ projects: [makeProject({ project_name: PROJECT, workflows: [SAMPLE_WORKFLOW] })] })
    );
    await openGuiEditor(page);
  });

  test("clicking a trigger adds it and clicking it again removes it", async ({ page }) => {
    const schedule = page.getByRole("button", { name: "Schedule", exact: true });

    await expect(schedule).toHaveAttribute("aria-pressed", "false");

    await schedule.click();
    await expect(schedule).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("Runs on a cron schedule")).toHaveCount(1);

    await schedule.click();
    await expect(schedule).toHaveAttribute("aria-pressed", "false");
    await expect(page.getByText("Runs on a cron schedule")).toHaveCount(0);
  });

  test("clicking Pull Request twice removes it instead of adding a duplicate", async ({ page }) => {
    const pullRequest = page.getByRole("button", { name: "Pull Request", exact: true });

    await pullRequest.click();
    await expect(page.getByText("Triggered on pull request events")).toHaveCount(1);

    await pullRequest.click();
    await expect(page.getByText("Triggered on pull request events")).toHaveCount(0);
    await expect(pullRequest).toHaveAttribute("aria-pressed", "false");
  });

  test("every trigger button stays clickable once added", async ({ page }) => {
    for (const label of ["Push", "Pull Request", "Manual Trigger", "Schedule", "Release"]) {
      await expect(page.getByRole("button", { name: label, exact: true })).toBeEnabled();
    }
  });
});

test.describe("GUI workflow editor — action inputs", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
    const checkout = makeActionsProject({
      actions_project_id: 7,
      name: "Checkout",
      owner: "actions",
      repo: "checkout",
      ref: "v4",
      inputs: [
        { name: "repository", description: "Repo to check out", required: true, default: null, type: "string", options: null },
        { name: "ref", description: "Branch or tag", required: false, default: null, type: "string", options: null },
        { name: "fetch-depth", description: "Commits to fetch", required: false, default: "1", type: "string", options: null },
      ],
    });
    await installApiMocks(
      page,
      createMockState({
        projects: [makeProject({ project_name: PROJECT, workflows: [SAMPLE_WORKFLOW] })],
        actionsProjects: [checkout],
      })
    );
    await openGuiEditor(page);

    // Add a step (which opens it) and point it at the imported action.
    await page.getByRole("button", { name: /Add Step/i }).click();
    await page.getByRole("radio", { name: "Use Action" }).click();
    await page.getByRole("button", { name: /Browse imported actions/i }).click();
    await page.getByRole("menuitem", { name: "Checkout" }).click();
  });

  test("shows required inputs and hides optional ones behind a disclosure", async ({ page }) => {
    await expect(page.getByLabel(/^repository \*/)).toBeVisible();
    await expect(page.getByLabel(/^ref/)).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Show 2 more options" })).toBeVisible();
  });

  test("expanding the disclosure reveals the optional inputs", async ({ page }) => {
    await page.getByRole("button", { name: "Show 2 more options" }).click();

    await expect(page.getByLabel(/^ref/)).toBeVisible();
    await expect(page.getByLabel(/^fetch-depth/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Hide 2 options" })).toBeVisible();
  });

  test("a set optional input stays visible with a Set badge after collapsing", async ({ page }) => {
    await page.getByRole("button", { name: "Show 2 more options" }).click();
    await page.getByLabel(/^fetch-depth/).fill("0");
    await page.getByRole("button", { name: "Hide 1 option" }).click();

    await expect(page.getByLabel(/^fetch-depth/)).toHaveValue("0");
    await expect(page.getByTitle("Optional input — you set this value")).toBeVisible();
  });
});

test.describe("GUI workflow editor — step detail panel", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
    await installApiMocks(
      page,
      createMockState({ projects: [makeProject({ project_name: PROJECT, workflows: [SAMPLE_WORKFLOW] })] })
    );
    await openGuiEditor(page);
  });

  test("shows an empty state until a step is selected", async ({ page }) => {
    await expect(panel(page)).toContainText("Select a step to edit it.");
    await expect(stepNameField(page)).toHaveCount(0);
  });

  test("clicking a step row opens it in the panel and marks the row current", async ({ page }) => {
    await stepRows(page).first().click();

    await expect(stepNameField(page)).toBeVisible();
    await expect(stepRows(page).first()).toHaveAttribute("aria-current", "true");
  });

  test("the panel is the only place a step is edited", async ({ page }) => {
    await stepRows(page).first().click();

    // No inline expand exists any more, so exactly one step form is mounted.
    await expect(stepNameField(page)).toHaveCount(1);
  });

  test("renaming a step in the panel updates its row title live", async ({ page }) => {
    await stepRows(page).first().click();
    await stepNameField(page).fill("Say hello");

    await expect(stepRows(page).first()).toContainText("Say hello");
  });

  test("adding a step opens it in the panel with no further clicks", async ({ page }) => {
    await page.getByRole("button", { name: /Add Step/i }).click();

    await expect(stepNameField(page)).toHaveValue("Step 2");
    await expect(stepRows(page).last()).toHaveAttribute("aria-current", "true");
  });

  test("the close button returns the panel to its empty state", async ({ page }) => {
    await stepRows(page).first().click();
    await page.getByRole("button", { name: "Close step details" }).click();

    await expect(panel(page)).toContainText("Select a step to edit it.");
  });

  test("Escape closes the panel", async ({ page }) => {
    await stepRows(page).first().click();
    await stepNameField(page).press("Escape");

    await expect(panel(page)).toContainText("Select a step to edit it.");
  });

  test("deleting the selected step falls back to the empty state", async ({ page }) => {
    await stepRows(page).first().click();
    await expect(stepNameField(page)).toBeVisible();

    await page.getByTitle("Remove step").first().click();

    await expect(panel(page)).toContainText("Select a step to edit it.");
  });
});
