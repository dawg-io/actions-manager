/**
 * Adding a repository to an existing project prompts for delivery.
 *
 * Attaching a repo used to be a silent no-op: _process_project_repos inserts
 * the join row and nothing else, so the project's workflows sat undelivered in
 * the new repo with nothing in the UI saying so. (They are correctly *not*
 * reported as drift - see backend _delivery_confirmed_on_branch - which is why
 * the gap was invisible.) The save now asks how to deliver them, and "Create
 * pull requests" hands off to the existing campaign modal scoped to just the
 * new repos.
 *
 * The prompt fires *after* the save resolves, because create_pull_requests
 * intersects selected_repos with the project's own repos - a repo with no
 * ProjectRepo row yet would be filtered out and 400.
 */
import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";

const mockNavigate = vi.fn();
const mockUseParams = vi.fn();

// Captured so tests can drive the section nav and the repo selection the way a
// user would, without rendering the real Sidebar / picker trees.
let capturedOnSectionChange: ((section: string) => void) | null = null;
let capturedSetSelectedRepos: ((repos: string[]) => void) | null = null;
let capturedPRModalProps: any = null;
// The badge/notice inputs, so a save can be asserted to update them in place.
let capturedPendingDeliveryRepos: string[] | undefined;
let capturedSidebarPendingCount: number | undefined;

vi.mock("react-router", () => ({
  useNavigate: () => mockNavigate,
  useParams: () => mockUseParams(),
  Link: function Link(props: any) {
    return <a href={props.to}>{props.children}</a>;
  },
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
  updateProjectDriftConfig: vi.fn(),
  updateProjectOrder: vi.fn(),
  exportProjectBackup: vi.fn(),
  linkReusableWorkflow: vi.fn(),
  unlinkReusableWorkflow: vi.fn(),
}));

vi.mock("./api/driftSettings", () => ({
  fetchDriftSettings: vi.fn().mockResolvedValue({ recheck_interval_minutes: 30 }),
  formatDriftInterval: () => "every 30 minutes",
  DEFAULT_DRIFT_SETTINGS: { recheck_interval_minutes: 30 },
  DRIFT_INTERVAL_OPTIONS: [],
}));

vi.mock("./api/projectDeletion", () => ({ deleteProjectEnhanced: vi.fn() }));
vi.mock("./api/handlers", () => ({ handleSaveProjectWithModal: vi.fn() }));
vi.mock("./api/secrets", () => ({ getSecrets: vi.fn() }));
vi.mock("./api/envVars", () => ({ getEnvVars: vi.fn() }));
vi.mock("./api/pullRequests", () => ({ getProjectPRStatus: vi.fn() }));
vi.mock("./api/actionsProjects", () => ({ listActionsProjects: vi.fn().mockResolvedValue([]) }));
vi.mock("./api/actionGroups", () => ({ listActionGroups: vi.fn().mockResolvedValue([]) }));
vi.mock("./api/codeowners", () => ({
  getProjectCodeownersStatuses: vi.fn().mockResolvedValue({ statuses: [] }),
}));

vi.mock("./components/Sidebar", () => ({
  default: function Sidebar(props: any) {
    capturedOnSectionChange = props.onSectionChange;
    capturedSidebarPendingCount = props.pendingDeliveryCount;
    return <div data-testid="sidebar" />;
  },
}));

vi.mock("./components/RepositoriesAndBranches", () => ({
  default: function RepositoriesAndBranches(props: any) {
    capturedSetSelectedRepos = props.setSelectedRepos;
    capturedPendingDeliveryRepos = props.pendingDeliveryRepos;
    return <div data-testid="repositories-and-branches" />;
  },
}));

// Captures the props the campaign modal is opened with, so tests can assert on
// the repo scope without driving the real 1100-line modal.
vi.mock("./components/CreatePRModal", () => ({
  default: function CreatePRModal(props: any) {
    capturedPRModalProps = props;
    return <div data-testid="create-pr-modal" />;
  },
}));

vi.mock("./components/ProjectList", () => ({
  default: function ProjectList() {
    return <div data-testid="project-list" />;
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

vi.mock("./components/BuildMetricsPanel", () => ({
  default: function BuildMetricsPanel() {
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

vi.mock("./components/WorkflowImportPanel", () => ({
  WorkflowImportPanel: function WorkflowImportPanel() {
    return null;
  },
}));

import ProjectMgmt, { reposAddedSinceSnapshot } from "./ProjectMgmt";
import { fetchProjects, loadProject } from "./api/projects";
import { getSecrets } from "./api/secrets";
import { getEnvVars } from "./api/envVars";
import { getProjectPRStatus } from "./api/pullRequests";
import { handleSaveProjectWithModal } from "./api/handlers";

import type { Mock } from "vitest";

const userDetails = {
  avatar_url: "https://example.com/avatar.png",
  github_user: "alice",
  account_type: "free",
  github_account_type: "User" as const,
};

const SAVED_REPO = "acme/existing";
const NEW_REPO = "acme/added";

const CI_WORKFLOW = {
  name: "ci",
  content: "name: CI\n",
  workflow_status: "synced_with_github",
};

function projectPayload(overrides: Record<string, unknown> = {}) {
  return {
    project_name: "proj-a",
    project_id: 42,
    project_code: "PROJA",
    selected_repos: [SAVED_REPO],
    workflows: [CI_WORKFLOW],
    rxworkflows: [],
    branch_regex: "",
    branch_option: "default",
    branch_max_age_days: 30,
    reusable_workflows_enabled: false,
    use_prefix: false,
    project_type: "standard",
    pr_state: "synced",
    ...overrides,
  };
}

/** Render, land on Repositories & Branches, and wait for the Save button. */
async function openRepoSection() {
  render(<ProjectMgmt userDetails={userDetails} onLogout={vi.fn()} />);
  await waitFor(() => expect(capturedOnSectionChange).not.toBeNull());
  act(() => capturedOnSectionChange!("repos-and-branches"));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /Save/ })).toBeInTheDocument(),
  );
}

/** Replace the selected repos, then press the section's local Save button. */
async function setReposAndSave(repos: string[]) {
  await waitFor(() => expect(capturedSetSelectedRepos).not.toBeNull());
  act(() => capturedSetSelectedRepos!(repos));
  const save = await screen.findByRole("button", { name: /💾 Save/ });
  await waitFor(() => expect(save).toBeEnabled());
  await userEvent.click(save);
}

const promptTitle = /Deliver this project's workflows to the new repositor/;

describe("reposAddedSinceSnapshot", () => {
  test("returns only repos absent from the snapshot", () => {
    expect(
      reposAddedSinceSnapshot([SAVED_REPO, NEW_REPO], { selectedRepos: [SAVED_REPO] }),
    ).toEqual([NEW_REPO]);
  });

  test("a removal is not an addition", () => {
    expect(
      reposAddedSinceSnapshot([SAVED_REPO], { selectedRepos: [SAVED_REPO, NEW_REPO] }),
    ).toEqual([]);
  });

  test("no snapshot means nothing is known to be new", () => {
    expect(reposAddedSinceSnapshot([SAVED_REPO], null)).toEqual([]);
  });
});

describe("ProjectMgmt – delivery prompt when a repository is added", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnSectionChange = null;
    capturedSetSelectedRepos = null;
    capturedPRModalProps = null;
    capturedPendingDeliveryRepos = undefined;
    capturedSidebarPendingCount = undefined;

    mockUseParams.mockReturnValue({ user: "alice", projectName: "proj-a" });
    (fetchProjects as Mock).mockResolvedValue([
      { project_id: 42, project_name: "proj-a", project_code: "PROJA" },
    ]);
    (loadProject as Mock).mockResolvedValue(projectPayload());
    (getSecrets as Mock).mockResolvedValue([]);
    (getEnvVars as Mock).mockResolvedValue([]);
    (getProjectPRStatus as Mock).mockResolvedValue({
      project_state: "synced",
      open_prs: 0,
      merged_prs: 0,
      total_prs: 0,
    });
    (handleSaveProjectWithModal as Mock).mockResolvedValue({
      success: true,
      results: ["ok"],
      projectId: 42,
      projectCode: "PROJA",
      prState: "synced",
    });
  });

  test("adding a repo and saving prompts, naming only the added repo", async () => {
    await openRepoSection();
    await setReposAndSave([SAVED_REPO, NEW_REPO]);

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(promptTitle);
    expect(dialog).toHaveTextContent(NEW_REPO);
    expect(dialog).not.toHaveTextContent(SAVED_REPO);
  });

  test("the reminder appears from the save response, with no page refresh", async () => {
    // Regression: the reminder used to come only from loadProject, so after
    // saving a newly added repo the badge, notice and sidebar count stayed
    // empty until the user manually refreshed. CLAUDE.md's UI-state-after-
    // mutations rule: the save response has to update it in place.
    (handleSaveProjectWithModal as Mock).mockResolvedValue({
      success: true,
      results: ["ok"],
      projectId: 42,
      projectCode: "PROJA",
      prState: "synced",
      pendingDeliveryRepos: [NEW_REPO],
    });

    await openRepoSection();
    expect(capturedPendingDeliveryRepos).toEqual([]);
    expect(capturedSidebarPendingCount).toBe(0);

    await setReposAndSave([SAVED_REPO, NEW_REPO]);

    // No reload, no second loadProject — the save response alone.
    await waitFor(() => expect(capturedPendingDeliveryRepos).toEqual([NEW_REPO]));
    expect(capturedSidebarPendingCount).toBe(1);
    expect(loadProject).toHaveBeenCalledTimes(1);
  });

  test("a save that clears the last waiting repo removes the reminder", async () => {
    (loadProject as Mock).mockResolvedValue(
      projectPayload({
        selected_repos: [SAVED_REPO, NEW_REPO],
        pending_delivery_repos: [NEW_REPO],
      }),
    );
    (handleSaveProjectWithModal as Mock).mockResolvedValue({
      success: true,
      results: ["ok"],
      projectId: 42,
      projectCode: "PROJA",
      prState: "synced",
      pendingDeliveryRepos: [],
    });

    await openRepoSection();
    await waitFor(() => expect(capturedSidebarPendingCount).toBe(1));

    await setReposAndSave([SAVED_REPO, NEW_REPO, "acme/third"]);

    await waitFor(() => expect(capturedPendingDeliveryRepos).toEqual([]));
    expect(capturedSidebarPendingCount).toBe(0);
  });

  test("no prompt for a re-added repo the server says is already delivered", async () => {
    // Review finding: "just added" is not "waiting". Removing a repo leaves its
    // delivery history behind, so a re-added repo can already hold the
    // workflows — and the prompt used to claim otherwise while the reminder on
    // the same screen correctly showed nothing.
    (handleSaveProjectWithModal as Mock).mockResolvedValue({
      success: true,
      results: ["ok"],
      projectId: 42,
      projectCode: "PROJA",
      prState: "synced",
      pendingDeliveryRepos: [],
      pendingDeliveryKnown: true,
    });

    await openRepoSection();
    await setReposAndSave([SAVED_REPO, NEW_REPO]);

    await waitFor(() => expect(handleSaveProjectWithModal).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(capturedPendingDeliveryRepos).toEqual([]);
  });

  test("still prompts when the server could not tell", async () => {
    // A project that has never been drift-checked answers [] either way.
    // Reading that as "nothing waiting" would silence the prompt entirely for
    // every new project — the case the feature exists for.
    (handleSaveProjectWithModal as Mock).mockResolvedValue({
      success: true,
      results: ["ok"],
      projectId: 42,
      projectCode: "PROJA",
      prState: "synced",
      pendingDeliveryRepos: [],
      pendingDeliveryKnown: false,
    });

    await openRepoSection();
    await setReposAndSave([SAVED_REPO, NEW_REPO]);

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(NEW_REPO);
  });

  test("a campaign clears only the repos the user left ticked", async () => {
    // Review finding: keying the clear on what the modal was *offered* dropped
    // the badge for a repo the user unticked, which gets no PR and is still
    // genuinely waiting.
    (loadProject as Mock).mockResolvedValue(
      projectPayload({
        selected_repos: [SAVED_REPO, NEW_REPO],
        pending_delivery_repos: [SAVED_REPO, NEW_REPO],
      }),
    );

    await openRepoSection();
    await waitFor(() =>
      expect(capturedPendingDeliveryRepos).toEqual([SAVED_REPO, NEW_REPO]),
    );

    // Reached from the reminder itself, which is how a user gets here.
    await userEvent.click(
      await screen.findByTestId("pending-delivery-create-pr-button"),
    );
    await waitFor(() => expect(screen.getByTestId("create-pr-modal")).toBeInTheDocument());

    // The user unticked SAVED_REPO in the modal, so only NEW_REPO gets a PR.
    act(() => capturedPRModalProps.onSuccess([], [], [], [], [NEW_REPO]));

    await waitFor(() => expect(capturedPendingDeliveryRepos).toEqual([SAVED_REPO]));
  });

  test("saving without adding a repo does not prompt", async () => {
    await openRepoSection();
    // Branch-config-only edits leave the repo set untouched. Re-setting the
    // same list still marks the section dirty enough to save.
    await waitFor(() => expect(capturedSetSelectedRepos).not.toBeNull());
    act(() => capturedSetSelectedRepos!([SAVED_REPO, NEW_REPO]));
    act(() => capturedSetSelectedRepos!([SAVED_REPO]));
    const save = screen.getByRole("button", { name: /💾 Save/ });
    if (!(save as HTMLButtonElement).disabled) {
      await userEvent.click(save);
    }

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("removing a repo does not prompt", async () => {
    (loadProject as Mock).mockResolvedValue(
      projectPayload({ selected_repos: [SAVED_REPO, NEW_REPO] }),
    );
    await openRepoSection();
    await setReposAndSave([SAVED_REPO]);

    await waitFor(() => expect(handleSaveProjectWithModal).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("a repo removed then re-added before saving is not treated as new", async () => {
    (loadProject as Mock).mockResolvedValue(
      projectPayload({ selected_repos: [SAVED_REPO, NEW_REPO] }),
    );
    await openRepoSection();
    await waitFor(() => expect(capturedSetSelectedRepos).not.toBeNull());
    act(() => capturedSetSelectedRepos!([SAVED_REPO]));
    act(() => capturedSetSelectedRepos!([SAVED_REPO, NEW_REPO]));

    const save = screen.getByRole("button", { name: /💾 Save/ });
    if (!(save as HTMLButtonElement).disabled) {
      await userEvent.click(save);
    }
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("a project with no workflows does not prompt", async () => {
    (loadProject as Mock).mockResolvedValue(projectPayload({ workflows: [] }));
    await openRepoSection();
    await setReposAndSave([SAVED_REPO, NEW_REPO]);

    await waitFor(() => expect(handleSaveProjectWithModal).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("a failed save does not prompt", async () => {
    (handleSaveProjectWithModal as Mock).mockResolvedValue({
      success: false,
      results: ["❌ Save failed: boom"],
    });
    await openRepoSection();
    await setReposAndSave([SAVED_REPO, NEW_REPO]);

    await waitFor(() => expect(handleSaveProjectWithModal).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("'Save locally only' dismisses without opening a campaign", async () => {
    await openRepoSection();
    await setReposAndSave([SAVED_REPO, NEW_REPO]);
    await screen.findByRole("dialog");

    await userEvent.click(screen.getByRole("button", { name: "Save locally only" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByTestId("create-pr-modal")).not.toBeInTheDocument();
  });

  test("'Create pull requests' opens the campaign scoped to the new repo only", async () => {
    await openRepoSection();
    await setReposAndSave([SAVED_REPO, NEW_REPO]);
    await screen.findByRole("dialog");

    await userEvent.click(screen.getByRole("button", { name: "Create pull requests" }));

    await waitFor(() => expect(screen.getByTestId("create-pr-modal")).toBeInTheDocument());
    expect(capturedPRModalProps.repositories).toEqual([{ name: NEW_REPO }]);
    // A new repo holds none of the workflows, so "changed only" would under-deliver.
    expect(capturedPRModalProps.preselectAllWorkflows).toBe(true);
  });

  test("closing a scoped campaign widens the next one back to every repo", async () => {
    // The header button only renders in a workflow section, and only enables
    // while the project is a draft.
    (loadProject as Mock).mockResolvedValue(projectPayload({ pr_state: "draft" }));
    (handleSaveProjectWithModal as Mock).mockResolvedValue({
      success: true,
      results: ["ok"],
      projectId: 42,
      projectCode: "PROJA",
      prState: "draft",
    });

    await openRepoSection();
    await setReposAndSave([SAVED_REPO, NEW_REPO]);
    await screen.findByRole("dialog");
    await userEvent.click(screen.getByRole("button", { name: "Create pull requests" }));
    await waitFor(() => expect(screen.getByTestId("create-pr-modal")).toBeInTheDocument());
    expect(capturedPRModalProps.repositories).toEqual([{ name: NEW_REPO }]);

    act(() => capturedPRModalProps.onClose());
    await waitFor(() =>
      expect(screen.queryByTestId("create-pr-modal")).not.toBeInTheDocument(),
    );

    // Re-open the way the header button does: the scope must have widened.
    act(() => capturedOnSectionChange!("workflows"));
    const headerButton = await screen.findByTestId("create-pull-requests-button");
    await waitFor(() => expect(headerButton).toBeEnabled());
    await userEvent.click(headerButton);

    await waitFor(() => expect(screen.getByTestId("create-pr-modal")).toBeInTheDocument());
    expect(capturedPRModalProps.repositories).toEqual([
      { name: SAVED_REPO },
      { name: NEW_REPO },
    ]);
    expect(capturedPRModalProps.preselectAllWorkflows).toBe(false);
  });
});
