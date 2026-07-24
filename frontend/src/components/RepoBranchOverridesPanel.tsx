import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchProjectRepoBranchConfigs,
  updateProjectRepoBranchConfig,
  resetProjectRepoBranchConfig,
  RepoBranchConfig,
  ProjectRepoBranchConfigsResponse,
  BranchConfigMode,
  BranchOptionValue,
} from "../api/projects";

interface RepoBranchOverridesPanelProps {
  user?: string;
  projectId?: number | string | null;
  /**
   * Names of currently-selected repositories. Used to filter the rows
   * returned from the API to those still selected and to detect when a
   * repo has been removed from the project (so we can clear local edits).
   */
  selectedRepos: string[];
  /**
   * Callback to remove a repository from the project.
   */
  onRemoveRepo: (repo: string) => void;
  /**
   * Project-level branch configuration for context display.
   */
  branchOption: "default" | "pattern";
  regexPattern: string;
  branchMaxAgeDays: number;
}

interface DraftConfig {
  branch_config_mode: BranchConfigMode;
  branch_option: BranchOptionValue;
  branch_regex: string;
  branch_max_age_days: number;
}

const isFiniteInteger = (n: unknown): boolean =>
  typeof n === "number" && Number.isFinite(n) && Number.isInteger(n);

const draftFromConfig = (cfg: RepoBranchConfig, projectDefault: ProjectRepoBranchConfigsResponse | null): DraftConfig => {
  const fallbackOption: BranchOptionValue =
    cfg.branch_option ?? projectDefault?.project_branch_option ?? "default";
  const fallbackRegex =
    cfg.branch_regex ?? projectDefault?.project_branch_regex ?? "";
  const fallbackMaxAge =
    cfg.branch_max_age_days ?? projectDefault?.project_branch_max_age_days ?? 30;
  return {
    branch_config_mode: cfg.branch_config_mode,
    branch_option: fallbackOption,
    branch_regex: fallbackRegex,
    branch_max_age_days: isFiniteInteger(fallbackMaxAge) ? fallbackMaxAge : 30,
  };
};

const draftsEqual = (a: DraftConfig, b: DraftConfig): boolean =>
  a.branch_config_mode === b.branch_config_mode &&
  a.branch_option === b.branch_option &&
  (a.branch_regex || "") === (b.branch_regex || "") &&
  a.branch_max_age_days === b.branch_max_age_days;

const RepoBranchOverridesPanel: React.FC<RepoBranchOverridesPanelProps> = ({
  user,
  projectId,
  selectedRepos,
  onRemoveRepo,
  branchOption,
  regexPattern,
  branchMaxAgeDays,
}) => {
  const [data, setData] = useState<ProjectRepoBranchConfigsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [activeRepoId, setActiveRepoId] = useState<number | null>(null);
  const [draft, setDraft] = useState<DraftConfig | null>(null);
  const [savedDraft, setSavedDraft] = useState<DraftConfig | null>(null);

  const [saving, setSaving] = useState<boolean>(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);

  const selectedSet = useMemo(() => new Set(selectedRepos), [selectedRepos]);
  // Stable key for the selected repos so we can refetch when membership
  // changes even if the parent keeps the same projectId.
  const selectedReposKey = useMemo(
    () => [...selectedRepos].sort((a, b) => a.localeCompare(b)).join("|"),
    [selectedRepos],
  );

  // Visible rows = those still selected on the project. Backend may include
  // extras only momentarily after add/remove until the project is re-saved.
  const visibleRepos = useMemo<RepoBranchConfig[]>(() => {
    if (!data) return [];
    return data.repos.filter((r) => selectedSet.has(r.repo_name));
  }, [data, selectedSet]);

  const refresh = useCallback(async () => {
    if (!projectId || !user) return;
    setLoading(true);
    setLoadError(null);
    try {
      const result = await fetchProjectRepoBranchConfigs(user, projectId);
      setData(result);
    } catch (err) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || (err as Error)?.message
        || "Failed to load repository branch configs";
      setLoadError(msg);
    } finally {
      setLoading(false);
    }
  }, [projectId, user]);

  useEffect(() => {
    if (projectId) {
      refresh();
    }
    // Re-fetch when the set of selected repos changes (e.g. after the parent
    // reloads the project on save and the projectId is unchanged).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh, projectId, selectedReposKey]);

  // Reset local editor state when the active repo is removed from the project.
  useEffect(() => {
    if (activeRepoId === null) return;
    const stillSelected = visibleRepos.some((r) => r.repo_id === activeRepoId);
    if (!stillSelected) {
      setActiveRepoId(null);
      setDraft(null);
      setSavedDraft(null);
      setSaveError(null);
      setSaveSuccess(null);
    }
  }, [visibleRepos, activeRepoId]);

  const handleToggleConfig = (repo: RepoBranchConfig) => {
    if (activeRepoId === repo.repo_id) {
      // Close editor
      setActiveRepoId(null);
      setDraft(null);
      setSavedDraft(null);
      setSaveError(null);
      setSaveSuccess(null);
    } else {
      // Open editor for this repo
      setActiveRepoId(repo.repo_id);
      const next = draftFromConfig(repo, data);
      setDraft(next);
      setSavedDraft(next);
      setSaveError(null);
      setSaveSuccess(null);
    }
  };

  const activeRepo = useMemo<RepoBranchConfig | null>(() => {
    if (activeRepoId === null) return null;
    return visibleRepos.find((r) => r.repo_id === activeRepoId) || null;
  }, [activeRepoId, visibleRepos]);

  const isDirty = !!(draft && savedDraft && !draftsEqual(draft, savedDraft));

  const updateDraft = (patch: Partial<DraftConfig>) => {
    setDraft((prev) => (prev ? { ...prev, ...patch } : prev));
    setSaveSuccess(null);
  };

  const handleSave = async () => {
    if (!activeRepo || !draft) return;
    if (!user || !projectId) return;
    if (
      draft.branch_config_mode === "override"
      && draft.branch_option === "pattern"
      && !draft.branch_regex.trim()
    ) {
      setSaveError("Branch name or pattern is required when overriding with a pattern");
      return;
    }
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(null);
    try {
      const payload =
        draft.branch_config_mode === "inherit"
          ? { branch_config_mode: "inherit" as const }
          : {
              branch_config_mode: "override" as const,
              branch_option: draft.branch_option,
              branch_regex: draft.branch_option === "pattern" ? draft.branch_regex.trim() : null,
              branch_max_age_days:
                draft.branch_option === "pattern" ? draft.branch_max_age_days : null,
            };
      const updated = await updateProjectRepoBranchConfig(
        user,
        projectId,
        activeRepo.repo_id,
        payload,
      );
      setData((prev) =>
        prev
          ? {
              ...prev,
              repos: prev.repos.map((r) => (r.repo_id === updated.repo_id ? updated : r)),
            }
          : prev,
      );
      const nextDraft = draftFromConfig(updated, data);
      setDraft(nextDraft);
      setSavedDraft(nextDraft);
      setSaveSuccess("Saved");
    } catch (err) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || (err as Error)?.message
        || "Failed to save branch configuration";
      setSaveError(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!activeRepo) return;
    if (!user || !projectId) return;
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(null);
    try {
      const updated = await resetProjectRepoBranchConfig(user, projectId, activeRepo.repo_id);
      setData((prev) =>
        prev
          ? {
              ...prev,
              repos: prev.repos.map((r) => (r.repo_id === updated.repo_id ? updated : r)),
            }
          : prev,
      );
      const nextDraft = draftFromConfig(updated, data);
      setDraft(nextDraft);
      setSavedDraft(nextDraft);
      setSaveSuccess("Reset to project default");
    } catch (err) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || (err as Error)?.message
        || "Failed to reset branch configuration";
      setSaveError(msg);
    } finally {
      setSaving(false);
    }
  };

  const getBranchSummary = (repo: RepoBranchConfig): string => {
    if (repo.branch_config_mode === "inherit") {
      // Show project default
      if (branchOption === "default") {
        return "Default branch";
      }
      return `Pattern: ${regexPattern || "(none)"}, ${branchMaxAgeDays}d`;
    }
    // Show override
    if (repo.branch_option === "default") {
      return "Default branch";
    }
    return `Pattern: ${repo.branch_regex || "(none)"}, ${repo.branch_max_age_days || 30}d`;
  };

  if (!projectId) {
    return null;
  }

  if (loading && visibleRepos.length === 0) {
    return (
      <div className="text-center py-4 text-sm text-slate-500 dark:text-slate-400">
        Loading repository configurations...
      </div>
    );
  }

  if (loadError) {
    return (
      <div
        role="alert"
        className="rounded border border-red-300 bg-red-50 dark:bg-red-900/20 dark:border-red-700 px-4 py-3 text-sm text-red-700 dark:text-red-200"
      >
        {loadError}
      </div>
    );
  }

  if (visibleRepos.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3" data-testid="repo-branch-overrides">
      {visibleRepos.map((repo) => {
        const isActive = repo.repo_id === activeRepoId;
        const isOverride = repo.branch_config_mode === "override";

        return (
          <div key={repo.repo_id} className="border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden">
            {/* Repository Row */}
            <div className="flex items-center justify-between p-4 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors">
              <div className="flex items-center gap-4 flex-1 min-w-0">
                {/* Repository Name */}
                <div className="font-mono text-sm text-slate-900 dark:text-slate-100 truncate font-medium">
                  {repo.repo_name}
                </div>

                {/* Badge */}
                {isOverride ? (
                  <span
                    className="shrink-0 rounded-full bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 text-xs font-medium px-3 py-1"
                    data-testid={`badge-override-${repo.repo_id}`}
                  >
                    Custom Branch Config
                  </span>
                ) : (
                  <span
                    className="shrink-0 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-medium px-3 py-1"
                    data-testid={`badge-inherit-${repo.repo_id}`}
                  >
                    Using Project Default
                  </span>
                )}

                {/* Branch Summary */}
                <div className="text-xs text-slate-600 dark:text-slate-400 truncate">
                  {getBranchSummary(repo)}
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  onClick={() => handleToggleConfig(repo)}
                  className="text-sm font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 px-3 py-1.5 rounded-md hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
                >
                  {isActive ? "Close" : "Configure"}
                </button>
                <button
                  type="button"
                  onClick={() => onRemoveRepo(repo.repo_name)}
                  className="text-sm font-medium text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 px-3 py-1.5 rounded-md hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                >
                  Remove
                </button>
              </div>
            </div>

            {/* Inline Editor (Expandable) */}
            {isActive && draft && (
              <div className="border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 p-4" data-testid="repo-editor-inline">
                <div className="space-y-4 max-w-3xl">
                  <div>
                    <div className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">
                      Branch Configuration for {repo.repo_name}
                    </div>
                    <div className="space-y-2">
                      <label className="flex items-start gap-2 text-sm text-slate-800 dark:text-slate-200 cursor-pointer">
                        <input
                          type="radio"
                          name={`mode-${repo.repo_id}`}
                          value="inherit"
                          checked={draft.branch_config_mode === "inherit"}
                          onChange={() => updateDraft({ branch_config_mode: "inherit" })}
                          className="mt-1"
                          data-testid="mode-inherit"
                        />
                        <span>
                          <span className="font-medium">Use project default</span>
                          <span className="block text-xs text-slate-500 dark:text-slate-400">
                            Inherit branch settings from the project ({branchOption}
                            {branchOption === "pattern" && regexPattern
                              ? `: ${regexPattern}, ${branchMaxAgeDays}d`
                              : ""}).
                          </span>
                        </span>
                      </label>
                      <label className="flex items-start gap-2 text-sm text-slate-800 dark:text-slate-200 cursor-pointer">
                        <input
                          type="radio"
                          name={`mode-${repo.repo_id}`}
                          value="override"
                          checked={draft.branch_config_mode === "override"}
                          onChange={() => updateDraft({ branch_config_mode: "override" })}
                          className="mt-1"
                          data-testid="mode-override"
                        />
                        <span>
                          <span className="font-medium">Override for this repository</span>
                          <span className="block text-xs text-slate-500 dark:text-slate-400">
                            Only this repository will use the settings below.
                          </span>
                        </span>
                      </label>
                    </div>
                  </div>

                  <fieldset
                    disabled={draft.branch_config_mode !== "override"}
                    className={
                      draft.branch_config_mode !== "override"
                        ? "opacity-50 pointer-events-none"
                        : ""
                    }
                  >
                    <div className="space-y-2">
                      <label className="flex items-center gap-2 text-sm text-slate-800 dark:text-slate-200 cursor-pointer">
                        <input
                          type="radio"
                          name={`option-${repo.repo_id}`}
                          value="default"
                          checked={draft.branch_option === "default"}
                          onChange={() => updateDraft({ branch_option: "default", branch_regex: "" })}
                          data-testid="option-default"
                        />{' '}
                        Default branch
                      </label>
                      <label className="flex items-center gap-2 text-sm text-slate-800 dark:text-slate-200 cursor-pointer">
                        <input
                          type="radio"
                          name={`option-${repo.repo_id}`}
                          value="pattern"
                          checked={draft.branch_option === "pattern"}
                          onChange={() => updateDraft({ branch_option: "pattern" })}
                          data-testid="option-pattern"
                        />{' '}
                        Branch name or pattern
                      </label>
                    </div>

                    {draft.branch_option === "pattern" && (
                      <div className="mt-3 space-y-3">
                        <div>
                          <label
                            htmlFor={`regex-${repo.repo_id}`}
                            className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1"
                          >
                            Branch name or pattern
                          </label>
                          <input
                            id={`regex-${repo.repo_id}`}
                            type="text"
                            placeholder="e.g., main, release-.*, feature/auth"
                            value={draft.branch_regex}
                            onChange={(e) => updateDraft({ branch_regex: e.target.value })}
                            className="w-full rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 px-2 py-1.5 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                            data-testid="input-regex"
                          />
                        </div>
                        <div>
                          <label
                            htmlFor={`maxage-${repo.repo_id}`}
                            className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1"
                          >
                            Max branch age (days)
                          </label>
                          <input
                            id={`maxage-${repo.repo_id}`}
                            type="number"
                            min={1}
                            max={30}
                            value={draft.branch_max_age_days}
                            onChange={(e) => {
                              const n = Number.parseInt(e.target.value, 10);
                              if (Number.isFinite(n)) {
                                updateDraft({
                                  branch_max_age_days: Math.max(1, Math.min(30, n)),
                                });
                              }
                            }}
                            className="w-24 rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 px-2 py-1.5 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            data-testid="input-max-age"
                          />
                          <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                            Only branches updated in the last {draft.branch_max_age_days} days will be targeted.
                          </p>
                        </div>
                      </div>
                    )}
                  </fieldset>

                  {saveError && (
                    <div
                      role="alert"
                      className="rounded border border-red-300 bg-red-50 dark:bg-red-900/20 dark:border-red-700 px-3 py-2 text-xs text-red-700 dark:text-red-200"
                      data-testid="save-error"
                    >
                      {saveError}
                    </div>
                  )}
                  {saveSuccess && (
                    <div
                      className="rounded border border-emerald-300 bg-emerald-50 dark:bg-emerald-900/20 dark:border-emerald-700 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-200"
                      data-testid="save-success"
                    >
                      {saveSuccess}
                    </div>
                  )}

                  <div className="flex items-center gap-2 pt-1">
                    <button
                      type="button"
                      onClick={handleSave}
                      disabled={saving || !isDirty}
                      className="inline-flex items-center rounded-md bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 dark:disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm font-medium px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      data-testid="save-btn"
                    >
                      {saving ? "Saving…" : "Save"}
                    </button>
                    <button
                      type="button"
                      onClick={handleReset}
                      disabled={saving || repo.branch_config_mode === "inherit"}
                      className="inline-flex items-center rounded-md border border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700/40 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium text-slate-700 dark:text-slate-200 px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      data-testid="reset-btn"
                    >
                      Reset to project default
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default RepoBranchOverridesPanel;
