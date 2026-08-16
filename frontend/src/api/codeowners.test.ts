import apiClient from "./apiClient";
import { getCodeowners, saveCodeownersDraft, getCodeownersDrift, deployCodeowners } from "./codeowners";

import type { Mocked } from 'vitest';
vi.mock("./apiClient", () => ({
  __esModule: true,
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const mockedApiClient = apiClient as Mocked<typeof apiClient>;

describe("codeowners API", () => {
  beforeEach(() => vi.clearAllMocks());

  describe("getCodeowners", () => {
    it("fetches from the correct endpoint with params", async () => {
      mockedApiClient.get.mockResolvedValueOnce({ data: { success: true, github: { exists: true } } });

      const result = await getCodeowners("org/repo1", "testuser", "My Project");

      expect(mockedApiClient.get).toHaveBeenCalledWith(
        "/api/repos/org/repo1/codeowners",
        { params: { github_user: "testuser", project_name: "My Project" } }
      );
      expect(result.success).toBe(true);
    });

    it("uses numeric repo id directly without encoding", async () => {
      mockedApiClient.get.mockResolvedValueOnce({ data: { success: true } });

      await getCodeowners(42, "testuser", "My Project");

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/repos/42/codeowners", expect.any(Object));
    });
  });

  describe("saveCodeownersDraft", () => {
    it("posts content to the correct endpoint", async () => {
      mockedApiClient.post.mockResolvedValueOnce({ data: { success: true, message: "Saved" } });

      const result = await saveCodeownersDraft("org/repo1", "testuser", "My Project", "* @owner");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/repos/org/repo1/codeowners",
        expect.objectContaining({ content: "* @owner", github_user: "testuser" })
      );
      expect(result.success).toBe(true);
    });

    it("uses default file path when not specified", async () => {
      mockedApiClient.post.mockResolvedValueOnce({ data: { success: true } });

      await saveCodeownersDraft("org/repo1", "user", "proj", "* @me");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ file_path: ".github/CODEOWNERS" })
      );
    });
  });

  describe("getCodeownersDrift", () => {
    it("fetches drift status from the correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValueOnce({ data: { success: true, has_drift: false, drift_status: "synced" } });

      const result = await getCodeownersDrift("org/repo1", "testuser", "My Project");

      expect(mockedApiClient.get).toHaveBeenCalledWith(
        "/api/repos/org/repo1/codeowners/drift",
        expect.any(Object)
      );
      expect(result.has_drift).toBe(false);
    });
  });

  describe("deployCodeowners", () => {
    it("posts to deploy endpoint with direct mode by default", async () => {
      mockedApiClient.post.mockResolvedValueOnce({ data: { success: true, mode: "direct" } });

      const result = await deployCodeowners("org/repo1", "testuser", "My Project");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/repos/org/repo1/codeowners/deploy",
        expect.objectContaining({ mode: "direct", github_user: "testuser" })
      );
      expect(result.success).toBe(true);
    });

    it("passes pr mode when specified in options", async () => {
      mockedApiClient.post.mockResolvedValueOnce({ data: { success: true, mode: "pr" } });

      await deployCodeowners("org/repo1", "testuser", "My Project", { mode: "pr" });

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ mode: "pr" })
      );
    });
  });
});
