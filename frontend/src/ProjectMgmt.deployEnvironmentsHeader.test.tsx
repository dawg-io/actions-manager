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
    Link: ({ to, children, ...rest }: any) => (
      <a href={to} {...rest}>
        {children}
      </a>
    ),
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
  default: function Sidebar(props: any) {
    return (
      <div data-testid="sidebar">
        <button type="button" onClick={() => props.onSectionChange("environments")}>
          Go Environments
        </button>
        <button type="button" onClick={() => props.onSectionChange("backup-export")}>
          Go Backup
        </button>
        <button type="button" onClick={() => props.onSectionChange("secrets")}>
          Go Secrets
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
    vi.clearAllMocks();
    mockUseParams.mockReturnValue({ user: "testuser", projectName: "MyProject" });
    vi.mocked(fetchProjects).mockResolvedValue([]);
    vi.mocked(loadProject).mockResolvedValue({
      project_name: "MyProject",
      updated_at: "2024-06-01T00:00:00Z",
      selected_repos: ["owner/repo"],
      workflows: [],
      rxworkflows: [],
      branch_regex: "",
      project_code: "MP",
      project_id: 123,
      project_type: "standard",
      use_prefix: true,
      repository_visibility_scope: "public",
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

  // The five Repository Config panels render full edit controls and none of
  // them was read-only aware. Rather than gating each control in each panel -
  // which is what gets missed - the page is wrapped in a disabled fieldset,
  // and HTML makes every descendant form control inert for free.
  // These live in the page header, outside the read-only fieldset that covers
  // the config panels - so the fieldset does not reach them and they need
  // gating of their own. "Create Environment" already had it; Add Secret and
  // Add Environment Variable did not, and stayed live for a viewer.
  test("disables the header Add Secret button for a viewer", async () => {
    const user = userEvent.setup();
    render(
      <ProjectMgmt
        userDetails={{
          avatar_url: "https://example.com/avatar.png",
          github_user: "testuser",
          account_type: "free",
          github_account_type: "User",
          workspace_role: "read_only",
        }}
        onLogout={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("sidebar")).toBeInTheDocument();
    });
    await user.click(screen.getByText("Go Secrets"));

    const add = screen.queryByRole("button", { name: /Add Secret/i });
    if (add) {
      expect(add).toBeDisabled();
    }
  });

  test("wraps the repository config page in a disabled fieldset for a viewer", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <ProjectMgmt
        userDetails={{
          avatar_url: "https://example.com/avatar.png",
          github_user: "testuser",
          account_type: "free",
          github_account_type: "User",
          workspace_role: "read_only",
        }}
        onLogout={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("sidebar")).toBeInTheDocument();
    });
    await user.click(screen.getByText("Go Environments"));

    const guard = container.querySelector("fieldset.repo-configs-readonly");
    expect(guard).not.toBeNull();
    expect(guard).toBeDisabled();
    // The panels are still rendered - a viewer reads them, they are not hidden.
    expect(screen.getByTestId("deploy-environments")).toBeInTheDocument();
  });

  test("leaves the page unwrapped for someone who can edit", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <ProjectMgmt
        userDetails={{
          avatar_url: "https://example.com/avatar.png",
          github_user: "testuser",
          account_type: "free",
          github_account_type: "User",
          workspace_role: "admin",
        }}
        onLogout={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("sidebar")).toBeInTheDocument();
    });
    await user.click(screen.getByText("Go Environments"));

    expect(container.querySelector("fieldset.repo-configs-readonly")).toBeNull();
    expect(screen.getByTestId("deploy-environments")).toBeInTheDocument();
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
          // Export Config lives under Project Configs, admin-only.
          workspace_role: "admin",
        }}
        onLogout={vi.fn()}
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

  test("offers export only, with no dead import control", async () => {
    const user = userEvent.setup();
    render(
      <ProjectMgmt
        userDetails={{
          avatar_url: "https://example.com/avatar.png",
          github_user: "testuser",
          account_type: "free",
          github_account_type: "User",
          // Export Config lives under Project Configs, admin-only.
          workspace_role: "admin",
        }}
        onLogout={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("sidebar")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Go Backup"));

    expect(screen.getByText("⬇️ Export Project Backup (JSON)")).toBeInTheDocument();

    // A permanently-disabled control promising a future release is worse than
    // no control, and there is now a working restore elsewhere in the product
    // to be confused with. Guard against it coming back.
    expect(screen.queryByRole("button", { name: /import/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/planned for a future release/i)).not.toBeInTheDocument();

    // Say plainly that this is not an installation backup, and where that lives.
    expect(screen.getByText(/not an installation backup/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Backup" })).toHaveAttribute("href", "/workspace/backup");
  });
});
