import { test, expect } from "@playwright/test";
import {
  TEST_USER,
  createMockState,
  installApiMocks,
  makeProject,
  seedAuthenticatedSession,
} from "./fixtures/mocks";

/**
 * Phase 1 — Project list / project creation flows.
 *
 * Notes
 * -----
 * The full "create project" form has a complex repository picker driven by
 * Radix UI dropdowns. Phase 1 focuses on the minimum set of guarantees the
 * issue lists:
 *
 *   * A new (empty) project list renders the empty-state copy.
 *   * Existing projects render with the correct status badge.
 *   * The "Create New Project" entry point navigates to the form route.
 *   * Required-field validation prevents an empty submission.
 *   * After saving, the new project is reflected in the list.
 */
test.describe("Project list", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("empty state is shown when the user has no projects", async ({ page }) => {
    await installApiMocks(page, createMockState({ projects: [] }));

    await page.goto(`/project/${TEST_USER}`);

    await expect(page.getByText(/No saved projects yet/i)).toBeVisible();
  });

  test("renders saved projects with their pr_state status text", async ({ page }) => {
    const projects = [
      makeProject({ project_id: 1, project_name: "alpha", pr_state: "draft" }),
      makeProject({ project_id: 2, project_name: "beta", pr_state: "open" }),
      makeProject({ project_id: 3, project_name: "gamma", pr_state: "synced" }),
    ];
    await installApiMocks(page, createMockState({ projects }));

    await page.goto(`/project/${TEST_USER}`);

    await expect(page.getByText("alpha", { exact: true })).toBeVisible();
    await expect(page.getByText("beta", { exact: true })).toBeVisible();
    await expect(page.getByText("gamma", { exact: true })).toBeVisible();

    // Status labels rendered by ProjectList.getStatusDisplay (per-row testid
    // keyed by stable project_id).
    await expect(page.getByTestId("project-status-1")).toContainText("Draft");
    await expect(page.getByTestId("project-status-2")).toContainText("Under Review");
    await expect(page.getByTestId("project-status-3")).toContainText("Synced");
  });

  test('"New Project" button navigates to the new-project route', async ({ page }) => {
    await installApiMocks(page, createMockState({ projects: [] }));

    await page.goto(`/project/${TEST_USER}`);

    await page.getByTestId("new-project-button").click();
    await page.waitForURL(new RegExp(`/project/${TEST_USER}/new`));
    await expect(page.getByLabel(/Project Name:/i)).toBeVisible();
  });

  test("renders project type labels and badges for existing projects", async ({ page }) => {
    const projects = [
      makeProject({ project_id: 1, project_name: "caller-app", project_type: "standard" }),
      makeProject({ project_id: 2, project_name: "shared-workflows", project_type: "rwx" }),
    ];
    await installApiMocks(page, createMockState({ projects }));

    await page.goto(`/project/${TEST_USER}`);

    const callerRow = page.getByTestId("project-row-caller-app");
    const reusableRow = page.getByTestId("project-row-shared-workflows");

    await expect(callerRow).toContainText("caller-app");
    await expect(callerRow).toContainText("Caller Workflow Project");
    await expect(reusableRow).toContainText("shared-workflows");
    await expect(reusableRow).toContainText("Reusable Workflow Project");
    await expect(page.getByText("Standard Project")).toHaveCount(0);

    await callerRow.click();

    await expect(page.getByLabel(/Project type: Caller Workflow Project/i)).toBeVisible();
    await expect(page.getByText("Standard Project")).toHaveCount(0);
  });
});

test.describe("Project creation", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("leaving the name empty keeps the wizard on Project Basics with inline validation", async ({ page }) => {
    await installApiMocks(page, createMockState({ projects: [] }));

    await page.goto(`/project/${TEST_USER}/new`);

    await expect(page.getByRole("heading", { name: "Project Basics" })).toBeVisible();
    await page.getByLabel(/Project Name:/i).focus();
    await page.getByLabel(/Project Name:/i).blur();
    await expect(page.getByText("Project name is required.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Continue" })).toBeDisabled();
  });

  test("filling in only the name keeps the wizard on Repositories until a repo is selected", async ({
    page,
  }) => {
    await installApiMocks(page, createMockState({ projects: [] }));

    await page.goto(`/project/${TEST_USER}/new`);
    await page.getByLabel(/Project Name:/i).fill("my-new-project");
    await page.getByRole("button", { name: "Continue" }).click();

    await expect(page.getByRole("heading", { name: /Repository Visibility and Selection/i })).toBeVisible();
    await expect(page.getByRole("button", { name: "Continue" })).toBeDisabled();
    await expect(page.getByTestId("visibility-scope-note")).toHaveText(/Showing public repositories only/i);
  });

  test("project type choices use caller/reusable workflow labels with helper text", async ({
    page,
  }) => {
    await installApiMocks(page, createMockState({ projects: [] }));

    await page.goto(`/project/${TEST_USER}/new`);

    await expect(page.getByText("Caller Workflow Project", { exact: true })).toBeVisible();
    await expect(
      page.getByText("Manage repositories that consume reusable workflows.", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Reusable Workflow Project", { exact: true })).toBeVisible();
    await expect(
      page.getByText("Author and manage reusable workflows used by caller workflow projects.", {
        exact: true,
      }),
    ).toBeVisible();

    const callerRadio = page.locator('input[name="projectType"][value="standard"]');
    const reusableRadio = page.locator('input[name="projectType"][value="rwx"]');

    await expect(callerRadio).toBeChecked();
    await page.getByText("Reusable Workflow Project", { exact: true }).click();
    await expect(reusableRadio).toBeChecked();
    await page.getByText("Caller Workflow Project", { exact: true }).click();
    await expect(callerRadio).toBeChecked();
    await expect(page.getByText("Standard Project")).toHaveCount(0);
  });
});
