import apiClient from "./apiClient";
import config from "../config";
import { errorDetail } from "./errorDetail";

const BACKEND_URL = config.BACKEND_URL;

/** A GitHub deployment environment as returned by /api/get-environments. */
export interface GitHubEnvironment {
  name: string;
}

export interface CreateEnvironmentResponse {
  created?: boolean;
}

export interface DeleteEnvironmentResponse {
  deleted?: boolean;
}

export interface SyncEnvironmentResponse {
  synced?: boolean;
}

export const createEnvironment = async (
  user: string,
  repoName: string,
  environmentName: string
): Promise<CreateEnvironmentResponse> => {
  try {
    const response = await apiClient.post(`${BACKEND_URL}/api/create-environment`, {
      user,
      repo_name: repoName,
      environment_name: environmentName,
    });

    console.log("✅ Environment created successfully:", response.data);
    return response.data;
  } catch (error) {
    console.error("❌ Error creating environment:", errorDetail(error));
    throw error;
  }
};

export const getEnvironments = async (
  user: string,
  repoName: string
): Promise<GitHubEnvironment[]> => {
  try {
    const response = await apiClient.get(`${BACKEND_URL}/api/get-environments`, {
      params: { user, repo_name: repoName },
    });

    console.log("✅ Environments fetched successfully:", response.data);
    return response.data.environments;
  } catch (error) {
    console.error("❌ Error fetching environments:", errorDetail(error));
    throw error;
  }
};

export const deleteDeploymentEnvironment = async (
  user: string,
  repoNames: string[],
  environmentName: string
): Promise<DeleteEnvironmentResponse> => {
  try {
    const response = await apiClient.delete(`${BACKEND_URL}/api/delete-environment`, {
      data: {
        user,
        repo_names: repoNames,
        environment_name: environmentName,
      },
    });

    console.log("✅ Deployment environment deleted successfully:", response.data);
    return response.data;
  } catch (error) {
    console.error("❌ Error deleting deployment environment:", errorDetail(error));
    throw error;
  }
};

export const syncEnvironment = async (
  user: string,
  projectName: string,
  repoNames: string[],
  environmentName: string
): Promise<SyncEnvironmentResponse> => {
  try {
    console.log("📌 Debug: Syncing Environment:", { user, projectName, repoNames, environmentName });

    const response = await apiClient.post(`${BACKEND_URL}/api/sync-environment`, {
      user,
      project_name: projectName,
      repo_names: repoNames,
      environment_name: environmentName,
    });

    console.log("✅ Sync response:", response.data);
    return response.data;
  } catch (error) {
    console.error("❌ Error syncing environment:", errorDetail(error));
    throw error;
  }
};

export const getEnvironmentsCount = async (
  user: string,
  repoNames: string[]
): Promise<number> => {
  try {
    const response = await apiClient.get(`${BACKEND_URL}/api/environments-count`, {
      params: { 
        user, 
        repo_names: repoNames.join(",")
      },
    });

    console.log("✅ Environment count fetched successfully:", response.data);
    return response.data.count || 0;
  } catch (error) {
    console.error("❌ Error fetching environment count:", errorDetail(error));
    return 0; // Return 0 on error to be safe
  }
};