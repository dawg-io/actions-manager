/**
 * PRHistoryDetail – Read-only detail view for a single historical pull request.
 *
 * Displays all metadata stored for the PR including description/body, associated
 * workflows, timestamps and a direct link to GitHub.  No mutating actions are
 * offered here — this component is purely informational.
 */

import React from "react";
import { PRHistoryItem } from "../api/pullRequests";
import { formatRelativeTime } from "../utils/timeFormat";

interface PRHistoryDetailProps {
  pr: PRHistoryItem;
  onBack: () => void;
}

const PRHistoryDetail: React.FC<PRHistoryDetailProps> = ({ pr, onBack }) => {
  const stateIcon = pr.pr_state === "merged" ? "🟣" : "⚫";
  const stateLabel = pr.pr_state === "merged" ? "Merged" : "Closed";
  const stateClass = pr.pr_state === "merged"
    ? "pr-history-state-merged"
    : "pr-history-state-closed";

  const resolvedDate = pr.merged_at || pr.closed_at;

  return (
    <div className="pr-history-detail">
      {/* ------------------------------------------------------------------ */}
      {/* Back navigation                                                     */}
      {/* ------------------------------------------------------------------ */}
      <button className="pr-history-back-btn" onClick={onBack}>
        ‹ Back to PR Campaigns
      </button>

      {/* ------------------------------------------------------------------ */}
      {/* Title row                                                           */}
      {/* ------------------------------------------------------------------ */}
      <div className="pr-history-detail-header">
        <div className="pr-history-detail-title-row">
          <span className={`pr-history-state-badge ${stateClass}`}>
            {stateIcon} {stateLabel}
          </span>
          <h2 className="pr-history-detail-title">
            {pr.title || `PR #${pr.pr_number}`}
            <span className="pr-history-detail-pr-number"> #{pr.pr_number}</span>
          </h2>
        </div>

        <a
          href={pr.pr_url}
          target="_blank"
          rel="noopener noreferrer"
          className="pr-history-github-link"
        >
          View on GitHub ↗
        </a>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Metadata grid                                                       */}
      {/* ------------------------------------------------------------------ */}
      <div className="pr-history-detail-meta-grid">
        <div className="pr-history-meta-item">
          <span className="pr-history-meta-label">Repository</span>
          <span className="pr-history-meta-value">{pr.repo_name}</span>
        </div>

        <div className="pr-history-meta-item">
          <span className="pr-history-meta-label">Source Branch</span>
          <span className="pr-history-meta-value pr-history-branch-chip">{pr.branch_name}</span>
        </div>

        <div className="pr-history-meta-item">
          <span className="pr-history-meta-label">Target Branch</span>
          <span className="pr-history-meta-value pr-history-branch-chip">{pr.target_branch}</span>
        </div>

        {pr.author && (
          <div className="pr-history-meta-item">
            <span className="pr-history-meta-label">Author</span>
            <span className="pr-history-meta-value">
              <a
                href={`https://github.com/${pr.author}`}
                target="_blank"
                rel="noopener noreferrer"
                className="pr-history-author-link"
              >
                @{pr.author}
              </a>
            </span>
          </div>
        )}

        {pr.source_project_name && (
          <div className="pr-history-meta-item">
            <span className="pr-history-meta-label">Source Project</span>
            <span className="pr-history-meta-value pr-history-source-project-badge">
              🔗 {pr.source_project_name}
            </span>
          </div>
        )}

        <div className="pr-history-meta-item">
          <span className="pr-history-meta-label">Created</span>
          <span className="pr-history-meta-value" title={new Date(pr.created_at).toLocaleString()}>
            {formatRelativeTime(pr.created_at)}
          </span>
        </div>

        {resolvedDate && (
          <div className="pr-history-meta-item">
            <span className="pr-history-meta-label">
              {pr.pr_state === "merged" ? "Merged" : "Closed"}
            </span>
            <span className="pr-history-meta-value" title={new Date(resolvedDate).toLocaleString()}>
              {formatRelativeTime(resolvedDate)}
            </span>
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Associated workflows                                                */}
      {/* ------------------------------------------------------------------ */}
      {pr.workflow_names && (
        <div className="pr-history-detail-section">
          <h3 className="pr-history-detail-section-title">Associated Workflows</h3>
          <div className="pr-history-workflows">
            {pr.workflow_names.split(",").map((wf, i) => {
              const name = wf.trim();
              if (!name) return null;
              return (
                <span key={`${pr.pr_id}-wf-${i}`} className="pr-history-workflow-chip">
                  🔀 {name}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* PR description / body                                               */}
      {/* ------------------------------------------------------------------ */}
      {pr.body && (
        <div className="pr-history-detail-section">
          <h3 className="pr-history-detail-section-title">Description</h3>
          <pre className="pr-history-body">{pr.body}</pre>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Footer link                                                         */}
      {/* ------------------------------------------------------------------ */}
      <div className="pr-history-detail-footer">
        <a
          href={pr.pr_url}
          target="_blank"
          rel="noopener noreferrer"
          className="pr-history-github-link-lg"
        >
          Open pull request #{pr.pr_number} on GitHub ↗
        </a>
      </div>
    </div>
  );
};

export default PRHistoryDetail;
