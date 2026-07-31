import React, { useState, useEffect, useCallback, useRef } from 'react';
import PlainFileEditor from './PlainFileEditor';
import WorkflowStatusBadge from './WorkflowStatusBadge';
import {
  getCodeowners,
  saveCodeownersDraft,
  getCodeownersDrift,
  CodeownersGetResponse,
  CodeownersDriftResponse,
} from '../api/codeowners';

interface CodeownersManagerProps {
  readonly user: string;
  readonly projectName: string;
  readonly selectedRepos: string[];
  readonly isReadOnly?: boolean;
  /** Pre-select this repo when the editor opens (from the unified nav). */
  readonly initialRepo?: string;
  /** Bump to force a reload of CODEOWNERS data (e.g. after a campaign completes). */
  readonly refreshCounter?: number;
  /** Called after a successful local draft save so the parent can refresh status. */
  readonly onSave?: () => void;
}

const FILE_PATH_OPTIONS = [
  { value: '.github/CODEOWNERS', label: '.github/CODEOWNERS (recommended)' },
  { value: 'CODEOWNERS', label: 'CODEOWNERS (repository root)' },
];

const DRIFT_BADGE_STYLES: Record<string, string> = {
  synced: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  content_mismatch: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  missing_locally: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  missing_on_github: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  absent: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
};

const DRIFT_LABELS: Record<string, string> = {
  synced: 'Synced',
  content_mismatch: 'Drift detected',
  missing_locally: 'Missing locally',
  missing_on_github: 'Draft (not on GitHub)',
  absent: 'No CODEOWNERS file',
};

const STATUS_LABELS: Record<string, string> = {
  new: 'New',
  committed_locally: 'Draft changes',
  under_review: 'PR open',
  synced_with_github: 'Synced',
};

const CodeownersManager: React.FC<CodeownersManagerProps> = ({
  user,
  projectName,
  selectedRepos,
  isReadOnly = false,
  initialRepo,
  refreshCounter,
  onSave,
}) => {
  const [activeRepo, setActiveRepo] = useState<string>(initialRepo ?? selectedRepos[0] ?? '');
  const [targetRepos, setTargetRepos] = useState<Set<string>>(new Set(selectedRepos));
  const [content, setContent] = useState<string>('');
  const [filePath, setFilePath] = useState<string>('.github/CODEOWNERS');
  const [info, setInfo] = useState<CodeownersGetResponse | null>(null);
  const [drift, setDrift] = useState<CodeownersDriftResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);
  const [isDirty, setIsDirty] = useState<boolean>(false);
  const [repoDropdownOpen, setRepoDropdownOpen] = useState<boolean>(false);
  const messageTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const repoDropdownRef = useRef<HTMLDivElement | null>(null);

  // Close repo dropdown when clicking outside
  useEffect(() => {
    if (!repoDropdownOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (repoDropdownRef.current && !repoDropdownRef.current.contains(event.target as Node)) {
        setRepoDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [repoDropdownOpen]);

  // Keep the active repo valid when the parent selection changes.
  useEffect(() => {
    if (selectedRepos.length > 0 && !selectedRepos.includes(activeRepo)) {
      setActiveRepo(selectedRepos[0]);
    } else if (selectedRepos.length === 0) {
      setActiveRepo('');
    }
  }, [selectedRepos, activeRepo]);

  // Reconcile target repos with the parent selection without overwriting
  // user toggles. We drop any targets that are no longer in selectedRepos,
  // and default to "all selected" when the user has no remaining targets.
  useEffect(() => {
    setTargetRepos(prev => {
      if (selectedRepos.length === 0) {
        return new Set();
      }
      const allowed = new Set(selectedRepos);
      const next = new Set(Array.from(prev).filter(repo => allowed.has(repo)));
      if (next.size === 0) {
        return new Set(selectedRepos);
      }
      return next;
    });
  }, [selectedRepos]);

  useEffect(() => {
    return () => {
      if (messageTimeoutRef.current) clearTimeout(messageTimeoutRef.current);
    };
  }, []);

  const showMessage = (text: string, type: 'success' | 'error') => {
    setMessage({ text, type });
    if (messageTimeoutRef.current) clearTimeout(messageTimeoutRef.current);
    messageTimeoutRef.current = setTimeout(() => setMessage(null), 5000);
  };

  const handleToggleRepo = (repoName: string) => {
    setTargetRepos(prev => {
      const next = new Set(prev);
      if (next.has(repoName)) {
        next.delete(repoName);
      } else {
        next.add(repoName);
      }
      return next;
    });
  };

  const handleSelectAllRepos = () => {
    setTargetRepos(new Set(selectedRepos));
  };

  const handleDeselectAllRepos = () => {
    setTargetRepos(new Set());
  };

  const loadCodeowners = useCallback(async (repoName: string) => {
    if (!repoName) return;
    setLoading(true);
    setWarnings([]);
    try {
      const data = await getCodeowners(repoName, user, projectName);
      setInfo(data);
      // Prefer the local draft when present, otherwise the GitHub copy.
      const initial = data.local?.content ?? data.github.content ?? '';
      setContent(initial);
      setFilePath(
        data.local?.file_path ?? data.github.path ?? '.github/CODEOWNERS'
      );
      setIsDirty(false);

      // Trigger drift check in parallel
      try {
        const driftData = await getCodeownersDrift(repoName, user, projectName);
        setDrift(driftData);
      } catch (err) {
        console.warn('Failed to load CODEOWNERS drift:', err);
        setDrift(null);
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail ?? err?.message ?? 'Failed to load CODEOWNERS';
      showMessage(detail, 'error');
      setInfo(null);
      setDrift(null);
    } finally {
      setLoading(false);
    }
  }, [user, projectName]);

  useEffect(() => {
    if (activeRepo) {
      loadCodeowners(activeRepo);
    }
  }, [activeRepo, loadCodeowners]);

  useEffect(() => {
    if (refreshCounter && activeRepo) {
      loadCodeowners(activeRepo);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshCounter]);

  const handleContentChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setContent(e.target.value);
    setIsDirty(true);
  };

  const handleFilePathChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setFilePath(e.target.value);
    setIsDirty(true);
  };

  const handleSaveDraft = async () => {
    if (targetRepos.size === 0) {
      showMessage('Please select at least one target repository', 'error');
      return;
    }
    setSaving(true);
    const targetRepoList = Array.from(targetRepos);
    const results: { repo: string; success: boolean; error?: string }[] = [];

    try {
      // Save to all target repos sequentially
      for (const repo of targetRepoList) {
        try {
          const result = await saveCodeownersDraft(
            repo, user, projectName, content, filePath
          );
          results.push({ repo, success: true });

          // Update state for activeRepo if it was saved
          if (repo === activeRepo) {
            setInfo(prev => prev ? { ...prev, local: result.codeowners } : prev);
            setWarnings(result.validation_warnings ?? []);
          }
        } catch (err: any) {
          const detail = err?.response?.data?.detail ?? err?.message ?? 'Failed to save';
          results.push({ repo, success: false, error: detail });
        }
      }

      const successCount = results.filter(r => r.success).length;
      const failCount = results.length - successCount;

      if (failCount === 0) {
        setIsDirty(false);
        showMessage(`Draft saved to ${successCount} ${successCount === 1 ? 'repository' : 'repositories'}`, 'success');
        onSave?.();
      } else {
        showMessage(`Saved to ${successCount} repos, ${failCount} failed`, 'error');
      }

      // Refresh drift status for active repo
      if (activeRepo && results.find(r => r.repo === activeRepo && r.success)) {
        try {
          const driftData = await getCodeownersDrift(activeRepo, user, projectName);
          setDrift(driftData);
        } catch (e) { console.error('drift refresh failed', e); }
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = () => {
    if (info) {
      const initial = info.local?.content ?? info.github.content ?? '';
      setContent(initial);
      setFilePath(info.local?.file_path ?? info.github.path ?? '.github/CODEOWNERS');
      setIsDirty(false);
      setWarnings([]);
    }
  };

  if (selectedRepos.length === 0) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
        📭 Select one or more repositories in <strong>Repositories &amp; Branches</strong> to manage their CODEOWNERS file.
      </div>
    );
  }

  const driftStatus = drift?.drift_status ?? 'absent';
  const driftLabel = DRIFT_LABELS[driftStatus] ?? driftStatus;
  const localStatus = info?.local?.status;

  return (
    <div className="space-y-4">
      {/* Repository selection dropdown */}
      <div className="relative" ref={repoDropdownRef}>
        <button
          type="button"
          onClick={() => setRepoDropdownOpen((open) => !open)}
          aria-haspopup="listbox"
          aria-expanded={repoDropdownOpen}
          className="flex w-full items-center justify-between rounded-md border border-slate-200 bg-white px-4 py-2.5 text-left text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
        >
          <span>
            Target Repositories ({targetRepos.size} of {selectedRepos.length} selected)
            {activeRepo && (
              <span className="ml-2 text-xs font-normal text-slate-500 dark:text-slate-400">
                · Viewing: <span className="font-medium text-blue-700 dark:text-blue-300">{activeRepo}</span>
              </span>
            )}
          </span>
          <svg
            className={`h-4 w-4 text-slate-500 transition-transform ${repoDropdownOpen ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {repoDropdownOpen && (
          <div className="absolute z-10 mt-1 w-full rounded-md border border-slate-200 bg-white p-3 shadow-lg dark:border-slate-700 dark:bg-slate-800">
            <div className="mb-2 flex items-center justify-end gap-2">
              <button
                onClick={handleSelectAllRepos}
                disabled={isReadOnly}
                className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                Select All
              </button>
              <button
                onClick={handleDeselectAllRepos}
                disabled={isReadOnly}
                className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                Deselect All
              </button>
            </div>

            <div className="max-h-64 space-y-1 overflow-y-auto">
              {selectedRepos.map((repo) => {
                const isTarget = targetRepos.has(repo);
                const isActive = repo === activeRepo;
                return (
                  <div
                    key={repo}
                    className={`flex items-center gap-2 rounded p-2 ${
                      isActive ? 'bg-blue-50 dark:bg-blue-900/20' : ''
                    } ${isTarget ? 'border border-slate-300 dark:border-slate-600' : 'border border-transparent'}`}
                  >
                    <input
                      type="checkbox"
                      checked={isTarget}
                      onChange={() => handleToggleRepo(repo)}
                      disabled={isReadOnly}
                      className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50"
                    />
                    <button
                      onClick={() => setActiveRepo(repo)}
                      className={`flex-1 text-left text-sm ${
                        isActive
                          ? 'font-medium text-blue-700 dark:text-blue-300'
                          : 'text-slate-700 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100'
                      }`}
                      title="Click to view this repository's CODEOWNERS"
                    >
                      {repo}
                    </button>
                    {isActive && (
                      <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                        Viewing
                      </span>
                    )}
                  </div>
                );
              })}
            </div>

            <p className="mt-3 text-xs text-slate-600 dark:text-slate-400">
              💡 Check repositories to deploy CODEOWNERS changes. Click a repository name to view its current content.
            </p>
          </div>
        )}
      </div>

      {/* Status badges + action buttons in one row */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {drift && (
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${DRIFT_BADGE_STYLES[driftStatus] ?? DRIFT_BADGE_STYLES.absent}`}
              title={drift.reason}
            >
              {driftLabel}
            </span>
          )}
          {localStatus && (
            <WorkflowStatusBadge status={localStatus} label={STATUS_LABELS[localStatus] ?? localStatus} />
          )}
          {isDirty && (
            <span className="rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-medium text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300">
              Unsaved changes
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {isDirty && (
            <button
              type="button"
              onClick={handleDiscard}
              disabled={saving}
              className="btn btn-secondary"
            >
              Revert
            </button>
          )}
          <button
            type="button"
            onClick={handleSaveDraft}
            disabled={saving || loading || isReadOnly || !isDirty || targetRepos.size === 0}
            title={
              targetRepos.size === 0 ? 'Select at least one target repository' :
              !isDirty ? 'No unsaved changes' :
              undefined
            }
            className="btn btn-primary"
          >
            {saving ? 'Saving…' : '💾 Commit Locally'}
          </button>
        </div>
      </div>

      {/* File path selector */}
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="codeowners-path-select" className="text-sm font-medium text-slate-700 dark:text-slate-300">
          File path:
        </label>
        <select
          id="codeowners-path-select"
          value={filePath}
          onChange={handleFilePathChange}
          disabled={isReadOnly}
          className="rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 disabled:opacity-60"
        >
          {FILE_PATH_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {/* Drift warning if managed externally */}
      {drift?.drift_status === 'missing_locally' && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-200">
          ⚠️ A CODEOWNERS file already exists on GitHub but is not managed by Actions Manager.
          Saving and deploying will start tracking it locally.
        </div>
      )}
      {drift?.drift_status === 'content_mismatch' && (
        <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-700 dark:bg-red-900/20 dark:text-red-200">
          ⚠️ Drift detected — the GitHub copy differs from the locally-managed CODEOWNERS.
          Review the GitHub content below and either re-deploy your draft or pull the
          remote version into the editor.
        </div>
      )}

      {/* Editor — locked when under review */}
      {localStatus === 'under_review' ? (
        <div>
          {/* Descriptive text, not a form label — PlainFileEditor is not a native control, labeled via aria-label instead. */}
          <div className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            CODEOWNERS content
          </div>
          <div className="workflow-editor-content workflow-editor-content--lockable relative h-[400px] overflow-hidden rounded-md">
            <div className="workflow-lock-overlay">
              <div className="workflow-lock-btn workflow-lock-btn-static">
                <span className="workflow-lock-icon" aria-hidden="true">🔒</span>
                <span className="workflow-lock-label">
                  <span className="workflow-lock-label-strong">Under Review</span>
                  {" — merge or close the PR to edit"}
                </span>
              </div>
            </div>
            <PlainFileEditor value={content} language="plain" readOnly height="400px" theme="dark" ariaLabel="CODEOWNERS content" />
          </div>
        </div>
      ) : (
        <div>
          {/* Descriptive text, not a form label — PlainFileEditor is not a native control, labeled via aria-label instead. */}
          <div className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            CODEOWNERS content
          </div>
          <PlainFileEditor
            value={content}
            onChange={(v) => { setContent(v); setIsDirty(true); }}
            language="plain"
            readOnly={loading || isReadOnly}
            height="400px"
            theme="dark"
            ariaLabel="CODEOWNERS content"
          />
        </div>
      )}

      {/* Validation warnings */}
      {warnings.length > 0 && (
        <div className="rounded-md border border-yellow-300 bg-yellow-50 p-3 text-sm dark:border-yellow-700 dark:bg-yellow-900/20">
          <p className="mb-1 font-medium text-yellow-900 dark:text-yellow-200">Validation warnings</p>
          <ul className="list-inside list-disc space-y-0.5 text-yellow-800 dark:text-yellow-200">
            {warnings.slice(0, 8).map((w, idx) => (
              <li key={`warn-${idx}`}>{w}</li>
            ))}
            {warnings.length > 8 && <li>…and {warnings.length - 8} more</li>}
          </ul>
        </div>
      )}

      {/* Status banner */}
      {message && (
        <div
          className={`rounded-md border p-3 text-sm ${
            message.type === 'success'
              ? 'border-green-300 bg-green-50 text-green-900 dark:border-green-700 dark:bg-green-900/20 dark:text-green-200'
              : 'border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-900/20 dark:text-red-200'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Helper text */}
      <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-300">
        <p className="mb-1 font-medium">About CODEOWNERS</p>
        <ul className="list-inside list-disc space-y-0.5">
          <li>Each line is a glob followed by one or more <code>@user</code>, <code>@org/team</code>, or email-address owners.</li>
          <li>Lines starting with <code>#</code> are comments.</li>
          <li>The last matching line wins, so put more-specific rules at the bottom.</li>
          <li>
            See the official{' '}
            <a
              href="https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners"
              target="_blank"
              rel="noreferrer"
              className="text-blue-600 underline hover:text-blue-800 dark:text-blue-400"
            >
              GitHub CODEOWNERS docs
            </a>{' '}
            for the full syntax.
          </li>
        </ul>
      </div>
    </div>
  );
};

export default CodeownersManager;
