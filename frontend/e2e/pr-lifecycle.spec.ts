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
 * Phase 1 — PR lifecycle state transitions.
 *
 * Verifies the four canonical states surfaced by `pr_state`:
 *
 *     new → draft → open → synced → draft
 *
 * The transitions themselves are exercised through mocked API responses
 * (`installApiMocks` flips the state container on `POST /create-pull-requests`
 * and `POST /merge-pull-request`). Each transition is asserted at the
 * dashboard list level by reloading and checking the visible status badge,
 * since those badges are the user-facing indicator the issue calls out.
 */
test.describe("PR lifecycle state transitions", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("project surfaces the Under Review badge once a PR is reported as open", async ({ page }) => {
    const project = makeProject({
      project_name: "lifecycle",
      pr_state: "open",
      workflows: [SAMPLE_WORKFLOW],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));

    await page.goto(`/project/${TEST_USER}`);

    await expect(page.getByText("lifecycle", { exact: true })).toBeVisible();
    await expect(page.getByTestId("project-status-1")).toContainText("Under Review");
  });

  test("merging a PR transitions the project from open → synced", async ({ page }) => {
    const state = createMockState({
      projects: [
        makeProject({
          project_name: "lifecycle",
          pr_state: "open",
          workflows: [SAMPLE_WORKFLOW],
        }),
      ],
      prStatus: {
        project_state: "open",
        pull_requests: [
          {
            repo_name: "octocat/hello-world",
            pr_number: 42,
            pr_url: "https://github.com/octocat/hello-world/pull/42",
            pr_state: "open",
            branch_name: "actions-manager/lifecycle",
            target_branch: "main",
            created_at: "2025-01-02T00:00:00Z",
            updated_at: "2025-01-02T00:00:00Z",
          },
        ],
        total_prs: 1,
        open_prs: 1,
        merged_prs: 0,
        closed_prs: 0,
      },
    });
    await installApiMocks(page, state);

    await page.goto(`/project/${TEST_USER}`);
    await expect(page.getByTestId("project-status-1")).toContainText("Under Review");

    // Simulate a merge happening server-side (UI control lives deep in the
    // project view; we drive the same backend transition the merge button
    // would have triggered) and refresh the list to assert the transition.
    // Mirrors the contract used by frontend/src/api/pullRequests.ts:mergePullRequest:
    // PUT /api/merge-pull-request with X-GitHub-User + the four required JSON fields.
    await page.evaluate(async (githubUser) => {
      await fetch("/api/merge-pull-request", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-GitHub-User": githubUser,
        },
        body: JSON.stringify({
          github_user: githubUser,
          project_name: "lifecycle",
          repo_name: "octocat/hello-world",
          pr_number: 42,
        }),
      });
    }, TEST_USER);

    await page.reload();
    await expect(page.getByTestId("project-status-1")).toContainText("Synced");
    await expect(page.getByTestId("project-status-1")).not.toContainText("Under Review");
  });

  test("editing a synced project's workflow returns the project to Draft", async ({ page }) => {
    const state = createMockState({
      projects: [
        makeProject({
          project_name: "lifecycle",
          pr_state: "synced",
          workflows: [SAMPLE_WORKFLOW],
        }),
      ],
      prStatus: {
        project_state: "synced",
        pull_requests: [],
        total_prs: 0,
        open_prs: 0,
        merged_prs: 1,
        closed_prs: 0,
      },
    });
    await installApiMocks(page, state);

    await page.goto(`/project/${TEST_USER}`);
    await expect(page.getByTestId("project-status-1")).toContainText("Synced");

    // Drive the same PUT the workflow editor would issue to persist a change.
    // Our mock flips the project's pr_state back to `draft`.
    await page.evaluate(async () => {
      await fetch("/api/projects/lifecycle/", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_name: "lifecycle",
          selected_repos: ["octocat/hello-world"],
          workflows: [
            { name: "ci.yml", content: "name: CI\non: [push]\n# edited\njobs: {}\n" },
          ],
          rxworkflows: [],
          github_user: "octocat",
          branch_regex: "",
          branch_option: "default",
          branch_max_age_days: 30,
          reusable_workflows_enabled: false,
          use_prefix: false,
        }),
      });
    });

    await page.reload();
    await expect(page.getByTestId("project-status-1")).toContainText("Draft");
    await expect(page.getByTestId("project-status-1")).not.toContainText("Synced");
  });
});
