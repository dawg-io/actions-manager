import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";
import RulesetManager from "./RulesetManager";
import apiClient from "../api/apiClient";
import { getRulesetSyncStatus } from "../api/rulesets";

vi.mock("../api/apiClient", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() },
}));

vi.mock("../api/rulesets", () => ({
  getRulesetSyncStatus: vi.fn(),
}));

vi.mock("../styles/RulesetManager.css", () => ({}));

const RULESET = {
  ruleset_id: 7,
  ruleset_name: "require-reviews",
  description: "Protected branch policy",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
  ruleset_json: { name: "require-reviews", target: "branch" },
};

const props = { user: "octocat", projectName: "Payments", selectedRepos: ["acme/api"] };

const mockedClient = vi.mocked(apiClient);
const mockedSyncStatus = vi.mocked(getRulesetSyncStatus);

/** The list load every render starts with. */
const listResponse = (rulesets: unknown[]) => ({ data: { success: true, rulesets } });

const syncStatus = (status: string) => ({
  success: true,
  is_synced: status === "exists",
  missing_repos: status === "exists" ? [] : ["acme/api"],
  repo_statuses: { "acme/api": { status, message: "" } },
});

/**
 * A selection of two repositories where only some lack the ruleset. With a
 * single selected repository the missing set equals the selection, so a test
 * built on it passes whether the code narrows to the missing list or sends
 * everything — which is exactly what the first version of these tests did.
 */
const mixedStatus = (statuses: Record<string, string>) => ({
  success: true,
  is_synced: Object.values(statuses).every(s => s === "exists"),
  missing_repos: Object.entries(statuses)
    .filter(([, s]) => s !== "exists")
    .map(([repo]) => repo),
  repo_statuses: Object.fromEntries(
    Object.entries(statuses).map(([repo, status]) => [repo, { status, message: "" }])
  ),
});

const TWO_REPOS = ["acme/api", "acme/web"];

/** Hoisted rather than inlined as a default parameter, which rebuilds it per call. */
const ONE_MISSING = { "acme/api": "not_found", "acme/web": "exists" };

const openDeleteDialog = async () => {
  render(<RulesetManager {...props} />);
  await screen.findByText("require-reviews");
  fireEvent.click(screen.getByTitle("Delete ruleset"));
  return screen.findByText(/Delete ruleset "require-reviews"\?/);
};

describe("RulesetManager ruleset sync", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedClient.get.mockResolvedValue(listResponse([RULESET]));
    mockedClient.post.mockResolvedValue({
      data: { success: true, applied_count: 1, error_count: 0 },
    });
  });

  /** Two repositories selected, the ruleset missing from acme/api only. */
  const renderWithMissing = async (statuses: Record<string, string> = ONE_MISSING) => {
    mockedSyncStatus.mockResolvedValue(mixedStatus(statuses) as any);
    render(<RulesetManager {...props} selectedRepos={TWO_REPOS} />);
    await screen.findByText("require-reviews");
    return screen.findByTitle("Sync ruleset to missing repositories");
  };

  test("applies only to the repositories missing it, not every selected one", async () => {
    // It used to POST /api/rulesets/{id}/sync — a route the backend does not
    // serve — with every selected repository. Two repos with one missing is
    // what makes the narrowing observable at all.
    const syncButton = await renderWithMissing();

    fireEvent.click(syncButton);

    await waitFor(() => expect(mockedClient.post).toHaveBeenCalled());
    expect(mockedClient.post).toHaveBeenCalledWith(
      expect.stringContaining("/api/rulesets/7/apply"),
      { repo_names: ["acme/api"], github_user: "octocat" }
    );
  });

  test("skips repositories whose status could not be checked", async () => {
    // The backend files permission_denied / repo_not_found / error under
    // missing_repos too — "treat as missing since we can't verify". Applying to
    // one of those can hit a repository that already holds the ruleset, which
    // GitHub rejects with a 422 reported back as a failure.
    const syncButton = await renderWithMissing({
      "acme/api": "not_found",
      "acme/web": "permission_denied",
    });

    fireEvent.click(syncButton);

    await waitFor(() => expect(mockedClient.post).toHaveBeenCalled());
    expect(mockedClient.post).toHaveBeenCalledWith(
      expect.stringContaining("/api/rulesets/7/apply"),
      { repo_names: ["acme/api"], github_user: "octocat" }
    );
    expect(await screen.findByText(/1 could not be checked and were skipped/)).toBeInTheDocument();
  });

  test("applies nothing when no repository is confirmed missing", async () => {
    const syncButton = await renderWithMissing({
      "acme/api": "permission_denied",
      "acme/web": "error",
    });

    fireEvent.click(syncButton);

    expect(await screen.findByText(/No repository is confirmed to be missing/)).toBeInTheDocument();
    expect(mockedClient.post).not.toHaveBeenCalled();
  });

  test("updates the panel after syncing, without a refresh", async () => {
    const syncButton = await renderWithMissing();
    expect(await screen.findByText(/Missing in 1 repositories/)).toBeInTheDocument();
    mockedSyncStatus.mockResolvedValue(
      mixedStatus({ "acme/api": "exists", "acme/web": "exists" }) as any
    );

    fireEvent.click(syncButton);

    expect(await screen.findByText(/Synced across all repositories/)).toBeInTheDocument();
  });

  test("reports a partial apply rather than claiming success", async () => {
    const syncButton = await renderWithMissing();
    mockedClient.post.mockResolvedValue({
      data: { success: false, applied_count: 0, error_count: 1 },
    });

    fireEvent.click(syncButton);

    expect(await screen.findByText(/Synced to 0 of 1 repositories, 1 failed/)).toBeInTheDocument();
  });

  test("keeps the Sync button when the post-sync re-read fails", async () => {
    // Storing a failed probe swapped the panel for an error state that has no
    // Sync button, with nothing to re-trigger the loader — one transient
    // failure removed the only retry short of reloading the page.
    const syncButton = await renderWithMissing();
    mockedSyncStatus.mockResolvedValue({
      success: false,
      error: "Failed to check sync status",
      is_synced: false,
      missing_repos: [],
      repo_statuses: {},
    } as any);

    fireEvent.click(syncButton);

    await waitFor(() => expect(mockedClient.post).toHaveBeenCalled());
    expect(await screen.findByTitle("Sync ruleset to missing repositories")).toBeInTheDocument();
  });

  test("refreshes the panel after Apply, which changes the same thing", async () => {
    mockedSyncStatus.mockResolvedValue(
      mixedStatus({ "acme/api": "not_found", "acme/web": "exists" }) as any
    );
    render(<RulesetManager {...props} selectedRepos={TWO_REPOS} />);
    await screen.findByText("require-reviews");
    expect(await screen.findByText(/Missing in 1 repositories/)).toBeInTheDocument();
    mockedSyncStatus.mockResolvedValue(
      mixedStatus({ "acme/api": "exists", "acme/web": "exists" }) as any
    );

    fireEvent.click(screen.getByTitle("Apply ruleset to selected repositories"));

    // The banner used to read "Applied to 2 repositories" above a panel still
    // reporting "Missing in 1", until the user reloaded.
    expect(await screen.findByText(/Synced across all repositories/)).toBeInTheDocument();
  });
});

describe("RulesetManager ruleset deletion", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedClient.get.mockResolvedValue(listResponse([RULESET]));
    mockedSyncStatus.mockResolvedValue(syncStatus("exists") as any);
    mockedClient.delete.mockResolvedValue({
      data: { success: true, message: "Ruleset 'require-reviews' deleted successfully" },
    });
  });

  test("asks whether the GitHub copy goes too, instead of silently keeping it", async () => {
    await openDeleteDialog();

    expect(screen.getByLabelText("Remove from ActionsManager only")).toBeChecked();
    expect(screen.getByLabelText("Delete from ActionsManager and GitHub")).toBeEnabled();
    // The old dialog promised the opposite: "Repositories that already have
    // rules applied will not be affected."
    expect(screen.getByText(/deletes the ruleset from your project's repositories/)).toBeInTheDocument();
  });

  test("keeps the GitHub copy when the project scope is confirmed", async () => {
    await openDeleteDialog();

    fireEvent.click(screen.getByRole("button", { name: /Remove from ActionsManager/i }));

    await waitFor(() => expect(mockedClient.delete).toHaveBeenCalled());
    expect(mockedClient.delete).toHaveBeenCalledWith(
      expect.stringContaining("/api/rulesets/7"),
      { params: { github_user: "octocat", scope: "project" } }
    );
  });

  test("deletes from GitHub too when that scope is chosen", async () => {
    mockedClient.delete.mockResolvedValue({
      data: {
        success: true,
        message: "Ruleset 'require-reviews' deleted successfully",
        removed_from_repos: ["acme/api"],
      },
    });
    await openDeleteDialog();

    fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));
    fireEvent.click(screen.getByRole("button", { name: /Delete Everywhere/i }));

    await waitFor(() => expect(mockedClient.delete).toHaveBeenCalled());
    expect(mockedClient.delete).toHaveBeenCalledWith(
      expect.stringContaining("/api/rulesets/7"),
      { params: { github_user: "octocat", scope: "project_and_github" } }
    );
    expect(await screen.findByText(/removed from 1 repository/)).toBeInTheDocument();
  });

  test("can lift the policy from GitHub while keeping the ruleset", async () => {
    mockedClient.delete.mockResolvedValue({
      data: {
        success: true,
        message: "Ruleset 'require-reviews' removed from GitHub",
        removed_from_repos: ["acme/api"],
      },
    });
    // After the removal the repository no longer has it.
    mockedSyncStatus
      .mockResolvedValueOnce(syncStatus("exists") as any)
      .mockResolvedValue(syncStatus("not_found") as any);
    await openDeleteDialog();

    fireEvent.click(screen.getByLabelText("Remove from GitHub only"));
    fireEvent.click(screen.getByRole("button", { name: /Remove from GitHub/i }));

    await waitFor(() => expect(mockedClient.delete).toHaveBeenCalled());
    expect(mockedClient.delete).toHaveBeenCalledWith(
      expect.stringContaining("/api/rulesets/7"),
      { params: { github_user: "octocat", scope: "github" } }
    );
    // The ruleset is still tracked, so the row stays.
    expect(screen.getByText("require-reviews")).toBeInTheDocument();
  });

  test("the sync panel stops claiming the ruleset is applied, without a refresh", async () => {
    mockedClient.delete.mockResolvedValue({
      data: { success: true, message: "Ruleset 'require-reviews' removed from GitHub" },
    });
    mockedSyncStatus
      .mockResolvedValueOnce(syncStatus("exists") as any)
      .mockResolvedValue(syncStatus("not_found") as any);
    await openDeleteDialog();
    expect(await screen.findByText(/Synced across all repositories/)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Remove from GitHub only"));
    fireEvent.click(screen.getByRole("button", { name: /Remove from GitHub/i }));

    // Keying the row's status off the pre-removal answer would leave this
    // reading "Synced" until the user reloaded.
    expect(await screen.findByText(/Missing in 1 repositories/)).toBeInTheDocument();
  });

  test("a check that could not answer does not disable the GitHub options", async () => {
    // permission_denied / error / repo_not_found all arrive with success: true.
    // Reading them as "nothing in GitHub" left the user unable to remove a
    // ruleset that is still enforced.
    mockedSyncStatus.mockResolvedValue(syncStatus("permission_denied") as any);
    render(<RulesetManager {...props} />);
    await screen.findByText("require-reviews");
    await waitFor(() => expect(mockedSyncStatus).toHaveBeenCalled());

    fireEvent.click(screen.getByTitle("Delete ruleset"));

    expect(await screen.findByLabelText("Delete from ActionsManager and GitHub")).toBeEnabled();
    expect(screen.getByLabelText("Remove from GitHub only")).toBeEnabled();
  });

  test("refreshes the sync panel after a partial failure, which already changed GitHub", async () => {
    mockedClient.delete.mockRejectedValue({
      response: {
        data: {
          detail: {
            message: "Could not remove ruleset 'require-reviews' from every repository",
            errors: ["acme/api: could not delete ruleset (HTTP 403)"],
          },
        },
      },
      message: "Request failed",
    });
    mockedSyncStatus
      .mockResolvedValueOnce(syncStatus("exists") as any)
      .mockResolvedValue(syncStatus("not_found") as any);
    await openDeleteDialog();

    fireEvent.click(screen.getByLabelText("Remove from GitHub only"));
    fireEvent.click(screen.getByRole("button", { name: /Remove from GitHub/i }));

    expect(await screen.findByText(/HTTP 403/)).toBeInTheDocument();
    // The repos that succeeded have changed, so the panel must not still read
    // "Synced across all repositories".
    expect(await screen.findByText(/Missing in 1 repositories/)).toBeInTheDocument();
  });

  test("offers no GitHub option for a ruleset no repository has", async () => {
    mockedSyncStatus.mockResolvedValue(syncStatus("not_found") as any);
    render(<RulesetManager {...props} />);
    await screen.findByText("require-reviews");
    await waitFor(() => expect(mockedSyncStatus).toHaveBeenCalled());

    fireEvent.click(screen.getByTitle("Delete ruleset"));

    expect(await screen.findByLabelText("Delete from ActionsManager and GitHub")).toBeDisabled();
  });

  test("drops the deleted ruleset from the list without a refresh", async () => {
    await openDeleteDialog();
    mockedClient.get.mockResolvedValue(listResponse([]));

    fireEvent.click(screen.getByRole("button", { name: /Remove from ActionsManager/i }));

    await waitFor(() => expect(screen.queryByText("require-reviews")).not.toBeInTheDocument());
  });

  test("reports the failing repositories when the GitHub delete fails", async () => {
    mockedClient.delete.mockRejectedValue({
      response: {
        data: {
          detail: {
            message: "Could not remove ruleset 'require-reviews' from every repository",
            errors: ["acme/api: could not delete ruleset (HTTP 403)"],
          },
        },
      },
      message: "Request failed",
    });
    await openDeleteDialog();

    fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));
    fireEvent.click(screen.getByRole("button", { name: /Delete Everywhere/i }));

    expect(await screen.findByText(/HTTP 403/)).toBeInTheDocument();
    // The row must survive: the ruleset is still enforced on acme/api.
    expect(screen.getByText("require-reviews")).toBeInTheDocument();
  });
});
