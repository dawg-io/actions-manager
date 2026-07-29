/* eslint-disable no-restricted-syntax -- Legacy: TODO migrate inline styles to Tailwind CSS classes */
import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { UnifiedWorkflowItem } from '../types/workflow';
import { normalizeWorkflowFilename } from '../utils/workflowFilename';
import WorkflowStatusBadge from './WorkflowStatusBadge';
import { CustomFile } from '../api/customFiles';

/** Small decorative indicator showing who last saved a workflow. */
const LastSavedByIndicator: React.FC<{ username: string }> = ({ username }) => {
  const [imageError, setImageError] = React.useState(false);

  return (
    <div className="workflow-last-saved-by" title={`Last saved by ${username}`}>
      {!imageError ? (
        <img
          src={`https://github.com/${encodeURIComponent(username)}.png?size=32`}
          alt=""
          aria-hidden="true"
          onError={() => setImageError(true)}
          style={{ width: 16, height: 16, borderRadius: '50%', display: 'inline-block', verticalAlign: 'middle' }}
        />
      ) : (
        <span
          style={{
            width: 16,
            height: 16,
            borderRadius: '50%',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: '#e5e7eb',
            color: '#6b7280',
            fontSize: '0.625rem',
            fontWeight: 600,
            verticalAlign: 'middle'
          }}
        >
          {username.charAt(0).toUpperCase()}
        </span>
      )}
      <span style={{ fontSize: '0.75rem', marginLeft: 4, opacity: 0.7 }}>{username}</span>
    </div>
  );
};

/** Amber badge shown when a workflow has been changed directly in GitHub. */
const DriftBadge: React.FC = () => (
  <div
    className="workflow-lifecycle-status status-drift"
    title="Workflow was changed directly in GitHub. Use Review Drift to resolve."
    data-testid="drift-badge"
    style={{
      background: 'rgba(245,158,11,0.15)',
      color: '#92400e',
      borderColor: 'rgba(245,158,11,0.4)',
    }}
  >
    <span aria-hidden="true">⚠️</span>
    <span className="lifecycle-label">Drift detected</span>
  </div>
);

interface UnifiedWorkflowListProps {
  unifiedWorkflows: UnifiedWorkflowItem[];
  selectedWorkflowId: string | null;
  isCollapsed: boolean;
  projectCode: string | null;
  usePrefix?: boolean;
  loadingStatuses: boolean;
  workflowStatuses: Record<string, any>;
  selectedRepos: string[];
  reusableWorkflowsEnabled: boolean;
  repoExists: boolean;
  setIsCollapsed: (collapsed: boolean) => void;
  handleSelectWorkflow: (workflowId: string) => void;
  /** Opens the Add Project File dialog (Workflow / Reusable Workflow / Link Reusable Workflow / Custom File / CODEOWNERS). */
  addWorkflowFn?: () => void;
  /** Set of workflow names currently drifted on GitHub (renders an amber badge). */
  driftedWorkflowNames?: Set<string>;
  // Project Files: Custom Files
  customFiles?: CustomFile[];
  selectedCustomFileId?: number | null;
  onSelectCustomFile?: (id: number) => void;
  // Project Files: CODEOWNERS
  codeownersRepos?: string[];
  selectedCodeownersRepo?: string | null;
  onSelectCodeowners?: (repo: string) => void;
  codeownersAggregateStatus?: string;
}

const WORKFLOW_STATUS_LABELS: Record<string, { label: string; className: string }> = {
  new:                  { label: 'New Local',           className: 'status-new' },
  committed_locally:    { label: 'Committed Locally',   className: 'status-committed' },
  under_review:         { label: 'Under Review',        className: 'status-review' },
  synced_with_github:   { label: 'Synced',              className: 'status-synced' },
};

const DETAIL_SEPARATOR = ' · ';
const COMPACT_FILENAME_MAX_LENGTH = 16;
const COMPACT_FILENAME_MIN_SEGMENT_LENGTH = 4;
const COMPACT_FILENAME_MAX_PREFIX_LENGTH = 6;
const COMPACT_FILENAME_FALLBACK_PREFIX_LENGTH = 6;
const COMPACT_FILENAME_NO_EXTENSION_PREFIX_LENGTH = 8;

const getWorkflowStatusDisplay = (status?: string) => {
  if (!status) return null;
  return WORKFLOW_STATUS_LABELS[status] || null;
};

const getWorkflowDisplayFilename = (workflow: UnifiedWorkflowItem, fallbackLabel: string) =>
  workflow.name ? normalizeWorkflowFilename(workflow.name) : fallbackLabel;

const selectAbbreviationPrefix = (stem: string) => {
  const firstSegment = stem.split(/[-_.]/)[0];
  if (firstSegment.length >= COMPACT_FILENAME_MIN_SEGMENT_LENGTH) {
    return firstSegment.slice(0, COMPACT_FILENAME_MAX_PREFIX_LENGTH);
  }
  return stem.slice(0, COMPACT_FILENAME_FALLBACK_PREFIX_LENGTH);
};

const abbreviateWorkflowFilename = (filename: string) => {
  if (filename.length <= COMPACT_FILENAME_MAX_LENGTH) return filename;

  const extensionMatch = filename.match(/\.(ya?ml)$/i);
  if (extensionMatch) {
    const extension = extensionMatch[1].toLowerCase();
    const stem = filename.slice(0, -extensionMatch[0].length);
    return `${selectAbbreviationPrefix(stem)}…${extension}`;
  }

  return `${filename.slice(0, COMPACT_FILENAME_NO_EXTENSION_PREFIX_LENGTH)}…`;
};

const getCompactStatus = (workflow: UnifiedWorkflowItem) => {
  const statusDisplay = getWorkflowStatusDisplay(workflow.workflowStatus);
  if (statusDisplay) return statusDisplay;
  if (workflow.isModified) {
    return { label: 'Unsaved changes', emoji: '', className: 'status-unsaved' };
  }
  return { label: 'No status', emoji: '', className: 'status-none' };
};

const getLinkedWorkflowSourceDetails = (workflow: UnifiedWorkflowItem) => [
  workflow.rwxProjectName ? `From: ${workflow.rwxProjectName}` : null,
  workflow.rwxRepo ? `Repo: ${workflow.rwxRepo}` : null,
].filter(Boolean).join(DETAIL_SEPARATOR);

const UnifiedWorkflowList: React.FC<UnifiedWorkflowListProps> = ({
  unifiedWorkflows,
  selectedWorkflowId,
  isCollapsed,
  projectCode,
  usePrefix = true,
  loadingStatuses,
  workflowStatuses,
  selectedRepos,
  reusableWorkflowsEnabled,
  repoExists,
  setIsCollapsed,
  handleSelectWorkflow,
  addWorkflowFn,
  driftedWorkflowNames,
  customFiles,
  selectedCustomFileId,
  onSelectCustomFile,
  codeownersRepos,
  selectedCodeownersRepo,
  onSelectCodeowners,
  codeownersAggregateStatus,
}) => {
  const isDrifted = (name?: string) =>
    !!(name && driftedWorkflowNames?.has(name));

  const regularWorkflows = unifiedWorkflows.filter(w => w.type === 'regular');
  const reusableWorkflows = unifiedWorkflows.filter(w => w.type === 'reusable');
  const linkedWorkflows = unifiedWorkflows.filter(w => w.type === 'linked');

  const renderCompactWorkflowItem = (workflow: UnifiedWorkflowItem, fallbackLabel: string) => {
    const filename = getWorkflowDisplayFilename(workflow, fallbackLabel);
    const status = getCompactStatus(workflow);
    const sourceDetails = workflow.type === 'linked' ? getLinkedWorkflowSourceDetails(workflow) : '';
    const titleParts = [
      filename,
      workflow.type === 'linked' ? 'Linked workflow' : status.label,
      sourceDetails || null,
    ].filter(Boolean);
    const ariaLabel = [filename, workflow.type === 'linked' ? `Linked workflow, ${status.label}` : status.label]
      .filter(Boolean)
      .join(', ');
    const isSelected = selectedWorkflowId === workflow.id;

    return (
      <li key={workflow.id} data-testid={workflow.type === 'linked' ? 'linked-rwx-workflow-card' : undefined}>
        <button
          className={`workflow-compact-item ${isSelected ? 'selected' : ''}`}
          onClick={() => handleSelectWorkflow(workflow.id)}
          title={titleParts.join(DETAIL_SEPARATOR)}
          aria-label={ariaLabel}
          aria-current={isSelected ? 'page' : undefined}
        >
          <span className="workflow-compact-icon" aria-hidden="true">
            {workflow.type === 'linked' ? '🔗' : workflow.type === 'reusable' ? '🔄' : '📄'}
          </span>
          <span className="workflow-compact-name">{abbreviateWorkflowFilename(filename)}</span>
          <span
            className={`workflow-compact-status-dot ${status.className}`}
            title={status.label}
            aria-hidden="true"
          />
        </button>
      </li>
    );
  };

  return (
    <div className={`unified-workflows-list ${isCollapsed ? 'collapsed' : 'expanded'}`}>
      <div className="workflows-list-header">
        <div className="workflows-list-header-content">
          {!isCollapsed && <h4>📁 Project Files</h4>}
          {isCollapsed && <h4>📁</h4>}
        </div>
        <div className="workflows-list-header-actions">
          {!isCollapsed && addWorkflowFn && (
            <button
              className="btn btn-primary"
              style={{ fontSize: '0.8rem', padding: '0.3rem 0.7rem', whiteSpace: 'nowrap' }}
              onClick={addWorkflowFn}
            >
              + Add File
            </button>
          )}
          <button
            className="workflows-list-toggle"
            onClick={() => setIsCollapsed(!isCollapsed)}
            title={isCollapsed ? 'Expand workflows list' : 'Collapse workflows list'}
          >
            {isCollapsed ? (
              <ChevronRight className="workflows-list-toggle-icon" />
            ) : (
              <ChevronLeft className="workflows-list-toggle-icon" />
            )}
          </button>
        </div>
      </div>
      
      {isCollapsed && (
        <nav className="workflows-list-container compact" aria-label="Compact workflow navigation">
          {unifiedWorkflows.length === 0 ? (
            <div className="empty-workflow-list compact">
              <span>No workflows</span>
            </div>
          ) : (
            <div className="workflow-compact-sections">
              {(regularWorkflows.length > 0 || (reusableWorkflowsEnabled && repoExists && reusableWorkflows.length > 0)) && (
                <div className="workflow-compact-section">
                  <ul className="workflow-compact-items">
                    {regularWorkflows.map((workflow) =>
                      renderCompactWorkflowItem(workflow, `Untitled Workflow ${workflow.originalIndex + 1}`)
                    )}
                    {reusableWorkflowsEnabled && repoExists && reusableWorkflows.map((workflow) =>
                      renderCompactWorkflowItem(workflow, `Untitled Reusable Workflow ${workflow.originalIndex + 1}`)
                    )}
                  </ul>
                </div>
              )}

              {linkedWorkflows.length > 0 && (
                <section className="workflow-compact-section linked" aria-label="Linked workflows">
                  <div className="workflow-compact-section-divider" title="Linked Workflows">
                    <span aria-hidden="true">🔗</span>
                  </div>
                  <ul className="workflow-compact-items">
                    {linkedWorkflows.map((workflow) =>
                      renderCompactWorkflowItem(workflow, `Untitled Linked Workflow ${workflow.originalIndex + 1}`)
                    )}
                  </ul>
                </section>
              )}

              {customFiles && customFiles.length > 0 && (
                <section className="workflow-compact-section" aria-label="Custom files">
                  <div className="workflow-compact-section-divider" title="Custom Files">
                    <span aria-hidden="true">📄</span>
                  </div>
                  <ul className="workflow-compact-items">
                    {customFiles.map((cf) => (
                      <li key={cf.id}>
                        <button
                          className={`workflow-compact-item ${selectedCustomFileId === cf.id ? 'selected' : ''}`}
                          onClick={() => onSelectCustomFile?.(cf.id)}
                          title={cf.file_path}
                          aria-label={cf.file_path}
                          aria-current={selectedCustomFileId === cf.id ? 'page' : undefined}
                        >
                          <span className="workflow-compact-icon" aria-hidden="true">📄</span>
                          <span className="workflow-compact-name">{cf.file_path.split('/').pop()}</span>
                          <span
                            className={`workflow-compact-status-dot ${WORKFLOW_STATUS_LABELS[cf.file_status ?? '']?.className ?? 'status-committed'}`}
                            aria-hidden="true"
                          />
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {codeownersRepos && codeownersRepos.length > 0 && (
                <section className="workflow-compact-section" aria-label="CODEOWNERS">
                  <div className="workflow-compact-section-divider" title="CODEOWNERS">
                    <span aria-hidden="true">👥</span>
                  </div>
                  <ul className="workflow-compact-items">
                    <li>
                      <button
                        className={`workflow-compact-item ${selectedCodeownersRepo !== null ? 'selected' : ''}`}
                        onClick={() => onSelectCodeowners?.(codeownersRepos?.[0] ?? selectedRepos[0])}
                        title="CODEOWNERS"
                        aria-label="CODEOWNERS"
                        aria-current={selectedCodeownersRepo !== null ? 'page' : undefined}
                      >
                        <span className="workflow-compact-icon" aria-hidden="true">👥</span>
                        <span className="workflow-compact-name">CODEOWNERS</span>
                        <span
                          className={`workflow-compact-status-dot ${codeownersAggregateStatus ? (WORKFLOW_STATUS_LABELS[codeownersAggregateStatus]?.className ?? 'status-none') : 'status-none'}`}
                          aria-hidden="true"
                        />
                      </button>
                    </li>
                  </ul>
                </section>
              )}
            </div>
          )}
        </nav>
      )}

      {!isCollapsed && (
        <div className="workflows-list-container">
          <div className="unified-workflow-sections">

              {/* Workflows Section */}
              <div className="pf-section">
                <div className="pf-section-header">
                  <span className="section-icon" aria-hidden="true">📝</span>
                  <span>Workflows</span>
                  {regularWorkflows.length > 0 && <span className="pf-section-count">{regularWorkflows.length}</span>}
                </div>
                <div className="pf-section-body">
                  {regularWorkflows.length === 0 ? (
                    <div className="empty-section-hint">No workflows yet</div>
                  ) : (
                    <ul className="workflow-items">
                      {regularWorkflows.map((workflow) => (
                        <li key={workflow.id} className="workflow-item-wrapper">
                          <button
                            className={`workflow-item ${selectedWorkflowId === workflow.id ? 'selected' : ''}`}
                            onClick={() => handleSelectWorkflow(workflow.id)}
                          >
                            <div className="workflow-item-content">
                              <div className="workflow-name">
                                {workflow.name && usePrefix && (
                                  <span className="workflow-prefix">
                                    AM_{(projectCode || '').toUpperCase()}_
                                  </span>
                                )}
                                {workflow.name ? normalizeWorkflowFilename(workflow.name) : `Untitled Workflow ${workflow.originalIndex + 1}`}
                              </div>
                              {(() => {
                                const statusDisplay = getWorkflowStatusDisplay(workflow.workflowStatus);
                                if (!statusDisplay) return null;
                                return <WorkflowStatusBadge status={workflow.workflowStatus ?? ''} label={statusDisplay.label} style={{ marginTop: '0.2rem' }} />;
                              })()}
                              {isDrifted(workflow.name) && <DriftBadge />}
                              {workflow.lastModifiedBy && <LastSavedByIndicator username={workflow.lastModifiedBy} />}
                            </div>
                            {workflow.isModified && <div className="modified-indicator" title="Unsaved changes">•</div>}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>

              {/* Reusable Workflows Section */}
              {reusableWorkflowsEnabled && repoExists && reusableWorkflows.length > 0 && (
                <div className="pf-section">
                  <div className="pf-section-header">
                    <span className="section-icon" aria-hidden="true">🔄</span>
                    <span>Reusable Workflows</span>
                    <span className="pf-section-count">{reusableWorkflows.length}</span>
                  </div>
                  <div className="pf-section-body">
                    <ul className="workflow-items">
                      {reusableWorkflows.map((workflow) => (
                        <li key={workflow.id} className="workflow-item-wrapper">
                          <button
                            className={`workflow-item ${selectedWorkflowId === workflow.id ? 'selected' : ''}`}
                            onClick={() => handleSelectWorkflow(workflow.id)}
                          >
                            <div className="workflow-item-content">
                              <div className="workflow-name">
                                {workflow.name && usePrefix && (
                                  <span className="workflow-prefix">
                                    AM_{(projectCode || '').toUpperCase()}_
                                  </span>
                                )}
                                {workflow.name ? normalizeWorkflowFilename(workflow.name) : `Untitled Reusable Workflow ${workflow.originalIndex + 1}`}
                              </div>
                              {(() => {
                                const statusDisplay = getWorkflowStatusDisplay(workflow.workflowStatus);
                                if (!statusDisplay) return null;
                                return <WorkflowStatusBadge status={workflow.workflowStatus ?? ''} label={statusDisplay.label} style={{ marginTop: '0.2rem' }} />;
                              })()}
                              {isDrifted(workflow.name) && <DriftBadge />}
                              {workflow.lastModifiedBy && <LastSavedByIndicator username={workflow.lastModifiedBy} />}
                              <div className="workflow-type">
                                <span className="type-badge reusable">Reusable</span>
                              </div>
                            </div>
                            {workflow.isModified && <div className="modified-indicator" title="Unsaved changes">•</div>}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* Linked Workflows Section */}
              {linkedWorkflows.length > 0 && (
                <div className="pf-section">
                  <div className="pf-section-header">
                    <span className="section-icon" aria-hidden="true">🔗</span>
                    <span>Linked Workflows</span>
                    <span className="pf-section-count">{linkedWorkflows.length}</span>
                  </div>
                  <div className="pf-section-body">
                    <ul className="workflow-items">
                      {linkedWorkflows.map((workflow) => (
                        <li key={workflow.id} className="workflow-item-wrapper" data-testid="linked-rwx-workflow-card">
                          <button
                            className={`workflow-item ${selectedWorkflowId === workflow.id ? 'selected' : ''}`}
                            onClick={() => handleSelectWorkflow(workflow.id)}
                          >
                            <div className="workflow-item-content">
                              <div className="workflow-name">
                                {workflow.name ? normalizeWorkflowFilename(workflow.name) : `Untitled Linked Workflow ${workflow.originalIndex + 1}`}
                              </div>
                              {workflow.rwxProjectName && (
                                <div className="workflow-prefix">From: {workflow.rwxProjectName}</div>
                              )}
                              {(() => {
                                const statusDisplay = getWorkflowStatusDisplay(workflow.workflowStatus);
                                if (!statusDisplay) return null;
                                return <WorkflowStatusBadge status={workflow.workflowStatus ?? ''} label={statusDisplay.label} style={{ marginTop: '0.2rem' }} />;
                              })()}
                              <WorkflowStatusBadge status="linked" style={{ marginTop: '0.2rem' }} />
                            </div>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* Custom Files Section */}
              {customFiles !== undefined && (
                <div className="pf-section">
                  <div className="pf-section-header">
                    <span className="section-icon" aria-hidden="true">📄</span>
                    <span>Custom Files</span>
                    {customFiles.length > 0 && <span className="pf-section-count">{customFiles.length}</span>}
                  </div>
                  <div className="pf-section-body">
                    {customFiles.length === 0 ? (
                      <div className="empty-section-hint">No custom files yet</div>
                    ) : (
                      <ul className="workflow-items">
                        {customFiles.map((cf) => (
                          <li key={cf.id} className="workflow-item-wrapper">
                            <button
                              className={`workflow-item ${selectedCustomFileId === cf.id ? 'selected' : ''}`}
                              onClick={() => onSelectCustomFile?.(cf.id)}
                              data-testid="custom-file-row"
                            >
                              <div className="workflow-item-content">
                                <div className="workflow-name" style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                                  {cf.file_path}
                                </div>
                                {cf.display_name && <div className="workflow-prefix">{cf.display_name}</div>}
                                <WorkflowStatusBadge status={cf.file_status} style={{ marginTop: '0.2rem' }} />
                                {cf.pending_delete && (
                                  <WorkflowStatusBadge
                                    status="pending_delete"
                                    label="Pending Deletion"
                                    style={{ marginTop: '0.2rem', backgroundColor: 'rgba(245,158,11,0.12)', borderColor: 'rgba(245,158,11,0.35)', color: '#fbbf24' }}
                                  />
                                )}
                                {cf.last_modified_by && (
                                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', marginTop: '0.25rem' }}>
                                    <img
                                      src={`https://github.com/${encodeURIComponent(cf.last_modified_by)}.png?size=32`}
                                      alt=""
                                      aria-hidden
                                      style={{ width: 14, height: 14, borderRadius: '50%' }}
                                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                                    />
                                    <span style={{ fontSize: '0.7rem', opacity: 0.7 }}>{cf.last_modified_by}</span>
                                  </div>
                                )}
                              </div>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )}

              {/* CODEOWNERS Section */}
              {codeownersRepos && codeownersRepos.length > 0 && (
                <div className="pf-section">
                  <div className="pf-section-header">
                    <span className="section-icon" aria-hidden="true">👥</span>
                    <span>CODEOWNERS</span>
                    {codeownersAggregateStatus && (
                      <WorkflowStatusBadge status={codeownersAggregateStatus} style={{ marginLeft: 'auto' }} />
                    )}
                  </div>
                  <div className="pf-section-body">
                    <ul className="codeowners-repo-list" style={{ padding: 0 }}>
                      <li>
                        <button
                          className={`codeowners-repo-item ${selectedCodeownersRepo !== null ? 'selected' : ''}`}
                          onClick={() => onSelectCodeowners?.(codeownersRepos?.[0] ?? selectedRepos[0])}
                          aria-label="CODEOWNERS"
                          aria-current={selectedCodeownersRepo !== null ? 'page' : undefined}
                        >
                          <span className="codeowners-repo-name">.github/CODEOWNERS</span>
                          <span className="codeowners-repo-path">{codeownersRepos.length} repo{codeownersRepos.length !== 1 ? 's' : ''}</span>
                        </button>
                      </li>
                    </ul>
                  </div>
                </div>
              )}
          </div>

        </div>
      )}
    </div>
  );
};

export default UnifiedWorkflowList;
