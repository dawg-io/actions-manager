/**
 * Pull Request API functions for Actions Manager
 * 
 * Provides functions to interact with the PR tracking endpoints.
 */

import config from "../config";

const BACKEND_URL = config.BACKEND_URL;

/**
 * Build common JSON headers. Authentication is handled by the HttpOnly session cookie.
 */
function writeHeaders(): Record<string, string> {
  return { "Content-Type": "application/json" };
}

export interface PRStatus {
  repo_name: string;
  pr_number: number;
  pr_url: string;
  pr_state: string;
  branch_name: string;
  target_branch: string;
  created_at: string;
  updated_at: string;
  /** Populated for cross-project PRs from a linked Standard/RWX project. */
  source_project_name?: string | null;
  mergeable?: boolean | null;
  mergeable_state?: string | null;
  draft?: boolean | null;
  can_merge?: boolean | null;
  merge_block_reason?: string | null;
  can_close?: boolean | null;
  close_block_reason?: string | null;
}

export interface ProjectPRStatus {
  project_state: string;
  pull_requests: PRStatus[];
  total_prs: number;
  open_prs: number;
  merged_prs: number;
  closed_prs: number;
  /**
   * Canonical reusable workflow IDs that must remain locked (`under_review`)
   * because an open PR campaign in some project sharing the workflow still
   * references them. The frontend uses this to avoid speculatively flipping
   * linked reusable workflow badges when a sibling caller's campaign is not
   * visible in this project's local `open_prs` count.
   */
  locked_workflow_ids?: number[];
}

export interface CreatePRsResponse {
  message?: string;
  results?: Record<string, any>;
  prs_created?: number;
  task_id?: string;
  status?: string;
  campaign_id?: number;
  /** Repos whose CODEOWNERS content was merged into an existing workflow/custom-file PR. */
  codeowners_merged_repos?: string[];
}

export interface PRTaskStatusResponse {
  status: string;
  repos: Record<string, { step: string; status: string; error?: string }>;
  results?: Record<string, any>;
  prs_created?: number;
  campaign_id?: number;
  error?: string;
  /** Repos whose CODEOWNERS content was merged into an existing workflow/custom-file PR. */
  codeowners_merged_repos?: string[];
}

export interface PreflightValidationResponse {
  status: string;
  validation_repo: string;
  last_preflight_run_at: string | null;
  last_preflight_pr_url: string | null;
}

/**
 * A single historical (merged or closed) pull request record returned by
 * GET /api/project-pr-history.
 *
 * ``source_project_name`` is only set when the PR was created by a *different*
 * project that is linked to the queried project via a reusable-workflow
 * relationship.  It is ``null`` when the PR belongs directly to the queried
 * project.
 */
export interface PRHistoryItem {
  pr_id: number;
  repo_name: string;
  pr_number: number;
  pr_url: string;
  pr_state: string; // "merged" | "closed"
  branch_name: string;
  target_branch: string;
  title: string | null;
  author: string | null;
  body: string | null;
  workflow_names: string | null;
  created_at: string;
  updated_at: string;
  merged_at: string | null;
  closed_at: string | null;
  /** Populated for cross-project PRs from a linked Standard/RWX project. */
  source_project_name: string | null;
}

/** Response envelope from GET /api/project-pr-history */
export interface PRHistoryResponse {
  pull_requests: PRHistoryItem[];
  total: number;
  merged_count: number;
  closed_count: number;
}

export interface PRCampaignPRItem extends PRHistoryItem {
  pr_state: "open" | "merged" | "closed" | string;
  actor?: string | null;
  file_names?: string | null;
  is_reusable_workflow_pr?: boolean;
  mergeable?: boolean | null;
  mergeable_state?: string | null;
  draft?: boolean | null;
  can_merge?: boolean | null;
  merge_block_reason?: string | null;
  can_close?: boolean | null;
  close_block_reason?: string | null;
}

export interface PRCampaign {
  campaign_id: string;
  campaign_name: string;
  campaign_status: "open" | "completed" | "cancelled" | "partially_completed" | "failed" | string;
  project_name: string;
  project_code: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  target_branches: string[];
  workflow_names: string[];
  custom_file_paths?: string[];
  repositories: string[];
  open_count: number;
  merged_count: number;
  closed_count: number;
  failed_count: number;
  completion_percentage: number;
  pull_requests: PRCampaignPRItem[];
}

export interface PRCampaignsResponse {
  campaigns: PRCampaign[];
  pull_requests: PRCampaignPRItem[];
  total_campaigns: number;
  active_campaigns: number;
  completed_campaigns: number;
  open_prs: number;
  merged_prs: number;
  closed_prs: number;
  repositories_affected: number;
}

/**
 * Create pull requests for a project's workflows
 * @param githubUser - GitHub username
 * @param projectName - Project name
 * @param selectedRepos - Optional array of repository names to create PRs for
 * @param selectedWorkflows - Optional array of workflow names to include in the PR
 * @param selectedReusableWorkflows - Optional array of reusable workflow names to include in the PR
 * @returns Promise with the response
 */
export async function createPullRequests(
  githubUser: string,
  projectName: string,
  selectedRepos?: string[],
  selectedWorkflows?: string[],
  selectedReusableWorkflows?: string[],
  selectedCustomFileIds?: number[],
  selectedCodeownersRepos?: string[]
): Promise<CreatePRsResponse> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/create-pull-requests`, {
      method: "POST",
      credentials: "include",
      headers: writeHeaders(),
      body: JSON.stringify({
        project_name: projectName,
        selected_repos: selectedRepos || null,
        selected_workflows: selectedWorkflows || null,
        selected_reusable_workflows: selectedReusableWorkflows || null,
        selected_custom_file_ids: selectedCustomFileIds ?? null,
        selected_codeowners_repos: selectedCodeownersRepos || null,
        async_mode: true
      }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `Failed to create pull requests: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Error creating pull requests:", error);
    throw error;
  }
}

/**
 * Get the status of a PR creation background task
 * @param taskId - The task ID returned by createPullRequests
 * @returns Promise with the task status
 */
export async function getCreatePullRequestsStatus(taskId: string): Promise<PRTaskStatusResponse> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/create-pull-requests/${taskId}`, {
      method: "GET",
      credentials: "include",
      headers: writeHeaders(),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `Failed to get PR creation status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Error getting PR creation status:", error);
    throw error;
  }
}

export async function runPreflightValidation(
  githubUser: string,
  projectName: string,
  selectedWorkflows?: string[]
): Promise<PreflightValidationResponse> {
  const response = await fetch(`${BACKEND_URL}/api/run-preflight-validation`, {
    method: "POST",
    credentials: "include",
    headers: writeHeaders(),
    body: JSON.stringify({
      project_name: projectName,
      selected_workflows: selectedWorkflows || null,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || `Failed to run preflight validation: ${response.status}`);
  }

  return await response.json();
}

export interface PreflightValidationStatusResponse {
  status: string;
  validation_repo: string | null;
  last_preflight_run_at: string | null;
  last_preflight_error: string | null;
  last_preflight_pr_url: string | null;
  pr_state: string | null;
  mergeable?: boolean | null;
  mergeable_state?: string | null;
  draft?: boolean | null;
  can_merge?: boolean | null;
  merge_block_reason?: string | null;
  can_close?: boolean | null;
  close_block_reason?: string | null;
}

export async function getPreflightValidationStatus(
  githubUser: string,
  projectName: string,
  refreshFromGitHub: boolean = true
): Promise<PreflightValidationStatusResponse> {
  const params = new URLSearchParams({
    github_user: githubUser,
    project_name: projectName,
    refresh_from_github: refreshFromGitHub.toString(),
  });

  const response = await fetch(`${BACKEND_URL}/api/preflight-validation-status?${params.toString()}`, {
    method: "GET",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || `Failed to get preflight status: ${response.status}`);
  }

  return await response.json();
}

export interface ClosePreflightValidationResponse {
  message: string;
  status: string;
  last_preflight_pr_url: string | null;
  branch_deleted: boolean;
  branch_delete_warning: string | null;
}

export async function closePreflightValidationPR(
  githubUser: string,
  projectName: string,
  cleanupBranch: boolean = true
): Promise<ClosePreflightValidationResponse> {
  const response = await fetch(`${BACKEND_URL}/api/close-preflight-validation-pr`, {
    method: "PATCH",
    credentials: "include",
    headers: writeHeaders(),
    body: JSON.stringify({
      project_name: projectName,
      cleanup_branch: cleanupBranch,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || `Failed to close validation PR: ${response.status}`);
  }

  return await response.json();
}

export interface MergePreflightValidationResponse {
  message: string;
  status: string;
  last_preflight_pr_url: string | null;
  merge_method?: string | null;
  branch_deleted: boolean;
  branch_delete_warning: string | null;
}

export async function mergePreflightValidationPR(
  githubUser: string,
  projectName: string,
  cleanupBranch: boolean = true
): Promise<MergePreflightValidationResponse> {
  const response = await fetch(`${BACKEND_URL}/api/merge-preflight-validation-pr`, {
    method: "PUT",
    credentials: "include",
    headers: writeHeaders(),
    body: JSON.stringify({
      project_name: projectName,
      cleanup_branch: cleanupBranch,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || `Failed to merge validation PR: ${response.status}`);
  }

  return await response.json();
}

/**
 * Get the PR status for a project
 * @param githubUser - GitHub username
 * @param projectName - Project name
 * @param refreshFromGitHub - If true, fetches current state from GitHub API (slow). If false, uses cached database state (fast, default).
 * @returns Promise with the project PR status
 */
export async function getProjectPRStatus(
  githubUser: string,
  projectName: string,
  refreshFromGitHub: boolean = false
): Promise<ProjectPRStatus> {
  try {
    const params = new URLSearchParams({
      github_user: githubUser,
      project_name: projectName,
      refresh_from_github: refreshFromGitHub.toString()
    });
    
    const response = await fetch(
      `${BACKEND_URL}/api/project-pr-status?${params.toString()}`,
      {
        method: "GET",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
      }
    );

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `Failed to get PR status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Error getting project PR status:", error);
    throw error;
  }
}

export interface MergePullRequestResponse {
  message: string;
  pr_number: number;
  repo_name: string;
  sha: string | null;
  merged: boolean;
  /** GitHub merge strategy that succeeded: merge, squash, or rebase. */
  merge_method?: string | null;
  /** True when ActionsManager successfully deleted the source branch after merge. */
  branch_deleted: boolean;
  /** Non-null when deletion was skipped or failed; contains a human-readable reason. */
  branch_delete_warning: string | null;
}

/**
 * Merge a pull request
 * @param githubUser - GitHub username
 * @param projectName - Project name
 * @param repoName - Repository name (owner/repo format)
 * @param prNumber - Pull request number
 * @returns Promise with the merge response (includes branch_deleted / branch_delete_warning)
 */
export async function mergePullRequest(
  githubUser: string,
  projectName: string,
  repoName: string,
  prNumber: number
): Promise<MergePullRequestResponse> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/merge-pull-request`, {
      method: "PUT",
      credentials: "include",
      headers: writeHeaders(),
      body: JSON.stringify({
        project_name: projectName,
        repo_name: repoName,
        pr_number: prNumber,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `Failed to merge pull request: ${response.status}`);
    }

    return await response.json() as MergePullRequestResponse;
  } catch (error) {
    console.error("Error merging pull request:", error);
    throw error;
  }
}

/**
 * Close a pull request without merging
 * @param githubUser - GitHub username
 * @param projectName - Project name
 * @param repoName - Repository name (owner/repo format)
 * @param prNumber - Pull request number
 * @returns Promise with the response
 */
export async function closePullRequest(
  githubUser: string,
  projectName: string,
  repoName: string,
  prNumber: number
): Promise<any> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/close-pull-request`, {
      method: "PATCH",
      credentials: "include",
      headers: writeHeaders(),
      body: JSON.stringify({
        project_name: projectName,
        repo_name: repoName,
        pr_number: prNumber,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `Failed to close pull request: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Error closing pull request:", error);
    throw error;
  }
}

/**
 * Fetch PR history (merged and closed PRs) for a project.
 *
 * This is a read-only endpoint — open PRs are excluded from the response.
 *
 * @param githubUser     - GitHub username
 * @param projectName    - Project name
 * @param stateFilter    - "all" (default), "merged", or "closed"
 * @param repoFilter     - Optional full repo name (owner/repo) to narrow results
 * @param workflowFilter - Optional workflow name substring to narrow results
 * @returns Promise with PR history response
 */
export async function getPRHistory(
  githubUser: string,
  projectName: string,
  stateFilter: "all" | "merged" | "closed" = "all",
  repoFilter?: string,
  workflowFilter?: string
): Promise<PRHistoryResponse> {
  try {
    const params = new URLSearchParams({
      github_user: githubUser,
      project_name: projectName,
      state_filter: stateFilter,
    });
    if (repoFilter) params.set("repo_filter", repoFilter);
    if (workflowFilter) params.set("workflow_filter", workflowFilter);

    const response = await fetch(
      `${BACKEND_URL}/api/project-pr-history?${params.toString()}`,
      {
        method: "GET",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
      }
    );

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `Failed to fetch PR history: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Error fetching PR history:", error);
    throw error;
  }
}

/**
 * Fetch PR Campaigns for a project.
 *
 * Campaigns are derived from existing PR tracking rows, preserving old PR
 * History data while surfacing active rollout management in one page.
 */
export async function getPRCampaigns(
  githubUser: string,
  projectName: string,
  refreshFromGitHub: boolean = false
): Promise<PRCampaignsResponse> {
  try {
    const params = new URLSearchParams({
      github_user: githubUser,
      project_name: projectName,
      refresh_from_github: refreshFromGitHub.toString(),
    });

    const response = await fetch(
      `${BACKEND_URL}/api/project-pr-campaigns?${params.toString()}`,
      {
        method: "GET",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
      }
    );

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `Failed to fetch PR campaigns: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Error fetching PR campaigns:", error);
    throw error;
  }
}
