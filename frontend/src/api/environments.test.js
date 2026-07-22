import axios from "axios";
import apiClient from "./apiClient";
import {
  createEnvironment,
  getEnvironments,
  deleteDeploymentEnvironment,
  syncEnvironment,
  getEnvironmentsCount,
} from "./environments";

vi.mock("./apiClient", () => ({
  __esModule: true,
  default: {
    post: jest.fn(),
    delete: jest.fn(),
  },
}));

const mockedAxios = /** @type {jest.Mocked<typeof axios>} */ (axios);

describe("environments API", () => {
  beforeEach(() => jest.clearAllMocks());

  describe("createEnvironment", () => {
    it("posts to create-environment and returns data", async () => {
      apiClient.post.mockResolvedValueOnce({ data: { created: true } });

      const result = await createEnvironment("testuser", "org/repo1", "production");

      expect(apiClient.post).toHaveBeenCalledWith(
        expect.stringContaining("/api/create-environment"),
        { user: "testuser", repo_name: "org/repo1", environment_name: "production" }
      );
      expect(result.created).toBe(true);
    });

    it("throws on API error", async () => {
      apiClient.post.mockRejectedValueOnce(new Error("network error"));

      await expect(createEnvironment("user", "repo", "env")).rejects.toThrow("network error");
    });
  });

  describe("getEnvironments", () => {
    it("fetches environments via axios and returns the list", async () => {
      mockedAxios.get.mockResolvedValueOnce({ data: { environments: ["production", "staging"] } });

      const result = await getEnvironments("testuser", "org/repo1");

      expect(result).toEqual(["production", "staging"]);
    });

    it("throws on API error", async () => {
      mockedAxios.get.mockRejectedValueOnce(new Error("not found"));

      await expect(getEnvironments("user", "repo")).rejects.toThrow("not found");
    });
  });

  describe("deleteDeploymentEnvironment", () => {
    it("sends delete request with correct payload", async () => {
      apiClient.delete.mockResolvedValueOnce({ data: { deleted: true } });

      const result = await deleteDeploymentEnvironment("testuser", ["org/repo1"], "production");

      expect(apiClient.delete).toHaveBeenCalledWith(
        expect.stringContaining("/api/delete-environment"),
        { data: { user: "testuser", repo_names: ["org/repo1"], environment_name: "production" } }
      );
      expect(result.deleted).toBe(true);
    });

    it("throws on API error", async () => {
      apiClient.delete.mockRejectedValueOnce(new Error("forbidden"));

      await expect(deleteDeploymentEnvironment("user", ["repo"], "env")).rejects.toThrow("forbidden");
    });
  });

  describe("syncEnvironment", () => {
    it("posts to sync-environment endpoint", async () => {
      apiClient.post.mockResolvedValueOnce({ data: { synced: true } });

      const result = await syncEnvironment("testuser", "My Project", ["org/repo1"], "production");

      expect(apiClient.post).toHaveBeenCalledWith(
        expect.stringContaining("/api/sync-environment"),
        expect.objectContaining({ user: "testuser", environment_name: "production" })
      );
      expect(result.synced).toBe(true);
    });

    it("throws on API error", async () => {
      apiClient.post.mockRejectedValueOnce(new Error("failed"));

      await expect(syncEnvironment("user", "proj", ["repo"], "env")).rejects.toThrow("failed");
    });
  });

  describe("getEnvironmentsCount", () => {
    it("returns the count of environments", async () => {
      mockedAxios.get.mockResolvedValueOnce({ data: { count: 3 } });

      const result = await getEnvironmentsCount("testuser", ["org/repo1", "org/repo2"]);

      expect(result).toBe(3);
    });

    it("returns 0 on error instead of throwing", async () => {
      mockedAxios.get.mockRejectedValueOnce(new Error("server error"));

      const result = await getEnvironmentsCount("testuser", ["org/repo1"]);
      expect(result).toBe(0);
    });
  });
});
