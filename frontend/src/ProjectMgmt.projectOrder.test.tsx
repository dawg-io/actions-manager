/**
 * Tests for persisting a manual Projects-grid order (issue #1804).
 *
 * The grid used to sort by updated_at, so opening or editing a project moved
 * its card. Order is now saved per user. ProjectMgmt owns the projects array,
 * so it applies a drop optimistically and must roll the whole list back if the
 * save fails — otherwise the UI and backend silently disagree.
 *
 * Real pointer dragging through dnd-kit is not reliably simulatable in jsdom,
 * so these drive the onReorder contract directly and leave genuine dragging to
 * the Playwright suite.
 */
import React from "react";
import { render, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";

const mockNavigate = jest.fn();
const mockUseParams = jest.fn();

// Captured from the mocked ProjectList so tests can invoke the reorder contract
// and observe what the parent renders back.
let capturedOnReorder: ((orderedIds: number[]) => void) | null = null;
let capturedProjects: any[] | null = null;
let capturedReorderError: string | null = null;

vi.mock(
  "react-router",
  () => ({
    useNavigate: () => mockNavigate,
    useParams: () => mockUseParams(),
    useLocation: () => ({ pathname: "/", search: "", hash: "", state: null, key: "test" }),
  }),
  { virtual: true },
);

vi.mock("./api/projects", () => ({
  __esModule: true,
  fetchProjects: jest.fn(),
  loadProject: jest.fn(),
  updateProjectName: jest.fn(),
  updateProjectColor: jest.fn(),
  updateProjectOrder: jest.fn(),
  exportProjectBackup: jest.fn(),
  linkReusableWorkflow: jest.fn(),
  unlinkReusableWorkflow: jest.fn(),
}));

vi.mock("./api/projectDeletion", () => ({ deleteProjectEnhanced: jest.fn() }));
vi.mock("./api/handlers", () => ({ handleSaveProjectWithModal: jest.fn() }));
vi.mock("./api/secrets", () => ({ getSecrets: jest.fn() }));
vi.mock("./api/envVars", () => ({ getEnvVars: jest.fn() }));
vi.mock("./api/pullRequests", () => ({ getProjectPRStatus: jest.fn() }));
vi.mock("./api/codeowners", () => ({
  getProjectCodeownersStatuses: jest.fn().mockResolvedValue({ statuses: [] }),
}));

vi.mock("./components/ProjectList", () => ({
  default: function ProjectList(props: any) {
    capturedOnReorder = props.onReorder;
    capturedProjects = props.projects;
    capturedReorderError = props.reorderError;
    return <div data-testid="project-list" />;
  },
}));

vi.mock("./components/Sidebar", () => ({ default: function C() { return <div data-testid="sidebar" />; } }));
vi.mock("./components/RepositoriesAndBranches", () => ({ default: function C() { return <div data-testid="repos" />; } }));
vi.mock("./components/DeployEnvironments", () => ({ default: function C() { return <div data-testid="envs" />; } }));
vi.mock("./components/EnvVars", () => ({ default: function C() { return <div data-testid="env-vars" />; } }));
vi.mock("./components/Secrets", () => ({ default: function C() { return <div data-testid="secrets" />; } }));
vi.mock("./components/UnifiedWorkflows", () => ({ default: function C() { return <div data-testid="unified-workflows" />; } }));
vi.mock("./components/RulesetManager", () => ({ default: function C() { return <div data-testid="rulesets" />; } }));
vi.mock("./components/CodeownersManager", () => ({ default: function C() { return <div data-testid="codeowners" />; } }));
vi.mock("./components/UserAvatar", () => ({ default: function C() { return <div data-testid="user-avatar" />; } }));
vi.mock("./components/PlanUsagePill", () => ({ default: function C() { return null; } }));
vi.mock("./components/BrandLogo", () => ({ default: function C() { return null; } }));
vi.mock("./components/SaveResultsModal", () => ({ default: function C() { return null; } }));
vi.mock("./components/DeleteProjectModal", () => ({ default: function C() { return null; } }));
vi.mock("./components/DangerZone", () => ({ default: function C() { return null; } }));
vi.mock("./components/ProjectMembers", () => ({ default: function C() { return null; } }));
vi.mock("./components/DriftDetection", () => ({ default: function C() { return null; } }));
vi.mock("./components/PRStatusPanel", () => ({ default: function C() { return null; } }));
vi.mock("./components/PRHistoryPanel", () => ({ default: function C() { return null; } }));
vi.mock("./components/CreatePRModal", () => ({ default: function C() { return null; } }));
vi.mock("./components/LinkedWorkflowsModal", () => ({ default: function C() { return null; } }));
vi.mock("./components/ProjectColorSelector", () => ({ default: function C() { return null; } }));

import ProjectMgmt from "./ProjectMgmt";
import { fetchProjects, updateProjectOrder } from "./api/projects";

const userDetails = {
  avatar_url: "https://example.com/avatar.png",
  github_user: "alice",
  account_type: "free",
  github_account_type: "User" as const,
};

const PROJECTS = [
  { project_id: 1, project_name: "alpha", project_code: "ALPHA", updated_at: "2024-01-01T00:00:00Z", pr_state: "new" as const, project_type: "standard" as const },
  { project_id: 2, project_name: "beta", project_code: "BETA", updated_at: "2024-01-02T00:00:00Z", pr_state: "new" as const, project_type: "standard" as const },
  { project_id: 3, project_name: "gamma", project_code: "GAMMA", updated_at: "2024-01-03T00:00:00Z", pr_state: "new" as const, project_type: "standard" as const },
];

function names(): string[] {
  return (capturedProjects ?? []).map((p) => p.project_name);
}

describe("ProjectMgmt – persistent project ordering", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    capturedOnReorder = null;
    capturedProjects = null;
    capturedReorderError = null;
    mockUseParams.mockReturnValue({ user: "alice", projectName: undefined });
    (fetchProjects as jest.Mock).mockResolvedValue(PROJECTS);
  });

  test("a drop reorders the grid immediately, before the save resolves", async () => {
    let resolveSave!: (v: number[]) => void;
    (updateProjectOrder as jest.Mock).mockReturnValue(
      new Promise<number[]>((resolve) => { resolveSave = resolve; }),
    );

    render(<ProjectMgmt userDetails={userDetails} onLogout={jest.fn()} />);
    await waitFor(() => expect(capturedOnReorder).not.toBeNull());
    await waitFor(() => expect(names()).toEqual(["alpha", "beta", "gamma"]));

    await act(async () => { capturedOnReorder!([3, 1, 2]); });

    // Applied optimistically — the save is still in flight.
    expect(names()).toEqual(["gamma", "alpha", "beta"]);
    await act(async () => { resolveSave([3, 1, 2]); });
  });

  test("the complete project id list is sent to the backend", async () => {
    (updateProjectOrder as jest.Mock).mockResolvedValue([3, 1, 2]);

    render(<ProjectMgmt userDetails={userDetails} onLogout={jest.fn()} />);
    await waitFor(() => expect(capturedOnReorder).not.toBeNull());
    await waitFor(() => expect(names()).toEqual(["alpha", "beta", "gamma"]));

    await act(async () => { capturedOnReorder!([3, 1, 2]); });

    await waitFor(() =>
      expect(updateProjectOrder as jest.Mock).toHaveBeenCalledWith("alice", [3, 1, 2]),
    );
  });

  test("a failed save rolls the order back and surfaces the error", async () => {
    (updateProjectOrder as jest.Mock).mockRejectedValue({
      response: { data: { detail: "Order rejected" } },
    });

    render(<ProjectMgmt userDetails={userDetails} onLogout={jest.fn()} />);
    await waitFor(() => expect(capturedOnReorder).not.toBeNull());
    await waitFor(() => expect(names()).toEqual(["alpha", "beta", "gamma"]));

    await act(async () => { capturedOnReorder!([3, 1, 2]); });

    await waitFor(() => expect(names()).toEqual(["alpha", "beta", "gamma"]));
    await waitFor(() => expect(capturedReorderError).toBe("Order rejected"));
  });

  test("the backend response is treated as canonical", async () => {
    // Backend disagrees with the optimistic guess; its answer wins.
    (updateProjectOrder as jest.Mock).mockResolvedValue([2, 3, 1]);

    render(<ProjectMgmt userDetails={userDetails} onLogout={jest.fn()} />);
    await waitFor(() => expect(capturedOnReorder).not.toBeNull());
    await waitFor(() => expect(names()).toEqual(["alpha", "beta", "gamma"]));

    await act(async () => { capturedOnReorder!([3, 1, 2]); });

    await waitFor(() => expect(names()).toEqual(["beta", "gamma", "alpha"]));
  });

  test("a stale in-flight save cannot clobber a newer arrangement", async () => {
    let resolveFirst!: (v: number[]) => void;
    (updateProjectOrder as jest.Mock)
      .mockReturnValueOnce(new Promise<number[]>((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValueOnce([2, 1, 3]);

    render(<ProjectMgmt userDetails={userDetails} onLogout={jest.fn()} />);
    await waitFor(() => expect(capturedOnReorder).not.toBeNull());
    await waitFor(() => expect(names()).toEqual(["alpha", "beta", "gamma"]));

    await act(async () => { capturedOnReorder!([3, 1, 2]); });
    await act(async () => { capturedOnReorder!([2, 1, 3]); });
    await waitFor(() => expect(names()).toEqual(["beta", "alpha", "gamma"]));

    // The first, slower save lands last and must be ignored.
    await act(async () => { resolveFirst([3, 1, 2]); });

    expect(names()).toEqual(["beta", "alpha", "gamma"]);
  });
});
