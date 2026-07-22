import axios, { AxiosResponse } from "axios";
import apiClient from "./apiClient";
import config from "../config";
import { Repository } from "./handlers";
import { toast } from "../utils/toast";

const BACKEND_URL = config.BACKEND_URL;

// ===== Type Definitions =====

interface CreateSecretsResponse {
  results?: Record<string, any>;
  error?: string;
  [key: string]: any;
}

interface GetSecretsResponse {
  secrets: Array<{
    secret_key: string;
    secret_value?: string;
  }>;
  [key: string]: any;
}

interface DeleteSecretsResponse {
  results?: Record<string, any>;
  [key: string]: any;
}

interface SyncSecretResponse {
  [key: string]: any;
}

interface GetSecretsCountResponse {
  count: number;
  [key: string]: any;
}

// Secret interface supports multiple property naming conventions used across different components
// - secret_key/name: Used by different components for the secret's key
// - secret_value/value: Used by different components for the secret's value
// - key/env_key: Alternative naming used in some contexts
// This flexibility allows the API to work with various component implementations
export interface Secret {
  secret_key?: string;
  key?: string;
  name?: string;
  secret_value?: string;
  value?: string;
  repo?: string;
}

// ===== API Functions =====

// ✅ Create secrets with axios and refresh after
export const createSecrets = async (
  user: string | undefined,
  selectedRepos: (string | Repository)[],
  secrets: Secret[],
  projectName: string | undefined,
  setSecrets?: (secrets: any) => void
): Promise<CreateSecretsResponse> => {
  // Validate required parameters
  if (!user || !projectName) {
    console.error("❌ User and project name are required");
    toast.error("User and project name are required.");
    return { error: "User and project name are required" };
  }

  try {
    // Convert Repository objects to strings
    const repoNames = selectedRepos.map(repo => 
      typeof repo === 'string' ? repo : (repo.full_name || repo.name)
    );

    const response: AxiosResponse<CreateSecretsResponse> = await apiClient.post(
      `${BACKEND_URL}/api/create-secrets`,
      {
        user,
        project_name: projectName,
        repo_names: repoNames,
        secrets,
      }
    );

    console.log("✅ Secrets saved:", response.data.results);

    // ✅ Fetch updated secrets after saving
    let allSecrets: Secret[] = [];
    for (const repo of repoNames) {
      const repoSecrets = await getSecrets(user, repo, projectName);
      allSecrets = [...allSecrets, ...repoSecrets];
    }

    if (typeof setSecrets === "function") {
      setSecrets(allSecrets);
    } else {
      console.warn("⚠️ setSecrets not provided or not a function");
    }

    return response.data;
  } catch (error) {
    console.error("❌ Error saving secrets:", error);
    toast.error("Error saving secrets. Please try again.");
    return { error: (error as Error).message };
  }
};

// ✅ Get secrets (still using fetch for query string simplicity, or you can convert too)
export const getSecrets = async (
  user: string,
  repoName: string,
  projectName: string
): Promise<Secret[]> => {
  try {
    const response: AxiosResponse<GetSecretsResponse> = await axios.get(
      `${BACKEND_URL}/api/get-secrets`,
      {
        params: {
          user,
          repo_name: repoName,
          project_name: projectName,
        },
      }
    );

    console.log(`📌 Debug: Fetched Secrets from GitHub for ${repoName}:`, response.data);
    return response.data.secrets || [];
  } catch (error) {
    console.error("❌ Error fetching secrets:", error);
    return [];
  }
};

// ✅ Delete secrets with axios and refresh after
export const deleteSecrets = async (
  user: string | undefined,
  projectName: string | undefined,
  selectedRepos: string[],
  secretKey: string,
  setSecrets?: (secrets: any) => void
): Promise<void> => {
  if (!user || !projectName || selectedRepos.length === 0 || secretKey.length === 0) {
    toast.error("Missing required fields. Please check your inputs.");
    return;
  }

  console.log("📌 Debug: Sending Delete Request with:", {
    user,
    projectName,
    selectedRepos,
    secretKey,
  });

  try {
    const response: AxiosResponse<DeleteSecretsResponse> = await apiClient.delete(
      `${BACKEND_URL}/api/delete-secrets`,
      {
        data: {
          user,
          project_name: projectName,
          repo_names: selectedRepos,
          secret_name: secretKey,
        },
      }
    );

    console.log("✅ Deleted secret:", response.data.results);
    // ✅ Fetch updated secrets after deletion
    let allSecrets: Secret[] = [];
    for (const repo of selectedRepos) {
      const repoSecrets = await getSecrets(user, repo, projectName);
      allSecrets = [...allSecrets, ...repoSecrets];
    }

    if (setSecrets) {
      setSecrets(allSecrets);
    }
  } catch (error) {
    console.error("❌ Error making delete request:", error);
    toast.error("Failed to delete secret. Please try again.");
  }
};

// Sync secret to all repositories  
export const syncSecret = async (
  user: string,
  projectName: string,
  selectedRepos: string[],
  secretKey: string
): Promise<SyncSecretResponse> => {
  try {
    console.log("📌 Debug: Syncing Secret:", { user, projectName, selectedRepos, secretKey });

    const response: AxiosResponse<SyncSecretResponse> = await apiClient.post(
      `${BACKEND_URL}/api/sync-secret`,
      {
        user,
        project_name: projectName,
        repo_names: selectedRepos,
        secret_key: secretKey,
      }
    );

    console.log("✅ Sync response:", response.data);
    return response.data;
  } catch (error) {
    console.error("❌ Error syncing secret:", error);
    throw error;
  }
};

// Get secrets count for a project
export const getSecretsCount = async (
  user: string,
  projectName: string,
  selectedRepos: string[]
): Promise<number> => {
  try {
    const repoNames = selectedRepos.join(",");
    const response: AxiosResponse<GetSecretsCountResponse> = await axios.get(
      `${BACKEND_URL}/api/secrets-count`,
      {
        params: {
          user,
          project_name: projectName,
          repo_names: repoNames,
        },
      }
    );

    console.log("📌 Debug: Secrets count:", response.data);
    return response.data.count || 0;
  } catch (error) {
    console.error("❌ Error fetching secrets count:", error);
    return 0;
  }
};
