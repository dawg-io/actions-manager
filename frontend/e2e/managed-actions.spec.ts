import { test, expect } from "@playwright/test";
import {
  TEST_USER,
  createMockState,
  installApiMocks,
  makeProject,
  makeActionsProject,
  SAMPLE_WORKFLOW,
  SAMPLE_ACTIONS_PREVIEW,
  seedAuthenticatedSession,
} from "./fixtures/mocks";

/**
 * Managed Actions (Actions Projects) — covers the catalog CRUD flow and its
 * consumption from the GUI workflow editor:
 *
 *   * Navigating from the project dashboard into the Managed Actions catalog.
 *   * Adding a new Managed Action from a pasted URL, editing its reviewed
 *     defaults, and saving it.
 *   * The saved action's marketplace branding icon rendering in the catalog.
 *   * Editing an existing Managed Action's values from its detail page.
 *   * Selecting an imported Managed Action from the GUI workflow editor's
 *     step picker so it's used by a workflow step.
 */
test.describe("Managed Actions", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("clicking into Managed Actions from the dashboard shows the catalog", async ({ page }) => {
    await installApiMocks(page, createMockState({ projects: [makeProject()] }));

    await page.goto(`/project/${TEST_USER}`);
    await page.getByTestId("actions-projects-nav-button").click();

    await expect(page).toHaveURL(`/project/${TEST_USER}/actions-projects`);
    await expect(page.getByTestId("actions-projects-list")).toBeVisible();
    await expect(page.getByText(/No Managed Actions yet/i)).toBeVisible();
  });

  test("adding a Managed Action, editing its values, and saving shows its marketplace icon", async ({ page }) => {
    const state = createMockState({ projects: [makeProject()] });
    await installApiMocks(page, state);

    await page.goto(`/project/${TEST_USER}/actions-projects`);
    await page.getByTestId("add-actions-project-button").click();
    await expect(page).toHaveURL(`/project/${TEST_USER}/actions-projects/new`);

    // Step 1 — paste a URL and fetch its metadata.
    await page.locator("#actions-yaml-url").fill(SAMPLE_ACTIONS_PREVIEW.source_url);
    await page.getByTestId("fetch-preview-button").click();

    // Step 2 — edit the reviewed defaults before saving.
    const nameInput = page.locator("#actions-project-name");
    await expect(nameInput).toHaveValue(SAMPLE_ACTIONS_PREVIEW.name);
    await nameInput.fill("Checkout (custom)");
    await page.locator("#actions-project-description").fill("Custom description for e2e");

    await expect(page.getByTestId("actions-project-inputs-editor")).toBeVisible();
    await page.getByRole("button", { name: /Add input/i }).click();
    await page.locator("#input-name-1").fill("fetch-depth");

    await page.getByTestId("save-actions-project-button").click();

    // Save redirects back to the catalog and shows the new card.
    await expect(page).toHaveURL(`/project/${TEST_USER}/actions-projects`);
    await expect(page.getByText("Managed Action saved")).toBeVisible();

    const card = page.getByTestId(`actions-project-card-${state.actionsProjects.length}`);
    await expect(card).toBeVisible();
    await expect(card).toContainText("Checkout (custom)");

    // Marketplace branding icon renders on the saved card (SVG from
    // ActionBrandingIcon, driven by the preview's branding_icon/color). The
    // card also renders a trailing chevron icon, so scope to the first svg.
    await expect(card.locator("svg").first()).toBeVisible();
  });

  test("editing a Managed Action's values from its detail page updates the UI without a refresh", async ({ page }) => {
    const existing = makeActionsProject({ actions_project_id: 7, name: "Checkout" });
    await installApiMocks(page, createMockState({ actionsProjects: [existing] }));

    await page.goto(`/project/${TEST_USER}/actions-projects/7`);
    await expect(page.getByTestId("actions-project-detail")).toBeVisible();

    await page.locator("#actions-project-name").fill("Checkout (renamed)");
    await page.getByTestId("save-actions-project-detail-button").click();

    await expect(page.getByText("Managed Action updated")).toBeVisible();
    // The heading reflects the saved name immediately — no reload needed.
    await expect(page.getByRole("heading", { name: "Checkout (renamed)" })).toBeVisible();
  });

  test("a Managed Action can be selected onto a workflow step from the GUI workflow editor", async ({ page }) => {
    const project = makeProject({
      project_name: "gui-editor-demo",
      workflows: [SAMPLE_WORKFLOW],
    });
    const importedAction = makeActionsProject({
      actions_project_id: 3,
      name: "Checkout",
      owner: "actions",
      repo: "checkout",
      ref: "v4",
      inputs: [
        { name: "token", description: "GH token", required: false, default: null, type: "string", options: null },
      ],
    });
    await installApiMocks(page, createMockState({ projects: [project], actionsProjects: [importedAction] }));

    await page.goto(`/project/${TEST_USER}/gui-editor-demo`);
    await expect(page.getByText(SAMPLE_WORKFLOW.name, { exact: false }).first()).toBeVisible({
      timeout: 15_000,
    });

    // Select the workflow, then switch the editor into GUI mode.
    await page.getByRole("button", { name: new RegExp(SAMPLE_WORKFLOW.name) }).click();
    await page.getByRole("button", { name: "GUI", exact: true }).click();

    // Add a step, open it in the detail panel, and switch it to "Use Action".
    await page.getByRole("button", { name: /Add Step/i }).click();
    await page.locator('[id^="step-row-"]').last().click();
    await page.getByRole("radio", { name: "Use Action" }).last().click();

    // Browse the imported Managed Actions catalog and pick it for this step.
    await page.getByRole("button", { name: /Browse imported actions/i }).click();
    await page.getByRole("menuitem", { name: importedAction.name }).click();

    const usesInput = page.locator('input[id^="step-uses-"]').last();
    await expect(usesInput).toHaveValue(`${importedAction.owner}/${importedAction.repo}@${importedAction.ref}`);

    // `token` is optional and unset, so it starts behind the disclosure.
    const disclosure = page.getByRole("button", { name: /Show 1 option/ });
    await expect(disclosure).toBeVisible();
    await disclosure.click();

    // The action's declared inputs render as typed `with:` fields once revealed.
    await expect(page.getByText("token", { exact: false }).last()).toBeVisible();
  });
});
