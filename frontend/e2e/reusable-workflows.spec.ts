import { test, expect } from "@playwright/test";
import {
  TEST_USER,
  PHASE2_REPOS,
  PHASE2_WORKFLOWS,
  corsHeaders,
  createMockState,
  installApiMocks,
  makeProject,
  makeWorkflow,
  mockReusableWorkflowLinks,
  seedAuthenticatedSession,
} from "./fixtures/mocks";

/**
 * Phase 2 — Reusable workflow (RWX) project behavior.
 *
 * Validates:
 *   1. RWX project loads and shows the reusable workflow in the list.
 *   2. No-prefix mode: workflow names do NOT include the project prefix.
 *   3. Standard project shows the linked reusable workflow card.
 *   4. The RWX source project name is visible on the linked workflow card.
 *   5. Standard projects that use prefixes still show their own prefix.
 *   6. Unrelated projects do not show a linked workflow card.
 */
test.describe("RWX project – basic workflow display", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("RWX project loads and shows the reusable workflow", async ({ page }) => {
    const rwxProject = makeProject({
      project_id: 2,
      project_name: "rwx-project",
      project_code: "RWX",
      project_type: "rwx",
      selected_repos: [PHASE2_REPOS.REUSABLE_WORKFLOWS],
      pr_state: "new",
      reusable_workflows_enabled: true,
      use_prefix: false,
      rxworkflows: [
        {
          name: PHASE2_WORKFLOWS.REUSABLE_BUILD,
          content: "name: Reusable Build\non:\n  workflow_call:\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo build\n",
          isReusable: true,
          workflowStatus: "committed_locally",
        },
      ],
    });

    await installApiMocks(page, createMockState({ projects: [rwxProject] }));
    await page.goto(`/project/${TEST_USER}/rwx-project`);

    // Reusable workflow should be visible in the list
    await expect(
      page.getByText(PHASE2_WORKFLOWS.REUSABLE_BUILD, { exact: false }).first(),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("RWX project with use_prefix=false does not show project prefix on workflow name", async ({
    page,
  }) => {
    const rwxProject = makeProject({
      project_id: 2,
      project_name: "rwx-no-prefix",
      project_code: "RNP",
      project_type: "rwx",
      selected_repos: [PHASE2_REPOS.REUSABLE_WORKFLOWS],
      pr_state: "draft",
      reusable_workflows_enabled: true,
      use_prefix: false,
      rxworkflows: [
        {
          name: PHASE2_WORKFLOWS.REUSABLE_BUILD,
          content: "name: Reusable Build\n",
          isReusable: true,
          workflowStatus: "committed_locally",
        },
      ],
    });

    await installApiMocks(page, createMockState({ projects: [rwxProject] }));
    await page.goto(`/project/${TEST_USER}/rwx-no-prefix`);

    // The workflow should be visible
    await expect(
      page.getByText(PHASE2_WORKFLOWS.REUSABLE_BUILD, { exact: false }).first(),
    ).toBeVisible({ timeout: 15_000 });

    // The prefix "AM_RNP_" must NOT appear in the visible workflow name text
    // (it is only injected by the UI when use_prefix=true)
    const workflowList = page.locator(".workflow-items");
    await expect(workflowList.first()).not.toContainText("AM_RNP_", { timeout: 5_000 });
  });

  test("standard project with use_prefix=true still shows the prefix", async ({ page }) => {
    const standardProject = makeProject({
      project_id: 1,
      project_name: "standard-prefix",
      project_code: "SPFX",
      project_type: "standard",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      pr_state: "draft",
      use_prefix: true,
      workflows: [
        makeWorkflow({ name: PHASE2_WORKFLOWS.CI, workflowStatus: "committed_locally" }),
      ],
    });

    await installApiMocks(page, createMockState({ projects: [standardProject] }));
    await page.goto(`/project/${TEST_USER}/standard-prefix`);

    // The prefix span "AM_SPFX_" should appear in the rendered workflow list
    await expect(
      page.locator(".workflow-prefix").first(),
    ).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("RWX linked workflow visibility in standard project", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("standard project shows linked reusable workflow card in Workflows panel", async ({
    page,
  }) => {
    const standardProject = makeProject({
      project_id: 1,
      project_name: "standard-linked",
      project_code: "SLK",
      project_type: "standard",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      pr_state: "synced",
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI, workflowStatus: "synced_with_github" })],
      linked_reusable_workflows: [
        {
          workflow_id: 10,
          workflow_name: PHASE2_WORKFLOWS.REUSABLE_BUILD,
          rwx_project_id: 2,
          rwx_project_name: "rwx-project",
          workflowStatus: "synced_with_github",
        },
      ],
    });

    await mockReusableWorkflowLinks(page, {
      linkedWorkflows: [
        {
          workflow_id: 10,
          workflow_name: PHASE2_WORKFLOWS.REUSABLE_BUILD,
          rwx_project_id: 2,
          rwx_project_name: "rwx-project",
        },
      ],
    });
    await installApiMocks(page, createMockState({ projects: [standardProject] }));

    await page.goto(`/project/${TEST_USER}/standard-linked`);

    // Linked workflow card should appear in the Workflows panel (default view)
    await expect(page.getByTestId("linked-rwx-workflow-card")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("linked-rwx-workflow-card")).toContainText(
      PHASE2_WORKFLOWS.REUSABLE_BUILD,
    );
    // Source RWX project name should be shown
    await expect(page.getByTestId("linked-rwx-workflow-card")).toContainText("rwx-project");

    // Linked Workflows is no longer in the Project Configs sidebar
    await page.getByRole("button", { name: "Project Configs" }).click();
    await expect(page.getByRole("button", { name: "Linked Workflows" })).toHaveCount(0);
  });

  test("standard project with no linked workflows does not show linked section in config", async ({
    page,
  }) => {
    const standardProject = makeProject({
      project_id: 1,
      project_name: "no-links",
      project_code: "NLK",
      project_type: "standard",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      pr_state: "new",
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI })],
      linked_reusable_workflows: [],
    });

    await mockReusableWorkflowLinks(page, { linkedWorkflows: [] });
    await installApiMocks(page, createMockState({ projects: [standardProject] }));

    await page.goto(`/project/${TEST_USER}/no-links`);

    // Linked Workflows is no longer in the Project Configs sidebar
    await page.getByRole("button", { name: "Project Configs" }).click();
    await expect(page.getByRole("button", { name: "Linked Workflows" })).toHaveCount(0);
  });

  test("standard project can open and use existing link modal from Add Workflow", async ({
    page,
  }) => {
    const alreadyLinkedWorkflow = {
      workflow_id: 10,
      workflow_name: PHASE2_WORKFLOWS.REUSABLE_BUILD,
      workflow_yaml: "name: Reusable Build\non:\n  workflow_call: {}\n",
      rwx_project_id: 2,
      rwx_project_name: "rwx-project",
      rwx_repo: PHASE2_REPOS.REUSABLE_WORKFLOWS,
      rwx_repo_visibility: "public",
    };
    const newLinkedWorkflow = {
      workflow_id: 11,
      workflow_name: "shared-deploy.yml",
      workflow_yaml: "name: Shared Deploy\non:\n  workflow_call: {}\n",
      rwx_project_id: 2,
      rwx_project_name: "rwx-project",
      rwx_repo: PHASE2_REPOS.REUSABLE_WORKFLOWS,
      rwx_repo_visibility: "public",
      link_validation: { allowed: true },
    };
    const blockedWorkflow = {
      workflow_id: 12,
      workflow_name: "private-deploy.yml",
      workflow_yaml: "name: Private Deploy\non:\n  workflow_call: {}\n",
      rwx_project_id: 3,
      rwx_project_name: "private-rwx-project",
      rwx_repo: "test-org/private-reusable-workflows",
      rwx_repo_visibility: "private",
      link_validation: {
        allowed: false,
        reason: "Public caller projects cannot link private reusable workflows.",
      },
    };
    const standardProject = makeProject({
      project_id: 1,
      project_name: "workflow-page-links",
      project_code: "WPL",
      project_type: "standard",
      repository_visibility_scope: "public",
      reusable_workflows_enabled: false,
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI })],
      linked_reusable_workflows: [alreadyLinkedWorkflow],
    });

    await installApiMocks(page, createMockState({ projects: [standardProject] }));
    await page.route(/\/api\/rwx-workflows(\?.*)?$/, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: corsHeaders(route),
        body: JSON.stringify([alreadyLinkedWorkflow, newLinkedWorkflow, blockedWorkflow]),
      }),
    );
    await page.route(/\/api\/projects\/workflow-page-links\/linked-reusable-workflows$/, (route) => {
      if (route.request().method() === "OPTIONS") {
        return route.fulfill({ status: 204, headers: corsHeaders(route), body: "" });
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: corsHeaders(route),
        body: JSON.stringify({ message: "linked", workflow_id: newLinkedWorkflow.workflow_id }),
      });
    });

    await page.goto(`/project/${TEST_USER}/workflow-page-links`);

    await page.getByRole("button", { name: "+ Add File" }).click();
    await expect(page.getByRole("button", { name: "Workflow", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Link Reusable Workflow" })).toBeVisible();
    await page.getByRole("button", { name: /Link Reusable Workflow/i }).click();

    await expect(page.getByRole("dialog", { name: /Link Reusable Workflow/i })).toBeVisible();
    await expect(page.getByText("✅ Already linked")).toBeVisible();
    await expect(page.getByText("Not available: Public caller projects cannot link private reusable workflows.")).toBeVisible();
    await expect(
      page.locator("label").filter({ hasText: "private-deploy.yml" }).getByRole("checkbox"),
    ).toBeDisabled();

    await page.locator("label").filter({ hasText: "shared-deploy.yml" }).getByRole("checkbox").check();

    const linkResponse = page.waitForResponse(
      (resp) =>
        resp.url().includes("/api/projects/workflow-page-links/linked-reusable-workflows") &&
        resp.request().method() === "POST" &&
        resp.status() === 200,
    );
    await page.getByRole("button", { name: "Add (1)" }).click();
    await linkResponse;
    await page.getByRole("dialog", { name: /Link Reusable Workflow/i }).getByRole("button", { name: "Close" }).first().click();

    const linkedCard = page
      .getByTestId("linked-rwx-workflow-card")
      .filter({ hasText: "shared-deploy.yml" });
    await expect(linkedCard).toHaveCount(1);
    await expect(linkedCard).toBeVisible({ timeout: 10_000 });
    await expect(linkedCard).toContainText("shared-deploy.yml");
  });
});

test.describe("RWX no-prefix regression", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("RWX project status badge reflects its own pr_state independently", async ({ page }) => {
    const rwxProject = makeProject({
      project_id: 2,
      project_name: "rwx-isolated",
      project_code: "RWI",
      project_type: "rwx",
      selected_repos: [PHASE2_REPOS.REUSABLE_WORKFLOWS],
      pr_state: "draft",
      reusable_workflows_enabled: true,
      use_prefix: false,
      rxworkflows: [
        makeWorkflow({
          name: PHASE2_WORKFLOWS.REUSABLE_BUILD,
          workflowStatus: "committed_locally",
        }),
      ],
    });

    const standardProject = makeProject({
      project_id: 1,
      project_name: "standard-isolated",
      project_code: "STI",
      project_type: "standard",
      selected_repos: [PHASE2_REPOS.SERVICE_A],
      pr_state: "synced",
      workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI, workflowStatus: "synced_with_github" })],
    });

    await installApiMocks(
      page,
      createMockState({ projects: [standardProject, rwxProject] }),
    );
    await page.goto(`/project/${TEST_USER}`);

    // Standard project shows Synced
    await expect(page.getByTestId("project-status-1")).toContainText(/Synced/i, {
      timeout: 15_000,
    });

    // RWX project shows Draft (independent state)
    await expect(page.getByTestId("project-status-2")).toContainText(/Draft/i, {
      timeout: 15_000,
    });
  });
});
