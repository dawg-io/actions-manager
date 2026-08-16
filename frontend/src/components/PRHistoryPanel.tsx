import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  closePullRequest,
  getPRCampaigns,
  mergePullRequest,
  PRCampaign,
  PRCampaignPRItem,
  PRCampaignsResponse,
  RollbackCreateResponse,
} from "../api/pullRequests";
import { formatRelativeTime } from "../utils/timeFormat";
import { normalizeWorkflowFilename } from "../utils/workflowFilename";
import ConfirmDialog from "./ConfirmDialog";
import RollbackCampaignModal from "./RollbackCampaignModal";
import { Button } from "./ui/button";
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from "./ui/accordion";
import { toast } from "../utils/toast";
import { usePagedList, PAGE_SIZE_OPTIONS, UsePagedListResult } from "../hooks/usePagedList";

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

// The snapshot maps are all keyed "owner/repo on branch" because a repo can be
// targeted on several branches in one campaign; the repo header shows the first.
const firstForRepo = <T,>(map: Record<string, T> | undefined, repoName: string): T | null =>
  Object.entries(map ?? {}).find(([key]) => key.startsWith(`${repoName} on `))?.[1] ?? null;

// The branch half of that same key — non-null exactly when firstForRepo matched,
// since both test the same prefix. A repo's default branch differs per repo, so
// a base SHA on its own doesn't say what it is the base of.
const firstBranchForRepo = (map: Record<string, unknown> | undefined, repoName: string): string | null =>
  Object.keys(map ?? {}).find((key) => key.startsWith(`${repoName} on `))?.slice(`${repoName} on `.length) ?? null;

const snapshotForRepo = (campaign: PRCampaign | undefined, repoName: string) => ({
  baseSha: firstForRepo(campaign?.base_commits, repoName),
  baseBranch: firstBranchForRepo(campaign?.base_commits, repoName),
  prUrl: firstForRepo(campaign?.target_pr_urls, repoName),
  protection: firstForRepo(campaign?.branch_protection, repoName),
});

const branchOptionLabels: Record<string, string> = {
  default: "Default branch",
  pattern: "Pattern",
};

const formatPolicyVersion = (version: number | null, sha256: string) =>
  version !== null && version !== undefined ? `v${version}` : sha256.slice(0, 7);

type BranchProtection = NonNullable<PRCampaign['branch_protection']>[string];

// GitHub's enforce_admins is true when admins are *not* exempt, so the wording
// is derived here rather than stored inverted.
const describeProtection = (protection: BranchProtection): string => {
  if (protection.status === 'none') return 'no branch protection';
  if (protection.status !== 'protected') return 'protection unreadable';

  const checks = protection.required_status_checks ?? [];
  return [
    protection.required_reviews ? `${protection.required_reviews} reviews` : 'no required reviews',
    checks.length > 0 ? `checks: ${checks.join(', ')}` : 'no required checks',
    protection.enforce_admins ? 'admins enforced' : 'admins exempt',
  ].join(' · ');
};

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
                variant="merge"
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
  const [rollbackCampaign, setRollbackCampaign] = useState<PRCampaign | null>(null);
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

  const completedPaged = usePagedList(completedCampaigns);
  const activityPaged = usePagedList(filteredActivity);

  const allRepos = useMemo(
    () => Array.from(new Set((data?.pull_requests ?? []).map((pr) => pr.repo_name))).sort((a, b) => a.localeCompare(b)),
    [data]
  );
  const allTargetBranches = useMemo(
    () => Array.from(new Set((data?.pull_requests ?? []).map((pr) => pr.target_branch))).sort((a, b) => a.localeCompare(b)),
    [data]
  );

  // "campaign-<id>" of a source campaign -> the campaign that rolls it back, so
  // both cards can name the other without the API carrying a reverse field.
  const rollbackBySource = useMemo(() => {
    const map = new Map<string, PRCampaign>();
    (data?.campaigns ?? []).forEach((campaign) => {
      if (campaign.rollback_of_campaign_id != null) {
        map.set(`campaign-${campaign.rollback_of_campaign_id}`, campaign);
      }
    });
    return map;
  }, [data]);

  const campaignNameById = useMemo(() => {
    const map = new Map<string, string>();
    (data?.campaigns ?? []).forEach((campaign) => map.set(campaign.campaign_id, campaign.campaign_name));
    return map;
  }, [data]);

  /** Per-repo delivery failures, which come back on a 200 alongside any successes. */
  const rollbackFailures = (result: RollbackCreateResponse) =>
    Object.entries(result.results ?? {})
      .filter(([, r]) => r?.status !== "pr_created" && r?.status !== "pr_updated")
      .map(([key, r]) => `${key}: ${r?.error || "delivery failed"}`);

  const handleRolledBack = async (result: RollbackCreateResponse) => {
    setRollbackCampaign(null);
    setError(null);
    setSuccess(null);
    const failures = rollbackFailures(result);
    const skipped = result.skipped.length;
    let skippedNote = "";
    if (skipped === 1) {
      skippedNote = " 1 repository was skipped as non-invertible.";
    } else if (skipped > 1) {
      skippedNote = ` ${skipped} repositories were skipped as non-invertible.`;
    }
    if (failures.length > 0) {
      skippedNote += ` Failed: ${failures.join("; ")}`;
    }
    if (result.aborted) {
      skippedNote += ` Delivery stopped early at ${result.aborted}`;
    }

    // A 200 with no PRs is still a failed rollback — reporting it as success is
    // how "opened with 0 pull requests" ends up in a green toast.
    const opened = result.prs_created > 0;
    const plural = result.prs_created === 1 ? "" : "s";
    const headline = opened
      ? `Rollback campaign opened with ${result.prs_created} pull request${plural}.`
      : "No rollback pull requests were opened.";
    const message = `${headline}${skippedNote}`;

    try {
      await refreshProjectCampaignState(false);
      if (opened) {
        setSuccess(message);
        toast.success(message);
      } else {
        setError(message);
        toast.error(message);
      }
    } catch (refreshError) {
      console.warn("⚠️ Rollback campaign created but refresh failed:", refreshError);
      setError(REFRESH_WARNING);
      toast.warning(REFRESH_WARNING);
    }
  };

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

  const renderWorkflowChips = (workflows: string[] | string | null, campaign?: PRCampaign) => {
    const names = Array.isArray(workflows)
      ? workflows
      : (workflows || "").split(",").map((name) => name.trim()).filter(Boolean);

    // The snapshot is keyed by the stored workflow name, the chips render the
    // normalized filename, so match on the normalized form. Snapshotted
    // workflows with no chip of their own are appended rather than dropped.
    const applied = new Map(
      Object.entries(campaign?.policy_version ?? {}).map(
        ([name, version]) => [normalizeWorkflowFilename(name), version]
      )
    );
    // Deduplicated after normalizing: the stored forms "ci" and "ci.yml" both
    // occur and collapse to one filename, which would otherwise render two
    // chips sharing a React key.
    const shown = [...new Set(names.map(normalizeWorkflowFilename))];
    const allNames = [...shown, ...[...applied.keys()].filter((name) => !shown.includes(name))];

    if (allNames.length === 0) return <span className="pr-campaign-muted">No workflows recorded</span>;
    return (
      <div className="pr-history-workflows">
        {allNames.map((name) => {
          const version = applied.get(name);
          return (
            <span
              key={name}
              className="pr-history-workflow-chip"
              title={version ? `Applied at campaign creation — sha256 ${version.sha256.slice(0, 16)}…` : undefined}
            >
              🔀 {name}
              {version && ` · ${formatPolicyVersion(version.version, version.sha256)}`}
            </span>
          );
        })}
      </div>
    );
  };

  const renderPaginationControls = (paged: UsePagedListResult<unknown>, idPrefix: string) => (
    <div className="pr-pagination">
      <div className="pr-history-filter-group">
        <label className="pr-history-filter-label" htmlFor={`${idPrefix}-page-size`}>Per page</label>
        <select
          id={`${idPrefix}-page-size`}
          className="pr-history-filter-select"
          value={String(paged.pageSize)}
          onChange={(e) => paged.setPageSize(e.target.value === "all" ? "all" : Number(e.target.value))}
        >
          {PAGE_SIZE_OPTIONS.map((opt) => (
            <option key={String(opt)} value={String(opt)}>{opt === "all" ? "All" : opt}</option>
          ))}
        </select>
      </div>
      {paged.pageSize !== "all" && paged.totalPages > 1 && (
        <div className="pr-pagination-nav">
          <button type="button" className="pr-pagination-btn" disabled={paged.page <= 1} onClick={() => paged.setPage(paged.page - 1)}>
            Previous
          </button>
          <span className="pr-pagination-info">Page {paged.page} of {paged.totalPages}</span>
          <button type="button" className="pr-pagination-btn" disabled={paged.page >= paged.totalPages} onClick={() => paged.setPage(paged.page + 1)}>
            Next
          </button>
        </div>
      )}
    </div>
  );

  const renderPRTable = (prs: PRCampaignPRItem[], includeActions: boolean, campaign?: PRCampaign) => {
    // Group PRs by repository
    const grouped = prs.reduce((acc, pr) => {
      if (!acc[pr.repo_name]) acc[pr.repo_name] = [];
      acc[pr.repo_name].push(pr);
      return acc;
    }, {} as Record<string, PRCampaignPRItem[]>);

    // Snapshotted targets that produced no PR would otherwise vanish from a
    // partially-rolled-out campaign, which is exactly what it needs to show.
    const repoNames = Array.from(
      new Set([...Object.keys(grouped), ...(campaign?.target_repos ?? [])])
    );

    return (
      <div className="pr-campaign-grouped-list">
        {repoNames.map((repoName) => {
          const repoPRs = grouped[repoName] ?? [];
          const { baseSha, baseBranch, prUrl, protection } = snapshotForRepo(campaign, repoName);
          const hasSnapshot = baseSha || prUrl || protection;
          return (
            <div key={repoName} className="pr-campaign-repo-group">
              <h4 className="pr-campaign-repo-title">{repoName}</h4>
              {hasSnapshot && (
                <div className="pr-campaign-repo-snapshot" data-testid="repo-snapshot-line">
                  {baseSha && (
                    <span title={`Base commit on ${baseBranch} at campaign creation: ${baseSha}`}>
                      base {baseBranch} {baseSha.slice(0, 7)}
                    </span>
                  )}
                  {prUrl && (
                    <a href={prUrl} target="_blank" rel="noopener noreferrer" className="pr-campaign-pr-link">
                      PR #{prUrl.split('/').pop()}
                    </a>
                  )}
                  {protection && (
                    <span title={protection.error || undefined}>{describeProtection(protection)}</span>
                  )}
                </div>
              )}
              <div className="pr-campaign-repo-prs">
                {repoPRs.length > 0 ? (
                  repoPRs.map((pr) => (
                    <PRRow
                      key={`${pr.pr_id}-${pr.pr_state}`}
                      pr={pr}
                      includeActions={includeActions}
                      processingKey={processingKey}
                      setPendingAction={setPendingAction}
                    />
                  ))
                ) : (
                  <div className="pr-campaign-grouped-pr pr-campaign-muted" data-testid="repo-no-pr-row">
                    No PR opened
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const renderRollbackLinks = (campaign: PRCampaign) => {
    const sourceName = campaign.rollback_of_campaign_id != null
      ? campaignNameById.get(`campaign-${campaign.rollback_of_campaign_id}`)
      : undefined;
    const rolledBackBy = rollbackBySource.get(campaign.campaign_id);
    if (!sourceName && !rolledBackBy) return null;
    return (
      <div className="pr-rollback-links">
        {sourceName && (
          <span className="pr-history-source-project-badge" data-testid="rollback-of-badge">
            ↩ Rollback of {sourceName}
          </span>
        )}
        {rolledBackBy && (
          <span className="pr-history-source-project-badge" data-testid="rolled-back-by-badge">
            ↩ Rolled back by {rolledBackBy.campaign_name}
          </span>
        )}
      </div>
    );
  };

  const renderCampaignCard = (campaign: PRCampaign, operational: boolean) => {
    const openPRs = openPRsForCampaign(campaign);
    const mergeableOpenPRs = mergeableOpenPRsForCampaign(campaign);
    const targetCount = campaign.target_repos?.length ?? 0;
    return (
      <AccordionItem key={campaign.campaign_id} value={campaign.campaign_id} className="pr-campaign-card">
        <AccordionTrigger
          className="pr-campaign-card-header"
          trailing={
            <div className="pr-campaign-header-actions">
              {/* Outside the operational gate on purpose: a fully merged
                  campaign sits in Completed, and that is exactly when a
                  rollback is wanted. Passed as `trailing` so it stays a real
                  <button> beside the toggle instead of nested inside it. */}
              {campaign.merged_count > 0 && (
                <Button
                  variant="outline"
                  onClick={() => setRollbackCampaign(campaign)}
                  disabled={processingKey !== null}
                  data-testid="rollback-campaign-button"
                  title={`Builds the inverse of the ${campaign.merged_count} merged pull request${campaign.merged_count === 1 ? "" : "s"} for review before any revert PR opens.`}
                >
                  Roll Back Campaign
                </Button>
              )}
              <div className="pr-campaign-progress" aria-label={`${campaign.completion_percentage}% complete`}>
                <span>{campaign.completion_percentage}%</span>
              </div>
            </div>
          }
        >
          <div className="pr-campaign-header-title">
            <div className="pr-campaign-eyebrow">Campaign: {campaign.campaign_name}</div>
            <h3>{campaign.campaign_name}</h3>
            {campaign.campaign_description && (
              <p className="pr-campaign-description">{campaign.campaign_description}</p>
            )}
            <p>
              Status: <strong>{statusLabels[campaign.campaign_status] || campaign.campaign_status}</strong>
              {" · "}
              {campaign.open_count} open • {campaign.merged_count} merged • {campaign.closed_count} closed
            </p>
          </div>
        </AccordionTrigger>
        <AccordionContent>
          {renderRollbackLinks(campaign)}
          <div className="pr-campaign-meta-grid">
            <div><span>Project</span><strong>{campaign.project_name}{campaign.project_code ? ` (${campaign.project_code})` : ""}</strong></div>
            <div><span>Created by</span><strong>{campaign.created_by || "Unknown"}</strong></div>
            <div><span>Created</span><strong>{formatRelativeTime(campaign.created_at)}</strong></div>
            <div>
              <span>Target branch</span>
              {/* The configured mode, not the branches it resolved to — a
                  project set to "default" follows each repo's own default. */}
              <strong title={campaign.target_branches.join(", ")}>
                {(campaign.branch_option && branchOptionLabels[campaign.branch_option])
                  || campaign.target_branches.join(", ")
                  || "Unknown"}
              </strong>
            </div>
            <div>
              <span>Repositories affected</span>
              {/* Targets that opened no PR are only in target_repos, so the two
                  counts diverge exactly when one failed to produce a PR. */}
              <strong title={(campaign.target_repos ?? campaign.repositories).join(", ")}>
                {targetCount > campaign.repositories.length
                  ? `${campaign.repositories.length} of ${targetCount} targeted`
                  : campaign.repositories.length}
              </strong>
            </div>
            <div><span>Remaining to merge</span><strong>{campaign.open_count}</strong></div>
            <div><span>Completed</span><strong>{campaign.completed_at ? formatRelativeTime(campaign.completed_at) : "In progress"}</strong></div>
          </div>

          {renderWorkflowChips(campaign.workflow_names, campaign)}
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
                variant="merge"
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

          {renderPRTable(campaign.pull_requests, operational, campaign)}
        </AccordionContent>
      </AccordionItem>
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
          <span className="pr-history-spinner" />{' '}
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
          <Accordion type="multiple" defaultValue={activeCampaigns.map((c) => c.campaign_id)} className="pr-campaign-list">
            {activeCampaigns.map((campaign) => renderCampaignCard(campaign, true))}
          </Accordion>
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
          <>
            {renderPaginationControls(completedPaged, "completed")}
            <Accordion type="multiple" className="pr-campaign-list">
              {completedPaged.pageItems.map((campaign) => renderCampaignCard(campaign, false))}
            </Accordion>
          </>
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
              <label className="pr-history-filter-label" htmlFor="pr-activity-filter-repo">Repository</label>
              <select id="pr-activity-filter-repo" className="pr-history-filter-select" value={filters.repo} onChange={(e) => setFilters({ ...filters, repo: e.target.value })}>
                <option value="">All repositories</option>
                {allRepos.map((repo) => <option key={repo} value={repo}>{repo}</option>)}
              </select>
            </div>
            <div className="pr-history-filter-group">
              <label className="pr-history-filter-label" htmlFor="pr-activity-filter-workflow">Workflow</label>
              <input id="pr-activity-filter-workflow" className="pr-history-filter-input" value={filters.workflow} onChange={(e) => setFilters({ ...filters, workflow: e.target.value })} placeholder="Filter by workflow" />
            </div>
            <div className="pr-history-filter-group">
              <label className="pr-history-filter-label" htmlFor="pr-activity-filter-state">PR state</label>
              <select id="pr-activity-filter-state" className="pr-history-filter-select" value={filters.state} onChange={(e) => setFilters({ ...filters, state: e.target.value })}>
                <option value="all">All states</option>
                <option value="open">Open</option>
                <option value="merged">Merged</option>
                <option value="closed">Closed</option>
              </select>
            </div>
            <div className="pr-history-filter-group">
              <label className="pr-history-filter-label" htmlFor="pr-activity-filter-target-branch">Target branch</label>
              <select id="pr-activity-filter-target-branch" className="pr-history-filter-select" value={filters.targetBranch} onChange={(e) => setFilters({ ...filters, targetBranch: e.target.value })}>
                <option value="">All branches</option>
                {allTargetBranches.map((branch) => <option key={branch} value={branch}>{branch}</option>)}
              </select>
            </div>
            <div className="pr-history-filter-group">
              <label className="pr-history-filter-label" htmlFor="pr-activity-filter-date">Date</label>
              <input id="pr-activity-filter-date" type="date" className="pr-history-filter-input" value={filters.date} onChange={(e) => setFilters({ ...filters, date: e.target.value })} />
            </div>
            <div className="pr-history-filter-group">
              <label className="pr-history-filter-label" htmlFor="pr-activity-filter-actor">Actor</label>
              <input id="pr-activity-filter-actor" className="pr-history-filter-input" value={filters.actor} onChange={(e) => setFilters({ ...filters, actor: e.target.value })} placeholder="Filter by actor" />
            </div>
          </div>
          {renderPaginationControls(activityPaged, "activity")}
          {filteredActivity.length > 0 ? renderPRTable(activityPaged.pageItems, false) : (
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

      <RollbackCampaignModal
        open={rollbackCampaign !== null}
        user={user}
        projectName={projectName}
        campaign={rollbackCampaign}
        onClose={() => setRollbackCampaign(null)}
        onRolledBack={(result) => { void handleRolledBack(result); }}
      />
    </div>
  );
};

export default PRHistoryPanel;
