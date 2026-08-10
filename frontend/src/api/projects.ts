import axios, { AxiosResponse, AxiosError } from "axios";
import apiClient from "./apiClient";
import config from "../config";
import type { ProjectColorKey } from "../utils/projectColors";
import type { CustomFile } from "./customFiles";

const BACKEND_URL = config.BACKEND_URL;

// ===== Type Definitions =====

// Workflow interface for API responses - always includes isReusable
export interface WorkflowData {
  name: string;
  content: string;
  isReusable: boolean;
  isModified?: boolean;
  gitHash?: string;
  workflowStatus?: string;
  savedName?: string;
  lastModifiedBy?: string;
}

// Workflow interface for saving - isReusable is optional since backend can infer it
export interface WorkflowSaveData {
  name: string;
  content: string;
  isReusable?: boolean;
}

// Project interface supports multiple property naming conventions used across different components
// - project_id/id: Backend uses project_id, frontend components use id
// - project_name/name: Backend uses project_name, frontend components use name
// This flexibility allows the API to work with various component implementations
export interface Project {
  project_id?: number;
  id?: number | string;
  project_name?: string;
  name?: string;
  project_code: string;
  github_user?: string;
  created_at?: string;
  updated_at: string;
  account_type?: string;
  workflow_count?: number;
  pr_url?: string;
  prUrl?: string;
  selected_repos?: string[];
  workflows?: WorkflowData[];
  rxworkflows?: WorkflowData[];
  branch_regex?: string;
  branch_option?: "default" | "pattern";
  branch_max_age_days?: number;
  reusable_workflows_enabled?: boolean;
  use_prefix?: boolean;
  pr_state?: "new" | "draft" | "open" | "synced";
  project_type?: "standard" | "rwx";
  /** Saved backend repository visibility scope ("public" | "private"). */
  repository_visibility_scope?: "public" | "private";
  /** User-selected project identity color key used as a decorative accent. */
  project_color?: ProjectColorKey | null;
  validation_repo?: string | null;
  preflight_required?: boolean;
  last_preflight_status?: string | null;
  last_preflight_run_at?: string | null;
  last_preflight_error?: string | null;
  last_preflight_pr_url?: string | null;
  /** Cached project-level drift summary from the latest manual drift check. */
  drift_status?: "unknown" | "clean" | "drifted" | "check_failed";
  drift_count?: number;
  last_drift_check_at?: string | null;
  drift_error_summary?: string | null;
  last_modified_by?: string;
}

export interface SaveProjectData {
  project_name: string;
  selected_repos: string[];
  workflows: WorkflowSaveData[];
  rxworkflows: WorkflowSaveData[];
  github_user?: string;
  branch_regex: string;
  branch_option: string;
  branch_max_age_days: number;
  reusable_workflows_enabled: boolean;
  use_prefix: boolean;
  project_id?: string | number | null;
  custom_project_key?: string | null;
  project_type?: "standard" | "rwx";
  repository_visibility_scope?: "public" | "private";
  project_color?: ProjectColorKey | null;
  validation_repo?: string | null;
  preflight_required?: boolean;
}

export interface SaveProjectResponse {
  project_code: string;
  project_id: string;
  message?: string;
  pr_state?: string;
}

export interface UpdateProjectColorResponse {
  message?: string;
  project_id: number;
  project_color: ProjectColorKey | null;
}

export interface UpdateProjectNameResponse {
  message?: string;
  project_id: number;
  project_name: string;
  project_code: string;
}

export interface ExportProjectBackupResponse {
  blob: Blob;
  filename?: string;
}

// ===== Linked Reusable Workflows API =====

export interface RwxWorkflow {
  workflow_id: number;
  workflow_name: string;
  workflow_yaml: string;
  rwx_project_id: number;
  rwx_project_name: string;
  /** First repo of the source RWX project — used to build "Open in GitHub" deep-links. */
  rwx_repo?: string;
  rwx_repo_visibility?: "public" | "private" | "internal";
  link_validation?: {
    allowed: boolean;
    reason?: string;
    incompatible_repositories?: string[];
  };
  workflowStatus?: string;
  isModified?: boolean;
}

export interface LinkedStandardProject {
  project_id: number;
  project_name: string;
  project_code: string;
}

export interface LinkWorkflowResponse {
  message: string;
  workflow_id?: number;
  workflow_name?: string;
  already_linked?: boolean;
}

/**
 * Full response type for GET /api/projects/{project_name}.
 * Extends the lightweight Project list type with fields only present when
 * loading a single project (linked workflows, linked projects, etc.).
 */
export interface LoadProjectResponse extends Project {
  linked_reusable_workflows?: RwxWorkflow[];
  linked_standard_projects?: LinkedStandardProject[];
  caller_project_role?: string;
  custom_files?: CustomFile[];
  /** Workflow names with persisted drift from the last drift check (issue #1793's WorkflowDriftState),
   * used to seed the drift badge on initial render before the live check resolves. */
  drifted_workflow_names?: string[];
}

// ===== API Functions =====

// Fetch all projects
export const fetchProjects = async (user: string | undefined): Promise<Project[]> => {
  try {
    if (!user) {
      console.error("❌ Error: GitHub user is missing!");
      return [];
    }


    const response: AxiosResponse<Project[]> = await apiClient.get(`/api/projects/`, {
      params: { github_user: user },
    });

    return response.data;
  } catch (error) {
    const axiosError = error as AxiosError;
    console.error("❌ Error fetching projects:", axiosError.response?.data || axiosError);
    return [];
  }
};

/**
 * Save the user's manual Projects-grid order (issue #1804).
 *
 * Takes the complete ordered list of the user's accessible project IDs — the
 * backend rejects partial lists so a filtered view can never overwrite the
 * saved order. Throws on failure so the caller can roll back its optimistic
 * update; unlike fetchProjects this must not swallow the error.
 */
export const updateProjectOrder = async (
  user: string,
  projectIds: number[],
): Promise<number[]> => {
  const response: AxiosResponse<{ project_ids: number[] }> = await apiClient.put(
    `/api/projects/order`,
    { github_user: user, project_ids: projectIds },
  );
  return response.data.project_ids;
};

// Load a specific project by name
export const loadProject = async (user: string, projectName: string): Promise<LoadProjectResponse | null> => {
  try {
    const response: AxiosResponse<LoadProjectResponse> = await apiClient.get(`/api/projects/${encodeURIComponent(projectName)}`, {
      params: { github_user: user }
    });
    return response.data;
  } catch (error) {
    const axiosError = error as AxiosError;
    console.error("❌ Error loading project:", axiosError.response?.data || axiosError);
    return null;
  }
};

// Save a new project
export const saveProject = async (projectData: SaveProjectData): Promise<SaveProjectResponse> => {
  try {

    const isUpdate = !!projectData.project_id;
    
    const url = isUpdate
      ? `${BACKEND_URL}/api/projects/${projectData.project_id}/`
      : `${BACKEND_URL}/api/projects/`;

    const repositoryVisibilityScope =
      projectData.repository_visibility_scope ?? (isUpdate ? undefined : "public");

    const requestData = {
      project_name: projectData.project_name,
      selected_repos: projectData.selected_repos,
      workflows: projectData.workflows,
      rxworkflows: projectData.rxworkflows,
      branch_regex: projectData.branch_regex,
      branch_option: projectData.branch_option,
      branch_max_age_days: projectData.branch_max_age_days,
      reusable_workflows_enabled: projectData.reusable_workflows_enabled,
      use_prefix: projectData.use_prefix,
      project_type: projectData.project_type || "standard",
      ...(projectData.custom_project_key !== undefined
        ? { custom_project_key: projectData.custom_project_key }
        : {}),
      ...(repositoryVisibilityScope
        ? { repository_visibility_scope: repositoryVisibilityScope }
        : {}),
      ...(projectData.project_color !== undefined ? { project_color: projectData.project_color } : {}),
      ...(projectData.validation_repo !== undefined ? { validation_repo: projectData.validation_repo } : {}),
      ...(projectData.preflight_required !== undefined ? { preflight_required: projectData.preflight_required } : {}),
    };

    
    const response: AxiosResponse<SaveProjectResponse> = isUpdate
      ? await apiClient.put(url, requestData)
      : await apiClient.post(url, requestData);

    console.log("✅ Project Saved:", response.data);
    return response.data;
  } catch (error) {
    const axiosError = error as AxiosError;
    console.error("❌ Error saving project:", axiosError.response?.data || axiosError);
    // Add more detailed error logging
    if (axiosError.response) {
      console.error("❌ Response status:", axiosError.response.status);
      console.error("❌ Response headers:", axiosError.response.headers);
    }
    throw error;
  }
};

export const updateProjectColor = async (
  githubUser: string,
  projectId: string | number,
  projectColor: ProjectColorKey | null,
): Promise<UpdateProjectColorResponse> => {
  try {
    const response: AxiosResponse<UpdateProjectColorResponse> = await apiClient.patch(
      `${BACKEND_URL}/api/projects/${projectId}/project-color`,
      { github_user: githubUser, project_color: projectColor },
    );
    return response.data;
  } catch (error) {
    const axiosError = error as AxiosError;
    console.error("❌ Error updating project color:", axiosError.response?.data || axiosError);
    throw error;
  }
};

export const updateProjectName = async (
  githubUser: string,
  projectId: string | number,
  projectName: string,
): Promise<UpdateProjectNameResponse> => {
  try {
    const response: AxiosResponse<UpdateProjectNameResponse> = await apiClient.patch(
      `${BACKEND_URL}/api/projects/${projectId}/project-name`,
      { github_user: githubUser, project_name: projectName },
    );
    return response.data;
  } catch (error) {
    const axiosError = error as AxiosError;
    console.error("❌ Error updating project name:", axiosError.response?.data || axiosError);
    throw error;
  }
};

export const exportProjectBackup = async (
  projectId: string | number,
): Promise<ExportProjectBackupResponse> => {
  try {
    const response = await apiClient.get(`${BACKEND_URL}/api/projects/${projectId}/backup-export`, {
      responseType: "blob",
    });
    const contentDisposition = response.headers?.["content-disposition"] as string | undefined;
    const filenameMatch = contentDisposition?.match(/filename="?([^"]+)"?/i);
    return {
      blob: response.data,
      filename: filenameMatch?.[1],
    };
  } catch (error) {
    const axiosError = error as AxiosError;
    console.error("❌ Error exporting project backup:", axiosError.response?.data || axiosError);
    throw error;
  }
};

// ===== Repository-level branch override types =====

export type BranchConfigMode = "inherit" | "override";
export type BranchOptionValue = "default" | "pattern";

export interface RepoBranchConfig {
  repo_id: number;
  repo_name: string;
  branch_config_mode: BranchConfigMode;
  branch_option: BranchOptionValue | null;
  branch_regex: string | null;
  branch_max_age_days: number | null;
  effective_branch_option: BranchOptionValue;
  effective_branch_regex: string;
  effective_branch_max_age_days: number;
  using_project_default: boolean;
}

export interface ProjectRepoBranchConfigsResponse {
  project_id: number;
  project_branch_option: BranchOptionValue;
  project_branch_regex: string;
  project_branch_max_age_days: number;
  repos: RepoBranchConfig[];
}

export interface RepoBranchConfigUpdate {
  branch_config_mode: BranchConfigMode;
  branch_option?: BranchOptionValue | null;
  branch_regex?: string | null;
  branch_max_age_days?: number | null;
}

/** Fetch all selected repos in a project plus their effective branch config. */
export const fetchProjectRepoBranchConfigs = async (
  user: string,
  projectId: number | string
): Promise<ProjectRepoBranchConfigsResponse> => {
  const response: AxiosResponse<ProjectRepoBranchConfigsResponse> = await apiClient.get(
    `/api/projects/${projectId}/repo-branch-configs`,
    { params: { github_user: user } }
  );
  return response.data;
};

/** Update branch override config for a single repo within a project. */
export const updateProjectRepoBranchConfig = async (
  user: string,
  projectId: number | string,
  repoId: number,
  payload: RepoBranchConfigUpdate
): Promise<RepoBranchConfig> => {
  const response: AxiosResponse<RepoBranchConfig> = await apiClient.patch(
    `/api/projects/${projectId}/repos/${repoId}/branch-config`,
    payload,
    { params: { github_user: user } }
  );
  return response.data;
};

/** Reset a repo back to the project's default branch configuration. */
export const resetProjectRepoBranchConfig = async (
  user: string,
  projectId: number | string,
  repoId: number
): Promise<RepoBranchConfig> => {
  const response: AxiosResponse<RepoBranchConfig> = await apiClient.delete(
    `/api/projects/${projectId}/repos/${repoId}/branch-config`,
    { params: { github_user: user } }
  );
  return response.data;
};


// ===== Linked Reusable Workflows API Functions =====

// Fetch all available RWX workflows that can be linked
export const getAvailableRwxWorkflows = async (user: string, projectName?: string): Promise<RwxWorkflow[]> => {
  try {
    const response: AxiosResponse<RwxWorkflow[]> = await axios.get(
      `${BACKEND_URL}/api/rwx-workflows`,
      { params: { github_user: user, standard_project_name: projectName } }
    );
    return response.data;
  } catch (error) {
    const axiosError = error as AxiosError;
    console.error("❌ Error fetching RWX workflows:", axiosError.response?.data || axiosError);
    throw axiosError;
  }
};

// Link a reusable workflow from an RWX project to a standard project
export const linkReusableWorkflow = async (
  user: string,
  projectName: string,
  workflowId: number,
  rwxProjectId: number
): Promise<LinkWorkflowResponse> => {
  try {
    const response: AxiosResponse<LinkWorkflowResponse> = await apiClient.post(
      `${BACKEND_URL}/api/projects/${encodeURIComponent(projectName)}/linked-reusable-workflows`,
      { workflow_id: workflowId, rwx_project_id: rwxProjectId }
    );
    console.log("✅ Workflow linked:", response.data);
    return response.data;
  } catch (error) {
    const axiosError = error as AxiosError;
    console.error("❌ Error linking workflow:", axiosError.response?.data || axiosError);
    throw error;
  }
};

// Unlink a reusable workflow from a standard project
export const unlinkReusableWorkflow = async (
  user: string,
  projectName: string,
  workflowId: number
): Promise<{ message: string }> => {
  try {
    const response: AxiosResponse<{ message: string }> = await apiClient.delete(
      `${BACKEND_URL}/api/projects/${encodeURIComponent(projectName)}/linked-reusable-workflows/${workflowId}`,
      { params: { github_user: user } }
    );
    console.log("✅ Workflow unlinked:", response.data);
    return response.data;
  } catch (error) {
    const axiosError = error as AxiosError;
    console.error("❌ Error unlinking workflow:", axiosError.response?.data || axiosError);
    throw error;
  }
};

export interface UpdateLinkedReusableWorkflowResponse {
  message: string;
  workflow_id: number;
  workflow_name: string;
  rwx_project_id: number;
  rwx_project_name: string;
  workflow_status?: string;
}

/**
 * Update the YAML of a reusable workflow that is linked into a standard project.
 *
 * Resolution is by ``workflowId`` joined through ``LinkedReusableWorkflow`` to
 * the named standard project — the backend does not rely on workflow_name (the
 * name returned for linked workflows is display-formatted with the source RWX
 * project's prefix and a ``.yml`` extension and would not match the canonical
 * stored stem, which previously caused duplicate workflow rows to be created
 * in the source RWX project).
 */
export const updateLinkedReusableWorkflow = async (
  user: string,
  standardProjectName: string,
  workflowId: number,
  content: string
): Promise<UpdateLinkedReusableWorkflowResponse> => {
  try {
    const response: AxiosResponse<UpdateLinkedReusableWorkflowResponse> =
      await apiClient.put(
        `${BACKEND_URL}/api/projects/${encodeURIComponent(standardProjectName)}/linked-reusable-workflows/${workflowId}`,
        { content }
      );
    console.log("✅ Linked reusable workflow updated:", response.data);
    return response.data;
  } catch (error) {
    const axiosError = error as AxiosError;
    console.error(
      "❌ Error updating linked reusable workflow:",
      axiosError.response?.data || axiosError
    );
    throw error;
  }
};
