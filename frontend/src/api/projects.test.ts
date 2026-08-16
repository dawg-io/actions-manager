import apiClient from "./apiClient";
import { saveProject, updateProjectColor, updateProjectName } from "./projects";
import config from "../config";

import type { Mocked } from 'vitest';
vi.mock("./apiClient", () => ({
  __esModule: true,
  default: {
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
  },
}));

const mockedApiClient = apiClient as Mocked<typeof apiClient>;

describe("projects API", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, "log").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const baseProjectData = {
    project_name: "Visibility Project",
    selected_repos: ["whatsupdawg/ptest1"],
    workflows: [],
    rxworkflows: [],
    github_user: "whatsupdawg",
    branch_regex: "",
    branch_option: "default",
    branch_max_age_days: 30,
    reusable_workflows_enabled: false,
    use_prefix: false,
    project_type: "standard" as const,
  };

  it("serializes private repository visibility when creating a project", async () => {
    mockedApiClient.post.mockResolvedValueOnce({
      data: { project_code: "VIS1", project_id: "1" },
    });

    await saveProject({
      ...baseProjectData,
      repository_visibility_scope: "private",
    });

    expect(mockedApiClient.post).toHaveBeenCalledWith(
      `${config.BACKEND_URL}/api/projects/`,
      expect.objectContaining({
        project_name: "Visibility Project",
        selected_repos: ["whatsupdawg/ptest1"],
        repository_visibility_scope: "private",
      }),
    );
  });

  it("defaults repository visibility to public for backward-compatible callers", async () => {
    mockedApiClient.post.mockResolvedValueOnce({
      data: { project_code: "VIS2", project_id: "2" },
    });

    await saveProject(baseProjectData);

    expect(mockedApiClient.post).toHaveBeenCalledWith(
      `${config.BACKEND_URL}/api/projects/`,
      expect.objectContaining({
        repository_visibility_scope: "public",
      }),
    );
  });

  it("serializes repository visibility when updating a project", async () => {
    mockedApiClient.put.mockResolvedValueOnce({
      data: { project_code: "VIS3", project_id: "3" },
    });

    await saveProject({
      ...baseProjectData,
      project_id: "3",
      repository_visibility_scope: "private",
    });

    expect(mockedApiClient.put).toHaveBeenCalledWith(
      `${config.BACKEND_URL}/api/projects/3/`,
      expect.objectContaining({
        repository_visibility_scope: "private",
      }),
    );
  });

  it("does not default update calls that omit repository visibility to public", async () => {
    mockedApiClient.put.mockResolvedValueOnce({
      data: { project_code: "VIS4", project_id: "4" },
    });

    await saveProject({ ...baseProjectData, project_id: "4" });

    const payload = mockedApiClient.put.mock.calls[0][1];
    expect(payload).not.toHaveProperty("repository_visibility_scope");
  });

  it("serializes a custom project key when creating a project", async () => {
    mockedApiClient.post.mockResolvedValueOnce({
      data: { project_code: "CUSTOM", project_id: "5" },
    });

    await saveProject({
      ...baseProjectData,
      custom_project_key: "CUSTOM",
    });

    expect(mockedApiClient.post).toHaveBeenCalledWith(
      `${config.BACKEND_URL}/api/projects/`,
      expect.objectContaining({
        custom_project_key: "CUSTOM",
      }),
    );
  });

  it("serializes project_color when provided", async () => {
    mockedApiClient.post.mockResolvedValueOnce({
      data: { project_code: "CLR1", project_id: "6" },
    });

    await saveProject({
      ...baseProjectData,
      project_color: "orange",
    });

    expect(mockedApiClient.post).toHaveBeenCalledWith(
      `${config.BACKEND_URL}/api/projects/`,
      expect.objectContaining({
        project_color: "orange",
      }),
    );
  });

  it("does not send project_color on update calls that omit it", async () => {
    mockedApiClient.put.mockResolvedValueOnce({
      data: { project_code: "CLR2", project_id: "7" },
    });

    await saveProject({ ...baseProjectData, project_id: "7" });

    const payload = mockedApiClient.put.mock.calls[0][1];
    expect(payload).not.toHaveProperty("project_color");
  });

  it("patches project color with a minimal payload", async () => {
    mockedApiClient.patch.mockResolvedValueOnce({
      data: { project_id: 123, project_color: "rose" },
    });

    await updateProjectColor("whatsupdawg", 123, "rose");

    expect(mockedApiClient.patch).toHaveBeenCalledWith(
      `${config.BACKEND_URL}/api/projects/123/project-color`,
      { github_user: "whatsupdawg", project_color: "rose" },
    );
  });

  it("patches project name with a minimal payload", async () => {
    mockedApiClient.patch.mockResolvedValueOnce({
      data: { project_id: 42, project_name: "New Name", project_code: "NWN" },
    });

    await updateProjectName("whatsupdawg", 42, "New Name");

    expect(mockedApiClient.patch).toHaveBeenCalledWith(
      `${config.BACKEND_URL}/api/projects/42/project-name`,
      { github_user: "whatsupdawg", project_name: "New Name" },
    );
  });

  it("rethrows error when project name update fails", async () => {
    const err = new Error("Network error");
    mockedApiClient.patch.mockRejectedValueOnce(err);

    await expect(updateProjectName("user", 1, "Name")).rejects.toThrow("Network error");
  });
});
