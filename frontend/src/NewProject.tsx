/* eslint-disable no-restricted-syntax -- Legacy: TODO migrate inline styles to Tailwind CSS classes */
import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router";
import { fetchRepos, fetchRwxRepos } from "./api/repos";
import { saveProject, fetchProjects } from "./api/projects";
import { getUserDetails } from "./api/user";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Label } from "./components/ui/label";
import { Checkbox } from "./components/ui/checkbox";
import ProjectColorSelector from "./components/ProjectColorSelector";
import { PROJECT_TYPE_CONFIG, ProjectType } from "./utils/projectTypeConfig";
import { PREFIX_MODE_CONFIG, NO_PREFIX_MODE_CONFIG } from "./utils/prefixModeConfig";
import { RWX_ONLY_PROJECT_COLOR_KEYS, type ProjectColorKey } from "./utils/projectColors";
import RepositoryBranchSelector from "./components/RepositoryBranchSelector";
import { toast } from "./utils/toast";
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

// Single source of truth for matching a repo against a visibility scope.
// Used by the picker filter, the post-change cleanup, and the submit-time
// validation so they cannot drift apart.
function repoMatchesVisibilityScope(repo: Repository, scope: VisibilityScope): boolean {
  const repoIsPrivate = !!repo.private;
  return scope === "private" ? repoIsPrivate : !repoIsPrivate;
}

interface NewProjectProps {
  user: string;
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

const NewProject: React.FC<NewProjectProps> = ({ user }) => {
  const navigate = useNavigate();
  const [projectType, setProjectType] = useState<ProjectType>("standard");
  const [projectName, setProjectName] = useState<string>("");
  const [projectKey, setProjectKey] = useState<string>("");
  const [useCustomKey, setUseCustomKey] = useState<boolean>(false);
  const [usePrefix, setUsePrefix] = useState<boolean | null>(null);
  const [projectColor, setProjectColor] = useState<ProjectColorKey>("blue");
  const [repos, setRepos] = useState<Repository[]>([]);
  const [selectedRepos, setSelectedRepos] = useState<string[]>([]);
  const [isCreating, setIsCreating] = useState<boolean>(false);
  const [rwxLoading, setRwxLoading] = useState<boolean>(false);
  const [reposLoading, setReposLoading] = useState<boolean>(false);
  const [rwxError, setRwxError] = useState<string | null>(null);
  const [reposError, setReposError] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState<WizardStep>(1);
  const [advancedOptionsOpen, setAdvancedOptionsOpen] = useState<boolean>(false);
  const [projectNameTouched, setProjectNameTouched] = useState<boolean>(false);
  // Repository visibility scope — must be selected (defaults to "public").
  const [visibilityScope, setVisibilityScope] = useState<VisibilityScope>("public");
  // Account tier and installation mode — needed to gate the "private" visibility
  // option. Free tier users on cloud require Professional/Enterprise; self-hosted
  // beta allows private repos when GitHub credentials have access.
  const [accountType, setAccountType] = useState<string | null>(null);
  const [installationMode, setInstallationMode] = useState<string | null>(null);
  // Beta per-type project counts — used to disable type options when limits are reached.
  const [betaCallerCount, setBetaCallerCount] = useState<number>(0);
  const [betaRwxCount, setBetaRwxCount] = useState<number>(0);

  const [rwxHelpOpen, setRwxHelpOpen] = useState<boolean>(false);

  // Fetch the caller's account_type and installation_mode so we can disable the
  // "private" visibility option for Free-tier cloud users only.
  // Also fetch project counts in self-hosted beta to enforce per-type limits in the UI.
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    const loadDetails = async () => {
      const details = await getUserDetails(user);
      if (cancelled) return;
      setAccountType(details?.account_type ?? null);
      const mode = details?.installation_mode ?? null;
      setInstallationMode(mode);
      if (mode?.toLowerCase() === "self-hosted") {
        const allProjects = await fetchProjects(user);
        if (cancelled) return;
        const callerCount = allProjects.filter(
          (p) => (p.project_type ?? "standard") === "standard"
        ).length;
        const rwxCount = allProjects.filter(
          (p) => p.project_type === "rwx"
        ).length;
        setBetaCallerCount(callerCount);
        setBetaRwxCount(rwxCount);
      }
    };
    loadDetails();
    return () => {
      cancelled = true;
    };
  }, [user]);

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

  // Fetch repositories when component mounts or project type changes
  useEffect(() => {
    if (!user) return;
    if (projectType === "rwx") {
      setRwxLoading(true);
      setRwxError(null);
      setReposError(null);
      // Clear any previously loaded standard repos so the RWX picker does
      // not briefly render stale (non-RWX) options while the async
      // fetchRwxRepos call is in flight.
      setRepos([]);
      // Auto-discover RWX repos across ALL accessible accounts (personal +
      // every org / GitHub App installation the user can see). The backend
      // mirrors the standard project picker's discovery and filters by the
      // `am-rwx` topic, so the user does not need to type an org login.
      fetchRwxRepos(user).then((fetchedRepos: any) => {
        // Backend returns either a list of repos or an `{error, status}` payload.
        // Distinguish the empty case from a permissions/access failure so the
        // UI can show a clear message instead of a silent empty list.
        if (Array.isArray(fetchedRepos)) {
          setRepos(fetchedRepos);
        } else {
          setRepos([]);
          if (fetchedRepos && (fetchedRepos.error || fetchedRepos.status)) {
            setRwxError(
              typeof fetchedRepos.error === "string"
                ? fetchedRepos.error
                : "Unable to load reusable workflow repositories.",
            );
          }
        }
        setSelectedRepos([]); // Reset selection on type change
        setRwxLoading(false);
      });
    } else {
      setRwxError(null);
      setReposError(null);
      setReposLoading(true);
      fetchRepos(user).then((fetchedRepos: any) => {
        if (Array.isArray(fetchedRepos)) {
          setRepos(fetchedRepos);
        } else if (fetchedRepos && (fetchedRepos.error || fetchedRepos.status)) {
          // Surface real transport / GitHub-API failures instead of falling
          // through to the empty-state UI (which would look like the user
          // has no repos at all).
          setRepos([]);
          setReposError(
            typeof fetchedRepos.error === "string"
              ? fetchedRepos.error
              : "Unable to load repositories.",
          );
        } else {
          console.error("❌ Error: Unexpected repository format:", fetchedRepos);
          setRepos([]);
        }
        setSelectedRepos([]); // Reset selection on type change
        setReposLoading(false);
      });
    }
  }, [user, projectType]);

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

  // Helper function to validate project inputs
  const validateProjectInputs = (): boolean => {
    if (!projectName.trim()) {
      toast.error("Project name cannot be empty.");
      return false;
    }
    
    if (selectedRepos.length === 0) {
      toast.error("Please select at least one repository.");
      return false;
    }

    // Block project creation if any selected repo does not match the chosen
    // visibility scope. This mirrors the backend tier/scope enforcement.
    const mismatched = selectedRepos.filter((name) => {
      const repo = repos.find((r) => (r.full_name || r.name) === name);
      if (!repo) return false; // unknown repo — let backend decide
      return !repoMatchesVisibilityScope(repo, visibilityScope);
    });
    if (mismatched.length > 0) {
      toast.error(
        `The following repositories do not match the selected ` +
          `${visibilityScope === "private" ? "Private" : "Public"} visibility: ` +
          mismatched.join(", ") +
          `. Remove them or change the visibility option.`,
      );
      return false;
    }

    if (visibilityScope === "private" && !privateAllowedByTier) {
      toast.error(
        "Free plan accounts cannot create private repository projects. " +
          "Upgrade to Professional or Enterprise to enable private repository projects.",
      );
      return false;
    }
    
    // Validate custom project key if provided
    if (useCustomKey && projectKey.trim()) {
      const cleanKey = projectKey.trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
      if (cleanKey.length < 2 || cleanKey.length > 10) {
        toast.error("Project key must be 2–10 characters (letters and numbers only).");
        return false;
      }
    }
    
    return true;
  };

  // Helper function to handle project limit errors
  const handleProjectLimitError = (errorMessage: string): void => {
    if (errorMessage.includes("Self-hosted beta")) {
      // Beta-specific errors already contain the right message from the backend
      toast.error(errorMessage);
    } else if (errorMessage.includes("can only create up to 3 projects") || errorMessage.includes("Free accounts")) {
      toast.error("Free plan users can create up to 3 projects. You've reached your limit. Please upgrade to Professional for up to 10 projects.");
    } else if (errorMessage.includes("can create up to 10 projects") || errorMessage.includes("Professional accounts")) {
      toast.error("Professional plan users can create up to 10 projects. You've reached your limit. Please upgrade to Enterprise for unlimited projects.");
    } else {
      toast.error(errorMessage);
    }
  };

  const handleCreateProject = async (): Promise<void> => {
    if (!validateProjectInputs()) {
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
      navigate(`/project/${user}`); // Go back to project list
    } catch (error) {
      console.error("❌ Error creating project:", error);

      const errorResponse = error as ErrorResponse;
      if (errorResponse.response?.status === 403) {
        const errorMessage = errorResponse.response?.data?.detail || "Project limit reached";
        handleProjectLimitError(errorMessage);
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
  const canContinue =
    currentStep === 1
      ? projectNameIsValid
      : currentStep === 2
        ? step2IsValid
        : formIsValid;

  const handleNextStep = (): void => {
    if (!canContinue || currentStep === FINAL_WIZARD_STEP) return;
    setCurrentStep((step) => Math.min(step + 1, FINAL_WIZARD_STEP) as WizardStep);
  };

  const handlePreviousStep = (): void => {
    setCurrentStep((step) => Math.max(step - 1, 1) as WizardStep);
  };

  // Switching the visibility scope must clear any already-selected repositories
  // that no longer match — otherwise the user could submit a mismatched set.
  const handleVisibilityScopeChange = (next: VisibilityScope): void => {
    if (next === visibilityScope) return;
    setVisibilityScope(next);
    setSelectedRepos((prev) =>
      prev.filter((name) => {
        const repo = repos.find((r) => (r.full_name || r.name) === name);
        if (!repo) return true; // keep unknown repos; backend will validate
        return repoMatchesVisibilityScope(repo, next);
      }),
    );
  };

  const handleAddRepo = (repoName: string): void => {
    if (!selectedRepos.includes(repoName)) {
      setSelectedRepos([...selectedRepos, repoName]);
    }
  };

  const handleClearSelectedRepos = (): void => {
    setSelectedRepos([]);
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
              <div className="space-y-6">
                <div>
                  <p className="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">
                    Step 1 of {FINAL_WIZARD_STEP}
                  </p>
                  <h3 className="mt-1 text-2xl font-semibold text-gray-900 dark:text-white">
                    Project Basics
                  </h3>
                  <p className="mt-2 text-sm text-gray-600 dark:text-slate-300">
                    Start with a clear project name, then choose whether this project manages caller workflows or reusable workflows.
                  </p>
                </div>

                <div className="rounded-xl border border-blue-500/40 bg-blue-500/5 p-4">
                  <Label htmlFor="project-name" className="mb-2 block text-base font-semibold text-gray-900 dark:text-white">
                    Project Name:
                  </Label>
                  <Input
                    id="project-name"
                    type="text"
                    placeholder="Enter project name"
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value)}
                    onBlur={() => setProjectNameTouched(true)}
                    aria-describedby={projectNameDescriptionIds}
                    aria-invalid={showProjectNameError}
                    className="h-12 text-base"
                  />
                  <p id="project-name-help" className="mt-2 text-xs text-gray-500 dark:text-slate-400">
                    Use a recognizable name for the workflow project you want to manage.
                  </p>
                  {showProjectNameError && (
                    <p id="project-name-error" className="mt-2 text-xs font-medium text-red-600 dark:text-red-400">
                      {projectNameError}
                    </p>
                  )}
                </div>

                <div>
                  <Label className="mb-3 block text-sm font-semibold text-gray-900 dark:text-white">
                    What type of project are you creating?
                  </Label>
                  <div className="grid gap-3 md:grid-cols-2">
                    {(["standard", "rwx"] as ProjectType[]).map((type) => {
                      const cfg = PROJECT_TYPE_CONFIG[type];
                      const TypeIcon = cfg.icon;
                      const isSelected = projectType === type;
                      const isTypeDisabled =
                        (type === "standard" && betaCallerLimitReached) ||
                        (type === "rwx" && betaRwxLimitReached);
                      const limitHelperText =
                        type === "standard" && betaCallerLimitReached
                          ? `Beta limit reached (${SELF_HOSTED_BETA_CALLER_LIMIT}/${SELF_HOSTED_BETA_CALLER_LIMIT} Caller Workflow Projects).`
                          : type === "rwx" && betaRwxLimitReached
                          ? `Beta limit reached (${SELF_HOSTED_BETA_RWX_LIMIT}/${SELF_HOSTED_BETA_RWX_LIMIT} Reusable Workflow Projects).`
                          : null;
                      return (
                        <label
                          key={type}
                          className={`flex gap-3 rounded-lg border p-4 transition focus-within:ring-2 focus-within:ring-blue-400 ${
                            isTypeDisabled
                              ? "cursor-not-allowed opacity-50 border-gray-200 dark:border-slate-700 bg-gray-100/50 dark:bg-slate-800/40"
                              : isSelected
                              ? "cursor-pointer border-blue-500 bg-blue-500/10"
                              : "cursor-pointer border-gray-200 dark:border-slate-700 bg-gray-100 dark:bg-slate-800/60 hover:border-blue-400/60"
                          }`}
                        >
                          <input
                            type="radio"
                            name="projectType"
                            value={type}
                            checked={isSelected}
                            disabled={isTypeDisabled}
                            onChange={() => !isTypeDisabled && setProjectType(type)}
                            className="mt-1"
                          />
                          <span className="flex-1">
                            <span className="flex items-center gap-2 font-semibold text-gray-900 dark:text-white">
                              <TypeIcon size={16} />
                              {getProjectTypeLabel(type)}
                              {isSelected && (
                                <span className={`ml-auto ${isTypeDisabled ? "text-gray-400 dark:text-slate-500" : "text-blue-600 dark:text-blue-400"}`}>✓</span>
                              )}
                            </span>
                            <span className="mt-1 block text-xs leading-5 text-gray-600 dark:text-slate-300">
                              {cfg.description}
                            </span>
                            {limitHelperText && (
                              <span className="mt-1 block text-xs font-medium text-amber-700 dark:text-amber-400">
                                {limitHelperText}
                              </span>
                            )}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                  {projectType === "rwx" && (
                    <p className="mt-3 text-sm text-gray-600 dark:text-slate-300">
                      ℹ️ Only repositories tagged with <code>am-rwx</code> are shown in the repository step.
                      Add the <code>am-rwx</code> topic to repositories that should be discoverable for reusable workflows.
                    </p>
                  )}
                </div>

                {projectType === "rwx" && (
                  <div className="rounded-xl border border-purple-500/40 bg-purple-500/5 p-4 space-y-2">
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">
                      🔄 About Reusable Workflow Projects
                    </p>
                    <p className="text-sm text-gray-600 dark:text-slate-300">
                      Reusable Workflow Projects are producer projects. They store shared GitHub Actions workflows that other repositories can call using <code>uses:</code>. For best results, create a dedicated GitHub repository such as <code>reusable-workflows</code>, then store reusable workflow files under <code>.github/workflows/</code>.
                    </p>
                    <p className="text-sm text-gray-600 dark:text-slate-300">
                      Each reusable workflow file must include <code>on: workflow_call</code> as its trigger. Caller repositories reference it with a path like{" "}
                      <code>your-org/reusable-workflows/.github/workflows/reusable-node-ci.yml@main</code>.
                    </p>
                    <a
                      className="inline-block text-sm font-medium text-purple-600 dark:text-purple-400 hover:underline"
                      href={getDocsUrl("reusableWorkflowSetup")}
                      rel="noreferrer"
                      target="_blank"
                    >
                      Reusable Workflow Repository Setup guide →
                    </a>
                  </div>
                )}

                <ProjectColorSelector value={projectColor} onChange={setProjectColor} projectType={projectType} />
              </div>
            )}

            {currentStep === 2 && (
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
                      const helperText = isPrivate
                        ? isSelfHostedBeta
                          ? "Use this project for private GitHub repositories only. Requires GitHub credentials with private repository access."
                          : "Use this project for private GitHub repositories only. Private repositories require a Professional or Enterprise plan and the correct GitHub permissions."
                        : "Use this project for public GitHub repositories only.";
                      return (
                        <label
                          key={scope}
                          data-testid={`visibility-option-${scope}`}
                          className={`flex gap-3 rounded-lg border p-4 transition focus-within:ring-2 focus-within:ring-blue-400 ${
                            isDisabled
                              ? "cursor-not-allowed border-gray-200 dark:border-slate-700 bg-gray-100 dark:bg-slate-800/60 opacity-60"
                              : isSelected
                                ? "cursor-pointer border-blue-500 bg-blue-500/10"
                                : "cursor-pointer border-gray-200 dark:border-slate-700 bg-gray-100 dark:bg-slate-800/60 hover:border-blue-400/60"
                          }`}
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

                <div>
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

                  {projectType === "rwx" && rwxLoading && (
                    <p className="mb-2 text-sm text-gray-600 dark:text-slate-300">⏳ Loading reusable workflow repositories…</p>
                  )}
                  {projectType === "rwx" && !rwxLoading && rwxError && (
                    <div className="mb-3 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-700 dark:bg-red-950 dark:text-red-200">
                      <strong>⚠️ Could not load reusable workflow repositories.</strong>
                      <div className="mt-1">{rwxError}</div>
                      <div className="mt-1 text-xs opacity-80">
                        Verify the signed-in account (or its GitHub App installation)
                        has access to the target organization, and that the repository
                        has the <code>am-rwx</code> topic, then try again.
                      </div>
                    </div>
                  )}
                  {projectType === "rwx" && !rwxLoading && !rwxError && repos.length === 0 && (
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

                  <RepositoryBranchSelector
                    availableRepositories={scopedRepos as any}
                    selectedRepositoryNames={selectedRepos}
                    visibilityScope={visibilityScope}
                    loading={projectType === "rwx" ? rwxLoading : reposLoading}
                    error={projectType === "rwx" ? rwxError : reposError}
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
            )}

            {currentStep === 3 && (
              <div className="space-y-6">
                <div>
                  <p className="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">
                    Step {FINAL_WIZARD_STEP} of {FINAL_WIZARD_STEP}
                  </p>
                  <h3 className="mt-1 text-2xl font-semibold text-gray-900 dark:text-white">
                    Resource Naming and Review
                  </h3>
                  <p className="mt-2 text-sm text-gray-600 dark:text-slate-300">
                    Pick how Actions Manager names generated resources, then review the project before creating it.
                  </p>
                </div>

                <div>
                  <Label className="mb-3 block text-sm font-semibold text-gray-900 dark:text-white">Resource Naming Mode:</Label>
                  <div className="grid gap-3 md:grid-cols-2">
                    <label
                      className={`flex cursor-pointer gap-3 rounded-lg border p-4 transition focus-within:ring-2 focus-within:ring-emerald-400 ${
                        usePrefix === true
                          ? "border-emerald-400/70 bg-emerald-500/10"
                          : "border-gray-200 dark:border-slate-700 bg-gray-100 dark:bg-slate-800/60 hover:border-emerald-400/60"
                      }`}
                    >
                      <input
                        type="radio"
                        name="resourceNamingMode"
                        value="prefix"
                        checked={usePrefix === true}
                        onChange={() => setUsePrefix(true)}
                        className="mt-1"
                      />
                      <span className="flex-1">
                        <span className="flex items-center gap-2 font-semibold text-gray-900 dark:text-white">
                          {PREFIX_MODE_CONFIG.label} - Recommended
                          {usePrefix === true && <span className="ml-auto text-emerald-600 dark:text-emerald-400">✓</span>}
                        </span>
                        <span className="mt-1 block text-xs leading-5 text-gray-600 dark:text-slate-300">
                          Adds an <code>{RESOURCE_PREFIX_TEMPLATE}</code> prefix to generated resources to avoid naming conflicts.
                        </span>
                      </span>
                    </label>

                    <label
                      className={`flex cursor-pointer gap-3 rounded-lg border p-4 transition focus-within:ring-2 focus-within:ring-amber-400 ${
                        usePrefix === false
                          ? "border-amber-400/70 bg-amber-500/10"
                          : "border-gray-200 dark:border-slate-700 bg-gray-100 dark:bg-slate-800/60 hover:border-amber-400/60"
                      }`}
                    >
                      <input
                        type="radio"
                        name="resourceNamingMode"
                        value="no-prefix"
                        checked={usePrefix === false}
                        onChange={() => setUsePrefix(false)}
                        className="mt-1"
                      />
                      <span className="flex-1">
                        <span className="flex items-center gap-2 font-semibold text-gray-900 dark:text-white">
                          {NO_PREFIX_MODE_CONFIG.label}
                          {usePrefix === false && <span className="ml-auto text-amber-700 dark:text-amber-300">✓</span>}
                        </span>
                        <span className="mt-1 block text-xs leading-5 text-gray-600 dark:text-slate-300">
                          Advanced option. Keeps names unchanged, but increases the chance of conflicts.
                        </span>
                      </span>
                    </label>
                  </div>
                  {usePrefix === false && (
                    <div className="mt-3 rounded-lg border border-amber-400/60 bg-amber-500/10 p-3 text-sm text-amber-900 dark:text-amber-100">
                      <strong>No Prefix Mode is intended for advanced users.</strong>
                      <p className="mt-1 text-xs leading-5">
                        Resource names must be unique, and Actions Manager will store secret and environment variable names locally for tracking. Secret values must remain only in GitHub.
                      </p>
                    </div>
                  )}
                </div>

                <div className="rounded-lg border border-gray-200 dark:border-slate-700 bg-gray-100 dark:bg-slate-800/60">
                  <button
                    type="button"
                    className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-gray-900 dark:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 disabled:cursor-default disabled:opacity-80"
                    aria-expanded={advancedOptionsVisible}
                    aria-label={
                      useCustomKey
                        ? "Advanced Options expanded because custom project key is enabled"
                        : "Advanced Options"
                    }
                    disabled={useCustomKey}
                    onClick={() => setAdvancedOptionsOpen((open) => !open)}
                  >
                    Advanced Options{' '}
                    <span aria-hidden="true">
                      {useCustomKey ? "Custom key enabled" : advancedOptionsVisible ? "−" : "+"}
                    </span>
                  </button>
                  {advancedOptionsVisible && (
                    <div className="space-y-3 border-t border-gray-200 dark:border-slate-700 p-4">
                      <div className="flex items-center space-x-2">
                        <Checkbox
                          id="use-custom-key"
                          checked={useCustomKey}
                          onCheckedChange={(checked) => {
                            const enabled = checked as boolean;
                            setUseCustomKey(enabled);
                            if (enabled) setAdvancedOptionsOpen(true);
                          }}
                        />
                        <Label htmlFor="use-custom-key" className="cursor-pointer text-gray-900 dark:text-white">
                          Use custom project key
                        </Label>
                      </div>

                      {useCustomKey && (
                        <div>
                          <Label htmlFor="project-key" className="mb-2 block text-sm font-medium text-gray-900 dark:text-white">
                            Project Key
                          </Label>
                          <Input
                            id="project-key"
                            type="text"
                            placeholder="Enter project key (2-10 chars, letters/numbers)"
                            value={projectKey}
                            onChange={(e) => setProjectKey(e.target.value)}
                            maxLength={10}
                          />
                          <p className="mt-1 text-xs text-gray-500 dark:text-slate-400">
                            Use 2-10 letters or numbers. Existing server-side validation is unchanged.
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <Button
                  onClick={handleCreateProject}
                  disabled={isCreating || !formIsValid}
                  className="w-full"
                >
                  {isCreating ? "⏳ Creating..." : "🚀 Create Project"}
                </Button>
              </div>
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
