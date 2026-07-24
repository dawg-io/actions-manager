import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  Rocket,
  Plus,
  Search,
  Copy,
  RefreshCw,
  MoreHorizontal,
  Trash2,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Edit,
} from "lucide-react";
import {
  deleteDeploymentEnvironment,
  createEnvironment,
  getEnvironments,
  syncEnvironment,
  getEnvironmentsCount,
} from "../api/environments";
import { CopyButton, copyToClipboard } from "../utils/copyUtils";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import ConfigBadge from "./ConfigBadge";

// TypeScript interfaces
interface Environment {
  name: string;
}

interface AllEnvironments {
  [repoName: string]: string[];
}

interface ManualEnvironment {
  name: string;
}

interface DeployEnvironmentsProps {
  user?: string;
  selectedRepos?: string[];
  accountType?: string;
  installationMode?: string | null;
  deploymentEnvironments?: string[];
  setDeploymentEnvironments?: (environments: string[]) => void;
  onFocusAddEnvironment?: (focusFn: () => void) => void;
  manualEnvironments?: ManualEnvironment[];
  setManualEnvironments?: (
    environments: ManualEnvironment[] | ((prev: ManualEnvironment[]) => ManualEnvironment[])
  ) => void;
  environmentsCount?: number;
}

const FREE_PLAN_LIMIT = 2;
const PROFESSIONAL_PLAN_LIMIT = 10;
const SELF_HOSTED_BETA_LIMIT = 6;

const DeployEnvironments: React.FC<DeployEnvironmentsProps> = ({
  user,
  selectedRepos = [],
  accountType,
  installationMode,
  setDeploymentEnvironments,
  onFocusAddEnvironment,
  manualEnvironments = [{ name: "" }],
  setManualEnvironments,
  environmentsCount: propEnvironmentsCount,
}) => {
  const isSelfHostedBeta = installationMode?.toLowerCase() === "self-hosted";
  const [environments, setEnvironments] = useState<string[]>([]);
  const [allEnvironments, setAllEnvironments] = useState<AllEnvironments>({});
  const [environmentsCount, setEnvironmentsCount] = useState<number>(
    propEnvironmentsCount ?? 0
  );
  const [isCountLoading, setIsCountLoading] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [deletingEnv, setDeletingEnv] = useState<string | null>(null);
  const [confirmDeleteEnv, setConfirmDeleteEnv] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState<string>("");

  const getEnvironmentsLimit = (): number => {
    if (isSelfHostedBeta) return SELF_HOSTED_BETA_LIMIT;
    if (accountType === "free") return FREE_PLAN_LIMIT;
    if (accountType === "professional") return PROFESSIONAL_PLAN_LIMIT;
    return Infinity;
  };

  const environmentsLimit = getEnvironmentsLimit();
  const isLimitedTier = isSelfHostedBeta || accountType === "free" || accountType === "professional";

  // Use only the first manual entry as the "draft" for the inline form
  const draft: ManualEnvironment = manualEnvironments?.[0] ?? { name: "" };

  const updateDraft = (next: Partial<ManualEnvironment>): void => {
    if (!setManualEnvironments) return;
    setManualEnvironments((prev) => {
      const list = prev && prev.length > 0 ? [...prev] : [{ name: "" }];
      list[0] = { ...list[0], ...next };
      return list;
    });
  };

  const clearDraft = (): void => {
    if (!setManualEnvironments) return;
    setManualEnvironments([{ name: "" }]);
    setErrorMessage(null);
  };

  // Update parent state whenever environments change
  useEffect(() => {
    if (setDeploymentEnvironments) {
      const allEnvironmentNames = [
        ...environments,
        ...manualEnvironments
          .map((env) => env.name.trim())
          .filter((name) => name && !environments.includes(name)),
      ];
      setDeploymentEnvironments(allEnvironmentNames);
    }
  }, [environments, manualEnvironments, setDeploymentEnvironments]);

  // Ensure there's always at least one empty input field
  useEffect(() => {
    if (manualEnvironments.length === 0 && setManualEnvironments) {
      setManualEnvironments([{ name: "" }]);
    }
  }, [manualEnvironments.length, setManualEnvironments]);

  const fetchEnvironmentCount = useCallback(async (): Promise<void> => {
    if (propEnvironmentsCount !== undefined) {
      setEnvironmentsCount(propEnvironmentsCount);
      return;
    }
    if (
      (!isSelfHostedBeta && accountType !== "free" && accountType !== "professional") ||
      !user ||
      selectedRepos.length === 0
    ) {
      return;
    }
    setIsCountLoading(true);
    try {
      const count = await getEnvironmentsCount(user, selectedRepos);
      setEnvironmentsCount(count);
    } catch (error) {
      console.error('Failed to load environment count:', error);
      setErrorMessage("Failed to load environment count.");
    } finally {
      setIsCountLoading(false);
    }
  }, [propEnvironmentsCount, isSelfHostedBeta, accountType, user, selectedRepos]);

  const fetchEnvironments = useCallback(async (): Promise<void> => {
    try {
      const allEnvironmentsData: AllEnvironments = {};

      const environmentsPerRepo = await Promise.all(
        selectedRepos.map(async (repo) => {
          const repoEnvironments: Environment[] = await getEnvironments(user, repo);
          return { repo, environments: repoEnvironments.map((env) => env.name) };
        })
      );

      environmentsPerRepo.forEach(({ repo, environments }) => {
        allEnvironmentsData[repo] = environments;
      });

      setAllEnvironments(allEnvironmentsData);

      // Collect all unique environments across repositories
      const uniqueEnvironments = new Set<string>();
      Object.values(allEnvironmentsData).forEach((envs) => {
        envs.forEach((env) => uniqueEnvironments.add(env));
      });
      setEnvironments(Array.from(uniqueEnvironments));
    } catch (error: any) {
      setErrorMessage(
        error.response?.data?.error ?? "Failed to fetch environments."
      );
    }
  }, [selectedRepos, user]);

  useEffect(() => {
    fetchEnvironments();
    if (isSelfHostedBeta || accountType === "free" || accountType === "professional") {
      fetchEnvironmentCount();
    }
  }, [user, selectedRepos, isSelfHostedBeta, accountType, fetchEnvironmentCount, fetchEnvironments]);

  const trimmedName = (draft.name || "").trim();
  const isFormValid = trimmedName.length > 0;
  const atLimit = isLimitedTier && environmentsCount >= environmentsLimit;
  const canAdd = isFormValid && !isSaving && !atLimit;

  const focusAddForm = useCallback((): void => {
    if (atLimit) {
      if (isSelfHostedBeta) {
        setErrorMessage(
          `Self-Hosted Beta: You can create up to ${environmentsLimit} deployment environments per project. You have reached the limit.`
        );
      } else {
        const tierName = accountType === "free" ? "Free" : "Professional";
        const upgradeMsg =
          accountType === "free"
            ? ` Upgrade to Professional for up to ${PROFESSIONAL_PLAN_LIMIT} deployment environments per project.`
            : " Upgrade to Enterprise for unlimited deployment environments.";
        setErrorMessage(
          `${tierName} plan users can create up to ${environmentsLimit} deployment environments per project. You have reached the limit.${upgradeMsg}`
        );
      }
      return;
    }

    const el = document.getElementById("deploy-env-add-name");
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.focus();
    }
  }, [atLimit, accountType, environmentsLimit]);

  useEffect(() => {
    if (onFocusAddEnvironment) {
      onFocusAddEnvironment(focusAddForm);
    }
  }, [onFocusAddEnvironment, focusAddForm]);

  const handleCreateEnvironment = useCallback(async (): Promise<void> => {
    if (!isFormValid || isSaving) return;
    if (atLimit) {
      if (isSelfHostedBeta) {
        setErrorMessage(
          `Self-Hosted Beta: You can create up to ${environmentsLimit} deployment environments per project. You have reached the limit.`
        );
      } else {
        const tierName = accountType === "free" ? "Free" : "Professional";
        const upgradeMsg =
          accountType === "free"
            ? ` Upgrade to Professional for up to ${PROFESSIONAL_PLAN_LIMIT} deployment environments per project.`
            : " Upgrade to Enterprise for unlimited deployment environments.";
        setErrorMessage(
          `${tierName} plan users can create up to ${environmentsLimit} deployment environments per project. You have reached the limit.${upgradeMsg}`
        );
      }
      return;
    }

    setIsSaving(true);
    setErrorMessage(null);
    try {
      for (const repo of selectedRepos) {
        await createEnvironment(user, repo, trimmedName);
      }

      // Clear the draft on success
      if (setManualEnvironments) {
        setManualEnvironments([{ name: "" }]);
      }

      // Refresh environments after creating new ones
      await fetchEnvironments();

      // Refresh environment count for free and professional accounts
      if (isLimitedTier) {
        await fetchEnvironmentCount();
      }

      setSuccessMessage(`Environment "${trimmedName}" created in GitHub.`);
    } catch (error: any) {
      setErrorMessage(
        error.response?.data?.error || "Failed to create environment."
      );
    } finally {
      setIsSaving(false);
    }
  }, [
    isFormValid,
    isSaving,
    atLimit,
    trimmedName,
    accountType,
    environmentsLimit,
    selectedRepos,
    user,
    setManualEnvironments,
    isLimitedTier,
    fetchEnvironments,
    fetchEnvironmentCount,
  ]);

  // Auto-clear success messages after a short delay
  useEffect(() => {
    if (!successMessage) return;
    const t = setTimeout(() => setSuccessMessage(null), 3500);
    return () => clearTimeout(t);
  }, [successMessage]);

  const performDelete = async (environmentName: string): Promise<void> => {
    setDeletingEnv(environmentName);
    setErrorMessage(null);
    try {
      await deleteDeploymentEnvironment(user, selectedRepos, environmentName);

      // Refresh environments after deletion
      await fetchEnvironments();

      // Refresh environment count for free and professional accounts
      if (isLimitedTier) {
        await fetchEnvironmentCount();
      }

      setSuccessMessage(`Environment "${environmentName}" deleted from GitHub.`);
    } catch (error: any) {
      setErrorMessage(
        error.response?.data?.error || `Failed to delete environment '${environmentName}'.`
      );
    } finally {
      setDeletingEnv(null);
      setConfirmDeleteEnv(null);
    }
  };

  const handleSyncEnvironment = async (environmentName: string): Promise<void> => {
    setErrorMessage(null);
    try {
      await syncEnvironment(user, "", selectedRepos, environmentName);

      // Refresh environments after sync
      await fetchEnvironments();

      // Refresh environment count for free and professional accounts
      if (isLimitedTier) {
        await fetchEnvironmentCount();
      }

      setSuccessMessage(`Synced ${environmentName} to all repositories.`);
    } catch (error: any) {
      setErrorMessage(
        error.response?.data?.error || `Failed to sync environment '${environmentName}'.`
      );
    }
  };

  const handleEdit = (environmentName: string): void => {
    // Pre-fill the environment name into the form for editing
    updateDraft({ name: environmentName });
    const el = document.getElementById("deploy-env-add-name");
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.focus();
    }
  };

  const allEnvNames = useMemo(() => environments, [environments]);
  const filteredEnvNames = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return allEnvNames;
    return allEnvNames.filter((name) => name.toLowerCase().includes(term));
  }, [allEnvNames, searchTerm]);

  const totalCount = allEnvNames.length;
  const syncedCount = useMemo(
    () =>
      allEnvNames.filter((env) => {
        return Object.entries(allEnvironments).every(([_, envs]) =>
          envs.includes(env)
        );
      }).length,
    [allEnvNames, allEnvironments]
  );

  const renderEnvironmentCard = (envName: string) => {
    const envReposSet = Object.entries(allEnvironments)
      .filter(([_, envs]) => envs.includes(envName))
      .map(([repo]) => repo);
    const missingRepos = selectedRepos.filter((repo) => !envReposSet.includes(repo));
    const isSynced = missingRepos.length === 0;
    const isDeleting = deletingEnv === envName;

    return (
      <div
        key={envName}
        data-testid={`env-card-${envName}`}
        className="group relative flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 transition-colors hover:border-blue-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900/40 dark:hover:border-blue-500/50 dark:hover:bg-slate-900/60"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                className="truncate font-mono text-sm font-semibold text-slate-900 dark:text-slate-100"
                title={envName}
              >
                {envName}
              </span>
              <CopyButton
                textToCopy={envName}
                title={`Copy environment name: ${envName}`}
              />
            </div>
            <div className="mt-1 text-xs text-slate-600 dark:text-slate-300">
              {isSynced
                ? `Synced across all ${selectedRepos.length} ${selectedRepos.length === 1 ? "repository" : "repositories"}`
                : `Present in ${envReposSet.length} of ${selectedRepos.length} ${selectedRepos.length === 1 ? "repository" : "repositories"}`}
            </div>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0 text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
                aria-label={`Actions for ${envName}`}
                disabled={isDeleting}
              >
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              {!isSynced && (isSelfHostedBeta || accountType !== "free") && (
                <DropdownMenuItem
                  onSelect={() => {
                    handleSyncEnvironment(envName);
                  }}
                >
                  <RefreshCw className="mr-2 h-4 w-4" /> Sync
                </DropdownMenuItem>
              )}
              <DropdownMenuItem
                onSelect={() => {
                  copyToClipboard(envName);
                }}
              >
                <Copy className="mr-2 h-4 w-4" /> Copy
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => {
                  handleEdit(envName);
                }}
              >
                <Edit className="mr-2 h-4 w-4" /> Edit
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => {
                  setConfirmDeleteEnv(envName);
                }}
                className="text-red-600 focus:text-red-700 dark:text-red-400 dark:focus:text-red-300"
              >
                <Trash2 className="mr-2 h-4 w-4" /> Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <ConfigBadge variant="info">Environment</ConfigBadge>
          {isSynced ? (
            <ConfigBadge variant="synced" icon={<CheckCircle2 className="h-3 w-3" />}>
              Synced
            </ConfigBadge>
          ) : (
            <ConfigBadge variant="warning" icon={<AlertTriangle className="h-3 w-3" />}>
              Not synced ({missingRepos.length} repo{missingRepos.length === 1 ? "" : "s"})
            </ConfigBadge>
          )}
          {isDeleting && (
            <ConfigBadge variant="saving" icon={<Loader2 className="h-3 w-3 animate-spin" />}>
              Deleting…
            </ConfigBadge>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-5">
      {/* Header summary card */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/40">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-300">
              <Rocket className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                Deploy Environments
              </h3>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                Manage GitHub deployment environments used by this project.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <ConfigBadge variant="info">{totalCount} Environments</ConfigBadge>
            <ConfigBadge variant="synced">Synced: {syncedCount}</ConfigBadge>
            <ConfigBadge variant="neutral">Project Scope</ConfigBadge>
            {isLimitedTier && (
              <ConfigBadge variant="limited">
                {isCountLoading
                  ? "Loading…"
                  : `${environmentsCount}/${environmentsLimit} used`}
              </ConfigBadge>
            )}
          </div>
        </div>
        {isLimitedTier && (
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            {isSelfHostedBeta
              ? <><strong>Self-Hosted Beta:</strong> You can create up to {environmentsLimit} deployment environments per project.</>
              : <><strong>{accountType === "free" ? "Free" : "Professional"} Plan:</strong> You can create up to {environmentsLimit} deployment environments per project.</>
            }
          </p>
        )}
      </div>

      {/* Status messages */}
      {errorMessage && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="flex-1">{errorMessage}</span>
          <button
            type="button"
            className="text-xs underline opacity-80 hover:opacity-100"
            onClick={() => setErrorMessage(null)}
          >
            Dismiss
          </button>
        </div>
      )}
      {successMessage && (
        <output
          className="flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300"
        >
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          <span>{successMessage}</span>
        </output>
      )}

      {/* Add Environment form card */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/40">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Add Environment
          </h4>
          {atLimit && <ConfigBadge variant="limited">Limited</ConfigBadge>}
        </div>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label
              htmlFor="deploy-env-add-name"
              className="text-xs font-medium text-slate-700 dark:text-slate-300"
            >
              Environment Name
            </label>
            <Input
              id="deploy-env-add-name"
              data-testid="deploy-env-add-name"
              type="text"
              placeholder="e.g. development"
              value={draft.name || ""}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                updateDraft({ name: e.target.value })
              }
              disabled={isSaving || atLimit}
            />
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Environment names should match the target GitHub environment.
            </span>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
          {isSaving && (
            <ConfigBadge variant="saving" icon={<Loader2 className="h-3 w-3 animate-spin" />}>
              Saving…
            </ConfigBadge>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={clearDraft}
            disabled={isSaving || !draft.name}
          >
            Clear
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={handleCreateEnvironment}
            disabled={!canAdd}
            data-testid="deploy-env-add-submit"
          >
            {isSaving ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Adding…
              </>
            ) : (
              <>
                <Plus className="h-4 w-4" />
                Add Environment
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Existing environments section */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/40">
        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Environments
            </h4>
            <ConfigBadge variant="neutral">{totalCount}</ConfigBadge>
          </div>
          {totalCount > 0 && (
            <div className="relative w-full sm:w-64">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                type="search"
                placeholder="Search environments…"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-8"
                aria-label="Search deployment environments"
              />
            </div>
          )}
        </div>
        {totalCount === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-slate-300 px-4 py-8 text-center dark:border-slate-700">
            <Rocket className="h-6 w-6 text-slate-400" />
            <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
              No environments yet
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Add your first deployment environment for this project.
            </p>
          </div>
        ) : filteredEnvNames.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-300 px-4 py-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
            No environments match &ldquo;{searchTerm}&rdquo;.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {filteredEnvNames.map(renderEnvironmentCard)}
          </div>
        )}
      </div>

      {/* Delete confirmation dialog */}
      <Dialog
        open={confirmDeleteEnv !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmDeleteEnv(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete deployment environment?</DialogTitle>
            <DialogDescription>
              This will permanently remove{" "}
              <span className="font-mono font-semibold">{confirmDeleteEnv}</span> from
              the selected repositories on GitHub. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfirmDeleteEnv(null)}
              disabled={deletingEnv === confirmDeleteEnv}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => confirmDeleteEnv && performDelete(confirmDeleteEnv)}
              disabled={deletingEnv === confirmDeleteEnv}
              data-testid="deploy-env-confirm-delete"
            >
              {deletingEnv === confirmDeleteEnv ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Deleting…
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4" /> Delete
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default DeployEnvironments;
