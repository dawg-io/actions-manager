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

/**
 * The editor's chrome: the toolbar's control cluster and the expanded
 * (pop-out) surface.
 *
 * These live here rather than in a jsdom unit test because they assert things
 * jsdom cannot model: real stacking against the fixed sidebar, real layout
 * geometry, and Radix's real dismiss behaviour under an actual mouse.
 */
test.describe("GUI workflow editor — toolbar and expanded surface", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
    await installApiMocks(
      page,
      createMockState({ projects: [makeProject({ project_name: PROJECT, workflows: [SAMPLE_WORKFLOW] })] })
    );
    await page.setViewportSize({ width: 1600, height: 900 });
    await openGuiEditor(page);
  });

  test("the editor controls sit as one right-aligned cluster", async ({ page }) => {
    // Two competing margin-left:auto used to split the row's free space and
    // strand the mode toggle in the middle of the page.
    const cluster = page.locator(".workflow-editor-controls");
    const row = page.locator(".workflow-toolbar-status");

    const c = (await cluster.boundingBox())!;
    const r = (await row.boundingBox())!;
    const rightGap = r.x + r.width - (c.x + c.width);

    expect(rightGap).toBeLessThan(40);
    expect(c.x - r.x).toBeGreaterThan(rightGap);
  });

  test("the Expand icon sits beside its label, not above it", async ({ page }) => {
    // .mode-btn declared no display, so the button stayed inline-block while
    // Tailwind preflight sets svg{display:block} - which stacked them.
    const box = (await page.getByRole("button", { name: /Expand/ }).boundingBox())!;
    expect(box.height).toBeLessThan(40);
  });

  test("the expanded editor covers the fixed sidebar", async ({ page }) => {
    await page.getByRole("button", { name: /Expand/ }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    const box = (await dialog.boundingBox())!;
    expect(box.x).toBe(0);
    expect(box.width).toBe(1600);

    // .sidebar is position:fixed z-index:1000; the dialog has to win.
    const owner = await page.evaluate(() =>
      document.elementFromPoint(60, 300)?.closest(".sidebar") ? "sidebar" : "dialog"
    );
    expect(owner).toBe("dialog");
  });

  // Deliberately no "outside click" test here. The dialog is inset-0 w-screen
  // h-screen, so every coordinate is inside it and Radix's dismiss layer has
  // no reachable outside surface to fire from - any such test passes whether
  // or not the guards exist. The dismissal contract is covered in jsdom
  // (UnifiedWorkflowEditor.test.tsx, "does NOT close on an outside click"),
  // where the events can be dispatched directly and the test genuinely fails
  // without onPointerDownOutside/onInteractOutside.

  test("Escape deselects a step before it collapses the editor", async ({ page }) => {
    // Radix listens for Escape at the document in the CAPTURE phase, so it
    // always beats the step panel's own bubble listener - the dialog has to
    // stand down explicitly rather than rely on stopPropagation.
    await page.getByRole("button", { name: /Expand/ }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    await dialog.locator('[id^="step-row-"]').first().click();
    await expect(dialog.locator('[data-step-selected="true"]')).toBeVisible();

    await page.keyboard.press("Escape");

    // First press deselects; the editor stays expanded.
    await expect(dialog.locator('[data-step-selected="true"]')).toHaveCount(0);
    await expect(dialog).toBeVisible();

    // Second press, nothing selected, collapses it.
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("expanded YAML fills the dialog instead of staying 400px", async ({ page }) => {
    // YAMLEditor's height default is an inline style, so without an explicit
    // override the expanded view showed a short editor in a 100vh dialog.
    await page.getByRole("button", { name: "YAML", exact: true }).click();
    await page.getByRole("button", { name: /Expand/ }).click();
    await expect(page.getByRole("dialog")).toBeVisible();

    const box = (await page.getByTestId("yaml-editor").boundingBox())!;
    expect(box.height).toBeGreaterThan(600);
  });

  test("expanding does not duplicate step row ids", async ({ page }) => {
    const before = await page.locator('[id^="step-row-"]').count();
    expect(before).toBeGreaterThan(0);

    await page.getByRole("button", { name: /Expand/ }).click();
    await expect(page.getByRole("dialog")).toBeVisible();

    // One surface is mounted at a time, so the count must not double.
    expect(await page.locator('[id^="step-row-"]').count()).toBe(before);
  });
});
