/**
 * Tests for the per-project drift check schedule (Drift Detection section).
 *
 * Drift cadence used to be one env var for the whole install. Each project can
 * now inherit the workspace default, opt out entirely, or pick its own
 * interval — so the control has to save without a refresh, and has to roll
 * back rather than show a value the server rejected.
 */
import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";

const mockNavigate = jest.fn();
const mockUseParams = jest.fn();

// Capture Sidebar's onSectionChange so tests can open the Project Info panel
let capturedOnSectionChange: ((section: string) => void) | null = null;

vi.mock(
  "react-router",
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
  updateProjectDriftConfig: jest.fn(),
  exportProjectBackup: jest.fn(),
  linkReusableWorkflow: jest.fn(),
  unlinkReusableWorkflow: jest.fn(),
}));

vi.mock("./api/driftSettings", async () => {
  const actual = await vi.importActual<typeof import("./api/driftSettings")>("./api/driftSettings");
  return { ...actual, fetchDriftSettings: jest.fn(), saveDriftSettings: jest.fn() };
});

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
    capturedOnSectionChange = props.onSectionChange;
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
import { fetchProjects, loadProject, updateProjectDriftConfig } from "./api/projects";
import { fetchDriftSettings } from "./api/driftSettings";
import { getSecrets } from "./api/secrets";
import { getEnvVars } from "./api/envVars";
import { getProjectPRStatus } from "./api/pullRequests";

const userDetails = {
  avatar_url: "https://example.com/avatar.png",
  github_user: "alice",
  account_type: "free",
  github_account_type: "User" as const,
};

const PROJECT = {
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
};

async function renderDriftSection() {
  render(<ProjectMgmt userDetails={userDetails} onLogout={jest.fn()} />);
  await waitFor(() => expect(capturedOnSectionChange).not.toBeNull());
  await act(async () => {
    capturedOnSectionChange!("drift-config");
  });
  return screen.findByTestId("project-drift-interval");
}

describe("ProjectMgmt - per-project drift schedule", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    capturedOnSectionChange = null;

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
    (loadProject as jest.Mock).mockResolvedValue({ ...PROJECT });
    (fetchDriftSettings as jest.Mock).mockResolvedValue({
      sweep_enabled: true,
      recheck_interval_minutes: 30,
      batch_size: 5,
      poll_interval_seconds: 60,
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

  test("a project with no override shows the inherited workspace default", async () => {
    const select = await renderDriftSection();

    expect(select).toHaveValue("inherit");
    expect(screen.getByRole("option", { name: /use workspace default \(every 30 minutes\)/i })).toBeInTheDocument();
  });

  test("a project with its own interval shows that interval", async () => {
    (loadProject as jest.Mock).mockResolvedValue({ ...PROJECT, drift_check_interval_minutes: 1440 });

    const select = await renderDriftSection();

    expect(select).toHaveValue("1440");
  });

  test("a project switched off shows Off, not the inherited default", async () => {
    // 0 and null mean opposite things; rendering 0 as "inherit" would tell the
    // user their project is being checked when it is not.
    (loadProject as jest.Mock).mockResolvedValue({ ...PROJECT, drift_check_interval_minutes: 0 });

    const select = await renderDriftSection();

    expect(select).toHaveValue("0");
  });

  test("choosing an interval saves it and renders it without a refresh", async () => {
    const user = userEvent.setup();
    (updateProjectDriftConfig as jest.Mock).mockResolvedValue({
      project_id: 42,
      drift_check_interval_minutes: 1440,
    });

    const select = await renderDriftSection();
    await user.selectOptions(select, "1440");

    await waitFor(() =>
      expect(updateProjectDriftConfig).toHaveBeenCalledWith("alice", 42, 1440),
    );
    expect(select).toHaveValue("1440");
    expect(await screen.findByText(/saved/i)).toBeInTheDocument();
  });

  test("choosing Off sends 0 rather than null", async () => {
    const user = userEvent.setup();
    (updateProjectDriftConfig as jest.Mock).mockResolvedValue({
      project_id: 42,
      drift_check_interval_minutes: 0,
    });

    const select = await renderDriftSection();
    await user.selectOptions(select, "0");

    await waitFor(() => expect(updateProjectDriftConfig).toHaveBeenCalledWith("alice", 42, 0));
  });

  test("returning to the workspace default sends null", async () => {
    const user = userEvent.setup();
    (loadProject as jest.Mock).mockResolvedValue({ ...PROJECT, drift_check_interval_minutes: 1440 });
    (updateProjectDriftConfig as jest.Mock).mockResolvedValue({
      project_id: 42,
      drift_check_interval_minutes: null,
    });

    const select = await renderDriftSection();
    await user.selectOptions(select, "inherit");

    await waitFor(() => expect(updateProjectDriftConfig).toHaveBeenCalledWith("alice", 42, null));
    expect(select).toHaveValue("inherit");
  });

  test("a failed save rolls back to the previous value and says why", async () => {
    const user = userEvent.setup();
    (updateProjectDriftConfig as jest.Mock).mockRejectedValue({
      response: { data: { detail: "Insufficient project permissions" } },
    });

    const select = await renderDriftSection();
    await user.selectOptions(select, "1440");

    await waitFor(() => expect(screen.getByText(/insufficient project permissions/i)).toBeInTheDocument());
    expect(select).toHaveValue("inherit");
  });
});
