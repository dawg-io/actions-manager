/**
 * API client for workflow drift detection (issue: "Detect GitHub-side workflow changes").
 *
 * Wraps the v2 endpoints exposed by backend/workflows.py:
 *   GET  /api/projects/{project_id}/drift
 *   GET  /api/workflows/{workflow_id}/drift
 *   POST /api/workflows/{workflow_id}/resolve-drift
 *   POST /api/drift/adopt-github-version   (scope-aware drift resolution)
 */
import apiClient from "./apiClient";

export interface WorkflowDriftDetail {
  workflow_id: number;
  workflow_name: string;
  workflow_filename: string;
  repo: string;
  branch: string;
  has_drift: boolean;
  actionsmanager_yaml: string | null;
  github_yaml: string | null;
  actionsmanager_sha: string | null;
  github_sha: string | null;
  last_checked: string;
  message: string;
  // Scope-aware drift metadata (issue: design-level drift fix)
  project_id?: number | null;
  repo_id?: number | null;
  is_shared_workflow?: boolean;
  has_repo_override?: boolean;
  override_id?: number | null;
  affected_repo_count?: number;
  affected_repos?: string[];
  source_repo_name?: string | null;
}

export interface ProjectDriftSummary {
  project_id: number;
  project_name: string;
  drift_count: number;
  drifted_workflows: WorkflowDriftDetail[];
  last_checked: string;
}

export interface WorkflowDriftResponse {
  workflow_id: number;
  workflow_name: string;
  workflow_filename: string;
  has_drift: boolean;
  drift_details: WorkflowDriftDetail[];
  last_checked: string;
}

export type DriftResolution = "use_github" | "restore_actionsmanager";
export type DriftDeliveryMode = "pr" | "direct";

export interface ResolveDriftRequest {
  github_user: string;
  repo: string;
  branch: string;
  resolution: DriftResolution;
  delivery_mode?: DriftDeliveryMode;
}

export interface ResolveDriftResponse {
  message: string;
  action: string;
  workflow_id: number;
  repo: string;
  branch: string;
  state?: "synced" | "drifted" | "pr_pending" | "unknown";
  stored_hash?: string;
  github_hash?: string;
  content_matches?: boolean;
  github_sha?: string;
  pr_result?: unknown;
}

export type AdoptResolutionMode =
  | "adopt_project_and_sync"
  | "adopt_local_only"
  | "create_repo_override";

export interface AdoptGithubVersionRequest {
  github_user: string;
  project_id: number;
  workflow_id: number;
  repo_id?: number;
  repo_name?: string;
  resolution_mode: AdoptResolutionMode;
  delivery_mode?: DriftDeliveryMode;
  target_repo_ids?: number[];
}

export interface AdoptGithubVersionResponse {
  success: boolean;
  message: string;
  resolution_mode: AdoptResolutionMode;
  updated_project_workflow: boolean;
  created_or_updated_override: {
    override_id: number;
    project_id: number;
    repo_id: number;
    workflow_id: number;
    workflow_name: string;
    source_repo_name: string;
    workflow_git_hash: string | null;
  } | null;
  affected_repos: string[];
  sync_results: unknown;
  new_drift_status: string;
}

export async function getProjectDrift(
  projectId: number,
  githubUser: string,
): Promise<ProjectDriftSummary> {
  const resp = await apiClient.get<ProjectDriftSummary>(
    `/api/projects/${projectId}/drift`,
    { params: { github_user: githubUser } },
  );
  return resp.data;
}

export async function getWorkflowDrift(
  workflowId: number,
  githubUser: string,
): Promise<WorkflowDriftResponse> {
  const resp = await apiClient.get<WorkflowDriftResponse>(
    `/api/workflows/${workflowId}/drift`,
    { params: { github_user: githubUser } },
  );
  return resp.data;
}

export async function resolveWorkflowDrift(
  workflowId: number,
  body: ResolveDriftRequest,
): Promise<ResolveDriftResponse> {
  const resp = await apiClient.post<ResolveDriftResponse>(
    `/api/workflows/${workflowId}/resolve-drift`,
    body,
  );
  return resp.data;
}

export async function adoptGithubVersion(
  body: AdoptGithubVersionRequest,
): Promise<AdoptGithubVersionResponse> {
  const resp = await apiClient.post<AdoptGithubVersionResponse>(
    `/api/drift/adopt-github-version`,
    body,
  );
  return resp.data;
}

