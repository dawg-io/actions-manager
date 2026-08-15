import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  closePreflightValidationPR,
  createPullRequests,
  getCreatePullRequestsStatus,
  getPreflightValidationStatus,
  mergePreflightValidationPR,
  runPreflightValidation,
} from "../api/pullRequests";
import { deployCodeowners } from "../api/codeowners";
import { Button } from "./ui/button";
import { getDocsUrl } from "../help/helpLinks";
import { normalizeWorkflowFilename } from "../utils/workflowFilename";

interface CreatePRModalProps {
  user: string;
  projectName: string;
  repositories: Array<{ name: string; full_name?: string }>;
  workflows: Array<{ name: string; status?: string }>;
  reusableWorkflows?: Array<{ name: string; status?: string; sourceRepo?: string }>;
  customFiles?: Array<{ id: number; file_path: string; file_status: string; pending_delete: boolean }>;
  /** Repos available for CODEOWNERS inclusion in this campaign. */
  codeownersRepos?: string[];
  validationRepo?: string | null;
  preflightRequired?: boolean;
  preflightStatus?: string | null;
  preflightRunAt?: string | null;
  preflightError?: string | null;
  preflightPrUrl?: string | null;
  onPreflightStatusChange?: (status: {
    status: string;
    runAt?: string | null;
    error?: string | null;
    prUrl?: string | null;
  }) => void;
  onClose: () => void;
  onSuccess: (selectedWorkflowNames: string[], selectedReusableWorkflowNames: string[], selectedCustomFileIds: number[], selectedCodeownersRepos: string[]) => void;
}

// ─── Pure helpers (no component state) ──────────────────────────────────────

function getPreflightStatusMessage(status: string | null, prState: string | null): string {
  switch (status || "not_run") {
    case "closed":
      return "The validation PR was closed without merging. Preflight was not approved. Re-run preflight after updating the workflow changes.";
    case "failed":
      return "ActionsManager could not create or manage the validation PR. Check repository access, branch permissions, and workflow write permissions.";
    case "running":
      return "Creating a validation PR in the validation repository. Refresh status if this takes longer than expected.";
    case "waiting_for_checks": // legacy
    case "validation_pr_open":
      return prState === "open"
        ? "A validation PR is open. Review the generated workflow changes in GitHub. Merge the validation PR to approve preflight, or close it if the changes need work."
        : "A validation PR was created. Refresh status to confirm whether it is open, merged, or closed.";
    case "passed":
      return "Preflight approved. The validation PR was merged, so the generated workflow changes were approved in the validation repository. You can now create the real PR Campaign.";
    case "stale":
      return "Preflight is stale. The workflow changes have changed since the last validation PR was approved. Re-run preflight to validate the current changes before creating the campaign.";
    case "validation_repo_inaccessible":
      return "ActionsManager cannot access the validation repository. Ensure the GitHub token has read access to pull requests in the validation repository. For GitHub Apps, verify the installation grants 'Pull requests: read' permission. For personal access tokens, the 'repo' scope (classic) or 'Pull requests: read' permission (fine-grained) is required.";
    case "not_configured":
      return "No validation repository is configured for this project.";
    default:
      return "No preflight has been run yet. Run preflight to create a validation PR with the generated workflow changes.";
  }
}

function getPreflightRequiredMessage(
  status: string | null,
  requiresPreflight: boolean,
  preflightPassed: boolean
): string | null {
  if (!requiresPreflight || preflightPassed) return null;
  switch (status || "not_run") {
    case "closed":
      return "Preflight is required before creating this campaign. The validation PR was closed without merge, so preflight is not approved. Re-run preflight after making fixes.";
    case "failed":
      return "Preflight is required before creating this campaign. ActionsManager could not create or manage the validation PR. Fix the error and re-run preflight.";
    case "running":
      return "Preflight is required before creating this campaign. A validation PR is being created; refresh status once it appears.";
    case "waiting_for_checks": // legacy
    case "validation_pr_open":
      return "Campaign creation is locked until the validation PR is merged and preflight is approved.";
    case "validation_repo_inaccessible":
      return "Preflight is required, but ActionsManager cannot access the validation repository. Ensure the GitHub token has 'Pull requests: read' permission on the validation repository.";
    case "stale":
      return "Preflight is required before creating this campaign. The workflow changes have changed since the last approval. Re-run preflight to validate the current changes.";
    default:
      return "Preflight is required before creating this campaign. Run preflight to create a validation PR, then merge it to approve the generated workflow changes.";
  }
}

// ─── usePreflightValidation ──────────────────────────────────────────────────

interface PreflightInitial {
  status: string | null;
  runAt: string | null;
  error: string | null;
  prUrl: string | null;
}

interface PreflightChangePayload {
  status: string;
  runAt?: string | null;
  error?: string | null;
  prUrl?: string | null;
}

function usePreflightValidation(
  user: string,
  projectName: string,
  validationRepo: string | null,
  initial: PreflightInitial,
  onChange?: (state: PreflightChangePayload) => void
) {
  const [status, setStatus] = useState<string | null>(initial.status);
  const [runAt, setRunAt] = useState<string | null>(initial.runAt);
  const [error, setError] = useState<string | null>(initial.error);
  const [prUrl, setPrUrl] = useState<string | null>(initial.prUrl);
  const [prState, setPrState] = useState<string | null>(null);
  const [canMerge, setCanMerge] = useState<boolean | null>(null);
  const [mergeBlockReason, setMergeBlockReason] = useState<string | null>(null);
  const [canClose, setCanClose] = useState<boolean | null>(null);
  const [closeBlockReason, setCloseBlockReason] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [closing, setClosing] = useState(false);
  const [merging, setMerging] = useState(false);
  const pollAttemptRef = useRef<number>(0);

  const applyRefresh = useCallback((refreshed: any) => {
    setStatus(refreshed.status);
    setRunAt(refreshed.last_preflight_run_at);
    setError(refreshed.last_preflight_error);
    setPrUrl(refreshed.last_preflight_pr_url);
    setPrState(refreshed.pr_state);
    setCanMerge(refreshed.can_merge ?? null);
    setMergeBlockReason(refreshed.merge_block_reason ?? null);
    setCanClose(refreshed.can_close ?? null);
    setCloseBlockReason(refreshed.close_block_reason ?? null);
    onChange?.({
      status: refreshed.status,
      runAt: refreshed.last_preflight_run_at,
      prUrl: refreshed.last_preflight_pr_url,
      error: refreshed.last_preflight_error,
    });
  }, [onChange]);

  const pending = Boolean(validationRepo) && Boolean(prUrl) &&
    (["running", "validation_pr_open", "waiting_for_checks"].includes(status || ""));

  useEffect(() => {
    if (!pending || refreshing || running || closing || merging) return;
    pollAttemptRef.current += 1;
    if (pollAttemptRef.current > 30) return;
    const interval = setInterval(() => {
      getPreflightValidationStatus(user, projectName, true).then(applyRefresh).catch(() => {});
    }, 8000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, refreshing, running, closing, merging, user, projectName, applyRefresh]);

  useEffect(() => {
    if (!validationRepo || !prUrl || prState !== null || refreshing || running || closing || merging) return;
    getPreflightValidationStatus(user, projectName, true).then(applyRefresh).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [validationRepo, prUrl, prState, user, projectName, applyRefresh]);

  const handleRun = useCallback(async (selectedWorkflowNames: string[]) => {
    setRunning(true);
    setError(null);
    setStatus("running");
    setCanMerge(null); setMergeBlockReason(null); setCanClose(null); setCloseBlockReason(null);
    onChange?.({ status: "running" });
    try {
      const response = await runPreflightValidation(user, projectName, selectedWorkflowNames);
      setStatus(response.status);
      setRunAt(response.last_preflight_run_at);
      setError(null);
      setPrUrl(response.last_preflight_pr_url);
      setPrState(null); setCanMerge(null); setMergeBlockReason(null); setCanClose(null); setCloseBlockReason(null);
      onChange?.({ status: response.status, runAt: response.last_preflight_run_at, prUrl: response.last_preflight_pr_url, error: null });
      if (validationRepo) {
        await getPreflightValidationStatus(user, projectName, true).then(applyRefresh).catch(() => {});
      }
    } catch (err: any) {
      const message = err.message || "Preflight validation failed";
      setStatus("failed");
      setError(message);
      onChange?.({ status: "failed", error: message });
    } finally {
      setRunning(false);
    }
  }, [user, projectName, validationRepo, onChange, applyRefresh]);

  const handleRefresh = useCallback(async () => {
    if (!validationRepo) return;
    setRefreshing(true);
    setError(null);
    try {
      await getPreflightValidationStatus(user, projectName, true).then(applyRefresh);
    } catch (err: any) {
      setError(err.message || "Failed to refresh preflight status");
    } finally {
      setRefreshing(false);
    }
  }, [user, projectName, validationRepo, applyRefresh]);

  const handleClose = useCallback(async () => {
    if (!validationRepo || !prUrl) return;
    setClosing(true);
    setError(null);
    try {
      const resp = await closePreflightValidationPR(user, projectName, true);
      setStatus(resp.status);
      setError(null);
      setPrState("closed");
      setCanMerge(false); setMergeBlockReason("Validation PR is closed.");
      setCanClose(false); setCloseBlockReason("Validation PR is already closed.");
      onChange?.({ status: resp.status, error: null, prUrl: resp.last_preflight_pr_url });
      await handleRefresh();
    } catch (err: any) {
      setError(err.message || "Failed to close validation PR");
    } finally {
      setClosing(false);
    }
  }, [user, projectName, validationRepo, prUrl, onChange, handleRefresh]);

  const handleMerge = useCallback(async () => {
    if (!validationRepo || !prUrl) return;
    setMerging(true);
    setError(null);
    try {
      const resp = await mergePreflightValidationPR(user, projectName, true);
      setStatus(resp.status);
      setError(null);
      setPrState("merged");
      setCanMerge(false); setMergeBlockReason("Validation PR is merged.");
      setCanClose(false); setCloseBlockReason("Validation PR is already merged.");
      onChange?.({ status: resp.status, error: null, prUrl: resp.last_preflight_pr_url });
      await handleRefresh();
    } catch (err: any) {
      setError(err.message || "Failed to merge validation PR");
    } finally {
      setMerging(false);
    }
  }, [user, projectName, validationRepo, prUrl, onChange, handleRefresh]);

  return {
    status, runAt, error, prUrl, prState,
    canMerge, mergeBlockReason, canClose, closeBlockReason,
    running, refreshing, closing, merging,
    handleRun, handleRefresh, handleClose, handleMerge,
  };
}

// ─── useCreatePRCampaign ─────────────────────────────────────────────────────

interface CreatePRCampaignParams {
  user: string;
  projectName: string;
  selectedRepos: Set<string>;
  selectedWorkflows: Set<string>;
  selectedReusableWorkflows: Set<string>;
  selectedCustomFileIds: Set<number>;
  onSuccess: (workflowNames: string[], reusableNames: string[], customFileIds: number[], codeownersRepos: string[]) => void;
  selectedCodeownersRepos: Set<string>;
}

function useCreatePRCampaign({
  user, projectName, selectedRepos, selectedWorkflows, selectedReusableWorkflows, selectedCustomFileIds, selectedCodeownersRepos, onSuccess,
}: CreatePRCampaignParams) {
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<any>(null);
  const [taskStatus, setTaskStatus] = useState<any>(null);
  const prPollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => { if (prPollIntervalRef.current) clearInterval(prPollIntervalRef.current); };
  }, []);

  const handleCreate = useCallback(async () => {
    const hasWorkflowsOrFiles = selectedWorkflows.size > 0 || selectedReusableWorkflows.size > 0 || selectedCustomFileIds.size > 0;
    const hasCodeowners = selectedCodeownersRepos.size > 0;
    // Caller repos are only required when there are workflows/custom files to deploy
    if (selectedRepos.size === 0 && hasWorkflowsOrFiles) { setError("Please select at least one repository"); return; }
    if (!hasWorkflowsOrFiles && !hasCodeowners) {
      setError("Please select at least one workflow, custom file, or CODEOWNERS"); return;
    }
    setCreating(true);
    setError(null);
    setResults(null);
    const codeownersRepoList = Array.from(selectedCodeownersRepos);

    // Deploy CODEOWNERS PRs under the given campaign so they appear in the same card.
    // Repos already merged into an existing workflow/custom-file PR (see
    // codeowners_merged_repos) are skipped here — they'd otherwise get a second,
    // redundant PR for the same repo.
    const deployCodeownersRepos = async (
      campaignId?: number, alreadyMerged: string[] = [],
    ): Promise<{ succeeded: string[]; failed: string[] }> => {
      const remaining = codeownersRepoList.filter(repo => !alreadyMerged.includes(repo));
      if (remaining.length === 0) return { succeeded: [...alreadyMerged], failed: [] };
      const deployResults = await Promise.allSettled(
        remaining.map(repo => deployCodeowners(repo, user, projectName, { mode: 'pr', campaignId }))
      );
      const succeeded: string[] = [...alreadyMerged];
      const failed: string[] = [];
      deployResults.forEach((r, i) => {
        if (r.status === 'fulfilled') succeeded.push(remaining[i]);
        else { failed.push(remaining[i]); console.error(`CODEOWNERS PR failed for ${remaining[i]}:`, r.reason); }
      });
      return { succeeded, failed };
    };

    try {
      // Always go through createPullRequests — it creates the campaign record so that
      // CODEOWNERS PRs (deployed afterwards) can share the same campaign_id and appear
      // as a single campaign card rather than a separate legacy group.
      const response = await createPullRequests(
        user, projectName,
        Array.from(selectedRepos),
        selectedWorkflows.size > 0 ? Array.from(selectedWorkflows) : undefined,
        selectedReusableWorkflows.size > 0 ? Array.from(selectedReusableWorkflows) : undefined,
        // Always send array so empty selection explicitly excludes files (not undefined=all)
        Array.from(selectedCustomFileIds),
        hasCodeowners ? codeownersRepoList : undefined,
      );
      if (response.task_id) {
        setTaskStatus({ status: "running", repos: {} });
        prPollIntervalRef.current = setInterval(async () => {
          try {
            const statusResponse = await getCreatePullRequestsStatus(response.task_id!);
            setTaskStatus(statusResponse);
            if (statusResponse.status === "completed" || statusResponse.status === "error") {
              if (prPollIntervalRef.current) { clearInterval(prPollIntervalRef.current); prPollIntervalRef.current = null; }
              if (statusResponse.status === "completed") {
                const { succeeded } = await deployCodeownersRepos(
                  statusResponse.campaign_id, statusResponse.codeowners_merged_repos || [],
                );
                setCreating(false);
                setResults({ message: "Pull requests created successfully", results: statusResponse.results, prs_created: statusResponse.prs_created });
                onSuccess(Array.from(selectedWorkflows), Array.from(selectedReusableWorkflows), Array.from(selectedCustomFileIds), succeeded);
              } else {
                setCreating(false);
                setError(statusResponse.error || "An error occurred during PR creation.");
              }
            }
          } catch (pollErr: any) {
            console.error("Error polling PR creation status:", pollErr);
          }
        }, 1000);
      } else {
        const { succeeded } = await deployCodeownersRepos(response.campaign_id, response.codeowners_merged_repos || []);
        setResults(response);
        setCreating(false);
        onSuccess(Array.from(selectedWorkflows), Array.from(selectedReusableWorkflows), Array.from(selectedCustomFileIds), succeeded);
      }
    } catch (err: any) {
      console.error("Error creating pull requests:", err);
      setError(err.message || "Failed to create pull requests");
      setCreating(false);
    }
  }, [user, projectName, selectedRepos, selectedWorkflows, selectedReusableWorkflows, selectedCustomFileIds, selectedCodeownersRepos, onSuccess]);

  return { creating, error, results, taskStatus, handleCreate };
}

// ─── Sub-component pure helpers ──────────────────────────────────────────────

function repoStatusLabel(repoData: any): string {
  if (!repoData) return "Pending";
  if (repoData.status === "completed") return "Created";
  if (repoData.status === "error") return "Failed";
  return repoData.step;
}

function repoStatusClass(repoData: any): string {
  if (!repoData) return "status-pending";
  if (repoData.status === "completed") return "status-completed";
  if (repoData.status === "error") return "status-error";
  return "status-running";
}

function createButtonText(creating: boolean, preflightConfigured: boolean, prCount: number, wfCount: number, cfCount = 0): string {
  if (creating) return "Creating PRs...";
  const s = (n: number) => (n !== 1 ? "s" : "");
  const prs = `${prCount} PR${s(prCount)}`;
  const items = wfCount > 0 && cfCount > 0
    ? `${wfCount} workflow${s(wfCount)}, ${cfCount} file${s(cfCount)}`
    : wfCount > 0
      ? `${wfCount} workflow${s(wfCount)}`
      : `${cfCount} file${s(cfCount)}`;
  return preflightConfigured ? `Create Campaign (${prs}, ${items})` : `Create ${prs} (${items})`;
}

function getPreflightDisabledReasons(
  prUrl: string | null,
  prState: string | null,
  canMerge: boolean | null,
  mergeBlockReason: string | null,
  canClose: boolean | null,
  closeBlockReason: string | null,
  actionInProgress: boolean
) {
  const prOpen = prState === "open";
  const showClose = Boolean(prUrl) && prOpen;
  const showMerge = Boolean(prUrl) && prOpen;
  const refresh = prUrl
    ? (actionInProgress ? "Wait for the current validation action to finish." : null)
    : "No validation PR has been created yet.";
  const close = showClose
    ? (canClose === false ? (closeBlockReason || "GitHub reports the validation PR cannot be closed.") : (actionInProgress ? "Wait for the current validation action to finish." : null))
    : null;
  const merge = showMerge
    ? (canMerge === false ? (mergeBlockReason || "GitHub reports the validation PR cannot be merged.") : (actionInProgress ? "Wait for the current validation action to finish." : null))
    : null;
  return { refresh, close, merge, showClose, showMerge };
}

// ─── Sub-components ──────────────────────────────────────────────────────────

interface PRCreationProgressProps {
  taskStatus: any;
  totalPRTargetRepos: Set<string>;
  selectedWorkflows: Set<string>;
  selectedReusableWorkflows: Set<string>;
  selectedCustomFileIds?: Set<number>;
  changedCustomFiles?: Array<{ id: number; file_path: string }>;
}

const PRCreationProgress: React.FC<PRCreationProgressProps> = ({
  taskStatus, totalPRTargetRepos, selectedWorkflows, selectedReusableWorkflows, selectedCustomFileIds, changedCustomFiles,
}) => (
  <div className="task-status-section" data-testid="pr-creation-progress">
    <div className="creating-spinner">
      <div className="spinner"></div>
      <span>Creating PR campaign</span>
    </div>
    <p className="task-progress-count">
      Creating {Object.values(taskStatus?.repos || {}).filter((r: any) => r.status === "completed").length} of {totalPRTargetRepos.size} pull request{totalPRTargetRepos.size !== 1 ? "s" : ""}
    </p>
    <div className="task-repos" data-testid="repo-progress-list">
      {Array.from(totalPRTargetRepos).map((repoName) => {
        const repoKeys = Object.keys(taskStatus?.repos || {});
        const matchingKey = repoKeys.find((k) => k.startsWith(repoName));
        const repoData = matchingKey ? taskStatus?.repos?.[matchingKey] ?? null : null;
        const statusLabel = repoStatusLabel(repoData);
        const statusClass = repoStatusClass(repoData);
        return (
          <div key={repoName} className="task-repo-item" data-testid="repo-status-row">
            <span className="task-repo-name">{repoName}</span>
            <span className={`repo-step ${statusClass}`}>{statusLabel}</span>
            {repoData?.error && <span className="repo-error">{repoData.error}</span>}
          </div>
        );
      })}
    </div>
    <div className="task-workflow-files">
      <span className="task-workflow-files-label">Workflow files:</span>
      <ul>
        {Array.from(selectedWorkflows).map((wf) => <li key={wf}>{normalizeWorkflowFilename(wf)}</li>)}
        {Array.from(selectedReusableWorkflows).map((wf) => <li key={wf}>{normalizeWorkflowFilename(wf)}</li>)}
      </ul>
    </div>
    {selectedCustomFileIds && selectedCustomFileIds.size > 0 && changedCustomFiles && (
      <div className="task-workflow-files">
        <span className="task-workflow-files-label">Custom files:</span>
        <ul>
          {changedCustomFiles.filter((f) => selectedCustomFileIds.has(f.id)).map((f) => <li key={f.id}>{f.file_path}</li>)}
        </ul>
      </div>
    )}
    {taskStatus?.status === "error" && taskStatus?.error && (
      <div className="error-message">❌ {taskStatus.error}</div>
    )}
  </div>
);

const PRCreationResults: React.FC<{ results: any }> = ({ results }) => (
  <div className="results-section">
    <div className="success-message">
      ✅ Successfully created {results.prs_created} pull request(s)!
    </div>
    <div className="results-details">
      {Object.entries(results.results || {}).map(([key, value]: [string, any]) => {
        const status = value.status || "unknown";
        const prUrl = value.pr_url;
        const prNumber = value.pr_number;
        return (
          <div key={key} className="result-item">
            <span className={`result-status ${status}`}>
              {status === "pr_created" && "✅ Created"}
              {status === "pr_updated" && "✅ Updated"}
              {status === "error" && "❌ Error"}
            </span>
            <span className="result-repo">{key}</span>
            {prUrl && (
              <a href={prUrl} target="_blank" rel="noopener noreferrer" className="result-link">
                PR #{prNumber} →
              </a>
            )}
          </div>
        );
      })}
    </div>
  </div>
);

interface WorkflowItemProps {
  name: string;
  selected: boolean;
  disabled: boolean;
  onToggle: (name: string) => void;
  extraClass?: string;
  badge?: React.ReactNode;
}

const WorkflowItem: React.FC<WorkflowItemProps> = ({ name, selected, disabled, onToggle, extraClass, badge }) => (
  <label className={`repo-item ${selected ? "selected" : ""} ${extraClass || ""}`}>
    <input
      type="checkbox"
      checked={selected}
      onChange={() => onToggle(name)}
      disabled={disabled}
    />
    <span className="repo-name">{normalizeWorkflowFilename(name)}</span>
    {badge}
  </label>
);

function workflowBadge(status: string | undefined): React.ReactNode {
  if (!status || status === "synced_with_github") return null;
  let label = status;
  if (status === "committed_locally") label = "Draft";
  else if (status === "new") label = "New";
  return <span className="workflow-status-badge">{label}</span>;
}

interface PreflightSectionProps {
  preflight: ReturnType<typeof usePreflightValidation>;
  validationRepo: string;
  formattedStatus: string;
  statusMessage: string;
  requiredMessage: string | null;
  validationActionInProgress: boolean;
  selectedWorkflowNames: string[];
}

const PreflightSection: React.FC<PreflightSectionProps> = ({
  preflight, validationRepo, formattedStatus, statusMessage, requiredMessage,
  validationActionInProgress, selectedWorkflowNames,
}) => {
  const showRunPreflight = !preflight.prUrl || ["not_run", "failed", "closed", "stale", "validation_repo_inaccessible"].includes(preflight.status || "not_run");
  const { refresh: refreshDisabledReason, close: closeDisabledReason, merge: mergeDisabledReason, showClose: showCloseValidationPr, showMerge: showMergeValidationPr } = getPreflightDisabledReasons(
    preflight.prUrl, preflight.prState, preflight.canMerge, preflight.mergeBlockReason, preflight.canClose, preflight.closeBlockReason, validationActionInProgress
  );
  const runButtonLabel = preflight.running ? "Running Preflight..." : (preflight.prUrl ? "Re-run Preflight" : "Run Preflight");

  return (
    <div className="repo-selection">
      <h3 className="selection-section-title">Preflight Validation</h3>
      <div className="results-details">
        <div className="result-item">
          <span className={`result-status ${preflight.status || "not_run"}`}>
            Status: {formattedStatus}
          </span>
          <span className="result-repo">{validationRepo}</span>
          {preflight.prUrl && (
            <a href={preflight.prUrl} target="_blank" rel="noopener noreferrer" className="result-link">
              Open Validation PR →
            </a>
          )}
        </div>
      </div>
      {preflight.runAt && (
        <p className="modal-description">Last run: {new Date(preflight.runAt).toLocaleString()}</p>
      )}
      {preflight.error && <div className="error-message">❌ {preflight.error}</div>}
      <p className="modal-description preflight-status-copy">{statusMessage}</p>
      {requiredMessage && <div className="error-message">{requiredMessage}</div>}
      <div className="preflight-actions">
        <div className="preflight-action-group">
          <span className="preflight-action-label">Primary</span>
          {showRunPreflight && (
            <Button
              onClick={() => preflight.handleRun(selectedWorkflowNames)}
              size="sm"
              disabled={validationActionInProgress || selectedWorkflowNames.length === 0}
            >
              {runButtonLabel}
            </Button>
          )}
          {showMergeValidationPr && (
            <Button onClick={preflight.handleMerge} variant="secondary" size="sm" disabled={Boolean(mergeDisabledReason)}>
              {preflight.merging ? "Merging..." : "Merge Validation PR"}
            </Button>
          )}
        </div>
        <div className="preflight-action-group">
          <span className="preflight-action-label">Secondary</span>
          <Button onClick={preflight.handleRefresh} variant="secondary" size="sm" disabled={Boolean(refreshDisabledReason)}>
            {preflight.refreshing ? "Refreshing..." : "Refresh Status"}
          </Button>
          {preflight.prUrl && (
            <Button asChild variant="link" size="sm">
              <a href={preflight.prUrl} target="_blank" rel="noopener noreferrer">Open Validation PR</a>
            </Button>
          )}
        </div>
        {showCloseValidationPr && (
          <div className="preflight-action-group">
            <span className="preflight-action-label">Cleanup</span>
            <Button onClick={preflight.handleClose} variant="destructive" size="sm" disabled={Boolean(closeDisabledReason)}>
              {preflight.closing ? "Closing..." : "Close Validation PR"}
            </Button>
          </div>
        )}
      </div>
      <div className="preflight-action-reasons">
        {showRunPreflight && selectedWorkflowNames.length === 0 && <p>Run Preflight unavailable: select at least one regular workflow.</p>}
        {refreshDisabledReason && <p>Refresh Status unavailable: {refreshDisabledReason}</p>}
        {showCloseValidationPr && closeDisabledReason && <p>Close Validation PR unavailable: {closeDisabledReason}</p>}
        {showMergeValidationPr && mergeDisabledReason && <p>Merge Validation PR unavailable: {mergeDisabledReason}</p>}
      </div>
    </div>
  );
};

interface WorkflowSectionProps {
  workflows: Array<{ name: string; status?: string }>;
  changed: Array<{ name: string; status?: string }>;
  unchanged: Array<{ name: string; status?: string }>;
  selected: Set<string>;
  showUnchanged: boolean;
  setShowUnchanged: (v: boolean) => void;
  creating: boolean;
  onToggle: (name: string) => void;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  title: string;
}

const WorkflowSection: React.FC<WorkflowSectionProps> = ({
  workflows, changed, unchanged, selected, showUnchanged, setShowUnchanged, creating, onToggle, onSelectAll, onDeselectAll, title,
}) => (
  <div className="repo-selection">
    <h3 className="selection-section-title">{title}</h3>
    <div className="selection-actions">
      <Button onClick={onSelectAll} variant="secondary" size="sm" disabled={creating}>Select All</Button>
      <Button onClick={onDeselectAll} variant="secondary" size="sm" disabled={creating}>Deselect All</Button>
      <span className="selection-count">{selected.size} of {workflows.length} selected</span>
    </div>
    {unchanged.length > 0 && changed.length > 0 && (
      <label className="show-unchanged-toggle">
        <input type="checkbox" checked={showUnchanged} onChange={(e) => setShowUnchanged(e.target.checked)} />
        <span>Show unchanged workflows ({unchanged.length} already synced)</span>
      </label>
    )}
    <div className="repo-list">
      {changed.map((wf) => (
        <WorkflowItem key={wf.name} name={wf.name} selected={selected.has(wf.name)} disabled={creating} onToggle={onToggle} badge={workflowBadge(wf.status)} />
      ))}
      {showUnchanged && unchanged.map((wf) => (
        <WorkflowItem key={wf.name} name={wf.name} selected={selected.has(wf.name)} disabled={creating} onToggle={onToggle} extraClass="unchanged-workflow" badge={<span className="workflow-status-badge synced">Synced</span>} />
      ))}
      {changed.length === 0 && workflows.map((wf) => (
        <WorkflowItem key={wf.name} name={wf.name} selected={selected.has(wf.name)} disabled={creating} onToggle={onToggle} />
      ))}
    </div>
  </div>
);

interface PRCreationFormProps {
  error: string | null;
  validationRepo: string | null;
  preflight: ReturnType<typeof usePreflightValidation>;
  formattedPreflightStatus: string;
  requiresPreflight: boolean;
  preflightPassed: boolean;
  campaignBlockedByPreflight: boolean;
  validationActionInProgress: boolean;
  selectedWorkflows: Set<string>;
  selectedReusableWorkflows: Set<string>;
  changedWorkflows: Array<{ name: string; status?: string }>;
  unchangedWorkflows: Array<{ name: string; status?: string }>;
  changedReusableWorkflows: Array<{ name: string; status?: string; sourceRepo?: string }>;
  unchangedReusableWorkflows: Array<{ name: string; status?: string; sourceRepo?: string }>;
  workflows: Array<{ name: string; status?: string }>;
  reusableWorkflows: Array<{ name: string; status?: string; sourceRepo?: string }>;
  changedCustomFiles: Array<{ id: number; file_path: string; file_status: string; pending_delete: boolean }>;
  selectedCustomFileIds: Set<number>;
  onToggleCustomFile: (id: number) => void;
  onSelectAllCustomFiles: () => void;
  onDeselectAllCustomFiles: () => void;
  showUnchangedWorkflows: boolean;
  setShowUnchangedWorkflows: (v: boolean) => void;
  repositories: Array<{ name: string; full_name?: string }>;
  selectedRepos: Set<string>;
  selectedReusableSourceRepos: Set<string>;
  creating: boolean;
  totalSelectedWorkflows: number;
  totalWorkflows: number;
  onToggleRepo: (name: string) => void;
  onSelectAllRepos: () => void;
  onDeselectAllRepos: () => void;
  onToggleWorkflow: (name: string) => void;
  onSelectAllWorkflows: () => void;
  onDeselectAllWorkflows: () => void;
  onToggleReusableWorkflow: (name: string) => void;
  onSelectAllReusableWorkflows: () => void;
  onDeselectAllReusableWorkflows: () => void;
  codeownersRepos?: string[];
  selectedCodeownersRepos: Set<string>;
  onSelectAllCodeownersRepos: () => void;
  onDeselectAllCodeownersRepos: () => void;
}

const PRCreationForm: React.FC<PRCreationFormProps> = ({
  error, validationRepo, preflight, formattedPreflightStatus,
  requiresPreflight, preflightPassed, campaignBlockedByPreflight,
  validationActionInProgress, selectedWorkflows, selectedReusableWorkflows,
  changedWorkflows, unchangedWorkflows, changedReusableWorkflows, unchangedReusableWorkflows,
  workflows, reusableWorkflows, changedCustomFiles, selectedCustomFileIds,
  onToggleCustomFile, onSelectAllCustomFiles, onDeselectAllCustomFiles,
  showUnchangedWorkflows, setShowUnchangedWorkflows,
  repositories, selectedRepos, selectedReusableSourceRepos, creating,
  totalSelectedWorkflows, totalWorkflows,
  onToggleRepo, onSelectAllRepos, onDeselectAllRepos,
  onToggleWorkflow, onSelectAllWorkflows, onDeselectAllWorkflows,
  onToggleReusableWorkflow, onSelectAllReusableWorkflows, onDeselectAllReusableWorkflows,
  codeownersRepos = [], selectedCodeownersRepos, onSelectAllCodeownersRepos, onDeselectAllCodeownersRepos,
}) => {
  const statusMessage = getPreflightStatusMessage(preflight.status, preflight.prState);
  const requiredMessage = getPreflightRequiredMessage(preflight.status, requiresPreflight, preflightPassed);

  return (
    <>
      <p className="modal-description">
        Preflight creates a validation pull request in a safe repository before the real campaign is created. Review the validation PR in GitHub. If the changes look correct, merge the validation PR to approve preflight. If the changes are wrong or need updates, close the validation PR and re-run preflight after making fixes.
      </p>
      {error && <div className="error-message">❌ {error}</div>}
      {validationRepo && (
        <PreflightSection
          preflight={preflight}
          validationRepo={validationRepo}
          formattedStatus={formattedPreflightStatus}
          statusMessage={statusMessage}
          requiredMessage={requiredMessage}
          validationActionInProgress={validationActionInProgress}
          selectedWorkflowNames={Array.from(selectedWorkflows)}
        />
      )}
      <div className={`repo-selection campaign-section ${campaignBlockedByPreflight ? "campaign-section-gated" : ""}`}>
        <h3 className="selection-section-title">Campaign Pull Requests</h3>
        {campaignBlockedByPreflight && (
          <div className="warning-message">Campaign creation is gated: {requiredMessage}</div>
        )}
        <p className="modal-description">
          Campaign creation is locked until the validation PR is merged. This prevents opening the real campaign before the generated workflow changes have been reviewed and approved in the validation repository.
        </p>
        <div className="campaign-summary">
          <span className="selection-count">
            {totalSelectedWorkflows} of {totalWorkflows} workflow{totalWorkflows !== 1 ? "s" : ""} selected
            {reusableWorkflows.length > 0 && ` (${selectedWorkflows.size} standard, ${selectedReusableWorkflows.size} reusable)`}
          </span>
        </div>
      </div>
      {workflows.length > 0 && (
        <WorkflowSection
          workflows={workflows}
          changed={changedWorkflows}
          unchanged={unchangedWorkflows}
          selected={selectedWorkflows}
          showUnchanged={showUnchangedWorkflows}
          setShowUnchanged={setShowUnchangedWorkflows}
          creating={creating}
          onToggle={onToggleWorkflow}
          onSelectAll={onSelectAllWorkflows}
          onDeselectAll={onDeselectAllWorkflows}
          title="Workflows"
        />
      )}
      {reusableWorkflows.length > 0 && (
        <WorkflowSection
          workflows={reusableWorkflows}
          changed={changedReusableWorkflows}
          unchanged={unchangedReusableWorkflows}
          selected={selectedReusableWorkflows}
          showUnchanged={showUnchangedWorkflows}
          setShowUnchanged={setShowUnchangedWorkflows}
          creating={creating}
          onToggle={onToggleReusableWorkflow}
          onSelectAll={onSelectAllReusableWorkflows}
          onDeselectAll={onDeselectAllReusableWorkflows}
          title="Reusable Workflows"
        />
      )}
      {changedCustomFiles.length > 0 && (
        <div className="repo-selection">
          <h3 className="selection-section-title">Custom Files</h3>
          <div className="selection-actions">
            <Button onClick={onSelectAllCustomFiles} variant="secondary" size="sm" disabled={creating}>Select All</Button>
            <Button onClick={onDeselectAllCustomFiles} variant="secondary" size="sm" disabled={creating}>Deselect All</Button>
            <span className="selection-count">{selectedCustomFileIds.size} of {changedCustomFiles.length} selected</span>
          </div>
          <div className="repo-list">
            {changedCustomFiles.map((cf) => {
              const isSelected = selectedCustomFileIds.has(cf.id);
              return (
                <label key={cf.id} className={`repo-item ${isSelected ? "selected" : ""}`}>
                  <input type="checkbox" checked={isSelected} onChange={() => onToggleCustomFile(cf.id)} disabled={creating} />
                  <span className="repo-name">{cf.file_path}{cf.pending_delete ? " (pending delete)" : ""}</span>
                </label>
              );
            })}
          </div>
        </div>
      )}
      {codeownersRepos.length > 0 && (
        <div className="repo-selection">
          <h3 className="selection-section-title">CODEOWNERS</h3>
          <div className="repo-list">
            <label className={`repo-item ${selectedCodeownersRepos.size > 0 ? "selected" : ""}`}>
              <input
                type="checkbox"
                checked={selectedCodeownersRepos.size > 0}
                onChange={() => selectedCodeownersRepos.size > 0 ? onDeselectAllCodeownersRepos() : onSelectAllCodeownersRepos()}
                disabled={creating}
              />
              <span className="repo-name">.github/CODEOWNERS</span>
              <span className="workflow-status-badge">{codeownersRepos.length} repo{codeownersRepos.length !== 1 ? "s" : ""}</span>
            </label>
          </div>
        </div>
      )}
      <div className="repo-selection">
        <h3 className="selection-section-title">Caller Repositories</h3>
        <div className="selection-actions">
          <Button onClick={onSelectAllRepos} variant="secondary" size="sm" disabled={creating}>Select All</Button>
          <Button onClick={onDeselectAllRepos} variant="secondary" size="sm" disabled={creating}>Deselect All</Button>
          <span className="selection-count">{selectedRepos.size} of {repositories.length} selected</span>
        </div>
        <div className="repo-list">
          {repositories.map((repo) => {
            const repoName = repo.full_name || repo.name;
            const isSelected = selectedRepos.has(repoName);
            return (
              <label key={repoName} className={`repo-item ${isSelected ? "selected" : ""}`}>
                <input type="checkbox" checked={isSelected} onChange={() => onToggleRepo(repoName)} disabled={creating} />
                <span className="repo-name">{repoName}</span>
              </label>
            );
          })}
        </div>
      </div>
      {selectedReusableSourceRepos.size > 0 && (
        <div className="repo-selection">
          <h3 className="selection-section-title">Reusable Workflow Source Repositories</h3>
          <p className="modal-description">
            These repositories will also receive PRs because you selected reusable workflows from them.
          </p>
          <div className="repo-list">
            {Array.from(selectedReusableSourceRepos).map((repoName) => (
              <div key={repoName} className="repo-item selected source-repo-item">
                <input type="checkbox" checked={true} disabled={true} readOnly />
                <span className="repo-name">{repoName}</span>
                <span className="workflow-status-badge">Source</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
};

// ─── Main component ───────────────────────────────────────────────────────────

const CreatePRModal: React.FC<CreatePRModalProps> = ({
  user,
  projectName,
  repositories,
  workflows,
  reusableWorkflows = [],
  customFiles = [],
  codeownersRepos = [],
  validationRepo = null,
  preflightRequired = false,
  preflightStatus = null,
  preflightRunAt = null,
  preflightError = null,
  preflightPrUrl = null,
  onPreflightStatusChange,
  onClose,
  onSuccess,
}) => {
  const [selectedRepos, setSelectedRepos] = useState<Set<string>>(
    new Set(repositories.map((r) => r.full_name || r.name))
  );
  const [showUnchangedWorkflows, setShowUnchangedWorkflows] = useState(false);
  const changedWorkflows = useMemo(() => workflows.filter((w) => w.status !== "synced_with_github"), [workflows]);
  const unchangedWorkflows = useMemo(() => workflows.filter((w) => w.status === "synced_with_github"), [workflows]);
  const changedReusableWorkflows = useMemo(() => reusableWorkflows.filter((w) => w.status !== "synced_with_github"), [reusableWorkflows]);
  const unchangedReusableWorkflows = useMemo(() => reusableWorkflows.filter((w) => w.status === "synced_with_github"), [reusableWorkflows]);
  const [selectedWorkflows, setSelectedWorkflows] = useState<Set<string>>(
    new Set((changedWorkflows.length > 0 ? changedWorkflows : workflows).map((w) => w.name))
  );
  const [selectedReusableWorkflows, setSelectedReusableWorkflows] = useState<Set<string>>(
    new Set(changedReusableWorkflows.map((w) => w.name))
  );

  const changedCustomFiles = useMemo(() => customFiles.filter((f) => f.file_status !== "synced_with_github" || f.pending_delete), [customFiles]);
  const [selectedCustomFileIds, setSelectedCustomFileIds] = useState<Set<number>>(
    new Set(changedCustomFiles.map((f) => f.id))
  );
  const [selectedCodeownersRepos, setSelectedCodeownersRepos] = useState<Set<string>>(new Set(codeownersRepos));

  const preflight = usePreflightValidation(
    user, projectName, validationRepo,
    { status: preflightStatus, runAt: preflightRunAt, error: preflightError, prUrl: preflightPrUrl },
    onPreflightStatusChange
  );

  const { creating, error, results, taskStatus, handleCreate } = useCreatePRCampaign({
    user, projectName, selectedRepos, selectedWorkflows, selectedReusableWorkflows, selectedCustomFileIds, selectedCodeownersRepos, onSuccess,
  });

  const handleToggleRepo = (name: string) => {
    const next = new Set(selectedRepos);
    if (next.has(name)) { next.delete(name); } else { next.add(name); }
    setSelectedRepos(next);
  };
  const handleToggleWorkflow = (name: string) => {
    const next = new Set(selectedWorkflows);
    if (next.has(name)) { next.delete(name); } else { next.add(name); }
    setSelectedWorkflows(next);
  };
  const handleToggleReusableWorkflow = (name: string) => {
    const next = new Set(selectedReusableWorkflows);
    if (next.has(name)) { next.delete(name); } else { next.add(name); }
    setSelectedReusableWorkflows(next);
  };

  const preflightConfigured = Boolean(validationRepo);
  const requiresPreflight = preflightConfigured && Boolean(preflightRequired);
  const preflightPassed = preflight.status === "passed";
  const campaignBlockedByPreflight = requiresPreflight && !preflightPassed;
  const validationActionInProgress = creating || preflight.running || preflight.refreshing || preflight.closing || preflight.merging;
  const hasWorkflowsOrFiles = selectedWorkflows.size > 0 || selectedReusableWorkflows.size > 0 || selectedCustomFileIds.size > 0;
  const canCreate = (selectedCodeownersRepos.size > 0 || hasWorkflowsOrFiles)
    && (!hasWorkflowsOrFiles || selectedRepos.size > 0)
    && (!requiresPreflight || preflightPassed);

  const selectedReusableSourceRepos = useMemo(() => {
    const sourceRepos = new Set<string>();
    reusableWorkflows.filter((w) => selectedReusableWorkflows.has(w.name) && w.sourceRepo).forEach((w) => sourceRepos.add(w.sourceRepo!));
    return sourceRepos;
  }, [reusableWorkflows, selectedReusableWorkflows]);

  const totalPRTargetRepos = useMemo(() => {
    const allTargets = new Set<string>();
    if (selectedWorkflows.size > 0 || selectedCustomFileIds.size > 0) { selectedRepos.forEach((repo) => allTargets.add(repo)); }
    selectedReusableSourceRepos.forEach((repo) => allTargets.add(repo));
    selectedCodeownersRepos.forEach((repo) => allTargets.add(repo));
    return allTargets;
  }, [selectedRepos, selectedReusableSourceRepos, selectedWorkflows.size, selectedCustomFileIds.size, selectedCodeownersRepos]);

  const formattedPreflightStatus = useMemo(() => {
    const s = preflight.status || "not_run";
    const map: Record<string, string> = {
      not_configured: "Not configured", not_run: "Not run", running: "Running",
      validation_pr_open: "Waiting for review", waiting_for_checks: "Waiting for review",
      passed: "Approved", failed: "Failed", closed: "Rejected",
      stale: "Stale — re-run required", validation_repo_inaccessible: "Inaccessible validation repo",
    };
    return map[s] || s;
  }, [preflight.status]);

  const totalSelectedWorkflows = selectedWorkflows.size + selectedReusableWorkflows.size;
  const totalWorkflows = workflows.length + reusableWorkflows.length;
  const modalTitle = campaignBlockedByPreflight ? "Campaign Readiness" : "Create PR Campaign";
  const isCreatingInProgress = creating || (taskStatus && taskStatus.status !== "completed" && taskStatus.status !== "error");

  // Dismissing happens on a dedicated backdrop button rather than a click
  // handler on the overlay div: a div with onClick is a non-native interactive
  // element with no keyboard path. The button is a real one, and the content
  // is its sibling rather than nested inside it.
  const handleOverlayClick = () => { onClose(); };

  return (
    <div className="modal-overlay">
      <button
        type="button"
        aria-label="Dismiss create pull request dialog"
        onClick={handleOverlayClick}
        className="absolute inset-0 cursor-default border-0 bg-transparent p-0"
      />
      <div className="modal-content create-pr-modal relative">
        <div className="modal-header">
          <div className="modal-header-text">
            <h2>{modalTitle}</h2>
            <a className="docs-inline-link" href={getDocsUrl("prCampaigns")} rel="noreferrer" target="_blank">
              PR campaigns docs →
            </a>
          </div>
          <button onClick={onClose} className="close-button" disabled={creating}>✕</button>
        </div>
        <div className="modal-body">
          {isCreatingInProgress ? (
            <PRCreationProgress taskStatus={taskStatus} totalPRTargetRepos={totalPRTargetRepos} selectedWorkflows={selectedWorkflows} selectedReusableWorkflows={selectedReusableWorkflows} selectedCustomFileIds={selectedCustomFileIds} changedCustomFiles={changedCustomFiles} />
          ) : results ? (
            <PRCreationResults results={results} />
          ) : (
            <PRCreationForm
              error={error}
              validationRepo={validationRepo}
              preflight={preflight}
              formattedPreflightStatus={formattedPreflightStatus}
              requiresPreflight={requiresPreflight}
              preflightPassed={preflightPassed}
              campaignBlockedByPreflight={campaignBlockedByPreflight}
              validationActionInProgress={validationActionInProgress}
              selectedWorkflows={selectedWorkflows}
              selectedReusableWorkflows={selectedReusableWorkflows}
              changedWorkflows={changedWorkflows}
              unchangedWorkflows={unchangedWorkflows}
              changedReusableWorkflows={changedReusableWorkflows}
              unchangedReusableWorkflows={unchangedReusableWorkflows}
              workflows={workflows}
              reusableWorkflows={reusableWorkflows}
              changedCustomFiles={changedCustomFiles}
              selectedCustomFileIds={selectedCustomFileIds}
              onToggleCustomFile={(id) => { const next = new Set(selectedCustomFileIds); if (next.has(id)) { next.delete(id); } else { next.add(id); } setSelectedCustomFileIds(next); }}
              onSelectAllCustomFiles={() => setSelectedCustomFileIds(new Set(changedCustomFiles.map((f) => f.id)))}
              onDeselectAllCustomFiles={() => setSelectedCustomFileIds(new Set())}
              showUnchangedWorkflows={showUnchangedWorkflows}
              setShowUnchangedWorkflows={setShowUnchangedWorkflows}
              repositories={repositories}
              selectedRepos={selectedRepos}
              selectedReusableSourceRepos={selectedReusableSourceRepos}
              creating={creating}
              totalSelectedWorkflows={totalSelectedWorkflows}
              totalWorkflows={totalWorkflows}
              onToggleRepo={handleToggleRepo}
              onSelectAllRepos={() => setSelectedRepos(new Set(repositories.map((r) => r.full_name || r.name)))}
              onDeselectAllRepos={() => setSelectedRepos(new Set())}
              onToggleWorkflow={handleToggleWorkflow}
              onSelectAllWorkflows={() => setSelectedWorkflows(new Set(workflows.map((w) => w.name)))}
              onDeselectAllWorkflows={() => setSelectedWorkflows(new Set())}
              onToggleReusableWorkflow={handleToggleReusableWorkflow}
              onSelectAllReusableWorkflows={() => setSelectedReusableWorkflows(new Set(reusableWorkflows.map((w) => w.name)))}
              onDeselectAllReusableWorkflows={() => setSelectedReusableWorkflows(new Set())}
              codeownersRepos={codeownersRepos}
              selectedCodeownersRepos={selectedCodeownersRepos}
              onSelectAllCodeownersRepos={() => setSelectedCodeownersRepos(new Set(codeownersRepos))}
              onDeselectAllCodeownersRepos={() => setSelectedCodeownersRepos(new Set())}
            />
          )}
        </div>
        <div className="modal-footer">
          {isCreatingInProgress ? (
            <Button onClick={onClose} variant="secondary" disabled>Close</Button>
          ) : results ? (
            <Button onClick={onClose}>Close</Button>
          ) : (
            <>
              <Button onClick={onClose} variant="secondary" disabled={creating}>Cancel</Button>
              <Button onClick={handleCreate} disabled={creating || !canCreate}>
                {createButtonText(creating, preflightConfigured, totalPRTargetRepos.size, totalSelectedWorkflows, selectedCustomFileIds.size + (selectedCodeownersRepos.size > 0 ? 1 : 0))}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default CreatePRModal;
