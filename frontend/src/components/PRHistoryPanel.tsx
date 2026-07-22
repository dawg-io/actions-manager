import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  closePullRequest,
  getPRCampaigns,
  mergePullRequest,
  PRCampaign,
  PRCampaignPRItem,
  PRCampaignsResponse,
} from "../api/pullRequests";
import { formatRelativeTime } from "../utils/timeFormat";
import { normalizeWorkflowFilename } from "../utils/workflowFilename";
import ConfirmDialog from "./ConfirmDialog";
import { Button } from "./ui/button";
import { toast } from "../utils/toast";

interface PRCampaignsPanelProps {
  user: string;
  projectName: string;
  onCampaignStateRefresh?: (refreshFromGitHub?: boolean) => Promise<void>;
}

type CampaignTab = "active" | "completed" | "activity";
type PendingAction =
  | { type: "merge"; pr: PRCampaignPRItem }
  | { type: "close"; pr: PRCampaignPRItem }
  | { type: "mergeCampaign"; campaign: PRCampaign }
  | { type: "closeCampaign"; campaign: PRCampaign }
  | null;

const statusLabels: Record<string, string> = {
  open: "Open",
  completed: "Completed",
  cancelled: "Cancelled",
  partially_completed: "Partially Completed",
  failed: "Failed",
  merged: "Merged",
  closed: "Closed",
};

const REFRESH_WARNING = "The PR was updated, but the latest project state could not be refreshed. Please refresh the page.";

const getStateLabelFn = (state: string) => statusLabels[state] || state;
const getStateClassFn = (state: string) =>
  state === "merged"
    ? "pr-history-state-merged"
    : state === "open"
    ? "pr-campaign-state-open"
    : "pr-history-state-closed";

interface PRRowProps {
  pr: PRCampaignPRItem;
  includeActions: boolean;
  processingKey: string | null;
  setPendingAction: (action: PendingAction) => void;
}

const PRRow: React.FC<PRRowProps> = ({ pr, includeActions, processingKey, setPendingAction }) => {
  const key = `${pr.repo_name}#${pr.pr_number}`;
  const isProcessing = processingKey === key;
  const mergeDisabled = isProcessing || pr.can_merge === false;
  const closeDisabled = isProcessing || pr.can_close === false;

  const workflowsRaw = pr.workflow_names || [];
  const workflows = Array.isArray(workflowsRaw)
    ? workflowsRaw
    : (workflowsRaw || "").split(",").map((name: string) => name.trim()).filter(Boolean);

  const files = (pr.file_names || "").split(",").map((f: string) => f.trim()).filter(Boolean);

  return (
    <div key={`${pr.pr_id}-${pr.pr_state}`} className={`pr-campaign-grouped-pr${pr.is_reusable_workflow_pr ? " pr-campaign-grouped-pr--linked" : ""}`} data-testid="repo-pr-row">
      <div className="pr-campaign-grouped-pr-header">
        <div className="pr-campaign-grouped-pr-info">
          <a href={pr.pr_url} target="_blank" rel="noopener noreferrer" className="pr-campaign-pr-link">
            PR #{pr.pr_number}
          </a>
          <span className={`pr-history-state-badge ${getStateClassFn(pr.pr_state)}`}>
            {getStateLabelFn(pr.pr_state)}
          </span>
          {pr.source_project_name && (
            <span className="pr-history-source-project-badge">
              🔗 {pr.source_project_name}
            </span>
          )}
          <div className="pr-campaign-branches">
            <span className="pr-history-branch">{pr.branch_name}</span>
            <span className="pr-campaign-branch-arrow">→</span>
            <span className="pr-history-branch">{pr.target_branch}</span>
          </div>
        </div>
        <div className="pr-campaign-row-actions">
          {includeActions && pr.pr_state === "open" && (
            <>
              {pr.can_merge === false && pr.merge_block_reason && (
                <span className="pr-campaign-muted">Merge unavailable: {pr.merge_block_reason}</span>
              )}
              {pr.can_close === false && pr.close_block_reason && (
                <span className="pr-campaign-muted">Close unavailable: {pr.close_block_reason}</span>
              )}
              <Button
                size="sm"
                disabled={mergeDisabled}
                title={pr.can_merge === false ? pr.merge_block_reason || undefined : undefined}
                onClick={() => setPendingAction({ type: "merge", pr })}
              >
                {isProcessing ? "Working..." : "Merge"}
              </Button>
              <Button
                size="sm"
                variant="destructive"
                disabled={closeDisabled}
                title={pr.can_close === false ? pr.close_block_reason || undefined : undefined}
                onClick={() => setPendingAction({ type: "close", pr })}
              >
                Close
              </Button>
            </>
          )}
        </div>
      </div>
      <div className="pr-campaign-grouped-workflows">
        <ul>
          {workflows.map((wf: string) => (
            <li key={wf}>{normalizeWorkflowFilename(wf)}</li>
          ))}
        </ul>
      </div>
      {files.length > 0 && (
        <div className="pr-campaign-grouped-workflows" data-testid="repo-pr-files">
          <ul>
            {files.map((f: string) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

const PRHistoryPanel: React.FC<PRCampaignsPanelProps> = ({ user, projectName, onCampaignStateRefresh }) => {
  const [data, setData] = useState<PRCampaignsResponse | null>(null);
  const [activeTab, setActiveTab] = useState<CampaignTab>("active");
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [processingKey, setProcessingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [filters, setFilters] = useState({
    repo: "",
    workflow: "",
    state: "all",
    targetBranch: "",
    date: "",
    actor: "",
  });

  const loadCampaigns = useCallback(async (refreshFromGitHub = false, rethrow = false) => {
    if (!user || !projectName) return;
    setError(null);
    if (refreshFromGitHub) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const campaigns = await getPRCampaigns(user, projectName, refreshFromGitHub);
      setData(campaigns);
    } catch (err: any) {
      setError(err.message || "Failed to load PR campaigns");
      if (rethrow) {
        throw err;
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [projectName, user]);

  const refreshProjectCampaignState = useCallback(async (refreshFromGitHub = false) => {
    await Promise.all([
      loadCampaigns(refreshFromGitHub, true),
      onCampaignStateRefresh ? onCampaignStateRefresh(refreshFromGitHub) : Promise.resolve(),
    ]);
  }, [loadCampaigns, onCampaignStateRefresh]);

  const handleRefreshStatus = () => {
    refreshProjectCampaignState(true).catch((refreshError) => {
      console.warn("⚠️ Could not refresh PR campaign state:", refreshError);
      setError(refreshError?.message || "Failed to refresh PR campaigns");
    });
  };

  useEffect(() => {
    loadCampaigns(false);
  }, [loadCampaigns]);

  const activeCampaigns = useMemo(
    () => data?.campaigns.filter((campaign) => campaign.campaign_status === "open") ?? [],
    [data]
  );
  const completedCampaigns = useMemo(
    () => data?.campaigns.filter((campaign) => campaign.campaign_status !== "open") ?? [],
    [data]
  );

  const filteredActivity = useMemo(() => {
    const rows = data?.pull_requests ?? [];
    const workflowNeedle = filters.workflow.trim().toLowerCase();
    const actorNeedle = filters.actor.trim().toLowerCase();
    return rows.filter((pr) => {
      const workflows = pr.workflow_names || "";
      const actor = pr.actor || pr.author || "";
      return (
        (!filters.repo || pr.repo_name === filters.repo) &&
        (!workflowNeedle || workflows.toLowerCase().includes(workflowNeedle)) &&
        (filters.state === "all" || pr.pr_state === filters.state) &&
        (!filters.targetBranch || pr.target_branch === filters.targetBranch) &&
        (!filters.date || pr.created_at.startsWith(filters.date) || pr.updated_at.startsWith(filters.date)) &&
        (!actorNeedle || actor.toLowerCase().includes(actorNeedle))
      );
    });
  }, [data, filters]);

  const allRepos = useMemo(
    () => Array.from(new Set((data?.pull_requests ?? []).map((pr) => pr.repo_name))).sort((a, b) => a.localeCompare(b)),
    [data]
  );
  const allTargetBranches = useMemo(
    () => Array.from(new Set((data?.pull_requests ?? []).map((pr) => pr.target_branch))).sort((a, b) => a.localeCompare(b)),
    [data]
  );

  const openPRsForCampaign = (campaign: PRCampaign) =>
    campaign.pull_requests.filter((pr) => pr.pr_state === "open");
  const mergeableOpenPRsForCampaign = (campaign: PRCampaign) =>
    openPRsForCampaign(campaign).filter((pr) => pr.can_merge !== false);

  const runPRAction = async (action: Exclude<PendingAction, null>) => {
    const prs =
      action.type === "mergeCampaign" || action.type === "closeCampaign"
        ? openPRsForCampaign(action.campaign)
        : [action.pr];
    const actionablePRs =
      action.type === "merge" || action.type === "mergeCampaign"
        ? prs.filter((pr) => pr.can_merge !== false)
        : prs.filter((pr) => pr.can_close !== false);
    if (actionablePRs.length === 0) return;

    setError(null);
    setSuccess(null);
    try {
      for (const pr of actionablePRs) {
        const key = `${pr.repo_name}#${pr.pr_number}`;
        setProcessingKey(key);
        if (action.type === "merge" || action.type === "mergeCampaign") {
          await mergePullRequest(user, projectName, pr.repo_name, pr.pr_number);
        } else {
          await closePullRequest(user, projectName, pr.repo_name, pr.pr_number);
        }
      }
      const verb = action.type === "merge" || action.type === "mergeCampaign" ? "merged" : "closed";
      try {
        await refreshProjectCampaignState(false);
        const message = `${actionablePRs.length} pull request${actionablePRs.length === 1 ? "" : "s"} ${verb}.`;
        setSuccess(message);
        toast.success(message);
      } catch (refreshError) {
        console.warn("⚠️ PR action succeeded but refresh failed:", refreshError);
        setError(REFRESH_WARNING);
        toast.warning(REFRESH_WARNING);
      }
    } catch (err: any) {
      setError(err.message || "PR campaign action failed");
    } finally {
      setProcessingKey(null);
    }
  };

  const renderWorkflowChips = (workflows: string[] | string | null) => {
    const names = Array.isArray(workflows)
      ? workflows
      : (workflows || "").split(",").map((name) => name.trim()).filter(Boolean);
    if (names.length === 0) return <span className="pr-campaign-muted">No workflows recorded</span>;
    return (
      <div className="pr-history-workflows">
        {names.map((name) => (
          <span key={name} className="pr-history-workflow-chip">🔀 {normalizeWorkflowFilename(name)}</span>
        ))}
      </div>
    );
  };

  const renderPRTable = (prs: PRCampaignPRItem[], includeActions: boolean) => {
    // Group PRs by repository
    const grouped = prs.reduce((acc, pr) => {
      if (!acc[pr.repo_name]) acc[pr.repo_name] = [];
      acc[pr.repo_name].push(pr);
      return acc;
    }, {} as Record<string, PRCampaignPRItem[]>);

    return (
      <div className="pr-campaign-grouped-list">
        {Object.entries(grouped).map(([repoName, repoPRs]) => (
          <div key={repoName} className="pr-campaign-repo-group">
            <h4 className="pr-campaign-repo-title">{repoName}</h4>
            <div className="pr-campaign-repo-prs">
              {repoPRs.map((pr) => (
                <PRRow
                  key={`${pr.pr_id}-${pr.pr_state}`}
                  pr={pr}
                  includeActions={includeActions}
                  processingKey={processingKey}
                  setPendingAction={setPendingAction}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderCampaignCard = (campaign: PRCampaign, operational: boolean) => {
    const openPRs = openPRsForCampaign(campaign);
    const mergeableOpenPRs = mergeableOpenPRsForCampaign(campaign);
    return (
      <div key={campaign.campaign_id} className="pr-campaign-card">
        <div className="pr-campaign-card-header">
          <div>
            <div className="pr-campaign-eyebrow">Campaign: {campaign.campaign_name}</div>
            <h3>{campaign.campaign_name}</h3>
            <p>
              Status: <strong>{statusLabels[campaign.campaign_status] || campaign.campaign_status}</strong>
              {" · "}
              {campaign.open_count} open • {campaign.merged_count} merged • {campaign.closed_count} closed
            </p>
          </div>
          <div className="pr-campaign-progress" aria-label={`${campaign.completion_percentage}% complete`}>
            <span>{campaign.completion_percentage}%</span>
          </div>
        </div>

        <div className="pr-campaign-meta-grid">
          <div><span>Project</span><strong>{campaign.project_name}{campaign.project_code ? ` (${campaign.project_code})` : ""}</strong></div>
          <div><span>Created by</span><strong>{campaign.created_by || "Unknown"}</strong></div>
          <div><span>Created</span><strong>{formatRelativeTime(campaign.created_at)}</strong></div>
          <div><span>Target branch</span><strong>{campaign.target_branches.join(", ") || "Unknown"}</strong></div>
          <div><span>Repositories affected</span><strong>{campaign.repositories.length}</strong></div>
          <div><span>Completed</span><strong>{campaign.completed_at ? formatRelativeTime(campaign.completed_at) : "In progress"}</strong></div>
        </div>

        {renderWorkflowChips(campaign.workflow_names)}
        {campaign.custom_file_paths && campaign.custom_file_paths.length > 0 && (
          <div className="pr-history-workflows">
            {campaign.custom_file_paths.map((path) => (
              <span key={path} className="pr-history-workflow-chip opacity-[0.85]">📄 {path}</span>
            ))}
          </div>
        )}

        {operational && (
          <div className="pr-campaign-actions">
            <Button onClick={handleRefreshStatus} disabled={refreshing}>Refresh Status</Button>
            <Button
              onClick={() => setPendingAction({ type: "mergeCampaign", campaign })}
              disabled={mergeableOpenPRs.length === 0 || processingKey !== null}
              title={mergeableOpenPRs.length === 0 && openPRs.length > 0 ? "No open PRs are currently mergeable. Refresh status or resolve the listed blockers." : undefined}
            >
              Merge Open PRs
            </Button>
            <Button
              variant="destructive"
              onClick={() => setPendingAction({ type: "closeCampaign", campaign })}
              disabled={openPRs.length === 0 || processingKey !== null || !openPRs.some((pr) => pr.can_close !== false)}
            >
              Close Open PRs
            </Button>
          </div>
        )}

        {renderPRTable(campaign.pull_requests, operational)}
      </div>
    );
  };

  const hasAnyCampaigns = (data?.total_campaigns ?? 0) > 0;

  return (
    <div className="pr-history-panel pr-campaigns-panel">
      <div className="pr-history-header">
        <div className="pr-history-title-row">
          <h2 className="pr-history-title">PR Campaigns</h2>
          {data && (
            <div className="pr-history-counts">
              <span className="pr-history-count-badge pr-history-count-total">{data.total_campaigns} campaigns</span>
              <span className="pr-history-count-badge pr-campaign-count-active">{data.active_campaigns} active</span>
              <span className="pr-history-count-badge pr-history-count-merged">{data.completed_campaigns} completed</span>
            </div>
          )}
        </div>
        <p className="pr-history-subtitle">
          Track workflow rollout campaigns, manage open pull requests, and review completed PR activity for this project.
        </p>
        <p className="pr-campaign-definition">
          A PR Campaign is a tracked rollout of workflow changes across repositories using pull requests.
        </p>
      </div>

      {data && (
        <div className="pr-campaign-summary">
          <div><span>Active Campaigns</span><strong>{data.active_campaigns}</strong></div>
          <div><span>Open PRs</span><strong>{data.open_prs}</strong></div>
          <div><span>Merged PRs</span><strong>{data.merged_prs}</strong></div>
          <div><span>Closed PRs</span><strong>{data.closed_prs}</strong></div>
          <div><span>Repositories Affected</span><strong>{data.repositories_affected}</strong></div>
        </div>
      )}

      <div className="pr-campaign-tabs">
        <button className={activeTab === "active" ? "active" : ""} onClick={() => setActiveTab("active")}>Active Campaigns</button>
        <button className={activeTab === "completed" ? "active" : ""} onClick={() => setActiveTab("completed")}>Completed Campaigns</button>
        <button className={activeTab === "activity" ? "active" : ""} onClick={() => setActiveTab("activity")}>All PRs</button>
      </div>

      {loading && (
        <div className="pr-history-loading">
          <span className="pr-history-spinner" />
          Loading PR campaigns…
        </div>
      )}

      {!loading && error && (
        <div className="pr-history-error">
          <span>⚠️ {error}</span>
          <button className="pr-history-retry-btn" onClick={() => loadCampaigns(false)}>Retry</button>
        </div>
      )}

      {!loading && success && <div className="pr-campaign-success">✅ {success}</div>}

      {!loading && !error && !hasAnyCampaigns && (
        <div className="pr-history-empty">
          <div className="pr-history-empty-icon">🚀</div>
          <p className="pr-history-empty-title">No PR campaigns yet</p>
          <p className="pr-history-empty-body">Create pull requests from Project Workflows to start tracking a workflow rollout campaign.</p>
        </div>
      )}

      {!loading && !error && hasAnyCampaigns && activeTab === "active" && (
        activeCampaigns.length > 0 ? (
          <div className="pr-campaign-list">{activeCampaigns.map((campaign) => renderCampaignCard(campaign, true))}</div>
        ) : (
          <div className="pr-history-empty">
            <div className="pr-history-empty-icon">✅</div>
            <p className="pr-history-empty-title">No active PR campaigns</p>
            <p className="pr-history-empty-body">Open workflow delivery pull requests will appear here while they are under review.</p>
          </div>
        )
      )}

      {!loading && !error && hasAnyCampaigns && activeTab === "completed" && (
        completedCampaigns.length > 0 ? (
          <div className="pr-campaign-list">{completedCampaigns.map((campaign) => renderCampaignCard(campaign, false))}</div>
        ) : (
          <div className="pr-history-empty">
            <div className="pr-history-empty-icon">📭</div>
            <p className="pr-history-empty-title">No completed campaigns yet</p>
            <p className="pr-history-empty-body">Merged and closed pull request campaigns will appear here after workflow delivery is completed.</p>
          </div>
        )
      )}

      {!loading && !error && hasAnyCampaigns && activeTab === "activity" && (
        <>
          <div className="pr-history-filters">
            <div className="pr-history-filter-group">
              <label className="pr-history-filter-label">Repository</label>
              <select className="pr-history-filter-select" value={filters.repo} onChange={(e) => setFilters({ ...filters, repo: e.target.value })}>
                <option value="">All repositories</option>
                {allRepos.map((repo) => <option key={repo} value={repo}>{repo}</option>)}
              </select>
            </div>
            <div className="pr-history-filter-group">
              <label className="pr-history-filter-label">Workflow</label>
              <input className="pr-history-filter-input" value={filters.workflow} onChange={(e) => setFilters({ ...filters, workflow: e.target.value })} placeholder="Filter by workflow" />
            </div>
            <div className="pr-history-filter-group">
              <label className="pr-history-filter-label">PR state</label>
              <select className="pr-history-filter-select" value={filters.state} onChange={(e) => setFilters({ ...filters, state: e.target.value })}>
                <option value="all">All states</option>
                <option value="open">Open</option>
                <option value="merged">Merged</option>
                <option value="closed">Closed</option>
              </select>
            </div>
            <div className="pr-history-filter-group">
              <label className="pr-history-filter-label">Target branch</label>
              <select className="pr-history-filter-select" value={filters.targetBranch} onChange={(e) => setFilters({ ...filters, targetBranch: e.target.value })}>
                <option value="">All branches</option>
                {allTargetBranches.map((branch) => <option key={branch} value={branch}>{branch}</option>)}
              </select>
            </div>
            <div className="pr-history-filter-group">
              <label className="pr-history-filter-label">Date</label>
              <input type="date" className="pr-history-filter-input" value={filters.date} onChange={(e) => setFilters({ ...filters, date: e.target.value })} />
            </div>
            <div className="pr-history-filter-group">
              <label className="pr-history-filter-label">Actor</label>
              <input className="pr-history-filter-input" value={filters.actor} onChange={(e) => setFilters({ ...filters, actor: e.target.value })} placeholder="Filter by actor" />
            </div>
          </div>
          {filteredActivity.length > 0 ? renderPRTable(filteredActivity, false) : (
            <div className="pr-history-empty">
              <p className="pr-history-empty-title">No PR activity matches these filters</p>
              <p className="pr-history-empty-body">Adjust the filters to review completed PR activity for this project.</p>
            </div>
          )}
        </>
      )}

      {pendingAction && (
        <ConfirmDialog
          open={true}
          title={
            pendingAction.type === "close" || pendingAction.type === "closeCampaign"
              ? "Close open pull request(s)?"
              : "Merge open pull request(s)?"
          }
          description={
            pendingAction.type === "close" || pendingAction.type === "closeCampaign"
              ? "This will close open pull requests without merging. Workflow changes will not be applied to those repositories."
              : "This will merge open pull requests in this PR Campaign."
          }
          confirmLabel={pendingAction.type === "close" || pendingAction.type === "closeCampaign" ? "Close Open PRs" : "Merge Open PRs"}
          destructive={pendingAction.type === "close" || pendingAction.type === "closeCampaign"}
          onCancel={() => setPendingAction(null)}
          onConfirm={() => {
            const action = pendingAction;
            setPendingAction(null);
            void runPRAction(action);
          }}
        />
      )}
    </div>
  );
};

export default PRHistoryPanel;
