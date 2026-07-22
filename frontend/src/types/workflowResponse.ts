// Shared types for workflow update responses

/**
 * Individual workflow result from backend PR-based workflow publishing.
 * Represents the result of publishing workflows to a specific repo/branch combination.
 */
export interface WorkflowResult {
  /** Status of the workflow publishing operation */
  status: "pr_created" | "pr_updated" | "error";
  /** GitHub PR URL (if PR was created/updated) */
  pr_url?: string;
  /** GitHub PR number (if PR was created/updated) */
  pr_number?: number;
  /** List of workflow names that were successfully committed */
  workflows_committed?: string[];
  /** List of workflow-specific errors or warnings */
  workflow_errors?: string[];
  /** Error message (if status is "error") */
  error?: string;
}

/**
 * Response from workflow update API endpoint.
 * Maps repo/branch combinations to their publishing results.
 */
export interface WorkflowUpdateResponse {
  /** Error message if the entire operation failed */
  error?: string;
  /** 
   * Results keyed by repo/branch combination.
   * Key format: "owner/repo on branch"
   * Value can be WorkflowResult (new PR-based format) or number (legacy status code)
   */
  results?: Record<string, WorkflowResult | number>;
}
