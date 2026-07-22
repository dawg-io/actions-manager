/* eslint-disable no-restricted-syntax -- Legacy: TODO migrate inline styles to Tailwind CSS classes */
import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Folder,
  FolderKanban,
  GitPullRequest,
  MoreHorizontal,
  PencilLine,
  Plus,
} from "lucide-react";
import { Project, WorkflowData } from "../api/projects";
import { PROJECT_COLOR_STYLES, normalizeProjectColorKey } from "../utils/projectColors";
import { cn } from "../lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import ProjectTypeBadge from "./ProjectTypeBadge";

// Constants for project state values
const PROJECT_STATE = {
  NEW: "new" as const,
  DRAFT: "draft" as const,
  OPEN: "open" as const,
  SYNCED: "synced" as const,
};

const STATE_DISPLAY = {
  NEW: "New" as const,
  DRAFT: "Draft" as const,
  OPEN: "Under Review" as const,
  SYNCED: "Synced" as const,
};

// Props interface for the ProjectList component
interface ProjectListProps {
  user?: string;
  projects?: Project[];
  onCreateProject?: () => void;
  isCreateProjectDisabled?: boolean;
}

const WARNING_STATUS_VALUES = new Set([
  "blocked",
  "drift",
  "drifted",
  "error",
  "failed",
  "failed_sync",
  "needs_attention",
]);

const LOCAL_CHANGE_STATUS_VALUES = new Set([
  "committed_locally",
  "draft",
  "local_changes",
  "new",
  "unsaved",
]);

const UNDER_REVIEW_STATUS_VALUES = new Set([
  "open",
  "under_review",
]);

const SYNCED_STATUS_VALUES = new Set([
  "synced",
  "synced_with_github",
]);

const normalizeStatusValue = (value: unknown): string => (
  typeof value === "string" ? value.trim().toLowerCase() : ""
);

const normalizeProjectName = (project: Project): string => (
  project.project_name?.trim()
  || project.name?.trim()
  || ""
);

const getProjectWorkflows = (project: Project): WorkflowData[] => [
  ...(project.workflows ?? []),
  ...(project.rxworkflows ?? []),
];

const getProjectWorkflowCount = (project: Project): number => {
  const count = project.workflow_count;
  if (typeof count === "number" && Number.isFinite(count) && count >= 0) return count;
  return getProjectWorkflows(project).length;
};

const projectHasWorkflowStatus = (project: Project, statusValues: Set<string>): boolean => (
  getProjectWorkflows(project).some((workflow) => statusValues.has(normalizeStatusValue(workflow.workflowStatus)))
);

const getCachedDriftStatus = (project: Project): string => {
  const projectFields = project as Project & Record<string, unknown>;
  const status = normalizeStatusValue(projectFields.drift_status);
  return status || "unknown";
};

const hasCachedDriftSummary = (project: Project): boolean => {
  const projectFields = project as Project & Record<string, unknown>;
  return (
    projectFields.drift_status !== undefined
    || projectFields.last_drift_check_at !== undefined
  );
};

const projectHasNeedsAttention = (project: Project): boolean => {
  const cachedStatus = getCachedDriftStatus(project);
  const cachedNeedsAttention = hasCachedDriftSummary(project)
    && (cachedStatus === "drifted" || cachedStatus === "check_failed");

  const projectFields = project as Project & Record<string, unknown>;
  const warningFields = [
    projectFields.drift_status,
    projectFields.sync_status,
    projectFields.workflow_status,
    projectFields.workflowStatus,
    projectFields.status,
  ];

  return cachedNeedsAttention
    || projectFields.has_drift === true
    || projectFields.blocked === true
    || warningFields.some((value) => WARNING_STATUS_VALUES.has(normalizeStatusValue(value)))
    || projectHasWorkflowStatus(project, WARNING_STATUS_VALUES);
};

const projectHasDrift = (project: Project): boolean => {
  if (hasCachedDriftSummary(project)) {
    return getCachedDriftStatus(project) === "drifted";
  }

  const projectFields = project as Project & Record<string, unknown>;
  const driftValues = new Set(["drift", "drifted", "drift_detected"]);
  const driftFields = [
    projectFields.drift_status,
    projectFields.workflow_status,
    projectFields.workflowStatus,
    projectFields.status,
  ];

  return projectFields.has_drift === true
    || driftFields.some((value) => driftValues.has(normalizeStatusValue(value)))
    || projectHasWorkflowStatus(project, driftValues);
};

type ProjectStateTone = "neutral" | "info" | "success" | "warning" | "danger";

const getProjectState = (project: Project): { label: string; tone: ProjectStateTone } => {
  const cachedDriftStatus = getCachedDriftStatus(project);
  if (projectHasDrift(project)) {
    return { label: "Drift Detected", tone: "danger" };
  }

  if (cachedDriftStatus === "check_failed") {
    return { label: "Needs Attention", tone: "warning" };
  }

  if (projectHasNeedsAttention(project)) {
    return { label: "Needs Sync", tone: "warning" };
  }

  const prState = project.pr_state ?? PROJECT_STATE.NEW;
  switch (prState) {
    case PROJECT_STATE.DRAFT:
      return { label: STATE_DISPLAY.DRAFT, tone: "warning" };
    case PROJECT_STATE.OPEN:
      return { label: STATE_DISPLAY.OPEN, tone: "info" };
    case PROJECT_STATE.SYNCED:
      return { label: STATE_DISPLAY.SYNCED, tone: "success" };
    case PROJECT_STATE.NEW:
    default:
      return { label: STATE_DISPLAY.NEW, tone: "neutral" };
  }
};

const getDriftIndicator = (project: Project): { label: string; tone: ProjectStateTone } | null => {
  if (!hasCachedDriftSummary(project)) return null;

  const driftStatus = getCachedDriftStatus(project);
  if (driftStatus === "drifted") return { label: "Drift detected", tone: "danger" };
  if (driftStatus === "check_failed") return { label: "Needs attention", tone: "warning" };
  if (driftStatus === "unknown") return { label: "Not checked", tone: "neutral" };
  return null;
};

const getStateBadgeClasses = (tone: ProjectStateTone): string => {
  switch (tone) {
    case "danger":
      return "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:border-rose-400/30 dark:bg-rose-400/10 dark:text-rose-200";
    case "warning":
      return "border-amber-500/30 bg-amber-500/10 text-amber-800 dark:border-amber-400/30 dark:bg-amber-400/10 dark:text-amber-200";
    case "success":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:border-emerald-400/30 dark:bg-emerald-400/10 dark:text-emerald-200";
    case "info":
      return "border-sky-500/30 bg-sky-500/10 text-sky-800 dark:border-sky-400/30 dark:bg-sky-400/10 dark:text-sky-200";
    case "neutral":
    default:
      return "border-slate-500/20 bg-slate-500/5 text-slate-700 dark:border-slate-400/20 dark:bg-slate-400/10 dark:text-slate-200";
  }
};

const formatUpdatedAt = (project: Project): string => {
  const raw = project.updated_at || project.created_at;
  const date = raw ? new Date(raw) : null;

  if (!date || Number.isNaN(date.getTime())) return "—";

  const now = new Date();
  const includeYear = date.getFullYear() !== now.getFullYear();
  return new Intl.DateTimeFormat(undefined, includeYear
    ? { month: "short", day: "numeric", year: "numeric" }
    : { month: "short", day: "numeric" },
  ).format(date);
};

const formatProjectMeta = (project: Project): string | null => {
  const repoCount = project.selected_repos?.length ?? 0;
  const parts: string[] = [];

  if (repoCount > 0) parts.push(`${repoCount} repo${repoCount === 1 ? "" : "s"}`);

  return parts.length > 0 ? parts.join(" · ") : null;
};

const ProjectList: React.FC<ProjectListProps> = ({
    user,
    projects = [],
    onCreateProject,
    isCreateProjectDisabled = false,
}) => {
  const navigate = useNavigate(); // ✅ React Router Navigation
  const [avatarErrors, setAvatarErrors] = useState<Record<string, boolean>>({});
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [projectTypeFilter, setProjectTypeFilter] = useState<"all" | "standard" | "rwx">("all");
  const [visibilityFilter, setVisibilityFilter] = useState<"all" | "public" | "private">("all");
  const [namingModeFilter, setNamingModeFilter] = useState<"all" | "prefix" | "no_prefix">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "new" | "draft" | "open" | "synced">("all");

  const handleAvatarError = (username: string): void => {
    setAvatarErrors(prev => ({ ...prev, [username]: true }));
  };

  const handleLoadProject = (projectName: string): void => {
    console.log("📌 Debug: Loading Project:", projectName);
  
    if (!user) {
      console.error("❌ Error: GitHub user is missing!");
      return;
    }
  
    // Navigate to the project URL; the parent's useEffect will trigger
    // loadProjectFromAPI (which has a staleness guard) to load the data.
    navigate(`/project/${user}/${projectName}`);
  };

  const filtersActive = (
    searchQuery.trim().length > 0
    || projectTypeFilter !== "all"
    || visibilityFilter !== "all"
    || namingModeFilter !== "all"
    || statusFilter !== "all"
  );

  const clearFilters = (): void => {
    setSearchQuery("");
    setProjectTypeFilter("all");
    setVisibilityFilter("all");
    setNamingModeFilter("all");
    setStatusFilter("all");
  };

  const filteredProjects = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();

    return projects.filter((project) => {
      const name = normalizeProjectName(project);
      const projectType = project.project_type ?? "standard";
      const visibility = project.repository_visibility_scope ?? "public";
      const usePrefix = project.use_prefix !== false;
      const state = project.pr_state ?? PROJECT_STATE.NEW;

      if (query && !name.toLowerCase().includes(query)) return false;
      if (projectTypeFilter !== "all" && projectType !== projectTypeFilter) return false;
      if (visibilityFilter !== "all" && visibility !== visibilityFilter) return false;
      if (namingModeFilter !== "all") {
        const namingMode = usePrefix ? "prefix" : "no_prefix";
        if (namingMode !== namingModeFilter) return false;
      }
      if (statusFilter !== "all" && state !== statusFilter) return false;
      return true;
    });
  }, [projects, searchQuery, projectTypeFilter, visibilityFilter, namingModeFilter, statusFilter]);
  

  const projectSummaryCards = useMemo(() => {
    const needsAttentionProjects = new Set(
      projects
        .filter(projectHasNeedsAttention)
        .map((project) => project.project_code),
    );
    const isOperational = (project: Project): boolean => (
      !needsAttentionProjects.has(project.project_code)
    );

    return [
      {
        label: "Total Projects",
        value: projects.length,
        icon: FolderKanban,
        accentClass: "text-slate-500 dark:text-slate-300",
      },
      {
        label: "Synced",
        value: projects.filter((project) => (
          isOperational(project)
          && getProjectState(project).label === STATE_DISPLAY.SYNCED
        )).length,
        icon: CheckCircle2,
        accentClass: "text-emerald-600 dark:text-emerald-300",
      },
      {
        label: "Draft / Local Changes",
        value: projects.filter((project) => (
          isOperational(project)
          && (
            project.pr_state === PROJECT_STATE.DRAFT
            || project.pr_state === PROJECT_STATE.NEW
            || projectHasWorkflowStatus(project, LOCAL_CHANGE_STATUS_VALUES)
          )
        )).length,
        icon: PencilLine,
        accentClass: "text-amber-600 dark:text-amber-300",
      },
      {
        label: "Under Review",
        value: projects.filter((project) => (
          isOperational(project)
          && (
            project.pr_state === PROJECT_STATE.OPEN
            || projectHasWorkflowStatus(project, UNDER_REVIEW_STATUS_VALUES)
          )
        )).length,
        icon: GitPullRequest,
        accentClass: "text-sky-600 dark:text-sky-300",
      },
      {
        label: "Needs Attention",
        value: needsAttentionProjects.size,
        icon: AlertTriangle,
        accentClass: "text-rose-600 dark:text-rose-300",
      },
    ];
  }, [projects]);

  return (
    <div className="w-full max-w-[1400px] mx-auto px-6 lg:px-8 space-y-6">

      <section
        aria-label="Project status summary"
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5"
      >
        {projectSummaryCards.map(({ label, value, icon: Icon, accentClass }) => (
          <div
            key={label}
            className="min-w-0 rounded-lg border border-slate-200 bg-white/90 px-4 py-3 shadow-sm dark:border-slate-700/80 dark:bg-slate-900/80"
            data-testid={`project-summary-card-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  {label}
                </p>
                <p className="mt-1 text-2xl font-semibold leading-none text-text-primary dark:text-text-primary-dark">
                  {value}
                </p>
              </div>
              <Icon className={`h-4 w-4 flex-shrink-0 ${accentClass}`} aria-hidden="true" />
            </div>
          </div>
        ))}
      </section>

      <Card className="w-full">
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex flex-col gap-1.5">
              <CardTitle>Saved Projects</CardTitle>
              <CardDescription>
                View and manage your workflow projects
              </CardDescription>
            </div>
            {onCreateProject && (
              <Button
                type="button"
                variant="outline"
                onClick={onCreateProject}
                disabled={isCreateProjectDisabled}
                data-testid="new-project-button"
                className="inline-flex items-center gap-1.5 self-start border-slate-600/80 bg-slate-700/90 text-slate-100 hover:border-slate-500 hover:bg-slate-600 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed dark:border-slate-600/80 dark:bg-slate-800/90 dark:text-slate-200 dark:hover:border-slate-500 dark:hover:bg-slate-700"
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                New Project
              </Button>
            )}
          </div>
          <div
            className="mt-4 rounded-lg border border-slate-200 bg-slate-50/60 p-4 shadow-sm dark:border-slate-700/80 dark:bg-slate-900/40"
            data-testid="projects-toolbar"
          >
            <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
              <div className="flex flex-col gap-4 md:flex-row md:flex-wrap md:items-end md:gap-3">
                <div className="w-full md:w-[320px] md:flex-none">
                  <Label htmlFor="project-search" className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    Search
                  </Label>
                  <Input
                    id="project-search"
                    data-testid="project-search-input"
                    placeholder="Search projects..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="bg-white/80 text-slate-900 shadow-sm placeholder:text-slate-400 dark:bg-slate-950/40 dark:text-slate-100 dark:placeholder:text-slate-500"
                  />
                </div>

                <div className="w-full md:w-[180px] md:flex-none">
                  <Label htmlFor="project-type-filter" className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    Type
                  </Label>
                  <select
                    id="project-type-filter"
                    data-testid="project-type-filter"
                    value={projectTypeFilter}
                    onChange={(e) => setProjectTypeFilter(e.target.value as typeof projectTypeFilter)}
                    className="h-10 w-full rounded-md border border-slate-200 bg-white/80 px-3 text-sm text-slate-900 shadow-sm transition focus:outline-none focus:ring-2 focus:ring-sky-500/25 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-100"
                    style={{ colorScheme: "light dark" }}
                  >
                    <option value="all">All</option>
                    <option value="standard">Standard</option>
                    <option value="rwx">Reusable (RWX)</option>
                  </select>
                </div>

                <div className="w-full md:w-[180px] md:flex-none">
                  <Label htmlFor="project-visibility-filter" className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    Visibility
                  </Label>
                  <select
                    id="project-visibility-filter"
                    data-testid="project-visibility-filter"
                    value={visibilityFilter}
                    onChange={(e) => setVisibilityFilter(e.target.value as typeof visibilityFilter)}
                    className="h-10 w-full rounded-md border border-slate-200 bg-white/80 px-3 text-sm text-slate-900 shadow-sm transition focus:outline-none focus:ring-2 focus:ring-sky-500/25 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-100"
                    style={{ colorScheme: "light dark" }}
                  >
                    <option value="all">All</option>
                    <option value="public">Public</option>
                    <option value="private">Private</option>
                  </select>
                </div>

                <div className="w-full md:w-[180px] md:flex-none">
                  <Label htmlFor="project-naming-mode-filter" className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    Naming Mode
                  </Label>
                  <select
                    id="project-naming-mode-filter"
                    data-testid="project-naming-mode-filter"
                    value={namingModeFilter}
                    onChange={(e) => setNamingModeFilter(e.target.value as typeof namingModeFilter)}
                    className="h-10 w-full rounded-md border border-slate-200 bg-white/80 px-3 text-sm text-slate-900 shadow-sm transition focus:outline-none focus:ring-2 focus:ring-sky-500/25 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-100"
                    style={{ colorScheme: "light dark" }}
                  >
                    <option value="all">All</option>
                    <option value="prefix">Prefix</option>
                    <option value="no_prefix">No Prefix</option>
                  </select>
                </div>

                <div className="w-full md:w-[180px] md:flex-none">
                  <Label htmlFor="project-status-filter" className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    Status
                  </Label>
                  <select
                    id="project-status-filter"
                    data-testid="project-status-filter"
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
                    className="h-10 w-full rounded-md border border-slate-200 bg-white/80 px-3 text-sm text-slate-900 shadow-sm transition focus:outline-none focus:ring-2 focus:ring-sky-500/25 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-100"
                    style={{ colorScheme: "light dark" }}
                  >
                    <option value="all">All</option>
                    <option value="new">New</option>
                    <option value="draft">Draft</option>
                    <option value="open">Under Review</option>
                    <option value="synced">Synced</option>
                  </select>
                </div>
              </div>

              <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center xl:flex-col xl:items-end">
                <p className="text-sm text-slate-600 dark:text-slate-300" data-testid="projects-filtered-count">
                  Showing <span className="font-medium text-slate-900 dark:text-slate-100">{filteredProjects.length}</span> of{" "}
                  <span className="font-medium text-slate-900 dark:text-slate-100">{projects.length}</span>
                </p>
                {filtersActive && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={clearFilters}
                    data-testid="clear-project-filters"
                    className="border-slate-300/70 text-slate-700 hover:bg-slate-100 dark:border-slate-600/80 dark:text-slate-200 dark:hover:bg-slate-800"
                  >
                    Clear Filters
                  </Button>
                )}
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {projects.length === 0 ? (
            <div className="text-center py-12 px-6">
              <p className="text-text-secondary dark:text-secondary-dark">
                No saved projects yet.
              </p>
            </div>
          ) : (
            <div className="p-3 sm:p-4">
              <div className="space-y-3">
                <div
                  className="hidden sm:grid project-list-grid rounded-md border border-slate-200/80 bg-slate-100/70 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-600 dark:border-slate-700/80 dark:bg-slate-800/30 dark:text-slate-300"
                  aria-hidden="true"
                >
                  <div>Project</div>
                  <div className="text-center">Type</div>
                  <div className="text-center">Scope</div>
                  <div className="text-center">State</div>
                  <div className="text-center">Activity</div>
                  <div className="text-center">Updated</div>
                  <div className="text-center">Workflows</div>
                  <div className="text-right">Actions</div>
                </div>
                {filteredProjects.length === 0 ? (
                  <div className="py-10 px-6 text-center">
                    <p className="text-sm text-muted-foreground">
                      No projects match your current search and filters.
                    </p>
                    {filtersActive && (
                      <div className="mt-4">
                        <Button variant="outline" size="sm" onClick={clearFilters}>
                          Clear Filters
                        </Button>
                      </div>
                    )}
                  </div>
                ) : filteredProjects
                  .sort((a, b) => new Date(b.updated_at || b.created_at || 0).getTime() - new Date(a.updated_at || a.created_at || 0).getTime())
                  .slice(0, filtersActive ? undefined : 10)
	                  .map((project) => {
	                    const projectName = normalizeProjectName(project);
	                    const projectState = project.pr_state ?? PROJECT_STATE.NEW;
	                    const showContinueEditing = projectState === PROJECT_STATE.DRAFT;
	                    const showConfigure = projectState === PROJECT_STATE.NEW;
	                    const showView = projectState === PROJECT_STATE.SYNCED || projectState === PROJECT_STATE.OPEN;
	                    const showOpenPrPlaceholder = projectState === PROJECT_STATE.OPEN;
	                    const scopeVisibility = (project.repository_visibility_scope ?? "public").toString().toLowerCase() === "private"
	                      ? "Private"
	                      : "Public";
	                    const usePrefix = project.use_prefix !== false;
	                    const namingModeLabel = usePrefix ? "Prefix" : "No Prefix";
                    const derivedState = getProjectState(project);
                    const projectMeta = formatProjectMeta(project);
                    const workflowCount = getProjectWorkflowCount(project);
                    const workflowLabel = workflowCount === 0
                      ? "No workflows"
                      : `${workflowCount} workflow${workflowCount === 1 ? "" : "s"}`;
                    const workflowLabelClasses = workflowCount === 0
                      ? "text-slate-500 dark:text-slate-400"
                      : "text-text-secondary dark:text-secondary-dark";
                    const driftIndicator = getDriftIndicator(project);
                    const projectFields = project as Project & Record<string, unknown>;
                    const projectColorKey = normalizeProjectColorKey(project.project_color);
                    const projectColorStyles = PROJECT_COLOR_STYLES[projectColorKey];
                    const prUrl = typeof projectFields.pr_url === "string"
                      ? projectFields.pr_url
                      : typeof projectFields.prUrl === "string"
                        ? projectFields.prUrl
                        : null;

                    return (
                      <div
                        key={project.project_id ?? project.id}
                        data-testid={`project-row-${projectName || project.project_code || String(project.project_id ?? project.id)}`}
                        className={cn(
                          "relative w-full rounded-lg border border-l-4 border-slate-200 bg-white/85 p-4 text-left shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50/90 dark:border-slate-700/80 dark:bg-slate-900/70 dark:hover:border-slate-600 dark:hover:bg-slate-900/90",
                          projectColorStyles.borderLeft,
                        )}
                      >
                        <button
                          className="absolute inset-0 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
                          onClick={() => handleLoadProject(projectName)}
                          aria-label={`Open project ${projectName || project.project_code || "project"}`}
                        />
                        <div className="relative pointer-events-none grid grid-cols-1 gap-3 sm:grid project-list-grid sm:items-center">
                          <div className="min-w-0">
                            <span className="inline-flex items-start gap-2 min-w-0">
                              <Folder
                                aria-hidden="true"
                               className={cn("mt-0.5 h-4 w-4 flex-shrink-0", projectColorStyles.icon)}
                              />
                              <span className="min-w-0">
                               <span className="block truncate font-medium text-text-primary dark:text-text-primary-dark">
                                 {projectName || "—"}
                               </span>
                               {projectMeta && (
                                 <span className="mt-1 block truncate text-xs text-slate-500 dark:text-slate-300">
                                   {projectMeta}
                                 </span>
                               )}
                              </span>
                            </span>
                          </div>
                          <div className="sm:justify-self-center">
                             <ProjectTypeBadge projectType={project.project_type} size="sm" />
                          </div>
                          <div
                             className="truncate text-xs text-text-secondary dark:text-secondary-dark sm:text-center"
                             data-testid={`project-scope-${project.project_id ?? project.id ?? project.project_code}`}
                          >
                             {scopeVisibility}
                             <span className="mx-1 text-text-secondary/50 dark:text-secondary-dark/50">·</span>
                             <span className={usePrefix ? "text-emerald-700 dark:text-emerald-200" : "text-amber-700 dark:text-amber-200"}>
                               {namingModeLabel}
                             </span>
                          </div>
                          <div
                             className="sm:justify-self-center"
                             data-testid={`project-status-${project.project_id ?? project.id ?? project.project_code}`}
                          >
                             <span
                              className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold tracking-wide ${getStateBadgeClasses(derivedState.tone)}`}
                              title={derivedState.label}
                            >
                              {derivedState.label}
                            </span>
                          </div>
                          <div className="min-w-0 text-sm text-text-secondary dark:text-secondary-dark sm:flex sm:items-center sm:justify-center">
                            {project.last_modified_by ? (
                              <span className="inline-flex items-center gap-1.5 min-w-0">
                               {!avatarErrors[project.last_modified_by] ? (
                                 <img
                                   src={`https://github.com/${encodeURIComponent(project.last_modified_by)}.png?size=40`}
                                   alt=""
                                   aria-hidden="true"
                                   onError={() => handleAvatarError(project.last_modified_by || '')}
                                   className="w-5 h-5 rounded-full flex-shrink-0"
                                 />
                               ) : (
                                 <span className="w-5 h-5 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center text-xs font-semibold text-gray-600 dark:text-gray-300 flex-shrink-0">
                                   {project.last_modified_by.charAt(0).toUpperCase()}
                                 </span>
                               )}
                               <span className="truncate">{project.last_modified_by}</span>
                              </span>
                            ) : (
                              <span className="text-text-secondary/50 dark:text-secondary-dark/50">—</span>
                            )}
                          </div>
                          <div className="text-sm text-text-secondary dark:text-secondary-dark sm:text-center sm:whitespace-nowrap">
                            {formatUpdatedAt(project)}
                          </div>
                          <div
                            className="sm:flex sm:items-center sm:justify-center sm:whitespace-nowrap"
                            data-testid={`project-workflows-${project.project_id ?? project.id ?? project.project_code}`}
                          >
                            <div className="inline-flex flex-col items-center gap-1">
                              <span className={`text-xs font-medium ${workflowLabelClasses}`}>
                                {workflowLabel}
                              </span>
                              {driftIndicator && (
                                <span
                                  className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-wide ${getStateBadgeClasses(driftIndicator.tone)}`}
                                  data-testid={`project-drift-indicator-${project.project_id ?? project.id ?? project.project_code}`}
                                >
                                  {driftIndicator.label}
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="pointer-events-auto flex justify-end sm:justify-self-end">
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                               <Button
                                 size="icon"
                                 variant="ghost"
                                 onClick={(e) => e.stopPropagation()}
                                 aria-label="More actions"
                                 data-testid={`project-more-${projectName || project.project_code}`}
                                 className="h-8 w-8 border border-transparent text-slate-500 hover:border-slate-300 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                               >
                                 <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                               </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
                               {showContinueEditing && (
                                 <DropdownMenuItem
                                   onSelect={() => handleLoadProject(projectName)}
                                   data-testid="project-action-continue-editing"
                                 >
                                   Continue Editing
                                 </DropdownMenuItem>
                               )}
                               {showConfigure && (
                                 <DropdownMenuItem
                                   onSelect={() => handleLoadProject(projectName)}
                                   data-testid="project-action-configure"
                                 >
                                   Configure
                                 </DropdownMenuItem>
                               )}
                               {showView && (
                                 <DropdownMenuItem
                                   onSelect={() => handleLoadProject(projectName)}
                                   data-testid="project-action-view"
                                 >
                                   View
                                 </DropdownMenuItem>
                               )}
                               {showOpenPrPlaceholder && prUrl && (
                                 <DropdownMenuItem
                                   onSelect={() => window.open(prUrl, "_blank", "noopener,noreferrer")}
                                   data-testid="project-action-open-pr"
                                 >
                                   Open PR
                                 </DropdownMenuItem>
                               )}
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </div>
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default ProjectList;
