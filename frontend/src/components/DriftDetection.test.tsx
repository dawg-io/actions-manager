import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";
import { vi } from "vitest";
import DriftDetection from "./DriftDetection";
import type { WorkflowDriftDetail, ProjectDriftSummary } from "../api/drift";

vi.mock("../api/drift", () => ({
  getProjectDrift: vi.fn(),
  resolveWorkflowDrift: vi.fn(),
  adoptGithubVersion: vi.fn(),
}));

vi.mock("../api/workflows", () => ({
  deleteWorkflowFromGitHub: vi.fn().mockResolvedValue({ success: true }),
  deleteWorkflowFromDatabase: vi.fn().mockResolvedValue({ success: true }),
}));

import { getProjectDrift, resolveWorkflowDrift } from "../api/drift";
import { deleteWorkflowFromGitHub, deleteWorkflowFromDatabase } from "../api/workflows";

const mockDrift = (overrides: Partial<WorkflowDriftDetail> = {}): WorkflowDriftDetail => ({
  workflow_id: 1,
  workflow_name: "Build",
  workflow_filename: "build.yml",
  repo: "org/repo",
  branch: "main",
  has_drift: true,
  actionsmanager_yaml: "a",
  github_yaml: "b",
  actionsmanager_sha: "sha-a",
  github_sha: "sha-b",
  last_checked: "2026-01-01T00:00:00Z",
  message: "",
  ...overrides,
});

const mockSummary = (
  drifted: WorkflowDriftDetail[],
  uncheckedCount = 0,
): ProjectDriftSummary => ({
  project_id: 1,
  project_name: "proj",
  drift_count: drifted.length,
  drifted_workflows: drifted,
  last_checked: new Date().toISOString(),
  unchecked_count: uncheckedCount,
});

const defaultProps = {
  user: "testuser",
  projectId: 1,
  projectName: "proj",
  selectedRepos: ["org/repo"],
};

/** Render, open the drift modal, and expand the diff for the first drift. */
async function openDiff(user: ReturnType<typeof userEvent.setup>) {
  render(<DriftDetection {...defaultProps} />);
  await waitFor(() => expect(screen.getByTestId("drift-banner")).toBeInTheDocument());
  await user.click(screen.getByTestId("review-drift-button"));
  await user.click(screen.getByRole("button", { name: /View Diff/i }));
}

describe("DriftDetection", () => {
  beforeEach(() => {
    vi.mocked(getProjectDrift).mockReset();
    vi.mocked(resolveWorkflowDrift).mockReset();
  });

  test("shows a not-checked-yet status row while the request is pending and there is no seeded drift", () => {
    vi.mocked(getProjectDrift).mockReturnValue(new Promise(() => {}));
    render(<DriftDetection {...defaultProps} />);
    expect(screen.queryByText(/Checking for workflow drift/i)).not.toBeInTheDocument();
    expect(screen.getByTestId("drift-status-row")).toHaveTextContent("Not checked yet");
    expect(screen.getByTestId("drift-status-row")).toHaveTextContent("❔");
    expect(screen.queryByTestId("drift-banner")).not.toBeInTheDocument();
  });

  test("a verified-clean project shows a checkmark, distinct from a never-checked project", async () => {
    vi.mocked(getProjectDrift).mockResolvedValueOnce(mockSummary([]));
    render(<DriftDetection {...defaultProps} />);

    await waitFor(() => expect(screen.getByTestId("drift-status-row")).toHaveTextContent("No drift detected"));
    expect(screen.getByTestId("drift-status-row")).toHaveTextContent("✅");
    expect(screen.getByTestId("drift-status-row")).not.toHaveTextContent("❔");
  });

  test("switching to a project with no repos clears the previous project's drift status instead of showing stale data", async () => {
    vi.mocked(getProjectDrift).mockResolvedValueOnce(mockSummary([]));
    const { rerender } = render(<DriftDetection {...defaultProps} />);
    await waitFor(() => expect(screen.getByTestId("drift-status-row")).toHaveTextContent("No drift detected"));

    rerender(<DriftDetection {...defaultProps} projectId={2} projectName="proj2" selectedRepos={[]} />);

    await waitFor(() => expect(screen.getByTestId("drift-status-row")).toHaveTextContent("Not checked yet"));
    expect(screen.getByTestId("drift-status-row")).toHaveTextContent("❔");
  });

  test("clicking Check Now on a clean project triggers a live refresh", async () => {
    const user = userEvent.setup();
    vi.mocked(getProjectDrift).mockResolvedValueOnce(mockSummary([]));
    render(<DriftDetection {...defaultProps} />);
    await waitFor(() => expect(screen.getByTestId("drift-status-row")).toBeInTheDocument());

    vi.mocked(getProjectDrift).mockResolvedValueOnce(mockSummary([]));
    await user.click(screen.getByTestId("drift-inline-check-now-button"));

    await waitFor(() =>
      expect(vi.mocked(getProjectDrift)).toHaveBeenLastCalledWith(1, "testuser", { refresh: true }),
    );
  });

  test("surfaces the stale reason inline on a clean project without needing the modal", async () => {
    vi.mocked(getProjectDrift).mockResolvedValue({
      ...mockSummary([]),
      stale_reason: "Automatic drift checks are paused: no saved GitHub token.",
    });
    render(<DriftDetection {...defaultProps} />);

    await waitFor(() => expect(screen.getByTestId("drift-status-row")).toHaveTextContent(
      /Automatic drift checks are paused/i,
    ));
  });

  test("renders the seeded banner synchronously, before the live check resolves", () => {
    vi.mocked(getProjectDrift).mockReturnValue(new Promise(() => {}));
    render(<DriftDetection {...defaultProps} seededDriftNames={["Build", "Deploy"]} />);

    // Synchronous assertion (no waitFor): the banner must be in the very first
    // paint, otherwise it pops in later and shifts the layout.
    expect(screen.getByTestId("drift-banner")).toBeInTheDocument();
    expect(screen.getByText("2 workflows changed in GitHub")).toBeInTheDocument();
  });

  test("disables Review Drift until the live check supplies resolvable rows", async () => {
    vi.mocked(getProjectDrift).mockReturnValue(new Promise(() => {}));
    const { rerender } = render(
      <DriftDetection {...defaultProps} seededDriftNames={["Build"]} refreshSignal={0} />,
    );
    expect(screen.getByTestId("review-drift-button")).toBeDisabled();

    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([mockDrift()]));
    rerender(<DriftDetection {...defaultProps} seededDriftNames={["Build"]} refreshSignal={1} />);

    await waitFor(() => expect(screen.getByTestId("review-drift-button")).toBeEnabled());
    expect(screen.getByText("1 workflow changed in GitHub")).toBeInTheDocument();
  });

  test("live check clears the seeded banner when the drift is already resolved", async () => {
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([]));
    render(
      <DriftDetection {...defaultProps} seededDriftNames={["Build"]} />,
    );
    expect(screen.getByTestId("drift-banner")).toBeInTheDocument();

    await waitFor(() => expect(screen.queryByTestId("drift-banner")).not.toBeInTheDocument());
    expect(screen.getByTestId("drift-status-row")).toHaveTextContent("No drift detected");
  });

  test("a failed first check keeps the seeded banner instead of blanking it", async () => {
    vi.mocked(getProjectDrift).mockRejectedValue(new Error("network error"));
    render(<DriftDetection {...defaultProps} seededDriftNames={["Build"]} />);

    await waitFor(() => expect(vi.mocked(getProjectDrift)).toHaveBeenCalled());
    expect(screen.getByTestId("drift-banner")).toBeInTheDocument();
    // Enabled despite no live rows so the failure message stays reachable.
    await waitFor(() => expect(screen.getByTestId("review-drift-button")).toBeEnabled());
  });

  test("opening the panel costs no GitHub calls — one cached read, no refresh", async () => {
    // The background sweep keeps stored state fresh, so re-checking on mount
    // would spend rate limit re-answering a question already answered.
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([mockDrift()]));
    render(<DriftDetection {...defaultProps} />);

    await waitFor(() => expect(screen.getByTestId("drift-banner")).toBeInTheDocument());
    expect(vi.mocked(getProjectDrift)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(getProjectDrift)).toHaveBeenCalledWith(1, "testuser", { refresh: undefined });
  });

  test("a stale-state reason is surfaced instead of the timestamp silently freezing", async () => {
    const user = userEvent.setup();
    vi.mocked(getProjectDrift).mockResolvedValue({
      ...mockSummary([mockDrift()]),
      stale_reason: "Automatic drift checks are paused: no saved GitHub token.",
    });
    render(<DriftDetection {...defaultProps} />);
    await waitFor(() => expect(screen.getByTestId("drift-banner")).toBeInTheDocument());
    await user.click(screen.getByTestId("review-drift-button"));

    expect(screen.getByTestId("drift-stale-reason")).toHaveTextContent(
      /Automatic drift checks are paused/i,
    );
  });

  test("no warning is shown when automatic checking is working", async () => {
    const user = userEvent.setup();
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([mockDrift()]));
    render(<DriftDetection {...defaultProps} />);
    await waitFor(() => expect(screen.getByTestId("drift-banner")).toBeInTheDocument());
    await user.click(screen.getByTestId("review-drift-button"));

    expect(screen.queryByTestId("drift-stale-reason")).not.toBeInTheDocument();
  });

  test("Check Now triggers a live refresh and updates the last-checked time", async () => {
    const user = userEvent.setup();
    vi.mocked(getProjectDrift).mockResolvedValueOnce(mockSummary([mockDrift()]));
    render(<DriftDetection {...defaultProps} />);
    await waitFor(() => expect(screen.getByTestId("drift-banner")).toBeInTheDocument());
    await user.click(screen.getByTestId("review-drift-button"));

    vi.mocked(getProjectDrift).mockResolvedValueOnce({
      ...mockSummary([mockDrift()]),
      last_checked: "2026-02-02T00:00:00Z",
    });
    await user.click(screen.getByTestId("drift-check-now-button"));

    await waitFor(() =>
      expect(vi.mocked(getProjectDrift)).toHaveBeenLastCalledWith(1, "testuser", { refresh: true }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("drift-last-checked")).toHaveTextContent(
        new Date("2026-02-02T00:00:00Z").toLocaleString(),
      ),
    );
  });

  test("an unchecked repo is surfaced instead of reading as clean", async () => {
    // No drift found, but GitHub couldn't be reached for some repos — showing
    // nothing would imply everything is in sync.
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([], 2));
    render(<DriftDetection {...defaultProps} />);

    const row = await screen.findByTestId("drift-status-row");
    expect(row).toHaveTextContent(/Couldn't check 2 workflows/i);
  });

  test("a fully successful clean check renders the clean status row", async () => {
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([], 0));
    render(<DriftDetection {...defaultProps} />);

    await waitFor(() => expect(vi.mocked(getProjectDrift)).toHaveBeenCalled());
    expect(screen.getByTestId("drift-status-row")).toHaveTextContent("No drift detected");
    expect(screen.queryByTestId("drift-banner")).not.toBeInTheDocument();
  });

  describe("Workflow deleted in GitHub", () => {
    const deletedDrift = () =>
      mockDrift({
        deleted_in_github: true,
        github_yaml: null,
        github_sha: null,
        message: "Workflow was deleted from org/repo",
        affected_repos: ["org/repo2"],
      });

    async function openDeletedDiff() {
      const user = userEvent.setup();
      vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([deletedDrift()]));
      render(<DriftDetection {...defaultProps} />);
      await waitFor(() => expect(screen.getByTestId("drift-banner")).toBeInTheDocument());
      await user.click(screen.getByTestId("review-drift-button"));
      await user.click(screen.getByRole("button", { name: /View Diff/i }));
      return user;
    }

    test("is labelled deleted rather than shown as generic drift", async () => {
      await openDeletedDiff();

      expect(screen.getByTestId("drift-status-deleted")).toHaveTextContent("Deleted in GitHub");
    });

    test("explains the deletion instead of rendering a blank diff pane", async () => {
      await openDeletedDiff();

      // The reported bug: the GitHub column rendered as one empty line.
      expect(screen.getByTestId("deleted-in-github-panel")).toBeInTheDocument();
      expect(screen.queryByText("Current GitHub version")).not.toBeInTheDocument();
      expect(screen.getByText(/no longer exists in org\/repo/i)).toBeInTheDocument();
    });

    test("does not offer to adopt content that does not exist", async () => {
      await openDeletedDiff();

      expect(screen.queryByTestId("adopt-github-version-button")).not.toBeInTheDocument();
      expect(screen.getByTestId("deleted-restore-pr-button")).toBeInTheDocument();
      expect(screen.getByTestId("delete-everywhere-button")).toBeInTheDocument();
    });

    test("delete everywhere names every repo before doing anything", async () => {
      const user = await openDeletedDiff();

      await user.click(screen.getByTestId("delete-everywhere-button"));

      expect(await screen.findByText(/org\/repo, org\/repo2/)).toBeInTheDocument();
      expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument();
      // Nothing deleted until the user confirms.
      expect(vi.mocked(deleteWorkflowFromGitHub)).not.toHaveBeenCalled();
    });

    test("confirming removes the file from every repo and from ActionsManager", async () => {
      const user = await openDeletedDiff();

      await user.click(screen.getByTestId("delete-everywhere-button"));
      await user.click(await screen.findByRole("button", { name: /Delete everywhere/i }));

      await waitFor(() =>
        expect(vi.mocked(deleteWorkflowFromGitHub)).toHaveBeenCalledWith(
          "testuser", ["org/repo", "org/repo2"], "Build", "", "proj",
        ),
      );
      await waitFor(() =>
        expect(vi.mocked(deleteWorkflowFromDatabase)).toHaveBeenCalledWith(
          "testuser", "proj", "Build",
        ),
      );
    });
  });

  test("shows the drift banner once a drifted response resolves", async () => {
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([mockDrift()]));
    const onDriftLoaded = vi.fn();
    render(<DriftDetection {...defaultProps} onDriftLoaded={onDriftLoaded} />);
    await waitFor(() => expect(screen.getByTestId("drift-banner")).toBeInTheDocument());
    expect(onDriftLoaded).toHaveBeenCalledWith([mockDrift()]);
  });

  test("shows the clean status row instead of the drift banner when the response reports no drift", async () => {
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([]));
    const onDriftLoaded = vi.fn();
    render(<DriftDetection {...defaultProps} onDriftLoaded={onDriftLoaded} />);
    await waitFor(() => expect(onDriftLoaded).toHaveBeenCalledWith([]));
    expect(screen.queryByTestId("drift-banner")).not.toBeInTheDocument();
    expect(screen.getByTestId("drift-status-row")).toHaveTextContent("No drift detected");
  });

  test("a failed check does not clear a previously known drift state", async () => {
    vi.mocked(getProjectDrift).mockResolvedValueOnce(mockSummary([mockDrift()]));
    const onDriftLoaded = vi.fn();
    const { rerender } = render(
      <DriftDetection {...defaultProps} onDriftLoaded={onDriftLoaded} refreshSignal={0} />,
    );
    await waitFor(() => expect(screen.getByTestId("drift-banner")).toBeInTheDocument());

    vi.mocked(getProjectDrift).mockRejectedValueOnce(new Error("network error"));
    rerender(<DriftDetection {...defaultProps} onDriftLoaded={onDriftLoaded} refreshSignal={1} />);

    await waitFor(() => expect(vi.mocked(getProjectDrift)).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId("drift-banner")).toBeInTheDocument();
    expect(onDriftLoaded).not.toHaveBeenLastCalledWith([]);
  });

  test("ignores a stale response from a previously viewed project", async () => {
    let resolveFirst!: (v: ProjectDriftSummary) => void;
    const first = new Promise<ProjectDriftSummary>((resolve) => {
      resolveFirst = resolve;
    });
    vi.mocked(getProjectDrift).mockReturnValueOnce(first);

    const onDriftLoaded = vi.fn();
    const { rerender } = render(
      <DriftDetection {...defaultProps} projectId={1} onDriftLoaded={onDriftLoaded} />,
    );

    vi.mocked(getProjectDrift).mockResolvedValueOnce(mockSummary([]));
    rerender(<DriftDetection {...defaultProps} projectId={2} onDriftLoaded={onDriftLoaded} />);
    await waitFor(() => expect(onDriftLoaded).toHaveBeenCalledWith([]));

    // The stale first-project response resolves after project 2's clean result already landed.
    resolveFirst(mockSummary([mockDrift()]));
    await Promise.resolve();
    await Promise.resolve();

    expect(onDriftLoaded).toHaveBeenLastCalledWith([]);
    expect(screen.queryByTestId("drift-banner")).not.toBeInTheDocument();
  });

  test("shows the clarified action labels, descriptions, and repo/branch", async () => {
    const user = userEvent.setup();
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([mockDrift()]));
    await openDiff(user);

    expect(screen.getByRole("button", { name: /Create Fix Pull Request/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Restore Directly/i })).toBeInTheDocument();
    expect(screen.getByText(/No other repositories are changed/i)).toBeInTheDocument();
    expect(screen.getByText(/Immediately overwrites the workflow/i)).toBeInTheDocument();
    expect(screen.getByText(/Recommended/i)).toBeInTheDocument();
    expect(screen.getByText(/Immediate GitHub change/i)).toBeInTheDocument();
    // Repo + target branch surfaced prominently above the diff.
    expect(screen.getByText(/Target branch:/i)).toBeInTheDocument();
    // Clarified diff column headers.
    expect(screen.getByText("ActionsManager managed version")).toBeInTheDocument();
    expect(screen.getByText("Current GitHub version")).toBeInTheDocument();
  });

  test("Create Fix Pull Request posts the pr payload and refreshes drift", async () => {
    const user = userEvent.setup();
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([mockDrift()]));
    vi.mocked(resolveWorkflowDrift).mockResolvedValue({
      message: "PR opened",
      action: "restore_actionsmanager",
      workflow_id: 1,
      repo: "org/repo",
      branch: "main",
      state: "pr_pending",
    });
    await openDiff(user);

    await user.click(screen.getByRole("button", { name: /Create Fix Pull Request/i }));

    expect(vi.mocked(resolveWorkflowDrift)).toHaveBeenCalledWith(1, {
      github_user: "testuser",
      repo: "org/repo",
      branch: "main",
      resolution: "restore_actionsmanager",
      delivery_mode: "pr",
      // Sent so the backend can reject a stale resolve (issue: drift hardening).
      expected_github_sha: "sha-b",
    });
    // Drift refetched after success (initial load + post-resolve refresh).
    await waitFor(() => expect(vi.mocked(getProjectDrift).mock.calls.length).toBeGreaterThanOrEqual(2));
  });

  test("a stale resolve surfaces the conflict instead of silently overwriting", async () => {
    // The backend 409s when the file changed since drift was checked; the user
    // must see that rather than believing their resolve succeeded.
    const user = userEvent.setup();
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([mockDrift()]));
    vi.mocked(resolveWorkflowDrift).mockRejectedValue({
      response: {
        status: 409,
        data: { detail: "ci.yml in org/repo@main changed since drift was checked." },
      },
    });
    await openDiff(user);

    await user.click(screen.getByRole("button", { name: /Create Fix Pull Request/i }));

    expect(
      await screen.findByText(/changed since drift was checked/i),
    ).toBeInTheDocument();
  });

  test("disables the actions and prevents duplicate submits while a resolve is in flight", async () => {
    const user = userEvent.setup();
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([mockDrift()]));
    let finish!: () => void;
    vi.mocked(resolveWorkflowDrift).mockReturnValue(
      new Promise((resolve) => {
        finish = () => resolve({
          message: "PR opened", action: "restore_actionsmanager",
          workflow_id: 1, repo: "org/repo", branch: "main", state: "pr_pending",
        });
      }),
    );
    await openDiff(user);

    const prButton = screen.getByRole("button", { name: /Create Fix Pull Request/i });
    await user.click(prButton);

    // In-flight: shows action-specific loading text and disables all row actions.
    expect(screen.getByRole("button", { name: /Creating pull request/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Restore Directly/i })).toBeDisabled();

    // A second click is a no-op (button disabled) — still exactly one call.
    await user.click(screen.getByRole("button", { name: /Creating pull request/i }));
    expect(vi.mocked(resolveWorkflowDrift)).toHaveBeenCalledTimes(1);

    finish();
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /Creating pull request/i })).not.toBeInTheDocument());
  });

  test("Restore Directly requires confirmation before writing to GitHub", async () => {
    const user = userEvent.setup();
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([mockDrift()]));
    vi.mocked(resolveWorkflowDrift).mockResolvedValue({
      message: "restored", action: "restore_actionsmanager",
      workflow_id: 1, repo: "org/repo", branch: "main", state: "synced",
    });
    await openDiff(user);

    await user.click(screen.getByRole("button", { name: /Restore Directly/i }));
    // No API call yet — confirmation dialog naming repo + branch appears first.
    expect(vi.mocked(resolveWorkflowDrift)).not.toHaveBeenCalled();
    expect(screen.getByText(/Overwrite GitHub directly\?/i)).toBeInTheDocument();
    expect(screen.getByText(/branch main in org\/repo/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Overwrite directly/i }));
    expect(vi.mocked(resolveWorkflowDrift)).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ resolution: "restore_actionsmanager", delivery_mode: "direct" }),
    );
  });

  test("shows the backend error detail instead of the raw axios message", async () => {
    const user = userEvent.setup();
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([mockDrift()]));
    vi.mocked(resolveWorkflowDrift).mockRejectedValue({
      response: { data: { detail: "Branch protection blocked the push" } },
      message: "Request failed with status code 500",
    });
    await openDiff(user);

    await user.click(screen.getByRole("button", { name: /Create Fix Pull Request/i }));

    await waitFor(() =>
      expect(screen.getByText("Branch protection blocked the push")).toBeInTheDocument());
    expect(screen.queryByText(/Request failed with status code 500/i)).not.toBeInTheDocument();
  });
});
