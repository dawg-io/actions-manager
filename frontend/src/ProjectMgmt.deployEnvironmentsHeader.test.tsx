import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";

const mockNavigate = jest.fn();
const mockUseParams = jest.fn();

vi.mock(
  "react-router-dom",
  () => ({
    useNavigate: () => mockNavigate,
    useParams: () => mockUseParams(),
    useLocation: () => ({ pathname: "/", search: "", hash: "", state: null, key: "test" }),
  }),
  { virtual: true }
);

vi.mock("./api/projects", () => ({
  __esModule: true,
  fetchProjects: jest.fn(),
  loadProject: jest.fn(),
  linkReusableWorkflow: jest.fn(),
  unlinkReusableWorkflow: jest.fn(),
  updateProjectColor: jest.fn(),
  exportProjectBackup: jest.fn(),
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

vi.mock("./components/Sidebar", () => ({
  default: function Sidebar(props: any) {
    return (
      <div data-testid="sidebar">
        <button type="button" onClick={() => props.onSectionChange("environments")}>
          Go Environments
        </button>
        <button type="button" onClick={() => props.onSectionChange("backup-export")}>
          Go Backup
        </button>
      </div>
    );
  },
}));

vi.mock("./components/ProjectList", () => ({
  default: function ProjectList() {
    return <div data-testid="project-list">ProjectList</div>;
  },
}));

vi.mock("./components/RepositoriesAndBranches", () => ({
  default: function RepositoriesAndBranches() {
    return <div data-testid="repositories-and-branches">Repos</div>;
  },
}));

vi.mock("./components/DeployEnvironments", () => {
  const React = require("react");
  const focusFn = () => undefined;
  return {
    default: function DeployEnvironments(props: any) {
      React.useEffect(() => {
        props.onFocusAddEnvironment?.(focusFn);
      }, [props.onFocusAddEnvironment]);
      return <div data-testid="deploy-environments">DeployEnvironments</div>;
    },
  };
});

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
import { fetchProjects, loadProject } from "./api/projects";
import { getSecrets } from "./api/secrets";
import { getEnvVars } from "./api/envVars";
import { getProjectPRStatus } from "./api/pullRequests";





describe("ProjectMgmt deploy environments header", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseParams.mockReturnValue({ user: "testuser", projectName: "MyProject" });
    fetchProjects.mockResolvedValue([]);
    loadProject.mockResolvedValue({
      project_name: "MyProject",
      selected_repos: ["owner/repo"],
      workflows: [],
      rxworkflows: [],
      branch_regex: "",
      project_code: "MP",
      project_id: 123,
      project_type: "standard",
      use_prefix: true,
      visibility_scope: "public",
    });
    getSecrets.mockResolvedValue([]);
    getEnvVars.mockResolvedValue([]);
    getProjectPRStatus.mockResolvedValue({
      project_state: "draft",
      open_prs: 0,
      merged_prs: 0,
      total_prs: 0,
    });
  });

  test('does not render global "Save to GitHub" or "Cancel" on Deploy Environments', async () => {
    const user = userEvent.setup();
    render(
      <ProjectMgmt
        userDetails={{
          avatar_url: "https://example.com/avatar.png",
          github_user: "testuser",
          account_type: "free",
          github_account_type: "User",
        }}
        onLogout={jest.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("sidebar")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Go Environments"));

    expect(screen.getByText("Back to Projects")).toBeInTheDocument();
    expect(screen.queryByText(/Save to GitHub/i)).not.toBeInTheDocument();
    expect(screen.queryByText("🔙 Cancel")).not.toBeInTheDocument();
  });

  test("shows disabled import placeholder in Backup & Export section", async () => {
    const user = userEvent.setup();
    render(
      <ProjectMgmt
        userDetails={{
          avatar_url: "https://example.com/avatar.png",
          github_user: "testuser",
          account_type: "free",
          github_account_type: "User",
        }}
        onLogout={jest.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("sidebar")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Go Backup"));

    expect(screen.getByText("⬇️ Export Project Backup (JSON)")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Import support is planned for a future release. Exported backups are being structured with an import-safe schema now so they can be reused later."
      )
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import Project Backup" })).toBeDisabled();
  });
});
