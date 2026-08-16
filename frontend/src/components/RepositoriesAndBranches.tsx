import React, { useEffect, useState } from "react";
import { fetchRepos } from "../api/repos";
import RepoBranchOverridesPanel from "./RepoBranchOverridesPanel";
import RepositoryBranchSelector from "./RepositoryBranchSelector";

// TypeScript interfaces
interface Repository {
  id: number;
  name: string;
  full_name?: string;
  private?: boolean;
  owner?: string;
  owner_type?: string;
}

type BranchOption = "default" | "pattern";
type VisibilityScope = "public" | "private";

// Single source of truth for matching a repo against a visibility scope.
// Mirrors the same function in NewProject.tsx to ensure consistent filtering.
function repoMatchesVisibilityScope(repo: Repository, scope: VisibilityScope): boolean {
  const repoIsPrivate = !!repo.private;
  return scope === "private" ? repoIsPrivate : !repoIsPrivate;
}

interface RepositoriesAndBranchesProps {
  user?: string;
  repos: Repository[];
  setRepos: (repos: Repository[] | ((prev: Repository[]) => Repository[])) => void;
  selectedRepos: string[];
  setSelectedRepos: (repos: string[] | ((prev: string[]) => string[])) => void;
  setRegexPattern: (pattern: string) => void;
  regexPattern: string;
  branchOption: BranchOption;
  setBranchOption: (option: BranchOption) => void;
  branchMaxAgeDays: number;
  setBranchMaxAgeDays: (days: number) => void;
  /**
   * When provided, the per-repository branch override panel is rendered
   * below the project-level config so users can override settings per repo.
   * Existing (un-saved) projects pass undefined so the panel stays hidden.
   */
  projectId?: number | string | null;
  /**
   * Repository visibility scope for the project ("public" | "private").
   * Determines which repositories are shown in the available list.
   */
  visibilityScope?: VisibilityScope;
  validationRepo?: string | null;
  setValidationRepo?: (repo: string | null) => void;
  preflightRequired?: boolean;
  setPreflightRequired?: (required: boolean) => void;
}

const RepositoriesAndBranches: React.FC<RepositoriesAndBranchesProps> = ({
  user,
  repos,
  setRepos,
  selectedRepos,
  setSelectedRepos,
  setRegexPattern,
  regexPattern,
  branchOption,
  setBranchOption,
  branchMaxAgeDays,
  setBranchMaxAgeDays,
  projectId,
  visibilityScope = "public",
  validationRepo = null,
  setValidationRepo,
  preflightRequired = false,
  setPreflightRequired,
}) => {
  const [reposLoading, setReposLoading] = useState<boolean>(false);
  const [reposError, setReposError] = useState<string | null>(null);

  const loadRepos = React.useCallback(() => {
    if (!user) return;
    setReposLoading(true);
    setReposError(null);
    fetchRepos(user)
      .then((fetchedRepos) => {
        if (Array.isArray(fetchedRepos)) {
          // fetchRepos resolves to unknown[] - the API response shape is only
          // known here, so this is the boundary that asserts it.
          setRepos(fetchedRepos as Repository[]);
        } else if (fetchedRepos && typeof fetchedRepos === "object" && "error" in fetchedRepos) {
          setReposError(String(fetchedRepos.error || "Failed to load repositories"));
          setRepos([]);
        } else {
          console.error("❌ Error: Unexpected repository format:", fetchedRepos);
          setRepos([]);
        }
      })
      .finally(() => setReposLoading(false));
  }, [user, setRepos]);

  // ✅ Fetch Repositories
  useEffect(() => {
    loadRepos();
  }, [loadRepos]);

  const handleRemoveRepo = (repoToRemove: string) => {
    setSelectedRepos(selectedRepos.filter((repo) => repo !== repoToRemove));
  };

  const handleAddRepo = (repoName: string) => {
    if (!selectedRepos.includes(repoName)) {
      setSelectedRepos([...selectedRepos, repoName]);
    }
  };

  const handleClearSelectedRepos = () => {
    setSelectedRepos([]);
  };

  const handleBranchOptionChange = (option: BranchOption) => {
    setBranchOption(option);
    if (option === "default") {
      setRegexPattern(""); // Clear regex pattern when switching to Default
    }
  };

  const handleRegexChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setRegexPattern(e.target.value);
  };

  const handleMaxAgeDaysChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = Number.parseInt(e.target.value, 10);
    if (!Number.isNaN(value)) {
      // Clamp value to valid range
      const clampedValue = Math.max(1, Math.min(30, value));
      setBranchMaxAgeDays(clampedValue);
    }
  };

  // Filter repositories by the project's visibility scope — mirrors the same
  // logic in NewProject.tsx so both creation and configuration show the same
  // filtered list. This ensures a private project can only select/show private
  // repos, and a public project can only select/show public repos.
  const scopedRepos = repos.filter((repo) =>
    repoMatchesVisibilityScope(repo, visibilityScope),
  );

  return (
    <div className="flex flex-col gap-6">
      {/* Project Default Branch Configuration - Full Width */}
      <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4 pb-2 border-b border-slate-200 dark:border-slate-700">
          🌿 Project Default Branch Configuration
        </h3>

        <div className="space-y-4">
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm text-slate-800 dark:text-slate-200 cursor-pointer">
              <input
                type="radio"
                name="branchOption"
                value="default"
                checked={branchOption === "default"}
                onChange={() => handleBranchOptionChange("default")}
                className="w-4 h-4"
              />
              <span className="font-medium">Default branch</span>
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-800 dark:text-slate-200 cursor-pointer">
              <input
                type="radio"
                name="branchOption"
                value="pattern"
                checked={branchOption === "pattern"}
                onChange={() => handleBranchOptionChange("pattern")}
                className="w-4 h-4"
              />
              <span className="font-medium">Branch name or pattern</span>
            </label>
          </div>

          {branchOption === "pattern" && (
            <div className="mt-4 p-4 bg-slate-50 dark:bg-slate-900/50 rounded-md border border-slate-200 dark:border-slate-700">
              <div className="space-y-4">
                <div>
                  <label htmlFor="repo-branch-pattern" className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                    Branch name or pattern
                  </label>
                  <input
                    id="repo-branch-pattern"
                    type="text"
                    placeholder="e.g., main, release-.*, feature/auth"
                    value={regexPattern}
                    onChange={handleRegexChange}
                    className="w-full rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                    Max branch age: {branchMaxAgeDays} days
                  </label>
                  <div className="flex items-center gap-4">
                    <input
                      type="range"
                      min="1"
                      max="30"
                      value={branchMaxAgeDays}
                      onChange={handleMaxAgeDaysChange}
                      className="flex-1 h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer"
                    />
                    <input
                      type="number"
                      min="1"
                      max="30"
                      value={branchMaxAgeDays}
                      onChange={handleMaxAgeDaysChange}
                      className="w-20 rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 text-center focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
                    Only branches with commits in the last {branchMaxAgeDays} days will be targeted
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <div>
        <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-1">
          Target Repositories
        </h3>
        <p className="text-sm text-slate-600 dark:text-slate-400 mb-3">
          These repositories receive workflow changes during PR Campaigns.
        </p>
      </div>

      {/* Unified horizontal repository selector + branch configuration. */}
      <RepositoryBranchSelector
        availableRepositories={scopedRepos}
        selectedRepositoryNames={selectedRepos}
        visibilityScope={visibilityScope}
        loading={reposLoading}
        error={reposError}
        onSelectRepository={handleAddRepo}
        onRemoveRepository={handleRemoveRepo}
        onClearSelectedRepositories={handleClearSelectedRepos}
        onRefresh={loadRepos}
        branchConfigSlot={
          projectId ? (
            <RepoBranchOverridesPanel
              user={user}
              projectId={projectId}
              selectedRepos={selectedRepos}
              onRemoveRepo={handleRemoveRepo}
              branchOption={branchOption}
              regexPattern={regexPattern}
              branchMaxAgeDays={branchMaxAgeDays}
            />
          ) : (
            <div className="rounded-md border border-dashed border-slate-300 px-3 py-6 text-center text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400">
              Save the project to configure per-repository branch overrides.
            </div>
          )
        }
      />

      <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-2">
          Validation Repository
        </h3>
        <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
          Optional. Used to test workflow changes before creating PR Campaigns.
        </p>
        {/* Descriptive text, not a form label — the select below carries its own aria-label. */}
        <p className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
          Select a safe repository where ActionsManager can open a test PR and run the generated workflow before rollout.
        </p>
        <select
          value={validationRepo || ""}
          onChange={(event) => setValidationRepo?.(event.target.value || null)}
          className="w-full rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          aria-label="Validation Repository"
        >
          <option value="">No validation repository</option>
          {scopedRepos.map((repo) => {
            const name = repo.full_name || repo.name;
            return (
              <option key={repo.id || name} value={name}>
                {name}
              </option>
            );
          })}
        </select>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
          This repository is not included in campaign targets unless it is also selected as a target repository.
        </p>
        {validationRepo && !scopedRepos.some((repo) => (repo.full_name || repo.name) === validationRepo) && (
          <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            Validation repository is not currently accessible in the repository list.
          </div>
        )}
        <label className="mt-4 flex items-center gap-2 text-sm text-slate-800 dark:text-slate-200">
          <input
            type="checkbox"
            checked={preflightRequired}
            onChange={(event) => setPreflightRequired?.(event.target.checked)}
            disabled={!validationRepo}
            className="w-4 h-4"
          />
          <span>Require successful preflight before campaign creation</span>
        </label>
      </div>
    </div>
  );
};

export default RepositoriesAndBranches;