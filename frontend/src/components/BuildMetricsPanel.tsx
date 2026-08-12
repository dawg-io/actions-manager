/* eslint-disable no-restricted-syntax -- Need inline style to size trend bars from runtime run counts */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw, AlertTriangle } from "lucide-react";
import { getProjectBuildMetrics, BuildMetricsSummary, TrendPoint, RecentRun } from "../api/buildMetrics";
import { Card } from "./ui";
import { formatRelativeTime } from "../utils/timeFormat";
import { getStatusIcon } from "../utils/statusUtils";

export interface BuildMetricsPanelProps {
  projectId: number;
  user: string;
}

/** "1m 42s" — short enough for a stat tile, exact enough to compare runs. */
export function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds < 0) return "—";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  if (minutes < 60) return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

// Matches the token-based select styling in WorkspaceNotifications.tsx.
const selectClassName =
  "h-9 rounded-md border border-border bg-container px-2 text-sm text-text-primary " +
  "disabled:opacity-50 dark:border-border-dark dark:bg-container-dark dark:text-text-primary-dark";

const StatTile: React.FC<{ label: string; value: string; hint?: string; testId: string }> = ({
  label, value, hint, testId,
}) => (
  <Card className="p-4">
    <div className="text-xs uppercase tracking-wide text-text-secondary dark:text-text-secondary-dark">{label}</div>
    <div className="mt-1 text-2xl font-semibold" data-testid={testId}>{value}</div>
    {hint && <div className="mt-1 text-xs text-text-secondary dark:text-text-secondary-dark">{hint}</div>}
  </Card>
);

/**
 * Daily run counts as bars. Hand-rolled rather than pulling in a chart library
 * for one figure — the same reasoning as PlanUsagePill's meter.
 */
const TrendBars: React.FC<{ trend: TrendPoint[]; successRate: number | null }> = ({ trend, successRate }) => {
  const peak = Math.max(1, ...trend.map((point) => point.total));
  const label = successRate === null
    ? `Daily runs over the last ${trend.length} days`
    : `Daily runs over the last ${trend.length} days, ${successRate}% success`;

  return (
    <div className="flex h-24 items-end gap-px" role="img" aria-label={label} data-testid="build-metrics-trend">
      {trend.map((point) => (
        <div
          key={point.date}
          className={point.total ? "flex-1 bg-success" : "flex-1 bg-border-light dark:bg-border-dark"}
          style={{ height: `${(point.total / peak) * 100}%`, minHeight: "2px" }}
          title={`${point.date}: ${point.total} run(s), ${point.success} passed, ${point.failure} failed`}
          data-testid="build-metrics-trend-bar"
        >
          <div
            className="w-full bg-danger"
            style={{ height: point.total ? `${(point.failure / point.total) * 100}%` : "0%" }}
          />
        </div>
      ))}
    </div>
  );
};

/**
 * One run, linked to itself on GitHub. The link is GitHub's own `html_url`
 * stored at sync time rather than a URL assembled here — the same way PR links
 * are handled elsewhere in the app.
 */
const RunRow: React.FC<{ run: RecentRun }> = ({ run }) => {
  const outcome = run.conclusion ?? run.status ?? "unknown";
  const label = [
    run.workflow_name,
    run.run_number ? `run ${run.run_number}` : null,
    run.repo,
    run.branch,
    outcome,
  ].filter(Boolean).join(", ");

  const detail = (
    <>
      <span aria-hidden="true">{getStatusIcon(outcome)}</span>
      <span className="font-medium">{run.workflow_name}</span>
      {run.run_number && <span className="text-text-secondary dark:text-text-secondary-dark">#{run.run_number}</span>}
      <span className="truncate text-text-secondary dark:text-text-secondary-dark">
        {run.repo} · {run.branch}
      </span>
      <span className="ml-auto shrink-0 text-text-secondary dark:text-text-secondary-dark">
        {formatDuration(run.duration_seconds)}
        {run.created_at && ` · ${formatRelativeTime(run.created_at)}`}
      </span>
    </>
  );

  // No html_url means the row still has to render — it just can't be a link,
  // matching how buildGithubWorkflowUrl's callers degrade rather than guess.
  if (!run.html_url) {
    return <div className="flex items-center gap-2 py-1 text-sm" data-testid="build-metrics-run">{detail}</div>;
  }

  return (
    <a
      className="flex items-center gap-2 rounded py-1 text-sm hover:underline"
      href={run.html_url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${label} — open in GitHub`}
      data-testid="build-metrics-run"
    >
      {detail}
    </a>
  );
};

const BuildMetricsPanel: React.FC<BuildMetricsPanelProps> = ({ projectId, user }) => {
  const [summary, setSummary] = useState<BuildMetricsSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Server-side, so the toggle searches the whole window rather than only the
  // rows already fetched.
  const [onlyFailures, setOnlyFailures] = useState(false);
  // Empty string = the whole project. Scoping is server-side so the numbers,
  // the trend and the run list all describe the same set of runs.
  const [workflow, setWorkflow] = useState("");
  // Discards out-of-order responses, so a slow refresh can't overwrite a newer
  // result. Same idiom as DriftDetection's requestIdRef.
  const requestIdRef = useRef(0);

  const load = useCallback(async (opts?: { refresh?: boolean }) => {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const result = await getProjectBuildMetrics(projectId, user, {
        refresh: opts?.refresh,
        onlyFailures,
        workflow,
      });
      if (requestId !== requestIdRef.current) return;
      // Rendered straight from the response — no refetch, no remount.
      setSummary(result);
    } catch {
      if (requestId !== requestIdRef.current) return;
      setError("Could not load build metrics.");
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  }, [projectId, user, onlyFailures, workflow]);

  // Switching project must not leave the previous project's numbers, trend and
  // run links on screen under the new project's heading for the length of a
  // round trip. The scope is reset too — a workflow filename from one project
  // means nothing in another.
  useEffect(() => {
    setSummary(null);
    setWorkflow("");
    setOnlyFailures(false);
  }, [projectId, user]);

  useEffect(() => {
    if (projectId && user) load();
  }, [projectId, user, load]);

  const successLabel = summary?.success_rate === null || summary?.success_rate === undefined
    ? "—"
    : `${summary.success_rate}%`;

  const scopedLabel = summary?.selected_workflow
    ? summary.workflows.find((w) => w.workflow_filename === summary.selected_workflow)?.workflow_name
      ?? summary.selected_workflow
    : null;
  // A workflow that has left the project keeps its option, so the control never
  // silently displays "All workflows" while the numbers below are scoped.
  const scopeMissingFromList = Boolean(
    workflow && !summary?.workflows.some((w) => w.workflow_filename === workflow),
  );

  return (
    <div className="p-6" data-testid="build-metrics-panel">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Build Metrics</h2>
          {summary && (
            <p className="text-sm text-text-secondary dark:text-text-secondary-dark">
              Last {summary.window_days} days · {scopedLabel ?? "all workflows"} ·{" "}
              {summary.last_synced
                ? `synced ${formatRelativeTime(summary.last_synced)}`
                : "not synced yet"}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Outside the "has runs" guard below on purpose: scoping to a
              workflow with no runs must not hide the control that got you
              there, or there is no way back to the whole project. */}
          {summary && summary.workflows.length > 0 && (
            <select
              className={selectClassName}
              value={workflow}
              onChange={(event) => setWorkflow(event.target.value)}
              disabled={loading}
              aria-label="Scope metrics to a workflow"
              data-testid="build-metrics-workflow-filter"
            >
              <option value="">All workflows</option>
              {summary.workflows.map((item) => (
                <option key={item.workflow_filename} value={item.workflow_filename}>
                  {item.workflow_name}
                </option>
              ))}
              {scopeMissingFromList && <option value={workflow}>{workflow}</option>}
            </select>
          )}
          <button
            className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm disabled:opacity-50 dark:border-border-dark"
            onClick={() => load({ refresh: true })}
            disabled={loading}
            data-testid="build-metrics-refresh"
          >
            <RefreshCw size={16} aria-hidden="true" />
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      {summary?.sync_failed && (
        // Shown alongside the numbers, not instead of them: they are the last
        // known values, and hiding them would be less useful than flagging them.
        <div
          className="mb-4 flex items-start gap-2 rounded-md border border-warning p-3 text-sm"
          data-testid="build-metrics-sync-warning"
        >
          <AlertTriangle size={16} aria-hidden="true" />
          <span>{summary.sync_message ?? "Could not refresh from GitHub. Showing the last known data."}</span>
        </div>
      )}

      {summary?.total_runs === 0 && (
        <p className="text-sm text-text-secondary dark:text-text-secondary-dark" data-testid="build-metrics-empty">
          {scopedLabel
            ? `No runs for ${scopedLabel} in the last ${summary.window_days} days.`
            : `No runs recorded in the last ${summary.window_days} days.`}
        </p>
      )}

      {summary && summary.total_runs > 0 && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <StatTile
              label="Success rate"
              value={successLabel}
              hint={`${summary.decided_runs} decided of ${summary.total_runs} runs`}
              testId="build-metrics-success-rate"
            />
            <StatTile label="Total runs" value={String(summary.total_runs)} testId="build-metrics-total-runs" />
            <StatTile label="Avg duration" value={formatDuration(summary.avg_duration_seconds)} testId="build-metrics-avg-duration" />
            <StatTile label="p95 duration" value={formatDuration(summary.p95_duration_seconds)} testId="build-metrics-p95-duration" />
            <StatTile label="Avg queue" value={formatDuration(summary.avg_queue_seconds)} testId="build-metrics-avg-queue" />
          </div>

          <Card className="mt-4 p-4">
            <div className="mb-2 text-sm font-medium">Runs per day</div>
            <TrendBars trend={summary.trend} successRate={summary.success_rate} />
          </Card>
        </>
      )}

      {/* Always project-wide, and rendered whether or not the current scope has
          runs — this is the index you navigate with, so it has to survive
          scoping to a quiet workflow. */}
      {summary && summary.workflows.length > 0 && (
        <Card className="mt-4 p-4">
          <div className="mb-2 text-sm font-medium">By workflow</div>
          <div className="space-y-1 text-sm">
            {summary.workflows.map((item) => {
              const isSelected = item.workflow_filename === summary.selected_workflow;
              return (
                <div
                  key={item.workflow_filename}
                  className={`flex items-center justify-between gap-4 rounded px-1 ${
                    isSelected ? "bg-hover-bg dark:bg-hover-dark-bg" : ""
                  }`}
                >
                  <button
                    type="button"
                    className="truncate text-left hover:underline"
                    onClick={() => setWorkflow(isSelected ? "" : item.workflow_filename)}
                    aria-current={isSelected}
                    aria-label={
                      isSelected
                        ? `Stop scoping to ${item.workflow_name}`
                        : `Scope metrics to ${item.workflow_name}`
                    }
                    data-testid={`build-metrics-workflow-row-${item.workflow_filename}`}
                  >
                    {item.workflow_name}
                  </button>
                  <span className="ml-auto shrink-0 text-text-secondary dark:text-text-secondary-dark">
                    {item.total} run{item.total === 1 ? "" : "s"} ·{" "}
                    {item.success_rate === null ? "—" : `${item.success_rate}%`} ·{" "}
                    {formatDuration(item.avg_duration_seconds)}
                  </span>
                  {/* A sibling of the scope button, not nested inside it —
                      clicking through to GitHub must not also change scope. */}
                  {item.actions_url && (
                    <a
                      className="shrink-0 hover:underline"
                      href={item.actions_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label={`${item.workflow_name} — open in GitHub`}
                    >
                      →
                    </a>
                  )}
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {summary && summary.total_runs > 0 && (
        <Card className="mt-4 p-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-sm font-medium">Recent runs</div>
            <button
              className="rounded-md border border-border px-2 py-1 text-xs disabled:opacity-50 dark:border-border-dark"
              onClick={() => setOnlyFailures((value) => !value)}
              disabled={loading}
              aria-pressed={onlyFailures}
              data-testid="build-metrics-failures-toggle"
            >
              {onlyFailures ? "Showing failures" : "Failures only"}
            </button>
          </div>
          {summary.recent_runs.length === 0 ? (
            <p
              className="text-sm text-text-secondary dark:text-text-secondary-dark"
              data-testid="build-metrics-runs-empty"
            >
              {onlyFailures
                ? `No failed runs in the last ${summary.window_days} days.`
                : "No runs to show."}
            </p>
          ) : (
            <div className="divide-y divide-border dark:divide-border-dark">
              {summary.recent_runs.map((run) => (
                <RunRow key={run.github_run_id} run={run} />
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
};

export default BuildMetricsPanel;
