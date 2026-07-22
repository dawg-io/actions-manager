import React, { useState, useEffect } from "react";
import { getProjectPRStatus, ProjectPRStatus, mergePullRequest, closePullRequest } from "../api/pullRequests";
import { Button } from "./ui/button";
import { formatRelativeTime } from "../utils/timeFormat";
import ConfirmDialog from "./ConfirmDialog";

interface PRStatusPanelProps {
  user: string;
  projectName: string;
  onClose: () => void;
  refreshProjectsList?: () => Promise<void>;
  onProjectStateChange?: (state: string) => void;
}

interface MergeAllResult {
  prNumber: number;
  repoName: string;
  success: boolean;
  message: string;
}

const PRStatusPanel: React.FC<PRStatusPanelProps> = ({ user, projectName, onClose, refreshProjectsList, onProjectStateChange }) => {
  const [prStatus, setPrStatus] = useState<ProjectPRStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [mergeWarning, setMergeWarning] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [processingPR, setProcessingPR] = useState<number | null>(null); // Track which PR is being processed
  const [mergingAll, setMergingAll] = useState<boolean>(false);
  const [mergingAllProgress, setMergingAllProgress] = useState<string | null>(null);
  const [mergeAllResults, setMergeAllResults] = useState<MergeAllResult[] | null>(null);

  // Confirm dialog state
  type PRAction = { type: 'merge' | 'close'; prNumber: number; repoName: string } | { type: 'mergeAll'; count: number } | null;
  const [pendingAction, setPendingAction] = useState<PRAction>(null);

  const loadPRStatus = async (refreshFromGitHub: boolean = false): Promise<ProjectPRStatus | null> => {
    try {
      setError(null);
      const status = await getProjectPRStatus(user, projectName, refreshFromGitHub);
      setPrStatus(status);
      return status;
    } catch (err: any) {
      console.error("Error loading PR status:", err);
      setError(err.message || "Failed to load PR status");
      return null;
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    // Load from GitHub so lifecycle action buttons reflect current mergeability.
    loadPRStatus(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, projectName]);

  const handleRefresh = async () => {
    setRefreshing(true);
    // Manual refresh: fetch from GitHub (slow but up-to-date)
    const status = await loadPRStatus(true);
    // Propagate any state changes (e.g., externally merged/closed PRs) back to
    // the parent so the workflow badges and project banner update immediately.
    if (status && onProjectStateChange) {
      onProjectStateChange(status.project_state || "new");
    }
  };

  const postMergeRefresh = async () => {
    const updatedStatus = await loadPRStatus(false);
    if (onProjectStateChange && updatedStatus?.project_state) {
      onProjectStateChange(updatedStatus.project_state);
    }
    if (refreshProjectsList) {
      await refreshProjectsList();
    }
    return updatedStatus;
  };

  const handleMergePR = (prNumber: number, repoName: string) => {
    setPendingAction({ type: 'merge', prNumber, repoName });
  };

  const doMergePR = async (prNumber: number, repoName: string) => {
    try {
      setProcessingPR(prNumber);
      setError(null);
      setMergeWarning(null);
      const result = await mergePullRequest(user, projectName, repoName, prNumber);
      if (result?.branch_delete_warning) {
        setMergeWarning(
          `PR merged successfully, but ActionsManager could not delete the source branch. You may need to delete it manually in GitHub. (${result.branch_delete_warning})`
        );
      }
      await postMergeRefresh();
    } catch (err: any) {
      console.error("Error merging PR:", err);
      setError(err.message || "Failed to merge pull request");
    } finally {
      setProcessingPR(null);
    }
  };

  const handleClosePR = (prNumber: number, repoName: string) => {
    setPendingAction({ type: 'close', prNumber, repoName });
  };

  const doClosePR = async (prNumber: number, repoName: string) => {
    try {
      setProcessingPR(prNumber);
      setError(null);
      await closePullRequest(user, projectName, repoName, prNumber);
      await postMergeRefresh();
    } catch (err: any) {
      console.error("Error closing PR:", err);
      setError(err.message || "Failed to close pull request");
    } finally {
      setProcessingPR(null);
    }
  };

  const handleMergeAll = () => {
    const openPRs = prStatus?.pull_requests.filter((pr) => pr.pr_state === "open") ?? [];
    const mergeablePRs = openPRs.filter((pr) => pr.can_merge !== false);
    if (mergeablePRs.length === 0) return;
    setPendingAction({ type: 'mergeAll', count: openPRs.length });
  };

  const doMergeAll = async () => {
    const openPRs = prStatus?.pull_requests.filter((pr) => pr.pr_state === "open" && pr.can_merge !== false) ?? [];
    if (openPRs.length === 0) return;

    setMergingAll(true);
    setMergeAllResults(null);
    setError(null);

    const results: MergeAllResult[] = [];

    try {
      for (let i = 0; i < openPRs.length; i++) {
        const pr = openPRs[i];
        setMergingAllProgress(`Merging ${i + 1} of ${openPRs.length}...`);
        try {
          setProcessingPR(pr.pr_number);
          const result = await mergePullRequest(user, projectName, pr.repo_name, pr.pr_number);
          const msg = result?.branch_delete_warning
            ? `Merged successfully (branch cleanup warning: ${result.branch_delete_warning})`
            : "Merged successfully";
          results.push({ prNumber: pr.pr_number, repoName: pr.repo_name, success: true, message: msg });
        } catch (err: any) {
          results.push({ prNumber: pr.pr_number, repoName: pr.repo_name, success: false, message: err.message || "Failed to merge" });
        }
      }

      setMergeAllResults(results);

      // Refresh status after all merges
      try {
        await postMergeRefresh();
      } catch (err: any) {
        setError(err.message || "Failed to refresh status after merge");
      }
    } finally {
      setProcessingPR(null);
      setMergingAll(false);
      setMergingAllProgress(null);
    }
  };

  const getPRStateColor = (state: string): string => {
    switch (state) {
      case "open":
        return "text-green-600";
      case "merged":
        return "text-purple-600";
      case "closed":
        return "text-gray-600";
      default:
        return "text-gray-600";
    }
  };

  const getPRStateIcon = (state: string): string => {
    switch (state) {
      case "open":
        return "🟢";
      case "merged":
        return "🟣";
      case "closed":
        return "⚫";
      default:
        return "⚪";
    }
  };

  if (loading) {
    return (
      <div className="pr-status-panel">
        <div className="pr-status-header">
          <h3>Active PR Campaign</h3>
          <button onClick={onClose} className="close-button">
            ✕
          </button>
        </div>
        <div className="pr-status-content">
          <div className="loading-spinner">Loading PR campaign...</div>
        </div>
      </div>
    );
  }

  if (error && !prStatus) {
    return (
      <div className="pr-status-panel">
        <div className="pr-status-header">
          <h3>Active PR Campaign</h3>
          <button onClick={onClose} className="close-button">
            ✕
          </button>
        </div>
        <div className="pr-status-content">
          <div className="error-message">❌ {error}</div>
          <Button onClick={handleRefresh} disabled={refreshing}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  if (!prStatus) {
    return null;
  }

  return (
    <div className="pr-status-panel">
      <div className="pr-status-header">
        <h3>Active PR Campaign</h3>
        <div className="pr-status-header-actions">
          {prStatus.open_prs > 0 && (
            <Button
              onClick={handleMergeAll}
              disabled={mergingAll || processingPR !== null || !prStatus.pull_requests.some((pr) => pr.pr_state === "open" && pr.can_merge !== false)}
              className="merge-all-button"
            >
              {mergingAll ? (mergingAllProgress || "Merging...") : `⇶ Merge All (${prStatus.open_prs})`}
            </Button>
          )}
          <button onClick={onClose} className="close-button">
            ✕
          </button>
        </div>
      </div>

      <div className="pr-status-content">
        {/* Inline error banner (real failures) */}
        {error && (
          <div className="error-message">❌ {error}</div>
        )}

        {/* Branch deletion warning banner (merge succeeded but branch not deleted) */}
        {mergeWarning && (
          <div className="warning-message" role="alert" aria-live="polite">⚠️ {mergeWarning}</div>
        )}

        {/* Summary */}
        <div className="pr-status-summary">
          <div className="summary-item">
            <span className="summary-label">Project State:</span>
            <span className={`summary-value ${prStatus.project_state === 'open' ? 'text-blue-600 font-bold' : ''}`}>
              {prStatus.project_state === 'new' && '🆕 New'}
              {prStatus.project_state === 'draft' && '📝 Draft'}
              {prStatus.project_state === 'open' && '🔵 Open'}
              {prStatus.project_state === 'synced' && '✅ Synced'}
            </span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Total PRs:</span>
            <span className="summary-value">{prStatus.total_prs}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Open:</span>
            <span className="summary-value text-green-600">{prStatus.open_prs}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Merged:</span>
            <span className="summary-value text-purple-600">{prStatus.merged_prs}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Closed:</span>
            <span className="summary-value text-gray-600">{prStatus.closed_prs}</span>
          </div>
        </div>

        {/* Merge All Results */}
        {mergeAllResults && (
          <div className="merge-all-results">
            <h4>Merge All Results</h4>
            {mergeAllResults.map((result) => (
              <div key={`${result.repoName}#${result.prNumber}`} className={`merge-result-item ${result.success ? "merge-result-success" : "merge-result-failure"}`}>
                <span className="merge-result-icon">{result.success ? "✅" : "❌"}</span>
                <span className="merge-result-repo">{result.repoName}</span>
                <span className="merge-result-pr">#{result.prNumber}</span>
                <span className="merge-result-message">{result.message}</span>
              </div>
            ))}
          </div>
        )}

        {/* PR List - active panel renders only open PRs.
            Merged/closed PRs live in the "PR Campaigns" view. We defensively
            filter on the client too in case stale state, cached responses
            or websocket updates ever include resolved PRs. */}
        {(() => {
          const openPRs = prStatus.pull_requests.filter(
            (pr) => pr.pr_state === "open"
          );
          return openPRs.length > 0 ? (
          <div className="pr-list">
            <h4>Pull Requests</h4>
            {openPRs.map((pr) => (
              <div key={`${pr.repo_name}-${pr.pr_number}`} className="pr-item" data-testid="repo-pr-row">
                <div className="pr-item-header">
                  <span className={`pr-state ${getPRStateColor(pr.pr_state)}`}>
                    {getPRStateIcon(pr.pr_state)} {pr.pr_state.toUpperCase()}
                  </span>
                  <span className="pr-number">#{pr.pr_number}</span>
                </div>
                {pr.source_project_name && (
                  <div className="pr-source-project">
                    <span className="source-project-label">🔗 From project:</span>{" "}
                    <span className="source-project-name">{pr.source_project_name}</span>
                  </div>
                )}
                <div className="pr-item-repo">{pr.repo_name}</div>
                <div className="pr-item-branches">
                  <span className="branch">{pr.branch_name}</span>
                  <span className="arrow">→</span>
                  <span className="branch">{pr.target_branch}</span>
                </div>
                <div className="pr-item-time">
                  <span className="time-label">Opened:</span> {formatRelativeTime(pr.created_at)}
                  {pr.updated_at && new Date(pr.updated_at).getTime() !== new Date(pr.created_at).getTime() && (
                    <>
                      {" • "}
                      <span className="time-label">Updated:</span> {formatRelativeTime(pr.updated_at)}
                    </>
                  )}
                </div>
                <a
                  href={pr.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="pr-link"
                >
                  View PR →
                </a>
                {pr.can_merge === false && pr.merge_block_reason && (
                  <div className="warning-message">Merge unavailable: {pr.merge_block_reason}</div>
                )}
                {pr.can_close === false && pr.close_block_reason && (
                  <div className="warning-message">Close unavailable: {pr.close_block_reason}</div>
                )}
                {/* Action buttons - only show for open PRs */}
                {pr.pr_state === "open" && (
                  <div className="pr-item-actions">
                    <Button
                      size="sm"
                      onClick={() => handleMergePR(pr.pr_number, pr.repo_name)}
                      disabled={processingPR === pr.pr_number || pr.can_merge === false}
                      title={pr.can_merge === false ? pr.merge_block_reason || undefined : undefined}
                      className="merge-button"
                    >
                      {processingPR === pr.pr_number ? "Processing..." : "✓ Merge"}
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => handleClosePR(pr.pr_number, pr.repo_name)}
                      disabled={processingPR === pr.pr_number || pr.can_close === false}
                      title={pr.can_close === false ? pr.close_block_reason || undefined : undefined}
                      className="close-button"
                    >
                      {processingPR === pr.pr_number ? "Processing..." : "✕ Close"}
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="no-prs">
            <p>No open pull requests for this project.</p>
            <p className="text-sm text-gray-500">
              Merged and closed pull requests are available in the "PR Campaigns" view.
            </p>
          </div>
        );
        })()}

        {/* Actions */}
        <div className="pr-status-actions">
          <Button onClick={handleRefresh} disabled={refreshing}>
            {refreshing ? "Refreshing..." : "🔄 Refresh Status"}
          </Button>
          <Button onClick={onClose} variant="secondary">
            Close
          </Button>
        </div>
      </div>

      {/* Confirm dialogs for merge / close / merge-all */}
      {pendingAction?.type === 'merge' && (
        <ConfirmDialog
          open={true}
          title={`Merge PR #${pendingAction.prNumber}?`}
          description={`This will merge pull request #${pendingAction.prNumber} in ${pendingAction.repoName}. This action cannot be undone.`}
          confirmLabel="Merge"
          onConfirm={() => { setPendingAction(null); void doMergePR(pendingAction.prNumber, pendingAction.repoName); }}
          onCancel={() => setPendingAction(null)}
        />
      )}
      {pendingAction?.type === 'close' && (
        <ConfirmDialog
          open={true}
          title={`Close PR #${pendingAction.prNumber}?`}
          description={`This will close pull request #${pendingAction.prNumber} in ${pendingAction.repoName} without merging. The workflow changes will not be applied to the repository.`}
          confirmLabel="Close PR"
          destructive
          onConfirm={() => { setPendingAction(null); void doClosePR(pendingAction.prNumber, pendingAction.repoName); }}
          onCancel={() => setPendingAction(null)}
        />
      )}
      {pendingAction?.type === 'mergeAll' && (
        <ConfirmDialog
          open={true}
          title={`Merge all ${pendingAction.count} open pull request(s)?`}
          description={`This will attempt to merge all ${pendingAction.count} open pull request(s) for this project. Each merge cannot be undone.`}
          confirmLabel="Merge all"
          onConfirm={() => { setPendingAction(null); void doMergeAll(); }}
          onCancel={() => setPendingAction(null)}
        />
      )}
    </div>
  );
};

export default PRStatusPanel;
