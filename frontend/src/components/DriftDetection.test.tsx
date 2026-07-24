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

import { getProjectDrift, resolveWorkflowDrift } from "../api/drift";

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

const mockSummary = (drifted: WorkflowDriftDetail[]): ProjectDriftSummary => ({
  project_id: 1,
  project_name: "proj",
  drift_count: drifted.length,
  drifted_workflows: drifted,
  last_checked: "2026-01-01T00:00:00Z",
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

  test("does not render the checking banner while the request is pending", () => {
    vi.mocked(getProjectDrift).mockReturnValue(new Promise(() => {}));
    const { container } = render(<DriftDetection {...defaultProps} />);
    expect(screen.queryByText(/Checking for workflow drift/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  test("shows the drift banner once a drifted response resolves", async () => {
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([mockDrift()]));
    const onDriftLoaded = vi.fn();
    render(<DriftDetection {...defaultProps} onDriftLoaded={onDriftLoaded} />);
    await waitFor(() => expect(screen.getByTestId("drift-banner")).toBeInTheDocument());
    expect(onDriftLoaded).toHaveBeenCalledWith([mockDrift()]);
  });

  test("stays hidden when the response reports no drift", async () => {
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([]));
    const onDriftLoaded = vi.fn();
    const { container } = render(<DriftDetection {...defaultProps} onDriftLoaded={onDriftLoaded} />);
    await waitFor(() => expect(onDriftLoaded).toHaveBeenCalledWith([]));
    expect(container).toBeEmptyDOMElement();
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
    });
    // Drift refetched after success (initial load + post-resolve refresh).
    await waitFor(() => expect(vi.mocked(getProjectDrift).mock.calls.length).toBeGreaterThanOrEqual(2));
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
