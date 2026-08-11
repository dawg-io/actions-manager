/* eslint-disable no-restricted-syntax, no-restricted-imports -- Legacy: TODO migrate inline styles and CSS imports to Tailwind CSS classes */
import UserAvatar from "./components/UserAvatar";
import PlanUsagePill from "./components/PlanUsagePill";
import BrandLogo from "./components/BrandLogo";
import { useParams, useNavigate, useLocation } from "react-router";
import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { fetchProjects, loadProject, Project, linkReusableWorkflow, RwxWorkflow, LinkedStandardProject, updateProjectColor, updateProjectName, updateProjectOrder, exportProjectBackup } from "./api/projects";
import { deleteProjectEnhanced } from "./api/projectDeletion";
import { handleSaveProjectWithModal } from "./api/handlers";
import { getSecrets } from "./api/secrets";
import { getEnvVars } from "./api/envVars";
import { Button } from "./components/ui/button";
import EnvVars from "./components/EnvVars";
import Secrets from "./components/Secrets";
import UnifiedWorkflows from "./components/UnifiedWorkflows";
import RulesetManager from "./components/RulesetManager";
import type { CustomFile } from "./api/customFiles";
import { listActionsProjects, ActionsProject } from "./api/actionsProjects";
import { listActionGroups, ActionGroup } from "./api/actionGroups";
import ProjectList from "./components/ProjectList";
import RepositoriesAndBranches from "./components/RepositoriesAndBranches";
import DeployEnvironments from "./components/DeployEnvironments";
import SaveResultsModal from "./components/SaveResultsModal";
import DeleteProjectModal from "./components/DeleteProjectModal";
import DangerZone from "./components/DangerZone";
import ProjectMembers from "./components/ProjectMembers";
import DriftDetection from "./components/DriftDetection";
import type { WorkflowDriftDetail } from "./api/drift";
import Sidebar from "./components/Sidebar";
import PRStatusPanel from "./components/PRStatusPanel";
import PRHistoryPanel from "./components/PRHistoryPanel";
import CreatePRModal from "./components/CreatePRModal";
import LinkedWorkflowsModal from "./components/LinkedWorkflowsModal";
import ProjectColorSelector from "./components/ProjectColorSelector";
import { WorkflowImportPanel } from "./components/WorkflowImportPanel";
import { getProjectTypeConfig, ProjectType } from "./utils/projectTypeConfig";
import { getPrefixModeConfig } from "./utils/prefixModeConfig";
import { normalizeProjectColorKey, type ProjectColorKey } from "./utils/projectColors";
import { PROJECT_TIER_CONFIG, getEffectiveTierKey, SELF_HOSTED_BETA_CALLER_LIMIT, SELF_HOSTED_BETA_RWX_LIMIT } from "./utils/accountTier";
import { getProjectPRStatus } from "./api/pullRequests";
import { getProjectCodeownersStatuses } from "./api/codeowners";
import type { GitHubTokenStatus } from "./api/user";
import { ProjectPRState } from "./types/workflow";
import "./styles/projectMgmt.css";
import "./styles/driftDetection.css";
import "./styles/prTracking.css";
import { toast } from './utils/toast';
import ConfirmDialog from './components/ConfirmDialog';

// Constant empty array to prevent unnecessary re-renders
const EMPTY_BUILD_TYPES: any[] = [];

// Keys for the Repository Configs collapsible group (shared with Sidebar)
const REPO_CONFIG_SECTION_KEYS = ['repos-and-branches', 'environments', 'envvars', 'secrets', 'rulesets'];

// Delay (ms) before scrolling to a repo-config anchor after the stacked page renders
const REPO_CONFIG_SCROLL_DELAY_MS = 50;

// Tailwind utility classes that turn each Repository Config block into a
// sticky full-page slide. The section is at least one viewport tall, and the
// title sticks to the top while the user scrolls within the section. Smooth
// scrolling between slides comes from sidebar-driven `scrollIntoView({
// behavior: 'smooth' })` and from `scroll-behavior: smooth` on the actual
// scroll container (`.section-container` in projectMgmt.css), since the
// `scroll-behavior` property is not inherited.
const REPO_CONFIG_SLIDE_CLASS = 'min-h-screen';
const REPO_CONFIG_SLIDE_TITLE_CLASS =
  'sticky top-0 z-10 bg-[var(--container-background-color)]';

const VALID_PROJECT_PR_STATES = new Set<ProjectPRState>(["new", "draft", "open", "synced"]);

const normalizeProjectPRState = (state?: string | null): ProjectPRState => {
  return state && VALID_PROJECT_PR_STATES.has(state as ProjectPRState)
    ? (state as ProjectPRState)
    : "new";
};

// TypeScript interfaces for data structures
interface RateLimitInfo {
  limit: number;
  used: number;
  remaining: number;
  percentage_used: number;
  should_warn: boolean;
  reset_at: string;
}

interface UserDetails {
  avatar_url: string;
  github_user: string;
  account_type: string;
  installation_mode?: string | null;
  github_account_type?: string | null;
  connected_github_account?: string | null;
  connected_github_account_type?: string | null;
  rate_limit?: RateLimitInfo;
  workspace_role?: string;
  github_token?: GitHubTokenStatus;
}

interface Repository {
  name: string;
  full_name: string;
  private: boolean;
  default_branch: string;
  permissions?: any;
}

interface ProjectWorkflow {
  name: string;
  content: string;
  isReusable: boolean;
  isModified?: boolean;
  gitHash?: string;
  workflowStatus?: string;
  savedName?: string;
}

interface ProjectRXWorkflow {
  name: string;
  content: string;
  isReusable?: boolean;
  isModified?: boolean;
  gitHash?: string;
  workflowStatus?: string;
  savedName?: string;
}

interface ProjectSecret {
  name: string;
  value?: string;
  repo?: string;
}

interface ProjectEnvVar {
  env_key: string;
  value?: string;
  repo: string;
}

interface SaveResultItem {
  repo: string;
  success: boolean;
  message?: string;
  error?: string;
}

interface DeploymentEnvironment {
  name: string;
  protection_rules?: any[];
  deployment_branch_policy?: any;
}

interface ManualEnvironment {
  name: string;
}

// Props interface for the RepoSelector component
interface RepoSelectorProps {
  userDetails?: UserDetails;
  onLogout?: () => void;
}

function RepoSelector({ userDetails, onLogout }: RepoSelectorProps) {
  const { user, projectName: urlProjectName } = useParams<{
    user: string;
    projectName: string;
  }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [projectName, setProjectName] = useState<string>(urlProjectName || "");
  const [repos, setRepos] = useState<Repository[]>([]);
  const [selectedRepos, setSelectedRepos] = useState<string[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [workflows, setWorkflows] = useState<ProjectWorkflow[]>([]);
  const [rxworkflows, setRXWorkflows] = useState<ProjectRXWorkflow[]>([]);
  const [customFiles, setCustomFiles] = useState<CustomFile[]>([]);
  const [importedActions, setImportedActions] = useState<ActionsProject[]>([]);
  const [actionGroups, setActionGroups] = useState<ActionGroup[]>([]);
  const [envVars, setEnvVars] = useState<ProjectEnvVar[]>([]);
  const [manualEnvVars, setManualEnvVars] = useState<ProjectEnvVar[]>([]);
  const [regexPattern, setRegexPattern] = useState<string>("");
  const [branchOption, setBranchOption] = useState<"default" | "pattern">("default");
  const [branchMaxAgeDays, setBranchMaxAgeDays] = useState<number>(30);
  const [secrets, setSecrets] = useState<ProjectSecret[]>([]);
  const [manualSecrets, setManualSecrets] = useState<ProjectSecret[]>([]);
  const [projectCode, setProjectCode] = useState<string>("");
  const [projectId, setProjectId] = useState<string | number>("");
  const [accountType, setAccountType] = useState<string | null>(null);
  const [isSaveResultsModalOpen, setIsSaveResultsModalOpen] = useState<boolean>(false);
  const [saveResults, setSaveResults] = useState<SaveResultItem[]>([]);
  const [saveSuccess, setSaveSuccess] = useState<boolean>(true);
  const [githubUpdatePerformed, setGithubUpdatePerformed] = useState<boolean>(false);
  const [deploymentEnvironments, setDeploymentEnvironments] = useState<DeploymentEnvironment[]>([]);

  // Drift detection state — lifted from <DriftDetection /> so we can render
  // per-workflow badges and warn users before destructive sync actions.
  const [driftDetails, setDriftDetails] = useState<WorkflowDriftDetail[]>([]);
  // Kept separate from driftDetails, which the live check overwrites — the
  // banner needs the persisted seed to survive until that check resolves.
  const [seededDriftNames, setSeededDriftNames] = useState<string[]>([]);
  const [driftRefreshSignal, setDriftRefreshSignal] = useState<number>(0);
  const driftedWorkflowNames = useMemo(
    () => new Set(driftDetails.map(d => d.workflow_name)),
    [driftDetails],
  );

  const [codeownersStatuses, setCodeownersStatuses] = useState<Record<string, string>>({});

  const codeownersAggregateStatus = useMemo(() => {
    const statuses = Object.values(codeownersStatuses);
    if (statuses.length === 0) return null;
    if (statuses.some(s => s === 'under_review')) return 'under_review';
    if (statuses.some(s => s === 'committed_locally' || s === 'new')) return 'committed_locally';
    if (statuses.every(s => s === 'synced_with_github')) return 'synced_with_github';
    return 'committed_locally';
  }, [codeownersStatuses]);

  const codeownersWithChanges = useMemo(() =>
    Object.entries(codeownersStatuses)
      .filter(([, status]) => status === 'committed_locally' || status === 'new')
      .map(([repo]) => repo),
    [codeownersStatuses]
  );

  // New state for enhanced deletion modal
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState<boolean>(false);
  const [driftDialogInfo, setDriftDialogInfo] = useState<{ label: string; onConfirm: () => void } | null>(null);
  const [pendingRename, setPendingRename] = useState<string | null>(null);
  
  // Progress bar state for save operations
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [saveProgress, setSaveProgress] = useState<number>(0);
  const [saveProgressText, setSaveProgressText] = useState<string>("");

  // Local save state for Repositories & Branches section
  const [isLocalSaving, setIsLocalSaving] = useState<boolean>(false);
  const [localSaveToastVisible, setLocalSaveToastVisible] = useState<boolean>(false);
  const localSaveToastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Snapshot of last-saved repos & branches config — used to track dirty state.
  // Stored as state (not a ref) so that useMemo re-evaluates after a save.
  type RepoBranchSnapshot = {
    selectedRepos: string[];
    regexPattern: string;
    branchOption: "default" | "pattern";
    branchMaxAgeDays: number;
    validationRepo: string | null;
    preflightRequired: boolean;
  };
  const [savedRepoBranchSnapshot, setSavedRepoBranchSnapshot] = useState<RepoBranchSnapshot | null>(null);
  
  // Reusable workflows enabled flag (used for RWX projects)
  const [reusableWorkflowsEnabled, setReusableWorkflowsEnabled] = useState<boolean>(false);

  // State for prefix usage setting
  const [usePrefix, setUsePrefix] = useState<boolean>(true);

  // State for project type (standard or rwx)
  const [projectType, setProjectType] = useState<ProjectType>("standard");

  // Saved backend repository visibility scope for the loaded project
  // ("public" | "private"). Defaults to "public" to match the backend default
  // and the migration fallback for legacy rows.
  const [repositoryVisibilityScope, setRepositoryVisibilityScope] = useState<"public" | "private">("public");
  const [validationRepo, setValidationRepo] = useState<string | null>(null);
  const [preflightRequired, setPreflightRequired] = useState<boolean>(false);
  const [lastPreflightStatus, setLastPreflightStatus] = useState<string | null>(null);
  const [lastPreflightRunAt, setLastPreflightRunAt] = useState<string | null>(null);
  const [lastPreflightError, setLastPreflightError] = useState<string | null>(null);
  const [lastPreflightPrUrl, setLastPreflightPrUrl] = useState<string | null>(null);

  // Project identity color (decorative accent only). UI falls back to "blue".
  const [projectColor, setProjectColor] = useState<ProjectColorKey>("blue");
  const [projectColorSaveState, setProjectColorSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [projectColorSaveError, setProjectColorSaveError] = useState<string | null>(null);
  const projectColorSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const projectColorSaveRequestIdRef = useRef<number>(0);

  // Projects-grid manual ordering (issue #1804)
  const [projectOrderError, setProjectOrderError] = useState<string | null>(null);
  const projectOrderRequestIdRef = useRef<number>(0);

  // Linked reusable workflows (for standard projects)
  const [linkedWorkflows, setLinkedWorkflows] = useState<RwxWorkflow[]>([]);
  const [showLinkedWorkflowsModal, setShowLinkedWorkflowsModal] = useState<boolean>(false);
  /** Project ID to filter in the modal when managing a specific linked RWX project's workflows */
  const [manageFilterProjectId, setManageFilterProjectId] = useState<number | undefined>(undefined);

  // Linked standard projects (for RWX projects – reverse relationship)
  const [linkedStandardProjects, setLinkedStandardProjects] = useState<LinkedStandardProject[]>([]);
  
  // New state for sidebar navigation
  const [activeSection, setActiveSection] = useState<string>('workflows');
  // Tracks which repo-config section is scrolled into view (drives sidebar highlight)
  const [scrollActiveSection, setScrollActiveSection] = useState<string>('workflows');

  // Workflow Import panel visibility
  const [showWorkflowImport, setShowWorkflowImport] = useState<boolean>(false);
  
  // Ref for the scrollable section container (used as IntersectionObserver root)
  const sectionContainerRef = useRef<HTMLDivElement>(null);

  // Staleness guard for loadProjectFromAPI: each call captures this counter at start
  // and discards results if a newer load (or back-navigation) has been initiated.
  const loadRequestCounterRef = useRef<number>(0);
  
  // New state for sidebar collapse
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(false);
  // Mobile sidebar visibility — toggled by the hamburger button
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState<boolean>(false);

  // State for PR tracking
  const [projectPRState, setProjectPRState] = useState<ProjectPRState>("new");
  const [showPRStatusPanel, setShowPRStatusPanel] = useState<boolean>(false);
  const [showCreatePRModal, setShowCreatePRModal] = useState<boolean>(false);
  const [prStatusRefreshKey, setPRStatusRefreshKey] = useState<number>(0);
  const [codeownersRefreshCounter, setCodeownersRefreshCounter] = useState<number>(0);

  // State for the caller's effective project role (from backend)
  const [callerProjectRole, setCallerProjectRole] = useState<string>("project_admin");

  // project_viewer users or users with workspace-level read_only role should not be able to modify the project
  const isProjectReadOnly = callerProjectRole === "project_viewer" || userDetails?.workspace_role === "read_only";

  // In self-hosted beta, all users get add/edit access regardless of stored account_type.
  // On cloud, Free-tier users cannot add secrets/env vars (handled inside those components).
  const isSelfHostedBeta = userDetails?.installation_mode?.toLowerCase() === "self-hosted";
  const isCloudFreeTier = !isSelfHostedBeta && accountType === "free";

  // State for workflow button functions
  const [refreshStatusFn, setRefreshStatusFn] = useState<(() => Promise<void>) | null>(null);
  const [isRefreshingStatus, setIsRefreshingStatus] = useState<boolean>(false);

  // State for reusable workflow button functions
  const [generateTemplatesFn, setGenerateTemplatesFn] = useState<(() => Promise<void>) | null>(null);
  const [isGeneratingTemplates, setIsGeneratingTemplates] = useState<boolean>(false);
  const [addRXWorkflowFn, setAddRXWorkflowFn] = useState<(() => void) | null>(null);

  // State for workflow add function
  const [addWorkflowFn, setAddWorkflowFn] = useState<(() => void) | null>(null);
  
  // State for clear workflow modified states function
  const [clearWorkflowModifiedStatesFn, setClearWorkflowModifiedStatesFn] = useState<(() => void) | null>(null);

  // Allow deep-linking into the workflow creation dialog from the project list
  // via `?addWorkflow=1`. Once launched, remove the param to avoid reopening.
  useEffect(() => {
    if (!urlProjectName) return;
    const params = new URLSearchParams(location.search);
    if (params.get("addWorkflow") !== "1") return;
    const workflowType = params.get("workflowType");

    if (activeSection !== "workflows") {
      setActiveSection("workflows");
      return;
    }

    const launchFn = workflowType === "reusable" ? addRXWorkflowFn : addWorkflowFn;
    if (!launchFn) return;

    launchFn();
    params.delete("addWorkflow");
    params.delete("workflowType");
    const search = params.toString();
    navigate(`${location.pathname}${search ? `?${search}` : ""}`, { replace: true });
  }, [urlProjectName, location.pathname, location.search, navigate, addWorkflowFn, addRXWorkflowFn, activeSection]);

  useEffect(() => {
    return () => {
      if (projectColorSaveTimerRef.current) {
        clearTimeout(projectColorSaveTimerRef.current);
        projectColorSaveTimerRef.current = null;
      }
    };
  }, []);

  const handleProjectColorChange = useCallback(async (nextColor: ProjectColorKey): Promise<void> => {
    if (isProjectReadOnly || !user) return;
    const numericProjectId = typeof projectId === "number" ? projectId : (projectId ? Number(projectId) : null);
    if (!numericProjectId || Number.isNaN(numericProjectId)) return;
    if (nextColor === projectColor) return;

    const previousColor = projectColor;
    setProjectColor(nextColor);
    setProjectColorSaveState("saving");
    setProjectColorSaveError(null);

    const requestId = ++projectColorSaveRequestIdRef.current;
    try {
      const response = await updateProjectColor(user, numericProjectId, nextColor);
      if (requestId !== projectColorSaveRequestIdRef.current) return;

      const savedColor = normalizeProjectColorKey(response.project_color);
      setProjectColor(savedColor);
      setProjects((prev) =>
        prev.map((p) => {
          const id = p.project_id ?? p.id;
          return Number(id) === numericProjectId ? { ...p, project_color: savedColor } : p;
        }),
      );

      setProjectColorSaveState("saved");
      if (projectColorSaveTimerRef.current) {
        clearTimeout(projectColorSaveTimerRef.current);
      }
      projectColorSaveTimerRef.current = setTimeout(() => {
        setProjectColorSaveState("idle");
        setProjectColorSaveError(null);
      }, 1500);
    } catch (error: any) {
      if (requestId !== projectColorSaveRequestIdRef.current) return;
      setProjectColor(previousColor);
      setProjectColorSaveState("error");
      setProjectColorSaveError(error?.response?.data?.detail || error?.message || "Failed to save project color.");
    }
  }, [isProjectReadOnly, user, projectId, projectColor]);

  /**
   * Persist a manual Projects-grid reorder (issue #1804).
   *
   * Applies optimistically so the drop feels instant, then rolls the whole list
   * back if the save fails. The request-id guard mirrors handleProjectColorSave:
   * a slow earlier save must not clobber a newer arrangement.
   */
  const handleProjectsReorder = useCallback(async (orderedIds: number[]): Promise<void> => {
    if (!user) return;

    const previousProjects = projects;
    const byId = new Map(projects.map((p) => [Number(p.project_id ?? p.id), p]));
    const reordered = orderedIds
      .map((id) => byId.get(Number(id)))
      .filter((p): p is Project => p !== undefined);

    // Guard against a drop computed from a stale list: if the ids don't cover
    // every project, saving would send a partial order and be rejected anyway.
    if (reordered.length !== projects.length) return;

    setProjectOrderError(null);
    setProjects(reordered);

    const requestId = ++projectOrderRequestIdRef.current;
    try {
      const canonicalIds = await updateProjectOrder(user, orderedIds);
      if (requestId !== projectOrderRequestIdRef.current) return;

      // The backend response is canonical — re-apply it in case it differs.
      const canonical = canonicalIds
        .map((id) => byId.get(Number(id)))
        .filter((p): p is Project => p !== undefined);
      if (canonical.length === reordered.length) {
        setProjects(canonical);
      }
    } catch (error: any) {
      if (requestId !== projectOrderRequestIdRef.current) return;
      setProjects(previousProjects);
      setProjectOrderError(
        error?.response?.data?.detail || error?.message || "Failed to save project order.",
      );
    }
  }, [user, projects]);

  const handleProjectNameSave = useCallback((newValue: string) => {
    if (newValue === projectName) return;
    setPendingRename(newValue);
  }, [projectName]);

  const confirmProjectRename = useCallback(async () => {
    const newName = pendingRename;
    setPendingRename(null);
    if (!newName || !user) return;

    const numericProjectId =
      typeof projectId === "number" ? projectId : Number(projectId) || null;
    if (!numericProjectId || Number.isNaN(numericProjectId)) return;

    const previousName = projectName;
    setProjectName(newName);
    try {
      await updateProjectName(user, numericProjectId, newName);
      toast.success(`Project renamed to "${newName}".`);
      setProjects((prev) =>
        prev.map((p) => {
          const id = p.project_id ?? p.id;
          return Number(id) === numericProjectId ? { ...p, project_name: newName, name: newName } : p;
        }),
      );
      navigate(`/project/${user}/${encodeURIComponent(newName)}`, { replace: true });
    } catch (error: any) {
      setProjectName(previousName);
      const detail = error?.response?.data?.detail || error?.message || "Failed to rename project.";
      toast.error(`Rename failed: ${detail}`);
    }
  }, [pendingRename, user, projectId, projectName, navigate]);

  const handleExportBackup = useCallback(async (): Promise<void> => {
    if (!projectId) {
      toast.error("Project must be saved before exporting a backup.");
      return;
    }

    try {
      const { blob, filename } = await exportProjectBackup(projectId);
      const cleanedProjectName = (projectName || "project").trim().replace(/[^a-zA-Z0-9._-]+/g, "-");
      let dashStart = 0;
      while (cleanedProjectName[dashStart] === "-") dashStart++;
      let dashEnd = cleanedProjectName.length;
      while (dashEnd > dashStart && cleanedProjectName[dashEnd - 1] === "-") dashEnd--;
      const safeProjectName = cleanedProjectName.slice(dashStart, dashEnd) || "project";
      const fallbackFileName = `actionsmanager-project-${safeProjectName}-${new Date().toISOString().replace(/[:]/g, "-")}.json`;

      const url = globalThis.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename || fallbackFileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      globalThis.URL.revokeObjectURL(url);
      toast.success("Backup export downloaded.");
    } catch (error: any) {
      toast.error(`Failed to export backup: ${error?.message || "Unknown error"}`);
    }
  }, [projectId, projectName]);

  // State for repo-config header quick actions (focus/scroll helpers)
  const [focusAddEnvironmentFn, setFocusAddEnvironmentFn] = useState<(() => void) | null>(null);
  const [manualEnvironments, setManualEnvironments] = useState<ManualEnvironment[]>([{ name: "" }]);
  const [addEnvVarFn, setAddEnvVarFn] = useState<(() => void) | null>(null);
  const [addSecretFn, setAddSecretFn] = useState<(() => void) | null>(null);

  // Function to load PR status for the current project
  const loadPRStatus = useCallback(async (projectNameToLoad: string, refreshFromGitHub: boolean = false): Promise<void> => {
    if (!user || !projectNameToLoad) return;
    
    try {
      // Use cached database state by default; refresh from GitHub when explicitly requested
      const prStatus = await getProjectPRStatus(user, projectNameToLoad, refreshFromGitHub);
      const newState = normalizeProjectPRState(prStatus.project_state);
      setProjectPRState(newState);
      console.log(`📌 Loaded PR status (${refreshFromGitHub ? 'live from GitHub' : 'cached'}): ${newState}, Open PRs: ${prStatus.open_prs}, Merged: ${prStatus.merged_prs}, Total: ${prStatus.total_prs}`);

      if (refreshFromGitHub && prStatus.total_prs > 0 && prStatus.open_prs === 0) {
        // After a live GitHub refresh: use the actual PR counts as the source of truth
        // for workflow badge updates, rather than relying solely on project_state.
        // This handles edge cases where the backend's project_state field did not
        // transition (e.g. due to an unexpected initial state), while the PR data
        // from GitHub is unambiguously showing all PRs resolved.
        //
        // Linked reusable workflows are *globally* shared: a sibling caller's open
        // PR campaign holds the workflow under_review everywhere, but that PR is
        // not visible in this project's pr_status view. Honour the backend's
        // `locked_workflow_ids` so a refresh in a sibling project never unlocks
        // a workflow that another caller is still reviewing.
        const lockedIds = new Set<number>(prStatus.locked_workflow_ids ?? []);
        const isLinkedLocked = (w: RwxWorkflow): boolean => lockedIds.has(w.workflow_id);
        if (prStatus.merged_prs === prStatus.total_prs) {
          // Every PR was merged — only flip workflows that were under review to synced.
          // Omitted workflows that kept their prior state must not be affected.
          setWorkflows((prev: ProjectWorkflow[]) => prev.map(w =>
            w.workflowStatus === 'under_review' ? { ...w, workflowStatus: 'synced_with_github' } : w
          ));
          setRXWorkflows((prev: ProjectRXWorkflow[]) => prev.map(w =>
            w.workflowStatus === 'under_review' ? { ...w, workflowStatus: 'synced_with_github' } : w
          ));
          setLinkedWorkflows((prev: RwxWorkflow[]) => prev.map(w =>
            w.workflowStatus === 'under_review' && !isLinkedLocked(w)
              ? { ...w, workflowStatus: 'synced_with_github' }
              : w
          ));
          setCustomFiles((prev: any[]) => prev.map((f: any) =>
            f.file_status === 'under_review' ? { ...f, file_status: 'synced_with_github' } : f
          ));
          console.log('✅ All PRs merged: under_review workflow badges updated to synced_with_github');
        } else {
          // At least one PR was closed without merge — revert Under Review badges
          setWorkflows((prev: ProjectWorkflow[]) => prev.map(w =>
            w.workflowStatus === 'under_review' ? { ...w, workflowStatus: 'committed_locally' } : w
          ));
          setRXWorkflows((prev: ProjectRXWorkflow[]) => prev.map(w =>
            w.workflowStatus === 'under_review' ? { ...w, workflowStatus: 'committed_locally' } : w
          ));
          setLinkedWorkflows((prev: RwxWorkflow[]) => prev.map(w =>
            w.workflowStatus === 'under_review' && !isLinkedLocked(w)
              ? { ...w, workflowStatus: 'committed_locally' }
              : w
          ));
          setCustomFiles((prev: any[]) => prev.map((f: any) =>
            f.file_status === 'under_review' ? { ...f, file_status: 'committed_locally' } : f
          ));
          console.log('✅ PRs closed without merge: Under Review badges reverted to committed_locally');
        }
      } else {
        // Non-refresh path (cached DB read) or some PRs still open:
        // use the backend's project_state for any necessary transitions.
        // Guard: never flip under_review → synced while open PRs exist in this
        // view. For RWX projects the project's own pr_state may be "synced"
        // even though a linked standard project has an open PR for one of its
        // reusable workflows. The open_prs count from get_project_pr_status
        // includes cross-project PRs, so checking it prevents premature unlock.
        const lockedIds = new Set<number>(prStatus.locked_workflow_ids ?? []);
        const isLinkedLocked = (w: RwxWorkflow): boolean => lockedIds.has(w.workflow_id);
        if (newState === 'synced' && prStatus.open_prs === 0 && prStatus.total_prs > 0) {
          setWorkflows((prev: ProjectWorkflow[]) => prev.map(w =>
            w.workflowStatus === 'under_review' ? { ...w, workflowStatus: 'synced_with_github' } : w
          ));
          setRXWorkflows((prev: ProjectRXWorkflow[]) => prev.map(w =>
            w.workflowStatus === 'under_review' ? { ...w, workflowStatus: 'synced_with_github' } : w
          ));
          setLinkedWorkflows((prev: RwxWorkflow[]) => prev.map(w =>
            w.workflowStatus === 'under_review' && !isLinkedLocked(w)
              ? { ...w, workflowStatus: 'synced_with_github' }
              : w
          ));
        } else if (newState === 'draft' && prStatus.total_prs > 0 && prStatus.open_prs === 0) {
          // Only clear under_review when this project's view shows resolved PRs.
          // Two guards prevent false downgrades:
          //   1. total_prs === 0 → any under_review badge here came from a PR not
          //      visible in this view (e.g. a deleted record); keep the badge.
          //   2. open_prs > 0 → at least one PR is still open (which may be a
          //      cross-project PR from a linked standard project for an RWX
          //      project's reusable workflow). The workflow must remain locked
          //      under_review while that PR is open. Without this guard the RWX
          //      project view would briefly show under_review then flip back to
          //      committed_locally on every page load, because the RWX project's
          //      own pr_state field is never set to "open" for cross-project PRs.
          setWorkflows((prev: ProjectWorkflow[]) => prev.map(w =>
            w.workflowStatus === 'under_review' ? { ...w, workflowStatus: 'committed_locally' } : w
          ));
          setRXWorkflows((prev: ProjectRXWorkflow[]) => prev.map(w =>
            w.workflowStatus === 'under_review' ? { ...w, workflowStatus: 'committed_locally' } : w
          ));
          setLinkedWorkflows((prev: RwxWorkflow[]) => prev.map(w =>
            w.workflowStatus === 'under_review' && !isLinkedLocked(w)
              ? { ...w, workflowStatus: 'committed_locally' }
              : w
          ));
        }
      }
    } catch (error) {
      console.warn("⚠️ Could not load PR status:", error);
      // Set to default state on error
      setProjectPRState("new");
    }
  }, [user]);

  // Function to refresh projects list
  const refreshProjectsList = useCallback(async (): Promise<void> => {
    if (!user) return;
    
    try {
      console.log("📌 Refreshing projects list...");
      const updatedProjects = await fetchProjects(user);
      setProjects(updatedProjects ?? []);
      console.log("✅ Projects list refreshed");
    } catch (error) {
      console.error("❌ Error refreshing projects:", error);
    }
  }, [user]);

  // Define loadProjectFromAPI before it's used in useEffect
  const loadProjectFromAPI = useCallback(async (
    name: string,
    options?: { throwOnError?: boolean; refreshPRFromGitHub?: boolean }
  ): Promise<void> => {
    if (!user) {
      console.error("❌ Error: GitHub user is missing! Redirecting to login...");
      navigate("/", { replace: true }); 
      return;
    }

    // Capture a snapshot of the counter at the start of this load so we can
    // detect if a newer load (or back-navigation) has superseded it.
    const thisRequestId = ++loadRequestCounterRef.current;

    try {
      console.log(`📌 Loading project: ${name}`);
      const response = await loadProject(user, name);

      // Discard results if a newer load or back-navigation has been initiated
      if (thisRequestId !== loadRequestCounterRef.current) return;

      if (response) {
        setProjectName(response.project_name ?? "");
        setSelectedRepos(response.selected_repos ?? []);
        // Set savedName equal to name so the backend can detect renames on next save
        setWorkflows((response.workflows ?? []).map(w => ({ ...w, savedName: w.name })));
        setRXWorkflows((response.rxworkflows ?? []).map(w => ({ ...w, savedName: w.name })));
        setCustomFiles(response.custom_files ?? []);
        // Seed the drift badge from the last persisted check (WorkflowDriftState)
        // so it's correct on first paint instead of defaulting to "no drift" and
        // flipping once <DriftDetection>'s live check resolves. That live check
        // still runs unconditionally and fully replaces this with authoritative
        // data via handleDriftLoaded/setDriftDetails below.
        setSeededDriftNames(response.drifted_workflow_names ?? []);
        setDriftDetails(
          (response.drifted_workflow_names ?? []).map((name): WorkflowDriftDetail => ({
            workflow_id: 0,
            workflow_name: name,
            workflow_filename: name,
            repo: "",
            branch: "",
            has_drift: true,
            actionsmanager_yaml: null,
            github_yaml: null,
            actionsmanager_sha: null,
            github_sha: null,
            last_checked: "",
            message: "",
          }))
        );
        setRegexPattern(response.branch_regex ?? "");
        
        // Migrate legacy branch_option values
        let branchOpt: string = response.branch_option ?? "default";
        if (branchOpt === "all") {
          branchOpt = "default";  // Safest migration
        } else if (branchOpt === "regex") {
          branchOpt = "pattern";
        }
        setBranchOption(branchOpt as "default" | "pattern");
        setBranchMaxAgeDays(response.branch_max_age_days ?? 30);

        // Capture the initial repos & branches snapshot so dirty tracking starts clean
        setSavedRepoBranchSnapshot({
          selectedRepos: response.selected_repos ?? [],
          regexPattern: response.branch_regex ?? "",
          branchOption: branchOpt as "default" | "pattern",
          branchMaxAgeDays: response.branch_max_age_days ?? 30,
          validationRepo: response.validation_repo ?? null,
          preflightRequired: !!response.preflight_required,
        });
        
        setProjectCode(response.project_code ?? "");
        setProjectId(response.project_id ?? "");
        setAccountType(response.account_type ?? null);
        setReusableWorkflowsEnabled(response.reusable_workflows_enabled ?? false);
        setUsePrefix(response.use_prefix ?? true);  // Default to true for backward compatibility
        const loadedProjectType: ProjectType = (response.project_type ?? "standard") as ProjectType;
        setProjectType(loadedProjectType);
        setRepositoryVisibilityScope(
          response.repository_visibility_scope === "private" ? "private" : "public",
        );
        setValidationRepo(response.validation_repo ?? null);
        setPreflightRequired(!!response.preflight_required);
        setLastPreflightStatus(response.last_preflight_status ?? null);
        setLastPreflightRunAt(response.last_preflight_run_at ?? null);
        setLastPreflightError(response.last_preflight_error ?? null);
        setLastPreflightPrUrl(response.last_preflight_pr_url ?? null);
        setProjectColor(normalizeProjectColorKey(response.project_color));
        setProjectColorSaveState("idle");
        setProjectColorSaveError(null);

        // Load linked reusable workflows for standard projects
        setLinkedWorkflows(response.linked_reusable_workflows ?? []);

        // Load linked standard projects for RWX projects (reverse relationship)
        setLinkedStandardProjects(response.linked_standard_projects ?? []);
        
        // Set PR state from project data
        setProjectPRState(normalizeProjectPRState(response.pr_state));

        // Set caller's effective project role from response
        setCallerProjectRole(response.caller_project_role ?? "project_admin");
        
        // Show drift detection if project has repos and workflows
        if (response.selected_repos && response.selected_repos.length > 0 &&
            ((response.workflows && response.workflows.length > 0) || 
             (response.rxworkflows && response.rxworkflows.length > 0))) {
          // Drift detection could be enabled here if needed
        }

        const secretsPromises = (response.selected_repos ?? []).map((repo: string) => getSecrets(user, repo, response.project_name ?? ""));
        const envVarsPromises = (response.selected_repos ?? []).map((repo: string) => getEnvVars(user, repo, response.project_name ?? ""));

        const secretsResults = await Promise.all(secretsPromises);
        const envVarsResults = await Promise.all(envVarsPromises);

        // Discard results if navigation occurred while fetching secrets/envvars
        if (thisRequestId !== loadRequestCounterRef.current) return;

        // Note: Secret[] from API has flexible property names (secret_key/key/name) to support different contexts,
        // while ProjectSecret[] in state expects 'name'. Both are compatible at runtime.
        const allSecrets = secretsResults.flat();
        const allEnvVars = envVarsResults.flat().map((env: any) => ({
          env_key: env.env_key,
          value: env.value ?? "N/A",
          repo: env.repo
        }));

        setSecrets(allSecrets as any);
        setEnvVars(allEnvVars);
        
        // Load PR status if project has an ID.
        // Refresh from GitHub when:
        //   - pr_state is "open" (PRs are known to be open, may have been merged externally)
        //   - pr_state is null/undefined (legacy projects with no tracked state)
        //   - any workflow (regular, reusable, or linked) is stuck at "under_review" (indicates
        //     outstanding PRs; handles DB inconsistency — applies to standard, RWX, and linked)
        if (response.project_id) {
          const workflowsNeedSync = (response.workflows ?? []).some(
            (w: ProjectWorkflow) => w.workflowStatus === 'under_review'
          ) || (response.rxworkflows ?? []).some(
            (w: ProjectRXWorkflow) => w.workflowStatus === 'under_review'
          ) || (response.linked_reusable_workflows ?? []).some(
            (w: RwxWorkflow) => w.workflowStatus === 'under_review'
          );
          const shouldRefreshFromGitHub =
            options?.refreshPRFromGitHub ??
            (response.pr_state === "open" ||
              !response.pr_state ||
              workflowsNeedSync);
          await loadPRStatus(name, shouldRefreshFromGitHub);
        }
      }
    } catch (error) {
      console.error("❌ Error loading project:", error);
      if (options?.throwOnError) {
        throw error;
      }
    }
  }, [user, navigate, loadPRStatus]);

  const refreshProjectCampaignState = useCallback(async (refreshFromGitHub: boolean = false): Promise<void> => {
    if (!projectName) return;
    await loadProjectFromAPI(projectName, { throwOnError: true, refreshPRFromGitHub: refreshFromGitHub });
    await refreshProjectsList();
    setDriftRefreshSignal((current) => current + 1);
  }, [loadProjectFromAPI, projectName, refreshProjectsList]);

  useEffect(() => {
    if (urlProjectName) {
      console.log("📌 Reloading project from URL:", urlProjectName);
      setProjectName(urlProjectName);
      loadProjectFromAPI(urlProjectName);
    } else {
      // No project in the URL (e.g. user navigated back to the project list).
      // Incrementing the counter invalidates any in-flight loadProjectFromAPI call
      // so it won't overwrite state after we clear projectName here.
      ++loadRequestCounterRef.current;
      setProjectName("");
    }
  }, [urlProjectName, loadProjectFromAPI]);

  useEffect(() => {
    if (!user || !projectName) return;
    getProjectCodeownersStatuses(user, projectName)
      .then((data) => {
        const map: Record<string, string> = {};
        data.statuses.forEach(({ repo_name, status }) => { map[repo_name] = status; });
        setCodeownersStatuses(map);
      })
      .catch(() => {}); // best-effort; badge just won't show
  }, [user, projectName, codeownersRefreshCounter]);

  useEffect(() => {
    if (user) {
      console.log("📌 Fetching projects for user:", user);
      fetchProjects(user).then((updatedProjects: Project[] | null) => {
        setProjects(updatedProjects ?? []);
        // Set accountType from the first project if available
        if (updatedProjects && updatedProjects.length > 0 && (updatedProjects[0] as any).account_type) {
          setAccountType((updatedProjects[0] as any).account_type);
        }
      });
    }
  }, [user]);

  // Imported Actions Projects (shared, workspace-wide catalog surfaced in the
  // GUI workflow editor's step picker). Failure is non-fatal - this only
  // enhances a form, it shouldn't block the editor from loading.
  useEffect(() => {
    if (user) {
      listActionsProjects(user)
        .then(setImportedActions)
        .catch((err) => console.warn("Failed to load imported Actions Projects:", err));
      listActionGroups(user)
        .then(setActionGroups)
        .catch((err) => console.warn("Failed to load Action Groups:", err));
    }
  }, [user]);

  // Cleanup the local save toast timer on component unmount
  useEffect(() => {
    return () => {
      if (localSaveToastTimerRef.current) {
        clearTimeout(localSaveToastTimerRef.current);
      }
    };
  }, []);

  // Scroll to the correct anchor when navigating within the Repository Configs page
  useEffect(() => {
    if (REPO_CONFIG_SECTION_KEYS.includes(activeSection)) {
      // Use a short timeout to allow the DOM to render the stacked sections first
      const timer = setTimeout(() => {
        const el = document.getElementById(`repo-config-${activeSection}`);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }, REPO_CONFIG_SCROLL_DELAY_MS);
      return () => clearTimeout(timer);
    }
  }, [activeSection]);

  // Scrollspy: update the sidebar highlight as the user scrolls through repo config sections
  useEffect(() => {
    const container = sectionContainerRef.current;
    if (!container || !REPO_CONFIG_SECTION_KEYS.includes(activeSection)) return;
    if (typeof IntersectionObserver === "undefined") return;

    const observer = new IntersectionObserver(
      (entries) => {
        // Pick the intersecting section whose top edge is closest to the container top
        const topmost = entries
          .filter(e => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (topmost) {
          const key = topmost.target.id.replace('repo-config-', '');
          if (REPO_CONFIG_SECTION_KEYS.includes(key)) {
            setScrollActiveSection(key);
          }
        }
      },
      {
        root: container,
        // Section is "active" when its top is in the upper 50% of the scrollable area
        rootMargin: '0px 0px -50% 0px',
        threshold: 0,
      }
    );

    const setupTimer = setTimeout(() => {
      REPO_CONFIG_SECTION_KEYS.forEach(key => {
        const el = document.getElementById(`repo-config-${key}`);
        if (el) observer.observe(el);
      });
    }, REPO_CONFIG_SCROLL_DELAY_MS);

    return () => {
      clearTimeout(setupTimer);
      observer.disconnect();
    };
  }, [activeSection]);

  // Callback function to add standard workflows to the main workflows list
  const addWorkflowToMain = (newWorkflow: ProjectWorkflow): void => {
    setWorkflows(prevWorkflows => [...prevWorkflows, newWorkflow]);
  };

  const resetProjectState = (): void => {
    console.log("📌 Resetting project state before cancel.");
    setProjectName("");
    setSelectedRepos([]);
    setWorkflows([]);
    setRXWorkflows([]);
    setRegexPattern("");
    setBranchOption("default");
    setProjectCode("");
    setProjectId("");
    setSecrets([]);
    setEnvVars([]);
    setManualEnvVars([]);
    setManualSecrets([]);
    setDeploymentEnvironments([]);
    setReusableWorkflowsEnabled(false);
    setLinkedWorkflows([]);
    setActiveSection('workflows');
  };

  const handleDeleteProject = (): void => {
    if (!projectName.trim()) {
      toast.error("Select a valid project to delete.");
      return;
    }
    // Open the enhanced deletion modal instead of simple confirmation
    setIsDeleteModalOpen(true);
  };

  const handleConfirmDeleteProject = async (deleteGitHubResources: boolean, deleteDeploymentEnvironments: boolean = true): Promise<void> => {
    if (!user) {
      console.error("❌ Error: GitHub user is missing!");
      return;
    }

    try {
      setIsDeleteModalOpen(false);

      // Use the enhanced deletion API
      const result = await deleteProjectEnhanced(user, projectName, deleteGitHubResources, deleteDeploymentEnvironments);
      
      // Show detailed results
      let message = "✅ Project deleted successfully!";
      if (result.details) {
        const { github_resources_deleted, errors } = result.details;
        if (github_resources_deleted.length > 0) {
          message += `\n\nGitHub resources deleted:\n${github_resources_deleted.join('\n')}`;
        }
        if (errors.length > 0) {
          message += `\n\nSome errors occurred:\n${errors.join('\n')}`;
        }
      }
      
      toast.success(message);
      resetProjectState();
      fetchProjects(user).then(setProjects);
    } catch (error) {
      console.error("❌ Error deleting project:", error);
      toast.error("Error deleting project. Please try again.");
    }
  };

  const handleDriftLoaded = useCallback((details: WorkflowDriftDetail[]) => {
    setDriftDetails(details);
    // The drift check that produced `details` already persisted a fresh
    // drift_status on the project row server-side (see get_project_drift /
    // _cache_project_drift_summary in backend/workflows.py) - refresh the
    // list so it doesn't keep showing the pre-check status until next login.
    refreshProjectsList();
  }, [refreshProjectsList]);

  // Mirrors handlePRCreationSuccess's local-patch pattern below: a drift
  // resolve action (adopt GitHub version, restore directly, or create a fix
  // PR) changes workflow_status server-side, but DriftDetection only
  // refreshes its own drift list - it doesn't own workflows/rxworkflows, so
  // it reports the change back here instead of us waiting for a reload.
  const handleDriftWorkflowStatusesChanged = useCallback((workflowNames: string[], status: string) => {
    const nameSet = new Set(workflowNames);
    setWorkflows((prev: ProjectWorkflow[]) => prev.map(w =>
      nameSet.has(w.name) ? { ...w, workflowStatus: status } : w
    ));
    setRXWorkflows((prev: ProjectRXWorkflow[]) => prev.map(w =>
      nameSet.has(w.name) ? { ...w, workflowStatus: status } : w
    ));
    setLinkedWorkflows((prev: RwxWorkflow[]) => prev.map(w =>
      nameSet.has(w.workflow_name) ? { ...w, workflowStatus: status } : w
    ));
  }, []);

  // Shows a ConfirmDialog when there is drift; otherwise runs fn immediately.
  // Per the issue's safety rules, never silently overwrite GitHub changes.
  const ifNotDrifted = useCallback((actionLabel: string, fn: () => void): void => {
    if (driftDetails.length === 0) {
      fn();
      return;
    }
    setDriftDialogInfo({ label: actionLabel, onConfirm: fn });
  }, [driftDetails]);

  // Helper function to validate project state before saving
  const validateProjectState = (): string | null => {
    if (!projectName?.trim()) {
      return "❌ Project name is required.";
    }
    
    if (!user) {
      return "❌ User authentication required.";
    }
    
    if (selectedRepos.length === 0) {
      return "❌ At least one repository must be selected.";
    }
    
    return null;
  };

  // Helper function to collect and validate workflow names
  const validateWorkflowNames = (): string | null => {
    const allWorkflowNames: string[] = [];
    
    // Collect workflow names from regular workflows
    workflows.forEach(workflow => {
      if (workflow.name?.trim()) {
        allWorkflowNames.push(workflow.name.trim());
      }
    });
    
    // Collect workflow names from reusable workflows (RWX projects)
    rxworkflows.forEach(workflow => {
      if (workflow.name?.trim()) {
        allWorkflowNames.push(workflow.name.trim());
      }
    });
    
    // Check for duplicates
    const duplicateNames = allWorkflowNames.filter((name, index) => 
      allWorkflowNames.indexOf(name) !== index
    );
    
    if (duplicateNames.length > 0) {
      const uniqueDuplicates = [...new Set(duplicateNames)];
      return `❌ Duplicate workflow names found: "${uniqueDuplicates.join('", "')}".\n\nPlease ensure all workflow names are unique within this project before saving.`;
    }
    
    return null;
  };

  const doSaveProject = async (): Promise<void> => {
    // Log project state for debugging
    console.log("📌 Starting save with project state:", {
      projectName,
      projectId,
      selectedRepos: selectedRepos.length,
      workflows: workflows.length,
      rxworkflows: rxworkflows.length
    });
    
    // Initialize progress tracking
    setIsSaving(true);
    setSaveProgress(0);
    setSaveProgressText("Initializing save...");
    
    try {
      const updateProgress = (percentage: number, text: string): void => {
        setSaveProgress(percentage);
        setSaveProgressText(text);
      };
      
      // Determine whether to update GitHub based on the active section
      // Workflow sections save to database only (PR creation is explicit via Create Pull Requests button)
      // Non-workflow sections save directly to GitHub
      const shouldUpdateGitHub = activeSection !== 'workflows' && activeSection !== 'rxworkflows';
      
      const result = await handleSaveProjectWithModal({
        user: user!,
        projectName,
        selectedRepos,
        workflows,
        rxworkflows,
        envVars,
        manualEnvVars,
        secrets,
        manualSecrets,
        deploymentEnvironments,
        branchRegex: regexPattern,
        branchOption,
        branchMaxAgeDays,
        projectId,
        selectedItems: null,
        updateGitHub: shouldUpdateGitHub,
        reusableWorkflowsEnabled,
        onProgress: updateProgress as any,
        projectKey: null,
        repositoryVisibilityScope,
        validationRepo,
        preflightRequired,
      });
      
      // Handle validation errors
      if (!result.success && result.results && result.results.length > 0) {
        const errorMessage = result.results[0];
        if (errorMessage.includes("valid project name")) {
          toast.error("Enter a valid project name.");
          return;
        } else if (errorMessage.includes("at least one repository")) {
          toast.error("Please select at least one repository.");
          return;
        }
      }
      
      // Clear manual input fields after successful save
      if (result.success) {
        setManualEnvVars([{ env_key: "", value: "", repo: "" }]);
        setManualSecrets([{ name: "", value: "", repo: "" }]);
        setManualEnvironments([{ name: "" }]);
        
        if (clearWorkflowModifiedStatesFn) {
          clearWorkflowModifiedStatesFn();
        }

        // Immediately reflect the updated PR state so the button re-enables without a page refresh
        if (result.prState) {
          setProjectPRState(normalizeProjectPRState(result.prState));
        }
      }
      
      setSaveResults((result.results as any) ?? []);
      setSaveSuccess(result.success);
      setGithubUpdatePerformed(result.githubUpdatePerformed ?? false);
      setIsSaveResultsModalOpen(true);
    } catch (error: any) {
      console.error("Error during project save:", error);
      setSaveResults([`❌ An error occurred: ${error.message}` as any]);
      setSaveSuccess(false);
      setGithubUpdatePerformed(false);
      setIsSaveResultsModalOpen(true);
    } finally {
      setIsSaving(false);
      setSaveProgress(0);
      setSaveProgressText("");
    }
  };

  const handleSaveProjectClick = async (): Promise<void> => {
    // Validate project state
    const validationError = validateProjectState();
    if (validationError) {
      toast.error(validationError);
      return;
    }

    // Validate workflow names
    const workflowError = validateWorkflowNames();
    if (workflowError) {
      toast.error(workflowError);
      return;
    }

    // Safety: warn before overwriting any GitHub changes that drifted.
    // Only warn for actions that actually push to GitHub (non-workflow sections),
    // since the workflow Save button only persists locally.
    const willPushToGitHub = activeSection !== 'workflows' && activeSection !== 'rxworkflows';
    if (willPushToGitHub) {
      ifNotDrifted('Save to GitHub', () => { doSaveProject(); });
      return;
    }
    doSaveProject();
  };

  const handleStayOnProject = (): void => {
    setIsSaveResultsModalOpen(false);
    // Reload project data to reflect any changes made during save
    if (projectName) {
      loadProjectFromAPI(projectName);
    }
  };

  const handleGoToMain = (): void => {
    setIsSaveResultsModalOpen(false);
    resetProjectState();
    navigate(`/project/${user}`);
  };

  // Callbacks for workflow functions
  const handleRefreshStatusCallback = useCallback((refreshFn: () => Promise<void>, isLoading: boolean) => {
    setRefreshStatusFn(() => refreshFn);
    setIsRefreshingStatus(isLoading);
  }, []);

  // Callbacks for reusable workflow functions
  const handleGenerateTemplatesCallback = useCallback((generateFn: () => Promise<void>, isGenerating: boolean) => {
    setGenerateTemplatesFn(() => generateFn);
    setIsGeneratingTemplates(isGenerating);
  }, []);

  const handleAddRXWorkflowCallback = useCallback((addFn: () => void) => {
    setAddRXWorkflowFn(() => addFn);
  }, []);

  // Callback for workflow add function
  const handleAddWorkflowCallback = useCallback((addFn: () => void) => {
    setAddWorkflowFn(() => addFn);
  }, []);

  // Callback for clear workflow modified states function
  const handleClearWorkflowModifiedStatesCallback = useCallback((clearFn: () => void) => {
    setClearWorkflowModifiedStatesFn(() => clearFn);
  }, []);

  const handleFocusAddEnvironmentCallback = useCallback((focusFn: () => void) => {
    setFocusAddEnvironmentFn(() => focusFn);
  }, []);

  const handleAddEnvVarCallback = useCallback((addFn: () => void) => {
    setAddEnvVarFn(() => addFn);
  }, []);

  const handleAddSecretCallback = useCallback((addFn: () => void) => {
    setAddSecretFn(() => addFn);
  }, []);

  const recordLinkedWorkflow = (workflow: RwxWorkflow): void => {
    setLinkedWorkflows(prev => {
      const alreadyLinked = prev.some(w => w.workflow_id === workflow.workflow_id);
      if (alreadyLinked) return prev;
      return [...prev, workflow];
    });
    console.log(`✅ Workflow '${workflow.workflow_name}' linked to project '${projectName}'`);
  };

  // Handler for linking reusable workflows from the modal (supports bulk selection)
  const handleLinkWorkflow = async (workflows: RwxWorkflow[]): Promise<void> => {
    if (!user || !projectName) return;
    const results = await Promise.allSettled(
      workflows.map((workflow) =>
        linkReusableWorkflow(user, projectName, workflow.workflow_id, workflow.rwx_project_id)
          .then(() => recordLinkedWorkflow(workflow))
      )
    );
    const failed = results.filter((r) => r.status === 'rejected');
    if (failed.length > 0) {
      console.error("❌ Some workflows failed to link:", failed);
      toast.error(`${failed.length} workflow(s) failed to link. Please try again.`);
    }
  };

  const handleOpenLinkModal = (): void => {
    setManageFilterProjectId(undefined);
    setShowLinkedWorkflowsModal(true);
  };

  const handleCloseLinkedWorkflowsModal = (): void => {
    setShowLinkedWorkflowsModal(false);
    setManageFilterProjectId(undefined);
  };

  // Function to open Create PR modal
  const handleOpenCreatePRModal = (): void => {
    if (!projectName) {
      toast.error("Please save the project first before creating pull requests");
      return;
    }
    if (selectedRepos.length === 0) {
      toast.error("Please select at least one repository");
      return;
    }
    // Safety: opening a PR pushes local content to GitHub, which would silently
    // overwrite drifted workflows.  Confirm before proceeding.
    ifNotDrifted('Create Pull Requests', () => setShowCreatePRModal(true));
  };

  // Function to handle successful PR creation
  const handlePRCreationSuccess = (selectedWorkflowNames: string[], selectedReusableWorkflowNames: string[], selectedCustomFileIds: number[], selectedCodeownersRepos: string[] = []): void => {
    console.log("✅ PRs created successfully");
    // Reload PR status
    if (projectName) {
      loadPRStatus(projectName);
    }
    setPRStatusRefreshKey(prev => prev + 1);
    // Refresh project list to update status
    refreshProjectsList();
    // Re-check drift since freshly-pushed workflows now match GitHub
    setDriftRefreshSignal(prev => prev + 1);
    // Only mark the workflows that were actually included in the PR as under_review.
    // Omitted workflows must keep their current status unchanged.
    const selectedSet = new Set(selectedWorkflowNames);
    setWorkflows((prev: ProjectWorkflow[]) => prev.map(w =>
      selectedSet.has(w.name) ? { ...w, workflowStatus: 'under_review' } : w
    ));
    // Mark selected reusable workflows as under_review as well (own rxworkflows + linked)
    const selectedRXSet = new Set(selectedReusableWorkflowNames);
    if (selectedRXSet.size > 0) {
      setRXWorkflows((prev: ProjectRXWorkflow[]) => prev.map(w =>
        selectedRXSet.has(w.name) ? { ...w, workflowStatus: 'under_review' } : w
      ));
      // Linked reusable workflows use workflow_name (not .name) as the key
      setLinkedWorkflows((prev: RwxWorkflow[]) => prev.map(w =>
        selectedRXSet.has(w.workflow_name) ? { ...w, workflowStatus: 'under_review' } : w
      ));
    }
    // Mark selected custom files as under_review
    if (selectedCustomFileIds.length > 0) {
      const selectedCFSet = new Set(selectedCustomFileIds);
      setCustomFiles((prev: CustomFile[]) => prev.map(f =>
        selectedCFSet.has(f.id) ? { ...f, file_status: 'under_review' } : f
      ));
    }
    // Bump refresh counter so CodeownersManager reloads and shows under_review status
    if (selectedCodeownersRepos.length > 0) {
      setCodeownersRefreshCounter(prev => prev + 1);
    }
  };

  const handlePreflightStatusChange = (status: {
    status: string;
    runAt?: string | null;
    error?: string | null;
    prUrl?: string | null;
  }): void => {
    setLastPreflightStatus(status.status);
    setLastPreflightRunAt(status.runAt ?? null);
    setLastPreflightError(status.error ?? null);
    setLastPreflightPrUrl(status.prUrl ?? null);
  };

  // Callback for when project PR state changes (from PRStatusPanel or save-draft)
  const handleProjectStateChange = useCallback((newState: string): void => {
    const normalizedState = normalizeProjectPRState(newState);
    setProjectPRState(normalizedState);
    // Update all workflow types (regular, reusable, linked) so every project type
    // sees consistent lock lifecycle when PRs are resolved.
    if (normalizedState === 'synced') {
      // All PRs merged – only workflows that were under review should become synced.
      // Omitted workflows (e.g. still committed_locally) must not be affected.
      setWorkflows((prev: ProjectWorkflow[]) => prev.map(w =>
        w.workflowStatus === 'under_review' ? { ...w, workflowStatus: 'synced_with_github' } : w
      ));
      setRXWorkflows((prev: ProjectRXWorkflow[]) => prev.map(w =>
        w.workflowStatus === 'under_review' ? { ...w, workflowStatus: 'synced_with_github' } : w
      ));
      setLinkedWorkflows((prev: RwxWorkflow[]) => prev.map(w =>
        w.workflowStatus === 'under_review' ? { ...w, workflowStatus: 'synced_with_github' } : w
      ));
      setCustomFiles((prev: CustomFile[]) => prev.map(f =>
        f.file_status === 'under_review' ? { ...f, file_status: 'synced_with_github' } : f
      ));
      setCodeownersRefreshCounter(prev => prev + 1);
    } else if (normalizedState === 'draft') {
      // PR closed or draft saved – revert any under_review workflows to committed_locally
      setWorkflows((prev: ProjectWorkflow[]) => prev.map(w =>
        w.workflowStatus === 'under_review' ? { ...w, workflowStatus: 'committed_locally' } : w
      ));
      setRXWorkflows((prev: ProjectRXWorkflow[]) => prev.map(w =>
        w.workflowStatus === 'under_review' ? { ...w, workflowStatus: 'committed_locally' } : w
      ));
      setLinkedWorkflows((prev: RwxWorkflow[]) => prev.map(w =>
        w.workflowStatus === 'under_review' ? { ...w, workflowStatus: 'committed_locally' } : w
      ));
      setCustomFiles((prev: CustomFile[]) => prev.map(f =>
        f.file_status === 'under_review' ? { ...f, file_status: 'committed_locally' } : f
      ));
      setCodeownersRefreshCounter(prev => prev + 1);
    }
  }, []);

  // Function to open the PR Campaigns workspace
  const handleTogglePRStatusPanel = (): void => {
    setShowPRStatusPanel(false);
    setActiveSection('pr-history');
  };

  // Function to render the content based on active section
  // Helper function to render the project list when no project is selected
  const renderProjectList = (): React.ReactElement => {
    return (
      <ProjectList
        user={user}
        projects={projects}
        onReorder={handleProjectsReorder}
        reorderError={projectOrderError}
        onCreateProject={() => navigate(`/project/${user}/new`)}
        isCreateProjectDisabled={(() => {
          if (projects.length === 0) return false;
          const installationMode = userDetails?.installation_mode;
          const effectiveAccountType = userDetails?.account_type ?? accountType;
          const tierKey = getEffectiveTierKey(effectiveAccountType, installationMode);
          if (!tierKey) return true;
          if (tierKey === "self-hosted-beta") {
            // Disable only when BOTH per-type limits are reached
            const callerCount = projects.filter(p => (p.project_type ?? "standard") === "standard").length;
            const rwxCount = projects.filter(p => p.project_type === "rwx").length;
            return callerCount >= SELF_HOSTED_BETA_CALLER_LIMIT && rwxCount >= SELF_HOSTED_BETA_RWX_LIMIT;
          }
          const limit = PROJECT_TIER_CONFIG[tierKey].limit;
          return limit !== null && projects.length >= limit;
        })()}
      />
    );
  };

  // Helper to render the RWX read-only repo panel so it can be reused consistently.
  const renderRWXReadOnlyRepoPanel = (): React.ReactElement => {
    return (
      <div
        style={{
          padding: "1rem",
          backgroundColor: "rgba(33,150,243,0.08)",
          borderRadius: "8px",
          border: "1px solid rgba(33,150,243,0.3)",
        }}
      >
        <p
          style={{
            margin: 0,
            fontSize: "0.9rem",
            color: "var(--text-secondary)",
          }}
        >
          🔧 <strong>Reusable Workflow Project</strong> — Repository is fixed and cannot be changed.
        </p>
        <ul
          style={{
            marginTop: "0.5rem",
            paddingLeft: "1.25rem",
            fontSize: "0.9rem",
            color: "var(--text-secondary)",
          }}
        >
          {selectedRepos.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </div>
    );
  };

  // Helper function to render workflows section
  const renderWorkflows = (): React.ReactElement => {
    // For RWX projects, reusable workflows are always enabled and the repo always exists
    const effectiveReusableEnabled = projectType === 'rwx' ? true : reusableWorkflowsEnabled;
    const effectiveRepoExists = projectType === 'rwx' ? true : false;
    return (
      <div className="section-content">
        <div className="section-card-content">
          <UnifiedWorkflows
            user={user!}
            projectName={projectName}
            projectCode={projectCode}
            selectedRepos={selectedRepos}
            regexPattern={regexPattern}
            accountType={accountType ?? undefined}
            projectPRState={projectPRState}
            usePrefix={usePrefix}
            isReadOnly={isProjectReadOnly}
            branchOption={branchOption}
            workflows={workflows as any}
            setWorkflows={setWorkflows as any}
            onRefreshStatus={handleRefreshStatusCallback}
            onAddWorkflow={handleAddWorkflowCallback}
            onClearModifiedStates={handleClearWorkflowModifiedStatesCallback}
            rxworkflows={rxworkflows as any}
            setRXWorkflows={setRXWorkflows as any}
            addWorkflowToMain={addWorkflowToMain}
            onGenerateTemplates={handleGenerateTemplatesCallback}
            onAddRXWorkflow={handleAddRXWorkflowCallback}
            detectedBuildTypes={EMPTY_BUILD_TYPES}
            reusableWorkflowsEnabled={effectiveReusableEnabled}
            repoExists={effectiveRepoExists}
            linkedWorkflows={projectType === 'standard' ? linkedWorkflows : []}
            setLinkedWorkflows={projectType === 'standard' ? setLinkedWorkflows : undefined}
            canLinkReusableWorkflows={projectType === 'standard' && !isProjectReadOnly}
            onLinkReusableWorkflow={projectType === 'standard' && !isProjectReadOnly ? handleOpenLinkModal : undefined}
            onImportExisting={!isProjectReadOnly && selectedRepos.length > 0 ? () => setShowWorkflowImport(true) : undefined}
            refreshProjectsList={refreshProjectsList}
            onProjectStateChange={handleProjectStateChange}
            driftedWorkflowNames={driftedWorkflowNames}
            customFiles={customFiles as any}
            setCustomFiles={setCustomFiles as any}
            projectId={typeof projectId === 'number' ? projectId : (projectId ? Number(projectId) : 0)}
            onCustomFilesChange={(updated) => {
              setCustomFiles(updated as any);
              const hasLocalChanges = (updated as any[]).some(
                (f: any) => f.file_status !== "synced_with_github" || f.pending_delete
              );
              if (hasLocalChanges && (projectPRState === 'new' || projectPRState === 'synced')) {
                setProjectPRState('draft');
              }
            }}
            codeownersRefreshCounter={codeownersRefreshCounter}
            codeownersAggregateStatus={codeownersAggregateStatus ?? undefined}
            onCodeownersSaved={() => setCodeownersRefreshCounter(prev => prev + 1)}
            importedActions={importedActions}
            actionGroups={actionGroups}
            secrets={secrets}
            envVars={envVars}
          />
        </div>
      </div>
    );
  };

  const numericProjectId =
    typeof projectId === 'number' ? projectId : (projectId ? Number(projectId) : 0);

  // Render all Repository Config sections as a single scrolling page with anchor IDs
  const renderRepoConfigsPage = (): React.ReactElement => {
    return (
      <div className="repo-configs-page">
        {/* Repositories & Branches */}
        <section
          id="repo-config-repos-and-branches"
          className={`repo-config-section ${REPO_CONFIG_SLIDE_CLASS}`}
          aria-label="Repositories & Branches"
          aria-current={scrollActiveSection === 'repos-and-branches' ? 'location' : undefined}
        >
          <h2 className={`section-title ${REPO_CONFIG_SLIDE_TITLE_CLASS}`}>📁 Repositories &amp; Branches</h2>
          <div className="section-card-content">
            {projectType === "rwx" ? renderRWXReadOnlyRepoPanel() : (
              <RepositoriesAndBranches
                user={user!}
                repos={repos as any}
                setRepos={setRepos as any}
                selectedRepos={selectedRepos}
                setSelectedRepos={setSelectedRepos}
                setRegexPattern={setRegexPattern}
                regexPattern={regexPattern}
                branchOption={branchOption as any}
                setBranchOption={setBranchOption as any}
                branchMaxAgeDays={branchMaxAgeDays}
                setBranchMaxAgeDays={setBranchMaxAgeDays}
                projectId={projectId || null}
                visibilityScope={repositoryVisibilityScope}
                validationRepo={validationRepo}
                setValidationRepo={setValidationRepo}
                preflightRequired={preflightRequired}
                setPreflightRequired={setPreflightRequired}
              />
            )}
          </div>
        </section>

        {/* Deploy Environments */}
        <section
          id="repo-config-environments"
          className={`repo-config-section ${REPO_CONFIG_SLIDE_CLASS}`}
          aria-label="Deploy Environments"
          aria-current={scrollActiveSection === 'environments' ? 'location' : undefined}
        >
          <h2 className={`section-title ${REPO_CONFIG_SLIDE_TITLE_CLASS}`}>🚀 Deploy Environments</h2>
          <div className="section-card-content">
            <DeployEnvironments
              user={user!}
              selectedRepos={selectedRepos}
              accountType={accountType as any}
              installationMode={userDetails?.installation_mode}
              deploymentEnvironments={deploymentEnvironments as any}
              setDeploymentEnvironments={setDeploymentEnvironments as any}
              onFocusAddEnvironment={handleFocusAddEnvironmentCallback}
              manualEnvironments={manualEnvironments}
              setManualEnvironments={setManualEnvironments}
            />
          </div>
        </section>

        {/* Environment Variables */}
        <section
          id="repo-config-envvars"
          className={`repo-config-section ${REPO_CONFIG_SLIDE_CLASS}`}
          aria-label="Environment Variables"
          aria-current={scrollActiveSection === 'envvars' ? 'location' : undefined}
        >
          <h2 className={`section-title ${REPO_CONFIG_SLIDE_TITLE_CLASS}`}>🔧 Environment Variables</h2>
          <div className="section-card-content">
            <EnvVars
              user={user}
              projectName={projectName}
              envVars={envVars as any}
              manualEnvVars={manualEnvVars as any}
              setManualEnvVars={setManualEnvVars as any}
              selectedRepos={selectedRepos}
              setEnvVars={setEnvVars as any}
              accountType={accountType as any}
              installationMode={userDetails?.installation_mode}
              onAddEnvVar={handleAddEnvVarCallback}
              projectCode={projectCode}
              usePrefix={usePrefix}
            />
          </div>
        </section>

        {/* Environment Secrets */}
        <section
          id="repo-config-secrets"
          className={`repo-config-section ${REPO_CONFIG_SLIDE_CLASS}`}
          aria-label="Environment Secrets"
          aria-current={scrollActiveSection === 'secrets' ? 'location' : undefined}
        >
          <h2 className={`section-title ${REPO_CONFIG_SLIDE_TITLE_CLASS}`}>🔐 Environment Secrets</h2>
          <div className="section-card-content">
            <Secrets
              user={user}
              projectName={projectName}
              secrets={secrets as any}
              manualSecrets={manualSecrets as any}
              setManualSecrets={setManualSecrets as any}
              selectedRepos={selectedRepos}
              setSecrets={setSecrets as any}
              accountType={accountType as any}
              installationMode={userDetails?.installation_mode}
              onAddSecret={handleAddSecretCallback}
              projectCode={projectCode}
              usePrefix={usePrefix}
            />
          </div>
        </section>

        {/* Environment Rulesets */}
        <section
          id="repo-config-rulesets"
          className={`repo-config-section ${REPO_CONFIG_SLIDE_CLASS}`}
          aria-label="Environment Rulesets"
          aria-current={scrollActiveSection === 'rulesets' ? 'location' : undefined}
        >
          <h2 className={`section-title ${REPO_CONFIG_SLIDE_TITLE_CLASS}`}>🛡️ Environment Rulesets</h2>
          <div className="section-card-content">
            <RulesetManager
              user={user!}
              projectName={projectName}
              selectedRepos={selectedRepos}
            />
          </div>
        </section>

      </div>
    );
  };

  // Helper function to render default repositories and branches section with title
  const renderDefaultRepositoriesAndBranches = (): React.ReactElement => {
    if (projectType === "rwx") {
      return (
        <div className="section-content">
          <h2 className="section-title">Repositories & Branches</h2>
          <div className="section-card-content">
            <div style={{ padding: "1rem", backgroundColor: "rgba(33,150,243,0.08)", borderRadius: "8px", border: "1px solid rgba(33,150,243,0.3)" }}>
              <p style={{ margin: 0, fontSize: "0.9rem", color: "var(--text-secondary)" }}>
                🔧 <strong>Reusable Workflow Project</strong> — Repository is fixed and cannot be changed.
              </p>
              <ul style={{ marginTop: "0.5rem", paddingLeft: "1.25rem", fontSize: "0.9rem", color: "var(--text-secondary)" }}>
                {selectedRepos.map(r => <li key={r}>{r}</li>)}
              </ul>
            </div>
          </div>
        </div>
      );
    }
    return (
      <div className="section-content">
        <h2 className="section-title">Repositories & Branches</h2>
        <div className="section-card-content">
          <RepositoriesAndBranches
            user={user!}
            repos={repos as any}
            setRepos={setRepos as any}
            selectedRepos={selectedRepos}
            setSelectedRepos={setSelectedRepos}
            setRegexPattern={setRegexPattern}
            regexPattern={regexPattern}
            branchOption={branchOption as any}
            setBranchOption={setBranchOption as any}
            branchMaxAgeDays={branchMaxAgeDays}
            setBranchMaxAgeDays={setBranchMaxAgeDays}
            projectId={projectId || null}
            visibilityScope={repositoryVisibilityScope}
            validationRepo={validationRepo}
            setValidationRepo={setValidationRepo}
            preflightRequired={preflightRequired}
            setPreflightRequired={setPreflightRequired}
          />
        </div>
      </div>
    );
  };

  // Helper function to render project info / settings detail section
  const renderProjectInfo = (): React.ReactElement => {
    const typeLabel = getProjectTypeConfig(projectType).label;
    const modeCfg = getPrefixModeConfig(usePrefix);
    const modeColor = usePrefix ? "var(--color-success-text)" : "var(--color-warning-text)";
    const modeBg = usePrefix ? "rgba(16,185,129,0.08)" : "rgba(245,158,11,0.08)";
    const modeBorder = usePrefix ? "rgba(16,185,129,0.3)" : "rgba(245,158,11,0.3)";

    return (
      <div className="section-content">
        <div className="section-card-content">
          <h3 style={{ margin: "0 0 1rem", fontSize: "1.1rem", fontWeight: 600 }}>ℹ️ Project Info</h3>

          {/* Summary rows */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "max-content 1fr",
            gap: "0.5rem 1.5rem",
            fontSize: "0.9rem",
            marginBottom: "1.5rem",
          }}>
            <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>Project Key</span>
            <span style={{ fontWeight: 600 }}>{projectCode || "—"}</span>

            <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>Type</span>
            <span style={{ fontWeight: 600 }}>{typeLabel}</span>

            <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>Mode</span>
            <span style={{ fontWeight: 600, color: modeColor }}>{modeCfg.label}</span>
          </div>

          {/* Resource Naming Mode detail card */}
          <div style={{
            padding: "1rem 1.25rem",
            borderRadius: "8px",
            border: `1px solid ${modeBorder}`,
            backgroundColor: modeBg,
          }}>
            <div style={{ fontWeight: 700, fontSize: "0.95rem", color: modeColor, marginBottom: "0.4rem" }}>
              Resource Naming Mode: {modeCfg.label}
            </div>
            <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
              {modeCfg.summary}
            </p>
            <ul style={{ margin: "0.6rem 0 0", paddingLeft: "1.1rem", fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.7 }}>
              {modeCfg.bullets.map((bullet, i) => <li key={i}>{bullet}</li>)}
            </ul>
          </div>

          <ProjectColorSelector
            className="mt-6"
            value={projectColor}
            onChange={handleProjectColorChange}
            projectType={projectType}
            disabled={isProjectReadOnly}
          />
          {!isProjectReadOnly && projectColorSaveState !== "idle" && (
            <output className="mt-2 text-xs text-text-muted dark:text-text-muted-dark" aria-live="polite">
              {projectColorSaveState === "saving"
                ? "Saving…"
                : projectColorSaveState === "saved"
                  ? "✅ Saved"
                  : `❌ ${projectColorSaveError || "Failed to save project color."}`}
            </output>
          )}
        </div>
      </div>
    );
  };

  const renderBackupExport = (): React.ReactElement => {
    return (
      <div className="section-content">
        <div className="section-card-content">
          <h3 style={{ margin: "0 0 0.75rem", fontSize: "1.1rem", fontWeight: 600 }}>💾 Backup &amp; Export</h3>
          <p style={{ margin: "0 0 0.75rem", color: "var(--text-secondary)", fontSize: "0.9rem" }}>
            Download a versioned JSON backup of this project configuration and workflow definitions.
          </p>
          <p style={{ margin: "0 0 1rem", color: "var(--text-secondary)", fontSize: "0.85rem", lineHeight: 1.6 }}>
            Includes project metadata, linked repositories, branch configuration, workflows, workflow YAML, status/hash metadata,
            workflow version history (when available), project relationships, rulesets, CODEOWNERS records, repo workflow overrides,
            and linked reusable workflow relationships.
          </p>
          <p style={{ margin: "0 0 1.25rem", color: "var(--text-secondary)", fontSize: "0.85rem", lineHeight: 1.6 }}>
            <strong>Excluded for security:</strong> GitHub OAuth tokens, PATs, repository secret values, webhook secrets, license secrets,
            admin credentials, raw environment secret values, and other sensitive runtime-only configuration.
          </p>
          <Button variant="outline" onClick={handleExportBackup} disabled={!projectId}>
            ⬇️ Export Project Backup (JSON)
          </Button>
          <div style={{ marginTop: "1.25rem" }}>
            <p style={{ margin: "0 0 0.5rem", color: "var(--text-secondary)", fontSize: "0.9rem", fontWeight: 600 }}>
              Import Project Backup
            </p>
            <Button variant="outline" disabled>
              Import Project Backup
            </Button>
            <p style={{ margin: "0.6rem 0 0", color: "var(--text-secondary)", fontSize: "0.85rem", lineHeight: 1.6 }}>
              Import support is planned for a future release. Exported backups are being structured with an import-safe schema now so they can be reused later.
            </p>
          </div>
        </div>
      </div>
    );
  };

  // Helper function to render linked caller workflow projects section (RWX projects only)
  const renderLinkedProjects = (): React.ReactElement => {
    return (
      <div className="section-content">
        <div className="section-card-content">
          <div style={{ marginBottom: '1rem' }}>
            <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600 }}>🔗 Linked Projects</h3>
            <p style={{ margin: '0.25rem 0 0', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Caller workflow projects that are using this reusable workflow project.
            </p>
          </div>

          {linkedStandardProjects.length === 0 ? (
            <div style={{
              padding: '2rem',
              textAlign: 'center',
              border: '2px dashed var(--border-color)',
              borderRadius: '8px',
              color: 'var(--text-secondary)',
            }}>
              <p style={{ margin: 0 }}>No linked caller workflow projects found.</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {linkedStandardProjects.map((proj) => (
                <div
                  key={proj.project_id}
                  className="linked-workflow-card"
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>
                      📁 {proj.project_name}
                    </div>
                    {proj.project_code && (
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                        Project Key: <strong>{proj.project_code}</strong>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  };

  // Main section content renderer with reduced complexity
  const renderSectionContent = (): React.ReactElement => {
    if (!projectName) {
      return renderProjectList();
    }

    // Repository Configs sections share a single scrolling page
    if (REPO_CONFIG_SECTION_KEYS.includes(activeSection)) {
      return renderRepoConfigsPage();
    }

    switch (activeSection) {
      case 'workflows':
        return renderWorkflows();
      case 'pr-history':
        // PR Campaigns view — active rollout management plus completed PR activity
        return user ? (
          <PRHistoryPanel
            user={user}
            projectName={projectName}
            onCampaignStateRefresh={refreshProjectCampaignState}
          />
        ) : renderWorkflows();
      case 'project-info':
        return renderProjectInfo();
      case 'linked-workflows':
        // Linked workflow linking moved to Workflows > Add Workflow > Link Reusable Workflow
        return renderWorkflows();
      case 'linked-projects':
        // Linked projects are for RWX projects only; fall back to workflows for other types
        return projectType === "rwx" ? renderLinkedProjects() : renderWorkflows();
      case 'custom-files':
      case 'codeowners':
        // Both are now in the unified Project Files editor (workflows section)
        return renderWorkflows();
      case 'backup-export':
        return renderBackupExport();
      case 'danger-zone':
        return (
          <DangerZone
            projectName={projectName}
            onDeleteProject={handleDeleteProject}
          />
        );
      case 'project-members': {
        const numericProjectId = typeof projectId === 'number' ? projectId : (projectId ? Number(projectId) : undefined);
        return (
          <ProjectMembers
            projectId={numericProjectId}
            projectName={projectName}
            workspaceRole={userDetails?.workspace_role}
          />
        );
      }
      default:
        return renderDefaultRepositoriesAndBranches();
    }
  };

  // Extract nested ternary operation for main content CSS classes
  const getMainContentClasses = () => {
    if (!projectName) {
      return 'main-content without-sidebar';
    }
    const sidebarClass = isSidebarCollapsed ? 'collapsed' : '';
    return `main-content with-sidebar ${sidebarClass}`;
  };

  // Memoized values for button display logic
  const isWorkflowSection = useMemo(() => {
    return activeSection === 'workflows' || activeSection === 'rxworkflows' || activeSection === 'custom-files' || activeSection === 'codeowners';
  }, [activeSection]);

  // Determine if repos & branches section is currently visible
  const isRepoBranchSection = useMemo(() => {
    // Show when the user navigated to repos-and-branches OR has scrolled to it
    return (
      REPO_CONFIG_SECTION_KEYS.includes(activeSection) &&
      (activeSection === 'repos-and-branches' || scrollActiveSection === 'repos-and-branches')
    );
  }, [activeSection, scrollActiveSection]);

  // Dirty state: true when repos & branches config differs from the last-saved snapshot
  const isRepoBranchDirty = useMemo(() => {
    if (!savedRepoBranchSnapshot) return false;
    // Compare as sets so remove-then-re-add produces the same result
    const sortedCurrent = [...selectedRepos].sort((a, b) => a.localeCompare(b));
    const sortedSaved = [...savedRepoBranchSnapshot.selectedRepos].sort((a, b) => a.localeCompare(b));
    const reposDiffer =
      sortedCurrent.length !== sortedSaved.length ||
      sortedCurrent.some((r, i) => r !== sortedSaved[i]);
    return (
      reposDiffer ||
      regexPattern !== savedRepoBranchSnapshot.regexPattern ||
      branchOption !== savedRepoBranchSnapshot.branchOption ||
      branchMaxAgeDays !== savedRepoBranchSnapshot.branchMaxAgeDays ||
      validationRepo !== savedRepoBranchSnapshot.validationRepo ||
      preflightRequired !== savedRepoBranchSnapshot.preflightRequired
    );
  }, [savedRepoBranchSnapshot, selectedRepos, regexPattern, branchOption, branchMaxAgeDays, validationRepo, preflightRequired]);

  // Local save handler: saves repos & branches config to the database only (no GitHub update)
  const handleLocalSaveRepoConfig = async (): Promise<void> => {
    if (!projectName || !user) return;
    // Validate that at least one repository is selected before calling the API
    if (selectedRepos.length === 0) {
      toast.error("Please select at least one repository before saving.");
      return;
    }
    setIsLocalSaving(true);
    try {
      const result = await handleSaveProjectWithModal({
        user,
        projectName,
        selectedRepos,
        workflows,
        rxworkflows,
        envVars,
        manualEnvVars,
        secrets,
        manualSecrets,
        deploymentEnvironments,
        branchRegex: regexPattern,
        branchOption,
        branchMaxAgeDays,
        projectId,
        selectedItems: null,
        updateGitHub: false,
        reusableWorkflowsEnabled,
        onProgress: null,
        projectKey: null,
        usePrefix,
        repositoryVisibilityScope,
        validationRepo,
        preflightRequired,
      });
      if (result.success) {
        // Update snapshot so dirty indicator resets
        setSavedRepoBranchSnapshot({
          selectedRepos: [...selectedRepos],
          regexPattern,
          branchOption,
          branchMaxAgeDays,
          validationRepo,
          preflightRequired,
        });
        // Update project metadata from result if available
        if (result.projectId && !projectId) {
          setProjectId(result.projectId);
        }
        if (result.projectCode && !projectCode) {
          setProjectCode(result.projectCode);
        }
        if (result.prState) {
          setProjectPRState(normalizeProjectPRState(result.prState));
        }
        // Show "Changes saved" toast
        if (localSaveToastTimerRef.current) {
          clearTimeout(localSaveToastTimerRef.current);
        }
        setLocalSaveToastVisible(true);
        localSaveToastTimerRef.current = setTimeout(() => {
          setLocalSaveToastVisible(false);
        }, 3000);
      } else {
        // result.results[0] already contains a formatted error message from handleSaveProjectWithModal
        toast.error(result.results?.[0] ?? 'Save failed: Unknown error');
      }
    } catch (error: any) {
      toast.error(`Save failed: ${error.message}`);
    } finally {
      setIsLocalSaving(false);
    }
  };

  // Count modified workflows in the current section
  const modifiedWorkflowsCount = useMemo(() => {
    if (activeSection === 'workflows') {
      return workflows.filter(w => w.isModified).length;
    } else if (activeSection === 'rxworkflows') {
      return rxworkflows.filter(w => w.isModified).length;
    }
    return 0;
  }, [activeSection, workflows, rxworkflows]);

  // Determine if we should show the top Commit Locally button
  // Only show when in workflow sections AND there are multiple modified workflows
  const shouldShowTopCommitButton = useMemo(() => {
    return isWorkflowSection && modifiedWorkflowsCount > 1;
  }, [isWorkflowSection, modifiedWorkflowsCount]);

  const saveButtonText = useMemo(() => {
    if (isWorkflowSection) {
      // Show count of modified workflows when there are multiple
      if (modifiedWorkflowsCount > 1) {
        return `💾 Commit ${modifiedWorkflowsCount} Workflows`;
      }
      return "💾 Commit Locally";
    }
    return "";
  }, [isWorkflowSection, modifiedWorkflowsCount]);

  const shouldShowPRButton = useMemo(() => {
    return isWorkflowSection && 
           projectId && 
           ['draft', 'open', 'synced'].includes(projectPRState) && 
           selectedRepos.length > 0;
  }, [isWorkflowSection, projectId, projectPRState, selectedRepos.length]);

  const isPRButtonDisabled = useMemo(() => {
    return isSaving || projectPRState !== 'draft';
  }, [isSaving, projectPRState]);

  const isLocalSaveDisabled = useMemo(() => {
    return isLocalSaving || !isRepoBranchDirty || selectedRepos.length === 0;
  }, [isLocalSaving, isRepoBranchDirty, selectedRepos.length]);

  return (
    <div className="app-layout">
      {projectName && (
        <Sidebar 
          activeSection={REPO_CONFIG_SECTION_KEYS.includes(activeSection) ? scrollActiveSection : activeSection}
          onSectionChange={setActiveSection}
          projectName={projectName}
          onProjectNameSave={handleProjectNameSave}
          projectCode={projectCode}
          projectType={projectType}
          repositoryVisibilityScope={repositoryVisibilityScope}
          usePrefix={usePrefix}
          isReadOnly={isProjectReadOnly}
          onLinkReusableWorkflow={() => setShowLinkedWorkflowsModal(true)}
          isCollapsed={isSidebarCollapsed}
          onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
          isMobileOpen={isMobileSidebarOpen}
          onMobileClose={() => setIsMobileSidebarOpen(false)}
        />
      )}
      {projectName && isMobileSidebarOpen && (
        <div
          className="sidebar-mobile-backdrop"
          aria-hidden="true"
          onClick={() => setIsMobileSidebarOpen(false)}
        />
      )}
      
      <div className={getMainContentClasses()}>
        {!projectName ? (
          <div className="project-list-container">
            <div className="project-list-header">
              <BrandLogo variant="full" size="lg" className="main-title" />
              <div className="header-controls">
                {userDetails && (
                  <PlanUsagePill
                    accountType={userDetails.account_type}
                    projectsUsed={projects.length}
                    installationMode={userDetails.installation_mode}
                    callerProjectsUsed={projects.filter(p => (p.project_type ?? "standard") === "standard").length}
                    rwxProjectsUsed={projects.filter(p => p.project_type === "rwx").length}
                  />
                )}
                {userDetails && (
                  <UserAvatar 
                    avatarUrl={userDetails.avatar_url} 
                    username={userDetails.github_user} 
                    accountType={userDetails.account_type}
                    installationMode={userDetails.installation_mode}
                    githubAccountType={userDetails.github_account_type}
                    connectedGithubAccount={userDetails.connected_github_account}
                    connectedGithubAccountType={userDetails.connected_github_account_type}
                    workspaceRole={userDetails.workspace_role}
                    rateLimit={userDetails.rate_limit}
                    githubToken={userDetails.github_token}
                    onLogout={onLogout}
                  />
                )}
              </div>
            </div>
            {renderSectionContent()}
          </div>
        ) : (
          <>
            {/* Read-only banner for project_viewer users */}
            {isProjectReadOnly && (
              <div className="mb-2 px-4 py-2 rounded-lg text-sm font-medium bg-yellow-50 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-300 border border-yellow-200 dark:border-yellow-800">
                👁️ You have <strong>viewer</strong> access to this project. Editing is disabled.
              </div>
            )}
            <div className="content-header">
              <div className="content-header-nav">
                <button
                  className="sidebar-mobile-toggle"
                  aria-label={isMobileSidebarOpen ? 'Close navigation' : 'Open navigation'}
                  onClick={() => setIsMobileSidebarOpen(prev => !prev)}
                >
                  <span aria-hidden="true">☰</span>
                </button>
                <button
                  className="back-to-projects-button"
                  onClick={handleGoToMain}
                >
                  <span aria-hidden="true">←</span>{' '}
                  Back to Projects
                </button>
              </div>

              <div className="header-action-buttons">
                {/* Workflow-specific buttons - only show when workflows section is active */}
                {activeSection === 'workflows' && (
                  <>
                    {/* Import Existing Workflows Button */}
                    {!isProjectReadOnly && selectedRepos && selectedRepos.length > 0 && (
                      <Button
                        variant="outline"
                        onClick={() => setShowWorkflowImport(true)}
                        data-testid="import-workflows-button"
                      >
                        📥 Import Existing
                      </Button>
                    )}
                    {/* Refresh Status Button */}
                    {selectedRepos && selectedRepos.length > 0 && workflows.some(w => w.name && w.name.trim()) && refreshStatusFn && (
                      <Button
                        variant="outline"
                        onClick={refreshStatusFn}
                        disabled={isRefreshingStatus}
                      >
                        {isRefreshingStatus ? "🔄 Refreshing..." : "🔄 Refresh Status"}
                      </Button>
                    )}
                  </>
                )}

                {/* Reusable Workflow-specific buttons - only show when rxworkflows section is active */}
                {activeSection === 'rxworkflows' && (
                  <>
                    {/* Generate Templates Button */}
                    {generateTemplatesFn && (
                      <Button
                        variant="outline"
                        onClick={generateTemplatesFn}
                        disabled={isGeneratingTemplates}
                      >
                        {isGeneratingTemplates ? "🔄 Generating..." : "📝 Generate Templates"}
                      </Button>
                    )}
                  </>
                )}

                {/* Deploy Environments-specific buttons - only show when environments section is active */}
                {activeSection === 'environments' && (
                  <>
                    {/* Create Environment (focus add form) */}
                    {focusAddEnvironmentFn && (
                      <Button
                        variant="outline"
                        onClick={isProjectReadOnly ? undefined : focusAddEnvironmentFn}
                        disabled={isProjectReadOnly}
                        title={isProjectReadOnly ? "You have read-only access to this project" : undefined}
                      >
                        ➕ Create Environment
                      </Button>
                    )}
                  </>
                )}

                {/* Environment Variables-specific buttons - only show when envvars section is active */}
                {activeSection === 'envvars' && !isCloudFreeTier && (
                  <>
                    {/* Add Environment Variable Button */}
                    {addEnvVarFn && (
                      <Button 
                        variant="outline"
                        onClick={addEnvVarFn}
                      >
                        ➕ Add Environment Variable
                      </Button>
                    )}
                  </>
                )}

                {/* Environment Secrets-specific buttons - only show when secrets section is active */}
                {activeSection === 'secrets' && !isCloudFreeTier && (
                  <>
                    {/* Add Secret Button */}
                    {addSecretFn && (
                      <Button 
                        variant="outline"
                        onClick={addSecretFn}
                      >
                        ➕ Add Secret
                      </Button>
                    )}
                  </>
                )}
                
                {/* Spacer to separate section-specific buttons from standard buttons */}
                {((activeSection === 'workflows' && refreshStatusFn) || 
                  (activeSection === 'rxworkflows' && generateTemplatesFn) ||
                  (activeSection === 'environments' && focusAddEnvironmentFn) ||
                  (activeSection === 'envvars' && !isCloudFreeTier && addEnvVarFn) ||
                  (activeSection === 'secrets' && !isCloudFreeTier && addSecretFn)) && (
                  <div style={{ width: "1px", height: "40px", backgroundColor: "var(--border-color)", margin: "0 1rem" }}></div>
                )}
                
                {/* Standard action buttons - conditional display based on section */}
                {/* Repos & Branches: local Save button (DB only) + "Save to GitHub" */}
                {isRepoBranchSection && projectType !== "rwx" && (
                  <>
                    {/* Local Save button — saves draft without pushing to GitHub */}
                    <button
                      className="action-button secondary"
                      onClick={isProjectReadOnly ? undefined : handleLocalSaveRepoConfig}
                      disabled={isProjectReadOnly || isLocalSaveDisabled}
                      title={
                        isProjectReadOnly
                          ? "You have read-only access to this project"
                          : selectedRepos.length === 0
                            ? "Select at least one repository to save"
                            : isRepoBranchDirty
                              ? "Save changes to the app (no GitHub push)"
                              : "No unsaved changes"
                      }
                      style={{
                        opacity: (isProjectReadOnly || isLocalSaveDisabled) ? 0.5 : 1,
                        cursor: (isProjectReadOnly || isLocalSaveDisabled) ? "not-allowed" : "pointer"
                      }}
                    >
                      {isLocalSaving ? "⏳ Saving..." : "💾 Save"}
                    </button>
                    {/* "Changes saved" toast shown inline next to the button */}
                    {localSaveToastVisible && (
                      <output
                        className="repo-success-message"
                        aria-live="polite"
                        style={{ marginRight: "0.5rem" }}
                      >
                        <span className="success-icon">✅</span>
                        <span className="success-text">Changes saved</span>
                      </output>
                    )}
                  </>
                )}
                {/* Save button with section-appropriate text - only show for workflow sections when multiple workflows are modified */}
                {shouldShowTopCommitButton && (
                  <button 
                    className="action-button secondary" 
                    onClick={isProjectReadOnly ? undefined : handleSaveProjectClick}
                    disabled={isProjectReadOnly || isSaving}
                    title={isProjectReadOnly ? "You have read-only access to this project" : undefined}
                    style={{
                      opacity: (isProjectReadOnly || isSaving) ? 0.5 : 1,
                      cursor: (isProjectReadOnly || isSaving) ? "not-allowed" : "pointer"
                    }}
                  >
                    {isSaving ? "⏳ Saving..." : saveButtonText}
                  </button>
                )}
                
                {/* Create Pull Requests button - show for workflows/rxworkflows; disabled when no local commits are ready */}
                {shouldShowPRButton && (
                  <button 
                    className="action-button primary" 
                    onClick={isProjectReadOnly ? undefined : handleOpenCreatePRModal}
                    disabled={isProjectReadOnly || isPRButtonDisabled}
                    title={
                      isProjectReadOnly ? 'You have read-only access to this project' :
                      projectPRState === 'open' ? 'Pull requests are already open and under review' :
                      projectPRState === 'synced' ? 'Workflows are synced with GitHub – commit changes locally first' :
                      undefined
                    }
                    style={{
                      opacity: (isProjectReadOnly || isPRButtonDisabled) ? 0.5 : 1,
                      cursor: (isProjectReadOnly || isPRButtonDisabled) ? "not-allowed" : "pointer",
                      backgroundColor: "#2563eb",
                      color: "white"
                    }}
                  >
                    🚀 Create Pull Requests
                  </button>
                )}
                
                {/* User Avatar - positioned at the end */}
                {userDetails && (
                  <UserAvatar 
                    avatarUrl={userDetails.avatar_url} 
                    username={userDetails.github_user} 
                    accountType={userDetails.account_type}
                    installationMode={userDetails.installation_mode}
                    githubAccountType={userDetails.github_account_type}
                    connectedGithubAccount={userDetails.connected_github_account}
                    connectedGithubAccountType={userDetails.connected_github_account_type}
                    workspaceRole={userDetails.workspace_role}
                    rateLimit={userDetails.rate_limit}
                    githubToken={userDetails.github_token}
                    onLogout={onLogout}
                  />
                )}
              </div>
            </div>
            
            {/* Project-Level PR Campaign Banner */}
            {projectId && projectPRState === 'open' && (
              <div className="project-pr-status-banner" role="alert" aria-live="polite">
                <div className="pr-banner-content">
                  <div className="pr-banner-icon" aria-hidden="true">🔵</div>
                  <div className="pr-banner-text">
                    <strong>Active PR Campaign</strong>
                    <span className="pr-banner-subtitle">
                      This workflow is part of an active PR campaign. Changes to workflows will add commits to existing PRs.
                    </span>
                  </div>
                  <button 
                    className="pr-banner-button"
                    onClick={handleTogglePRStatusPanel}
                    aria-label="Manage PR Campaign"
                  >
                    <span aria-hidden="true">📊</span> Manage PR Campaign
                  </button>
                </div>
              </div>
            )}
            
            {/* Drift Detection Component */}
            <DriftDetection
              user={user!}
              projectId={typeof projectId === "number" ? projectId : (projectId ? Number(projectId) : null)}
              projectName={projectName}
              selectedRepos={selectedRepos}
              onDriftLoaded={handleDriftLoaded}
              refreshSignal={driftRefreshSignal}
              seededDriftNames={seededDriftNames}
              onWorkflowStatusesChanged={handleDriftWorkflowStatusesChanged}
            />
            
            {/* Progress bar for save operations */}
            {isSaving && (
              <div style={{
                width: "calc(100% - 2 * var(--spacing-xl))",
                margin: "0 var(--spacing-xl) 1rem",
                padding: "0.5rem",
                backgroundColor: "var(--background-color, #f5f5f5)",
                border: "1px solid var(--border-color, #ddd)",
                borderRadius: "4px"
              }}>
                <div style={{
                  fontSize: "0.9rem",
                  marginBottom: "0.5rem",
                  color: "var(--text-color, #333)"
                }}>
                  {saveProgressText}
                </div>
                <div style={{
                  width: "100%",
                  height: "8px",
                  backgroundColor: "var(--progress-background, #e0e0e0)",
                  borderRadius: "4px",
                  overflow: "hidden"
                }}>
                  <div style={{
                    width: `${saveProgress}%`,
                    height: "100%",
                    backgroundColor: "var(--progress-color, #4caf50)",
                    transition: "width 0.3s ease-in-out"
                  }}></div>
                </div>
                <div style={{
                  fontSize: "0.8rem",
                  marginTop: "0.25rem",
                  color: "var(--text-color-muted, #666)",
                  textAlign: "right"
                }}>
                  {Math.round(saveProgress)}%
                </div>
              </div>
            )}
            
            <div className="section-container" ref={sectionContainerRef}>
              {renderSectionContent()}
            </div>
          </>
        )}
      </div>
      
      
      {(() => {
        // Handle the case where saveResults are already strings (from API)
        // vs. SaveResultItem objects (legacy format)
        const convertedResults: string[] = saveResults.length > 0 ? saveResults.map((item: any): string => {
          // If item is already a string (new format from API), return it as-is
          if (typeof item === 'string') {
            return item;
          }
          
          // If item is a SaveResultItem object (legacy format), convert it
          if (typeof item === 'object' && item !== null) {
            return item.success 
              ? `✅ ${item.message ?? `Successfully processed ${item.repo ?? ''}`}`
              : `❌ ${item.error ?? item.message ?? `Failed to process ${item.repo ?? 'unknown'}`}`;
          }
          
          // Fallback for unexpected formats
          return `❌ Failed to process unknown item`;
        }) : [];
        
        return (
          <SaveResultsModal
            isOpen={isSaveResultsModalOpen}
            onClose={() => setIsSaveResultsModalOpen(false)}
            onStayOnProject={handleStayOnProject}
            onGoToMain={handleGoToMain}
            projectName={projectName}
            results={convertedResults as any}
            isSuccess={saveSuccess}
            githubUpdatePerformed={githubUpdatePerformed}
          />
        );
      })()}

      <DeleteProjectModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onConfirmDelete={handleConfirmDeleteProject}
        projectName={projectName}
        githubUser={user!}
      />
      
      {/* Legacy PR status drawer (campaign page is the primary entry point) */}
      {showPRStatusPanel && projectName && user && (
        <PRStatusPanel
          user={user}
          projectName={projectName}
          onClose={() => setShowPRStatusPanel(false)}
          refreshProjectsList={refreshProjectsList}
          onProjectStateChange={handleProjectStateChange}
          key={prStatusRefreshKey}
        />
      )}
      
      {/* Create PR Modal */}
      {showCreatePRModal && projectName && user && (
        <CreatePRModal
          user={user}
          projectName={projectName}
          repositories={selectedRepos.map((r: string) => ({ name: r }))}
          workflows={workflows.filter((w) => !w.isReusable).map((w) => ({ name: w.name, status: w.workflowStatus }))}
          customFiles={customFiles}
          reusableWorkflows={[
            // RWX project's own workflows use the first selected repo as source
            ...rxworkflows.map((w) => ({
              name: w.name,
              status: w.workflowStatus,
              sourceRepo: selectedRepos.length > 0 ? selectedRepos[0] : undefined
            })),
            // Linked workflows have their own source repo
            ...linkedWorkflows.map((w) => ({
              name: w.workflow_name,
              status: w.workflowStatus,
              sourceRepo: w.rwx_repo
            })),
          ]}
          validationRepo={validationRepo}
          preflightRequired={preflightRequired}
          preflightStatus={lastPreflightStatus}
          preflightRunAt={lastPreflightRunAt}
          preflightError={lastPreflightError}
          preflightPrUrl={lastPreflightPrUrl}
          onPreflightStatusChange={handlePreflightStatusChange}
          codeownersRepos={codeownersWithChanges}
          onClose={() => setShowCreatePRModal(false)}
          onSuccess={handlePRCreationSuccess}
        />
      )}

      {/* Workflow Import Modal */}
      {showWorkflowImport && numericProjectId > 0 && user && (
        <WorkflowImportPanel
          projectId={numericProjectId}
          projectName={projectName}
          githubUser={user}
          selectedRepos={selectedRepos}
          onImportComplete={(prState) => {
            if (prState) {
              setProjectPRState(normalizeProjectPRState(prState));
            }
            // Reload the full project so imported workflows appear immediately
            loadProjectFromAPI(projectName);
          }}
          onClose={() => setShowWorkflowImport(false)}
        />
      )}

      {/* Linked Workflows Modal */}
      {user && projectName && (
        <LinkedWorkflowsModal
          isOpen={showLinkedWorkflowsModal}
          user={user}
          projectName={projectName}
          alreadyLinkedIds={linkedWorkflows.map(w => w.workflow_id)}
          onLink={handleLinkWorkflow}
          filterProjectId={manageFilterProjectId}
          onClose={handleCloseLinkedWorkflowsModal}
        />
      )}

      {driftDialogInfo && (
        <ConfirmDialog
          open={true}
          title={`${driftDialogInfo.label} with unresolved drift?`}
          description="One or more workflows have been changed directly in GitHub since your last sync. Proceeding will overwrite those changes."
          confirmLabel={driftDialogInfo.label}
          destructive
          onConfirm={() => { const fn = driftDialogInfo.onConfirm; setDriftDialogInfo(null); fn(); }}
          onCancel={() => setDriftDialogInfo(null)}
        />
      )}

      {pendingRename !== null && (
        <ConfirmDialog
          open={true}
          title="Rename project?"
          description={`This will change the project display name to "${pendingRename}". The project key (${projectCode}) will remain unchanged.`}
          confirmLabel="Rename"
          onConfirm={confirmProjectRename}
          onCancel={() => setPendingRename(null)}
        />
      )}
    </div>
  );
}

export default RepoSelector;
