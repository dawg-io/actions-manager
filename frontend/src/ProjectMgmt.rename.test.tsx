/**
 * Regression tests for project rename navigation.
 *
 * Root cause: after a successful rename the URL still contained the old project
 * name.  When the user navigated away and back, the `useEffect` that watches
 * `urlProjectName` fired with the old name and reset `projectName` state, so
 * the old name re-appeared without a full browser refresh.
 *
 * Fix: `confirmProjectRename` now calls `navigate` to update the URL to the
 * new project name after a successful API call, so re-entering the route
 * loads the renamed project.
 */
import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";

const mockNavigate = jest.fn();
const mockUseParams = jest.fn();

// Capture Sidebar's onProjectNameSave so tests can trigger a rename
let capturedOnProjectNameSave: ((name: string) => void) | null = null;

vi.mock(
  "react-router-dom",
  () => ({
    useNavigate: () => mockNavigate,
    useParams: () => mockUseParams(),
    useLocation: () => ({
      pathname: "/project/alice/old-name",
      search: "",
      hash: "",
      state: null,
      key: "test",
    }),
  }),
  { virtual: true }
);

vi.mock("./api/projects", () => ({
  __esModule: true,
  fetchProjects: jest.fn(),
  loadProject: jest.fn(),
  updateProjectName: jest.fn(),
  updateProjectColor: jest.fn(),
  exportProjectBackup: jest.fn(),
  linkReusableWorkflow: jest.fn(),
  unlinkReusableWorkflow: jest.fn(),
}));

vi.mock("./api/projectDeletion", () => ({
  deleteProjectEnhanced: jest.fn(),
}));

vi.mock("./api/handlers", () => ({
  handleSaveProjectWithModal: jest.fn(),
}));

vi.mock("./api/secrets", () => ({
  getSecrets: jest.fn(),
}));

vi.mock("./api/envVars", () => ({
  getEnvVars: jest.fn(),
}));

vi.mock("./api/pullRequests", () => ({
  getProjectPRStatus: jest.fn(),
}));

vi.mock("./api/codeowners", () => ({
  getProjectCodeownersStatuses: jest.fn().mockResolvedValue({ statuses: [] }),
}));

vi.mock("./components/Sidebar", () => ({
  default: function Sidebar(props: any) {
    capturedOnProjectNameSave = props.onProjectNameSave;
    return <div data-testid="sidebar" />;
  },
}));

// Render ConfirmDialog buttons so tests can click them
vi.mock("./components/ConfirmDialog", () => ({
  default: function ConfirmDialog(props: any) {
    if (!props.open) return null;
    return (
      <div data-testid="confirm-dialog">
        <button data-testid="confirm-rename-btn" onClick={props.onConfirm}>
          {props.confirmLabel ?? "Confirm"}
        </button>
        <button data-testid="cancel-rename-btn" onClick={props.onCancel}>
          {props.cancelLabel ?? "Cancel"}
        </button>
      </div>
    );
  },
}));

vi.mock("./components/ProjectList", () => ({
  default: function ProjectList(props: any) {
    return (
      <div data-testid="project-list">
        {(props.projects ?? []).map((p: any) => (
          <span key={p.id ?? p.project_id} data-testid="project-name-in-list">
            {p.project_name ?? p.name}
          </span>
        ))}
      </div>
    );
  },
}));

vi.mock("./components/RepositoriesAndBranches", () => ({
  default: function RepositoriesAndBranches() {
    return <div data-testid="repositories-and-branches" />;
  },
}));

vi.mock("./components/DeployEnvironments", () => ({
  default: function DeployEnvironments() {
    return <div data-testid="deploy-environments" />;
  },
}));

vi.mock("./components/EnvVars", () => ({
  default: function EnvVars() {
    return <div data-testid="env-vars" />;
  },
}));

vi.mock("./components/Secrets", () => ({
  default: function Secrets() {
    return <div data-testid="secrets" />;
  },
}));

vi.mock("./components/UnifiedWorkflows", () => ({
  default: function UnifiedWorkflows() {
    return <div data-testid="unified-workflows" />;
  },
}));

vi.mock("./components/RulesetManager", () => ({
  default: function RulesetManager() {
    return <div data-testid="rulesets" />;
  },
}));

vi.mock("./components/CodeownersManager", () => ({
  default: function CodeownersManager() {
    return <div data-testid="codeowners" />;
  },
}));

vi.mock("./components/UserAvatar", () => ({
  default: function UserAvatar() {
    return <div data-testid="user-avatar" />;
  },
}));

vi.mock("./components/PlanUsagePill", () => ({
  default: function PlanUsagePill() {
    return null;
  },
}));

vi.mock("./components/BrandLogo", () => ({
  default: function BrandLogo() {
    return null;
  },
}));

vi.mock("./components/SaveResultsModal", () => ({
  default: function SaveResultsModal() {
    return null;
  },
}));

vi.mock("./components/DeleteProjectModal", () => ({
  default: function DeleteProjectModal() {
    return null;
  },
}));

vi.mock("./components/DangerZone", () => ({
  default: function DangerZone() {
    return null;
  },
}));

vi.mock("./components/ProjectMembers", () => ({
  default: function ProjectMembers() {
    return null;
  },
}));

vi.mock("./components/DriftDetection", () => ({
  default: function DriftDetection() {
    return null;
  },
}));

vi.mock("./components/PRStatusPanel", () => ({
  default: function PRStatusPanel() {
    return null;
  },
}));

vi.mock("./components/PRHistoryPanel", () => ({
  default: function PRHistoryPanel() {
    return null;
  },
}));

vi.mock("./components/CreatePRModal", () => ({
  default: function CreatePRModal() {
    return null;
  },
}));

vi.mock("./components/LinkedWorkflowsModal", () => ({
  default: function LinkedWorkflowsModal() {
    return null;
  },
}));

vi.mock("./components/ProjectColorSelector", () => ({
  default: function ProjectColorSelector() {
    return null;
  },
}));

import ProjectMgmt from "./ProjectMgmt";
import { fetchProjects, loadProject, updateProjectName } from "./api/projects";
import { getSecrets } from "./api/secrets";
import { getEnvVars } from "./api/envVars";
import { getProjectPRStatus } from "./api/pullRequests";

const userDetails = {
  avatar_url: "https://example.com/avatar.png",
  github_user: "alice",
  account_type: "free",
  github_account_type: "User" as const,
};

function renderWithProject() {
  return render(<ProjectMgmt userDetails={userDetails} onLogout={jest.fn()} />);
}

describe("ProjectMgmt – rename navigates to new URL (stale-name regression)", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    capturedOnProjectNameSave = null;

    mockUseParams.mockReturnValue({ user: "alice", projectName: "old-name" });

    (fetchProjects as jest.Mock).mockResolvedValue([
      {
        project_id: 42,
        project_name: "old-name",
        project_code: "OLD",
        updated_at: "2024-01-01T00:00:00Z",
        pr_state: "new",
        project_type: "standard",
      },
    ]);
    (loadProject as jest.Mock).mockResolvedValue({
      project_name: "old-name",
      project_id: 42,
      project_code: "OLD",
      selected_repos: [],
      workflows: [],
      rxworkflows: [],
      branch_regex: "",
      branch_option: "default",
      branch_max_age_days: 30,
      reusable_workflows_enabled: false,
      use_prefix: false,
      project_type: "standard",
      pr_state: "new",
    });
    (getSecrets as jest.Mock).mockResolvedValue([]);
    (getEnvVars as jest.Mock).mockResolvedValue([]);
    (getProjectPRStatus as jest.Mock).mockResolvedValue({
      project_state: "new",
      open_prs: 0,
      merged_prs: 0,
      total_prs: 0,
    });
  });

  test("navigate is called with new-name URL after a successful rename", async () => {
    const user = userEvent.setup();
    (updateProjectName as jest.Mock).mockResolvedValue({
      project_id: 42,
      project_name: "new-name",
      project_code: "OLD",
    });

    const { rerender } = renderWithProject();

    // Wait for the project to load so the Sidebar (and its callback) is mounted
    await waitFor(() => expect(screen.getByTestId("sidebar")).toBeInTheDocument());
    expect(capturedOnProjectNameSave).not.toBeNull();

    // Trigger the rename – this sets pendingRename and shows the ConfirmDialog
    act(() => {
      capturedOnProjectNameSave!("new-name");
    });

    // Confirm the rename
    const confirmBtn = await screen.findByTestId("confirm-rename-btn");
    await user.click(confirmBtn);

    // The key assertion: navigate must be called with the new project name in the URL
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(
        "/project/alice/new-name",
        { replace: true }
      );
    });

    // Sanity check: the API was called with the right arguments
    expect(updateProjectName).toHaveBeenCalledWith("alice", 42, "new-name");

    // Regression: the projects list state must also reflect the new name immediately.
    // Simulate the user navigating back to the project list by clearing the urlProjectName param.
    mockUseParams.mockReturnValue({ user: "alice", projectName: undefined });
    rerender(<ProjectMgmt userDetails={userDetails} onLogout={jest.fn()} />);

    // The project list should now show the new name without requiring a hard refresh
    await waitFor(() => {
      expect(screen.getByTestId("project-name-in-list")).toHaveTextContent("new-name");
    });
  });

  test("navigate is NOT called when the rename API call fails", async () => {
    const user = userEvent.setup();
    (updateProjectName as jest.Mock).mockRejectedValue(
      new Error("Conflict: name already taken")
    );

    renderWithProject();

    await waitFor(() => expect(screen.getByTestId("sidebar")).toBeInTheDocument());
    expect(capturedOnProjectNameSave).not.toBeNull();

    act(() => {
      capturedOnProjectNameSave!("new-name");
    });

    const confirmBtn = await screen.findByTestId("confirm-rename-btn");
    await user.click(confirmBtn);

    // Give any async state updates time to settle
    await waitFor(() => expect(updateProjectName).toHaveBeenCalled());

    // navigate must NOT have been called with the new project URL on failure
    expect(mockNavigate).not.toHaveBeenCalledWith(
      "/project/alice/new-name",
      expect.anything()
    );
  });
});
