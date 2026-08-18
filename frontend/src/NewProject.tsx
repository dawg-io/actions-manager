/* eslint-disable no-restricted-syntax -- Legacy: TODO migrate inline styles to Tailwind CSS classes */
import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router";
import { saveProject } from "./api/projects";
import { Button } from "./components/ui/button";
import { PROJECT_TYPE_CONFIG, ProjectType } from "./utils/projectTypeConfig";
import { RWX_ONLY_PROJECT_COLOR_KEYS, type ProjectColorKey } from "./utils/projectColors";
import ProjectBasicsStep from "./components/ProjectBasicsStep";
import RepositoriesStep from "./components/RepositoriesStep";
import ReviewStep from "./components/ReviewStep";
import { toast } from "./utils/toast";
import { tour, TourStepId } from "./utils/tour";
import { useTourDemoSeeding } from "./hooks/useTourDemoSeeding";
import { useNewProjectAccount, useNewProjectRepos } from "./hooks/useNewProjectData";
import {
  validateProjectInputs,
  describeProjectLimitError,
  repoMatchesVisibilityScope,
} from "./utils/newProjectValidation";
import { getDocsUrl } from "./help/helpLinks";
import { SELF_HOSTED_BETA_CALLER_LIMIT, SELF_HOSTED_BETA_RWX_LIMIT } from "./utils/accountTier";

// TypeScript interfaces
interface Repository {
  id: string | number;
  name: string;
  full_name: string;
  private: boolean;
  default_branch: string;
  permissions?: any;
}

// Repository visibility scope for the project. A "mixed" option is
// intentionally NOT supported — projects must be either public-only or
// private-only.
type VisibilityScope = "public" | "private";
type WizardStep = 1 | 2 | 3;
const FINAL_WIZARD_STEP = 3;
const RESOURCE_PREFIX_TEMPLATE = "AM_{PROJECT_CODE}_";

// Leaving a wizard step is what completes the tour step attached to it. Kept
// here rather than read out of the component's state by the tour, so the
// wizard stays the only thing that knows how its own steps advance.
const TOUR_STEP_FOR_WIZARD_STEP: Record<number, TourStepId> = {
  1: "project-basics",
  2: "pick-repos",
};

/**
 * Where to land after a project is created.
 *
 * On the tour, into the project itself: the next step is inside it, and the
 * dashboard detour is where users got stranded. Records the name so the tour
 * can point back at the project's card if they navigate away.
 */
function destinationAfterCreate(user: string, createdName: string): string {
  if (!tour.isActive()) return `/project/${user}`;
  tour.demoProjectName = createdName;
  return `/project/${user}/${encodeURIComponent(createdName)}`;
}

/** Row for a repository the tour just created, so the picker can show it. */
function demoRepoEntry(fullName: string, scope: VisibilityScope): Repository {
  return {
    id: fullName,
    name: fullName.split("/").pop() || fullName,
    full_name: fullName,
    private: scope === "private",
    default_branch: "main",
  };
}

/** Whether the wizard may leave the given step. */
function stepIsComplete(
  step: WizardStep,
  validity: { projectNameIsValid: boolean; step2IsValid: boolean; formIsValid: boolean },
): boolean {
  if (step === 1) return validity.projectNameIsValid;
  if (step === 2) return validity.step2IsValid;
  return validity.formIsValid;
}

interface NewProjectProps {
  user: string;
  /** Current guided-tour step, or null. Drives the demo pre-fill. */
  tourStep?: string | null;
}

interface ProjectData {
  github_user: string;
  project_name: string;
  custom_project_key: string | null;
  selected_repos: string[];
  workflows: any[];
  rxworkflows: any[];
  branch_regex: string;
  branch_option: string;
  branch_max_age_days: number;
  reusable_workflows_enabled: boolean;
  use_prefix: boolean;
  project_type: "standard" | "rwx";
  repository_visibility_scope: VisibilityScope;
  project_color: ProjectColorKey;
}

interface ErrorResponse {
  response?: {
    status: number;
    data?: {
      detail?: string;
    };
  };
}

const NewProject: React.FC<NewProjectProps> = ({ user, tourStep = null }) => {
  const navigate = useNavigate();
  const [projectType, setProjectType] = useState<ProjectType>("standard");
  const [projectName, setProjectName] = useState<string>("");
  const [projectKey, setProjectKey] = useState<string>("");
  const [useCustomKey, setUseCustomKey] = useState<boolean>(false);
  const [usePrefix, setUsePrefix] = useState<boolean | null>(null);
  const [projectColor, setProjectColor] = useState<ProjectColorKey>("blue");
  const [selectedRepos, setSelectedRepos] = useState<string[]>([]);
  const [isCreating, setIsCreating] = useState<boolean>(false);
  const [currentStep, setCurrentStep] = useState<WizardStep>(1);
  const [advancedOptionsOpen, setAdvancedOptionsOpen] = useState<boolean>(false);
  const [projectNameTouched, setProjectNameTouched] = useState<boolean>(false);
  // Repository visibility scope — must be selected (defaults to "public").
  const [visibilityScope, setVisibilityScope] = useState<VisibilityScope>("public");
  const [rwxHelpOpen, setRwxHelpOpen] = useState<boolean>(false);

  const { accountType, installationMode, betaCallerCount, betaRwxCount } =
    useNewProjectAccount(user);

  // Normalize tier name. The backend treats "pro" as an alias for "professional".
  const normalizedTier = (accountType || "free").toLowerCase().replace(/^pro$/, "professional");
  const isSelfHostedBeta = installationMode?.toLowerCase() === "self-hosted";
  // In self-hosted beta, private repos are always allowed when credentials permit.
  // On cloud, only Professional/Enterprise accounts may use private repos.
  const isFreeTier = !isSelfHostedBeta && (!accountType || normalizedTier === "free");
  const privateAllowedByTier = !isFreeTier;

  // Per-type limit flags for self-hosted beta project creation UI.
  const betaCallerLimitReached = isSelfHostedBeta && betaCallerCount >= SELF_HOSTED_BETA_CALLER_LIMIT;
  const betaRwxLimitReached = isSelfHostedBeta && betaRwxCount >= SELF_HOSTED_BETA_RWX_LIMIT;

  useTourDemoSeeding({
    user,
    tourStep,
    setProjectName,
    setProjectColor,
    setUsePrefix,
  });

  const { repos, setRepos, loading: reposLoading, error: reposError } = useNewProjectRepos(
    user,
    projectType,
    // Selection is meaningless across a type change: the two types list
    // different repositories.
    () => setSelectedRepos([]),
  );

  // Purple/green are the only colors for Reusable Workflow Projects; the other
  // six are for Caller Workflow Projects. Reset when switching project type.
  useEffect(() => {
    if (projectType === "rwx" && !RWX_ONLY_PROJECT_COLOR_KEYS.includes(projectColor)) {
      setProjectColor("purple");
    }
    if (projectType !== "rwx" && RWX_ONLY_PROJECT_COLOR_KEYS.includes(projectColor)) {
      setProjectColor("blue");
    }
  }, [projectType, projectColor]);

  const handleCreateProject = async (): Promise<void> => {
    const validationError = validateProjectInputs({
      projectName,
      selectedRepos,
      repos,
      visibilityScope,
      privateAllowedByTier,
      useCustomKey,
      projectKey,
    });
    if (validationError) {
      toast.error(validationError);
      return;
    }

    // Runtime check that should never fail if validation is correct
    if (usePrefix === null) {
      toast.error("Please select a Resource Naming Mode before creating the project.");
      return;
    }

    setIsCreating(true);

    try {
      // Create project with only basic data - no workflows
      const projectData: ProjectData = {
        github_user: user,
        project_name: projectName.trim(),
        custom_project_key: useCustomKey ? projectKey.trim() : null,
        selected_repos: selectedRepos,
        workflows: [], // Empty workflows array
        rxworkflows: [], // Empty reusable workflows array
        branch_regex: "",
        branch_option: "default",
        branch_max_age_days: 30,
        reusable_workflows_enabled: projectType === "rwx",
        use_prefix: usePrefix,
        project_type: projectType,
        repository_visibility_scope: visibilityScope,
        project_color: projectColor,
      };

      await saveProject(projectData);

      toast.success("Project created successfully! You can now add workflows to it.");
      // Real completion signal for the guided tour. Fired here rather than on
      // the route change because Cancel navigates to the same place.
      tour.completed("naming-mode");
      navigate(destinationAfterCreate(user, projectName.trim()));
    } catch (error) {
      console.error("❌ Error creating project:", error);

      const errorResponse = error as ErrorResponse;
      if (errorResponse.response?.status === 403) {
        const errorMessage = errorResponse.response?.data?.detail || "Project limit reached";
        toast.error(describeProjectLimitError(errorMessage));
      } else {
        toast.error("Error creating project. Please try again.");
      }
    } finally {
      setIsCreating(false);
    }
  };

  const handleRemoveRepo = (repoToRemove: string): void => {
    setSelectedRepos(selectedRepos.filter((repo) => repo !== repoToRemove));
  };

  // Repositories matching the selected visibility scope. The picker
  // component owns its own search input, so we pre-filter only by scope here.
  const scopedRepos = repos.filter((repo) =>
    repoMatchesVisibilityScope(repo, visibilityScope),
  );
  const projectNameIsValid = projectName.trim().length > 0;
  const projectNameError = projectNameIsValid ? "" : "Project name is required.";
  const showProjectNameError = projectNameTouched && !projectNameIsValid;
  const projectNameDescriptionIds = [
    "project-name-help",
    showProjectNameError ? "project-name-error" : null,
  ].filter(Boolean).join(" ");
  const stepLabels = ["Project Basics", "Repositories", "Review"] as const;
  const getProjectTypeLabel = (type: ProjectType): string => PROJECT_TYPE_CONFIG[type].label;
  const projectTypeLabel = getProjectTypeLabel(projectType);
  const visibilityLabel = visibilityScope === "private" ? "Private repositories" : "Public repositories";
  const namingLabel = usePrefix === null ? "Not selected" : usePrefix ? "Prefix Mode" : "No Prefix Mode";
  const advancedOptionsVisible = advancedOptionsOpen || useCustomKey;
  const step2IsValid =
    selectedRepos.length > 0 &&
    !(visibilityScope === "private" && !privateAllowedByTier);
  const step3IsValid = usePrefix !== null; // Naming mode must be explicitly selected
  const formIsValid =
    projectNameIsValid &&
    step2IsValid &&
    step3IsValid;
  const canContinue = stepIsComplete(currentStep, {
    projectNameIsValid,
    step2IsValid,
    formIsValid,
  });

  const handleNextStep = (): void => {
    if (!canContinue || currentStep === FINAL_WIZARD_STEP) return;
    const completedTourStep = TOUR_STEP_FOR_WIZARD_STEP[currentStep];
    if (completedTourStep) tour.completed(completedTourStep);
    setCurrentStep((step) => Math.min(step + 1, FINAL_WIZARD_STEP) as WizardStep);
  };

  const handlePreviousStep = (): void => {
    setCurrentStep((step) => Math.max(step - 1, 1) as WizardStep);
  };

  const findRepoByName = (name: string): Repository | undefined =>
    repos.find((r) => (r.full_name || r.name) === name);

  const repoStillMatchesScope = (name: string, scope: VisibilityScope): boolean => {
    const repo = findRepoByName(name);
    if (!repo) return true; // keep unknown repos; backend will validate
    return repoMatchesVisibilityScope(repo, scope);
  };

  // Switching the visibility scope must clear any already-selected repositories
  // that no longer match — otherwise the user could submit a mismatched set.
  const handleVisibilityScopeChange = (next: VisibilityScope): void => {
    if (next === visibilityScope) return;
    setVisibilityScope(next);
    setSelectedRepos((prev) => prev.filter((name) => repoStillMatchesScope(name, next)));
  };

  const handleAddRepo = (repoName: string): void => {
    if (!selectedRepos.includes(repoName)) {
      setSelectedRepos([...selectedRepos, repoName]);
    }
  };

  const handleClearSelectedRepos = (): void => {
    setSelectedRepos([]);
  };

  // The repository list was fetched before this repo existed, so add it to the
  // picker directly rather than refetching — the user must see it selected
  // immediately, not after a round trip.
  const handleDemoRepoCreated = (fullName: string): void => {
    setRepos((previous) =>
      previous.some((r) => (r.full_name || r.name) === fullName)
        ? previous
        : [...previous, demoRepoEntry(fullName, visibilityScope)],
    );
    handleAddRepo(fullName);
  };

  return (
    <div className="newProjectContainer w-full max-w-[1400px] mx-auto px-6 lg:px-8">
      <div className="mb-6">
        <p className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">
          Guided setup
        </p>
        <h2 className="text-3xl font-bold text-gray-900 dark:text-white">Create Project</h2>
        <p className="mt-2 max-w-2xl text-sm text-gray-600 dark:text-slate-300">
          Follow three short steps to define the project, choose repositories, and review resource naming.{" "}
          <a
            className="font-medium text-blue-600 dark:text-blue-400 hover:underline"
            href={getDocsUrl("projects")}
            rel="noreferrer"
            target="_blank"
          >
            Learn more →
          </a>
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-5">
          <div className="rounded-xl border border-border dark:border-border-dark bg-container dark:bg-container-dark p-4">
            <ol className="grid gap-2 sm:grid-cols-3">
              {stepLabels.map((label, index) => {
                const stepNumber = (index + 1) as WizardStep;
                const isActive = currentStep === stepNumber;
                const isComplete = currentStep > stepNumber;
                return (
                  <li
                    key={label}
                    className={`rounded-lg border px-3 py-2 text-sm ${
                      isActive
                        ? "border-blue-500 bg-blue-500/10 text-gray-900 dark:text-white"
                        : isComplete
                          ? "border-emerald-500/50 bg-emerald-500/10 text-gray-900 dark:text-white"
                          : "border-gray-200 dark:border-slate-700 text-gray-500 dark:text-slate-400"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="flex h-6 w-6 items-center justify-center rounded-full border border-current text-xs font-semibold">
                        {isComplete ? "✓" : stepNumber}
                      </span>
                      <span className="font-medium">{label}</span>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>

          <section className="rounded-xl border border-border dark:border-border-dark bg-container dark:bg-container-dark p-5 shadow-sm">
            {currentStep === 1 && (
              <ProjectBasicsStep
                betaCallerLimitReached={betaCallerLimitReached}
                betaRwxLimitReached={betaRwxLimitReached}
                projectColor={projectColor}
                projectName={projectName}
                projectNameDescriptionIds={projectNameDescriptionIds}
                projectNameError={projectNameError}
                projectType={projectType}
                setProjectColor={setProjectColor}
                setProjectName={setProjectName}
                setProjectNameTouched={setProjectNameTouched}
                setProjectType={setProjectType}
                showProjectNameError={showProjectNameError}
              />
            )}

            {currentStep === 2 && (
              <RepositoriesStep
                handleAddRepo={handleAddRepo}
                handleClearSelectedRepos={handleClearSelectedRepos}
                handleRemoveRepo={handleRemoveRepo}
                handleVisibilityScopeChange={handleVisibilityScopeChange}
                isSelfHostedBeta={isSelfHostedBeta}
                privateAllowedByTier={privateAllowedByTier}
                repos={repos}
                projectType={projectType}
                reposError={reposError}
                reposLoading={reposLoading}
                rwxHelpOpen={rwxHelpOpen}
                scopedRepos={scopedRepos}
                selectedRepos={selectedRepos}
                setRwxHelpOpen={setRwxHelpOpen}
                setSelectedRepos={setSelectedRepos}
                onDemoRepoCreated={handleDemoRepoCreated}
                user={user}
                visibilityScope={visibilityScope}
              />
            )}

            {currentStep === 3 && (
              <ReviewStep
                advancedOptionsVisible={advancedOptionsVisible}
                formIsValid={formIsValid}
                handleCreateProject={handleCreateProject}
                isCreating={isCreating}
                projectKey={projectKey}
                setAdvancedOptionsOpen={setAdvancedOptionsOpen}
                setProjectKey={setProjectKey}
                setUseCustomKey={setUseCustomKey}
                setUsePrefix={setUsePrefix}
                useCustomKey={useCustomKey}
                usePrefix={usePrefix}
              />
            )}
          </section>

          <div className="flex flex-col gap-3 sm:flex-row sm:justify-between">
            <Button
              type="button"
              variant="outline"
              onClick={handlePreviousStep}
              disabled={currentStep === 1 || isCreating}
            >
              Back
            </Button>
            {currentStep < FINAL_WIZARD_STEP && (
              <Button
                type="button"
                data-testid="wizard-continue"
                onClick={handleNextStep}
                disabled={!canContinue || isCreating}
              >
                Continue
              </Button>
            )}
          </div>
        </div>

        <aside className="rounded-xl border border-border dark:border-border-dark bg-container dark:bg-container-dark p-5 shadow-sm lg:sticky lg:top-4 lg:self-start">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Project Summary</h3>
          <dl className="mt-4 space-y-3 text-sm">
            <div>
              <dt className="text-xs uppercase tracking-wide text-gray-500 dark:text-slate-400">Name</dt>
              <dd className="mt-1 text-gray-900 dark:text-white">{projectName.trim() || "Not set"}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-gray-500 dark:text-slate-400">Type</dt>
              <dd className="mt-1 text-gray-900 dark:text-white">
                {projectTypeLabel}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-gray-500 dark:text-slate-400">Visibility</dt>
              <dd className="mt-1 text-gray-900 dark:text-white">{visibilityLabel}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-gray-500 dark:text-slate-400">Naming</dt>
              <dd className="mt-1 text-gray-900 dark:text-white">{namingLabel}</dd>
            </div>
            {useCustomKey && (
              <div>
                <dt className="text-xs uppercase tracking-wide text-gray-500 dark:text-slate-400">Project Key</dt>
                <dd className="mt-1 text-gray-900 dark:text-white">{projectKey.trim() || "Not set"}</dd>
              </div>
            )}
            <div>
              <dt className="text-xs uppercase tracking-wide text-gray-500 dark:text-slate-400">Repositories</dt>
              <dd className="mt-1 text-gray-900 dark:text-white">
                {selectedRepos.length === 1
                  ? "1 selected"
                  : `${selectedRepos.length} selected`}
              </dd>
              {selectedRepos.length > 0 && (
                <ul className="mt-2 space-y-1 text-xs text-gray-600 dark:text-slate-300">
                  {selectedRepos.slice(0, 5).map((repo) => (
                    <li key={repo} className="truncate">
                      {repo}
                    </li>
                  ))}
                  {selectedRepos.length > 5 && (
                    <li>+{selectedRepos.length - 5} more</li>
                  )}
                </ul>
              )}
            </div>
          </dl>
        </aside>
      </div>
    </div>
  );
};

export default NewProject;
