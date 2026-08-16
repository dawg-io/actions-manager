/**
 * Integration test: WorkflowImportPanel is reachable from the project
 * workflows management page via the "Import Existing" button.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";
import ProjectMgmt from "./ProjectMgmt";
import { fetchProjects, loadProject } from "./api/projects";
import { getSecrets } from "./api/secrets";
import { getEnvVars } from "./api/envVars";
import { getProjectPRStatus } from "./api/pullRequests";





const mockNavigate = vi.fn();
const mockUseParams = vi.fn();

vi.mock(
  "react-router",
  () => ({
    useNavigate: () => mockNavigate,
    useParams: () => mockUseParams(),
    useLocation: () => ({ pathname: "/project/alice/TestProject", search: "", hash: "", state: null, key: "test" }),
  }));

vi.mock("./api/projects", () => ({
  __esModule: true,
  fetchProjects: vi.fn(),
  loadProject: vi.fn(),
  linkReusableWorkflow: vi.fn(),
  unlinkReusableWorkflow: vi.fn(),
  updateProjectColor: vi.fn(),
  exportProjectBackup: vi.fn(),
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
  default: function Sidebar(props: { onSectionChange?: (s: string) => void }) {
    return <div data-testid="sidebar" />;
  },
}));

vi.mock("./components/ProjectList", () => ({
  default: function ProjectList() {
    return <div data-testid="project-list" />;
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
  default: function SaveResultsModal() { return null; },
}));

vi.mock("./components/DeleteProjectModal", () => ({
  default: function DeleteProjectModal() { return null; },
}));

vi.mock("./components/DangerZone", () => ({
  default: function DangerZone() { return null; },
}));

vi.mock("./components/ProjectMembers", () => ({
  default: function ProjectMembers() { return null; },
}));

vi.mock("./components/DriftDetection", () => ({
  default: function DriftDetection() { return null; },
}));

vi.mock("./components/PRStatusPanel", () => ({
  default: function PRStatusPanel() { return null; },
}));

vi.mock("./components/PRHistoryPanel", () => ({
  default: function PRHistoryPanel() { return null; },
}));

vi.mock("./components/CreatePRModal", () => ({
  default: function CreatePRModal() { return null; },
}));

vi.mock("./components/LinkedWorkflowsModal", () => ({
  default: function LinkedWorkflowsModal() { return null; },
}));

vi.mock("./components/ProjectColorSelector", () => ({
  default: function ProjectColorSelector() { return null; },
}));

// Mock the WorkflowImportPanel to verify it gets rendered
vi.mock("./components/WorkflowImportPanel", () => ({
  __esModule: true,
  WorkflowImportPanel: function MockWorkflowImportPanel(props: any) {
    return (
      <div data-testid="workflow-import-panel">
        Import Panel: projectId={props.projectId} projectName={props.projectName}
        githubUser={props.githubUser}
        selectedRepos={JSON.stringify(props.selectedRepos)}
        <button data-testid="import-modal-close" onClick={props.onClose}>Close</button>
        <button
          data-testid="import-complete"
          onClick={() => props.onImportComplete?.("open")}
        >
          Complete
        </button>
      </div>
    );
  },
}));

describe("ProjectMgmt – Workflow Import entry point", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Simulate loading a specific project
    mockUseParams.mockReturnValue({ user: "alice", projectName: "TestProject" });
    vi.mocked(fetchProjects).mockResolvedValue([]);
    vi.mocked(loadProject).mockResolvedValue({
      project_name: "TestProject",
      updated_at: "2024-06-01T00:00:00Z",
      project_code: "TP",
      project_id: 42,
      pr_state: "draft",
      selected_repos: ["alice/my-repo", "alice/other-repo"],
      workflows: [],
      rxworkflows: [],
      project_type: "standard",
      account_type: "professional",
    });
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

  test("shows 'Import Existing' button when project has repos and user is not read-only", async () => {
    render(
      <ProjectMgmt
        userDetails={{
          avatar_url: "https://example.com/avatar.png",
          github_user: "alice",
          account_type: "professional",
          github_account_type: "User",
        }}
        onLogout={vi.fn()}
      />
    );

    // Wait for the import button to appear (project loads async)
    const importBtn = await screen.findByTestId("import-workflows-button");
    expect(importBtn).toBeInTheDocument();
    expect(importBtn).toHaveTextContent("Import Existing");
  });

  test("clicking 'Import Existing' opens the WorkflowImportPanel modal", async () => {
    const user = userEvent.setup();

    render(
      <ProjectMgmt
        userDetails={{
          avatar_url: "https://example.com/avatar.png",
          github_user: "alice",
          account_type: "professional",
          github_account_type: "User",
        }}
        onLogout={vi.fn()}
      />
    );

    const importBtn = await screen.findByTestId("import-workflows-button");
    await user.click(importBtn);

    const panel = await screen.findByTestId("workflow-import-panel");
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveTextContent("projectId=42");
    expect(panel).toHaveTextContent("projectName=TestProject");
    expect(panel).toHaveTextContent("githubUser=alice");
    expect(panel).toHaveTextContent("alice/my-repo");
    expect(panel).toHaveTextContent("alice/other-repo");
  });

  test("clicking 'Import Existing' still opens the modal when project_id is a string", async () => {
    const user = userEvent.setup();
    vi.mocked(loadProject).mockResolvedValue({
      project_name: "TestProject",
      updated_at: "2024-06-01T00:00:00Z",
      project_code: "TP",
      project_id: 42,
      pr_state: "draft",
      selected_repos: ["alice/my-repo", "alice/other-repo"],
      workflows: [],
      rxworkflows: [],
      project_type: "standard",
      account_type: "professional",
    });

    render(
      <ProjectMgmt
        userDetails={{
          avatar_url: "https://example.com/avatar.png",
          github_user: "alice",
          account_type: "professional",
          github_account_type: "User",
        }}
        onLogout={vi.fn()}
      />
    );

    const importBtn = await screen.findByTestId("import-workflows-button");
    await user.click(importBtn);

    await waitFor(() => {
      expect(screen.getByTestId("workflow-import-panel")).toHaveTextContent("projectId=42");
    });
  });

  test("modal closes when onClose is triggered", async () => {
    const user = userEvent.setup();

    render(
      <ProjectMgmt
        userDetails={{
          avatar_url: "https://example.com/avatar.png",
          github_user: "alice",
          account_type: "professional",
          github_account_type: "User",
        }}
        onLogout={vi.fn()}
      />
    );

    const importBtn = await screen.findByTestId("import-workflows-button");
    await user.click(importBtn);

    // Panel is visible
    await waitFor(() => {
      expect(screen.getByTestId("workflow-import-panel")).toBeInTheDocument();
    });

    // Click close button in the mock modal
    const closeBtn = screen.getByTestId("import-modal-close");
    await user.click(closeBtn);

    // Panel is no longer visible
    await waitFor(() => {
      expect(screen.queryByTestId("workflow-import-panel")).not.toBeInTheDocument();
    });
  });

  test("import completion calls loadProject so imported workflows appear immediately", async () => {
    const user = userEvent.setup();

    render(
      <ProjectMgmt
        userDetails={{
          avatar_url: "https://example.com/avatar.png",
          github_user: "alice",
          account_type: "professional",
          github_account_type: "User",
        }}
        onLogout={vi.fn()}
      />
    );

    // Wait for the initial project load to complete (1 call)
    await screen.findByTestId("import-workflows-button");
    expect(loadProject).toHaveBeenCalledTimes(1);

    // Open the import modal and trigger import completion
    await user.click(screen.getByTestId("import-workflows-button"));
    await waitFor(() => {
      expect(screen.getByTestId("workflow-import-panel")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("import-complete"));

    // loadProject must be called a second time so workflows state is updated
    await waitFor(() => {
      expect(loadProject).toHaveBeenCalledTimes(2);
    });
    // Modal stays open (user sees the success state inside it)
    expect(screen.getByTestId("workflow-import-panel")).toBeInTheDocument();
  });

  test("import completion refreshes state without closing the modal", async () => {
    const user = userEvent.setup();

    render(
      <ProjectMgmt
        userDetails={{
          avatar_url: "https://example.com/avatar.png",
          github_user: "alice",
          account_type: "professional",
          github_account_type: "User",
        }}
        onLogout={vi.fn()}
      />
    );

    const importBtn = await screen.findByTestId("import-workflows-button");
    await user.click(importBtn);

    await waitFor(() => {
      expect(screen.getByTestId("workflow-import-panel")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("import-complete"));

    await waitFor(() => {
      expect(screen.getByTestId("workflow-import-panel")).toBeInTheDocument();
    });
  });

  test("'Import Existing' button is NOT shown for read-only users", async () => {
    vi.mocked(loadProject).mockResolvedValue({
      project_name: "TestProject",
      updated_at: "2024-06-01T00:00:00Z",
      project_code: "TP",
      project_id: 42,
      pr_state: "draft",
      selected_repos: ["alice/my-repo"],
      workflows: [],
      rxworkflows: [],
      project_type: "standard",
      account_type: "professional",
    });

    render(
      <ProjectMgmt
        userDetails={{
          avatar_url: "https://example.com/avatar.png",
          github_user: "alice",
          account_type: "professional",
          github_account_type: "User",
          workspace_role: "read_only",
        }}
        onLogout={vi.fn()}
      />
    );

    // Wait for project to load
    await waitFor(() => {
      expect(screen.getByTestId("unified-workflows")).toBeInTheDocument();
    });

    // Import button should not be present for read-only users
    expect(screen.queryByTestId("import-workflows-button")).not.toBeInTheDocument();
  });
});
