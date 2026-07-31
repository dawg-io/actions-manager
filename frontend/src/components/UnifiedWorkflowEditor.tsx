import React, { useState, useRef, useEffect } from 'react';
import { FileText, FilePlus2, Upload } from 'lucide-react';
import { Button } from './ui/button';
import YAMLEditor from './YAMLEditor';
import type { WorkflowDiagnostic } from './YAMLEditor';
import ValidationPanel from './ValidationPanel';
import ReusableGUIWorkflowEditor from './ReusableGUIWorkflowEditor';
import GUIWorkflowEditor from './GUIWorkflowEditor';
import VersionHistoryPanel from './VersionHistoryPanel';
import OpenInGitHubModal from './OpenInGitHubModal';
import EditableNameField from './EditableNameField';
import WorkflowStatusBadge, { WorkflowStatus } from './WorkflowStatusBadge';
import ConfirmDialog from './ConfirmDialog';
import { WorkflowGUI, guiToYaml } from '../utils/workflowGuiConversion';
import { UnifiedWorkflowItem, ProjectPRState } from '../types/workflow';
import { ActionsProject } from '../api/actionsProjects';
import { ActionGroup } from '../api/actionGroups';
import {
  normalizeWorkflowStem,
  validateWorkflowName,
} from '../utils/workflowFilename';
import { getDocsUrl } from '../help/helpLinks';

/**
 * Builds a GitHub URL pointing directly to the workflow file inside a repository.
 *
 * The filename is constructed to match what the backend's `format_workflow_name()`
 * function produces when it pushes workflows to GitHub:
 *
 *  - **Secure Mode** (`usePrefix=true`):  `AM_{PROJECT_CODE}_{name}.yml`
 *    Resources use the `AM_PROJECT_CODE_` prefix so all managed files are
 *    clearly namespaced in the repository.
 *  - **Less Secure / no-prefix Mode** (`usePrefix=false`):  `{name}.yml`
 *    (or `{name}` unchanged when the name already ends in `.yml`/`.yaml`).
 *
 * The `HEAD` ref is used so GitHub automatically resolves to the repository's
 * default branch without requiring branch information in the application state.
 *
 * @param repo          - Full repository name in `"owner/repo"` format.
 * @param workflowName  - Workflow name as stored in the database (stem, possibly
 *                        already containing an extension for some legacy entries).
 * @param projectCode   - Project code used for the prefix (e.g. `"REG1"`).
 *                        Required when `usePrefix` is `true`; ignored otherwise.
 * @param usePrefix     - When `true` (Secure Mode), the `AM_{projectCode}_` prefix
 *                        is prepended and `.yml` is appended.  Defaults to `false`.
 * @returns A GitHub blob URL for the workflow file, or `null` when inputs are
 *          invalid (bad repo format, missing project code in Secure Mode, or
 *          workflow name contains unsafe characters).
 */
function buildGithubWorkflowUrl(
  repo: string,
  workflowName: string,
  projectCode: string | null = null,
  usePrefix: boolean = false
): string | null {
  // Validate repo is in "owner/repo" format to avoid constructing invalid URLs.
  if (!repo || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo)) {
    return null;
  }

  // Validate workflowName: must not be empty and must not contain path separators
  // or path-traversal sequences.  All other characters are passed through
  // encodeURIComponent so names with spaces, dashes, etc. still produce valid URLs.
  if (!workflowName) {
    return null;
  }
  if (workflowName.includes('/') || workflowName.includes('\\') || workflowName.includes('..')) {
    return null;
  }

  let fileName: string;
  if (usePrefix) {
    // Secure Mode: mirror the server-side format_workflow_name() logic.
    // Requires a non-empty project code — return null rather than silently
    // producing an incorrect no-prefix URL.
    if (!projectCode) {
      return null;
    }
    // Strip any existing .yml/.yaml suffix before applying the AM_ prefix so that
    // a name stored as "build.yml" doesn't become "AM_CODE_build.yml.yml".
    const stem = workflowName.replace(/\.(yml|yaml)$/i, '');
    fileName = `AM_${projectCode.toUpperCase()}_${stem}.yml`;
  } else {
    // Less Secure / no-prefix Mode (also used for linked workflows whose names
    // belong to a separate RWX project and must not carry the current prefix).
    // Add .yml only when the name doesn't already carry an extension so that
    // names like "rtx-1.yml" stored with their extension don't become "rtx-1.yml.yml".
    if (workflowName.endsWith('.yml') || workflowName.endsWith('.yaml')) {
      fileName = workflowName;
    } else {
      fileName = `${workflowName}.yml`;
    }
  }

  return `https://github.com/${repo}/blob/HEAD/.github/workflows/${encodeURIComponent(fileName)}`;
}

/**
 * Builds a GitHub URL pointing to a repository.
 *
 * @param repo - Full repository name in `"owner/repo"` format.
 * @returns A GitHub repository URL, or `null` when repo format is invalid.
 */
function buildGithubRepoUrl(repo: string): string | null {
  // Validate repo is in "owner/repo" format
  if (!repo || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo)) {
    return null;
  }
  return `https://github.com/${repo}`;
}

interface UnifiedWorkflowEditorProps {
  selectedWorkflow: UnifiedWorkflowItem | null | undefined;
  editMode: 'yaml' | 'gui';
  regularGuiWorkflow: WorkflowGUI;
  guiWorkflow: WorkflowGUI;
  projectCode: string | null;
  projectPRState?: ProjectPRState;
  usePrefix?: boolean;
  isReadOnly?: boolean;
  user: string;
  projectName: string;
  /** Repositories linked to this project (format: "owner/repo"). Used for "Open in GitHub" links. */
  selectedRepos?: string[];
  importedActions: ActionsProject[];
  actionGroups: ActionGroup[];
  setEditMode: (mode: 'yaml' | 'gui') => void;
  setRegularGuiWorkflow: (workflow: WorkflowGUI) => void;
  setGuiWorkflow: (workflow: WorkflowGUI) => void;
  handleWorkflowChange: (field: string, value: string) => void;
  saveDraftWorkflow: (index: number | null, type: 'regular' | 'reusable') => void;
  /** Draft save for linked reusable workflows – persists content to the RWX project DB. */
  saveDraftLinkedWorkflow?: (index: number) => Promise<void>;
  commitAndUpdatePR?: (index: number | null, type: 'regular' | 'reusable') => Promise<boolean>;
  /** Separate callback for linked reusable workflows – routes save to RWX project. */
  commitAndUpdatePRLinked?: (index: number) => Promise<boolean>;
  deleteWorkflow: (index: number, type: 'regular' | 'reusable') => void;
  /** Unlink a linked reusable workflow from this project (removes association only). */
  unlinkWorkflow?: (workflowId: number) => Promise<void>;
  /** Opens the workflow-creation dialog — surfaced in the empty state when nothing is selected. */
  addWorkflowFn?: () => void;
  /** Opens the existing-workflow import panel — surfaced in the empty state when nothing is selected. */
  onImportExisting?: () => void;
}

interface WorkflowEditorHeaderProps {
  selectedWorkflow: UnifiedWorkflowItem;
  projectCode: string | null;
  editMode: 'yaml' | 'gui';
  projectPRState?: ProjectPRState;
  usePrefix?: boolean;
  isReadOnly?: boolean;
  isUnlockedPR?: boolean;
  /** When true the workflow is soft-locked (under_review, not yet unlocked) — hides the save button */
  isLocked?: boolean;
  /** Repositories linked to this project (format: "owner/repo"). Used for "Open in GitHub" links. */
  selectedRepos?: string[];
  handleWorkflowChange: (field: string, value: string) => void;
  saveDraftWorkflow: (index: number | null, type: 'regular' | 'reusable') => void;
  /** Draft save for linked reusable workflows – persists content to the RWX project DB. */
  onSaveDraftLinked?: () => void;
  onCommitAndUpdatePR?: () => void;
  deleteWorkflow: (index: number, type: 'regular' | 'reusable') => void;
  onRequestDelete?: (index: number, type: 'regular' | 'reusable', name: string) => void;
  /** Called when user confirms unlinking a linked reusable workflow. */
  onUnlinkWorkflow?: (workflowId: number) => void;
  setEditMode: (mode: 'yaml' | 'gui') => void;
  onShowVersionHistory: () => void;
}

interface WorkflowEditorContentProps {
  selectedWorkflow: UnifiedWorkflowItem;
  editMode: 'yaml' | 'gui';
  disableEditing?: boolean;
  regularGuiWorkflow: WorkflowGUI;
  guiWorkflow: WorkflowGUI;
  handleWorkflowChange: (field: string, value: string) => void;
  setRegularGuiWorkflow: (workflow: WorkflowGUI) => void;
  setGuiWorkflow: (workflow: WorkflowGUI) => void;
  importedActions: ActionsProject[];
  actionGroups: ActionGroup[];
}

const WorkflowEditorHeader: React.FC<WorkflowEditorHeaderProps> = ({
  selectedWorkflow,
  projectCode,
  editMode,
  projectPRState = "new",
  usePrefix = true,
  isReadOnly = false,
  isUnlockedPR = false,
  isLocked = false,
  selectedRepos = [],
  handleWorkflowChange,
  saveDraftWorkflow,
  onSaveDraftLinked,
  onCommitAndUpdatePR,
  deleteWorkflow,
  onRequestDelete,
  onUnlinkWorkflow,
  setEditMode,
  onShowVersionHistory
}) => {
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const [githubModalOpen, setGithubModalOpen] = useState(false);
  const moreMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (moreMenuRef.current && !moreMenuRef.current.contains(event.target as Node)) {
        setMoreMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Close More menu on Escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && moreMenuOpen) {
        setMoreMenuOpen(false);
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [moreMenuOpen]);

  // Close More menu whenever the selected workflow changes
  useEffect(() => {
    setMoreMenuOpen(false);
  }, [selectedWorkflow?.id]);

  const workflowType = selectedWorkflow.type;
  const isReusable = workflowType === 'reusable';
  const isLinked = workflowType === 'linked';
  // Safe: only used inside !isLinked blocks where type is guaranteed regular or reusable
  const editableType: 'regular' | 'reusable' = isReusable ? 'reusable' : 'regular';
  const placeholder = isReusable || isLinked ? "Enter reusable workflow name" : "Enter workflow name";
  const badge = isLinked ? "Linked Workflow" : isReusable ? "Reusable Workflow" : "Regular Workflow";
  const badgeClass = isLinked ? "linked" : isReusable ? "reusable" : "regular";

  // Determine workflow state badge.
  //
  // The badge MUST be derived purely from the per-workflow state
  // (`selectedWorkflow.workflowStatus` + `selectedWorkflow.isModified`).  It must
  // NOT fall back to the project-wide `projectPRState`, because that value is
  // shared across every workflow in the project; using it here causes editing or
  // committing one workflow to incorrectly relabel every other workflow as
  // "Draft" / "Synced" (see issue: "Editing One Synced Workflow Incorrectly
  // Marks All Workflows as Draft").
  const getWorkflowStateBadge = (): { text: string; status: WorkflowStatus } | null => {
    const status = selectedWorkflow.workflowStatus;

    // 1. Workflow has an open PR — locked state takes precedence.
    if (status === 'under_review') {
      return { text: 'Under Review', status: 'under_review' };
    }
    // 2. Any unsaved editor edits — covers both "new and not saved" and
    //    "existing edited but not yet committed locally".
    if (selectedWorkflow.isModified) {
      return { text: 'Unsaved', status: 'unsaved' };
    }
    // 3. New workflow committed locally but not in GitHub yet.
    if (status === 'new') {
      return { text: 'New Local', status: 'new' };
    }
    // 4. Existing workflow committed locally, not pushed via PR/merge.
    if (status === 'committed_locally') {
      return { text: 'Draft', status: 'committed_locally' };
    }
    // 5. Workflow matches GitHub.
    if (status === 'synced_with_github') {
      return { text: 'Synced', status: 'synced_with_github' };
    }
    return null;
  };

  const stateBadge = getWorkflowStateBadge();

  // Determine primary action button
  const getPrimaryAction = (): { text: string; onClick: () => void; disabled: boolean; title: string; className: string } | null => {
    if (isReadOnly) {
      return {
        text: '💾 Commit Locally',
        onClick: () => {},
        disabled: true,
        title: "You have read-only access to this project",
        className: 'btn btn-primary'
      };
    }

    if (isUnlockedPR && onCommitAndUpdatePR) {
      return {
        text: '🔄 Commit and Update PR',
        onClick: onCommitAndUpdatePR,
        disabled: !selectedWorkflow.name || !selectedWorkflow.content,
        title: "Commit changes and update the existing open pull request",
        className: 'btn btn-pr-update'
      };
    }

    if (isLocked) {
      return {
        text: '🔒 Unlock to Commit',
        onClick: () => {},
        disabled: true,
        title: "Unlock the workflow below to commit changes",
        className: 'btn btn-primary'
      };
    }

    if (isLinked && onSaveDraftLinked) {
      return {
        text: '💾 Save to RWX Project',
        onClick: onSaveDraftLinked,
        disabled: !selectedWorkflow.content,
        title: `Save changes to the source RWX project '${selectedWorkflow.rwxProjectName || ''}'`,
        className: 'btn btn-primary'
      };
    }

    if (!isLinked) {
      const saveButtonText = projectPRState === "open" ? "💾 Commit Locally (Update PR)" : "💾 Commit Locally";
      const saveButtonTitle = projectPRState === "open"
        ? "Commit this workflow to local database (will update open PRs when pushed to GitHub)"
        : "Commit this workflow to local database";

      return {
        text: saveButtonText,
        onClick: () => {
          saveDraftWorkflow(selectedWorkflow.originalIndex, editableType);
        },
        disabled: !selectedWorkflow.name || !selectedWorkflow.content,
        title: saveButtonTitle,
        className: 'btn btn-primary'
      };
    }

    return null;
  };

  const primaryAction = getPrimaryAction();
  const readOnlyTooltip = "You have read-only access to this project";

  const securePrefix =
    !isLinked && usePrefix && projectCode ? `AM_${projectCode.toUpperCase()}_` : '';

  // The editable input always exposes only the workflow stem.  The `.yml`
  // suffix is rendered as a locked, non-editable segment to the right of the
  // input in both prefix and no-prefix modes so the two UIs share the same
  // visual pattern.  In prefix mode the project-managed `AM_{code}_` prefix
  // is additionally rendered as a locked segment to the left of the input.
  // For linked workflows (whose names belong to a different RWX project) the
  // input is disabled below; we still strip the extension so the suffix chip
  // and read-only display continue to render the canonical name.
  const editableNameValue = normalizeWorkflowStem(selectedWorkflow.name || '');

  const editableNamePrefix = securePrefix || undefined;
  const editableNameSuffix = '.yml';

  // Full canonical filename used for display in non-edit contexts (e.g. the
  // "Open in GitHub" modal).  Re-applies the locked prefix (when in prefix
  // mode) and the `.yml` suffix that surround the editable input.
  const displayedWorkflowFilename = `${securePrefix}${editableNameValue}.yml`;

  const validateWorkflowFilenameDraft = (draftValue: string) => {
    const trimmed = (draftValue ?? '').trim();
    if (!trimmed) return 'Workflow name cannot be empty.';

    // In prefix mode the input only contains the editable suffix.  Reject any
    // attempt to re-include the project-managed prefix to avoid producing
    // duplicated prefixes like `AM_CODE_AM_CODE_name.yml` after concatenation.
    // Use case-insensitive comparison to match the backend's case-insensitive strip.
    if (securePrefix && trimmed.toLowerCase().startsWith(securePrefix.toLowerCase())) {
      return 'Do not include the project prefix; it is added automatically.';
    }

    return validateWorkflowName(trimmed);
  };

  // Helper functions for GitHub URLs
  const githubRepos = isLinked
    ? (selectedWorkflow.rwxRepo ? [selectedWorkflow.rwxRepo] : [])
    : selectedRepos.filter(r => r?.includes('/'));

  const workflowFileName = selectedWorkflow.name || '';
  const applyPrefix = !isLinked && !!usePrefix;

  const buildWorkflowUrlForRepo = (repo: string) => {
    return buildGithubWorkflowUrl(repo, workflowFileName, projectCode, applyPrefix);
  };

  const buildRepoUrlForRepo = (repo: string) => {
    return buildGithubRepoUrl(repo);
  };

  return (
    <>
      <div className="workflow-editor-header-new">
        {/* Top Row */}
        <div className="workflow-toolbar-top">
          {/* Left side: filename, type badge, state badge */}
          <div className="workflow-identity">
            <EditableNameField
              value={editableNameValue}
              prefix={editableNamePrefix}
              suffix={editableNameSuffix}
              onSave={(newValue) => {
                // In prefix mode the value already excludes the locked prefix
                // and ".yml" suffix; in no-prefix mode the user may have typed
                // the extension, which normalizeWorkflowStem strips.
                handleWorkflowChange('name', normalizeWorkflowStem(newValue));
              }}
              validate={validateWorkflowFilenameDraft}
              ariaLabel="workflow filename"
              inputId="workflow-filename"
              placeholder={placeholder}
              disabled={isLinked || isReadOnly || isLocked}
              className="workflow-filename-input"
              displayClassName="text-lg font-medium"
              inputClassName="workflow-filename-rename-input"
            />
            <span className={`workflow-type-badge-new ${badgeClass}`}>{badge}</span>
            {isLinked && selectedWorkflow.rwxProjectName && (
              <span className="workflow-linked-source">
                from <strong>{selectedWorkflow.rwxProjectName}</strong>
              </span>
            )}
            {stateBadge && (
              <WorkflowStatusBadge
                status={stateBadge.status}
                label={stateBadge.text}
                data-testid="workflow-status-badge"
              />
            )}
          </div>

          {/* Right side: primary action, More dropdown */}
          <div className="workflow-primary-actions">
            {primaryAction && (
              <button
                className={primaryAction.className}
                onClick={primaryAction.onClick}
                disabled={primaryAction.disabled}
                title={primaryAction.title}
                data-testid={isUnlockedPR ? "update-pr-button" : undefined}
              >
                {primaryAction.text}
              </button>
            )}

            {!isLinked && (
              <div className="more-menu-dropdown" ref={moreMenuRef}>
                <button
                  className="btn btn-secondary"
                  onClick={() => !isReadOnly && setMoreMenuOpen(prev => !prev)}
                  disabled={isReadOnly}
                  title={isReadOnly ? readOnlyTooltip : "More options"}
                  aria-haspopup="true"
                  aria-expanded={moreMenuOpen}
                  aria-label="More options"
                >
                  More ▾
                </button>
                {moreMenuOpen && (
                  <div className="more-menu-content" role="menu">
                    <button
                      className="more-menu-item"
                      role="menuitem"
                      onClick={() => { setGithubModalOpen(true); setMoreMenuOpen(false); }}
                      disabled={githubRepos.length === 0}
                      title={githubRepos.length === 0 ? "No repositories available" : "Open this workflow in GitHub"}
                    >
                      ⤴ Open in GitHub
                    </button>
                    <button
                      className="more-menu-item"
                      role="menuitem"
                      onClick={() => { onShowVersionHistory(); setMoreMenuOpen(false); }}
                      title="View version history for this workflow"
                    >
                      📜 History
                    </button>
                    <button
                      className="more-menu-item"
                      role="menuitem"
                      disabled
                      title="Duplicate workflow — coming soon"
                    >
                      📋 Duplicate workflow
                    </button>
                    <button
                      className="more-menu-item"
                      role="menuitem"
                      disabled
                      title="Rename workflow — coming soon"
                    >
                      ✏️ Rename workflow
                    </button>
                    <hr className="more-menu-divider" />
                    <button
                      className="more-menu-item more-menu-item--danger"
                      role="menuitem"
                      onClick={() => { 
                        if (onRequestDelete) {
                          onRequestDelete(selectedWorkflow.originalIndex, editableType, selectedWorkflow.name);
                        } else {
                          deleteWorkflow(selectedWorkflow.originalIndex, editableType);
                        }
                        setMoreMenuOpen(false); 
                      }}
                      title="Delete this workflow"
                    >
                      🗑️ Delete workflow
                    </button>
                  </div>
                )}
              </div>
            )}

            {isLinked && onUnlinkWorkflow && (
              <div className="more-menu-dropdown" ref={moreMenuRef}>
                <button
                  className="btn btn-secondary"
                  onClick={() => !isReadOnly && setMoreMenuOpen(prev => !prev)}
                  disabled={isReadOnly}
                  title={isReadOnly ? readOnlyTooltip : "More options"}
                  aria-haspopup="true"
                  aria-expanded={moreMenuOpen}
                  aria-label="More options"
                  data-testid="linked-workflow-more-button"
                >
                  More ▾
                </button>
                {moreMenuOpen && (
                  <div className="more-menu-content" role="menu">
                    {selectedWorkflow.rwxRepo && (
                      <button
                        className="more-menu-item"
                        role="menuitem"
                        onClick={() => { setGithubModalOpen(true); setMoreMenuOpen(false); }}
                        title="Open this workflow in GitHub"
                      >
                        ⤴ Open in GitHub
                      </button>
                    )}
                    <hr className="more-menu-divider" />
                    <button
                      className="more-menu-item more-menu-item--danger"
                      role="menuitem"
                      onClick={() => {
                        const workflowId = Number.parseInt(selectedWorkflow.id.replace('linked-', ''), 10);
                        onUnlinkWorkflow(workflowId);
                        setMoreMenuOpen(false);
                      }}
                      title="Remove this linked workflow from the project"
                      data-testid="unlink-workflow-button"
                    >
                      🔗✂ Unlink Workflow
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Second Row: Status/Context */}
        <div className="workflow-toolbar-status">
          {/* Repository context */}
          {selectedRepos.length > 0 && (
            <div className="status-item">
              <span className="status-label">Repos:</span>
              <span className="status-value">{selectedRepos.join(', ')}</span>
            </div>
          )}
          {isLinked && selectedWorkflow.rwxRepo && (
            <div className="status-item">
              <span className="status-label">Repo:</span>
              <span className="status-value">{selectedWorkflow.rwxRepo}</span>
            </div>
          )}

          {/* Drift/sync status — derived from workflow state */}
          {stateBadge?.text === 'Synced' && (
            <div className="status-item">
              <span className="status-value">No drift detected</span>
            </div>
          )}

          {/* Editor mode toggle */}
          {!isLinked && (
            <div className="editor-mode-selector">
              <span className="mode-label">Editor:</span>
              <button
                className={`mode-btn ${editMode === 'yaml' ? 'mode-btn-active' : ''}`}
                onClick={() => setEditMode('yaml')}
                disabled={isReadOnly || isLocked}
                title={isReadOnly ? readOnlyTooltip : 'YAML editor'}
              >
                YAML
              </button>
              <span className="mode-separator">|</span>
              <button
                className={`mode-btn ${editMode === 'gui' ? 'mode-btn-active' : ''}`}
                onClick={() => setEditMode('gui')}
                disabled={isReadOnly || isLocked}
                title={isReadOnly ? readOnlyTooltip : 'GUI editor'}
              >
                GUI
              </button>
            </div>
          )}

          {/* Docs link */}
          <a
            className="docs-help-link"
            href={getDocsUrl("workflows")}
            rel="noreferrer"
            target="_blank"
            title="Open workflow editor documentation"
          >
            Help
          </a>
        </div>
      </div>

      {/* Open in GitHub Modal */}
      <OpenInGitHubModal
        isOpen={githubModalOpen}
        onClose={() => setGithubModalOpen(false)}
        workflowName={displayedWorkflowFilename}
        repositories={githubRepos}
        buildWorkflowUrl={buildWorkflowUrlForRepo}
        buildRepoUrl={buildRepoUrlForRepo}
      />
    </>
  );
};

const WorkflowEditorContent: React.FC<WorkflowEditorContentProps> = ({
  selectedWorkflow,
  editMode,
  disableEditing = false,
  regularGuiWorkflow,
  guiWorkflow,
  handleWorkflowChange,
  setRegularGuiWorkflow,
  setGuiWorkflow,
  importedActions,
  actionGroups
}) => {
  const [yamlDiagnostics, setYamlDiagnostics] = useState<WorkflowDiagnostic[]>([]);
  const isRegular = selectedWorkflow.type === 'regular';
  const isLinked = selectedWorkflow.type === 'linked';
  const yamlPlaceholder = isRegular 
    ? "# GitHub Actions workflow YAML content"
    : "# Reusable workflow YAML content";

  useEffect(() => {
    setYamlDiagnostics([]);
  }, [selectedWorkflow.id]);

  if (editMode === 'yaml' || isLinked || disableEditing) {
    return (
      <>
        <YAMLEditor
          key={selectedWorkflow.id}
          value={selectedWorkflow.content || ''}
          onChange={(value: string) => {
            if (!disableEditing) {
              handleWorkflowChange('content', value);
            }
          }}
          onStructuralDiagnostics={setYamlDiagnostics}
          placeholder={yamlPlaceholder}
          readOnly={disableEditing}
        />
        <ValidationPanel diagnostics={yamlDiagnostics} />
      </>
    );
  }

  const handleGUIChange = (newWorkflow: WorkflowGUI) => {
    // Always update the GUI workflow state
    if (isRegular) {
      setRegularGuiWorkflow(newWorkflow);
    } else {
      setGuiWorkflow(newWorkflow);
    }

    // Sync name changes from GUI editor to workflow state
    // But only if the new name is not empty and different from current
    // This prevents erasing the name if GUI state gets reset to default
    if (newWorkflow.name && newWorkflow.name !== selectedWorkflow.name) {
      handleWorkflowChange('name', newWorkflow.name);
    }

    try {
      const yamlContent = guiToYaml(newWorkflow);
      handleWorkflowChange('content', yamlContent);
    } catch (error) {
      console.error('Failed to convert GUI to YAML:', error);
    }
  };

  return isRegular ? (
    <GUIWorkflowEditor
      key={selectedWorkflow.id}
      workflow={regularGuiWorkflow}
      onChange={handleGUIChange}
      importedActions={importedActions}
      actionGroups={actionGroups}
    />
  ) : (
    <ReusableGUIWorkflowEditor
      key={selectedWorkflow.id}
      workflow={guiWorkflow}
      onChange={handleGUIChange}
      importedActions={importedActions}
      actionGroups={actionGroups}
    />
  );
};

const UnifiedWorkflowEditor: React.FC<UnifiedWorkflowEditorProps> = ({
  selectedWorkflow,
  editMode,
  regularGuiWorkflow,
  guiWorkflow,
  projectCode,
  projectPRState = "new",
  usePrefix = true,
  isReadOnly = false,
  user,
  projectName,
  selectedRepos = [],
  importedActions,
  actionGroups,
  setEditMode,
  setRegularGuiWorkflow,
  setGuiWorkflow,
  handleWorkflowChange,
  saveDraftWorkflow,
  saveDraftLinkedWorkflow,
  commitAndUpdatePR,
  commitAndUpdatePRLinked,
  deleteWorkflow,
  unlinkWorkflow,
  addWorkflowFn,
  onImportExisting
}) => {
  const [showVersionHistory, setShowVersionHistory] = useState(false);
  const [isUnlocked, setIsUnlocked] = useState(false);
  const [showUnlockModal, setShowUnlockModal] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<{ index: number; type: 'regular' | 'reusable'; name: string } | null>(null);
  const [pendingUnlink, setPendingUnlink] = useState<{ workflowId: number; name: string } | null>(null);

  // Reset lock state whenever the selected workflow changes
  useEffect(() => {
    setIsUnlocked(false);
    setShowUnlockModal(false);
  }, [selectedWorkflow?.id]);

  const handleShowVersionHistory = () => {
    setShowVersionHistory(true);
  };

  const handleCloseVersionHistory = () => {
    setShowVersionHistory(false);
  };

  const handleRestoreVersion = (content: string) => {
    handleWorkflowChange('content', content);
    setShowVersionHistory(false);
  };

  // Wrapper for commit-and-update-PR: re-locks on success, stays unlocked on failure.
  // Linked workflows use a separate code path (commitAndUpdatePRLinked) so that:
  //   - the save step targets the RWX project (not the standard project)
  //   - the index refers to the linkedWorkflows array, not workflows/rxworkflows
  const handleCommitAndUpdatePR = async () => {
    if (!selectedWorkflow) return;
    let success = false;
    if (selectedWorkflow.type === 'linked' && commitAndUpdatePRLinked) {
      success = await commitAndUpdatePRLinked(selectedWorkflow.originalIndex);
    } else if (commitAndUpdatePR) {
      const editableType: 'regular' | 'reusable' =
        selectedWorkflow.type === 'reusable' ? 'reusable' : 'regular';
      success = await commitAndUpdatePR(selectedWorkflow.originalIndex, editableType);
    }
    if (success) {
      setIsUnlocked(false);
    }
  };

  // Memoized handler so WorkflowEditorHeader doesn't re-render on every render of the parent
  const handleSaveDraftLinked = React.useCallback(() => {
    if (saveDraftLinkedWorkflow && selectedWorkflow?.type === 'linked') {
      saveDraftLinkedWorkflow(selectedWorkflow.originalIndex);
    }
  }, [saveDraftLinkedWorkflow, selectedWorkflow?.type, selectedWorkflow?.originalIndex]);

  const hasSaveDraftLinked =
    !!saveDraftLinkedWorkflow && selectedWorkflow?.type === 'linked';

  const hasCommitAction =
    selectedWorkflow?.type === 'linked' ? !!commitAndUpdatePRLinked : !!commitAndUpdatePR;

  if (!selectedWorkflow) {
    return (
      <div className="unified-workflows-editor unified-workflows-empty-state">
        <div className="empty-state-card">
          <FileText className="empty-state-icon" aria-hidden="true" />
          <h3>Select a project file</h3>
          <p>Choose a workflow or file from the panel on the left to begin editing.</p>
          {(addWorkflowFn || onImportExisting) && (
            <div className="empty-state-actions">
              {!isReadOnly && addWorkflowFn && (
                <Button onClick={addWorkflowFn}>
                  <FilePlus2 className="h-4 w-4" aria-hidden="true" />
                  Add Workflow
                </Button>
              )}
              {onImportExisting && (
                <Button variant="outline" onClick={onImportExisting}>
                  <Upload className="h-4 w-4" aria-hidden="true" />
                  Import Existing
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  const workflowClass = selectedWorkflow.type === 'regular' 
    ? 'regular-workflow-editor' 
    : selectedWorkflow.type === 'linked'
      ? 'linked-workflow-editor'
      : 'reusable-workflow-editor';

  const showLockOverlay = selectedWorkflow?.workflowStatus === 'under_review' && !isUnlocked;
  const isUnlockedPR = isUnlocked && selectedWorkflow?.workflowStatus === 'under_review';

  return (
    <div className="unified-workflows-editor">
      <div className={workflowClass}>
        <WorkflowEditorHeader
          selectedWorkflow={selectedWorkflow}
          projectCode={projectCode}
          editMode={editMode}
          projectPRState={projectPRState}
          usePrefix={usePrefix}
          isReadOnly={isReadOnly}
          isUnlockedPR={isUnlockedPR}
          isLocked={showLockOverlay}
          selectedRepos={selectedRepos}
          handleWorkflowChange={handleWorkflowChange}
          saveDraftWorkflow={saveDraftWorkflow}
          onSaveDraftLinked={hasSaveDraftLinked ? handleSaveDraftLinked : undefined}
          onCommitAndUpdatePR={hasCommitAction ? handleCommitAndUpdatePR : undefined}
          deleteWorkflow={deleteWorkflow}
          onRequestDelete={(idx, type, name) => setPendingDelete({ index: idx, type, name })}
          onUnlinkWorkflow={unlinkWorkflow ? (workflowId) => setPendingUnlink({ workflowId, name: selectedWorkflow.name }) : undefined}
          setEditMode={setEditMode}
          onShowVersionHistory={handleShowVersionHistory}
        />
        <div className="workflow-editor-content workflow-editor-content--lockable">
          <WorkflowEditorContent
            selectedWorkflow={selectedWorkflow}
            editMode={editMode}
            disableEditing={isReadOnly || showLockOverlay}
            regularGuiWorkflow={regularGuiWorkflow}
            guiWorkflow={guiWorkflow}
            handleWorkflowChange={handleWorkflowChange}
            setRegularGuiWorkflow={setRegularGuiWorkflow}
            setGuiWorkflow={setGuiWorkflow}
            importedActions={importedActions}
            actionGroups={actionGroups}
          />
          {showLockOverlay && (
            <div className="workflow-lock-overlay" data-testid="workflow-lock-overlay">
              <button
                className="workflow-lock-btn"
                onClick={() => setShowUnlockModal(true)}
                title="This workflow has an open pull request. Click to unlock editing."
                data-testid="unlock-workflow-button"
              >
                <span className="workflow-lock-icon">🔒</span>
                <span className="workflow-lock-label">Unlock to Edit</span>
              </button>
            </div>
          )}
          {isReadOnly && !showLockOverlay && (
            <div className="workflow-lock-overlay">
              <div className="workflow-lock-btn workflow-lock-btn-static" role="status" aria-live="polite" tabIndex={0}>
                <span className="workflow-lock-icon">🔒</span>
                <span className="workflow-lock-label workflow-lock-label-strong">Read Only Mode</span>
                <span className="workflow-lock-label">You can view workflows but cannot make changes.</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {showVersionHistory && selectedWorkflow.name && (
        <VersionHistoryPanel
          user={user}
          projectName={projectName}
          workflowName={selectedWorkflow.name}
          currentContent={selectedWorkflow.content || ''}
          onClose={handleCloseVersionHistory}
          onRestore={handleRestoreVersion}
        />
      )}

      {showUnlockModal && (
        <div
          className="workflow-lock-modal-backdrop"
          onClick={(e) => { if (e.target === e.currentTarget) setShowUnlockModal(false); }}
        >
          <div className="workflow-lock-modal">
            <div className="workflow-lock-modal-header">
              <span className="workflow-lock-modal-icon">🔒</span>
              <h3 className="workflow-lock-modal-title">Open Pull Request Detected</h3>
            </div>
            <p className="workflow-lock-modal-body">
              This workflow already has an open pull request. If you continue editing, your changes will be added to the existing pull request instead of creating a separate one.
            </p>
            <div className="workflow-lock-modal-actions">
              <button
                className="btn btn-secondary"
                onClick={() => setShowUnlockModal(false)}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={() => { setIsUnlocked(true); setShowUnlockModal(false); }}
              >
                Unlock and Edit
              </button>
            </div>
          </div>
        </div>
      )}

      {pendingDelete && (
        <ConfirmDialog
          open={true}
          title={`Delete workflow "${pendingDelete.name}"?`}
          description="This will remove the workflow from your project and all GitHub repositories. This action cannot be undone."
          confirmLabel="Delete workflow"
          destructive
          onConfirm={() => { deleteWorkflow(pendingDelete.index, pendingDelete.type); setPendingDelete(null); }}
          onCancel={() => setPendingDelete(null)}
        />
      )}

      {pendingUnlink && (
        <ConfirmDialog
          open={true}
          title={`Unlink workflow "${pendingUnlink.name}"?`}
          description="This will remove the linked reusable workflow from this project only. The source reusable workflow will not be deleted and no GitHub files will be modified."
          confirmLabel="Unlink Workflow"
          destructive
          onConfirm={() => { if (unlinkWorkflow) { unlinkWorkflow(pendingUnlink.workflowId); } setPendingUnlink(null); }}
          onCancel={() => setPendingUnlink(null)}
        />
      )}
    </div>
  );
};

export default UnifiedWorkflowEditor;
