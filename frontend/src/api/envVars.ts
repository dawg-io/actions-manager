import { AxiosResponse } from "axios";
import apiClient from "./apiClient";
import config from "../config";
import { Repository } from "./handlers";
import { toast } from "../utils/toast";

const BACKEND_URL = config.BACKEND_URL;

// TypeScript interfaces for API responses
interface UpdateEnvVarsResponse {
  error?: string;
  [key: string]: any;
}

interface GetEnvVarsResponse {
  env_vars: Array<{
    env_key: string;
    value?: string;
  }>;
  [key: string]: any;
}

interface DeleteEnvVarsResponse {
  results?: any;
  [key: string]: any;
}

interface SyncEnvVarResponse {
  [key: string]: any;
}

interface GetEnvVarsCountResponse {
  count: number;
  [key: string]: any;
}

// TypeScript interfaces for data structures
export interface EnvVar {
  env_key: string;
  value?: string;
  repo: string;
}

export interface ManualEnvVar {
  key: string;
  value: string;
}

// Update environment variables
export const updateEnvVars = async (
  user: string,
  selectedRepos: (string | Repository)[],
  envVars: Array<{ key: string; value: string }>,
  projectName: string
): Promise<UpdateEnvVarsResponse> => {
  try {
    console.log("📌 Debug: Sending Env Vars Update Request:", { user, selectedRepos, envVars, projectName });

    // Convert Repository objects to strings
    const repoNames = selectedRepos.map(repo => 
      typeof repo === 'string' ? repo : (repo.full_name || repo.name)
    );

    const response: AxiosResponse<UpdateEnvVarsResponse> = await apiClient.post(`${BACKEND_URL}/api/update-env-vars`, {
      user,
      repo_names: repoNames,
      env: envVars,
      project_name: projectName,
    });

    console.log("📌 Debug: Env Vars API Response:", response.data);

    // Return the response data directly - the calling code handles state management
    return response.data;
  } catch (error) {
    console.error("❌ Error updating env vars:", error);
    return { error: (error as Error).message };
  }
};

// Fetch environment variables
export const getEnvVars = async (
  user: string,
  repoName: string,
  projectName: string
): Promise<EnvVar[]> => {
  try {
    const response = await fetch(
      `${BACKEND_URL}/api/get-env-vars?user=${user}&repo_name=${encodeURIComponent(repoName)}&project_name=${encodeURIComponent(projectName)}`,
      { credentials: "include" }
    );
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const data: GetEnvVarsResponse = await response.json();
    console.log(`📌 Debug: Fetched Environment Variables from GitHub for ${repoName}:`, data);

    // ✅ Ensure env_vars is properly structured
    if (!data.env_vars || !Array.isArray(data.env_vars)) {
      console.warn(`⚠️ Warning: Unexpected response format for env vars in ${repoName}`, data);
      return [];
    }

    // ✅ Ensure each variable contains `value`
    return data.env_vars.map(env => ({
      env_key: env.env_key,  // ✅ Ensure correct key name
      value: env.value || "N/A",  // ✅ Ensure value exists
      repo: repoName  // ✅ Store the associated repository
    }));
  } catch (error) {
    console.error("❌ Error fetching environment variables:", error);
    return [];
  }
};

export const handleDeleteEnvVars = async (
  user: string,
  projectName: string,
  selectedRepos: (string | Repository)[],
  envVars: Array<{ env_key: string; value?: string }>
): Promise<void> => {  
  if (!user || !projectName || selectedRepos.length === 0 || envVars.length === 0) {
    toast.error("Missing required fields. Please check your inputs.");
    return;
  }

  console.log("📌 Debug: Sending Delete Request with:", {
    user,
    projectName,
    selectedRepos,
    envVars
  });

  try {
    // Convert Repository objects to strings
    const repoNames = selectedRepos.map(repo => 
      typeof repo === 'string' ? repo : (repo.full_name || repo.name)
    );

    const response: AxiosResponse<DeleteEnvVarsResponse> = await apiClient.delete(`${BACKEND_URL}/api/delete-env-vars`, {
      data: {
        user,
        project_name: projectName,
        repo_names: repoNames,
        env: envVars,
      },
    });

    const data = response.data;
    console.log("✅ Deleted environment variables:", data.results);

    // ✅ Optionally fetch updates after deletion
    const repoStrings = selectedRepos.map(repo => 
      typeof repo === 'string' ? repo : (repo.full_name || repo.name)
    );
    for (const repo of repoStrings) {
      await getEnvVars(user, repo, projectName);
    }

  } catch (error) {
    console.error("❌ Error making delete request:", error);
    toast.error("Failed to delete environment variables. Please try again.");
  }
};

// Sync environment variable to all repositories
export const syncEnvVar = async (
  user: string,
  projectName: string,
  selectedRepos: (string | Repository)[],
  envKey: string
): Promise<SyncEnvVarResponse> => {
  try {
    console.log("📌 Debug: Syncing Env Var:", { user, projectName, selectedRepos, envKey });

    // Convert Repository objects to strings
    const repoNames = selectedRepos.map(repo => 
      typeof repo === 'string' ? repo : (repo.full_name || repo.name)
    );

    const response: AxiosResponse<SyncEnvVarResponse> = await apiClient.post(`${BACKEND_URL}/api/sync-env-var`, {
      user,
      project_name: projectName,
      repo_names: repoNames,
      env_key: envKey,
    });

    console.log("✅ Sync response:", response.data);
    return response.data;
  } catch (error) {
    console.error("❌ Error syncing environment variable:", error);
    throw error;
  }
};

// Get environment variables count for a project
export const getEnvVarsCount = async (
  user: string,
  projectName: string,
  selectedRepos: (string | Repository)[]
): Promise<number> => {
  try {
    // Convert Repository objects to strings
    const repoNames = selectedRepos.map(repo => 
      typeof repo === 'string' ? repo : (repo.full_name || repo.name)
    );
    const repoNamesString = repoNames.join(",");
    
    const response = await fetch(
      `${BACKEND_URL}/api/env-vars-count?user=${user}&project_name=${encodeURIComponent(projectName)}&repo_names=${encodeURIComponent(repoNamesString)}`,
      { credentials: "include" }
    );
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const data: GetEnvVarsCountResponse = await response.json();
    console.log("📌 Debug: Environment variables count:", data);
    return data.count || 0;
  } catch (error) {
    console.error("❌ Error fetching environment variables count:", error);
    return 0;
  }
};