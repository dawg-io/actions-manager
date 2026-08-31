import axios from "axios";
import apiClient from "./apiClient";
import { getProjectDeletionSummary, deleteProjectEnhanced } from "./projectDeletion";

import type { Mocked } from "vitest";

vi.mock("./apiClient", () => ({
  __esModule: true,
  default: {
    get: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockedAxios = axios as Mocked<typeof axios>;
const mockedApiClient = apiClient as Mocked<typeof apiClient>;

describe("projectDeletion API", () => {
  beforeEach(() => vi.clearAllMocks());

  describe("getProjectDeletionSummary", () => {
    it("requests the summary for the given project and user", async () => {
      mockedApiClient.get.mockResolvedValueOnce({
        data: { project_name: "My Project", project_code: "MP", workflows: [] },
      });

      const result = await getProjectDeletionSummary("testuser", "My Project");

      expect(mockedApiClient.get).toHaveBeenCalledWith(
        expect.stringContaining("/api/projects/My%20Project/deletion-summary"),
        { params: { github_user: "testuser" } }
      );
      expect(result.project_code).toBe("MP");
    });

    it("encodes project names containing URL-significant characters", async () => {
      mockedApiClient.get.mockResolvedValueOnce({ data: {} });

      await getProjectDeletionSummary("testuser", "a/b?c&d");

      expect(mockedApiClient.get).toHaveBeenCalledWith(
        expect.stringContaining("/api/projects/a%2Fb%3Fc%26d/deletion-summary"),
        expect.any(Object)
      );
    });

    it("throws on API error", async () => {
      mockedApiClient.get.mockRejectedValueOnce(new Error("not found"));

      await expect(getProjectDeletionSummary("testuser", "My Project")).rejects.toThrow(
        "not found"
      );
    });

    // Regression: the endpoint calls assert_session_owns_user, so the request has
    // to carry the session cookie. Bare axios omits it cross-origin (the cloud
    // deployment serves the API from a different origin than the app), which made
    // the delete dialog fall back to "database only" for every project.
    it("goes through the credentialed client, never bare axios", async () => {
      mockedApiClient.get.mockResolvedValueOnce({ data: {} });

      await getProjectDeletionSummary("testuser", "My Project");

      expect(mockedApiClient.get).toHaveBeenCalledTimes(1);
      expect(mockedAxios.get).not.toHaveBeenCalled();
    });
  });

  describe("deleteProjectEnhanced", () => {
    it("keeps GitHub resources and removes deployment environments by default", async () => {
      mockedApiClient.delete.mockResolvedValueOnce({ data: { message: "done" } });

      await deleteProjectEnhanced("testuser", "My Project");

      expect(mockedApiClient.delete).toHaveBeenCalledWith(
        expect.stringContaining("/api/projects/My%20Project/enhanced"),
        {
          data: {
            github_user: "testuser",
            project_name: "My Project",
            delete_github_resources: false,
            delete_deployment_environments: true,
          },
        }
      );
    });

    it("forwards both flags when they are given explicitly", async () => {
      mockedApiClient.delete.mockResolvedValueOnce({ data: {} });

      await deleteProjectEnhanced("testuser", "My Project", true, false);

      expect(mockedApiClient.delete).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          data: expect.objectContaining({
            delete_github_resources: true,
            delete_deployment_environments: false,
          }),
        })
      );
    });

    it("returns the deletion details from the response", async () => {
      mockedApiClient.delete.mockResolvedValueOnce({
        data: {
          message: "✅ Project deletion completed",
          details: {
            project_deleted: true,
            github_resources_deleted: ["Repository Secret: FOO from org/repo"],
            errors: [],
          },
        },
      });

      const result = await deleteProjectEnhanced("testuser", "My Project", true);

      expect(result.details?.project_deleted).toBe(true);
      expect(result.details?.github_resources_deleted).toEqual([
        "Repository Secret: FOO from org/repo",
      ]);
    });

    it("throws on API error", async () => {
      mockedApiClient.delete.mockRejectedValueOnce(new Error("forbidden"));

      await expect(deleteProjectEnhanced("testuser", "My Project")).rejects.toThrow("forbidden");
    });
  });
});
