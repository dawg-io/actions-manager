/* eslint-disable no-restricted-syntax, no-restricted-imports -- Legacy: TODO migrate inline styles to Tailwind CSS classes */
import React, { useState } from "react";
import WorkflowStatusBadge from "./WorkflowStatusBadge";
import PlainFileEditor, { PlainFileEditorLanguage } from "./PlainFileEditor";
import {
  CustomFile,
  CreateCustomFilePayload,
  createCustomFile,
  updateCustomFile,
  deleteCustomFile,
  restoreCustomFile,
  validateFilePath,
} from "../api/customFiles";
import "../styles/UnifiedWorkflows.css";

export function detectLanguage(filePath: string): PlainFileEditorLanguage {
  const ext = filePath.split('.').pop()?.toLowerCase() ?? '';
  if (ext === 'yaml' || ext === 'yml') return 'yaml';
  if (ext === 'sh' || ext === 'bash') return 'shell';
  if (ext === 'properties') return 'properties';
  if (ext === 'toml') return 'toml';
  return 'plain';
}

interface CustomFilesProps {
  projectId: number;
  githubUser: string;
  initialFiles?: CustomFile[];
  onChange?: (files: CustomFile[]) => void;
}

const ZERO_HASH = "0".repeat(40);

export function isNeverSynced(cf: CustomFile): boolean {
  return cf.git_hash === null || cf.git_hash === ZERO_HASH;
}

// ── Form component ────────────────────────────────────────────────────────────

export interface FileFormProps {
  initial?: Partial<CustomFile>;
  onSave: (data: CreateCustomFilePayload) => void;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
  hideButtons?: boolean;
}

export const FileForm = React.forwardRef<HTMLFormElement, FileFormProps>(
  ({ initial, onSave, onCancel, saving, error, hideButtons }, ref) => {
  const [displayName, setDisplayName] = useState(initial?.display_name ?? "");
  const [filePath, setFilePath] = useState(initial?.file_path ?? "");
  const [fileContent, setFileContent] = useState(initial?.file_content ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [pathError, setPathError] = useState<string | null>(null);

  const handlePathChange = (val: string) => {
    setFilePath(val);
    setPathError(validateFilePath(val));
  };

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const pe = validateFilePath(filePath);
    if (pe) { setPathError(pe); return; }
    onSave({ display_name: displayName || undefined, file_path: filePath.trim(), file_content: fileContent, description: description || undefined });
  };

  const isEditing = !!initial?.id;
  const buttonLabel = saving ? "Saving…" : (isEditing ? "Save Changes" : "Add File");

  const inputCls = "w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500";
  const filePathCls = `w-full rounded-md border px-2 py-1.5 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-1 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500 dark:placeholder:text-slate-500 dark:disabled:bg-slate-700 dark:disabled:text-slate-400 ${pathError ? "border-red-400 bg-red-50 text-slate-900 focus:border-red-500 focus:ring-red-500 dark:border-red-600 dark:bg-red-900/10 dark:text-slate-100" : "border-slate-300 bg-white text-slate-900 focus:border-blue-500 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"}`;

  return (
    <form ref={ref} onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.75rem", padding: "1.25rem" }}>
      <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
        ⚠️ Custom Files are for workflow-adjacent text files only. Do not store secrets, tokens, certificates, or credentials.
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        <label htmlFor="cf-display-name" style={{ fontSize: "0.8rem", fontWeight: 500 }}>Display Name <span className="text-slate-500 dark:text-slate-400">(optional)</span></label>
        <input
          id="cf-display-name"
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="e.g. Build Script"
          className={inputCls}
        />
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        <label htmlFor="cf-file-path" style={{ fontSize: "0.8rem", fontWeight: 500 }}>File Path <span className="text-red-500">*</span></label>
        <input
          id="cf-file-path"
          type="text"
          value={filePath}
          onChange={(e) => handlePathChange(e.target.value)}
          placeholder="e.g. .github/scripts/build.sh"
          disabled={isEditing}
          required
          className={filePathCls}
          data-testid="file-path-input"
        />
        {pathError && <span className="text-xs text-red-500 dark:text-red-400" data-testid="path-error">{pathError}</span>}
        <span className="text-xs text-slate-500 dark:text-slate-400">Examples: .github/scripts/build.sh · sonar-project.properties · .yamllint.yml</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        {/* Descriptive text, not a form label — PlainFileEditor is not a native control, labeled via aria-label instead. */}
        <div style={{ fontSize: "0.8rem", fontWeight: 500 }}>File Content</div>
        <PlainFileEditor
          value={fileContent}
          onChange={setFileContent}
          language={detectLanguage(filePath)}
          height="350px"
          theme="dark"
          ariaLabel="File Content"
        />
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        <label htmlFor="cf-description" style={{ fontSize: "0.8rem", fontWeight: 500 }}>Description <span className="text-slate-500 dark:text-slate-400">(optional)</span></label>
        <input
          id="cf-description"
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What this file is for"
          className={inputCls}
        />
      </div>

      {error && <div className="text-sm text-red-500 dark:text-red-400">{error}</div>}

      {!hideButtons && (
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button type="submit" disabled={saving || !!pathError || !filePath.trim()} className="btn btn-primary" data-testid="save-button">
            {buttonLabel}
          </button>
          <button type="button" onClick={onCancel} className="btn btn-secondary">
            Cancel
          </button>
        </div>
      )}
    </form>
  );
});
FileForm.displayName = 'FileForm';

// ── Main component ─────────────────────────────────────────────────────────────

// ponytail: fully controlled — no internal files state; parent (ProjectMgmt) owns customFiles
const CustomFiles: React.FC<CustomFilesProps> = ({ projectId, githubUser, initialFiles: files = [], onChange }) => {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [mode, setMode] = useState<'view' | 'edit' | 'add'>('view');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const selectedFile = files.find(f => f.id === selectedId) ?? null;

  const selectFile = (id: number) => {
    setSelectedId(id);
    setMode('view');
    setFormError(null);
  };

  const handleAdd = async (data: CreateCustomFilePayload) => {
    setSaving(true);
    setFormError(null);
    try {
      const result = await createCustomFile(projectId, { ...data, github_user: githubUser });
      onChange?.([...files, result.custom_file]);
      setSelectedId(result.custom_file.id);
      setMode('view');
    } catch (e: any) {
      setFormError(e?.response?.data?.detail ?? "Failed to create file");
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async (id: number, data: CreateCustomFilePayload) => {
    setSaving(true);
    setFormError(null);
    try {
      const result = await updateCustomFile(projectId, id, { ...data, github_user: githubUser });
      onChange?.(files.map((f) => (f.id === id ? result.custom_file : f)));
      setMode('view');
    } catch (e: any) {
      setFormError(e?.response?.data?.detail ?? "Failed to update file");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (cf: CustomFile) => {
    if (!globalThis.confirm(isNeverSynced(cf) && cf.file_status === "new"
      ? `Delete "${cf.file_path}"? This will remove it permanently.`
      : `Mark "${cf.file_path}" for deletion? It will be removed from GitHub on the next delivery.`
    )) return;
    try {
      const result = await deleteCustomFile(projectId, cf.id);
      if (result.hard_deleted) {
        onChange?.(files.filter((f) => f.id !== cf.id));
        setSelectedId(null);
        setMode('view');
      } else {
        onChange?.(files.map((f) => (f.id === cf.id ? result.custom_file! : f)));
      }
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? "Failed to delete file");
    }
  };

  const handleRestore = async (cf: CustomFile) => {
    try {
      const result = await restoreCustomFile(projectId, cf.id);
      onChange?.(files.map((f) => (f.id === cf.id ? result.custom_file : f)));
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? "Failed to restore file");
    }
  };

  // ── Left panel ──────────────────────────────────────────────────────────────

  const renderFileListItem = (cf: CustomFile) => {
    const isSelected = selectedId === cf.id;
    return (
      <li key={cf.id} className="workflow-item-wrapper">
        <button
          className={`workflow-item ${isSelected ? 'selected' : ''}`}
          onClick={() => selectFile(cf.id)}
          data-testid="custom-file-row"
        >
          <div className="workflow-item-content">
            <div className="workflow-name" style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
              {cf.file_path}
            </div>
            {cf.display_name && (
              <div className="workflow-prefix">{cf.display_name}</div>
            )}
            <WorkflowStatusBadge status={cf.file_status} style={{ marginTop: '0.2rem' }} />
            {cf.pending_delete && (
              <WorkflowStatusBadge
                status="pending_delete"
                label="Pending Deletion"
                data-testid="pending-delete-badge"
                style={{
                  marginTop: '0.2rem',
                  backgroundColor: 'rgba(245,158,11,0.12)',
                  borderColor: 'rgba(245,158,11,0.35)',
                  color: '#fbbf24',
                }}
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
    );
  };

  // ── Right panel ─────────────────────────────────────────────────────────────

  const renderEmptyState = () => (
    <div className="no-workflow-selected">
      <div className="no-workflow-content">
        <div style={{ fontSize: '2rem', marginBottom: '0.75rem' }}>📄</div>
        <h3>Custom Files</h3>
        <p>
          {files.length === 0
            ? 'No custom files yet. Click Add File to deploy workflow-adjacent files to every repo in this project.'
            : 'Select a file from the list to view or edit it.'}
        </p>
      </div>
    </div>
  );

  const renderViewPanel = (cf: CustomFile) => (
    <div className="regular-workflow-editor">
      <div className="workflow-editor-header-new">
        <div className="workflow-toolbar-top">
          <div className="workflow-identity" style={{ minWidth: 0, flex: 1 }}>
            <code className="workflow-name" style={{ fontFamily: 'monospace', fontSize: '0.875rem' }}>
              {cf.file_path}
            </code>
            <WorkflowStatusBadge status={cf.file_status} />
            {cf.pending_delete && (
              <WorkflowStatusBadge
                status="pending_delete"
                label="Pending Deletion"
                data-testid="pending-delete-badge"
                style={{
                  backgroundColor: 'rgba(245,158,11,0.12)',
                  borderColor: 'rgba(245,158,11,0.35)',
                  color: '#fbbf24',
                }}
              />
            )}
          </div>
          <div className="workflow-primary-actions">
            {!cf.pending_delete && (
              <button className="btn btn-secondary" onClick={() => setMode('edit')} data-testid="edit-button">
                Edit
              </button>
            )}
            {cf.pending_delete ? (
              <button className="btn btn-secondary" onClick={() => handleRestore(cf)} data-testid="restore-button">
                Restore
              </button>
            ) : (
              <button className="btn btn-danger" onClick={() => handleDelete(cf)} data-testid="delete-button">
                Delete
              </button>
            )}
          </div>
        </div>
        <div className="workflow-toolbar-status">
          {cf.display_name && (
            <span className="status-item">
              <span className="status-label">Display name:</span>
              <span className="status-value">{cf.display_name}</span>
            </span>
          )}
          {cf.description && (
            <span className="status-item">
              <span className="status-label">Description:</span>
              <span className="status-value">{cf.description}</span>
            </span>
          )}
          {cf.last_modified_by && (
            <span className="status-item">
              <span className="status-label">Last saved by:</span>
              <span className="status-value">{cf.last_modified_by}</span>
            </span>
          )}
        </div>
      </div>
      <div className="workflow-editor-content" style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column', padding: '1rem' }}>
        <PlainFileEditor
          value={cf.file_content || ''}
          language={detectLanguage(cf.file_path)}
          readOnly
          height="100%"
          theme="dark"
        />
      </div>
    </div>
  );

  const renderEditPanel = (cf: CustomFile) => (
    <div className="regular-workflow-editor">
      <div className="workflow-editor-header-new">
        <div className="workflow-toolbar-top">
          <div className="workflow-identity">
            <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Editing:</span>
            <code className="workflow-name" style={{ fontFamily: 'monospace', fontSize: '0.875rem' }}>
              {cf.file_path}
            </code>
          </div>
        </div>
      </div>
      <div className="workflow-editor-content" style={{ overflow: 'auto' }}>
        <FileForm
          initial={cf}
          onSave={(data) => handleUpdate(cf.id, data)}
          onCancel={() => { setMode('view'); setFormError(null); }}
          saving={saving}
          error={formError}
        />
      </div>
    </div>
  );

  const renderAddPanel = () => (
    <div className="regular-workflow-editor">
      <div className="workflow-editor-header-new">
        <div className="workflow-toolbar-top">
          <div className="workflow-identity">
            <span className="workflow-name">Add Custom File</span>
          </div>
        </div>
      </div>
      <div className="workflow-editor-content" style={{ overflow: 'auto' }}>
        <FileForm
          onSave={handleAdd}
          onCancel={() => { setMode('view'); setFormError(null); }}
          saving={saving}
          error={formError}
        />
      </div>
    </div>
  );

  const renderRightPanel = () => {
    if (mode === 'add') return renderAddPanel();
    if (selectedFile) {
      return mode === 'edit' ? renderEditPanel(selectedFile) : renderViewPanel(selectedFile);
    }
    return renderEmptyState();
  };

  return (
    <div className="unified-workflows-container">
      {/* Left: file list */}
      <div className="unified-workflows-list">
        <div className="workflows-list-header">
          <div className="workflows-list-header-content">
            <h4>📄 Custom Files</h4>
          </div>
        </div>
        <div className="workflows-list-container">
          {files.length === 0 ? (
            <div className="empty-workflow-list" data-testid="empty-state">
              <p>No custom files yet</p>
              <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                Click "Add File" to deploy files to every repo
              </p>
            </div>
          ) : (
            <div className="unified-workflow-sections">
              <ul className="workflow-items">
                {files.map(renderFileListItem)}
              </ul>
            </div>
          )}
          <div className="add-workflow-button-container">
            <button
              className="add-workflow-button"
              onClick={() => { setSelectedId(null); setMode('add'); setFormError(null); }}
              data-testid="add-custom-file-button"
            >
              ➕ Add File
            </button>
          </div>
        </div>
      </div>

      {/* Right: editor / detail panel */}
      <div className="unified-workflows-editor">
        {renderRightPanel()}
      </div>
    </div>
  );
};

export default CustomFiles;

// ── CustomFilePanel — standalone right-panel for use in unified Project Files editor ──

export interface CustomFilePanelProps {
  /** The file to view/edit. null triggers add-new mode. */
  cf: CustomFile | null;
  allFiles: CustomFile[];
  projectId: number;
  githubUser: string;
  onChange: (files: CustomFile[]) => void;
  /** Called after a new file is created so the nav can select it. */
  onAfterAdd?: (newId: number) => void;
}

export const CustomFilePanel: React.FC<CustomFilePanelProps> = ({
  cf,
  allFiles,
  projectId,
  githubUser,
  onChange,
  onAfterAdd,
}) => {
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [resetKey, setResetKey] = useState(0);
  const formRef = React.useRef<HTMLFormElement>(null);

  const cfId = cf?.id ?? null;
  React.useEffect(() => { setResetKey(0); setFormError(null); }, [cfId]);

  const handleAdd = async (data: CreateCustomFilePayload) => {
    setSaving(true);
    setFormError(null);
    try {
      const result = await createCustomFile(projectId, { ...data, github_user: githubUser });
      onChange([...allFiles, result.custom_file]);
      onAfterAdd?.(result.custom_file.id);
    } catch (e: any) {
      setFormError(e?.response?.data?.detail ?? "Failed to create file");
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async (id: number, data: CreateCustomFilePayload) => {
    setSaving(true);
    setFormError(null);
    try {
      const result = await updateCustomFile(projectId, id, { ...data, github_user: githubUser });
      onChange(allFiles.map((f) => (f.id === id ? result.custom_file : f)));
    } catch (e: any) {
      setFormError(e?.response?.data?.detail ?? "Failed to update file");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (file: CustomFile) => {
    if (!globalThis.confirm(isNeverSynced(file) && file.file_status === "new"
      ? `Delete "${file.file_path}"? This will remove it permanently.`
      : `Mark "${file.file_path}" for deletion? It will be removed from GitHub on the next delivery.`
    )) return;
    try {
      const result = await deleteCustomFile(projectId, file.id);
      if (result.hard_deleted) {
        onChange(allFiles.filter((f) => f.id !== file.id));
      } else {
        onChange(allFiles.map((f) => (f.id === file.id ? result.custom_file! : f)));
      }
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? "Failed to delete file");
    }
  };

  const handleRestore = async (file: CustomFile) => {
    try {
      const result = await restoreCustomFile(projectId, file.id);
      onChange(allFiles.map((f) => (f.id === file.id ? result.custom_file : f)));
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? "Failed to restore file");
    }
  };

  // Add mode (cf === null)
  if (cf === null) {
    return (
      <div className="regular-workflow-editor">
        <div className="workflow-editor-header-new">
          <div className="workflow-toolbar-top">
            <div className="workflow-identity">
              <span className="workflow-name">Add Custom File</span>
            </div>
            <div className="workflow-primary-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setFormError(null)} disabled={saving}>Revert</button>
              <button type="button" className="btn btn-primary" disabled={saving} onClick={() => formRef.current?.requestSubmit()}>
                {saving ? "Adding…" : "💾 Commit Locally"}
              </button>
            </div>
          </div>
        </div>
        <div className="workflow-editor-content" style={{ overflow: 'auto' }}>
          <FileForm
            ref={formRef}
            onSave={handleAdd}
            onCancel={() => setFormError(null)}
            saving={saving}
            error={formError}
            hideButtons
          />
        </div>
      </div>
    );
  }

  // Pending delete: read-only view with Restore action
  if (cf.pending_delete) {
    return (
      <div className="regular-workflow-editor">
        <div className="workflow-editor-header-new">
          <div className="workflow-toolbar-top">
            <div className="workflow-identity" style={{ minWidth: 0, flex: 1 }}>
              <code className="workflow-name" style={{ fontFamily: 'monospace', fontSize: '0.875rem' }}>
                {cf.file_path}
              </code>
              <WorkflowStatusBadge status={cf.file_status} />
              <WorkflowStatusBadge
                status="pending_delete"
                label="Pending Deletion"
                data-testid="pending-delete-badge"
                style={{ backgroundColor: 'rgba(245,158,11,0.12)', borderColor: 'rgba(245,158,11,0.35)', color: '#fbbf24' }}
              />
            </div>
            <div className="workflow-primary-actions">
              <button className="btn btn-secondary" onClick={() => handleRestore(cf)} data-testid="restore-button">
                Restore
              </button>
            </div>
          </div>
        </div>
        <div className="workflow-editor-content" style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column', padding: '1rem' }}>
          <PlainFileEditor
            value={cf.file_content || ''}
            language={detectLanguage(cf.file_path)}
            readOnly
            height="100%"
            theme="dark"
          />
        </div>
      </div>
    );
  }

  // Under review: locked read-only — matches workflow lock behavior
  if (cf.file_status === 'under_review') {
    return (
      <div className="regular-workflow-editor">
        <div className="workflow-editor-header-new">
          <div className="workflow-toolbar-top">
            <div className="workflow-identity" style={{ minWidth: 0, flex: 1 }}>
              <code className="workflow-name" style={{ fontFamily: 'monospace', fontSize: '0.875rem' }}>
                {cf.file_path}
              </code>
              <WorkflowStatusBadge status={cf.file_status} />
            </div>
          </div>
          {cf.last_modified_by && (
            <div className="workflow-toolbar-status">
              <span className="status-item">
                <span className="status-label">Last saved by:</span>
                <span className="status-value">{cf.last_modified_by}</span>
              </span>
            </div>
          )}
        </div>
        <div className="workflow-editor-content workflow-editor-content--lockable">
          <div className="workflow-lock-overlay">
            <div className="workflow-lock-btn workflow-lock-btn-static">
              <span className="workflow-lock-icon" aria-hidden="true">🔒</span>
              <span className="workflow-lock-label">
                <span className="workflow-lock-label-strong">Under Review</span>
                {" — merge or close the PR Campaign to edit"}
              </span>
            </div>
          </div>
          <PlainFileEditor
            value={cf.file_content || ''}
            language={detectLanguage(cf.file_path)}
            readOnly
            height="100%"
            theme="dark"
          />
        </div>
      </div>
    );
  }

  // Normal file: always directly editable, no Edit button required
  return (
    <div className="regular-workflow-editor">
      <div className="workflow-editor-header-new">
        <div className="workflow-toolbar-top">
          <div className="workflow-identity" style={{ minWidth: 0, flex: 1 }}>
            <code className="workflow-name" style={{ fontFamily: 'monospace', fontSize: '0.875rem' }}>
              {cf.file_path}
            </code>
            <WorkflowStatusBadge status={cf.file_status} />
          </div>
          <div className="workflow-primary-actions">
            <button type="button" className="btn btn-secondary" onClick={() => { setFormError(null); setResetKey(k => k + 1); }} disabled={saving}>Revert</button>
            <button type="button" className="btn btn-primary" disabled={saving} onClick={() => formRef.current?.requestSubmit()} data-testid="save-button">
              {saving ? "Saving…" : "💾 Commit Locally"}
            </button>
            <button className="btn btn-danger" onClick={() => handleDelete(cf)} data-testid="delete-button">
              Delete
            </button>
          </div>
        </div>
        {cf.last_modified_by && (
          <div className="workflow-toolbar-status">
            <span className="status-item">
              <span className="status-label">Last saved by:</span>
              <span className="status-value">{cf.last_modified_by}</span>
            </span>
          </div>
        )}
      </div>
      <div className="workflow-editor-content" style={{ overflow: 'auto' }}>
        <FileForm
          ref={formRef}
          key={`${cf.id}-${resetKey}`}
          initial={cf}
          onSave={(data) => handleUpdate(cf.id, data)}
          onCancel={() => { setFormError(null); setResetKey(k => k + 1); }}
          saving={saving}
          error={formError}
          hideButtons
        />
      </div>
    </div>
  );
};
