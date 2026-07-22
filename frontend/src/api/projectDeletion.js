import axios from "axios";
import apiClient from "./apiClient";
import config from "../config";

const BACKEND_URL = config.BACKEND_URL;

// Get project deletion summary (list of resources that would be deleted)
export const getProjectDeletionSummary = async (user, projectName) => {
  try {
    console.log(`📌 Debug: Getting deletion summary for project '${projectName}', user '${user}'`);

    const response = await axios.get(`${BACKEND_URL}/api/projects/${encodeURIComponent(projectName)}/deletion-summary`, {
      params: { github_user: user },
    });

    console.log("✅ Project deletion summary retrieved:", response.data);
    return response.data;
  } catch (error) {
    console.error("❌ Error getting project deletion summary:", error.response?.data || error);
    throw error;
  }
};

// Enhanced project deletion with option to delete GitHub resources
export const deleteProjectEnhanced = async (user, projectName, deleteGitHubResources = false, deleteDeploymentEnvironments = true) => {
  try {
    console.log(`📌 Debug: Enhanced deletion for project '${projectName}', user '${user}', deleteGitHub: ${deleteGitHubResources}, deleteDeploymentEnvironments: ${deleteDeploymentEnvironments}`);

    const response = await apiClient.delete(`${BACKEND_URL}/api/projects/${encodeURIComponent(projectName)}/enhanced`, {
      data: {
        github_user: user,
        project_name: projectName,
        delete_github_resources: deleteGitHubResources,
        delete_deployment_environments: deleteDeploymentEnvironments
      }
    });

    console.log("✅ Project deleted successfully:", response.data);
    return response.data;
  } catch (error) {
    console.error("❌ Error deleting project:", error.response?.data || error);
    throw error;
  }
};