import {
  handleSaveProject,
  handleSaveProjectWithModal,
  handleUpdateGitHub,
  type HandleUpdateGitHubParams,
  type SaveProjectWithModalParams,
} from "./handlers";
import { saveProject } from "./projects";
import { updateWorkflows } from "./workflows";
import { createSecrets } from "./secrets";
import { createEnvironment } from "./environments";

import type { MockedFunction } from 'vitest';
vi.mock("./projects", () => ({
  saveProject: vi.fn(),
  fetchProjects: vi.fn().mockResolvedValue([]),
  loadProject: vi.fn(),
}));
vi.mock("./workflows", () => ({ updateWorkflows: vi.fn() }));
vi.mock("./secrets", () => ({ createSecrets: vi.fn() }));
vi.mock("./envVars", () => ({ updateEnvVars: vi.fn() }));
vi.mock("./environments", () => ({ createEnvironment: vi.fn() }));
vi.mock("../utils/toast", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const mockedSaveProject = saveProject as MockedFunction<typeof saveProject>;
const mockedUpdateWorkflows = updateWorkflows as MockedFunction<typeof updateWorkflows>;
const mockedCreateSecrets = createSecrets as MockedFunction<typeof createSecrets>;
const mockedCreateEnvironment = createEnvironment as MockedFunction<typeof createEnvironment>;

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, "log").mockImplementation(() => undefined);
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  vi.spyOn(console, "warn").mockImplementation(() => undefined);
});

afterEach(() => vi.restoreAllMocks());

// ── handleSaveProject ─────────────────────────────────────────────────────────

describe("handleSaveProject", () => {
  const callWith = (overrides: Record<string, unknown> = {}) =>
    handleSaveProject(
      (overrides.user as string) ?? "testuser",
      (overrides.projectName as string) ?? "My Project",
      (overrides.selectedRepos as string[]) ?? ["org/repo1"],
      [],
      [],
      null,
      null,
      "",
      "default",
      30,
      null
    );

  it("returns error for empty project name", async () => {
    const result = await callWith({ projectName: "" });
    expect(result).toEqual({ success: false, error: "Enter a valid project name." });
  });

  it("returns error for whitespace-only project name", async () => {
    const result = await callWith({ projectName: "   " });
    expect(result).toEqual({ success: false, error: "Enter a valid project name." });
  });

  it("returns error for empty repos array", async () => {
    const result = await callWith({ selectedRepos: [] });
    expect(result).toEqual({ success: false, error: "Please select at least one repository." });
  });

  it("calls saveProject with correct payload and returns success", async () => {
    mockedSaveProject.mockResolvedValueOnce({ project_code: "PRJ1", project_id: "42" });

    const result = await callWith();

    expect(mockedSaveProject).toHaveBeenCalledWith(
      expect.objectContaining({
        github_user: "testuser",
        project_name: "My Project",
        selected_repos: ["org/repo1"],
      })
    );
    expect(result).toEqual(
      expect.objectContaining({ success: true, projectId: "42", projectCode: "PRJ1" })
    );
  });

  it("returns failure when saveProject response is missing project_code", async () => {
    mockedSaveProject.mockResolvedValueOnce({ project_id: "42" } as never);

    const result = await callWith();
    expect(result.success).toBe(false);
  });

  it("maps Repository objects to full_name strings in payload", async () => {
    mockedSaveProject.mockResolvedValueOnce({ project_code: "PRJ1", project_id: "1" });

    await handleSaveProject(
      "user", "Proj",
      [{ full_name: "org/repo-obj", name: "repo-obj" }],
      [], [], null, null, "", "default", 30, null
    );

    expect(mockedSaveProject).toHaveBeenCalledWith(
      expect.objectContaining({ selected_repos: ["org/repo-obj"] })
    );
  });

  it("filters out workflows when selectedItems.workflows is false", async () => {
    mockedSaveProject.mockResolvedValueOnce({ project_code: "PRJ1", project_id: "1" });

    await handleSaveProject(
      "user", "Proj", ["org/repo1"],
      [{ name: "ci.yml", content: "name: CI" }],
      [],
      null, null, "", "default", 30, null,
      false,
      { workflows: false, rxworkflows: true }
    );

    expect(mockedSaveProject).toHaveBeenCalledWith(
      expect.objectContaining({ workflows: [] })
    );
  });
});

// ── handleUpdateGitHub ────────────────────────────────────────────────────────

describe("handleUpdateGitHub", () => {
  const base: HandleUpdateGitHubParams = {
    user: "testuser",
    selectedRepos: ["org/repo1"] as string[],
    workflows: [],
    rxworkflows: [],
    envVars: [],
    manualEnvVars: [],
    secrets: [],
    manualSecrets: [],
    deploymentEnvironments: [],
    regexPattern: "",
    branchOption: "default",
    branchMaxAgeDays: 30,
    projectName: "My Project",
    setIsCreatingProject: null,
    setProjects: null,
    projectId: null,
    skipProjectSave: true,
  };

  it("returns failure when selectedRepos is empty", async () => {
    const result = await handleUpdateGitHub({ ...base, selectedRepos: [] });
    expect(result.success).toBe(false);
  });

  it("calls updateWorkflows for modified workflows", async () => {
    mockedUpdateWorkflows.mockResolvedValueOnce({ results: { "org/repo1": 200 } });

    const result = await handleUpdateGitHub({
      ...base,
      workflows: [{ name: "ci.yml", content: "name: CI", isModified: true }],
    });

    expect(mockedUpdateWorkflows).toHaveBeenCalledWith(
      "testuser",
      ["org/repo1"],
      [expect.objectContaining({ name: "ci.yml" })],
      [],
      "",
      "default",
      "My Project"
    );
    expect(result.success).toBe(true);
  });

  it("skips updateWorkflows when no workflows are modified", async () => {
    await handleUpdateGitHub({
      ...base,
      workflows: [{ name: "ci.yml", content: "name: CI" }],
    });

    expect(mockedUpdateWorkflows).not.toHaveBeenCalled();
  });

  it("calls createSecrets when manualSecrets has valid entries", async () => {
    mockedCreateSecrets.mockResolvedValueOnce({});

    await handleUpdateGitHub({
      ...base,
      manualSecrets: [{ key: "TOKEN", value: "secret123" }],
      selectedItems: { secrets: true },
    });

    expect(mockedCreateSecrets).toHaveBeenCalled();
  });

  it("calls createEnvironment for each deployment environment", async () => {
    mockedCreateEnvironment.mockResolvedValue({ created: true } as never);

    await handleUpdateGitHub({
      ...base,
      deploymentEnvironments: ["production"],
      selectedItems: { deploymentEnvironments: true },
    });

    expect(mockedCreateEnvironment).toHaveBeenCalledWith("testuser", "org/repo1", "production");
  });

  it("calls onProgress at key stages", async () => {
    const onProgress = vi.fn();

    await handleUpdateGitHub({ ...base, onProgress });

    expect(onProgress).toHaveBeenCalledWith(expect.any(Number), expect.any(String));
  });
});

// ── handleSaveProjectWithModal ────────────────────────────────────────────────

describe("handleSaveProjectWithModal", () => {
  const base: SaveProjectWithModalParams = {
    user: "testuser",
    projectName: "My Project",
    selectedRepos: ["org/repo1"] as string[],
    workflows: [],
    rxworkflows: [],
    envVars: [],
    manualEnvVars: [],
    secrets: [],
    manualSecrets: [],
    deploymentEnvironments: [],
    branchRegex: "",
    branchOption: "default",
    branchMaxAgeDays: 30,
    projectId: null,
    selectedItems: null,
    updateGitHub: false,
  };

  it("returns success after saving project without GitHub update", async () => {
    mockedSaveProject.mockResolvedValueOnce({ project_code: "PRJ1", project_id: "42" });

    const result = await handleSaveProjectWithModal(base);

    expect(result.success).toBe(true);
    expect(mockedUpdateWorkflows).not.toHaveBeenCalled();
  });

  it("returns failure when project save fails", async () => {
    mockedSaveProject.mockResolvedValueOnce({ project_id: "1" } as never);

    const result = await handleSaveProjectWithModal(base);
    expect(result.success).toBe(false);
  });

  it("calls updateWorkflows when updateGitHub is true and workflows are modified", async () => {
    mockedSaveProject.mockResolvedValueOnce({ project_code: "PRJ1", project_id: "42" });
    mockedUpdateWorkflows.mockResolvedValueOnce({ results: { "org/repo1": 200 } });

    const result = await handleSaveProjectWithModal({
      ...base,
      updateGitHub: true,
      workflows: [{ name: "ci.yml", content: "name: CI", isModified: true }],
    });

    expect(mockedUpdateWorkflows).toHaveBeenCalled();
    expect(result.success).toBe(true);
  });

  it("calls onProgress callback at key stages", async () => {
    const onProgress = vi.fn();
    mockedSaveProject.mockResolvedValueOnce({ project_code: "PRJ1", project_id: "42" });

    await handleSaveProjectWithModal({ ...base, onProgress });

    expect(onProgress).toHaveBeenCalledWith(expect.any(Number), expect.any(String));
  });
});
