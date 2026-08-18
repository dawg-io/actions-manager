import React from 'react';
import RepositoryBranchSelector from './RepositoryBranchSelector';
import { Label } from './ui/label';
import CreateDemoRepoButton from './CreateDemoRepoButton';
import { tour } from '../utils/tour';
import { repoMatchesVisibilityScope } from '../utils/newProjectValidation';
import { optionCardClass } from './ProjectBasicsStep';

/** Why a scope is or is not available, which differs between cloud and beta. */
function visibilityHelperText(isPrivate: boolean, isSelfHostedBeta: boolean): string {
  if (!isPrivate) return 'Use this project for public GitHub repositories only.';
  return isSelfHostedBeta
    ? 'Use this project for private GitHub repositories only. Requires GitHub credentials with private repository access.'
    : 'Use this project for private GitHub repositories only. Private repositories require a Professional or Enterprise plan and the correct GitHub permissions.';
}
import { getDocsUrl } from '../help/helpLinks';
import type { ProjectType } from '../utils/projectTypeConfig';

const FINAL_WIZARD_STEP = 3;

type VisibilityScope = 'public' | 'private';

interface Repository {
  id: string | number;
  name: string;
  full_name: string;
  private: boolean;
  default_branch: string;
  permissions?: any;
}

export interface RepositoriesStepProps {
  readonly projectType: ProjectType;
  readonly user: string;
  readonly visibilityScope: VisibilityScope;
  readonly handleVisibilityScopeChange: (scope: VisibilityScope) => void;
  readonly privateAllowedByTier: boolean;
  readonly isSelfHostedBeta: boolean;
  readonly repos: Repository[];
  readonly scopedRepos: Repository[];
  readonly selectedRepos: string[];
  readonly reposLoading: boolean;
  readonly reposError: string | null;
  readonly rwxHelpOpen: boolean;
  readonly setRwxHelpOpen: (update: (open: boolean) => boolean) => void;
  readonly handleAddRepo: (name: string) => void;
  readonly handleRemoveRepo: (name: string) => void;
  readonly handleClearSelectedRepos: () => void;
  readonly setSelectedRepos: (names: string[]) => void;
  /** Adds a tour-created repository to the picker and selects it. */
  readonly onDemoRepoCreated: (fullName: string) => void;
}

/** Wizard step 2: repository visibility scope and selection. */
const RepositoriesStep: React.FC<RepositoriesStepProps> = ({
  projectType,
  user,
  visibilityScope,
  handleVisibilityScopeChange,
  privateAllowedByTier,
  isSelfHostedBeta,
  repos,
  scopedRepos,
  selectedRepos,
  reposLoading,
  reposError,
  rwxHelpOpen,
  setRwxHelpOpen,
  handleAddRepo,
  handleRemoveRepo,
  handleClearSelectedRepos,
  setSelectedRepos,
  onDemoRepoCreated,
}) => (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">
          Step 2 of {FINAL_WIZARD_STEP}
        </p>
        <h3 className="mt-1 text-2xl font-semibold text-gray-900 dark:text-white">
          Repository Visibility and Selection
        </h3>
        <p className="mt-2 text-sm text-gray-600 dark:text-slate-300">
          Choose the visibility scope first, then select repositories from the existing picker.
        </p>
      </div>

      <div>
        <Label className="mb-3 block text-sm font-semibold text-gray-900 dark:text-white">Repository Visibility:</Label>
        <div className="grid gap-3 md:grid-cols-2">
          {(["public", "private"] as VisibilityScope[]).map((scope) => {
            const isSelected = visibilityScope === scope;
            const isPrivate = scope === "private";
            const isDisabled = isPrivate && !privateAllowedByTier;
            const labelText = isPrivate ? "Private repositories" : "Public repositories";
            const helperText = visibilityHelperText(isPrivate, isSelfHostedBeta);
            return (
              <label
                key={scope}
                data-testid={`visibility-option-${scope}`}
                className={`flex gap-3 rounded-lg border p-4 transition focus-within:ring-2 focus-within:ring-blue-400 ${optionCardClass(
                  isDisabled,
                  isSelected,
                  "cursor-not-allowed border-gray-200 dark:border-slate-700 bg-gray-100 dark:bg-slate-800/60 opacity-60",
                  "cursor-pointer border-blue-500 bg-blue-500/10",
                  "cursor-pointer border-gray-200 dark:border-slate-700 bg-gray-100 dark:bg-slate-800/60 hover:border-blue-400/60",
                )}`}
              >
                <input
                  type="radio"
                  name="repositoryVisibilityScope"
                  value={scope}
                  checked={isSelected}
                  disabled={isDisabled}
                  onChange={() => handleVisibilityScopeChange(scope)}
                  className="mt-1"
                />
                <span className="flex-1">
                  <span className="flex items-center gap-2 font-semibold text-gray-900 dark:text-white">
                    {labelText}
                    {isSelected && <span className="ml-auto text-blue-600 dark:text-blue-400">✓</span>}
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-gray-600 dark:text-slate-300">
                    {helperText}
                  </span>
                  {isDisabled && (
                    <span className="mt-2 block text-xs font-medium text-red-600 dark:text-red-400">
                      ⚠️ Free plan accounts cannot create private repository projects. Upgrade to Professional or Enterprise to enable this option.
                    </span>
                  )}
                </span>
              </label>
            );
          })}
        </div>
      </div>

      <div data-testid="repo-picker">
        <h4 className="text-lg font-semibold text-gray-900 dark:text-white">
          {projectType === "rwx" ? "Select Reusable Workflow Repository" : "Select Repositories"}
        </h4>

        {projectType === "rwx" && (
          <p className="mb-3 mt-1 text-sm text-gray-600 dark:text-slate-300">
            Select the repository that will store your reusable workflow definitions. This is usually a dedicated repository (for example, <code>reusable-workflows</code>), not one of your application repositories.
          </p>
        )}

        <p
          data-testid="visibility-scope-note"
          className="mb-3 mt-1 text-xs text-gray-500 dark:text-slate-400"
        >
          {visibilityScope === "private"
            ? "Showing private repositories only."
            : "Showing public repositories only."}
        </p>

        {projectType === "rwx" && reposLoading && (
          <p className="mb-2 text-sm text-gray-600 dark:text-slate-300">⏳ Loading reusable workflow repositories…</p>
        )}
        {projectType === "rwx" && !reposLoading && reposError && (
          <div className="mb-3 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-700 dark:bg-red-950 dark:text-red-200">
            <strong>⚠️ Could not load reusable workflow repositories.</strong>
            <div className="mt-1">{reposError}</div>
            <div className="mt-1 text-xs opacity-80">
              Verify the signed-in account (or its GitHub App installation)
              has access to the target organization, and that the repository
              has the <code>am-rwx</code> topic, then try again.
            </div>
          </div>
        )}
        {projectType === "rwx" && !reposLoading && !reposError && repos.length === 0 && (
          <div className="mb-3 rounded-lg border border-gray-200 dark:border-slate-600 bg-gray-100 dark:bg-slate-800/60 p-4 text-sm text-gray-600 dark:text-slate-300">
            <p className="font-semibold text-gray-900 dark:text-white mb-1">No reusable workflow repository selected yet.</p>
            <p>
              No repositories with the <code>am-rwx</code> topic were found in your accessible GitHub accounts or organizations.
              Create or select a repository such as <code>reusable-workflows</code>, add the <code>am-rwx</code> topic to it, then add workflow files under <code>.github/workflows/</code>. Each reusable workflow must use <code>on: workflow_call</code>.
            </p>
          </div>
        )}

        {projectType !== "rwx" && repos.length > 0 &&
          repos.filter((r) => repoMatchesVisibilityScope(r, visibilityScope)).length === 0 && (
          <p
            data-testid="visibility-empty-state"
            className="mb-2 text-sm text-gray-600 dark:text-slate-300"
          >
            {visibilityScope === "private"
              ? "⚠️ No private repositories were found for this GitHub account, or private repository access is not available."
              : "⚠️ No public repositories were found for this GitHub account."}
          </p>
        )}

        {tour.isActive() && projectType !== "rwx" && (
        <CreateDemoRepoButton
          onCreated={onDemoRepoCreated}
          user={user}
          visibility={visibilityScope}
        />
      )}

      <RepositoryBranchSelector
          availableRepositories={scopedRepos as any}
          selectedRepositoryNames={selectedRepos}
          visibilityScope={visibilityScope}
          loading={reposLoading}
          error={reposError}
          onSelectRepository={handleAddRepo}
          onRemoveRepository={handleRemoveRepo}
          onClearSelectedRepositories={handleClearSelectedRepos}
          onReplaceSelection={setSelectedRepos}
          singleSelect={projectType === "rwx"}
          resetSearchKey={projectType}
          searchPlaceholder={
            projectType === "rwx"
              ? "Search reusable workflow repositories..."
              : "Search repositories by name, owner, organization, or account..."
          }
        />

        {projectType === "rwx" && (
          <div className="mt-4 rounded-lg border border-gray-200 dark:border-slate-700 bg-gray-100 dark:bg-slate-800/60">
            <button
              type="button"
              className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-gray-900 dark:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400"
              aria-expanded={rwxHelpOpen}
              onClick={() => setRwxHelpOpen((open) => !open)}
            >
              What should this repository look like?{' '}
              <span aria-hidden="true">{rwxHelpOpen ? "−" : "+"}</span>
            </button>
            {rwxHelpOpen && (
              <div className="space-y-4 border-t border-gray-200 dark:border-slate-700 p-4 text-sm text-gray-600 dark:text-slate-300">
                <div>
                  <p className="font-semibold text-gray-900 dark:text-white mb-1">Recommended folder structure</p>
                  <pre className="overflow-x-auto rounded bg-gray-50 dark:bg-slate-900 p-3 text-xs text-gray-700 dark:text-slate-200">{`reusable-workflows/
└── .github/
    └── workflows/
        ├── reusable-node-ci.yml
        ├── reusable-python-ci.yml
        └── reusable-docker-build.yml`}</pre>
                  <p className="mt-2 text-xs text-gray-500 dark:text-slate-400">
                    Example workflow path: <code>.github/workflows/reusable-node-ci.yml</code>
                  </p>
                </div>

                <div>
                  <p className="font-semibold text-gray-900 dark:text-white mb-1">Example reusable workflow</p>
                  <pre className="overflow-x-auto rounded bg-gray-50 dark:bg-slate-900 p-3 text-xs text-gray-700 dark:text-slate-200">{`name: Reusable Node CI

on:
  workflow_call:
    inputs:
      node-version:
        description: Node.js version to use
        required: false
        type: string
        default: "24"
    secrets:
      NPM_TOKEN:
        required: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-node@v6
        with:
node-version: \${{ inputs.node-version }}
cache: npm
      - run: npm ci
      - run: npm test -- --watch=false
      - run: npm run build`}</pre>
                </div>

                <div>
                  <p className="font-semibold text-gray-900 dark:text-white mb-1">Example caller workflow</p>
                  <pre className="overflow-x-auto rounded bg-gray-50 dark:bg-slate-900 p-3 text-xs text-gray-700 dark:text-slate-200">{`name: Node CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  node-ci:
    uses: YOUR_ORG_OR_USER/reusable-workflows/.github/workflows/reusable-node-ci.yml@main
    with:
      node-version: "24"
    secrets: inherit`}</pre>
                  <p className="mt-2 text-xs text-gray-500 dark:text-slate-400">
                    Replace <code>YOUR_ORG_OR_USER</code> and <code>reusable-workflows</code> with your actual GitHub owner and repository name.
                  </p>
                </div>

                <div className="rounded-lg border border-amber-400/50 bg-amber-500/10 p-3 text-xs text-amber-900 dark:text-amber-100">
                  <strong>Beta tip:</strong> For beta testing, <code>@main</code> is the simplest reference. For production-style usage, prefer a version tag (for example <code>@v1.0.0</code>) or a release branch so caller repositories do not change unexpectedly when you push to <code>main</code>.
                </div>

                <a
                  className="inline-block text-sm font-medium text-purple-600 dark:text-purple-400 hover:underline"
                  href={getDocsUrl("reusableWorkflowSetup")}
                  rel="noreferrer"
                  target="_blank"
                >
                  Full setup guide →
                </a>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
);

export default RepositoriesStep;
