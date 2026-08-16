/**
 * Regression tests for drift status not syncing to the project list.
 *
 * Root cause: GET /api/projects/{id}/drift (fired by <DriftDetection> when a
 * project's detail page loads) does a live GitHub check and persists the
 * result server-side (see get_project_drift / _cache_project_drift_summary
 * in backend/workflows.py), but the frontend's onDriftLoaded callback
 * (handleDriftLoaded in ProjectMgmt.tsx) only updated local driftDetails
 * state used for a save-guard - it never refreshed the `projects` list state
 * that <ProjectList> renders. The list state was otherwise only fetched once
 * per mount/login, so a project's drift badge stayed stale in the list until
 * the next full reload, even though the just-viewed detail page already
 * showed it correctly.
 *
 * Fix: handleDriftLoaded now also calls the existing refreshProjectsList()
 * (the same function already used after other status-changing actions like
 * delete/PR-campaign updates), so the list picks up the freshly-persisted
 * drift_status without requiring navigation away/back or a reload.
 */
import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";

const mockNavigate = vi.fn();
const mockUseParams = vi.fn();

// Capture DriftDetection's onDriftLoaded so tests can simulate a drift check completing
let capturedOnDriftLoaded: ((details: unknown[]) => void) | null = null;
let capturedSeededDriftNames: string[] | null = null;

vi.mock(
  "react-router",
  () => ({
    useNavigate: () => mockNavigate,
    useParams: () => mockUseParams(),
    useLocation: () => ({
      pathname: "/project/alice/proj-a",
      search: "",
      hash: "",
      state: null,
      key: "test",
    }),
  }));

vi.mock("./api/projects", () => ({
  __esModule: true,
  fetchProjects: vi.fn(),
  loadProject: vi.fn(),
  updateProjectName: vi.fn(),
  updateProjectColor: vi.fn(),
  exportProjectBackup: vi.fn(),
  linkReusableWorkflow: vi.fn(),
  unlinkReusableWorkflow: vi.fn(),
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

vi.mock("./api/codeowners", () => ({
  getProjectCodeownersStatuses: vi.fn().mockResolvedValue({ statuses: [] }),
}));

vi.mock("./components/Sidebar", () => ({
  default: function Sidebar() {
    return <div data-testid="sidebar" />;
  },
}));

vi.mock("./components/ProjectList", () => ({
  default: function ProjectList(props: any) {
    return (
      <div data-testid="project-list">
        {(props.projects ?? []).map((p: any) => (
          <span
            key={p.id ?? p.project_id}
            data-testid="project-drift-in-list"
          >
            {p.drift_status ?? "unknown"}
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

// Captures the driftedWorkflowNames prop each render, so tests can assert on
// the badge-driving state without needing the real UnifiedWorkflowList tree.
let capturedDriftedWorkflowNames: Set<string> | null = null;

vi.mock("./components/UnifiedWorkflows", () => ({
  default: function UnifiedWorkflows(props: any) {
    capturedDriftedWorkflowNames = props.driftedWorkflowNames;
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

// Capture onDriftLoaded instead of rendering nothing, so tests can simulate
// a drift check completing the way the real DriftDetection component does.
vi.mock("./components/DriftDetection", () => ({
  default: function DriftDetection(props: any) {
    capturedOnDriftLoaded = props.onDriftLoaded;
    capturedSeededDriftNames = props.seededDriftNames;
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

import type { Mock } from 'vitest';
const userDetails = {
  avatar_url: "https://example.com/avatar.png",
  github_user: "alice",
  account_type: "free",
  github_account_type: "User" as const,
};

const baseProject = {
  project_id: 42,
  project_name: "proj-a",
  project_code: "PROJA",
  updated_at: "2024-01-01T00:00:00Z",
  pr_state: "new" as const,
  project_type: "standard" as const,
};

const fakeDriftDetail = {
  workflow_id: 1,
  workflow_name: "CI",
  workflow_filename: "ci.yml",
  repo: "acme/proj-a",
  branch: "main",
  has_drift: true,
  actionsmanager_yaml: "name: CI\n",
  github_yaml: "name: CI (changed)\n",
  actionsmanager_sha: "aaa",
  github_sha: "bbb",
  last_checked: "2024-01-02T00:00:00Z",
  message: "drifted",
};

function renderWithProject() {
  return render(<ProjectMgmt userDetails={userDetails} onLogout={vi.fn()} />);
}

describe("ProjectMgmt – drift status syncs to project list (stale-list regression)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnDriftLoaded = null;
    capturedDriftedWorkflowNames = null;
    capturedSeededDriftNames = null;

    mockUseParams.mockReturnValue({ user: "alice", projectName: "proj-a" });

    (fetchProjects as Mock)
      .mockResolvedValueOnce([{ ...baseProject, drift_status: "clean" }])
      .mockResolvedValue([{ ...baseProject, drift_status: "drifted", drift_count: 1 }]);

    (loadProject as Mock).mockResolvedValue({
      project_name: "proj-a",
      project_id: 42,
      project_code: "PROJA",
      selected_repos: ["acme/proj-a"],
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
    (getSecrets as Mock).mockResolvedValue([]);
    (getEnvVars as Mock).mockResolvedValue([]);
    (getProjectPRStatus as Mock).mockResolvedValue({
      project_state: "new",
      open_prs: 0,
      merged_prs: 0,
      total_prs: 0,
    });
  });

  test("list reflects drift status after the detail page's drift check loads, without a reload", async () => {
    // Start on the project list (no project selected in the URL) - mirrors
    // the reported flow: list -> open a project -> back to list.
    mockUseParams.mockReturnValue({ user: "alice", projectName: undefined });

    const { rerender } = renderWithProject();

    // Wait for the initial list fetch to land - starts out clean.
    await waitFor(() => expect(fetchProjects).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByTestId("project-drift-in-list")).toHaveTextContent("clean")
    );

    // Navigate into the project's detail page - mounts <DriftDetection>.
    mockUseParams.mockReturnValue({ user: "alice", projectName: "proj-a" });
    rerender(<ProjectMgmt userDetails={userDetails} onLogout={vi.fn()} />);

    await waitFor(() => expect(capturedOnDriftLoaded).not.toBeNull());

    // Simulate DriftDetection completing a real drift check on the detail page.
    act(() => {
      capturedOnDriftLoaded!([fakeDriftDetail]);
    });

    // Regression: navigating back to the list must show the new status
    // immediately - this only works if handleDriftLoaded also triggered a
    // projects-list refresh while we were on the detail page.
    await waitFor(() => expect(fetchProjects).toHaveBeenCalledTimes(2));

    mockUseParams.mockReturnValue({ user: "alice", projectName: undefined });
    rerender(<ProjectMgmt userDetails={userDetails} onLogout={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByTestId("project-drift-in-list")).toHaveTextContent("drifted")
    );
  });

  test("the empty-check callback (no repos selected yet) still safely refreshes the list", async () => {
    mockUseParams.mockReturnValue({ user: "alice", projectName: "proj-a" });
    renderWithProject();

    await waitFor(() => expect(fetchProjects).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(capturedOnDriftLoaded).not.toBeNull());

    act(() => {
      capturedOnDriftLoaded!([]);
    });

    await waitFor(() => expect(fetchProjects).toHaveBeenCalledTimes(2));
  });

  test("drift badge is seeded from the persisted project-load response before the live check resolves", async () => {
    mockUseParams.mockReturnValue({ user: "alice", projectName: "proj-a" });
    (loadProject as Mock).mockResolvedValue({
      project_name: "proj-a",
      project_id: 42,
      project_code: "PROJA",
      selected_repos: ["acme/proj-a"],
      workflows: [],
      rxworkflows: [],
      branch_regex: "",
      branch_option: "default",
      branch_max_age_days: 30,
      reusable_workflows_enabled: false,
      use_prefix: false,
      project_type: "standard",
      pr_state: "new",
      drifted_workflow_names: ["CI"],
    });

    renderWithProject();

    // Assert the seeded state lands from the project-load response alone -
    // note we never invoke capturedOnDriftLoaded in this test, so this can
    // only be true if it came from loadProject's drifted_workflow_names,
    // not from a live drift check. This is what makes the badge correct on
    // first paint instead of a flip.
    await waitFor(() => expect(capturedDriftedWorkflowNames).not.toBeNull());
    expect(Array.from(capturedDriftedWorkflowNames!)).toEqual(["CI"]);
  });

  test("persisted drift names are passed to DriftDetection so the banner renders on first paint", async () => {
    mockUseParams.mockReturnValue({ user: "alice", projectName: "proj-a" });
    (loadProject as Mock).mockResolvedValue({
      project_name: "proj-a",
      project_id: 42,
      project_code: "PROJA",
      selected_repos: ["acme/proj-a"],
      workflows: [],
      rxworkflows: [],
      branch_regex: "",
      branch_option: "default",
      branch_max_age_days: 30,
      reusable_workflows_enabled: false,
      use_prefix: false,
      project_type: "standard",
      pr_state: "new",
      drifted_workflow_names: ["CI"],
    });

    renderWithProject();

    // The banner lives inside DriftDetection and starts from its own empty
    // state, so it can only render on first paint if the persisted names are
    // threaded in as a prop. capturedOnDriftLoaded is never invoked here, so
    // this can only come from loadProject's response.
    await waitFor(() => expect(capturedSeededDriftNames).toEqual(["CI"]));
  });

  test("seeded drift names survive the live check overwriting driftDetails", async () => {
    mockUseParams.mockReturnValue({ user: "alice", projectName: "proj-a" });
    (loadProject as Mock).mockResolvedValue({
      project_name: "proj-a",
      project_id: 42,
      project_code: "PROJA",
      selected_repos: ["acme/proj-a"],
      workflows: [],
      rxworkflows: [],
      branch_regex: "",
      branch_option: "default",
      branch_max_age_days: 30,
      reusable_workflows_enabled: false,
      use_prefix: false,
      project_type: "standard",
      pr_state: "new",
      drifted_workflow_names: ["CI"],
    });

    renderWithProject();
    await waitFor(() => expect(capturedOnDriftLoaded).not.toBeNull());

    act(() => {
      capturedOnDriftLoaded!([]);
    });

    // driftDetails is now empty, but the seed must not be clobbered with it -
    // DriftDetection owns when to stop using the seed, via its own liveLoaded.
    await waitFor(() => expect(Array.from(capturedDriftedWorkflowNames!)).toEqual([]));
    expect(capturedSeededDriftNames).toEqual(["CI"]);
  });

  test("live check result still fully replaces the seeded state once it resolves", async () => {
    mockUseParams.mockReturnValue({ user: "alice", projectName: "proj-a" });
    (loadProject as Mock).mockResolvedValue({
      project_name: "proj-a",
      project_id: 42,
      project_code: "PROJA",
      selected_repos: ["acme/proj-a"],
      workflows: [],
      rxworkflows: [],
      branch_regex: "",
      branch_option: "default",
      branch_max_age_days: 30,
      reusable_workflows_enabled: false,
      use_prefix: false,
      project_type: "standard",
      pr_state: "new",
      drifted_workflow_names: ["CI"],
    });

    renderWithProject();
    await waitFor(() => expect(capturedOnDriftLoaded).not.toBeNull());

    act(() => {
      capturedOnDriftLoaded!([]); // live check found nothing drifted
    });

    await waitFor(() => expect(Array.from(capturedDriftedWorkflowNames!)).toEqual([]));
  });
});
