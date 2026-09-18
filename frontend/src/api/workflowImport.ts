/**
 * Workflow Import API client.
 *
 * Provides functions to discover, preview, and import existing GitHub Actions
 * workflows into ActionsManager projects.
 */

import config from '../config';

const API_BASE_URL = config.BACKEND_URL;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DiscoveredWorkflow {
  repo_name: string;
  branch: string;
  file_name: string;
  path: string;
  blob_sha: string | null;
  /**
   * True when the file is triggered by `workflow_call`, i.e. a reusable workflow.
   * Optional so a frontend running ahead of the backend degrades to "not
   * reusable" rather than failing to render the scan.
   */
  is_reusable?: boolean;
}

export interface DiscoveryRepoResult {
  repo_name: string;
  branch: string;
  workflows: DiscoveredWorkflow[];
  warning: string | null;
  error: string | null;
}

export interface CrossRepoMatch {
  file_name: string;
  path: string;
  repos: Array<{ repo_name: string; branch: string; blob_sha: string | null }>;
  identical_across_repos: boolean;
}

export interface DiscoveryResponse {
  repositories_scanned: number;
  workflows_found: number;
  results: DiscoveryRepoResult[];
  cross_repo_matches: CrossRepoMatch[];
}

export interface PreviewResponse {
  repo_name: string;
  branch: string;
  path: string;
  file_name: string;
  content: string;
  blob_sha: string | null;
  is_reusable?: boolean;
}

export interface ImportWorkflowItem {
  source_repo: string;
  source_branch: string;
  workflow_path: string;
  content_sha?: string | null;
}

export interface ImportResult {
  workflow_path: string;
  source_repo: string;
  status: 'success' | 'error';
  message: string;
  workflow_name?: string | null;
}

export interface ImportResponse {
  message: string;
  import_mode: string;
  results: ImportResult[];
  pr_state: string | null;
  pr_results: Record<string, unknown> | null;
  /** Set when the workflows were filed into a different project than the one open. */
  destination_project_name?: string | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build JSON headers. Authentication is handled by the HttpOnly session cookie.
 */
function buildHeaders(_githubUser: string): Record<string, string> {
  return {
    'Content-Type': 'application/json',
  };
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Discover existing GitHub Actions workflows in project repositories.
 */
export async function discoverWorkflows(
  projectId: number,
  githubUser: string,
  projectName: string
): Promise<DiscoveryResponse> {
  const params = new URLSearchParams({
    github_user: githubUser,
    project_name: projectName,
  });

  const response = await fetch(
    `${API_BASE_URL}/api/projects/${projectId}/workflow-import/discover?${params}`,
    {
      method: 'GET',
      credentials: 'include',
      headers: buildHeaders(githubUser),
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Discovery failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Preview a specific workflow file content from GitHub.
 */
export async function previewWorkflow(
  projectId: number,
  githubUser: string,
  projectName: string,
  repoName: string,
  branch: string,
  workflowPath: string
): Promise<PreviewResponse> {
  const params = new URLSearchParams({
    github_user: githubUser,
    project_name: projectName,
    repo_name: repoName,
    branch,
    workflow_path: workflowPath,
  });

  const response = await fetch(
    `${API_BASE_URL}/api/projects/${projectId}/workflow-import/preview?${params}`,
    {
      method: 'GET',
      credentials: 'include',
      headers: buildHeaders(githubUser),
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Preview failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Import selected workflows into ActionsManager.
 *
 * @param importMode - "save_local_only" or "save_and_create_pr_campaign"
 * @param destinationProjectId - File the workflows into this Reusable Workflow
 *   Project instead of the one being viewed. The source repository is still
 *   validated against the open project. An id rather than a name: project names
 *   are only unique per owner, so a name can resolve to someone else's project.
 */
export async function importWorkflows(
  projectId: number,
  githubUser: string,
  projectName: string,
  workflows: ImportWorkflowItem[],
  importMode: 'save_local_only' | 'save_and_create_pr_campaign' = 'save_local_only',
  targetRepos?: string[],
  destinationProjectId?: number
): Promise<ImportResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/projects/${projectId}/workflow-import`,
    {
      method: 'POST',
      credentials: 'include',
      headers: buildHeaders(githubUser),
      body: JSON.stringify({
        github_user: githubUser,
        project_name: projectName,
        workflows,
        import_mode: importMode,
        target_repos: targetRepos,
        destination_project_id: destinationProjectId,
      }),
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Import failed: ${response.status}`);
  }

  return response.json();
}
