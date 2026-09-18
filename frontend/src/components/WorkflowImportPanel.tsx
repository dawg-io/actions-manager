/**
 * WorkflowImportPanel - Guided modal import flow for existing GitHub Actions workflows.
 *
 * Opens as a modal/drawer when the user clicks "Import Existing Workflows".
 * Auto-scans repositories on open and presents a guided selection experience.
 *
 * Flow:
 * 1. Modal opens → auto-scans project repositories
 * 2. Displays discovered workflow files with selection checkboxes
 * 3. User can preview YAML content
 * 4. User selects workflows and chooses: Save Locally Only or Save & Create PR Campaign
 *
 * Display-only derived labels (not persisted):
 * - "Local Draft" - project.pr_state=draft, no real hash, no open PR
 * - "Imported Locally" - import metadata exists, no real hash, no open PR
 * - "Pending Sync" - local workflow not synced to one or more repos
 * - "Under Review" - open PR exists
 * - "Synced" - synced_with_github and content matches
 * - "Drift Detected" - drift detection reports has_drift=true
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  discoverWorkflows,
  previewWorkflow,
  importWorkflows,
  DiscoveryResponse,
  DiscoveredWorkflow,
  ImportWorkflowItem,
  PreviewResponse,
} from '../api/workflowImport';
import { fetchProjects } from '../api/projects';

const ALREADY_MANAGED_EMPTY_STATE = 'All discovered workflows are already managed by this project.';

type ImportMode = 'save_local_only' | 'save_and_create_pr_campaign';

/** A Reusable Workflow Project an import can be filed into. */
interface RwxDestination {
  id: number;
  name: string;
}

/** What one import call into the open project produced. */
interface ImportOutcome {
  message: string;
  prState: string | null;
  campaignFailed: boolean;
}

interface WorkflowImportPanelProps {
  projectId: number;
  projectName: string;
  githubUser: string;
  selectedRepos?: string[];
  /** Reusable workflows are only out of place in a caller project. */
  projectType?: 'standard' | 'rwx';
  onImportComplete?: (prState: string | null) => void;
  /** Opens the create-project flow preset to a Reusable Workflow Project. */
  onCreateReusableProject?: () => void;
  onClose: () => void;
}

const toImportItems = (list: SelectedWorkflow[]): ImportWorkflowItem[] =>
  list.map((wf) => ({
    source_repo: wf.repo_name,
    source_branch: wf.branch,
    workflow_path: wf.path,
    content_sha: wf.blob_sha,
  }));

interface SelectedWorkflow extends DiscoveredWorkflow {
  selected: boolean;
  crossRepoCount?: number;
  differsBetweenRepos?: boolean;
}

export const WorkflowImportPanel: React.FC<WorkflowImportPanelProps> = ({
  projectId,
  projectName,
  githubUser,
  selectedRepos,
  projectType = 'standard',
  onImportComplete,
  onCreateReusableProject,
  onClose,
}) => {
  const [discovery, setDiscovery] = useState<DiscoveryResponse | null>(null);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);

  const [selectedWorkflows, setSelectedWorkflows] = useState<SelectedWorkflow[]>([]);
  const [previewData, setPreviewData] = useState<PreviewResponse | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);

  const [isImporting, setIsImporting] = useState(false);
  const [importResult, setImportResult] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  // Reusable-workflow routing: which Reusable Workflow Projects exist, which one
  // is picked, and the import that is paused waiting on that choice.
  const [rwxProjects, setRwxProjects] = useState<RwxDestination[]>([]);
  const [rwxLookup, setRwxLookup] = useState<'idle' | 'loading' | 'loaded'>('idle');
  const [destinationId, setDestinationId] = useState<number | null>(null);
  const [decision, setDecision] = useState<{ mode: ImportMode } | null>(null);
  const decisionRef = React.useRef<HTMLDivElement | null>(null);

  // Discover workflows
  const handleDiscover = useCallback(async () => {
    setIsDiscovering(true);
    setDiscoveryError(null);
    setDiscovery(null);
    setSelectedWorkflows([]);
    setPreviewData(null);
    setImportResult(null);
    setImportError(null);

    try {
      const result = await discoverWorkflows(projectId, githubUser, projectName);
      setDiscovery(result);

      // Build cross-repo lookup
      const crossRepoLookup: Record<string, { count: number; differs: boolean }> = {};
      for (const match of result.cross_repo_matches) {
        crossRepoLookup[match.file_name] = {
          count: match.repos.length,
          differs: !match.identical_across_repos,
        };
      }

      // Flatten all discovered workflows into selectable list
      const allWorkflows: SelectedWorkflow[] = [];
      for (const repoResult of result.results) {
        for (const wf of repoResult.workflows) {
          const cross = crossRepoLookup[wf.file_name];
          allWorkflows.push({
            ...wf,
            selected: false,
            crossRepoCount: cross?.count,
            differsBetweenRepos: cross?.differs,
          });
        }
      }
      setSelectedWorkflows(allWorkflows);
    } catch (err: any) {
      setDiscoveryError(err.message || 'Failed to discover workflows');
    } finally {
      setIsDiscovering(false);
    }
  }, [projectId, githubUser, projectName]);

  // Auto-scan on modal open
  useEffect(() => {
    handleDiscover();
  }, []);

  // Preview a workflow
  const handlePreview = useCallback(
    async (wf: DiscoveredWorkflow) => {
      setIsPreviewing(true);
      setPreviewData(null);
      setImportError(null);
      try {
        const result = await previewWorkflow(
          projectId,
          githubUser,
          projectName,
          wf.repo_name,
          wf.branch,
          wf.path
        );
        setPreviewData(result);
      } catch (err: any) {
        setPreviewData(null);
        setImportError(err.message || 'Failed to preview workflow');
      } finally {
        setIsPreviewing(false);
      }
    },
    [projectId, githubUser, projectName]
  );

  // Toggle workflow selection
  const toggleWorkflow = useCallback((index: number) => {
    setSelectedWorkflows((prev) =>
      prev.map((wf, i) => (i === index ? { ...wf, selected: !wf.selected } : wf))
    );
  }, []);

  // Select/deselect all
  const toggleAll = useCallback((selectAll: boolean) => {
    setSelectedWorkflows((prev) => prev.map((wf) => ({ ...wf, selected: selectAll })));
  }, []);

  const selectedReusable = selectedWorkflows.filter((wf) => wf.selected && wf.is_reusable);
  const canRouteReusable = projectType !== 'rwx';

  // Only a caller project with a reusable workflow in the scan needs somewhere
  // to send it, so the project list is fetched on that condition alone.
  const needsRwxProjects =
    canRouteReusable && selectedWorkflows.some((wf) => wf.is_reusable);

  useEffect(() => {
    if (!needsRwxProjects) return;
    let cancelled = false;
    setRwxLookup('loading');
    fetchProjects(githubUser)
      .then((projects) => {
        if (cancelled) return;
        const destinations = projects
          .filter((project) => project.project_type === 'rwx')
          .map((project) => ({
            id: project.project_id,
            name: project.project_name || project.name || '',
          }))
          .filter((project): project is RwxDestination =>
            typeof project.id === 'number' && !!project.name
          );
        setRwxProjects(destinations);
        setDestinationId((current) => current ?? destinations[0]?.id ?? null);
      })
      .catch(() => {
        // A failed lookup just means no destinations to offer - the user can
        // still import into this project, so it must not block the panel.
        if (!cancelled) setRwxProjects([]);
      })
      .finally(() => {
        if (!cancelled) setRwxLookup('loaded');
      });
    return () => { cancelled = true; };
  }, [needsRwxProjects, githubUser]);

  // The decision replaces the footer's import buttons, and on a long scan it
  // renders below the fold - without this the click looks like it did nothing.
  useEffect(() => {
    if (decision) decisionRef.current?.scrollIntoView({ block: 'nearest' });
  }, [decision]);

  /** Import into the project the panel is open on. */
  const importIntoThisProject = useCallback(
    async (mode: ImportMode, items: ImportWorkflowItem[]): Promise<ImportOutcome> => {
      const result = await importWorkflows(
        projectId,
        githubUser,
        projectName,
        items,
        mode,
        mode === 'save_and_create_pr_campaign' ? (selectedRepos || undefined) : undefined
      );
      const prResults = result.pr_results;
      return {
        message: result.message,
        prState: result.pr_state,
        campaignFailed:
          mode === 'save_and_create_pr_campaign' &&
          (
            !prResults ||
            typeof prResults.error === 'string' ||
            prResults.prs_created === 0
          ),
      };
    },
    [projectId, githubUser, projectName, selectedRepos]
  );

  /**
   * File reusable workflows into a Reusable Workflow Project.
   *
   * Always a local save: the workflow is delivered by the project that now owns
   * it, not by this campaign, so a campaign-mode import says so rather than
   * leaving the user to notice the missing PRs.
   */
  const importIntoReusableProject = useCallback(
    async (destinationProjectId: number, items: ImportWorkflowItem[], mode: ImportMode): Promise<string[]> => {
      const result = await importWorkflows(
        projectId,
        githubUser,
        projectName,
        items,
        'save_local_only',
        undefined,
        destinationProjectId
      );
      const notes = [result.message];
      if (mode === 'save_and_create_pr_campaign') {
        notes.push('No PR Campaign was created for them - they are delivered by the project that now owns them.');
      }
      return notes;
    },
    [projectId, githubUser, projectName]
  );

  /**
   * Run the import.
   *
   * With a destination set, reusable workflows are filed into that Reusable
   * Workflow Project and everything else still lands in the open project, so a
   * mixed selection does not force the user to import twice.
   */
  const runImport = useCallback(
    async (mode: ImportMode, destinationProjectId: number | null) => {
      const selected = selectedWorkflows.filter((wf) => wf.selected);
      if (selected.length === 0) return;

      const here = destinationProjectId ? selected.filter((wf) => !wf.is_reusable) : selected;
      const moved = destinationProjectId ? selected.filter((wf) => wf.is_reusable) : [];

      setIsImporting(true);
      setImportResult(null);
      setImportError(null);

      // Declared out here so a failure in the second call can still report what
      // the first one wrote, and still tell the parent to refetch.
      const messages: string[] = [];
      let prState: string | null = null;
      let campaignFailed = false;
      let wroteSomething = false;

      try {
        if (here.length > 0) {
          const outcome = await importIntoThisProject(mode, toImportItems(here));
          wroteSomething = true;
          prState = outcome.prState;
          campaignFailed = outcome.campaignFailed;
          messages.push(outcome.message);
        }

        if (moved.length > 0 && destinationProjectId) {
          const notes = await importIntoReusableProject(destinationProjectId, toImportItems(moved), mode);
          wroteSomething = true;
          messages.push(...notes);
        }

        if (campaignFailed) {
          setImportError('Workflows were saved locally, but PR Campaign creation failed. No PRs were created.');
        } else {
          setImportResult(messages.join(' '));
        }
      } catch (err: any) {
        const failure = err.message || 'Import failed';
        setImportError(
          messages.length > 0 ? `${messages.join(' ')} The rest failed: ${failure}` : failure
        );
      } finally {
        setIsImporting(false);
        // Anything already written has to reach the parent even when a later
        // call failed, or the project view stays stale until a manual refresh.
        if (wroteSomething && onImportComplete) {
          onImportComplete(prState);
        }
      }
    },
    [selectedWorkflows, importIntoThisProject, importIntoReusableProject, onImportComplete]
  );

  // Import selected workflows, pausing first if any of them are reusable.
  const handleImport = useCallback(
    (mode: ImportMode) => {
      const selected = selectedWorkflows.filter((wf) => wf.selected);
      if (selected.length === 0) return;

      if (canRouteReusable && selected.some((wf) => wf.is_reusable)) {
        setDecision({ mode });
        return;
      }
      void runImport(mode, null);
    },
    [selectedWorkflows, canRouteReusable, runImport]
  );

  /**
   * Where the reusable workflows should go.
   *
   * The "you have none" branch must not show while the lookup is still in
   * flight, or a slow response pushes the user into creating a second Reusable
   * Workflow Project and loses the scan on navigation.
   */
  const renderDestinationChoice = () => {
    if (rwxLookup !== 'loaded') {
      return (
        <div className="import-reusable-choice" data-testid="rwx-lookup-loading">
          <p>Looking for your Reusable Workflow Projects…</p>
        </div>
      );
    }

    if (rwxProjects.length === 0) {
      return (
        <div className="import-reusable-choice" data-testid="no-rwx-project">
          <p>
            You do not have a Reusable Workflow Project yet. Create one and these
            workflows can be imported into it instead.
          </p>
          {onCreateReusableProject && (
            <button
              type="button"
              className="btn-import-reusable"
              onClick={onCreateReusableProject}
              disabled={isImporting}
              data-testid="create-rwx-project-button"
            >
              Create a Reusable Workflow Project
            </button>
          )}
        </div>
      );
    }

    const selectedName = rwxProjects.find((project) => project.id === destinationId)?.name ?? '';
    return (
      <div className="import-reusable-choice">
        <label htmlFor="reusable-destination">Reusable Workflow Project</label>
        <select
          id="reusable-destination"
          value={destinationId ?? ''}
          onChange={(e) => setDestinationId(Number(e.target.value))}
          data-testid="reusable-destination"
        >
          {rwxProjects.map((project) => (
            <option key={project.id} value={project.id}>{project.name}</option>
          ))}
        </select>
        <button
          type="button"
          className="btn-import-reusable"
          onClick={() => resolveDecision(destinationId)}
          disabled={isImporting || destinationId === null}
          data-testid="import-into-rwx-button"
        >
          Import into {selectedName}
        </button>
      </div>
    );
  };

  const resolveDecision = (destinationProjectId: number | null) => {
    if (!decision) return;
    const { mode } = decision;
    setDecision(null);
    void runImport(mode, destinationProjectId);
  };

  // See CreatePRModal: dismissal lives on a real button, not a div onClick.
  // The in-flight guard stays - an import must not be dismissed mid-run.
  const handleOverlayClick = () => { if (!isImporting) { onClose(); } };

  const selectedCount = selectedWorkflows.filter((wf) => wf.selected).length;
  const showAlreadyManagedEmptyState =
    discovery?.workflows_found === 0 &&
    discovery.results.some((repoResult) => repoResult.warning === ALREADY_MANAGED_EMPTY_STATE);

  return (
    <div className="modal-overlay" data-testid="workflow-import-modal">
      <button
        type="button"
        aria-label="Dismiss workflow import"
        onClick={handleOverlayClick}
        className="absolute inset-0 cursor-default border-0 bg-transparent p-0"
      />
      <div className="modal-content workflow-import-modal relative">
        {/* Modal Header */}
        <div className="modal-header">
          <h2>Import Existing Workflows</h2>
          <button
            onClick={onClose}
            disabled={isImporting}
            className="modal-close-button"
            data-testid="import-modal-close"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Modal Body */}
        <div className="modal-body" data-testid="workflow-import-panel">
          <p className="modal-description">
            Discover and import existing GitHub Actions workflows from your project
            repositories. Imported workflows are saved as local drafts until you create
            a PR Campaign or sync them directly.
          </p>

          {/* Scanning indicator */}
          {isDiscovering && (
            <div className="import-scanning" data-testid="import-scanning">
              Scanning repositories for existing workflows...
            </div>
          )}

          {/* Discovery error */}
          {discoveryError && (
            <div className="import-error" data-testid="discovery-error">
              ⚠️ {discoveryError}
              <button onClick={handleDiscover} className="btn-retry ml-3">
                Retry
              </button>
            </div>
          )}

          {/* Discovery results */}
          {discovery && !isDiscovering && (
            <div className="discovery-results" data-testid="discovery-results">
              <div className="discovery-summary">
                <span>
                  Found <strong>{discovery.workflows_found}</strong> workflow(s) across{' '}
                  <strong>{discovery.repositories_scanned}</strong> repository(ies)
                </span>
                <button onClick={handleDiscover} disabled={isDiscovering} className="btn-refresh" data-testid="discover-button">
                  Re-scan
                </button>
              </div>

              {/* Show warnings/errors per repo */}
              {discovery.results.map((repoResult) =>
                repoResult.error ? (
                  <div key={repoResult.repo_name} className="repo-error">
                    ⚠️ {repoResult.repo_name}: {repoResult.error}
                  </div>
                ) : repoResult.warning ? (
                  <div key={repoResult.repo_name} className="repo-warning">
                    ℹ️ {repoResult.repo_name}: {repoResult.warning}
                  </div>
                ) : null
              )}

              {/* Workflow selection list */}
              {selectedWorkflows.length > 0 && (
                <>
                  <div className="selection-controls">
                    <label>
                      <input
                        type="checkbox"
                        checked={selectedCount === selectedWorkflows.length && selectedWorkflows.length > 0}
                        onChange={(e) => toggleAll(e.target.checked)}
                      />
                      Select All ({selectedWorkflows.length})
                    </label>
                  </div>

                  <div className="workflow-list" data-testid="workflow-list">
                    {selectedWorkflows.map((wf, idx) => (
                      <div key={`${wf.repo_name}-${wf.path}`} className="workflow-item">
                        <label className="workflow-checkbox">
                          <input
                            type="checkbox"
                            checked={wf.selected}
                            onChange={() => toggleWorkflow(idx)}
                          />
                          <div className="workflow-info">
                            <span className="workflow-filename">{wf.file_name}</span>
                            {wf.is_reusable && (
                              <span
                                className="workflow-reusable-dot"
                                data-testid={`reusable-dot-${wf.repo_name}-${wf.path}`}
                                title="Reusable workflow (triggered by workflow_call)"
                              >
                                <span className="sr-only">Reusable workflow</span>
                              </span>
                            )}
                            <span className="workflow-repo">{wf.repo_name}</span>
                            <span className="workflow-branch">{wf.branch}</span>
                            {wf.blob_sha && (
                              <span className="workflow-sha">{wf.blob_sha.substring(0, 7)}</span>
                            )}
                            {wf.crossRepoCount && wf.crossRepoCount > 1 && (
                              <span className={`workflow-cross-repo ${wf.differsBetweenRepos ? 'differs' : 'identical'}`}>
                                {wf.crossRepoCount} repos{wf.differsBetweenRepos ? ' (differs)' : ' (identical)'}
                              </span>
                            )}
                          </div>
                        </label>
                        <button
                          className="btn-preview"
                          onClick={() => handlePreview(wf)}
                          disabled={isPreviewing}
                          data-testid={`preview-${wf.repo_name}-${wf.path}`}
                        >
                          Preview
                        </button>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {discovery.workflows_found === 0 && (
                <div className="empty-state" data-testid="empty-state">
                  {showAlreadyManagedEmptyState
                    ? ALREADY_MANAGED_EMPTY_STATE
                    : 'No workflow files found in the selected repositories.'}
                </div>
              )}
            </div>
          )}

          {/* Preview panel */}
          {previewData && (
            <div className="preview-panel" data-testid="preview-panel">
              <div className="preview-header">
                <h4>Preview: {previewData.file_name}</h4>
                <button onClick={() => setPreviewData(null)}>Close Preview</button>
              </div>
              <div className="preview-meta">
                <span>Repository: {previewData.repo_name}</span>
                <span>Branch: {previewData.branch}</span>
                {previewData.blob_sha && <span>SHA: {previewData.blob_sha.substring(0, 7)}</span>}
              </div>
              <pre className="preview-content">{previewData.content}</pre>
            </div>
          )}

          {/* Reusable workflows need a home decision before anything is written */}
          {decision && (
            <div className="import-reusable-decision" data-testid="reusable-decision" ref={decisionRef}>
              <h4>
                {selectedReusable.length === 1
                  ? 'One selected workflow is reusable'
                  : `${selectedReusable.length} selected workflows are reusable`}
              </h4>
              <p className="import-reusable-names">
                {selectedReusable.map((wf) => wf.file_name).join(', ')}
              </p>
              <p>
                {selectedReusable.length === 1 ? 'It is triggered by ' : 'They are triggered by '}
                <code>workflow_call</code>, so a caller workflow has to reference{' '}
                {selectedReusable.length === 1 ? 'it' : 'them'} to run. A Reusable Workflow
                Project keeps one copy that every caller project links to, instead of a copy
                per project.
              </p>

              {decision.mode === 'save_and_create_pr_campaign' && (
                <p data-testid="reusable-campaign-note">
                  Filing them into a Reusable Workflow Project saves them there locally —
                  no PR Campaign is created for them, because that project delivers them.
                </p>
              )}

              {renderDestinationChoice()}

              <div className="import-reusable-actions">
                <button
                  type="button"
                  className="btn-save-local"
                  onClick={() => resolveDecision(null)}
                  disabled={isImporting}
                  data-testid="import-here-anyway-button"
                >
                  Import into {projectName} anyway
                </button>
                <button
                  type="button"
                  className="btn-close-modal"
                  onClick={() => setDecision(null)}
                  disabled={isImporting}
                  data-testid="reusable-decision-cancel"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Import result */}
          {importResult && (
            <div className="import-success" data-testid="import-success">
              ✅ {importResult}
            </div>
          )}

          {importError && (
            <div className="import-error" data-testid="import-error">
              ❌ {importError}
            </div>
          )}
        </div>

        {/* Modal Footer with import actions */}
        <div className="modal-footer">
          {selectedCount > 0 && !importResult && !decision && (
            <div className="import-actions" data-testid="import-actions">
              <span className="import-info">
                {selectedCount} workflow(s) selected
              </span>
              <button
                className="btn-save-local"
                onClick={() => handleImport('save_local_only')}
                disabled={isImporting}
                data-testid="save-local-button"
              >
                {isImporting ? 'Importing...' : 'Save Locally Only'}
              </button>
              <button
                className="btn-save-and-pr"
                onClick={() => handleImport('save_and_create_pr_campaign')}
                disabled={isImporting}
                data-testid="save-and-pr-button"
              >
                {isImporting ? 'Importing...' : 'Save & Create PR Campaign'}
              </button>
            </div>
          )}
          {(importResult || (!selectedCount && !isDiscovering && discovery)) && (
            <button
              onClick={onClose}
              className="btn-close-modal"
              data-testid="import-done-button"
            >
              {importResult ? 'Done' : 'Close'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default WorkflowImportPanel;
