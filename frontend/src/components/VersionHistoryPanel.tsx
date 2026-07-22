import React, { useState, useEffect } from 'react';
import { 
  getWorkflowVersions, 
  restoreWorkflowVersion, 
  WorkflowVersion, 
  VersionHistoryResponse 
} from '../api/workflows';
import ConfirmDialog from './ConfirmDialog';
import { toast } from '../utils/toast';
// eslint-disable-next-line no-restricted-imports -- Legacy: TODO migrate CSS file to Tailwind CSS classes
import '../styles/VersionHistoryPanel.css';

interface VersionHistoryPanelProps {
  user: string;
  projectName: string;
  workflowName: string;
  currentContent: string;
  onClose: () => void;
  onRestore: (content: string) => void;
}

const VersionHistoryPanel: React.FC<VersionHistoryPanelProps> = ({
  user,
  projectName,
  workflowName,
  currentContent,
  onClose,
  onRestore,
}) => {
  const [versions, setVersions] = useState<WorkflowVersion[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<WorkflowVersion | null>(null);
  const [comparing, setComparing] = useState<boolean>(false);
  const [restoring, setRestoring] = useState<boolean>(false);
  const [confirmingRestore, setConfirmingRestore] = useState<WorkflowVersion | null>(null);

  useEffect(() => {
    loadVersionHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, projectName, workflowName]);

  const loadVersionHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const response: VersionHistoryResponse = await getWorkflowVersions(
        user,
        projectName,
        workflowName
      );
      setVersions(response.versions);
    } catch (err: any) {
      console.error('Error loading version history:', err);
      setError(err.message || 'Failed to load version history');
    } finally {
      setLoading(false);
    }
  };

  const handleRestore = async (version: WorkflowVersion) => {
    setConfirmingRestore(version);
  };

  const doRestore = async (version: WorkflowVersion) => {
    setConfirmingRestore(null);
    setRestoring(true);
    setError(null);

    try {
      const response = await restoreWorkflowVersion(
        user,
        projectName,
        workflowName,
        version.version_id
      );
      
      // Update the parent component with the restored content
      onRestore(response.restored_content);
      
      // Reload version history to show the new restore entry
      await loadVersionHistory();
      
      toast.success(response.message || `Workflow restored to version ${version.version_number}.`);
    } catch (err: any) {
      console.error('Error restoring version:', err);
      setError(err.message || 'Failed to restore version');
      toast.error(`Failed to restore version: ${err.message}`);
    } finally {
      setRestoring(false);
    }
  };

  const handleViewVersion = (version: WorkflowVersion) => {
    setSelectedVersion(version);
    setComparing(false);
  };

  const handleCompareVersion = (version: WorkflowVersion) => {
    setSelectedVersion(version);
    setComparing(true);
  };

  const formatDate = (dateString: string): string => {
    try {
      const date = new Date(dateString);
      return date.toLocaleString();
    } catch {
      return dateString;
    }
  };

  const parseMetadata = (metadata: string | null): Record<string, any> | null => {
    if (!metadata) return null;
    try {
      return JSON.parse(metadata);
    } catch {
      return null;
    }
  };

  const getMetadataAction = (parsed: Record<string, any> | null): string => {
    return parsed?.action || 'saved';
  };

  const isPRMerged = (parsed: Record<string, any> | null): boolean => {
    return parsed?.action === 'pr_merged';
  };

  const getPRMergedLabel = (parsed: Record<string, any> | null): string => {
    if (parsed?.pr_number) {
      return `PR #${parsed.pr_number} merged`;
    }
    return 'PR merged';
  };

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div className="version-history-overlay" onClick={handleOverlayClick}>
      <div className="version-history-panel">
        <div className="version-history-header">
          <h2>Version History: {workflowName}</h2>
          <button className="close-button" onClick={onClose}>✕</button>
        </div>

        {error && (
          <div className="error-message">
            ❌ {error}
          </div>
        )}

        <div className="version-history-content">
          {loading ? (
            <div className="loading-state">
              <div className="spinner"></div>
              <p>Loading version history...</p>
            </div>
          ) : versions.length === 0 ? (
            <div className="empty-state">
              <p>No version history available yet.</p>
              <p className="empty-state-hint">Versions will be created automatically when you save the workflow.</p>
            </div>
          ) : (
            <div className="version-list-container">
              <div className="version-list">
                <div className="version-list-header">
                  <span className="header-version">Version</span>
                  <span className="header-date">Date</span>
                  <span className="header-action">Action</span>
                  <span className="header-controls">Controls</span>
                </div>
                {versions.map((version) => {
                  const parsedMeta = parseMetadata(version.metadata);
                  const merged = isPRMerged(parsedMeta);
                  return (
                  <div 
                    key={version.version_id} 
                    className={`version-item ${selectedVersion?.version_id === version.version_id ? 'selected' : ''} ${merged ? 'version-item-merged' : ''}`}
                  >
                    <span className="version-number">
                      v{version.version_number}
                    </span>
                    <span className="version-date">{formatDate(version.created_at)}</span>
                    <span className="version-action">
                      {merged
                        ? <span className="action-pr-merged">⭐️ {getPRMergedLabel(parsedMeta)}</span>
                        : getMetadataAction(parsedMeta)
                      }
                    </span>
                    <div className="version-controls">
                      <button
                        className="btn-view"
                        onClick={() => handleViewVersion(version)}
                        title="View this version"
                      >
                        👁️ View
                      </button>
                      <button
                        className="btn-compare"
                        onClick={() => handleCompareVersion(version)}
                        title="Compare with current version"
                      >
                        🔍 Compare
                      </button>
                      <button
                        className="btn-restore"
                        onClick={() => handleRestore(version)}
                        disabled={restoring}
                        title="Restore to this version"
                      >
                        ↩️ Restore
                      </button>
                    </div>
                  </div>
                  );
                })}
              </div>

              {selectedVersion && (
                <div className="version-preview">
                  <div className="preview-header">
                    <h3>
                      {comparing ? 'Comparison' : `Version ${selectedVersion.version_number}`}
                    </h3>
                    <button 
                      className="btn-close-preview"
                      onClick={() => setSelectedVersion(null)}
                    >
                      ✕
                    </button>
                  </div>
                  <div className="preview-content">
                    {comparing ? (
                      <div className="comparison-view">
                        <div className="comparison-column">
                          <h4>Current Version</h4>
                          <pre className="code-preview">{currentContent}</pre>
                        </div>
                        <div className="comparison-divider"></div>
                        <div className="comparison-column">
                          <h4>Version {selectedVersion.version_number}</h4>
                          <pre className="code-preview">{selectedVersion.content}</pre>
                        </div>
                      </div>
                    ) : (
                      <pre className="code-preview">{selectedVersion.content}</pre>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="version-history-footer">
          <button className="btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>

      {confirmingRestore && (
        <ConfirmDialog
          open={true}
          title={`Restore to version ${confirmingRestore.version_number}?`}
          description="This will replace the current workflow content with the content from this version. A new version entry will be created to track this restoration."
          confirmLabel="Restore"
          onConfirm={() => { void doRestore(confirmingRestore); }}
          onCancel={() => setConfirmingRestore(null)}
        />
      )}
    </div>
  );
};

export default VersionHistoryPanel;
