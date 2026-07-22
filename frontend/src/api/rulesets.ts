import apiClient from "./apiClient";
import config from "../config";

const BACKEND_URL = config.BACKEND_URL;

// TypeScript interfaces for API responses
interface RulesetSyncStatusResponse {
  success: boolean;
  error?: string;
  is_synced: boolean;
  missing_repos: string[];
  repo_statuses: Record<string, any>;
}

interface ApiError {
  response?: {
    data?: {
      detail?: string;
    };
  };
  message: string;
}

// Check ruleset sync status across repositories
export const getRulesetSyncStatus = async (
  user: string,
  rulesetId: number,
  selectedRepos: string[]
): Promise<RulesetSyncStatusResponse> => {
  try {
    const response = await apiClient.post(`${BACKEND_URL}/api/rulesets/${rulesetId}/sync-status`, {
      github_user: user,
      repo_names: selectedRepos
    });

    // Example usage of nullish coalescing for success message
    setSuccessMessage(response.data.message ?? 'Ruleset uploaded successfully');

    return response.data;
  } catch (error) {
    console.error("❌ Error fetching ruleset sync status:", error);
    const err = error as ApiError;
    return {
      success: false,
      error: err.response?.data?.detail ?? err.message,
      is_synced: false,
      missing_repos: selectedRepos ?? [],
      repo_statuses: {}
    };
  }
};
// Sets a success message for the user, e.g., via a toast notification or global state.
// For now, log to console (replace with your app's notification system as needed).
function setSuccessMessage(message: string) {
  console.log("✅ Success:", message);
}
