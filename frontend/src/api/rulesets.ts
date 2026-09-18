import apiClient from "./apiClient";
import config from "../config";
import { apiErrorMessage } from "../utils/apiErrorMessage";

const BACKEND_URL = config.BACKEND_URL;

// TypeScript interfaces for API responses
interface RulesetSyncStatusResponse {
  success: boolean;
  error?: string;
  is_synced: boolean;
  missing_repos: string[];
  repo_statuses: Record<string, any>;
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

    return response.data;
  } catch (error) {
    console.error("❌ Error fetching ruleset sync status:", error);
    return {
      success: false,
      // `detail` is sometimes the structured {message, errors[]} the removal
      // routes answer with. Kept raw it reaches the panel as a React child and
      // renders "[object Object]", or throws outright. It was also `??`, so a
      // `detail: ""` answer survived and blanked the error banner entirely.
      error: apiErrorMessage(error, "Failed to check sync status"),
      is_synced: false,
      missing_repos: selectedRepos ?? [],
      repo_statuses: {}
    };
  }
};
