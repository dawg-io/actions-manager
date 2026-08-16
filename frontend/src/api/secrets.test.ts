import axios from "axios";
import apiClient from "./apiClient";
import { createSecrets, getSecrets, deleteSecrets, syncSecret, getSecretsCount } from "./secrets";

import type { Mocked } from 'vitest';
vi.mock("./apiClient", () => ({
  __esModule: true,
  default: {
    post: vi.fn(),
    delete: vi.fn(),
  },
}));
vi.mock("../utils/toast", () => ({ toast: { error: vi.fn() } }));

const mockedApiClient = apiClient as Mocked<typeof apiClient>;
const mockedAxios = axios as Mocked<typeof axios>;

describe("secrets API", () => {
  beforeEach(() => vi.clearAllMocks());

  describe("createSecrets", () => {
    it("returns error and calls toast when user is missing", async () => {
      const { toast } = await import("../utils/toast");

      const result = await createSecrets(undefined, ["org/repo1"], [], "My Project");

      expect(result).toEqual({ error: "User and project name are required" });
      expect(toast.error).toHaveBeenCalled();
    });

    it("returns error when projectName is missing", async () => {
      const result = await createSecrets("user", ["org/repo1"], [], undefined);

      expect(result).toEqual({ error: "User and project name are required" });
    });

    it("posts secrets and calls setSecrets with refreshed data", async () => {
      const mockSetSecrets = vi.fn();
      mockedApiClient.post.mockResolvedValueOnce({ data: { results: "ok" } });
      mockedAxios.get.mockResolvedValueOnce({ data: { secrets: [{ secret_key: "TOKEN" }] } });

      const result = await createSecrets(
        "testuser",
        ["org/repo1"],
        [{ key: "TOKEN", value: "abc" }],
        "My Project",
        mockSetSecrets
      );

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        expect.stringContaining("/api/create-secrets"),
        expect.objectContaining({
          user: "testuser",
          repo_names: ["org/repo1"],
          project_name: "My Project",
        })
      );
      expect(mockSetSecrets).toHaveBeenCalledWith([{ secret_key: "TOKEN" }]);
      expect(result).toEqual({ results: "ok" });
    });

    it("maps Repository objects to full_name strings", async () => {
      mockedApiClient.post.mockResolvedValueOnce({ data: {} });
      mockedAxios.get.mockResolvedValueOnce({ data: { secrets: [] } });

      await createSecrets("user", [{ full_name: "org/repo1", name: "repo1" }], [], "proj");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ repo_names: ["org/repo1"] })
      );
    });

    it("returns error object on API failure", async () => {
      mockedApiClient.post.mockRejectedValueOnce(new Error("network error"));

      const result = await createSecrets("user", ["repo"], [], "proj");
      expect(result).toEqual({ error: "network error" });
    });
  });

  describe("getSecrets", () => {
    it("returns secrets array from API", async () => {
      mockedAxios.get.mockResolvedValueOnce({ data: { secrets: [{ secret_key: "TOKEN" }] } });

      const result = await getSecrets("testuser", "org/repo1", "My Project");

      expect(result).toEqual([{ secret_key: "TOKEN" }]);
    });

    it("returns empty array on API error", async () => {
      mockedAxios.get.mockRejectedValueOnce(new Error("network error"));

      const result = await getSecrets("user", "repo", "proj");
      expect(result).toEqual([]);
    });

    it("returns empty array when secrets is undefined in response", async () => {
      mockedAxios.get.mockResolvedValueOnce({ data: {} });

      const result = await getSecrets("user", "repo", "proj");
      expect(result).toEqual([]);
    });
  });

  describe("deleteSecrets", () => {
    it("calls toast.error and returns early when user is missing", async () => {
      const { toast } = await import("../utils/toast");

      await deleteSecrets(undefined, "proj", ["repo"], "KEY");

      expect(toast.error).toHaveBeenCalled();
      expect(mockedApiClient.delete).not.toHaveBeenCalled();
    });

    it("deletes secret and refreshes setSecrets", async () => {
      const mockSetSecrets = vi.fn();
      mockedApiClient.delete.mockResolvedValueOnce({ data: { results: "ok" } });
      mockedAxios.get.mockResolvedValueOnce({ data: { secrets: [] } });

      await deleteSecrets("testuser", "My Project", ["org/repo1"], "TOKEN", mockSetSecrets);

      expect(mockedApiClient.delete).toHaveBeenCalledWith(
        expect.stringContaining("/api/delete-secrets"),
        expect.objectContaining({
          data: expect.objectContaining({ user: "testuser", secret_name: "TOKEN" }),
        })
      );
      expect(mockSetSecrets).toHaveBeenCalledWith([]);
    });
  });

  describe("syncSecret", () => {
    it("posts to sync-secret endpoint", async () => {
      mockedApiClient.post.mockResolvedValueOnce({ data: { synced: true } });

      const result = await syncSecret("user", "proj", ["org/repo1"], "TOKEN");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        expect.stringContaining("/api/sync-secret"),
        expect.objectContaining({ secret_key: "TOKEN" })
      );
      expect(result).toEqual({ synced: true });
    });

    it("throws on error", async () => {
      mockedApiClient.post.mockRejectedValueOnce(new Error("failed"));

      await expect(syncSecret("user", "proj", ["repo"], "KEY")).rejects.toThrow("failed");
    });
  });

  describe("getSecretsCount", () => {
    it("returns the count of secrets", async () => {
      mockedAxios.get.mockResolvedValueOnce({ data: { count: 2 } });

      const result = await getSecretsCount("user", "proj", ["org/repo1", "org/repo2"]);
      expect(result).toBe(2);
    });

    it("returns 0 on error instead of throwing", async () => {
      mockedAxios.get.mockRejectedValueOnce(new Error("server error"));

      const result = await getSecretsCount("user", "proj", ["repo"]);
      expect(result).toBe(0);
    });
  });
});
