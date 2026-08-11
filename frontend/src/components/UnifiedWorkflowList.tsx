/* eslint-disable no-restricted-syntax -- Legacy: TODO migrate inline styles to Tailwind CSS classes */
import React from 'react';
import { ChevronDown, ChevronLeft, ChevronRight, Plus } from 'lucide-react';
import { UnifiedWorkflowItem } from '../types/workflow';
import { normalizeWorkflowFilename } from '../utils/workflowFilename';
import { CustomFile } from '../api/customFiles';
import {
  PANEL_DEFAULT_WIDTH,
  PANEL_MAX_WIDTH,
  PANEL_MIN_WIDTH,
  PROJECT_FILES_CLOSED_SECTIONS_KEY,
  PROJECT_FILES_WIDTH_KEY,
  clampPanelWidth,
  readStoredClosedSections,
  readStoredPanelWidth,
  writeStoredPreference,
} from '../utils/projectFilesPanelPrefs';

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
  /** Set of workflow names currently drifted on GitHub (renders a small warning icon). */
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

/** Stable ids so a section's open/closed state survives a reload. */
const SECTION_WORKFLOWS = 'workflows';
const SECTION_REUSABLE = 'reusable';
const SECTION_LINKED = 'linked';
const SECTION_CUSTOM = 'custom';
const SECTION_CODEOWNERS = 'codeowners';

const SECTION_ICONS: Record<string, string> = {
  [SECTION_WORKFLOWS]: '📝',
  [SECTION_REUSABLE]: '🔄',
  [SECTION_LINKED]: '🔗',
  [SECTION_CUSTOM]: '📄',
  [SECTION_CODEOWNERS]: '👥',
};

/** Distinct per row kind — the icon is the only type signal a one-line row has. */
const ROW_ICONS: Record<UnifiedWorkflowItem['type'] | 'custom', string> = {
  regular: '📄',
  reusable: '🔄',
  linked: '🔗',
  custom: '📎',
};

const SECTION_LABELS: Record<string, string> = {
  [SECTION_WORKFLOWS]: 'Workflows',
  [SECTION_REUSABLE]: 'Reusable Workflows',
  [SECTION_LINKED]: 'Linked Workflows',
  [SECTION_CUSTOM]: 'Custom Files',
  [SECTION_CODEOWNERS]: 'CODEOWNERS',
};

const getWorkflowStatusDisplay = (status?: string) => {
  if (!status) return null;
  return WORKFLOW_STATUS_LABELS[status] || null;
};

const UNSAVED_LABEL = 'Unsaved changes';

const getRowStatus = (status: string | undefined, isModified?: boolean) => {
  const statusDisplay = getWorkflowStatusDisplay(status);
  if (statusDisplay) return statusDisplay;
  if (isModified) return { label: UNSAVED_LABEL, className: 'status-unsaved' };
  return { label: 'No status', className: 'status-none' };
};

const getWorkflowDisplayFilename = (workflow: UnifiedWorkflowItem, fallbackLabel: string) =>
  workflow.name ? normalizeWorkflowFilename(workflow.name) : fallbackLabel;

/**
 * The row's state, in words. Shared by the tooltip and the accessible name so the
 * two can never drift apart. `modified` is skipped when the status already says
 * "Unsaved changes", which is what getRowStatus reports for an unsaved draft.
 */
const buildStateParts = ({
  typeLabel = null,
  status,
  drifted = false,
  modified = false,
  pendingDelete = false,
}: {
  typeLabel?: string | null;
  status: string;
  drifted?: boolean;
  modified?: boolean;
  pendingDelete?: boolean;
}): string[] =>
  [
    typeLabel,
    status,
    drifted ? 'Drift detected' : null,
    pendingDelete ? 'Pending Deletion' : null,
    modified && status !== UNSAVED_LABEL ? UNSAVED_LABEL : null,
  ].filter(Boolean) as string[];

interface FileRowProps {
  icon: string;
  name: string;
  /** Full tooltip text — carries the detail the compact row no longer shows. */
  title: string;
  ariaLabel: string;
  /** Secondary inline text, e.g. the source project of a linked workflow. */
  meta?: string;
  statusLabel: string;
  statusClassName: string;
  selected: boolean;
  onSelect: () => void;
  drifted?: boolean;
  modified?: boolean;
  pendingDelete?: boolean;
  testId?: string;
}

/** Single-line, IDE-style row: icon, filename, indicators, status dot. */
const FileRow: React.FC<FileRowProps> = ({
  icon,
  name,
  title,
  ariaLabel,
  meta,
  statusLabel,
  statusClassName,
  selected,
  onSelect,
  drifted,
  modified,
  pendingDelete,
  testId,
}) => (
  <li>
    <button
      type="button"
      className={`pf-row ${selected ? 'selected' : ''}`}
      onClick={onSelect}
      title={title}
      aria-label={ariaLabel}
      aria-current={selected ? 'page' : undefined}
      data-testid={testId}
    >
      <span className="pf-row-icon" aria-hidden="true">{icon}</span>
      <span className="pf-row-name">{name}</span>
      {meta && <span className="pf-row-meta">{meta}</span>}
      {drifted && (
        <span className="pf-row-drift" data-testid="drift-badge" title="Drift detected">
          <span aria-hidden="true">⚠️</span>
        </span>
      )}
      {pendingDelete && (
        <span className="pf-row-pending-delete" title="Pending Deletion" aria-hidden="true">🗑</span>
      )}
      {modified && <span className="pf-row-modified" title="Unsaved changes" aria-hidden="true">•</span>}
      <span className={`pf-row-dot ${statusClassName}`} title={statusLabel} aria-hidden="true" />
    </button>
  </li>
);

interface PanelSectionProps {
  id: string;
  count?: number;
  closed: boolean;
  onToggle: (id: string) => void;
  children: React.ReactNode;
}

const PanelSection: React.FC<PanelSectionProps> = ({ id, count, closed, onToggle, children }) => {
  const label = SECTION_LABELS[id];
  return (
    <section className="pf-section" aria-label={label}>
      <button
        type="button"
        className="pf-section-header"
        onClick={() => onToggle(id)}
        aria-expanded={!closed}
        aria-controls={`pf-section-body-${id}`}
      >
        <ChevronDown className={`pf-section-chevron ${closed ? 'closed' : ''}`} aria-hidden="true" />
        <span className="pf-section-icon" aria-hidden="true">{SECTION_ICONS[id]}</span>
        <span className="pf-section-label">{label}</span>
        {count !== undefined && count > 0 && <span className="pf-section-count">{count}</span>}
      </button>
      {/* Unmounted rather than hidden so a closed section costs no DOM — the
          element itself stays so aria-controls always resolves. */}
      <div className="pf-section-body" id={`pf-section-body-${id}`} hidden={closed}>
        {!closed && children}
      </div>
    </section>
  );
};

/** Drag handle on the panel's right edge. Mouse events (not pointer) so it works in jsdom. */
const ResizeHandle: React.FC<{ width: number; onResize: (width: number) => void }> = ({ width, onResize }) => {
  const [dragOrigin, setDragOrigin] = React.useState<{ x: number; width: number } | null>(null);

  React.useEffect(() => {
    if (!dragOrigin) return;
    const onMove = (event: MouseEvent) =>
      onResize(clampPanelWidth(dragOrigin.width + event.clientX - dragOrigin.x));
    const onUp = () => setDragOrigin(null);

    document.body.classList.add('pf-resizing');
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      document.body.classList.remove('pf-resizing');
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [dragOrigin, onResize]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'ArrowLeft') onResize(clampPanelWidth(width - 16));
    else if (event.key === 'ArrowRight') onResize(clampPanelWidth(width + 16));
    else if (event.key === 'Home') onResize(PANEL_MIN_WIDTH);
    else if (event.key === 'End') onResize(PANEL_MAX_WIDTH);
    else if (event.key === 'Enter' || event.key === ' ') onResize(PANEL_DEFAULT_WIDTH);
    else return;
    event.preventDefault();
  };

  // The ARIA window-splitter pattern (role="separator" + tabindex + aria-valuenow)
  // would be the closer semantic fit, but SonarQube's prefer-tag-over-role rule
  // rejects that role outside a decorative <hr>. A button is the honest
  // alternative: natively focusable and activatable, so no tabIndex is needed.
  // The name stays constant — putting the live width in it would make assistive
  // tech re-announce on every drag frame — and the width rides in the title.
  return (
    <button
      type="button"
      className="pf-resize-handle"
      aria-label="Resize Project Files panel"
      title={`Resize Project Files panel (${width}px). Drag, or use arrow keys.`}
      onDoubleClick={() => onResize(PANEL_DEFAULT_WIDTH)}
      onMouseDown={(event) => {
        event.preventDefault();
        setDragOrigin({ x: event.clientX, width });
      }}
      onKeyDown={handleKeyDown}
    />
  );
};

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
  const [panelWidth, setPanelWidth] = React.useState(readStoredPanelWidth);
  const [closedSections, setClosedSections] = React.useState<Set<string>>(readStoredClosedSections);

  React.useEffect(() => {
    writeStoredPreference(PROJECT_FILES_WIDTH_KEY, String(panelWidth));
  }, [panelWidth]);

  React.useEffect(() => {
    writeStoredPreference(PROJECT_FILES_CLOSED_SECTIONS_KEY, JSON.stringify([...closedSections]));
  }, [closedSections]);

  const toggleSection = (id: string) =>
    setClosedSections((previous) => {
      const next = new Set(previous);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  /** From the collapsed rail: reopen the panel with that section showing. */
  const revealSection = (id: string) => {
    setClosedSections((previous) => {
      if (!previous.has(id)) return previous;
      const next = new Set(previous);
      next.delete(id);
      return next;
    });
    setIsCollapsed(false);
  };

  const isDrifted = (name?: string) => !!(name && driftedWorkflowNames?.has(name));

  const regularWorkflows = unifiedWorkflows.filter(w => w.type === 'regular');
  const reusableWorkflows = unifiedWorkflows.filter(w => w.type === 'reusable');
  const linkedWorkflows = unifiedWorkflows.filter(w => w.type === 'linked');

  const showReusableSection = reusableWorkflowsEnabled && repoExists && reusableWorkflows.length > 0;
  const showCodeownersSection = !!codeownersRepos && codeownersRepos.length > 0;

  /** The on-GitHub filename, kept in the tooltip since the row shows the bare name. */
  const getFullFilename = (workflow: UnifiedWorkflowItem, filename: string) =>
    workflow.name && usePrefix && workflow.type !== 'linked'
      ? `AM_${(projectCode || '').toUpperCase()}_${filename}`
      : filename;

  const renderWorkflowRow = (workflow: UnifiedWorkflowItem, fallbackLabel: string) => {
    const filename = getWorkflowDisplayFilename(workflow, fallbackLabel);
    const fullFilename = getFullFilename(workflow, filename);
    const status = getRowStatus(workflow.workflowStatus, workflow.isModified);
    const drifted = workflow.type !== 'linked' && isDrifted(workflow.name);
    // aria-label replaces the button's content, so every indicator rendered as an
    // aria-hidden glyph has to be spelled out here or it is lost to assistive tech.
    const stateParts = buildStateParts({
      typeLabel: workflow.type === 'linked' ? 'Linked workflow' : null,
      status: status.label,
      drifted,
      modified: workflow.isModified,
    });
    const titleParts = [
      fullFilename,
      ...stateParts,
      workflow.type === 'linked' && workflow.rwxProjectName ? `From: ${workflow.rwxProjectName}` : null,
      workflow.type === 'linked' && workflow.rwxRepo ? `Repo: ${workflow.rwxRepo}` : null,
      workflow.lastModifiedBy ? `Last saved by ${workflow.lastModifiedBy}` : null,
    ].filter(Boolean);

    return (
      <FileRow
        key={workflow.id}
        icon={ROW_ICONS[workflow.type]}
        name={filename}
        title={titleParts.join(DETAIL_SEPARATOR)}
        ariaLabel={[filename, ...stateParts].join(', ')}
        meta={workflow.type === 'linked' ? workflow.rwxProjectName : undefined}
        statusLabel={status.label}
        statusClassName={status.className}
        selected={selectedWorkflowId === workflow.id}
        onSelect={() => handleSelectWorkflow(workflow.id)}
        drifted={drifted}
        modified={workflow.isModified}
        testId={workflow.type === 'linked' ? 'linked-rwx-workflow-card' : undefined}
      />
    );
  };

  const renderCustomFileRow = (cf: CustomFile) => {
    const status = getRowStatus(cf.file_status);
    const stateParts = buildStateParts({
      status: status.label,
      pendingDelete: cf.pending_delete,
    });
    const titleParts = [
      cf.file_path,
      cf.display_name || null,
      ...stateParts,
      cf.last_modified_by ? `Last saved by ${cf.last_modified_by}` : null,
    ].filter(Boolean);

    return (
      <FileRow
        key={cf.id}
        icon={ROW_ICONS.custom}
        name={cf.file_path.split('/').pop() || cf.file_path}
        title={titleParts.join(DETAIL_SEPARATOR)}
        ariaLabel={[cf.file_path, ...stateParts].join(', ')}
        statusLabel={status.label}
        statusClassName={status.className}
        selected={selectedCustomFileId === cf.id}
        onSelect={() => onSelectCustomFile?.(cf.id)}
        pendingDelete={cf.pending_delete}
        testId="custom-file-row"
      />
    );
  };

  const renderCodeownersRow = () => {
    const status = getRowStatus(codeownersAggregateStatus);
    const repoCount = `${codeownersRepos!.length} repo${codeownersRepos!.length !== 1 ? 's' : ''}`;

    return (
      <FileRow
        icon={SECTION_ICONS[SECTION_CODEOWNERS]}
        name=".github/CODEOWNERS"
        title={['.github/CODEOWNERS', repoCount, status.label].join(DETAIL_SEPARATOR)}
        ariaLabel={`.github/CODEOWNERS, ${status.label}`}
        statusLabel={status.label}
        statusClassName={status.className}
        selected={!!selectedCodeownersRepo}
        onSelect={() => onSelectCodeowners?.(codeownersRepos?.[0] ?? selectedRepos[0])}
      />
    );
  };

  if (isCollapsed) {
    const railSections = [
      SECTION_WORKFLOWS,
      showReusableSection ? SECTION_REUSABLE : null,
      linkedWorkflows.length > 0 ? SECTION_LINKED : null,
      customFiles !== undefined ? SECTION_CUSTOM : null,
      showCodeownersSection ? SECTION_CODEOWNERS : null,
    ].filter(Boolean) as string[];

    return (
      <div className="unified-workflows-list collapsed">
        <button
          type="button"
          className="workflows-list-toggle pf-rail-toggle"
          onClick={() => setIsCollapsed(false)}
          title="Expand Project Files"
          aria-label="Expand Project Files"
          aria-expanded={false}
        >
          <ChevronRight className="workflows-list-toggle-icon" />
        </button>

        <nav className="pf-rail" aria-label="Project Files">
          {railSections.map((id) => (
            <button
              key={id}
              type="button"
              className="pf-rail-item"
              onClick={() => revealSection(id)}
              title={SECTION_LABELS[id]}
              aria-label={SECTION_LABELS[id]}
            >
              <span aria-hidden="true">{SECTION_ICONS[id]}</span>
            </button>
          ))}
        </nav>

        <button
          type="button"
          className="pf-rail-label"
          onClick={() => setIsCollapsed(false)}
          title="Expand Project Files"
        >
          Project Files
        </button>
      </div>
    );
  }

  return (
    <div
      className="unified-workflows-list expanded"
      style={{ '--pf-panel-width': `${panelWidth}px` } as React.CSSProperties}
    >
      <div className="workflows-list-header">
        <h4 className="pf-panel-title">Project Files</h4>
        <div className="workflows-list-header-actions">
          {addWorkflowFn && (
            <button
              type="button"
              className="pf-icon-button"
              onClick={addWorkflowFn}
              title="Add File"
              aria-label="Add File"
            >
              <Plus className="pf-icon" />
            </button>
          )}
          <button
            type="button"
            className="workflows-list-toggle"
            onClick={() => setIsCollapsed(true)}
            title="Collapse Project Files"
            aria-label="Collapse Project Files"
            aria-expanded
          >
            <ChevronLeft className="workflows-list-toggle-icon" />
          </button>
        </div>
      </div>

      <div className="workflows-list-container">
        <div className="unified-workflow-sections">
          <PanelSection
            id={SECTION_WORKFLOWS}
            count={regularWorkflows.length}
            closed={closedSections.has(SECTION_WORKFLOWS)}
            onToggle={toggleSection}
          >
            {regularWorkflows.length === 0 ? (
              <div className="empty-section-hint">No workflows yet</div>
            ) : (
              <ul className="pf-rows">
                {regularWorkflows.map((workflow) =>
                  renderWorkflowRow(workflow, `Untitled Workflow ${workflow.originalIndex + 1}`)
                )}
              </ul>
            )}
          </PanelSection>

          {showReusableSection && (
            <PanelSection
              id={SECTION_REUSABLE}
              count={reusableWorkflows.length}
              closed={closedSections.has(SECTION_REUSABLE)}
              onToggle={toggleSection}
            >
              <ul className="pf-rows">
                {reusableWorkflows.map((workflow) =>
                  renderWorkflowRow(workflow, `Untitled Reusable Workflow ${workflow.originalIndex + 1}`)
                )}
              </ul>
            </PanelSection>
          )}

          {linkedWorkflows.length > 0 && (
            <PanelSection
              id={SECTION_LINKED}
              count={linkedWorkflows.length}
              closed={closedSections.has(SECTION_LINKED)}
              onToggle={toggleSection}
            >
              <ul className="pf-rows">
                {linkedWorkflows.map((workflow) =>
                  renderWorkflowRow(workflow, `Untitled Linked Workflow ${workflow.originalIndex + 1}`)
                )}
              </ul>
            </PanelSection>
          )}

          {customFiles !== undefined && (
            <PanelSection
              id={SECTION_CUSTOM}
              count={customFiles.length}
              closed={closedSections.has(SECTION_CUSTOM)}
              onToggle={toggleSection}
            >
              {customFiles.length === 0 ? (
                <div className="empty-section-hint">No custom files yet</div>
              ) : (
                <ul className="pf-rows">{customFiles.map(renderCustomFileRow)}</ul>
              )}
            </PanelSection>
          )}

          {showCodeownersSection && (
            <PanelSection
              id={SECTION_CODEOWNERS}
              closed={closedSections.has(SECTION_CODEOWNERS)}
              onToggle={toggleSection}
            >
              <ul className="pf-rows">{renderCodeownersRow()}</ul>
            </PanelSection>
          )}
        </div>
      </div>

      <ResizeHandle width={panelWidth} onResize={setPanelWidth} />
    </div>
  );
};

export default UnifiedWorkflowList;
