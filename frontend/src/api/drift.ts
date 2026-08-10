/**
 * API client for workflow drift detection (issue: "Detect GitHub-side workflow changes").
 *
 * Wraps the v2 endpoints exposed by backend/workflows.py:
 *   GET  /api/projects/{project_id}/drift
 *   GET  /api/workflows/{workflow_id}/drift
 *   POST /api/workflows/{workflow_id}/resolve-drift
 *   POST /api/drift/adopt-github-version   (scope-aware drift resolution)
 *   POST /api/projects/{project_id}/drift/bulk-resolve   (bulk-fix workflow drift)
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
  /**
   * The check could not be completed (revoked token, rate limit, GitHub 5xx).
   * has_drift carries no meaning when this is true — the state is unknown, so
   * the UI must not present it as either drifted or clean.
   */
  check_failed?: boolean;
  /**
   * The workflow file is absent from GitHub. github_yaml is null rather than
   * empty, and there is nothing to adopt — the diff view must say so instead
   * of rendering a blank "Current GitHub version" pane.
   */
  deleted_in_github?: boolean;
}

export interface ProjectDriftSummary {
  project_id: number;
  project_name: string;
  drift_count: number;
  drifted_workflows: WorkflowDriftDetail[];
  /**
   * When the reported state was established — null when no check has ever run.
   * Not the time of the request: an empty list from a check that never
   * happened must not read as "verified clean just now".
   */
  last_checked: string | null;
  /** Workflow/repo pairs GitHub could not be queried about; >0 means the picture is incomplete. */
  unchecked_count?: number;
  /**
   * Why the reported state may be older than it looks — e.g. the background
   * sweep cannot check this project because its owner has no saved token.
   * Null when automatic checking is working normally.
   */
  stale_reason?: string | null;
}

export type DriftResolution = "use_github" | "restore_actionsmanager";
export type DriftDeliveryMode = "pr" | "direct";

export interface ResolveDriftRequest {
  github_user: string;
  repo: string;
  branch: string;
  resolution: DriftResolution;
  delivery_mode?: DriftDeliveryMode;
  /**
   * The GitHub blob SHA this decision was based on. The backend refuses a
   * direct push with 409 if GitHub has moved on since, so a stale drift view
   * can't silently revert someone else's fix.
   */
  expected_github_sha?: string | null;
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
  // The branch whose drift is being resolved — without it the backend adopts
  // from the repo's default branch, which may not be the file the user saw.
  branch?: string;
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

/**
 * Project drift summary.
 *
 * Serves the last known state by default, which costs no GitHub API calls — so
 * opening a project is free however often it is done. Pass `refresh` to run a
 * live check, which is what the "Check now" action does.
 */
export async function getProjectDrift(
  projectId: number,
  githubUser: string,
  options?: { refresh?: boolean },
): Promise<ProjectDriftSummary> {
  const resp = await apiClient.get<ProjectDriftSummary>(
    `/api/projects/${projectId}/drift`,
    {
      params: {
        github_user: githubUser,
        ...(options?.refresh ? { refresh: true } : {}),
      },
    },
  );
  return resp.data;
}

export interface WorkflowDriftResponse {
  workflow_id: number;
  workflow_name: string;
  workflow_filename: string;
  has_drift: boolean;
  drift_details: WorkflowDriftDetail[];
  last_checked: string;
}

/**
 * Live drift detail for one workflow, including GitHub's current content.
 *
 * The cached project summary deliberately omits `github_yaml`, because a
 * stored snapshot may no longer match GitHub. This fetches the real thing when
 * a diff is actually opened.
 */
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

export interface BulkResolveDriftItem {
  workflow_id: number;
  repo: string;
  branch: string;
  /** See ResolveDriftRequest.expected_github_sha. */
  expected_github_sha?: string | null;
}

export interface BulkResolveDriftRequest {
  github_user: string;
  items: BulkResolveDriftItem[];
  resolution: DriftResolution;
  delivery_mode?: DriftDeliveryMode;
}

export interface BulkResolveDriftItemResult {
  workflow_id: number;
  repo: string;
  branch: string;
  success: boolean;
  message: string;
  pr_url?: string | null;
}

export interface BulkResolveDriftResponse {
  success: boolean;
  results: BulkResolveDriftItemResult[];
}

export async function bulkResolveWorkflowDrift(
  projectId: number,
  body: BulkResolveDriftRequest,
): Promise<BulkResolveDriftResponse> {
  const resp = await apiClient.post<BulkResolveDriftResponse>(
    `/api/projects/${projectId}/drift/bulk-resolve`,
    body,
  );
  return resp.data;
}

