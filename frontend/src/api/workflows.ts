import axios, { AxiosResponse, AxiosError } from "axios";
import apiClient from "./apiClient";
import config from "../config";
import { Workflow } from "../types/workflow";
import { WorkflowUpdateResponse } from "../types/workflowResponse";
import { toast } from "../utils/toast";

const BACKEND_URL = config.BACKEND_URL;

// ===== Type Definitions =====

interface SaveWorkflowsResponse {
  success?: boolean;
  message?: string;
  project_code?: string;
  pr_state?: string;
  state_changed?: boolean;
}

interface UpdateWorkflowsResponse extends WorkflowUpdateResponse {
  status?: number;
}

interface DeleteWorkflowResponse {
  success: boolean;
  data?: {
    message?: string;
    results?: Record<string, number>;
  };
  skipped?: boolean;
}

interface WorkflowsCountResponse {
  count: number;
}

// ===== API Functions =====

// Save workflows to DB
export const saveWorkflows = async (
  user: string,
  projectName: string,
  workflows: Workflow[],
  rxworkflows: Workflow[] = []
): Promise<SaveWorkflowsResponse> => {
  try {
    // Map savedName → original_name for the backend rename path; drop the
    // frontend-only savedName field so the payload stays clean.
    const mapPayload = (wf: Workflow) => {
      const { savedName, ...rest } = wf;
      return savedName && savedName !== rest.name
        ? { ...rest, original_name: savedName }
        : rest;
    };

    const response: AxiosResponse<SaveWorkflowsResponse> = await apiClient.post(
      `${BACKEND_URL}/api/save-workflows`,
      {
        workflows: workflows.map(mapPayload),
        rxworkflows: rxworkflows.map(mapPayload),
        project_name: projectName,
      }
    );

    console.log("✅ Workflows saved to DB:", response.data);
    return response.data;
  } catch (error) {
    console.error("❌ Error saving workflows:", error);
    throw error;
  }
};

// Run workflow for selected repositories
export const updateWorkflows = async (
  user: string,
  selectedRepos: string[],
  workflows: Workflow[],
  rxworkflows: Workflow[],
  regexPattern: string,
  branchOption: string,
  projectName: string
): Promise<UpdateWorkflowsResponse> => {
  try {
    const requestBody = {
      user,
      repo_names: selectedRepos,
      workflows,
      rxworkflows,
      regex_pattern: regexPattern,
      branch_option: branchOption,
      project_name: projectName,
    };

    console.log("📌 Debug: Sending Workflow Update Request:", requestBody);

    const response: AxiosResponse<UpdateWorkflowsResponse> = await apiClient.post(
      `${BACKEND_URL}/api/update-workflow`,
      requestBody
    );

    return response.data;
  } catch (error) {
    console.error("❌ Error updating workflow:", error);

    // Return a consistent error response structure instead of null
    // This ensures processWorkflowResults can handle the error properly
    const axiosError = error as AxiosError<UpdateWorkflowsResponse>;
    if (axiosError.response?.data) {
      // Return the backend error response if available
      return axiosError.response.data;
    } else {
      // Return a fallback error structure
      return {
        error: axiosError.message || "Network error occurred",
        status: axiosError.response?.status || 500,
        results: {}, // Empty results to prevent processWorkflowResults from failing
      };
    }
  }
};

// Delete a workflow from GitHub repositories only (no state update)
export const deleteWorkflowFromGitHub = async (
  user: string,
  selectedRepos: string[],
  workflowName: string,
  regexPattern: string,
  projectName: string
): Promise<DeleteWorkflowResponse> => {
  if (!workflowName?.trim()) {
    console.log("🛑 Skipping GitHub delete for empty workflow entry.");
    return { success: true, skipped: true };
  }

  try {
    const requestData = {
      user,
      repo_names: selectedRepos,
      workflow_name: workflowName,
      regex_pattern: regexPattern,
      project_name: projectName,
    };

    console.log("📌 Debug: Sending Workflow Delete Request to GitHub:", requestData);

    const response: AxiosResponse<any> = await apiClient.delete(
      `${BACKEND_URL}/api/delete-workflow`,
      { data: requestData }
    );

    console.log(`✅ Deleted workflow from GitHub: ${workflowName}`);
    console.log("📌 Debug: Deleted branches:", response.data.results);

    return { success: true, data: response.data };
  } catch (error) {
    console.error("❌ Error deleting workflow from GitHub:", error);
    throw error;
  }
};

// Delete a workflow from database only (no state update)
export const deleteWorkflowFromDatabase = async (
  user: string,
  projectName: string,
  workflowName: string
): Promise<DeleteWorkflowResponse> => {
  if (!workflowName?.trim()) {
    console.log("🛑 Skipping database delete for empty workflow entry.");
    return { success: true, skipped: true };
  }

  try {
    const requestData = {
      user,
      workflow_name: workflowName,
      project_name: projectName,
    };

    console.log(`📌 Deleting workflow '${workflowName}' from database...`);

    const response: AxiosResponse<any> = await apiClient.delete(
      `${BACKEND_URL}/api/delete-db-workflow`,
      { data: requestData }
    );

    console.log(`✅ Deleted workflow from database: ${workflowName}`);
    return { success: true, data: response.data };
  } catch (error) {
    console.error("❌ Error deleting workflow from database:", error);
    throw error;
  }
};

// Delete a reusable workflow from GitHub am-reuseable-workflow repository
export const deleteReusableWorkflowFromGitHub = async (
  user: string,
  workflowName: string,
  projectName: string
): Promise<DeleteWorkflowResponse> => {
  try {
    const requestData = {
      user,
      workflow_name: workflowName,
      project_name: projectName,
    };

    console.log(`📌 Deleting reusable workflow '${workflowName}' from GitHub repository...`);

    const response: AxiosResponse<any> = await apiClient.delete(
      `${BACKEND_URL}/api/delete-reusable-workflow`,
      { data: requestData }
    );

    console.log(`✅ Deleted reusable workflow from GitHub: ${workflowName}`);
    return { success: true, data: response.data };
  } catch (error) {
    console.error("❌ Error deleting reusable workflow from GitHub:", error);
    throw error;
  }
};

// Legacy function for backward compatibility - delete from both GitHub and database
export const handleDeleteWorkflow = async (
  user: string,
  workflows: Workflow[],
  selectedRepos: string[],
  projectName: string,
  setWorkflows: (workflows: Workflow[]) => void,
  index: number,
  regexPattern: string = ""
): Promise<void> => {
  const workflowToDelete = workflows[index];

  if (!workflowToDelete?.name?.trim()) {
    console.log("🛑 Skipping delete for empty workflow entry.");
    setWorkflows(workflows.filter((_, i) => i !== index));
    return;
  }

  try {
    // Delete from GitHub first
    await deleteWorkflowFromGitHub(
      user,
      selectedRepos,
      workflowToDelete.name,
      regexPattern,
      projectName
    );

    // Then delete from database
    await deleteWorkflowFromDatabase(user, projectName, workflowToDelete.name);

    console.log(`✅ Successfully deleted workflow: ${workflowToDelete.name}`);
    setWorkflows(workflows.filter((_, i) => i !== index));
  } catch (error) {
    console.error("❌ Error deleting workflow:", error);
    toast.error("Error deleting workflow. Check console for details.");
  }
};

// Get workflows count for a project
export const getWorkflowsCount = async (
  user: string,
  projectName: string
): Promise<number> => {
  try {
    const response: AxiosResponse<WorkflowsCountResponse> = await axios.get(
      `${BACKEND_URL}/api/workflows-count`,
      {
        params: {
          user,
          project_name: projectName,
        },
      }
    );

    console.log("✅ Workflows count retrieved:", response.data);
    return response.data.count || 0;
  } catch (error) {
    console.error("❌ Error fetching workflows count:", error);
    return 0;
  }
};

// ===== Workflow Version History API Functions =====

export interface WorkflowVersion {
  version_id: number;
  version_number: number;
  content: string;
  metadata: string | null;
  created_at: string;
}

export interface VersionHistoryResponse {
  workflow_id: number;
  workflow_name: string;
  versions: WorkflowVersion[];
  total_versions: number;
}

export interface RestoreVersionResponse {
  message: string;
  workflow_name: string;
  restored_version: number;
  restored_content: string;
}

/**
 * Get all version history for a specific workflow
 */
export const getWorkflowVersions = async (
  user: string,
  projectName: string,
  workflowName: string
): Promise<VersionHistoryResponse> => {
  try {
    const response: AxiosResponse<VersionHistoryResponse> = await axios.get(
      `${BACKEND_URL}/api/workflows/${encodeURIComponent(workflowName)}/versions`,
      {
        params: {
          user,
          project_name: projectName,
        },
      }
    );

    console.log(`✅ Retrieved ${response.data.total_versions} versions for workflow '${workflowName}'`);
    return response.data;
  } catch (error) {
    console.error(`❌ Error fetching workflow versions for '${workflowName}':`, error);
    throw error;
  }
};

/**
 * Restore a workflow to a previous version
 */
export const restoreWorkflowVersion = async (
  user: string,
  projectName: string,
  workflowName: string,
  versionId: number
): Promise<RestoreVersionResponse> => {
  try {
    const response: AxiosResponse<RestoreVersionResponse> = await apiClient.post(
      `${BACKEND_URL}/api/workflows/restore-version`,
      {
        project_name: projectName,
        workflow_name: workflowName,
        version_id: versionId,
      }
    );

    console.log(`✅ Restored workflow '${workflowName}' to version ${versionId}`);
    return response.data;
  } catch (error) {
    console.error(`❌ Error restoring workflow version ${versionId}:`, error);
    throw error;
  }
};
