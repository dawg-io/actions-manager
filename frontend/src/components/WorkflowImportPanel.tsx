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
  PreviewResponse,
} from '../api/workflowImport';

const ALREADY_MANAGED_EMPTY_STATE = 'All discovered workflows are already managed by this project.';

interface WorkflowImportPanelProps {
  projectId: number;
  projectName: string;
  githubUser: string;
  selectedRepos?: string[];
  onImportComplete?: (prState: string | null) => void;
  onClose: () => void;
}

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
  onImportComplete,
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // Import selected workflows
  const handleImport = useCallback(
    async (mode: 'save_local_only' | 'save_and_create_pr_campaign') => {
      const selected = selectedWorkflows.filter((wf) => wf.selected);
      if (selected.length === 0) return;

      setIsImporting(true);
      setImportResult(null);
      setImportError(null);

      try {
        const result = await importWorkflows(
          projectId,
          githubUser,
          projectName,
          selected.map((wf) => ({
            source_repo: wf.repo_name,
            source_branch: wf.branch,
            workflow_path: wf.path,
            content_sha: wf.blob_sha,
          })),
          mode,
          mode === 'save_and_create_pr_campaign' ? (selectedRepos || undefined) : undefined
        );

        const prResults = result.pr_results;
        const prCreationFailed =
          mode === 'save_and_create_pr_campaign' &&
          (
            !prResults ||
            typeof prResults.error === 'string' ||
            prResults.prs_created === 0
          );

        if (prCreationFailed) {
          setImportError('Workflows were saved locally, but PR Campaign creation failed. No PRs were created.');
        } else {
          setImportResult(result.message);
        }

        if (onImportComplete) {
          onImportComplete(result.pr_state);
        }
      } catch (err: any) {
        setImportError(err.message || 'Import failed');
      } finally {
        setIsImporting(false);
      }
    },
    [selectedWorkflows, projectId, githubUser, projectName, selectedRepos, onImportComplete]
  );

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget && !isImporting) {
      onClose();
    }
  };

  const selectedCount = selectedWorkflows.filter((wf) => wf.selected).length;
  const showAlreadyManagedEmptyState =
    discovery?.workflows_found === 0 &&
    discovery.results.some((repoResult) => repoResult.warning === ALREADY_MANAGED_EMPTY_STATE);

  return (
    <div
      className="modal-overlay"
      onClick={handleOverlayClick}
      data-testid="workflow-import-modal"
    >
      <div className="modal-content workflow-import-modal">
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
          {selectedCount > 0 && !importResult && (
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
