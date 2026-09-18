/* eslint-disable no-restricted-syntax, no-restricted-imports -- Legacy: TODO migrate inline styles and CSS imports to Tailwind CSS classes */
import React, { useState, useEffect, useRef } from 'react';
import apiClient from '../api/apiClient';
import config from '../config';
import { getRulesetSyncStatus } from '../api/rulesets';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import RemovalScopeDialog, { RemovalScope } from './RemovalScopeDialog';
import '../styles/RulesetManager.css';

const BACKEND_URL = config.BACKEND_URL;

// TypeScript interfaces
interface Ruleset {
  ruleset_id: number;
  ruleset_name: string;
  description?: string;
  created_at: string;
  updated_at: string;
  ruleset_json: any;
}

interface RulesetManagerProps {
  user: string;
  projectName: string;
  selectedRepos?: string[];
}

interface ApiResponse {
  data: {
    success: boolean;
    message?: string;
    rulesets?: Ruleset[];
    applied_count?: number;
    error_count?: number;
    removed_from_repos?: string[];
  };
}

interface RulesetSyncStatus {
  success: boolean;
  is_synced: boolean;
  missing_repos: string[];
  repo_statuses: Record<string, any>;
  error?: string;
}

const RulesetManager: React.FC<RulesetManagerProps> = ({ 
  user, 
  projectName, 
  selectedRepos = []
}) => {
  const [rulesets, setRulesets] = useState<Ruleset[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string>('');
  const [successMessage, setSuccessMessage] = useState<string>('');
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [expandedRuleset, setExpandedRuleset] = useState<number | null>(null);
  const [rulesetSyncStatuses, setRulesetSyncStatuses] = useState<Record<number, RulesetSyncStatus>>({});
  const [loadingSyncStatus, setLoadingSyncStatus] = useState<boolean>(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);
  // Latest selection, so an in-flight sync-status answer can be discarded when
  // it no longer describes what the user has selected.
  const selectedReposRef = useRef<string[]>(selectedRepos);
  useEffect(() => { selectedReposRef.current = selectedRepos; }, [selectedRepos]);

  // Load rulesets when component mounts or project changes
  useEffect(() => {
    if (user && projectName) {
      loadRulesets();
    }
  }, [user, projectName]);

  // Load ruleset sync statuses when rulesets or selectedRepos change
  useEffect(() => {
    const loadRulesetSyncStatuses = async (): Promise<void> => {
      if (!user || !selectedRepos || selectedRepos.length === 0 || rulesets.length === 0) {
        setRulesetSyncStatuses({});
        return;
      }

      setLoadingSyncStatus(true);
      try {
        const syncStatuses: Record<number, RulesetSyncStatus> = {};
        
        // Check sync status for each ruleset
        for (const ruleset of rulesets) {
          try {
            const repoNames = selectedRepos.map(repo => 
              typeof repo === 'string' ? repo : (repo as any).full_name || (repo as any).name
            );
            
            const syncStatus = await getRulesetSyncStatus(user, ruleset.ruleset_id, repoNames);
            syncStatuses[ruleset.ruleset_id] = syncStatus;
          } catch (error) {
            console.error(`Error checking sync status for ruleset ${ruleset.ruleset_id}:`, error);
            syncStatuses[ruleset.ruleset_id] = {
              success: false,
              is_synced: false,
              missing_repos: selectedRepos,
              repo_statuses: {},
              error: 'Failed to check sync status'
            };
          }
        }
        
        setRulesetSyncStatuses(syncStatuses);
      } catch (error) {
        console.error('Error loading ruleset sync statuses:', error);
      } finally {
        setLoadingSyncStatus(false);
      }
    };

    if (user && selectedRepos.length > 0 && rulesets.length > 0) {
      loadRulesetSyncStatuses();
    }
  }, [user, selectedRepos, rulesets]);

  const loadRulesets = async (): Promise<void> => {
    if (!user || !projectName) return;

    setIsLoading(true);
    try {
      const response: ApiResponse = await apiClient.get(`${BACKEND_URL}/api/rulesets/${projectName}`, {
        params: { github_user: user }
      });

      if (response.data.success) {
        setRulesets(response.data.rulesets || []);
      } else {
        setUploadError('Failed to load rulesets');
      }
    } catch (error) {
      console.error('Error loading rulesets:', error);
      setUploadError('Error loading rulesets');
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>): void => {
    const file = event.target.files?.[0];
    if (file) {
      if (!file.name.endsWith('.json')) {
        setUploadError('Please select a JSON file');
        return;
      }
      setSelectedFile(file);
      setUploadError('');
    }
  };

  const handleUpload = async (): Promise<void> => {
    if (!selectedFile) {
      setUploadError('Please select a file');
      return;
    }

    if (!user || !projectName) {
      setUploadError('User or project information missing');
      return;
    }

    setIsUploading(true);
    setUploadError('');
    setSuccessMessage('');

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('project_name', projectName);
      formData.append('github_user', user);

      const response: ApiResponse = await apiClient.post(`${BACKEND_URL}/api/rulesets/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      if (response.data.success) {
        setSuccessMessage(response.data.message || 'Ruleset uploaded successfully');
        setSelectedFile(null);
        // Reset file input
        const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
        if (fileInput) {
          fileInput.value = '';
        }
        await loadRulesets();
      } else {
        setUploadError('Failed to upload ruleset');
      }
    } catch (error) {
      console.error('Error uploading ruleset:', error);
      setUploadError(apiErrorMessage(error, 'Error uploading ruleset'));
    } finally {
      setIsUploading(false);
    }
  };

  const handleDeleteRuleset = (rulesetId: number): void => {
    setPendingDeleteId(rulesetId);
  };

  /**
   * True only when every repository we checked reports the ruleset missing. An
   * unchecked ruleset stays deletable from GitHub — the backend treats a
   * repository without it as nothing to do, so guessing "never applied" here
   * would only hide the option that fixes a leftover.
   */
  const hasNoGithubCopy = (rulesetId: number | null): boolean => {
    if (rulesetId === null) return false;
    const syncStatus = rulesetSyncStatuses[rulesetId];
    if (!syncStatus?.success) return false;
    const statuses = Object.values(syncStatus.repo_statuses ?? {});
    // 'permission_denied', 'error' and 'repo_not_found' all come back with
    // success: true. They mean the check did not answer, not that the ruleset
    // is absent, so they must not disable the GitHub options.
    return statuses.length > 0 && statuses.every(repo => repo?.status === 'not_found');
  };

  /**
   * Re-read one ruleset's sync status. Shared by every mutation that changes
   * what GitHub holds, so the panel never reports a pre-action count.
   *
   * The answer is dropped if the repository selection changed while it was in
   * flight: the load effect writes the whole map for the new selection, and a
   * late single-entry write would overwrite that with a verdict for a selection
   * it never checked — reporting "synced" for a repository nobody looked at.
   *
   * A failed read is also not stored. The panel renders an error branch that
   * carries no Sync button, and nothing re-runs the load effect, so one
   * transient failure would strip the only retry short of reloading the page.
   * Keeping the previous count leaves it briefly stale but still actionable,
   * and the next selection change corrects it.
   */
  const refreshSyncStatus = async (rulesetId: number): Promise<boolean> => {
    const askedFor = selectedRepos;
    if (askedFor.length === 0) return false;
    const asked = askedFor.join('\u0000');

    const syncStatus = await getRulesetSyncStatus(user, rulesetId, askedFor);
    if (selectedReposRef.current.join('\u0000') !== asked) return false;
    if (!syncStatus.success) return false;

    setRulesetSyncStatuses(prev => ({ ...prev, [rulesetId]: syncStatus }));
    return true;
  };

  /**
   * A GitHub-only removal keeps the row, so its sync status has to be re-read or
   * the panel goes on claiming the ruleset is still applied. Every other scope
   * drops the row, so the stale status is pruned instead — ids are serial, but
   * leaving it would let a later ruleset read it back.
   */
  const refreshAfterRemoval = async (rulesetId: number, scope: RemovalScope): Promise<void> => {
    if (scope === 'github') {
      await refreshSyncStatus(rulesetId);
      return;
    }

    setRulesetSyncStatuses(prev => {
      const next = { ...prev };
      delete next[rulesetId];
      return next;
    });
    await loadRulesets();
  };

  const doDeleteRuleset = async (rulesetId: number, scope: RemovalScope): Promise<void> => {
    setPendingDeleteId(null);
    setIsLoading(true);
    setUploadError('');
    setSuccessMessage('');
    try {
      const response: ApiResponse = await apiClient.delete(`${BACKEND_URL}/api/rulesets/${rulesetId}`, {
        params: { github_user: user, scope }
      });

      if (response.data.success) {
        const removed = response.data.removed_from_repos ?? [];
        const outcome = response.data.message || 'Ruleset deleted successfully';
        const repoCount = `${removed.length} ${removed.length === 1 ? 'repository' : 'repositories'}`;
        setSuccessMessage(
          removed.length > 0 && scope !== 'github'
            ? `${outcome} and removed from ${repoCount}`
            : outcome
        );
        await refreshAfterRemoval(rulesetId, scope);
      } else {
        setUploadError('Failed to delete ruleset');
      }
    } catch (error) {
      console.error('Error deleting ruleset:', error);
      setUploadError(apiErrorMessage(error, 'Error deleting ruleset'));
      // A 502 is partial: the repositories that succeeded have already changed,
      // so the sync panel is stale even though the removal failed overall.
      await refreshAfterRemoval(rulesetId, scope);
    } finally {
      setIsLoading(false);
    }
  };

  const applyRuleset = async (rulesetId: number): Promise<void> => {
    if (!selectedRepos || selectedRepos.length === 0) {
      setUploadError('Please select repositories to apply the ruleset to');
      return;
    }

    setIsLoading(true);
    setUploadError('');
    setSuccessMessage('');

    try {
      const repoNames = selectedRepos.map(repo => 
        typeof repo === 'string' ? repo : (repo as any).full_name || (repo as any).name
      );

      const response: ApiResponse = await apiClient.post(`${BACKEND_URL}/api/rulesets/${rulesetId}/apply`, {
        repo_names: repoNames,
        github_user: user
      });

      if (response.data.success) {
        setSuccessMessage(
          `Applied ruleset to ${response.data.applied_count} repositories successfully`
        );
      } else {
        setUploadError(
          `Applied to ${response.data.applied_count} repositories, ${response.data.error_count} failed`
        );
      }

      // Apply changes exactly what the sync panel reports, so it has to be
      // re-read here too. Without this the banner said "Applied to 2
      // repositories" above a panel still reading "Missing in 1".
      await refreshSyncStatus(rulesetId);
    } catch (error) {
      console.error('Error applying ruleset:', error);
      setUploadError(apiErrorMessage(error, 'Error applying ruleset'));
      // Partial application is possible before a throw, same as sync.
      await refreshSyncStatus(rulesetId);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleRulesetExpansion = (rulesetId: number): void => {
    setExpandedRuleset(expandedRuleset === rulesetId ? null : rulesetId);
  };

  const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Get sync status for a specific ruleset
  const getRulesetSyncStatusDisplay = (rulesetId: number): RulesetSyncStatus | null => {
    const syncStatus = rulesetSyncStatuses[rulesetId];
    
    if (!syncStatus) {
      return null;
    }

    return syncStatus;
  };

  /**
   * Repositories the status panel positively reports as lacking the ruleset.
   *
   * The backend's `missing_repos` cannot be used: it appends a repository for
   * 'permission_denied', 'repo_not_found' and plain 'error' as well as
   * 'not_found' — "treat as missing since we can't verify". Applying to one of
   * those means applying to a repository that may well already hold the
   * ruleset, which GitHub rejects with a 422 reported back as a failure. Only
   * a confirmed absence is a target.
   */
  const missingFrom = (status?: RulesetSyncStatus): string[] =>
    Object.entries(status?.repo_statuses ?? {})
      .filter(([, repo]) => repo?.status === 'not_found')
      .map(([repo]) => repo);

  /**
   * Bring the repositories that are missing the ruleset back in line.
   *
   * This used to POST /api/rulesets/{id}/sync, which no route serves, so the
   * button under "⚠️ Missing in N repositories" had never worked. Sync is an
   * apply narrowed to the repositories that lack it — its own tooltip says so —
   * and /apply already does exactly that for a given list.
   *
   * Targets come from the status the panel is already showing. Probing again
   * first doubled the GitHub reads for the same answer (one sequential read per
   * repository, each way), and storing a failed probe swapped the panel for an
   * error state that has no Sync button and nothing to re-trigger it. The
   * mandatory refresh below is what corrects a stale count.
   */
  const syncRuleset = async (rulesetId: number): Promise<void> => {
    if (!selectedRepos || selectedRepos.length === 0) {
      setUploadError('Please select repositories to sync the ruleset to');
      return;
    }

    const shown = rulesetSyncStatuses[rulesetId];
    const missingRepos = missingFrom(shown);
    const uncheckable = (shown?.missing_repos?.length ?? 0) - missingRepos.length;

    setIsLoading(true);
    setUploadError('');
    setSuccessMessage('');

    try {
      if (missingRepos.length === 0) {
        setSuccessMessage(
          uncheckable > 0
            ? `No repository is confirmed to be missing the ruleset. ${uncheckable} could not be checked.`
            : 'Ruleset is already applied to every selected repository'
        );
        await refreshSyncStatus(rulesetId);
        return;
      }

      const response: ApiResponse = await apiClient.post(`${BACKEND_URL}/api/rulesets/${rulesetId}/apply`, {
        repo_names: missingRepos,
        github_user: user
      });

      const appliedCount = response.data.applied_count ?? 0;
      const note = uncheckable > 0 ? ` (${uncheckable} could not be checked and were skipped)` : '';
      if (response.data.success) {
        setSuccessMessage(
          `Synced ruleset to ${appliedCount} ${appliedCount === 1 ? 'repository' : 'repositories'}${note}`
        );
      } else {
        setUploadError(
          `Synced to ${appliedCount} of ${missingRepos.length} repositories, ${response.data.error_count ?? 0} failed${note}`
        );
      }

      await refreshSyncStatus(rulesetId);
    } catch (error) {
      console.error('Error syncing ruleset:', error);
      setUploadError(apiErrorMessage(error, 'Error syncing ruleset'));
      // A thrown apply is not an untouched apply: the request can have created
      // the ruleset on some repositories before failing, so the panel is stale.
      await refreshSyncStatus(rulesetId);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="ruleset-manager">
      <div className="section-header">
        <h3>📋 Repository Rulesets</h3>
        <p className="section-description">
          Manage and apply GitHub repository rulesets across your selected repositories
        </p>
      </div>

      {/* Success Message */}
      {successMessage && (
        <div className="success-message">
          <span>✅ {successMessage}</span>
          <button onClick={() => setSuccessMessage('')}>×</button>
        </div>
      )}

      {/* Error Message */}
      {uploadError && (
        <div className="error-message">
          <span>❌ {uploadError}</span>
          <button onClick={() => setUploadError('')}>×</button>
        </div>
      )}

      {/* Upload Section */}
      <div className="upload-section">
        <h4>📋 Upload Ruleset</h4>
        <div className="upload-controls">
          <div className="file-input-wrapper">
            <input
              type="file"
              accept=".json"
              onChange={handleFileSelect}
              className="file-input"
              id="ruleset-file"
            />
            <label htmlFor="ruleset-file" className="file-input-label">
              {selectedFile ? selectedFile.name : "Choose JSON file..."}
            </label>
          </div>
          
          <button
            onClick={handleUpload}
            disabled={!selectedFile || isUploading}
            className="upload-button"
          >
            {isUploading ? "⏳ Uploading..." : "📤 Upload Ruleset"}
          </button>
        </div>
        
        <div className="upload-help">
          <small>
            📄 Upload exported GitHub repository ruleset JSON files.{' '}
            <a 
              href="https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/managing-rulesets-for-a-repository" 
              target="_blank" 
              rel="noopener noreferrer"
            >
              Learn more about rulesets{' '}
            </a>
          </small>
        </div>
      </div>

      {/* Rulesets List */}
      <div className="rulesets-section">
        <h4>📋 Uploaded Rulesets</h4>
        
        {isLoading ? (
          <div className="loading-section">
            <p>⏳ Loading rulesets...</p>
          </div>
        ) : rulesets.length === 0 ? (
          <div className="no-rulesets">
            <p>📭 No rulesets uploaded yet. Upload a ruleset JSON file to get started.</p>
          </div>
        ) : (
          <div className="rulesets-list">
            {rulesets.map((ruleset) => (
              <div key={ruleset.ruleset_id} className="ruleset-card">
                <div className="ruleset-header-row">
                  <div className="ruleset-info">
                    <h5>{ruleset.ruleset_name}</h5>
                    <p className="ruleset-description">
                      {ruleset.description || 'No description provided'}
                    </p>
                    <div className="ruleset-meta">
                      <span>Created: {formatDate(ruleset.created_at)}</span>
                      {ruleset.updated_at !== ruleset.created_at && (
                        <span>Updated: {formatDate(ruleset.updated_at)}</span>
                      )}
                    </div>
                  </div>
                  
                  <div className="ruleset-actions">
                    {/* Sync Status Display */}
                    {selectedRepos && selectedRepos.length > 0 && (
                      <div style={{ marginBottom: '8px' }}>
                        {(() => {
                          const syncStatus = getRulesetSyncStatusDisplay(ruleset.ruleset_id);
                          const isLoadingThisRuleset = loadingSyncStatus;
                          
                          if (isLoadingThisRuleset) {
                            return (
                              <div className="sync-status loading">
                                <span>⏳ Checking sync status...</span>
                              </div>
                            );
                          }
                          
                          if (!syncStatus) {
                            return (
                              <div className="sync-status unknown">
                                <span>❓ Unknown sync status</span>
                              </div>
                            );
                          }
                          
                          if (syncStatus.error) {
                            return (
                              <div className="sync-status error">
                                <span>❌ Error: {syncStatus.error}</span>
                              </div>
                            );
                          }
                          
                          if (syncStatus.is_synced) {
                            return (
                              <div className="sync-status synced">
                                <span>✅ Synced across all repositories</span>
                              </div>
                            );
                          } else {
                            const missingCount = syncStatus.missing_repos?.length || 0;
                            return (
                              <div className="sync-status out-of-sync">
                                <span>⚠️ Missing in {missingCount} repositories</span>
                                <button
                                  onClick={() => syncRuleset(ruleset.ruleset_id)}
                                  disabled={isLoading}
                                  className="sync-button"
                                  title="Sync ruleset to missing repositories"
                                >
                                  🔄 Sync
                                </button>
                              </div>
                            );
                          }
                        })()}
                      </div>
                    )}
                    
                    <div className="action-buttons">
                      <button
                        onClick={() => toggleRulesetExpansion(ruleset.ruleset_id)}
                        className="expand-button"
                        title="View ruleset details"
                      >
                        {expandedRuleset === ruleset.ruleset_id ? "📤 Collapse" : "📥 Expand"}
                      </button>
                      
                      <button
                        onClick={() => applyRuleset(ruleset.ruleset_id)}
                        disabled={!selectedRepos || selectedRepos.length === 0 || isLoading}
                        className="apply-button"
                        title="Apply ruleset to selected repositories"
                      >
                        🚀 Apply
                      </button>
                      
                      <button
                        onClick={() => handleDeleteRuleset(ruleset.ruleset_id)}
                        disabled={isLoading}
                        className="delete-button"
                        title="Delete ruleset"
                      >
                        🗑️ Delete
                      </button>
                    </div>
                  </div>
                </div>

                {/* Expanded ruleset details */}
                {expandedRuleset === ruleset.ruleset_id && (
                  <div className="ruleset-details">
                    <h6>Ruleset Configuration:</h6>
                    <pre className="ruleset-json">
                      {JSON.stringify(ruleset.ruleset_json, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Info Section */}
      <div className="info-section">
        <h4>ℹ️ About Rulesets</h4>
        <ul>
          <li>Rulesets define rules that apply to repositories (branch protection, required workflows, etc.)</li>
          <li>Export rulesets from GitHub repository settings as JSON files</li>
          <li>Apply rulesets to multiple repositories for consistent governance</li>
          <li>Select repositories in the "Repositories & Branches" section before applying</li>
        </ul>
      </div>

      {pendingDeleteId !== null && (
        <RemovalScopeDialog
          open={true}
          title={`Delete ruleset "${rulesets.find(r => r.ruleset_id === pendingDeleteId)?.ruleset_name ?? ''}"?`}
          githubLocation="your project's repositories"
          resourceNoun="ruleset"
          projectScopeDetail="it stops checking whether the repositories still have it"
          githubScopeWarning="This action cannot be undone! The ruleset is permanently deleted from your project's repositories, and any branch protection it enforces stops applying."
          offerGitHubOnly
          githubOnlyDetail="ActionsManager keeps the ruleset, so you can apply it again without re-importing it"
          neverSynced={hasNoGithubCopy(pendingDeleteId)}
          onConfirm={(scope) => { void doDeleteRuleset(pendingDeleteId, scope); }}
          onCancel={() => setPendingDeleteId(null)}
        />
      )}
    </div>
  );
};

export default RulesetManager;
