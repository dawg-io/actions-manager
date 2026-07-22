import axios from "axios";
import apiClient from "./apiClient";
import config from "../config";

const BACKEND_URL = config.BACKEND_URL;

export const createEnvironment = async (user, repoName, environmentName) => {
  try {
    const response = await apiClient.post(`${BACKEND_URL}/api/create-environment`, {
      user,
      repo_name: repoName,
      environment_name: environmentName,
    });

    console.log("✅ Environment created successfully:", response.data);
    return response.data;
  } catch (error) {
    console.error("❌ Error creating environment:", error.response?.data || error.message);
    throw error;
  }
};

export const getEnvironments = async (user, repoName) => {
  try {
    const response = await axios.get(`${BACKEND_URL}/api/get-environments`, {
      params: { user, repo_name: repoName },
    });

    console.log("✅ Environments fetched successfully:", response.data);
    return response.data.environments;
  } catch (error) {
    console.error("❌ Error fetching environments:", error.response?.data || error.message);
    throw error;
  }
};

export const deleteDeploymentEnvironment = async (user, repoNames, environmentName) => {
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
    console.error("❌ Error deleting deployment environment:", error.response?.data || error.message);
    throw error;
  }
};

export const syncEnvironment = async (user, projectName, repoNames, environmentName) => {
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
    console.error("❌ Error syncing environment:", error);
    throw error;
  }
};

export const getEnvironmentsCount = async (user, repoNames) => {
  try {
    const response = await axios.get(`${BACKEND_URL}/api/environments-count`, {
      params: { 
        user, 
        repo_names: repoNames.join(",")
      },
    });

    console.log("✅ Environment count fetched successfully:", response.data);
    return response.data.count || 0;
  } catch (error) {
    console.error("❌ Error fetching environment count:", error.response?.data || error.message);
    return 0; // Return 0 on error to be safe
  }
};