import apiClient from "./apiClient";
import config from "../config";

const BACKEND_URL = config.BACKEND_URL;

// Fetch repositories for a user.
//
// Returns either:
//   - an array of repos on success
//   - a 200 `{error: ...}` payload that the backend itself returns on
//     GitHub-API failures (preserved for backward compatibility), or
//   - an `{error, status}` payload synthesised here for transport / network
//     failures so callers can surface a real error instead of silently
//     showing an empty list.
export const fetchRepos = async (
  user: string | undefined
): Promise<unknown[] | { error: string; status?: number }> => {
  try {
    const response = await apiClient.get("/api/repos", { params: { user } });
    return response.data;
  } catch (error: any) {
    console.error("❌ Error fetching repositories:", error);
    const detail =
      error.response?.data?.detail ||
      error.response?.data?.error ||
      error.message ||
      "Failed to load repositories";
    return { error: String(detail), status: error.response?.status };
  }
};

export const createGitHubRepo = async (
  user: string | undefined,
  visibility: string,
  owner?: string
): Promise<unknown> => {
  try {
    const payload: Record<string, unknown> = { user, visibility };
    if (owner && owner !== user) payload.owner = owner;
    const response = await apiClient.post(`${BACKEND_URL}/api/create-repo`, payload);
    return response.data;
  } catch (error: any) {
    console.error("Error creating GitHub repo:", error);
    const detail = error.response?.data?.detail || error.response?.data?.error || error.message;
    return { error: detail, status: error.response?.status };
  }
};

export const fetchRwxRepos = async (
  user: string | undefined,
  owner?: string
): Promise<unknown> => {
  try {
    const params: Record<string, unknown> = { user };
    if (owner && owner !== user) params.owner = owner;
    const response = await apiClient.get("/api/rwx-repos", { params });
    return response.data;
  } catch (error: any) {
    console.error("❌ Error fetching RWX repositories:", error);
    const detail = error.response?.data?.detail || error.response?.data?.error || error.message;
    return { error: detail, status: error.response?.status };
  }
};

export const checkRepoStatus = async (user: string, repoName: string): Promise<boolean> => {
  try {
    const response = await apiClient.get(`/api/repos/status/${user}/${repoName}`);
    return response.data.exists;
  } catch (error) {
    console.error("Error checking repo status:", error);
    return false;
  }
};

export const detectBuildTypes = async (
  user: string,
  owner: string,
  repo: string
): Promise<unknown> => {
  try {
    const response = await apiClient.get(`/api/repos/detect-build-type/${owner}/${repo}`, { params: { user } });
    return response.data;
  } catch (error: any) {
    console.error("❌ Error detecting build types:", error);
    return { error: error.message };
  }
};

export const suggestWorkflow = async (
  user: string,
  owner: string,
  repo: string,
  buildType: string | null = null
): Promise<unknown> => {
  try {
    const params = buildType ? { user, build_type: buildType } : { user };
    const response = await apiClient.get(`/api/repos/suggest-workflow/${owner}/${repo}`, { params });
    if (response.data?.workflow) {
      return response.data.workflow;
    }
    return response.data;
  } catch (error: any) {
    console.error("❌ Error suggesting workflow:", error);
    return { error: error.message };
  }
};
