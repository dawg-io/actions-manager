import apiClient from "./apiClient";
import config from "../config";
import { errorDetail } from "./errorDetail";

const BACKEND_URL = config.BACKEND_URL;

// Mirrors the backend ProjectDeletionSummary model in
// backend/project_deletion.py. Declared here rather than in the modal that
// renders it so the request and its shape stay in one place.
export interface DeletionSummaryWorkflow {
  name: string;
  is_reusable: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface DeletionSummarySecret {
  name: string;
  repository: string;
  created_at?: string;
  updated_at?: string;
}

export interface DeletionSummaryEnvironmentVariable {
  name: string;
  repository: string;
  environment: string;
  value?: string;
}

export interface DeletionSummaryDeploymentEnvironment {
  name: string;
  repository: string;
  url?: string;
}

export interface ProjectDeletionSummary {
  project_name: string;
  project_code: string;
  workflows: DeletionSummaryWorkflow[];
  reusable_workflows: DeletionSummaryWorkflow[];
  secrets: DeletionSummarySecret[];
  environment_variables: DeletionSummaryEnvironmentVariable[];
  deployment_environments: DeletionSummaryDeploymentEnvironment[];
}

export interface EnhancedDeletionResult {
  message?: string;
  details?: {
    project_deleted: boolean;
    /** Human-readable lines, e.g. "Repository Secret: FOO from org/repo". */
    github_resources_deleted: string[];
    errors: string[];
  };
}


// Get project deletion summary (list of resources that would be deleted)
export const getProjectDeletionSummary = async (
  user: string,
  projectName: string
): Promise<ProjectDeletionSummary> => {
  try {
    console.log(`📌 Debug: Getting deletion summary for project '${projectName}', user '${user}'`);

    const response = await apiClient.get(`${BACKEND_URL}/api/projects/${encodeURIComponent(projectName)}/deletion-summary`, {
      params: { github_user: user },
    });

    return response.data;
  } catch (error) {
    console.error(
      "❌ Error getting project deletion summary:",
      errorDetail(error)
    );
    throw error;
  }
};

// Enhanced project deletion with option to delete GitHub resources
export const deleteProjectEnhanced = async (
  user: string,
  projectName: string,
  deleteGitHubResources = false,
  deleteDeploymentEnvironments = true
): Promise<EnhancedDeletionResult> => {
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
    console.error(
      "❌ Error deleting project:",
      errorDetail(error)
    );
    throw error;
  }
};