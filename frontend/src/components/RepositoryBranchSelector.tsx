import React, { useMemo, useState } from "react";

/**
 * RepositoryBranchSelector — the unified, horizontal repository selection UI
 * for ActionsManager.
 *
 * Layout:
 *   - Left (≈35%):   Selected Repositories panel
 *   - Right (≈65%):  Available Repositories panel (search + scrollable list)
 *   - Bottom full:   Branch Configuration panel (slot, parent-supplied)
 *
 * The component is purely presentational: it owns the search box state and
 * the highlighted/selected state of rows but defers persistence (add/remove,
 * branch overrides, etc.) to the parent via callbacks. This keeps it
 * reusable across both the New Project flow (no branchConfigSlot) and the
 * existing project Repositories &amp; Branches screen.
 */

export interface RepositoryBranchSelectorRepo {
  id: string | number;
  /** Short repo name (e.g. "test1"). Used as a fallback when full_name is missing. */
  name: string;
  /** Owner-qualified name (e.g. "whatsupdawg/test1"). Preferred display value. */
  full_name?: string;
  /** True when the repo is private on GitHub. */
  private?: boolean;
  /** "User" or "Organization" — drives the Personal vs Organization badge. */
  owner_type?: string;
  /** Owner login, used as a fallback for the avatar/initial. */
  owner?: string;
}

export interface RepositoryBranchSelectorProps {
  /** Full list of repositories the user can pick from. */
  availableRepositories: RepositoryBranchSelectorRepo[];
  /** Names (full_name or name) of repositories already in the project. */
  selectedRepositoryNames: string[];
  /** Visibility filter mode for the helper text under the right-hand heading. */
  visibilityScope?: "public" | "private";
  /** Loading flag — shows a placeholder in the available list. */
  loading?: boolean;
  /** Optional error text — shown in the available list when set. */
  error?: string | null;
  /** Called when a repository should be added to the selection. */
  onSelectRepository: (repoName: string) => void;
  /** Called when a repository should be removed from the selection. */
  onRemoveRepository: (repoName: string) => void;
  /**
   * Called when the entire selection should be replaced (used by
   * `singleSelect`). When omitted, single-select falls back to the
   * remove-then-add dance using `onRemoveRepository` / `onSelectRepository`,
   * which is unsafe if the parent updates state from a closed-over array.
   * Always supply this when `singleSelect` is true.
   */
  onReplaceSelection?: (repoNames: string[]) => void;
  /** Optional — called when the user clicks "Clear all". */
  onClearSelectedRepositories?: () => void;
  /** Optional — called when the user clicks the refresh button. */
  onRefresh?: () => void;
  /** Optional slot for the bottom Branch Configuration card (parent-rendered). */
  branchConfigSlot?: React.ReactNode;
  /** Optional override for the count shown in the Branch Configuration heading. */
  branchConfigCount?: number;
  /** Helper line under the Selected Repositories heading. */
  selectedHelperText?: string;
  /** Helper line under the Available Repositories heading. */
  availableHelperText?: string;
  /** Placeholder for the search input. */
  searchPlaceholder?: string;
  /** Disable the underlying inputs (read-only contexts). */
  readOnly?: boolean;
  /**
   * When true, selecting a repository replaces any existing selection.
   * Used by RWX projects which only allow a single repository.
   */
  singleSelect?: boolean;
  /**
   * Optional key — when its value changes, the internal search input is
   * reset. Useful for parents that swap the available repository list (e.g.
   * standard ↔ RWX project type toggle) so a stale query from the previous
   * list doesn't make the new list look empty.
   */
  resetSearchKey?: string | number;
  /** Test id forwarded to the root container. */
  "data-testid"?: string;
}

const formatVisibilityHelper = (scope?: "public" | "private"): string => {
  if (scope === "private") return "Showing private repositories only.";
  if (scope === "public") return "Showing public repositories only.";
  return "Showing all accessible repositories.";
};

/** Lightweight stand-in for a GitHub repo avatar (no network fetch). */
const RepoAvatar: React.FC<{ label?: string }> = ({ label }) => {
  const initial = (label || "?").trim().charAt(0).toUpperCase() || "?";
  return (
    <span
      aria-hidden="true"
      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-700/70 text-xs font-semibold text-slate-100 ring-1 ring-slate-600"
    >
      {initial}
    </span>
  );
};

const VisibilityBadge: React.FC<{ isPrivate?: boolean }> = ({ isPrivate }) => (
  <span
    className={
      isPrivate
        ? "inline-flex items-center rounded-full border border-slate-400/40 bg-slate-400/10 px-2 py-0.5 text-[11px] font-medium text-slate-300"
        : "inline-flex items-center rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-300"
    }
  >
    {isPrivate ? "Private" : "Public"}
  </span>
);

const AccountTypeBadge: React.FC<{ ownerType?: string }> = ({ ownerType }) => {
  const isOrg = (ownerType || "").toLowerCase() === "organization";
  return (
    <span
      className={
        isOrg
          ? "inline-flex items-center rounded-full border border-indigo-500/40 bg-indigo-500/10 px-2 py-0.5 text-[11px] font-medium text-indigo-300"
          : "inline-flex items-center rounded-full border border-sky-500/40 bg-sky-500/10 px-2 py-0.5 text-[11px] font-medium text-sky-300"
      }
    >
      {isOrg ? "Organization" : "Personal"}
    </span>
  );
};

const repoKey = (r: RepositoryBranchSelectorRepo): string =>
  r.full_name || r.name;

const RepositoryBranchSelector: React.FC<RepositoryBranchSelectorProps> = ({
  availableRepositories,
  selectedRepositoryNames,
  visibilityScope,
  loading = false,
  error = null,
  onSelectRepository,
  onRemoveRepository,
  onReplaceSelection,
  onClearSelectedRepositories,
  onRefresh,
  branchConfigSlot,
  branchConfigCount,
  selectedHelperText = "These repositories will be included in this project.",
  availableHelperText,
  searchPlaceholder = "Search repositories by name, owner, organization, or account...",
  readOnly = false,
  singleSelect = false,
  resetSearchKey,
  "data-testid": dataTestId = "repository-branch-selector",
}) => {
  const [searchTerm, setSearchTerm] = useState("");

  // Reset the internal search box whenever the parent signals that the
  // available list is logically different (e.g. project type toggle), so a
  // stale query from the previous list does not hide every row in the new
  // list and look like an empty fetch.
  // Intentionally depends only on resetSearchKey: adding `searchTerm` would
  // immediately re-clear it on every keystroke.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  React.useEffect(() => {
    setSearchTerm("");
  }, [resetSearchKey]);

  const selectedSet = useMemo(
    () => new Set(selectedRepositoryNames),
    [selectedRepositoryNames],
  );

  // Selected repo cards are derived from availableRepositories when possible
  // so we can show badges/avatars; if a name has no matching repo metadata
  // (e.g. previously-saved repo not currently in the fetch result) we render
  // a name-only card without misleading visibility/account-type badges.
  const selectedDisplayRepos = useMemo(() => {
    const byKey = new Map(availableRepositories.map((r) => [repoKey(r), r]));
    return selectedRepositoryNames.map((name) => {
      const match = byKey.get(name);
      if (match) return { repo: match, hasMetadata: true };
      return {
        repo: { id: name, name, full_name: name } as RepositoryBranchSelectorRepo,
        hasMetadata: false,
      };
    });
  }, [availableRepositories, selectedRepositoryNames]);

  const filteredAvailable = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return availableRepositories;
    return availableRepositories.filter((r) => {
      const full = (r.full_name || "").toLowerCase();
      const short = (r.name || "").toLowerCase();
      const owner = (r.owner || "").toLowerCase();
      return (
        full.includes(term) || short.includes(term) || owner.includes(term)
      );
    });
  }, [availableRepositories, searchTerm]);

  const handleToggleAvailable = (repo: RepositoryBranchSelectorRepo) => {
    if (readOnly) return;
    const key = repoKey(repo);
    if (selectedSet.has(key)) {
      onRemoveRepository(key);
      return;
    }
    if (singleSelect) {
      // Replace the entire selection in a single setState so consumers that
      // derive the next state from a closed-over array don't end up with
      // both the previous and the new repo selected. Prefer the explicit
      // onReplaceSelection callback when provided; otherwise fall back to
      // the legacy remove-then-add sequence (which is safe only when the
      // previous selection was empty).
      if (onReplaceSelection) {
        onReplaceSelection([key]);
        return;
      }
      selectedRepositoryNames.forEach((existing) => {
        if (existing !== key) onRemoveRepository(existing);
      });
    }
    onSelectRepository(key);
  };

  const helperLine = availableHelperText ?? formatVisibilityHelper(visibilityScope);

  const branchCount =
    typeof branchConfigCount === "number"
      ? branchConfigCount
      : selectedRepositoryNames.length;

  return (
    <div
      data-testid={dataTestId}
      className="flex flex-col gap-6"
    >
      {/* Top: two-column repository area */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,35fr)_minmax(0,65fr)]">
        {/* ── Selected Repositories ─────────────────────────────────────── */}
        <section
          aria-label="Selected Repositories"
          data-testid="selected-repositories-panel"
          className="min-w-0 rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800"
        >
          <header className="mb-3 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                👥 Selected Repositories ({selectedRepositoryNames.length})
              </h3>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                {selectedHelperText}
              </p>
            </div>
            {onClearSelectedRepositories && (
              <button
                type="button"
                onClick={onClearSelectedRepositories}
                disabled={readOnly || selectedRepositoryNames.length === 0}
                data-testid="selected-clear-all"
                className="shrink-0 rounded-md border border-red-400/40 px-2.5 py-1 text-xs font-medium text-red-500 transition-colors hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-50 dark:text-red-300"
              >
                🗑 Clear all
              </button>
            )}
          </header>

          {selectedDisplayRepos.length === 0 ? (
            <div
              data-testid="selected-empty-state"
              className="rounded-md border border-dashed border-slate-300 px-3 py-6 text-center text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400"
            >
              No repositories selected yet. Pick from the list on the right.
            </div>
          ) : (
            <ul className="space-y-2" data-testid="selected-repositories-list">
              {selectedDisplayRepos.map(({ repo, hasMetadata }) => {
                const key = repoKey(repo);
                return (
                  <li
                    key={key}
                    data-testid={`selected-repo-${key}`}
                    data-has-metadata={hasMetadata ? "true" : "false"}
                    className="group flex items-center gap-2 rounded-md border border-blue-500/40 bg-blue-500/5 p-2 shadow-sm dark:border-blue-400/40 dark:bg-blue-500/10"
                  >
                    <span
                      aria-hidden="true"
                      className="cursor-grab text-slate-400 dark:text-slate-500"
                      title="Drag to reorder (visual only)"
                    >
                      ⋮⋮
                    </span>
                    <RepoAvatar label={repo.owner || repo.full_name || repo.name} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                        {repo.full_name || repo.name}
                      </div>
                      {hasMetadata ? (
                        <div className="mt-1 flex flex-wrap items-center gap-1.5">
                          <VisibilityBadge isPrivate={!!repo.private} />
                          <AccountTypeBadge ownerType={repo.owner_type} />
                        </div>
                      ) : (
                        // Repo metadata isn't in the current available list
                        // (e.g. a previously-saved repo that the latest
                        // fetch didn't return). Showing the badges here
                        // would mis-label the repo (defaulting to Public /
                        // Personal), so we show a neutral marker instead.
                        <div
                          className="mt-1 text-[11px] italic text-slate-500 dark:text-slate-400"
                          data-testid={`selected-repo-unknown-${key}`}
                        >
                          Metadata unavailable
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => onRemoveRepository(key)}
                      disabled={readOnly}
                      aria-label={`Remove ${repo.full_name || repo.name}`}
                      data-testid={`remove-selected-${key}`}
                      className="ml-1 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-200/70 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-slate-700 dark:hover:text-slate-100"
                      title="Remove from project"
                    >
                      ✕
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          {selectedDisplayRepos.length > 0 && (
            <div className="mt-3 rounded-md border border-blue-500/30 bg-blue-500/5 p-2 text-[11px] text-slate-600 dark:text-slate-300">
              <strong className="text-blue-500 dark:text-blue-300">Tip:</strong>{" "}
              Drag handles are a visual affordance — order reflects the
              current sequence shown here.
            </div>
          )}
        </section>

        {/* ── Available Repositories ────────────────────────────────────── */}
        <section
          aria-label="Available Repositories"
          data-testid="available-repositories-panel"
          className="min-w-0 rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800"
        >
          <header className="mb-3 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                📁 Available Repositories
              </h3>
              <p
                className="mt-1 text-xs text-slate-500 dark:text-slate-400"
                data-testid="available-helper-text"
              >
                {helperLine}
              </p>
            </div>
            {onRefresh && (
              <button
                type="button"
                onClick={onRefresh}
                disabled={loading}
                data-testid="available-refresh"
                className="shrink-0 rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                ⟳ Refresh
              </button>
            )}
          </header>

          <div className="mb-3">
            <label htmlFor="repo-branch-selector-search" className="sr-only">
              Search repositories
            </label>
            <input
              id="repo-branch-selector-search"
              type="text"
              placeholder={searchPlaceholder}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              disabled={readOnly}
              data-testid="available-search-input"
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500"
            />
          </div>

          <div
            className="max-h-96 overflow-x-hidden overflow-y-auto rounded-md border border-slate-200 dark:border-slate-700"
            data-testid="available-repositories-list"
          >
            {loading ? (
              <div
                className="px-3 py-6 text-center text-xs text-slate-500 dark:text-slate-400"
                data-testid="available-loading"
              >
                Loading repositories…
              </div>
            ) : error ? (
              <div
                role="alert"
                className="px-3 py-6 text-center text-xs text-red-600 dark:text-red-300"
                data-testid="available-error"
              >
                {error}
              </div>
            ) : filteredAvailable.length === 0 ? (
              <div
                className="px-3 py-6 text-center text-xs text-slate-500 dark:text-slate-400"
                data-testid="available-empty"
              >
                {searchTerm
                  ? "No repositories match your search."
                  : "No repositories available."}
              </div>
            ) : (
              <ul className="divide-y divide-slate-200 dark:divide-slate-700">
                {filteredAvailable.map((repo) => {
                  const key = repoKey(repo);
                  const isSelected = selectedSet.has(key);
                  return (
                    <li key={repo.id ?? key}>
                      <label
                        data-testid={`available-repo-${key}`}
                        data-selected={isSelected ? "true" : "false"}
                        className={
                          (isSelected
                            ? "border-l-2 border-blue-500 bg-blue-500/10 dark:bg-blue-500/15 "
                            : "border-l-2 border-transparent hover:bg-slate-50 dark:hover:bg-slate-700/40 ") +
                          "flex min-w-0 cursor-pointer items-center gap-3 px-3 py-2 text-sm text-slate-800 dark:text-slate-100"
                        }
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          disabled={readOnly}
                          onChange={() => handleToggleAvailable(repo)}
                          aria-label={`Select ${repo.full_name || repo.name}`}
                          data-testid={`available-checkbox-${key}`}
                          className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-900"
                        />
                        <RepoAvatar label={repo.owner || repo.full_name || repo.name} />
                        <span className="min-w-0 flex-1 truncate font-medium">
                          {repo.full_name || repo.name}
                        </span>
                        <VisibilityBadge isPrivate={!!repo.private} />
                        <AccountTypeBadge ownerType={repo.owner_type} />
                      </label>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </section>
      </div>

      {/* Bottom: Branch Configuration (only when slot is provided) */}
      {branchConfigSlot && (
        <section
          aria-label="Branch Configuration"
          data-testid="branch-configuration-panel"
          className="min-w-0 rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800"
        >
          <header className="mb-3 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                🌿 Branch Configuration ({branchCount})
              </h3>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                Configure branch rules for each selected repository.
              </p>
            </div>
          </header>
          {selectedRepositoryNames.length === 0 ? (
            <div
              data-testid="branch-config-empty"
              className="rounded-md border border-dashed border-slate-300 px-3 py-6 text-center text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400"
            >
              Select one or more repositories to configure branch rules.
            </div>
          ) : (
            branchConfigSlot
          )}
        </section>
      )}
    </div>
  );
};

export default RepositoryBranchSelector;
