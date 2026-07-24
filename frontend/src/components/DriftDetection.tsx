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
import {
  getProjectDrift,
  resolveWorkflowDrift,
  adoptGithubVersion,
  type WorkflowDriftDetail,
  type DriftDeliveryMode,
  type AdoptResolutionMode,
} from "../api/drift";
import ConfirmDialog from "./ConfirmDialog";
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
}

/**
 * Render two `<pre>` blocks side-by-side highlighting changed lines.
 * Lightweight (no extra deps) inline diff suitable for short workflow files.
 */
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
  const leftLines = (left || "").split("\n");
  const rightLines = (right || "").split("\n");
  const max = Math.max(leftLines.length, rightLines.length);
  const rows: { l: string; r: string; changed: boolean }[] = [];
  for (let i = 0; i < max; i++) {
    const l = leftLines[i] ?? "";
    const r = rightLines[i] ?? "";
    rows.push({ l, r, changed: l !== r });
  }
  return (
    <div
      className="border border-slate-200 dark:border-slate-700 rounded-md overflow-hidden"
      style={{ display: "grid", gridTemplateColumns: "1fr 1fr", fontFamily: "monospace", fontSize: "0.8rem" }}
    >
      {/* Column Headers */}
      <div className="bg-slate-50 dark:bg-slate-800 px-2 py-1 text-sm font-semibold border-b border-r border-slate-200 dark:border-slate-700">
        ActionsManager managed version
      </div>
      <div className="bg-slate-50 dark:bg-slate-800 px-2 py-1 text-sm font-semibold border-b border-slate-200 dark:border-slate-700">
        Current GitHub version
      </div>

      {/* Diff Content */}
      <div
        className="m-0 px-2 py-1 overflow-x-auto whitespace-pre border-r border-slate-200 dark:border-slate-700"
        style={{ background: "transparent" }}
      >
        {rows.map((row, i) => (
          <div
            key={`l-${i}`}
            style={{
              backgroundColor: row.changed && row.l ? "rgba(239,68,68,0.10)" : undefined,
            }}
          >
            {row.l || " "}
          </div>
        ))}
      </div>
      <div
        className="m-0 px-2 py-1 overflow-x-auto whitespace-pre"
        style={{ background: "transparent" }}
      >
        {rows.map((row, i) => (
          <div
            key={`r-${i}`}
            style={{
              backgroundColor: row.changed && row.r ? "rgba(16,185,129,0.12)" : undefined,
            }}
          >
            {row.r || " "}
          </div>
        ))}
      </div>

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
}) => {
  const [drifts, setDrifts] = useState<WorkflowDriftDetail[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [openDiffKey, setOpenDiffKey] = useState<string | null>(null);
  const [resolving, setResolving] = useState<string | null>(null);
  const [resolvingMode, setResolvingMode] = useState<DriftDeliveryMode | null>(null);
  const [adoptDetail, setAdoptDetail] = useState<WorkflowDriftDetail | null>(null);
  // Direct restore overwrites GitHub with no PR review, so it is gated behind
  // an explicit confirmation naming the repo + target branch.
  const [confirmDirect, setConfirmDirect] = useState<WorkflowDriftDetail | null>(null);

  const driftKey = useCallback(
    (d: WorkflowDriftDetail) => `${d.workflow_id}::${d.repo}::${d.branch}`,
    [],
  );

  // Mirrors `drifts` so a failed background check can fall back to the last
  // known state without adding `drifts` as a loadDrift dependency (which would
  // re-trigger the load-on-mount effect on every successful load).
  const driftsRef = useRef<WorkflowDriftDetail[]>([]);
  // Discards out-of-order responses, e.g. the user navigates to a different
  // project before an in-flight request resolves. Same idiom as
  // ProjectMgmt.tsx's loadRequestCounterRef.
  const requestIdRef = useRef(0);

  const loadDrift = useCallback(async (): Promise<WorkflowDriftDetail[]> => {
    const requestId = ++requestIdRef.current;
    if (!user || !projectId || !projectName || selectedRepos.length === 0) {
      driftsRef.current = [];
      setDrifts([]);
      onDriftLoaded?.([]);
      return [];
    }
    setError(null);
    try {
      const summary = await getProjectDrift(projectId, user);
      if (requestId !== requestIdRef.current) return driftsRef.current;
      driftsRef.current = summary.drifted_workflows;
      setDrifts(summary.drifted_workflows);
      onDriftLoaded?.(summary.drifted_workflows);
      return summary.drifted_workflows;
    } catch (err: unknown) {
      if (requestId !== requestIdRef.current) return driftsRef.current;
      setError(driftErrorMessage(err, "Failed to check drift"));
      // A failed background check must not erase a previously known drift state.
      return driftsRef.current;
    }
  }, [user, projectId, projectName, selectedRepos, onDriftLoaded]);

  useEffect(() => {
    loadDrift();
  }, [loadDrift, refreshSignal]);

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
        });

        // Check the resolution result state
        if (response.state === "synced") {
          // Success - drift resolved
          setSuccess(response.message || "Drift resolved successfully");

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
          await loadDrift();
          if (openDiffKey === key) setOpenDiffKey(null);
        } else {
          // Unknown state or no state - refresh and show message
          setSuccess(response.message);
          await loadDrift();
          if (openDiffKey === key) setOpenDiffKey(null);
        }
      } catch (err: unknown) {
        setError(driftErrorMessage(err, "Resolution failed"));
        // Keep diff open on error
      } finally {
        setResolving(null);
        setResolvingMode(null);
      }
    },
    [driftKey, loadDrift, openDiffKey, user],
  );

  const handleAdoptResolved = useCallback(async (message: string) => {
    setSuccess(message);
    const refreshed = await loadDrift();
    if (refreshed.length === 0) {
      setSuccess("All workflow drift resolved.");
      setTimeout(() => setShowModal(false), 2000);
    }
  }, [loadDrift]);

  const driftCount = drifts.length;
  const summaryText = useMemo(() => {
    if (driftCount === 0) return "";
    if (driftCount === 1) return "1 workflow changed in GitHub";
    return `${driftCount} workflows changed in GitHub`;
  }, [driftCount]);

  if (driftCount === 0 && !showModal) {
    return null;
  }

  return (
    <>
      {driftCount > 0 && (
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
            data-testid="review-drift-button"
          >
            Review Drift
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

          {/* Drift table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left border-b border-slate-200 dark:border-slate-700">
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
                  const busy = resolving === k;
                  return (
                    <React.Fragment key={k}>
                      <tr className="border-b border-slate-100 dark:border-slate-800">
                        <td className="py-2 pr-4 font-medium">
                          <div className="flex items-center gap-2">
                            <span>{d.workflow_filename}</span>
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
                          <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200">
                            Drift detected
                          </span>
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
                            onClick={() => setOpenDiffKey(isOpen ? null : k)}
                          >
                            {isOpen ? "Hide Diff" : "View Diff"}
                          </Button>
                        </td>
                      </tr>
                      {isOpen && (
                        <tr>
                          <td colSpan={6} className="py-2">
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
                              <SideBySideDiff
                                left={d.actionsmanager_yaml ?? ""}
                                right={d.github_yaml ?? ""}
                                repo={d.repo}
                                branch={d.branch}
                                onAdoptGithub={() => setAdoptDetail(d)}
                                onRestorePR={() =>
                                  handleResolve(d, "restore_actionsmanager", "pr")
                                }
                                onRestoreDirect={() => setConfirmDirect(d)}
                                busyAction={busy ? resolvingMode : null}
                              />
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
    </>
  );
};

export default DriftDetection;
