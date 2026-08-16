import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";

const mockNavigate = vi.fn();
const mockUseParams = vi.fn();

vi.mock(
  "react-router",
  () => ({
    useNavigate: () => mockNavigate,
    useParams: () => mockUseParams(),
    useLocation: () => ({ pathname: "/", search: "", hash: "", state: null, key: "test" }),
  }));

vi.mock("./api/projects", () => ({
  __esModule: true,
  fetchProjects: vi.fn(),
  loadProject: vi.fn(),
  linkReusableWorkflow: vi.fn(),
  unlinkReusableWorkflow: vi.fn(),
  updateProjectColor: vi.fn(),
}));

vi.mock("./api/projectDeletion", () => ({
  deleteProjectEnhanced: vi.fn(),
}));

vi.mock("./api/handlers", () => ({
  handleSaveProjectWithModal: vi.fn(),
}));

vi.mock("./api/secrets", () => ({
  getSecrets: vi.fn(),
}));

vi.mock("./api/envVars", () => ({
  getEnvVars: vi.fn(),
}));

vi.mock("./api/pullRequests", () => ({
  getProjectPRStatus: vi.fn(),
}));

vi.mock("./components/Sidebar", () => ({
  default: function Sidebar() {
    return <div data-testid="sidebar" />;
  },
}));

vi.mock("./components/ProjectList", () => ({
  default: function ProjectList(props: { onCreateProject?: () => void; isCreateProjectDisabled?: boolean }) {
    return (
      <div data-testid="project-list">
        <button
          data-testid="new-project-button"
          onClick={props.onCreateProject}
          disabled={props.isCreateProjectDisabled}
        >
          New Project
        </button>
      </div>
    );
  },
}));

vi.mock("./components/RepositoriesAndBranches", () => ({
  default: function RepositoriesAndBranches() {
    return <div data-testid="repositories-and-branches">Repos</div>;
  },
}));

vi.mock("./components/DeployEnvironments", () => ({
  default: function DeployEnvironments() {
    return <div data-testid="deploy-environments">DeployEnvironments</div>;
  },
}));

vi.mock("./components/EnvVars", () => ({
  default: function EnvVars() {
    return <div data-testid="env-vars">EnvVars</div>;
  },
}));

vi.mock("./components/Secrets", () => ({
  default: function Secrets() {
    return <div data-testid="secrets">Secrets</div>;
  },
}));

vi.mock("./components/UnifiedWorkflows", () => ({
  default: function UnifiedWorkflows() {
    return <div data-testid="unified-workflows">Workflows</div>;
  },
}));

vi.mock("./components/RulesetManager", () => ({
  default: function RulesetManager() {
    return <div data-testid="rulesets">Rulesets</div>;
  },
}));

vi.mock("./components/CodeownersManager", () => ({
  default: function CodeownersManager() {
    return <div data-testid="codeowners">Codeowners</div>;
  },
}));

vi.mock("./components/UserAvatar", () => ({
  default: function UserAvatar() {
    return <div data-testid="user-avatar">UserAvatar</div>;
  },
}));

vi.mock("./components/PlanUsagePill", () => ({
  default: function PlanUsagePill() {
    return <div data-testid="plan-usage-pill">PlanUsagePill</div>;
  },
}));

vi.mock("./components/BrandLogo", () => ({
  default: function BrandLogo() {
    return <div data-testid="brand-logo">BrandLogo</div>;
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
import { fetchProjects, type Project } from "./api/projects";
import { getSecrets } from "./api/secrets";
import { getEnvVars } from "./api/envVars";
import { getProjectPRStatus } from "./api/pullRequests";





/** Build a minimal project stub with an optional account_type and project_type override. */
function makeProject(
  id: number,
  accountType?: string,
  projectType?: "standard" | "rwx",
): Project {
  return {
    id,
    project_name: `Project${id}`,
    project_code: `P${id}`,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-06-01T00:00:00Z",
    pr_state: "draft",
    project_type: projectType ?? "standard",
    ...(accountType ? { account_type: accountType } : {}),
  };
}

describe("ProjectMgmt – New Project header button", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Show the project-list view (no project selected)
    mockUseParams.mockReturnValue({ user: "alice", projectName: undefined });
    vi.mocked(getSecrets).mockResolvedValue([]);
    vi.mocked(getEnvVars).mockResolvedValue([]);
    vi.mocked(getProjectPRStatus).mockResolvedValue({
      project_state: "draft",
      pull_requests: [],
      closed_prs: 0,
      open_prs: 0,
      merged_prs: 0,
      total_prs: 0,
    });
  });

  test("clicking New Project navigates to /project/:user/new", async () => {
    const user = userEvent.setup();
    // One project – well under the free limit of 3
    vi.mocked(fetchProjects).mockResolvedValue([makeProject(1, "free")]);

    render(
      <ProjectMgmt
        userDetails={{
          avatar_url: "https://example.com/avatar.png",
          github_user: "alice",
          account_type: "free",
          github_account_type: "User",
        }}
        onLogout={vi.fn()}
      />
    );

    const btn = await screen.findByTestId("new-project-button");
    await user.click(btn);

    expect(mockNavigate).toHaveBeenCalledWith("/project/alice/new");
  });

  test("button is disabled when free-plan project limit (3) is reached via userDetails", async () => {
    // 3 projects – exactly at the free limit
    vi.mocked(fetchProjects).mockResolvedValue([
      makeProject(1, "free"),
      makeProject(2),
      makeProject(3),
    ]);

    render(
      <ProjectMgmt
        userDetails={{
          avatar_url: "https://example.com/avatar.png",
          github_user: "alice",
          account_type: "free",
          github_account_type: "User",
        }}
        onLogout={vi.fn()}
      />
    );

    // Wait for projects to load asynchronously before asserting disabled state
    await waitFor(() => {
      const btn = screen.getByTestId("new-project-button");
      expect(btn).toBeDisabled();
    });
  });

  test("button is disabled when limit is reached using accountType state fallback (userDetails absent)", async () => {
    // 3 projects; first carries account_type so the component can set accountType state
    vi.mocked(fetchProjects).mockResolvedValue([
      makeProject(1, "free"),
      makeProject(2),
      makeProject(3),
    ]);

    // No userDetails prop – simulates still-loading auth
    render(<ProjectMgmt onLogout={vi.fn()} />);

    await waitFor(() => {
      const btn = screen.getByTestId("new-project-button");
      expect(btn).toBeDisabled();
    });
  });

  test("button is disabled when projects are loaded but account type is not yet known", async () => {
    // Projects present but no account_type on any of them, and no userDetails
    vi.mocked(fetchProjects).mockResolvedValue([makeProject(1), makeProject(2)]);

    render(<ProjectMgmt onLogout={vi.fn()} />);

    await waitFor(() => {
      const btn = screen.getByTestId("new-project-button");
      expect(btn).toBeDisabled();
    });
  });
});

describe("ProjectMgmt – New Project button self-hosted beta limits", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseParams.mockReturnValue({ user: "alice", projectName: undefined });
    vi.mocked(getSecrets).mockResolvedValue([]);
    vi.mocked(getEnvVars).mockResolvedValue([]);
    vi.mocked(getProjectPRStatus).mockResolvedValue({
      project_state: "draft",
      pull_requests: [],
      closed_prs: 0,
      open_prs: 0,
      merged_prs: 0,
      total_prs: 0,
    });
  });

  const betaUserDetails = {
    avatar_url: "https://example.com/avatar.png",
    github_user: "alice",
    account_type: "free",
    github_account_type: "User" as const,
    installation_mode: "self-hosted",
  };

  test("beta: button is enabled with 3 caller and 0 reusable projects", async () => {
    vi.mocked(fetchProjects).mockResolvedValue([
      makeProject(1, "free", "standard"),
      makeProject(2, "free", "standard"),
      makeProject(3, "free", "standard"),
    ]);

    render(<ProjectMgmt userDetails={betaUserDetails} onLogout={vi.fn()} />);

    await waitFor(() => {
      const btn = screen.getByTestId("new-project-button");
      expect(btn).not.toBeDisabled();
    });
  });

  test("beta: button is enabled with 4 caller and 0 reusable projects (can still create rwx)", async () => {
    vi.mocked(fetchProjects).mockResolvedValue([
      makeProject(1, "free", "standard"),
      makeProject(2, "free", "standard"),
      makeProject(3, "free", "standard"),
      makeProject(4, "free", "standard"),
    ]);

    render(<ProjectMgmt userDetails={betaUserDetails} onLogout={vi.fn()} />);

    await waitFor(() => {
      const btn = screen.getByTestId("new-project-button");
      expect(btn).not.toBeDisabled();
    });
  });

  test("beta: button is disabled with 4 caller and 2 reusable projects (both limits reached)", async () => {
    vi.mocked(fetchProjects).mockResolvedValue([
      makeProject(1, "free", "standard"),
      makeProject(2, "free", "standard"),
      makeProject(3, "free", "standard"),
      makeProject(4, "free", "standard"),
      makeProject(5, "free", "rwx"),
      makeProject(6, "free", "rwx"),
    ]);

    render(<ProjectMgmt userDetails={betaUserDetails} onLogout={vi.fn()} />);

    await waitFor(() => {
      const btn = screen.getByTestId("new-project-button");
      expect(btn).toBeDisabled();
    });
  });

  test("beta: button is enabled with 0 caller and 2 reusable projects (caller limit not reached)", async () => {
    vi.mocked(fetchProjects).mockResolvedValue([
      makeProject(1, "free", "rwx"),
      makeProject(2, "free", "rwx"),
    ]);

    render(<ProjectMgmt userDetails={betaUserDetails} onLogout={vi.fn()} />);

    await waitFor(() => {
      const btn = screen.getByTestId("new-project-button");
      expect(btn).not.toBeDisabled();
    });
  });
});
