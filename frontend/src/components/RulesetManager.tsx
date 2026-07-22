/* eslint-disable no-restricted-syntax, no-restricted-imports -- Legacy: TODO migrate inline styles and CSS imports to Tailwind CSS classes */
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import config from '../config';
import { getRulesetSyncStatus } from '../api/rulesets';
import ConfirmDialog from './ConfirmDialog';
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
  };
}

interface ApiError {
  response?: {
    data?: {
      detail?: string;
    };
  };
  message: string;
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

  // Load rulesets when component mounts or project changes
  useEffect(() => {
    if (user && projectName) {
      loadRulesets();
    }
  }, [user, projectName]); // eslint-disable-line react-hooks/exhaustive-deps

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
      const response: ApiResponse = await axios.get(`${BACKEND_URL}/api/rulesets/${projectName}`, {
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

      const response: ApiResponse = await axios.post(`${BACKEND_URL}/api/rulesets/upload`, formData, {
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
      const err = error as ApiError;
      setUploadError(err.response?.data?.detail || 'Error uploading ruleset');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDeleteRuleset = (rulesetId: number): void => {
    setPendingDeleteId(rulesetId);
  };

  const doDeleteRuleset = async (rulesetId: number): Promise<void> => {
    setPendingDeleteId(null);
    setIsLoading(true);
    try {
      const response: ApiResponse = await axios.delete(`${BACKEND_URL}/api/rulesets/${rulesetId}`, {
        params: { github_user: user }
      });

      if (response.data.success) {
        setSuccessMessage(response.data.message || 'Ruleset deleted successfully');
        await loadRulesets();
      } else {
        setUploadError('Failed to delete ruleset');
      }
    } catch (error) {
      console.error('Error deleting ruleset:', error);
      const err = error as ApiError;
      setUploadError(err.response?.data?.detail || 'Error deleting ruleset');
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

      const response: ApiResponse = await axios.post(`${BACKEND_URL}/api/rulesets/${rulesetId}/apply`, {
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
    } catch (error) {
      console.error('Error applying ruleset:', error);
      const err = error as ApiError;
      setUploadError(err.response?.data?.detail || 'Error applying ruleset');
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

  const syncRuleset = async (rulesetId: number): Promise<void> => {
    if (!selectedRepos || selectedRepos.length === 0) {
      setUploadError('Please select repositories to sync the ruleset to');
      return;
    }

    setIsLoading(true);
    setUploadError('');
    setSuccessMessage('');

    try {
      const repoNames = selectedRepos.map(repo => 
        typeof repo === 'string' ? repo : (repo as any).full_name || (repo as any).name
      );

      const response: ApiResponse = await axios.post(`${BACKEND_URL}/api/rulesets/${rulesetId}/sync`, {
        repo_names: repoNames,
        github_user: user
      });

      if (response.data.success) {
        setSuccessMessage(
          `Synced ruleset to ${response.data.applied_count} repositories successfully`
        );
        
        // Refresh sync status after successful sync
        const syncStatus = await getRulesetSyncStatus(user, rulesetId, repoNames);
        setRulesetSyncStatuses(prev => ({
          ...prev,
          [rulesetId]: syncStatus
        }));
        
      } else {
        setUploadError(
          `Synced to ${response.data.applied_count} repositories, ${response.data.error_count} failed`
        );
      }
    } catch (error) {
      console.error('Error syncing ruleset:', error);
      const err = error as ApiError;
      setUploadError(err.response?.data?.detail || 'Error syncing ruleset');
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
        <ConfirmDialog
          open={true}
          title="Delete ruleset?"
          description="This will permanently delete the ruleset from Actions Manager. Repositories that already have rules applied will not be affected."
          confirmLabel="Delete"
          destructive
          onConfirm={() => { void doDeleteRuleset(pendingDeleteId); }}
          onCancel={() => setPendingDeleteId(null)}
        />
      )}
    </div>
  );
};

export default RulesetManager;
