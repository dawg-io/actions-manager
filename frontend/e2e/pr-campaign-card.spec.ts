import { test, expect } from "@playwright/test";
import {
  TEST_USER,
  PHASE2_REPOS,
  PHASE2_WORKFLOWS,
  createMockState,
  installApiMocks,
  makeProject,
  makeWorkflow,
  seedAuthenticatedSession,
} from "./fixtures/mocks";

/**
 * PR campaign card — the creation-time snapshot and the rollback flow.
 *
 * Component tests already cover this card's rendering in isolation. What they
 * cannot cover is the part that only exists end to end: that the campaigns
 * endpoint's snapshot fields survive the trip into the rendered card, and that
 * the rollback choice a user makes in the dialog is the one actually sent to
 * the server.
 */

const BASE_SERVICE = "1f4c9ab7e3d05628c1a4f70b9d2e6538ac014b7d";
const BASE_WORKER = "7b02e5d4c1908af36e2d7c45b019f3a8de62c0f1";

const beforeRollback = "jobs:\n  build:\n    runs-on: ubuntu-24.04\n";
const afterRollback = "jobs:\n  build:\n    runs-on: ubuntu-latest\n";

/** A campaign where every target opened a PR and one of them has merged. */
function campaignState(overrides: { campaignExtras?: Record<string, unknown> } = {}) {
  const project = makeProject({
    project_id: 1,
    project_name: "rollout",
    project_code: "RO",
    selected_repos: [PHASE2_REPOS.SERVICE_A, PHASE2_REPOS.SERVICE_B],
    pr_state: "open",
    workflows: [makeWorkflow({ name: PHASE2_WORKFLOWS.CI, workflowStatus: "under_review" })],
  });
  return createMockState({
    projects: [project],
    prStatus: {
      project_state: "open",
      pull_requests: [
        {
          repo_name: PHASE2_REPOS.SERVICE_A,
          pr_number: 201,
          pr_url: `https://github.com/${PHASE2_REPOS.SERVICE_A}/pull/201`,
          pr_state: "open",
          branch_name: "actions-manager/rollout",
          target_branch: "main",
          workflow_names: PHASE2_WORKFLOWS.CI,
          created_at: "2025-01-02T00:00:00Z",
          updated_at: "2025-01-02T00:00:00Z",
        },
        {
          repo_name: PHASE2_REPOS.SERVICE_B,
          pr_number: 202,
          pr_url: `https://github.com/${PHASE2_REPOS.SERVICE_B}/pull/202`,
          pr_state: "merged",
          branch_name: "actions-manager/rollout",
          target_branch: "main",
          workflow_names: PHASE2_WORKFLOWS.CI,
          created_at: "2025-01-02T00:00:00Z",
          updated_at: "2025-01-02T00:00:00Z",
          merged_at: "2025-01-02T00:00:00Z",
        },
      ],
      total_prs: 2,
      open_prs: 1,
      merged_prs: 1,
      closed_prs: 0,
    },
    campaignExtras: {
      branch_option: "default",
      target_repos: [PHASE2_REPOS.SERVICE_A, PHASE2_REPOS.SERVICE_B],
      base_commits: {
        [`${PHASE2_REPOS.SERVICE_A} on main`]: BASE_SERVICE,
        [`${PHASE2_REPOS.SERVICE_B} on main`]: BASE_WORKER,
      },
      branch_protection: {
        [`${PHASE2_REPOS.SERVICE_A} on main`]: {
          status: "protected",
          required_reviews: 2,
          required_status_checks: ["ci/test"],
          enforce_admins: true,
        },
        [`${PHASE2_REPOS.SERVICE_B} on main`]: { status: "none" },
      },
      ...(overrides.campaignExtras ?? {}),
    },
  });
}

async function openCampaigns(page: import("@playwright/test").Page) {
  await page.goto(`/project/${TEST_USER}/rollout`);
  await page.getByRole("button", { name: /Manage PR Campaign/i }).click();
  await expect(page.getByTestId("repo-pr-row").first()).toBeVisible({ timeout: 15_000 });
}

test.describe("PR campaign card", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("shows the configured branch mode, not the branch it resolved to", async ({ page }) => {
    await installApiMocks(page, campaignState());
    await openCampaigns(page);

    // "main" is what every PR targets, but the project is on default-branch
    // mode — each repo follows its own default, so naming one is misleading.
    await expect(page.getByText("Default branch")).toBeVisible();
  });

  test("names the base branch alongside the base commit for each repository", async ({ page }) => {
    await installApiMocks(page, campaignState());
    await openCampaigns(page);

    const snapshots = page.getByTestId("repo-snapshot-line");
    await expect(snapshots.first()).toContainText(`base main ${BASE_SERVICE.slice(0, 7)}`);
    await expect(snapshots.nth(1)).toContainText(`base main ${BASE_WORKER.slice(0, 7)}`);
    // Branch protection as it stood when the campaign went out.
    await expect(snapshots.first()).toContainText("2 reviews");
    await expect(snapshots.nth(1)).toContainText("no branch protection");
  });

  test("counts repositories that opened a PR and those still to merge", async ({ page }) => {
    await installApiMocks(page, campaignState());
    await openCampaigns(page);

    await expect(page.getByText("Remaining to merge")).toBeVisible();
    await expect(page.getByText("Targets at creation")).toHaveCount(0);
  });

  test("reports the shortfall when a target opened no pull request", async ({ page }) => {
    // Three targets snapshotted, two PRs opened — the third must stay visible
    // rather than silently dropping out of the campaign.
    const state = campaignState({
      campaignExtras: {
        target_repos: [PHASE2_REPOS.SERVICE_A, PHASE2_REPOS.SERVICE_B, "acme-corp/no-pr-service"],
      },
    });
    await installApiMocks(page, state);
    await openCampaigns(page);

    await expect(page.getByText("2 of 3 targeted")).toBeVisible();
    await expect(page.getByTestId("repo-no-pr-row")).toHaveCount(1);
  });

  test("rollback control sits beside the toggle and does not collapse the card", async ({ page }) => {
    await installApiMocks(page, campaignState());
    await openCampaigns(page);

    const rollback = page.getByTestId("rollback-campaign-button");
    await expect(rollback).toBeVisible();

    // A <button> nested inside the trigger's <button> is invalid markup; the
    // control has to be a sibling of the toggle, not a child of it.
    const nestedInTrigger = await rollback.evaluate(
      (el) => el.closest('[data-state]')?.tagName === "BUTTON",
    );
    expect(nestedInTrigger).toBe(false);

    await rollback.click();
    // The dialog opened over a card that is still expanded behind it.
    await expect(page.getByTestId("rollback-summary")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("repo-pr-row").first()).toBeVisible();
  });
});

test.describe("PR campaign rollback", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  /** Only the merged repo is a rollback target, and it changed since. */
  const preview = {
    campaign_id: 1,
    campaign_name: `Update ${PHASE2_WORKFLOWS.CI}`,
    invertible_count: 1,
    targets: [
      {
        repo_name: PHASE2_REPOS.SERVICE_B,
        target_branch: "main",
        pr_number: 202,
        pr_url: `https://github.com/${PHASE2_REPOS.SERVICE_B}/pull/202`,
        workflow_names: PHASE2_WORKFLOWS.CI,
        invertible: true,
        reason: null,
        files: [
          {
            path: `.github/workflows/${PHASE2_WORKFLOWS.CI}`,
            action: "restore",
            before: beforeRollback,
            after: afterRollback,
          },
        ],
      },
      {
        repo_name: PHASE2_REPOS.SERVICE_A,
        target_branch: "main",
        pr_number: 201,
        pr_url: `https://github.com/${PHASE2_REPOS.SERVICE_A}/pull/201`,
        workflow_names: PHASE2_WORKFLOWS.CI,
        invertible: false,
        reason: "The workflow changed on main after this campaign merged.",
        files: [],
      },
    ],
  };

  test("separates what can be rolled back from what cannot, with the reason", async ({ page }) => {
    const state = campaignState();
    state.rollbackPreview = preview;
    await installApiMocks(page, state);
    await openCampaigns(page);

    await page.getByTestId("rollback-campaign-button").click();
    await expect(page.getByTestId("rollback-summary")).toContainText("1 of 2", { timeout: 15_000 });
    await expect(page.getByTestId("rollback-target")).toHaveCount(2);
    await expect(page.getByTestId("rollback-reason")).toContainText(
      "changed on main after this campaign merged",
    );
  });

  test("carries the chosen post-merge action through to the server", async ({ page }) => {
    const state = campaignState();
    state.rollbackPreview = preview;
    await installApiMocks(page, state);
    await openCampaigns(page);

    await page.getByTestId("rollback-campaign-button").click();
    await expect(page.getByTestId("rollback-summary")).toBeVisible({ timeout: 15_000 });

    // "keep" is not the default, so seeing it arrive proves the selection was
    // carried rather than the default being sent regardless.
    await page.locator("#rollback-am-keep").check();
    await page.getByTestId("rollback-confirm").click();

    await expect
      .poll(() => state.lastRollbackRequest?.am_action, { timeout: 15_000 })
      .toBe("keep");
    expect(state.lastRollbackRequest?.campaign_id).toBeTruthy();
  });
});
