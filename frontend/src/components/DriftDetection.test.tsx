import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";
import DriftDetection from "./DriftDetection";
import type { WorkflowDriftDetail, ProjectDriftSummary } from "../api/drift";

vi.mock("../api/drift", () => ({
  getProjectDrift: vi.fn(),
  resolveWorkflowDrift: vi.fn(),
  adoptGithubVersion: vi.fn(),
}));

import { getProjectDrift } from "../api/drift";

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

describe("DriftDetection", () => {
  beforeEach(() => {
    vi.mocked(getProjectDrift).mockReset();
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
});
