/**
 * Tests for bulk-fixing workflow drift: selecting multiple drifted
 * workflows and resolving them together, plus the "identical drift" group
 * selection affordance. The existing single-item flow is covered by
 * DriftDetection.test.tsx and is untouched by this feature - these tests
 * only exercise the additive bulk-select/bulk-resolve behavior.
 */
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
  bulkResolveWorkflowDrift: vi.fn(),
}));

import { getProjectDrift, bulkResolveWorkflowDrift } from "../api/drift";

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
  selectedRepos: ["org/repo", "org/repo2"],
};

async function openModal() {
  render(<DriftDetection {...defaultProps} />);
  await waitFor(() => expect(screen.getByTestId("drift-banner")).toBeInTheDocument());
  const user = userEvent.setup();
  await user.click(screen.getByTestId("review-drift-button"));
  return user;
}

describe("DriftDetection - bulk resolve", () => {
  beforeEach(() => {
    vi.mocked(getProjectDrift).mockReset();
    vi.mocked(bulkResolveWorkflowDrift).mockReset();
  });

  test("checkboxes render per row; bulk toolbar only appears once something is selected", async () => {
    vi.mocked(getProjectDrift).mockResolvedValue(
      mockSummary([mockDrift({ workflow_id: 1 }), mockDrift({ workflow_id: 2, repo: "org/repo2" })]),
    );
    const user = await openModal();

    expect(screen.queryByTestId("bulk-action-toolbar")).not.toBeInTheDocument();

    const boxes = screen.getAllByTestId(/^select-drift-/);
    expect(boxes).toHaveLength(2);

    await user.click(boxes[0]);
    expect(screen.getByTestId("bulk-action-toolbar")).toBeInTheDocument();
    expect(screen.getByText("1 of 2 selected")).toBeInTheDocument();
  });

  test("identical drifts (same github_sha) show a 'select all' group affordance", async () => {
    vi.mocked(getProjectDrift).mockResolvedValue(
      mockSummary([
        mockDrift({ workflow_id: 1, repo: "org/repo", github_sha: "same-sha" }),
        mockDrift({ workflow_id: 2, repo: "org/repo2", github_sha: "same-sha" }),
      ]),
    );
    const user = await openModal();

    const groupButtons = screen.getAllByTestId(/^select-group-/);
    expect(groupButtons).toHaveLength(2);
    expect(groupButtons[0]).toHaveTextContent("2 identical — select all");

    await user.click(groupButtons[0]);
    expect(screen.getByText("2 of 2 selected")).toBeInTheDocument();
  });

  test("drifts with different github_sha do not show the group affordance", async () => {
    vi.mocked(getProjectDrift).mockResolvedValue(
      mockSummary([
        mockDrift({ workflow_id: 1, repo: "org/repo", github_sha: "sha-a" }),
        mockDrift({ workflow_id: 2, repo: "org/repo2", github_sha: "sha-b" }),
      ]),
    );
    await openModal();

    expect(screen.queryByTestId(/^select-group-/)).not.toBeInTheDocument();
  });

  test("bulk Create Fix PR calls the bulk API with selected items and refreshes drift once", async () => {
    vi.mocked(getProjectDrift).mockResolvedValue(
      mockSummary([
        mockDrift({ workflow_id: 1, repo: "org/repo", branch: "main" }),
        mockDrift({ workflow_id: 2, repo: "org/repo2", branch: "main" }),
      ]),
    );
    vi.mocked(bulkResolveWorkflowDrift).mockResolvedValue({
      success: true,
      results: [
        { workflow_id: 1, repo: "org/repo", branch: "main", success: true, message: "PR opened" },
        { workflow_id: 2, repo: "org/repo2", branch: "main", success: true, message: "PR opened" },
      ],
    });
    const user = await openModal();

    await user.click(screen.getByTestId("select-all-drifts"));
    await user.click(screen.getByRole("button", { name: /Create Fix PR \(2\)/i }));

    expect(vi.mocked(bulkResolveWorkflowDrift)).toHaveBeenCalledWith(1, {
      github_user: "testuser",
      items: expect.arrayContaining([
        { workflow_id: 1, repo: "org/repo", branch: "main" },
        { workflow_id: 2, repo: "org/repo2", branch: "main" },
      ]),
      resolution: "restore_actionsmanager",
      delivery_mode: "pr",
    });

    // Drift refetched exactly once after the whole batch completes (initial
    // load + one post-bulk-resolve refresh), not once per item.
    await waitFor(() => expect(vi.mocked(getProjectDrift)).toHaveBeenCalledTimes(2));
  });

  test("bulk Restore Directly is gated behind a confirmation naming the selection count", async () => {
    vi.mocked(getProjectDrift).mockResolvedValue(mockSummary([mockDrift({ workflow_id: 1 })]));
    const user = await openModal();

    await user.click(screen.getByTestId("select-all-drifts"));
    await user.click(screen.getByRole("button", { name: /Restore Directly \(1\)/i }));

    expect(vi.mocked(bulkResolveWorkflowDrift)).not.toHaveBeenCalled();
    expect(screen.getByText(/Overwrite GitHub directly\?/i)).toBeInTheDocument();
    expect(screen.getByText(/immediately overwrites 1 workflow/i)).toBeInTheDocument();

    vi.mocked(bulkResolveWorkflowDrift).mockResolvedValue({
      success: true,
      results: [{ workflow_id: 1, repo: "org/repo", branch: "main", success: true, message: "restored" }],
    });
    await user.click(screen.getByRole("button", { name: /Overwrite directly/i }));

    expect(vi.mocked(bulkResolveWorkflowDrift)).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ resolution: "restore_actionsmanager", delivery_mode: "direct" }),
    );
  });

  test("a mixed success/failure response renders an N resolved, M failed summary", async () => {
    vi.mocked(getProjectDrift).mockResolvedValue(
      mockSummary([
        mockDrift({ workflow_id: 1, repo: "org/repo" }),
        mockDrift({ workflow_id: 2, repo: "org/repo2" }),
      ]),
    );
    vi.mocked(bulkResolveWorkflowDrift).mockResolvedValue({
      success: false,
      results: [
        { workflow_id: 1, repo: "org/repo", branch: "main", success: true, message: "ok" },
        { workflow_id: 2, repo: "org/repo2", branch: "main", success: false, message: "GitHub API failed" },
      ],
    });
    const user = await openModal();

    await user.click(screen.getByTestId("select-all-drifts"));
    await user.click(screen.getByRole("button", { name: /Adopt GitHub Version \(2\)/i }));

    await waitFor(() => expect(screen.getByText(/1 resolved, 1 failed/i)).toBeInTheDocument());
    expect(screen.getByText(/GitHub API failed/i)).toBeInTheDocument();
  });
});
