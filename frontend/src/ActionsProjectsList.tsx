import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { ChevronRight, Plus, FolderKanban } from "lucide-react";
import { Card } from "./components/ui/card";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Label } from "./components/ui/label";
import { listActionsProjects, ActionsProject } from "./api/actionsProjects";
import { listActionGroups, ActionGroup } from "./api/actionGroups";
import { toast } from "./utils/toast";
import { ActionBrandingIcon } from "./utils/actionBranding";
import ManageActionGroupsModal from "./components/ManageActionGroupsModal";

interface ActionsProjectsListProps {
  readonly user: string;
}

const ALL_GROUPS = "all";

export default function ActionsProjectsList({ user }: ActionsProjectsListProps): React.ReactElement {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ActionsProject[]>([]);
  const [actionGroups, setActionGroups] = useState<ActionGroup[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [groupFilter, setGroupFilter] = useState<string>(ALL_GROUPS);
  const [isManageGroupsOpen, setIsManageGroupsOpen] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listActionsProjects(user), listActionGroups(user)])
      .then(([projectsData, groupsData]) => {
        if (!cancelled) {
          setProjects(projectsData);
          setActionGroups(groupsData);
        }
      })
      .catch((err) => {
        if (!cancelled) toast.error(err instanceof Error ? err.message : "Failed to load Managed Actions");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  const filtersActive = searchQuery.trim().length > 0 || groupFilter !== ALL_GROUPS;

  const clearFilters = (): void => {
    setSearchQuery("");
    setGroupFilter(ALL_GROUPS);
  };

  const selectedGroup = actionGroups.find((g) => String(g.action_group_id) === groupFilter);

  const filteredProjects = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return projects.filter((project) => {
      if (query) {
        const haystack = `${project.name} ${project.owner} ${project.repo}`.toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      if (selectedGroup && !selectedGroup.actions_project_ids.includes(project.actions_project_id)) {
        return false;
      }
      return true;
    });
  }, [projects, searchQuery, selectedGroup]);

  return (
    <div className="w-full max-w-[1400px] mx-auto px-6 lg:px-8" data-testid="actions-projects-list">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-3xl font-bold text-gray-900 dark:text-white">Managed Actions</h2>
          <p className="mt-2 max-w-2xl text-sm text-gray-600 dark:text-slate-300">
            Custom GitHub Actions imported from an actions.yaml file.
          </p>
        </div>
        <div className="flex gap-2 self-start">
          <Button
            type="button"
            variant="outline"
            onClick={() => setIsManageGroupsOpen(true)}
            data-testid="manage-action-groups-button"
            className="inline-flex items-center gap-1.5"
          >
            <FolderKanban className="h-4 w-4" aria-hidden="true" />
            Manage Groups
          </Button>
          <Button
            type="button"
            onClick={() => navigate(`/project/${user}/actions-projects/new`)}
            data-testid="add-actions-project-button"
            className="inline-flex items-center gap-1.5"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add Managed Action
          </Button>
        </div>
      </div>

      {projects.length > 0 && (
        <div
          className="mb-4 rounded-lg border border-slate-200 bg-slate-50/60 p-4 shadow-sm dark:border-slate-700/80 dark:bg-slate-900/40"
          data-testid="actions-projects-toolbar"
        >
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end sm:gap-3">
              <div className="w-full sm:w-[280px] sm:flex-none">
                <Label htmlFor="actions-search" className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Search
                </Label>
                <Input
                  id="actions-search"
                  data-testid="actions-search-input"
                  placeholder="Search actions..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
              <div className="w-full sm:w-[200px] sm:flex-none">
                <Label htmlFor="actions-group-filter" className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Group
                </Label>
                <select
                  id="actions-group-filter"
                  data-testid="actions-group-filter"
                  value={groupFilter}
                  onChange={(e) => setGroupFilter(e.target.value)}
                  className="h-10 w-full rounded-md border border-slate-200 bg-white/80 px-3 text-sm text-slate-900 shadow-sm transition focus:outline-none focus:ring-2 focus:ring-sky-500/25 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-100 [color-scheme:light_dark]"
                >
                  <option value={ALL_GROUPS}>All Groups</option>
                  {actionGroups.map((group) => (
                    <option key={group.action_group_id} value={String(group.action_group_id)}>
                      {group.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center">
              <p className="text-sm text-slate-600 dark:text-slate-300" data-testid="actions-filtered-count">
                Showing <span className="font-medium text-slate-900 dark:text-slate-100">{filteredProjects.length}</span> of{" "}
                <span className="font-medium text-slate-900 dark:text-slate-100">{projects.length}</span>
              </p>
              {filtersActive && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={clearFilters}
                  data-testid="clear-actions-filters"
                >
                  Clear Filters
                </Button>
              )}
            </div>
          </div>
        </div>
      )}

      {!isLoading && projects.length === 0 && (
        <p className="text-sm text-gray-600 dark:text-slate-300">
          No Managed Actions yet. Add one from a repo's actions.yaml to get started.
        </p>
      )}

      {!isLoading && projects.length > 0 && filteredProjects.length === 0 && (
        <p className="text-sm text-gray-600 dark:text-slate-300">
          No actions match your filters.
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {filteredProjects.map((project) => (
          <Card
            key={project.actions_project_id}
            data-testid={`actions-project-card-${project.actions_project_id}`}
            className="cursor-pointer transition-shadow hover:shadow-md"
            onClick={() => navigate(`/project/${user}/actions-projects/${project.actions_project_id}`)}
          >
            <div className="flex items-center gap-3 p-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary dark:bg-primary-dark/10 dark:text-primary-dark">
                <ActionBrandingIcon icon={project.branding_icon} color={project.branding_color} size={20} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold text-text-primary dark:text-text-primary-dark">
                  {project.name}
                </p>
                <p className="truncate text-xs text-text-muted dark:text-text-muted-dark">
                  {project.owner}/{project.repo} · {project.inputs.length} input{project.inputs.length === 1 ? "" : "s"}
                </p>
              </div>
              <ChevronRight className="h-5 w-5 shrink-0 text-text-muted dark:text-text-muted-dark" aria-hidden="true" />
            </div>
          </Card>
        ))}
      </div>

      <ManageActionGroupsModal
        isOpen={isManageGroupsOpen}
        user={user}
        projects={projects}
        actionGroups={actionGroups}
        onGroupsChange={setActionGroups}
        onClose={() => setIsManageGroupsOpen(false)}
      />
    </div>
  );
}
