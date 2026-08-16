/* eslint-disable no-restricted-syntax -- Diff view uses inline pre/grid styling */
/**
 * Drift detection panel: surfaces GitHub-side workflow changes per the
 * "Detect GitHub-side workflow changes" issue and the scope-aware drift
 * resolution flow ("Fix design-level drift issue").
 *
 * Renders:
 *  • A compact alert at the top of the workflow panel when drift exists
 *    ("3 workflows changed in GitHub" + Review Drift button).
 *  • A modal listing all drifted (workflow, repo, branch) tuples with a
 *    side-by-side YAML diff view.
 *  • Adopt GitHub Version (scope-aware modal) / Restore ActionsManager
 *    (PR or direct) actions.
 *
 * Drift state is also reported up via the optional onDriftLoaded callback
 * so callers can render per-workflow badges and gate destructive actions.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { DiffColumns, diffGridStyle } from "./DiffColumns";
import {
  getProjectDrift,
  getWorkflowDrift,
  resolveWorkflowDrift,
  adoptGithubVersion,
  bulkResolveWorkflowDrift,
  type WorkflowDriftDetail,
  type DriftDeliveryMode,
  type AdoptResolutionMode,
  type DriftResolution,
  type BulkResolveDriftItem,
} from "../api/drift";
import ConfirmDialog from "./ConfirmDialog";
import { deleteWorkflowFromGitHub, deleteWorkflowFromDatabase } from "../api/workflows";
import { getDocsUrl } from "../help/helpLinks";

/**
 * Prefer the backend's safe FastAPI error detail over the raw axios message
 * (which is just "Request failed with status code 500"). Same pattern used
 * across the app (ProjectMgmt, CustomFiles, workflowOperations).
 */
const driftErrorMessage = (err: unknown, fallback: string): string => {
  const r = err as { response?: { data?: { detail?: string } }; message?: string };
  return r?.response?.data?.detail || r?.message || fallback;
};

/**
 * The status row's message for a project with no known drift: unchecked
 * (GitHub didn't respond), clean-with-a-timestamp, or never checked.
 */
const getDriftStatusRowMessage = (uncheckedCount: number, lastChecked: string | null): string => {
  if (uncheckedCount > 0) {
    return `Couldn't check ${uncheckedCount} workflow${uncheckedCount === 1 ? "" : "s"} — GitHub didn't respond. Drift status may be out of date.`;
  }
  if (lastChecked) {
    return `No drift detected — last checked ${new Date(lastChecked).toLocaleString()}`;
  }
  return "Not checked yet";
};

interface DriftDetectionProps {
  user: string;
  projectId: number | null;
  projectName: string;
  selectedRepos: string[];
  /**
   * Called whenever drift state is (re)loaded so the parent can render
   * per-workflow drift badges and decide whether destructive actions need
   * confirmation.
   */
  onDriftLoaded?: (details: WorkflowDriftDetail[]) => void;
  /**
   * External signal – when this number changes, drift is re-checked.
   * Use this to refresh after a save/PR completes.
   */
  refreshSignal?: number;
  /**
   * Called whenever a resolve action changes a workflow's status server-side
   * (synced_with_github via use_github/direct, under_review via a fix PR).
   * loadDrift() only refreshes this component's own drift list - the parent
   * owns the workflows/rxworkflows state that status badges elsewhere on the
   * page render from, so it needs this callback to patch that sibling state
   * itself. Mirrors the pattern CreatePRModal's PR-campaign flow already
   * uses (ProjectMgmt.tsx's handlePRCreationSuccess).
   */
  onWorkflowStatusesChanged?: (workflowNames: string[], status: string) => void;
  /**
   * Workflow names with drift persisted by the last check, from the project
   * fetch. Renders the banner on first paint so it doesn't pop in and shift
   * the layout once the live check resolves. Superseded by live data as soon
   * as the check completes.
   */
  seededDriftNames?: string[];
}

/**
 * Render two `<pre>` blocks side-by-side highlighting changed lines.
 * Lightweight (no extra deps) inline diff suitable for short workflow files.
 */
/**
 * Shown instead of a diff when the workflow file no longer exists in GitHub.
 *
 * A side-by-side diff renders the missing side as a single blank line, which
 * reads as "the file is empty" rather than "the file is gone". Adopting
 * GitHub's version is also impossible here — the server re-fetches and 404s —
 * so that action is replaced with the two that make sense: put the file back,
 * or accept the deletion and remove the workflow everywhere.
 */
const DeletedInGithubPanel: React.FC<{
  detail: WorkflowDriftDetail;
  busyAction: DriftDeliveryMode | null;
  onRestorePR: () => void;
  onRestoreDirect: () => void;
  onDeleteEverywhere: () => void;
}> = ({ detail, busyAction, onRestorePR, onRestoreDirect, onDeleteEverywhere }) => {
  const disabled = busyAction !== null;
  return (
    <div
      className="rounded-md border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20"
      data-testid="deleted-in-github-panel"
    >
      <p className="text-sm font-medium text-red-900 dark:text-red-200">
        This workflow no longer exists in {detail.repo}
      </p>
      <p className="mt-1 text-xs text-red-800 dark:text-red-300">
        The file was removed from GitHub outside ActionsManager. ActionsManager still manages
        it, so it will keep being reported as drifted until you either put it back or remove it
        here too.
      </p>

      <div className="mt-4 flex flex-col gap-3 sm:flex-row">
        <div className="flex-1">
          <Button
            size="sm"
            variant="default"
            disabled={disabled}
            onClick={onRestorePR}
            className="w-full justify-start"
            data-testid="deleted-restore-pr-button"
          >
            {busyAction === "pr" ? "Creating pull request…" : "Recreate via Pull Request"}
          </Button>
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
            Opens a pull request in <strong>{detail.repo}</strong> that adds the workflow back.
          </p>
        </div>
        <div className="flex-1">
          <Button
            size="sm"
            variant="destructive"
            disabled={disabled}
            onClick={onDeleteEverywhere}
            className="w-full justify-start"
            data-testid="delete-everywhere-button"
          >
            Delete Everywhere
          </Button>
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
            Accepts the deletion: removes this workflow from the other repositories and from
            ActionsManager.
          </p>
        </div>
      </div>

      <button
        type="button"
        disabled={disabled}
        onClick={onRestoreDirect}
        className="mt-3 text-xs text-slate-600 underline hover:text-slate-900 disabled:opacity-50 dark:text-slate-400 dark:hover:text-slate-100"
        data-testid="deleted-restore-direct-button"
      >
        {busyAction === "direct" ? "Restoring directly…" : "Or recreate it directly, without review"}
      </button>
    </div>
  );
};

const SideBySideDiff: React.FC<{
  left: string;
  right: string;
  repo: string;
  branch: string;
  onAdoptGithub: () => void;
  onRestorePR: () => void;
  onRestoreDirect: () => void;
  /** Which restore action is currently running for this row, if any. */
  busyAction: DriftDeliveryMode | null;
}> = ({ left, right, repo, branch, onAdoptGithub, onRestorePR, onRestoreDirect, busyAction }) => {
  const disabled = busyAction !== null;
  return (
    <div
      className="border border-slate-200 dark:border-slate-700 rounded-md overflow-hidden"
      style={diffGridStyle}
    >
      <DiffColumns
        left={left}
        right={right}
        leftLabel="ActionsManager managed version"
        rightLabel="Current GitHub version"
      />

      {/* Action Buttons aligned with columns */}
      <div className="border-t border-r border-slate-200 dark:border-slate-700 px-2 py-3 bg-slate-50/50 dark:bg-slate-800/50 flex flex-col gap-4">
        <div>
          <Button
            size="sm"
            variant="default"
            disabled={disabled}
            onClick={onRestorePR}
            className="w-full justify-start"
            data-testid="restore-pr-button"
          >
            {busyAction === "pr" ? "Creating pull request…" : "Create Fix Pull Request"}
          </Button>
          <p className="text-xs text-slate-600 dark:text-slate-400 mt-1 whitespace-normal">
            Opens a pull request only in <strong>{repo}</strong> that restores this
            workflow to the ActionsManager-managed version. No other repositories are
            changed.{" "}
            <span className="px-1.5 py-0.5 text-[0.65rem] rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200 align-middle">
              Recommended
            </span>
          </p>
        </div>
        <div>
          <Button
            size="sm"
            variant="destructive"
            disabled={disabled}
            onClick={onRestoreDirect}
            className="w-full justify-start"
            data-testid="restore-direct-button"
          >
            {busyAction === "direct" ? "Restoring directly…" : "Restore Directly"}
          </Button>
          <p className="text-xs text-slate-600 dark:text-slate-400 mt-1 whitespace-normal">
            Immediately overwrites the workflow on <strong>{branch}</strong> in{" "}
            <strong>{repo}</strong> with the ActionsManager-managed version. No pull
            request is created.{" "}
            <span className="px-1.5 py-0.5 text-[0.65rem] rounded-full bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 align-middle">
              Immediate GitHub change
            </span>
          </p>
        </div>
      </div>
      <div className="border-t border-slate-200 dark:border-slate-700 px-2 py-3 bg-slate-50/50 dark:bg-slate-800/50 flex flex-col gap-1">
        <Button
          size="sm"
          variant="secondary"
          disabled={disabled}
          onClick={onAdoptGithub}
          className="w-full justify-start"
          data-testid="adopt-github-version-button"
        >
          Adopt GitHub Version
        </Button>
        <p className="text-xs text-slate-600 dark:text-slate-400 mt-1 whitespace-normal">
          Import the GitHub version of <strong>{repo}</strong> into ActionsManager —
          choose to keep it local-only (no GitHub change), sync it to the other
          repositories, or set a per-repo override.
        </p>
      </div>
    </div>
  );
};

/**
 * Scope-aware drift resolution modal: lets the user choose between adopting
 * the GitHub version for the whole project (and syncing the other repos),
 * adopting locally only (current behaviour, with explicit warning), or
 * creating a per-repo override so this repo can intentionally diverge.
 */
const AdoptGithubVersionModal: React.FC<{
  open: boolean;
  onClose: () => void;
  detail: WorkflowDriftDetail | null;
  user: string;
  onResolved: (message: string) => void;
}> = ({ open, onClose, detail, user, onResolved }) => {
  const [mode, setMode] = useState<AdoptResolutionMode>("adopt_project_and_sync");
  const [delivery, setDelivery] = useState<DriftDeliveryMode>("pr");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setMode("adopt_project_and_sync");
      setDelivery("pr");
      setSubmitting(false);
      setError(null);
    }
  }, [open]);

  if (!detail) return null;
  const projectId = detail.project_id ?? null;
  const repoId = detail.repo_id ?? null;
  const affected = detail.affected_repos ?? [];
  const isShared = !!detail.is_shared_workflow;

  const handleConfirm = async () => {
    if (!projectId || !detail.workflow_id) {
      setError("Missing project/workflow context for this drift.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const response = await adoptGithubVersion({
        github_user: user,
        project_id: projectId,
        workflow_id: detail.workflow_id,
        repo_id: repoId ?? undefined,
        repo_name: detail.repo,
        branch: detail.branch,
        resolution_mode: mode,
        delivery_mode: mode === "adopt_project_and_sync" ? delivery : undefined,
      });
      // Branch on the structured response: keep modal open on partial-failure
      // (e.g. some direct pushes failed) so the user sees what happened and
      // can retry or pick a different mode.
      if (response.success === false) {
        setError(response.message || "Adoption did not fully succeed.");
        return;
      }
      onResolved(response.message || "GitHub version adopted.");
      onClose();
    } catch (err: unknown) {
      setError(driftErrorMessage(err, "Failed to adopt GitHub version"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-w-2xl" data-testid="adopt-github-version-modal">
        <DialogHeader>
          <DialogTitle>Adopt GitHub Version</DialogTitle>
          <DialogDescription>
            {isShared ? (
              <>
                This workflow is shared across multiple repositories in this project.
                The GitHub version from <strong>{detail.repo}</strong> is different from
                the ActionsManager version. Choose how this change should be handled.
              </>
            ) : (
              <>
                The GitHub version of <strong>{detail.workflow_filename}</strong> in
                {" "}<strong>{detail.repo}</strong> differs from the ActionsManager
                version. Choose how this change should be handled.
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {/* Option 1: adopt_project_and_sync */}
          <label
            className={`block p-3 rounded-lg border cursor-pointer ${
              mode === "adopt_project_and_sync"
                ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20"
                : "border-slate-200 dark:border-slate-700 hover:border-slate-400"
            }`}
            data-testid="adopt-mode-project-and-sync"
            aria-label="Adopt for project and sync other repositories"
          >
            <div className="flex items-start gap-2">
              <input
                type="radio"
                name="adopt-mode"
                checked={mode === "adopt_project_and_sync"}
                onChange={() => setMode("adopt_project_and_sync")}
                className="mt-1"
              />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">
                    Adopt for project and sync other repositories
                  </span>
                  <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200">
                    Recommended
                  </span>
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                  Use the GitHub version from {detail.repo} as the new project workflow,
                  then sync that version to {affected.length} other
                  {" "}repository{affected.length === 1 ? "" : "ies"} in this project.
                  {" "}<strong>Writes to GitHub</strong> in those repositories (via pull
                  request or direct commit, below).
                </p>
                {mode === "adopt_project_and_sync" && (
                  <div className="mt-2 flex items-center gap-3 text-sm">
                    <label className="flex items-center gap-1">
                      <input
                        type="radio"
                        name="adopt-delivery"
                        checked={delivery === "pr"}
                        onChange={() => setDelivery("pr")}
                      />{' '}
                      Pull request
                    </label>
                    <label className="flex items-center gap-1">
                      <input
                        type="radio"
                        name="adopt-delivery"
                        checked={delivery === "direct"}
                        onChange={() => setDelivery("direct")}
                      />{' '}
                      Direct commit
                    </label>
                  </div>
                )}
              </div>
            </div>
          </label>

          {/* Option 2: adopt_local_only */}
          <label
            className={`block p-3 rounded-lg border cursor-pointer ${
              mode === "adopt_local_only"
                ? "border-amber-500 bg-amber-50 dark:bg-amber-900/20"
                : "border-slate-200 dark:border-slate-700 hover:border-slate-400"
            }`}
            data-testid="adopt-mode-local-only"
            aria-label="Adopt locally only"
          >
            <div className="flex items-start gap-2">
              <input
                type="radio"
                name="adopt-mode"
                checked={mode === "adopt_local_only"}
                onChange={() => setMode("adopt_local_only")}
                className="mt-1"
              />
              <div className="flex-1">
                <span className="font-medium">Adopt locally only</span>
                <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                  Update the ActionsManager draft using the GitHub version from
                  {" "}{detail.repo}, but do not sync the other repositories.
                  {" "}<strong>No GitHub change</strong> — review and deploy the updated
                  draft normally afterward.
                </p>
                {mode === "adopt_local_only" && affected.length > 0 && (
                  <div className="mt-2 px-2 py-1 text-xs rounded bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200">
                    ⚠️ This may cause other repositories to show drift.
                  </div>
                )}
              </div>
            </div>
          </label>

          {/* Option 3: create_repo_override */}
          <label
            className={`block p-3 rounded-lg border cursor-pointer ${
              mode === "create_repo_override"
                ? "border-purple-500 bg-purple-50 dark:bg-purple-900/20"
                : "border-slate-200 dark:border-slate-700 hover:border-slate-400"
            }`}
            data-testid="adopt-mode-repo-override"
            aria-label="Create repo-specific override"
          >
            <div className="flex items-start gap-2">
              <input
                type="radio"
                name="adopt-mode"
                checked={mode === "create_repo_override"}
                onChange={() => setMode("create_repo_override")}
                className="mt-1"
              />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">Create repo-specific override</span>
                  <span className="px-2 py-0.5 text-xs rounded-full bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200">
                    Repo Override
                  </span>
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                  Pin {detail.repo} to its GitHub version as a repo-specific workflow
                  override. <strong>No GitHub change</strong> — the shared project
                  workflow and the other repositories are left untouched.
                </p>
              </div>
            </div>
          </label>
        </div>

        {error && (
          <div className="px-3 py-2 text-sm rounded bg-red-50 text-red-800 border border-red-200 dark:bg-red-900/20 dark:text-red-200 dark:border-red-800">
            {error}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="default"
            onClick={handleConfirm}
            disabled={submitting}
            data-testid="adopt-confirm-button"
          >
            {submitting ? "Working…" : "Confirm"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const DriftDetection: React.FC<DriftDetectionProps> = ({
  user,
  projectId,
  projectName,
  selectedRepos,
  onDriftLoaded,
  refreshSignal,
  onWorkflowStatusesChanged,
  seededDriftNames,
}) => {
  const [drifts, setDrifts] = useState<WorkflowDriftDetail[]>([]);
  const [uncheckedCount, setUncheckedCount] = useState(0);
  const [liveLoaded, setLiveLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [openDiffKey, setOpenDiffKey] = useState<string | null>(null);
  // When the shown state was established. null = never checked, which must not
  // render as "clean" — see the banner below.
  const [lastChecked, setLastChecked] = useState<string | null>(null);
  // Why the state may be older than it looks (e.g. the background sweep can't
  // check this project). Null when nothing is wrong.
  const [staleReason, setStaleReason] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  // GitHub's side of a diff, fetched when a row is expanded. The cached list
  // omits it deliberately: a stored snapshot may no longer match GitHub.
  const [liveDiffs, setLiveDiffs] = useState<Record<string, WorkflowDriftDetail>>({});
  const [diffLoadingKey, setDiffLoadingKey] = useState<string | null>(null);
  const [resolving, setResolving] = useState<string | null>(null);
  const [resolvingMode, setResolvingMode] = useState<DriftDeliveryMode | null>(null);
  const [adoptDetail, setAdoptDetail] = useState<WorkflowDriftDetail | null>(null);
  // Direct restore overwrites GitHub with no PR review, so it is gated behind
  // an explicit confirmation naming the repo + target branch.
  const [confirmDirect, setConfirmDirect] = useState<WorkflowDriftDetail | null>(null);
  // "Delete Everywhere" for a workflow already removed from GitHub: drops the
  // file from the project's other repos and the workflow from ActionsManager.
  const [confirmDeleteEverywhere, setConfirmDeleteEverywhere] = useState<WorkflowDriftDetail | null>(null);
  const [deletingEverywhere, setDeletingEverywhere] = useState(false);

  // Bulk-fix: select multiple drifted workflows and resolve them together.
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [bulkResolving, setBulkResolving] = useState<DriftDeliveryMode | "use_github" | null>(null);
  // Direct restore overwrites GitHub with no PR review - same confirmation
  // gate as the single-item direct restore above, just naming the batch.
  const [confirmBulkDirect, setConfirmBulkDirect] = useState(false);

  const driftKey = useCallback(
    (d: WorkflowDriftDetail) => `${d.workflow_id}::${d.repo}::${d.branch}`,
    [],
  );

  const driftByKey = useMemo(() => {
    const m = new Map<string, WorkflowDriftDetail>();
    drifts.forEach((d) => m.set(driftKey(d), d));
    return m;
  }, [drifts, driftKey]);

  // Groups drifted workflows that have the identical GitHub-side change, so
  // the user can select a whole group in one click instead of eyeballing
  // diffs one at a time. github_sha is a content hash of that file's GitHub
  // blob, so it's a cheap and reliable equality key; github_yaml is a
  // fallback for the rare case a sha wasn't available. __solo__-prefixed
  // keys guarantee items with neither never falsely group together.
  const groupKeyFor = useCallback(
    (d: WorkflowDriftDetail) => d.github_sha ?? d.github_yaml ?? `__solo__${driftKey(d)}`,
    [driftKey],
  );
  const driftGroups = useMemo(() => {
    const groups = new Map<string, WorkflowDriftDetail[]>();
    drifts.forEach((d) => {
      const gk = groupKeyFor(d);
      groups.set(gk, [...(groups.get(gk) ?? []), d]);
    });
    return groups;
  }, [drifts, groupKeyFor]);

  const toggleSelected = useCallback((k: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelectedKeys(new Set(drifts.map(driftKey)));
  }, [drifts, driftKey]);

  const deselectAll = useCallback(() => {
    setSelectedKeys(new Set());
  }, []);

  const selectGroup = useCallback((d: WorkflowDriftDetail) => {
    const group = driftGroups.get(groupKeyFor(d)) ?? [d];
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      group.forEach((g) => next.add(driftKey(g)));
      return next;
    });
  }, [driftGroups, groupKeyFor, driftKey]);

  // Mirrors `drifts` so a failed background check can fall back to the last
  // known state without adding `drifts` as a loadDrift dependency (which would
  // re-trigger the load-on-mount effect on every successful load).
  const driftsRef = useRef<WorkflowDriftDetail[]>([]);
  // Discards out-of-order responses, e.g. the user navigates to a different
  // project before an in-flight request resolves. Same idiom as
  // ProjectMgmt.tsx's loadRequestCounterRef.
  const requestIdRef = useRef(0);

  const loadDrift = useCallback(async (
    opts?: { refresh?: boolean },
  ): Promise<WorkflowDriftDetail[]> => {
    const requestId = ++requestIdRef.current;
    if (!user || !projectId || !projectName || selectedRepos.length === 0) {
      driftsRef.current = [];
      setDrifts([]);
      // Otherwise these carry over from whatever project was last loaded,
      // e.g. showing this project as "last checked 3pm" using another
      // project's timestamp.
      setLastChecked(null);
      setStaleReason(null);
      setUncheckedCount(0);
      // A loaded project with no repos can't drift, so treat that as a
      // completed check and let the seeded banner clear. Before the project
      // loads there is no projectId yet — stay pending so the seed still shows.
      if (projectId) setLiveLoaded(true);
      onDriftLoaded?.([]);
      return [];
    }
    setError(null);
    try {
      const summary = await getProjectDrift(projectId, user, { refresh: opts?.refresh });
      if (requestId !== requestIdRef.current) return driftsRef.current;
      driftsRef.current = summary.drifted_workflows;
      setDrifts(summary.drifted_workflows);
      setLastChecked(summary.last_checked ?? null);
      setStaleReason(summary.stale_reason ?? null);
      // >0 means GitHub couldn't be queried for some repos, so an empty drift
      // list is not evidence that everything is in sync.
      setUncheckedCount(summary.unchecked_count ?? 0);
      setLiveLoaded(true);
      onDriftLoaded?.(summary.drifted_workflows);
      return summary.drifted_workflows;
    } catch (err: unknown) {
      if (requestId !== requestIdRef.current) return driftsRef.current;
      setError(driftErrorMessage(err, "Failed to check drift"));
      // A failed background check must not erase a previously known drift
      // state, so liveLoaded stays as-is: on a first-load failure the seeded
      // banner keeps rendering rather than blanking out.
      return driftsRef.current;
    }
  }, [user, projectId, projectName, selectedRepos, onDriftLoaded]);

  /**
   * Read the stored state and stop there — opening a project costs no GitHub
   * calls at all.
   *
   * This used to fire a live check behind the render whenever the stored state
   * looked old, because nothing else kept it fresh. The background sweep does
   * that now, so re-checking on mount would spend rate limit re-answering a
   * question already answered on a timer. When the sweep genuinely cannot
   * check a project, `stale_reason` says so, which is more honest than a
   * silent refresh that may also fail.
   */
  useEffect(() => {
    loadDrift();
  }, [loadDrift, refreshSignal]);

  /** Run a live check on demand. */
  const handleCheckNow = useCallback(async () => {
    setChecking(true);
    try {
      await loadDrift({ refresh: true });
      // Anything fetched for a diff describes the previous check.
      setLiveDiffs({});
    } finally {
      setChecking(false);
    }
  }, [loadDrift]);

  /**
   * Expand a row, fetching GitHub's current content if the cached row lacks it.
   *
   * The list is served from stored state and omits github_yaml on purpose, so
   * this is where the one API call per opened diff happens.
   */
  const handleToggleDiff = useCallback(async (detail: WorkflowDriftDetail, key: string) => {
    if (openDiffKey === key) {
      setOpenDiffKey(null);
      return;
    }
    setOpenDiffKey(key);
    if (detail.github_yaml !== null || liveDiffs[key] || !user) return;

    setDiffLoadingKey(key);
    try {
      const live = await getWorkflowDrift(detail.workflow_id, user);
      const match = live.drift_details.find(
        (d) => d.repo === detail.repo && d.branch === detail.branch,
      );
      if (match) setLiveDiffs((prev) => ({ ...prev, [key]: match }));
    } catch (err: unknown) {
      setError(driftErrorMessage(err, "Failed to load the GitHub version"));
    } finally {
      setDiffLoadingKey(null);
    }
  }, [openDiffKey, liveDiffs, user]);

  const handleResolve = useCallback(
    async (
      detail: WorkflowDriftDetail,
      resolution: "use_github" | "restore_actionsmanager",
      deliveryMode?: DriftDeliveryMode,
    ) => {
      const key = driftKey(detail);
      setResolving(key);
      setResolvingMode(deliveryMode ?? null);
      setError(null);
      setSuccess(null);
      try {
        const response = await resolveWorkflowDrift(detail.workflow_id, {
          github_user: user,
          repo: detail.repo,
          branch: detail.branch,
          resolution,
          delivery_mode: deliveryMode,
          // What this decision was based on. If GitHub has moved on, the
          // backend 409s rather than overwriting the newer content.
          expected_github_sha: detail.github_sha,
        });

        // Check the resolution result state
        if (response.state === "synced") {
          // Success - drift resolved
          setSuccess(response.message || "Drift resolved successfully");
          onWorkflowStatusesChanged?.([detail.workflow_name], "synced_with_github");

          // Refresh drift data to update badges and capture fresh list
          const refreshed = await loadDrift();

          // Close the diff for this workflow
          if (openDiffKey === key) setOpenDiffKey(null);

          // If no drifts remain (per refreshed data), show completion message
          if (refreshed.length === 0) {
            setSuccess("All workflow drift resolved.");
            // Close modal after a delay
            setTimeout(() => setShowModal(false), 2000);
          }
        } else if (response.state === "drifted") {
          // Drift was not resolved - show warning
          setError(response.message || "Drift was not resolved. Local and GitHub versions still differ.");
          // Keep the diff open
        } else if (response.state === "pr_pending") {
          // PR created — the drift clears once the PR is merged, not now.
          setSuccess(
            response.message
              || `Pull request opened in ${detail.repo}. Review and merge it to complete the restore.`,
          );
          onWorkflowStatusesChanged?.([detail.workflow_name], "under_review");
          await loadDrift();
          if (openDiffKey === key) setOpenDiffKey(null);
        } else {
          // Unknown state or no state - refresh and show message
          setSuccess(response.message);
          await loadDrift();
          if (openDiffKey === key) setOpenDiffKey(null);
        }
      } catch (err: unknown) {
        const message = driftErrorMessage(err, "Resolution failed");
        // A 409 means the file moved on, and the row still holds the SHA that
        // was just rejected — refresh so retrying compares against what is
        // actually on GitHub instead of failing identically forever. loadDrift
        // clears the error itself, so set the message after it, not before.
        if ((err as { response?: { status?: number } })?.response?.status === 409) {
          await loadDrift();
        }
        // Keep diff open on error so the user can see what they were resolving.
        setError(message);
      } finally {
        setResolving(null);
        setResolvingMode(null);
      }
    },
    [driftKey, loadDrift, openDiffKey, user, onWorkflowStatusesChanged],
  );

  const handleBulkResolve = useCallback(
    async (resolution: DriftResolution, deliveryMode?: DriftDeliveryMode) => {
      if (!projectId || selectedKeys.size === 0) return;
      const items: BulkResolveDriftItem[] = [];
      selectedKeys.forEach((k) => {
        const d = driftByKey.get(k);
        // expected_github_sha lets the backend reject any item whose file moved
        // on since the check, without failing the rest of the batch.
        if (d) items.push({
          workflow_id: d.workflow_id,
          repo: d.repo,
          branch: d.branch,
          expected_github_sha: d.github_sha,
        });
      });
      if (items.length === 0) return;

      setBulkResolving(deliveryMode ?? "use_github");
      setError(null);
      setSuccess(null);
      try {
        const response = await bulkResolveWorkflowDrift(projectId, {
          github_user: user,
          items,
          resolution,
          delivery_mode: deliveryMode,
        });
        const okCount = response.results.filter((r) => r.success).length;
        const failCount = response.results.length - okCount;
        const failures = response.results.filter((r) => !r.success);
        const summary = failCount === 0
          ? `${okCount} of ${okCount} resolved successfully.`
          : `${okCount} resolved, ${failCount} failed: `
            + failures.map((f) => `${f.repo} (${f.message})`).join("; ");

        // Same gap as the single-item flow above: the bulk-resolve response
        // only tells this component's own drift list to refresh - the
        // parent's workflows/rxworkflows state (and the status badges it
        // drives) needs the same explicit patch for every item that succeeded.
        const newStatus = resolution === "use_github" || deliveryMode === "direct"
          ? "synced_with_github"
          : "under_review";
        const successNames = response.results
          .filter((r) => r.success)
          .map((r) => driftByKey.get(`${r.workflow_id}::${r.repo}::${r.branch}`)?.workflow_name)
          .filter((name): name is string => Boolean(name));
        if (successNames.length > 0) {
          onWorkflowStatusesChanged?.(successNames, newStatus);
        }

        setSelectedKeys(new Set());
        // loadDrift() clears any error state as soon as it starts (see its
        // own setError(null)), so the outcome must be set AFTER it resolves,
        // not before — otherwise the refresh wipes the message we just set.
        const refreshed = await loadDrift();
        if (failCount === 0 && refreshed.length === 0) {
          setSuccess("All workflow drift resolved.");
          setTimeout(() => setShowModal(false), 2000);
        } else if (failCount === 0) {
          setSuccess(summary);
        } else {
          setError(summary);
        }
      } catch (err: unknown) {
        setError(driftErrorMessage(err, "Bulk resolution failed"));
      } finally {
        setBulkResolving(null);
      }
    },
    [projectId, selectedKeys, driftByKey, user, loadDrift, onWorkflowStatusesChanged],
  );

  const handleDeleteEverywhere = useCallback(async (detail: WorkflowDriftDetail) => {
    setDeletingEverywhere(true);
    setError(null);
    setSuccess(null);
    try {
      // The file is already gone from detail.repo; affected_repos is the rest
      // of the project's repos that still share this workflow. Repos where the
      // file is already absent are skipped server-side.
      const repos = Array.from(new Set([detail.repo, ...(detail.affected_repos ?? [])]));
      await deleteWorkflowFromGitHub(user, repos, detail.workflow_name, "", projectName);
      await deleteWorkflowFromDatabase(user, projectName, detail.workflow_name);

      setConfirmDeleteEverywhere(null);
      setOpenDiffKey(null);
      setSuccess(`'${detail.workflow_name}' removed from ActionsManager and ${repos.length} repositor${repos.length === 1 ? "y" : "ies"}.`);
      await loadDrift();
    } catch (err: unknown) {
      setError(driftErrorMessage(err, "Failed to delete the workflow"));
    } finally {
      setDeletingEverywhere(false);
    }
  }, [user, projectName, loadDrift]);

  const handleAdoptResolved = useCallback(async (message: string) => {
    setSuccess(message);
    const refreshed = await loadDrift();
    if (refreshed.length === 0) {
      setSuccess("All workflow drift resolved.");
      setTimeout(() => setShowModal(false), 2000);
    }
  }, [loadDrift]);

  const driftCount = drifts.length;
  // Until the live check has succeeded once, drive the banner from the drift
  // the last check persisted. Otherwise the banner is absent on first paint
  // and pops in when the check resolves, shifting the page layout.
  const bannerCount = liveLoaded ? driftCount : (seededDriftNames?.length ?? 0);
  // The seed carries names only, so the modal's rows/resolve actions aren't
  // usable yet. An error still enables it — that's how the user reaches the
  // failure message inside the modal.
  const canReviewDrift = liveLoaded || error !== null;
  const summaryText = useMemo(() => {
    if (bannerCount === 0) return "";
    if (bannerCount === 1) return "1 workflow changed in GitHub";
    return `${bannerCount} workflows changed in GitHub`;
  }, [bannerCount]);

  return (
    <>
      {bannerCount === 0 && (
        // Persistent, muted status row so a clean or never-checked project
        // always has a way to trigger a live check — the "Review Drift"
        // button below only exists once drift is already known, so without
        // this there was no manual-check path at all until something first
        // went wrong. handleCheckNow runs directly; there's nothing to
        // review yet, so opening the modal first would add a step for
        // nothing.
        <output
          className="mx-4 mb-2 px-4 py-2 rounded-lg flex items-center gap-3 bg-slate-100 border border-slate-300 text-slate-800 dark:bg-slate-800/60 dark:border-slate-600 dark:text-slate-200"
          data-testid="drift-status-row"
        >
          <span aria-hidden="true">{uncheckedCount > 0 || !lastChecked ? "❔" : "✅"}</span>
          <span className="font-medium flex-1">
            {getDriftStatusRowMessage(uncheckedCount, lastChecked)}
          </span>
          {uncheckedCount === 0 && staleReason && (
            <span className="text-xs text-slate-500 dark:text-slate-400">{staleReason}</span>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={handleCheckNow}
            disabled={checking}
            data-testid="drift-inline-check-now-button"
          >
            {checking ? "Checking…" : "Check Now"}
          </Button>
        </output>
      )}

      {bannerCount > 0 && (
        <div
          className="mx-4 mb-2 px-4 py-2 rounded-lg flex items-center gap-3 bg-amber-50 border border-amber-200 text-amber-900 dark:bg-amber-900/20 dark:border-amber-800 dark:text-amber-200"
          role="alert"
          aria-live="polite"
          data-testid="drift-banner"
        >
          <span aria-hidden="true">⚠️</span>
          <span className="font-medium flex-1">{summaryText}</span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowModal(true)}
            disabled={!canReviewDrift}
            data-testid="review-drift-button"
          >
            {canReviewDrift ? "Review Drift" : "Checking…"}
          </Button>
        </div>
      )}

      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent
          className="max-w-5xl max-h-[85vh] overflow-y-auto"
          data-testid="drift-modal"
        >
          <DialogHeader>
            <DialogTitle className="text-amber-700 dark:text-amber-400">
              ⚠️ Workflow Drift Detected
            </DialogTitle>
            <DialogDescription>
              The following workflows were changed directly in GitHub. Review the diff and
              choose how to resolve each drift safely.
            </DialogDescription>
            <div className="flex items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
              <span data-testid="drift-last-checked">
                {lastChecked
                  ? `Last checked ${new Date(lastChecked).toLocaleString()}`
                  : "Never checked"}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={handleCheckNow}
                disabled={checking}
                data-testid="drift-check-now-button"
              >
                {checking ? "Checking…" : "Check Now"}
              </Button>
            </div>
            {staleReason && (
              // Without this the timestamp simply stops advancing and the
              // feature reads as broken rather than blocked on a token.
              <p
                className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-900/20 dark:text-amber-200"
                data-testid="drift-stale-reason"
              >
                {staleReason}
              </p>
            )}
            <a
              className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400 self-start"
              href={getDocsUrl("driftDetection")}
              rel="noreferrer"
              target="_blank"
            >
              Learn about drift detection →
            </a>
          </DialogHeader>

          {success && (
            <div className="px-3 py-2 text-sm rounded bg-green-50 text-green-800 border border-green-200 dark:bg-green-900/20 dark:text-green-200 dark:border-green-800">
              ✓ {success}
            </div>
          )}

          {error && (
            <div className="px-3 py-2 text-sm rounded bg-red-50 text-red-800 border border-red-200 dark:bg-red-900/20 dark:text-red-200 dark:border-red-800">
              {error}
            </div>
          )}

          {/* Bulk-fix selection bar */}
          {driftCount > 0 && (
            <div className="flex flex-wrap items-center gap-3 px-1" data-testid="drift-selection-bar">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  data-testid="select-all-drifts"
                  checked={selectedKeys.size > 0 && selectedKeys.size === drifts.length}
                  ref={(el) => {
                    if (el) el.indeterminate = selectedKeys.size > 0 && selectedKeys.size < drifts.length;
                  }}
                  onChange={(e) => (e.target.checked ? selectAll() : deselectAll())}
                />
                <span className="text-slate-600 dark:text-slate-400">
                  {selectedKeys.size} of {drifts.length} selected
                </span>
              </label>
              <Button variant="outline" size="sm" onClick={selectAll}>Select All</Button>
              <Button variant="outline" size="sm" onClick={deselectAll}>Deselect All</Button>

              {selectedKeys.size > 0 && (
                <div className="flex flex-wrap items-center gap-2 ml-auto" data-testid="bulk-action-toolbar">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={bulkResolving !== null}
                    onClick={() => handleBulkResolve("use_github")}
                  >
                    {bulkResolving === "use_github"
                      ? "Adopting…"
                      : `Adopt GitHub Version (${selectedKeys.size})`}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={bulkResolving !== null}
                    onClick={() => handleBulkResolve("restore_actionsmanager", "pr")}
                  >
                    {bulkResolving === "pr"
                      ? "Creating PRs…"
                      : `Create Fix PR (${selectedKeys.size})`}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={bulkResolving !== null}
                    onClick={() => setConfirmBulkDirect(true)}
                  >
                    {bulkResolving === "direct"
                      ? "Restoring…"
                      : `Restore Directly (${selectedKeys.size})`}
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* Drift table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left border-b border-slate-200 dark:border-slate-700">
                  <th className="py-2 pr-2" />
                  <th className="py-2 pr-4">Workflow</th>
                  <th className="py-2 pr-4">Repo</th>
                  <th className="py-2 pr-4">Branch</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Last Checked</th>
                  <th className="py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {drifts.map((d) => {
                  const k = driftKey(d);
                  const isOpen = openDiffKey === k;
                  const diffButtonLabel = isOpen ? "Hide Diff" : "View Diff";
                  const busy = resolving === k;
                  const group = driftGroups.get(groupKeyFor(d)) ?? [d];
                  return (
                    <React.Fragment key={k}>
                      <tr className="border-b border-slate-100 dark:border-slate-800">
                        <td className="py-2 pr-2">
                          <input
                            type="checkbox"
                            data-testid={`select-drift-${k}`}
                            checked={selectedKeys.has(k)}
                            onChange={() => toggleSelected(k)}
                          />
                        </td>
                        <td className="py-2 pr-4 font-medium">
                          <div className="flex items-center gap-2">
                            <span>{d.workflow_filename}</span>
                            {group.length > 1 && (
                              <button
                                type="button"
                                className="text-xs text-blue-600 hover:underline dark:text-blue-400"
                                data-testid={`select-group-${k}`}
                                onClick={() => selectGroup(d)}
                              >
                                {group.length} identical — select all
                              </button>
                            )}
                            {d.is_shared_workflow && (
                              <span
                                className="px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                                data-testid="shared-workflow-badge"
                              >
                                Shared Workflow
                              </span>
                            )}
                            {d.has_repo_override && (
                              <span
                                className="px-2 py-0.5 text-xs rounded-full bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200"
                                data-testid="repo-override-badge"
                                title="This repository uses a workflow override and is no longer following the shared project workflow for this file."
                              >
                                Repo Override
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-2 pr-4">{d.repo}</td>
                        <td className="py-2 pr-4">{d.branch}</td>
                        <td className="py-2 pr-4">
                          {d.deleted_in_github ? (
                            <span
                              className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                              data-testid="drift-status-deleted"
                            >
                              Deleted in GitHub
                            </span>
                          ) : (
                            <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200">
                              Drift detected
                            </span>
                          )}
                        </td>
                        <td className="py-2 pr-4 text-xs text-slate-500 dark:text-slate-400">
                          {d.last_checked
                            ? new Date(d.last_checked).toLocaleString()
                            : "—"}
                        </td>
                        <td className="py-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleToggleDiff(d, k)}
                            disabled={diffLoadingKey === k}
                          >
                            {diffLoadingKey === k ? "Loading…" : diffButtonLabel}
                          </Button>
                        </td>
                      </tr>
                      {isOpen && (
                        <tr>
                          <td colSpan={7} className="py-2">
                            <div className="space-y-2">
                              <p className="text-sm text-slate-700 dark:text-slate-300">
                                Repository: <strong>{d.repo}</strong>
                                {" · "}Target branch: <strong>{d.branch}</strong>
                              </p>
                              {d.message && (
                                <p className="text-xs text-slate-500 dark:text-slate-400">
                                  {d.message}
                                </p>
                              )}
                              {d.deleted_in_github ? (
                                <DeletedInGithubPanel
                                  detail={d}
                                  busyAction={busy ? resolvingMode : null}
                                  onRestorePR={() =>
                                    handleResolve(d, "restore_actionsmanager", "pr")
                                  }
                                  onRestoreDirect={() => setConfirmDirect(d)}
                                  onDeleteEverywhere={() => setConfirmDeleteEverywhere(d)}
                                />
                              ) : (
                                <SideBySideDiff
                                  left={d.actionsmanager_yaml ?? ""}
                                  right={liveDiffs[k]?.github_yaml ?? d.github_yaml ?? ""}
                                  repo={d.repo}
                                  branch={d.branch}
                                  onAdoptGithub={() => setAdoptDetail(d)}
                                  onRestorePR={() =>
                                    handleResolve(d, "restore_actionsmanager", "pr")
                                  }
                                  onRestoreDirect={() => setConfirmDirect(d)}
                                  busyAction={busy ? resolvingMode : null}
                                />
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowModal(false)}>
              Cancel
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AdoptGithubVersionModal
        open={adoptDetail !== null}
        onClose={() => setAdoptDetail(null)}
        detail={adoptDetail}
        user={user}
        onResolved={handleAdoptResolved}
      />

      <ConfirmDialog
        open={confirmDirect !== null}
        title="Overwrite GitHub directly?"
        description={
          confirmDirect
            ? `This immediately overwrites ${confirmDirect.workflow_filename} on branch `
              + `${confirmDirect.branch} in ${confirmDirect.repo} with the `
              + `ActionsManager-managed version. The current GitHub version is replaced `
              + `now, with no pull request to review. This cannot be undone from here.`
            : ""
        }
        confirmLabel="Overwrite directly"
        destructive
        onCancel={() => setConfirmDirect(null)}
        onConfirm={() => {
          const d = confirmDirect;
          setConfirmDirect(null);
          if (d) handleResolve(d, "restore_actionsmanager", "direct");
        }}
      />

      <ConfirmDialog
        open={confirmDeleteEverywhere !== null}
        title="Delete this workflow everywhere?"
        description={
          confirmDeleteEverywhere
            ? `'${confirmDeleteEverywhere.workflow_name}' will be deleted from `
              + `${Array.from(new Set([confirmDeleteEverywhere.repo, ...(confirmDeleteEverywhere.affected_repos ?? [])])).join(", ")} `
              + `and removed from ActionsManager, including its version history. `
              + `This cannot be undone.`
            : ""
        }
        confirmLabel={deletingEverywhere ? "Deleting…" : "Delete everywhere"}
        destructive
        onCancel={() => setConfirmDeleteEverywhere(null)}
        onConfirm={() => {
          if (confirmDeleteEverywhere) handleDeleteEverywhere(confirmDeleteEverywhere);
        }}
      />

      <ConfirmDialog
        open={confirmBulkDirect}
        title="Overwrite GitHub directly?"
        description={
          `This immediately overwrites ${selectedKeys.size} workflow(s) with the `
          + `ActionsManager-managed version. The current GitHub versions are replaced `
          + `now, with no pull request to review. This cannot be undone from here.`
        }
        confirmLabel="Overwrite directly"
        destructive
        onCancel={() => setConfirmBulkDirect(false)}
        onConfirm={() => {
          setConfirmBulkDirect(false);
          handleBulkResolve("restore_actionsmanager", "direct");
        }}
      />
    </>
  );
};

export default DriftDetection;
