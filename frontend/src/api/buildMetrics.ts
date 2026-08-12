/**
 * API client for project build metrics (issue #689).
 *
 * Wraps the endpoint exposed by backend/build_metrics.py:
 *   GET /api/projects/{project_id}/build-metrics
 *
 * The default request is served from stored runs and costs no GitHub API calls;
 * `refresh` asks the backend to re-sync from GitHub first.
 */
import apiClient from "./apiClient";

export interface TrendPoint {
  date: string;
  total: number;
  success: number;
  failure: number;
}

export interface WorkflowBreakdown {
  workflow_name: string;
  /** Delivered filename — the stable key to pass back as `workflow` to scope. */
  workflow_filename: string;
  total: number;
  /** Null when no run in the window produced a pass/fail verdict. */
  success_rate: number | null;
  avg_duration_seconds: number | null;
  /**
   * This workflow's Actions page on GitHub, pointing at the repo it most
   * recently ran in. Null when that repo is no longer part of the project, in
   * which case the row renders as plain text rather than a dead link.
   */
  actions_url: string | null;
}

export interface RecentRun {
  github_run_id: number;
  run_number: number | null;
  workflow_name: string;
  /** "owner/repo" — null when the repo has left the project. */
  repo: string | null;
  branch: string;
  event: string | null;
  status: string | null;
  /** Null while the run is still in flight. */
  conclusion: string | null;
  created_at: string | null;
  duration_seconds: number | null;
  /** GitHub's own run URL, stored at sync time. */
  html_url: string | null;
}

export interface BuildMetricsSummary {
  project_id: number;
  project_name: string;
  /** History window actually applied, after clamping to the account's tier. */
  window_days: number;
  /**
   * When runs were last pulled from GitHub — null when that has never happened.
   * Not the time of this request: an empty result from a sync that never ran
   * must not read as "verified quiet just now".
   */
  last_synced: string | null;
  total_runs: number;
  /**
   * Runs that produced a pass/fail verdict — the denominator of success_rate.
   * Cancelled, skipped and in-flight runs count towards total_runs only.
   */
  decided_runs: number;
  conclusion_counts: Record<string, number>;
  /** Null rather than 0 when nothing has been decided: "no data" is not "all failed". */
  success_rate: number | null;
  avg_duration_seconds: number | null;
  p50_duration_seconds: number | null;
  p95_duration_seconds: number | null;
  avg_queue_seconds: number | null;
  /**
   * The workflow every figure above is scoped to, echoed by the server. Null
   * means the whole project.
   */
  selected_workflow: string | null;
  trend: TrendPoint[];
  /**
   * Always every workflow in the window, even while scoped — this is what the
   * switcher is built from, so it must never collapse to the current
   * selection.
   */
  workflows: WorkflowBreakdown[];
  /**
   * Newest first, capped server-side. Narrowed by the `onlyFailures` option;
   * every other field is always computed over the whole window, so filtering
   * this list never moves the success rate.
   */
  recent_runs: RecentRun[];
  /** True when the GitHub sync failed — the numbers are the last known ones. */
  sync_failed: boolean;
  sync_message: string | null;
}

export async function getProjectBuildMetrics(
  projectId: number,
  githubUser: string,
  options?: { refresh?: boolean; days?: number; onlyFailures?: boolean; workflow?: string | null },
): Promise<BuildMetricsSummary> {
  const resp = await apiClient.get<BuildMetricsSummary>(
    `/api/projects/${projectId}/build-metrics`,
    {
      params: {
        github_user: githubUser,
        ...(options?.refresh ? { refresh: true } : {}),
        ...(options?.days ? { days: options.days } : {}),
        ...(options?.onlyFailures ? { only_failures: true } : {}),
        ...(options?.workflow ? { workflow: options.workflow } : {}),
      },
    },
  );
  return resp.data;
}
