import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  Wrench,
  Plus,
  Search,
  Copy,
  RefreshCw,
  MoreHorizontal,
  Trash2,
  AlertTriangle,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import {
  handleDeleteEnvVars,
  updateEnvVars,
  getEnvVars,
  syncEnvVar,
  getEnvVarsCount,
} from "../api/envVars";
import PrefixedInput from "./PrefixedInput";
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
interface EnvVar {
  env_key: string;
  value?: string;
  repo: string;
}

interface ManualEnvVar {
  key: string;
  value: string;
}

interface EnvVarsProps {
  user?: string;
  projectName?: string;
  selectedRepos?: string[];
  envVars?: EnvVar[];
  setEnvVars?: (envVars: EnvVar[] | ((prev: EnvVar[]) => EnvVar[])) => void;
  manualEnvVars: ManualEnvVar[];
  setManualEnvVars: (
    envVars: ManualEnvVar[] | ((prev: ManualEnvVar[]) => ManualEnvVar[]),
  ) => void;
  accountType?: string;
  installationMode?: string | null;
  onAddEnvVar?: (addFunction: () => void) => void;
  projectCode?: string;
  usePrefix?: boolean;
}

const FREE_PLAN_LIMIT = 2;
const PROFESSIONAL_PLAN_LIMIT = 10;
const SELF_HOSTED_BETA_LIMIT = 6;

const VALID_KEY_REGEX = /^[A-Z0-9_]+$/i;

const EnvVars: React.FC<EnvVarsProps> = ({
  user,
  projectName,
  selectedRepos = [],
  envVars = [],
  setEnvVars,
  manualEnvVars,
  setManualEnvVars,
  accountType,
  installationMode,
  onAddEnvVar,
  projectCode,
  usePrefix = true,
}) => {
  const isSelfHostedBeta = installationMode?.toLowerCase() === "self-hosted";
  const [envRepoTracker, setEnvRepoTracker] = useState<
    Map<string, Map<string, string>>
  >(new Map());
  const [envVarsCount, setEnvVarsCount] = useState<number>(0);
  const [isCountLoading, setIsCountLoading] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);
  const [confirmDeleteKey, setConfirmDeleteKey] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState<string>("");

  const getEnvVarsLimit = (): number => {
    if (isSelfHostedBeta) return SELF_HOSTED_BETA_LIMIT;
    if (accountType === "free") return FREE_PLAN_LIMIT;
    if (accountType === "professional") return PROFESSIONAL_PLAN_LIMIT;
    return Infinity;
  };

  const envVarsLimit = getEnvVarsLimit();
  const isLimitedTier = isSelfHostedBeta || accountType === "free" || accountType === "professional";

  // Use only the first manual entry as the "draft" for the inline form. The
  // manualEnvVars array is preserved for backward compatibility with the
  // parent state shape; auto-add of empty rows is no longer used.
  const draft: ManualEnvVar = manualEnvVars?.[0] ?? { key: "", value: "" };

  const updateDraft = (next: Partial<ManualEnvVar>): void => {
    setManualEnvVars((prev) => {
      const list = prev && prev.length > 0 ? [...prev] : [{ key: "", value: "" }];
      list[0] = { ...list[0], ...next };
      return list;
    });
  };

  const clearDraft = (): void => {
    setManualEnvVars([{ key: "", value: "" }]);
    setErrorMessage(null);
  };

  // Helper function to merge environment variables avoiding duplicates
  const mergeEnvVars = (prevEnvVars: EnvVar[], newEnvVars: EnvVar[]): EnvVar[] => {
    const mergedEnvVars = [...prevEnvVars];
    for (const newEnvVar of newEnvVars) {
      const existingIndex = mergedEnvVars.findIndex(
        (envVar) =>
          envVar.env_key === newEnvVar.env_key && envVar.repo === newEnvVar.repo,
      );
      if (existingIndex >= 0) {
        mergedEnvVars[existingIndex] = newEnvVar;
      } else {
        mergedEnvVars.push(newEnvVar);
      }
    }
    return mergedEnvVars;
  };

  // Helper function to fetch environment variables for selected repos
  const fetchEnvVarsForRepos = async (): Promise<EnvVar[]> => {
    if (!user || !projectName) return [];
    const envVarsPerRepo = await Promise.all(
      selectedRepos.map(async (repo) => {
        return await getEnvVars(user, repo, projectName);
      }),
    );
    return envVarsPerRepo.flat().map((envVar) => ({
      ...envVar,
      repo: Array.isArray(envVar.repo) ? envVar.repo[0] : envVar.repo,
    }));
  };

  const updateEnvVarsState = (allEnvVars: EnvVar[]): void => {
    if (Array.isArray(allEnvVars) && setEnvVars) {
      setEnvVars((prevEnvVars) => mergeEnvVars(prevEnvVars, allEnvVars));
    }
  };

  const fetchEnvVarsCount = useCallback(async (): Promise<void> => {
    if (
      (!isSelfHostedBeta && accountType !== "free" && accountType !== "professional") ||
      !user ||
      !projectName ||
      selectedRepos.length === 0
    ) {
      return;
    }
    setIsCountLoading(true);
    try {
      const count = await getEnvVarsCount(user, projectName, selectedRepos);
      setEnvVarsCount(count);
    } catch (error) {
      // Surface fetch errors but do not block the UI.
      setErrorMessage("Failed to load environment variable usage count.");
    } finally {
      setIsCountLoading(false);
    }
  }, [isSelfHostedBeta, accountType, user, projectName, selectedRepos]);

  const removeDeletedEnvVar = (envKey: string): void => {
    if (!setEnvVars) return;
    setEnvVars((prevEnvVars) =>
      prevEnvVars.filter(
        (envVar) =>
          !(envVar.env_key === envKey && selectedRepos.includes(envVar.repo)),
      ),
    );
  };

  // Ensure parent state always has at least one empty draft entry.
  useEffect(() => {
    if (!manualEnvVars || manualEnvVars.length === 0) {
      setManualEnvVars([{ key: "", value: "" }]);
    }
  }, [manualEnvVars, setManualEnvVars]);

  // Validation for the Add Variable form
  const trimmedKey = (draft.key || "").trim();
  const trimmedValue = (draft.value || "").trim();
  const isKeyValid = trimmedKey.length > 0 && VALID_KEY_REGEX.test(trimmedKey);
  const isFormValid = isKeyValid && trimmedValue.length > 0;
  const atLimit = isLimitedTier && envVarsCount >= envVarsLimit;
  const canAdd = isFormValid && !isSaving && !atLimit;

  const handleCreateEnvVar = useCallback(async (): Promise<void> => {
    if (!user || !projectName || !isFormValid || isSaving) return;
    if (atLimit) {
      setErrorMessage(
        isSelfHostedBeta
          ? `Self-Hosted Beta: You can create up to ${envVarsLimit} environment variables per project. You have reached the limit.`
          : `You have reached the limit of ${envVarsLimit} environment variables for ${accountType} accounts.`,
      );
      return;
    }
    setIsSaving(true);
    setErrorMessage(null);
    try {
      const response = await updateEnvVars(
        user,
        selectedRepos,
        [{ key: trimmedKey, value: draft.value }],
        projectName,
      );
      // Check if backend returned an error response
      if (response?.error) {
        setErrorMessage(
          typeof response.error === "string"
            ? response.error
            : "Failed to save environment variable.",
        );
        return;
      }
      // Clear the draft on success
      setManualEnvVars([{ key: "", value: "" }]);
      const allEnvVars = await fetchEnvVarsForRepos();
      updateEnvVarsState(allEnvVars);
      if (isLimitedTier) {
        await fetchEnvVarsCount();
      }
      setSuccessMessage(`Saved ${trimmedKey} to GitHub.`);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? `Failed to save environment variable: ${error.message}`
          : "Failed to save environment variable.",
      );
    } finally {
      setIsSaving(false);
    }
    // The omitted dependencies are stable: `setManualEnvVars` / `setEnvVars`
    // are React state setters and the helper closures only read state through
    // the explicitly-listed values. Adding them would not change behaviour but
    // would re-create the callback on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    user,
    projectName,
    selectedRepos,
    trimmedKey,
    draft.value,
    isFormValid,
    isSaving,
    atLimit,
    envVarsLimit,
    accountType,
    isLimitedTier,
  ]);

  // Build the per-key tracker for existing variables.
  useEffect(() => {
    const tracker = new Map<string, Map<string, string>>();
    for (const env of envVars) {
      if (!tracker.has(env.env_key)) {
        tracker.set(env.env_key, new Map());
      }
      tracker.get(env.env_key)!.set(env.repo, env.value || "N/A");
    }
    setEnvRepoTracker(tracker);
    if (isLimitedTier) {
      fetchEnvVarsCount();
    }
  }, [envVars, isLimitedTier, fetchEnvVarsCount]);

  // Expose add function to the parent so the global "Add" button can focus
  // / scroll to the form. The function focuses the first input.
  const focusAddForm = useCallback((): void => {
    if (atLimit) {
      if (isSelfHostedBeta) {
        setErrorMessage(
          `Self-Hosted Beta: You can create up to ${envVarsLimit} environment variables per project. You have reached the limit.`,
        );
      } else {
        const tierName = accountType === "free" ? "Free" : "Professional";
        const upgradeMsg =
          accountType === "free"
            ? " Upgrade to Professional for up to 10 environment variables per project."
            : " Upgrade to Enterprise for unlimited environment variables.";
        setErrorMessage(
          `${tierName} plan users can create up to ${envVarsLimit} environment variables per project. You have reached the limit.${upgradeMsg}`,
        );
      }
      return;
    }
    const el = document.getElementById("envvars-add-key");
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.focus();
    }
  }, [atLimit, accountType, envVarsLimit]);

  useEffect(() => {
    if (onAddEnvVar) {
      onAddEnvVar(focusAddForm);
    }
  }, [onAddEnvVar, focusAddForm]);

  useEffect(() => {
    if (isLimitedTier && user && projectName && selectedRepos.length > 0) {
      fetchEnvVarsCount();
    }
  }, [isLimitedTier, user, projectName, selectedRepos, fetchEnvVarsCount]);

  // Auto-clear success messages after a short delay
  useEffect(() => {
    if (!successMessage) return;
    const t = setTimeout(() => setSuccessMessage(null), 3500);
    return () => clearTimeout(t);
  }, [successMessage]);

  const performDelete = async (envKey: string): Promise<void> => {
    if (!user || !projectName) return;
    setDeletingKey(envKey);
    setErrorMessage(null);
    try {
      await handleDeleteEnvVars(user, projectName, selectedRepos, [
        { env_key: envKey },
      ]);
      removeDeletedEnvVar(envKey);
      if (isLimitedTier) {
        await fetchEnvVarsCount();
      }
      setSuccessMessage(`Deleted ${envKey}.`);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? `Failed to delete ${envKey}: ${error.message}`
          : `Failed to delete ${envKey}.`,
      );
    } finally {
      setDeletingKey(null);
      setConfirmDeleteKey(null);
    }
  };

  const handleSyncEnvVar = async (envKey: string): Promise<void> => {
    if (!user || !projectName) return;
    setErrorMessage(null);
    try {
      await syncEnvVar(user, projectName, selectedRepos, envKey);
      const allEnvVars = await fetchEnvVarsForRepos();
      updateEnvVarsState(allEnvVars);
      setSuccessMessage(`Synced ${envKey} to GitHub.`);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? `Failed to sync ${envKey}: ${error.message}`
          : `Failed to sync ${envKey}.`,
      );
    }
  };

  const allKeys = useMemo(
    () => Array.from(envRepoTracker.keys()),
    [envRepoTracker],
  );

  const filteredKeys = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return allKeys;
    return allKeys.filter((k) => k.toLowerCase().includes(term));
  }, [allKeys, searchTerm]);

  const totalCount = allKeys.length;
  const syncedCount = useMemo(
    () =>
      allKeys.filter((key) => {
        const repos = envRepoTracker.get(key);
        if (!repos) return false;
        return selectedRepos.every((r) => repos.has(r.trim()));
      }).length,
    [allKeys, envRepoTracker, selectedRepos],
  );

  const renderResourceCard = (envKey: string) => {
    const envRepos = envRepoTracker.get(envKey) || new Map<string, string>();
    const missingRepos = selectedRepos.filter((repo) => !envRepos.has(repo.trim()));
    const isSynced = missingRepos.length === 0;
    const value = Array.from(envRepos.values())[0] || "N/A";
    const isDeleting = deletingKey === envKey;

    return (
      <div
        key={envKey}
        data-testid={`envvar-card-${envKey}`}
        className="group relative flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 transition-colors hover:border-blue-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900/40 dark:hover:border-blue-500/50 dark:hover:bg-slate-900/60"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                className="truncate font-mono text-sm font-semibold text-slate-900 dark:text-slate-100"
                title={envKey}
              >
                {envKey}
              </span>
              <CopyButton textToCopy={envKey} title={`Copy key: ${envKey}`} />
            </div>
            <div
              className="mt-1 truncate font-mono text-xs text-slate-600 dark:text-slate-300"
              title={value}
            >
              {value}
            </div>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0 text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
                aria-label={`Actions for ${envKey}`}
                disabled={isDeleting}
              >
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              {!isSynced && (
                <DropdownMenuItem
                  onSelect={() => {
                    handleSyncEnvVar(envKey);
                  }}
                >
                  <RefreshCw className="mr-2 h-4 w-4" /> Sync
                </DropdownMenuItem>
              )}
              <DropdownMenuItem
                onSelect={() => {
                  copyToClipboard(envKey);
                }}
              >
                <Copy className="mr-2 h-4 w-4" /> Copy Key
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => {
                  copyToClipboard(value);
                }}
              >
                <Copy className="mr-2 h-4 w-4" /> Copy Value
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => {
                  setConfirmDeleteKey(envKey);
                }}
                className="text-red-600 focus:text-red-700 dark:text-red-400 dark:focus:text-red-300"
              >
                <Trash2 className="mr-2 h-4 w-4" /> Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <ConfigBadge variant="variable">Variable</ConfigBadge>
          {isSynced ? (
            <ConfigBadge
              variant="synced"
              icon={<CheckCircle2 className="h-3 w-3" />}
            >
              Synced
            </ConfigBadge>
          ) : (
            <ConfigBadge
              variant="warning"
              icon={<AlertTriangle className="h-3 w-3" />}
            >
              Not synced ({missingRepos.length} repo{missingRepos.length === 1 ? "" : "s"})
            </ConfigBadge>
          )}
          {isDeleting && (
            <ConfigBadge
              variant="saving"
              icon={<Loader2 className="h-3 w-3 animate-spin" />}
            >
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
              <Wrench className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                Environment Variables
              </h3>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                Manage non-sensitive configuration values for workflows and environments.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <ConfigBadge variant="info">Total: {totalCount}</ConfigBadge>
            <ConfigBadge variant="synced">Synced: {syncedCount}</ConfigBadge>
            <ConfigBadge variant="neutral">
              {usePrefix ? "Prefix Mode" : "No Prefix Mode"}
            </ConfigBadge>
            <ConfigBadge variant="info">GitHub Synced</ConfigBadge>
            {isLimitedTier && (
              <ConfigBadge variant="limited">
                {isCountLoading
                  ? "Loading…"
                  : `${envVarsCount}/${envVarsLimit} used`}
              </ConfigBadge>
            )}
          </div>
        </div>
        {isLimitedTier && (
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            {isSelfHostedBeta
              ? <><strong>Self-Hosted Beta:</strong> You can create up to {envVarsLimit} environment variables per project.</>
              : <><strong>{accountType === "free" ? "Free" : "Professional"} Plan:</strong>{" "}You can create up to {envVarsLimit} environment variables per project.</>
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

      {/* Add Variable form card */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/40">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Add Variable
          </h4>
          {atLimit && <ConfigBadge variant="limited">Limited</ConfigBadge>}
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="flex flex-col gap-1">
            <label
              htmlFor="envvars-add-key"
              className="text-xs font-medium text-slate-700 dark:text-slate-300"
            >
              Variable Key
            </label>
            <PrefixedInput
              prefix={`AM_${(projectCode || "").toUpperCase()}_`}
              value={draft.key || ""}
              onChange={(value: string) =>
                updateDraft({ key: value.toUpperCase() })
              }
              placeholder="e.g. API_URL"
              className="input"
              showPrefix={usePrefix}
              id="envvars-add-key"
              data-testid="envvars-add-key"
              disabled={isSaving || atLimit}
            />
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Use letters, numbers, and underscores only.
            </span>
          </div>
          <div className="flex flex-col gap-1">
            <label
              htmlFor="envvars-add-value"
              className="text-xs font-medium text-slate-700 dark:text-slate-300"
            >
              Value
            </label>
            <Input
              id="envvars-add-value"
              data-testid="envvars-add-value"
              type="text"
              placeholder="e.g. https://api.internal"
              value={draft.value || ""}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                updateDraft({ value: e.target.value })
              }
              disabled={isSaving || atLimit}
            />
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Saved directly to GitHub for the selected repositories.
            </span>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
          {isSaving && (
            <ConfigBadge
              variant="saving"
              icon={<Loader2 className="h-3 w-3 animate-spin" />}
            >
              Saving…
            </ConfigBadge>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={clearDraft}
            disabled={isSaving || (!draft.key && !draft.value)}
          >
            Clear
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={handleCreateEnvVar}
            disabled={!canAdd}
            data-testid="envvars-add-submit"
          >
            <Plus className="h-4 w-4" />
            Add Variable
          </Button>
        </div>
      </div>

      {/* Existing variables section */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/40">
        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Existing Variables
            </h4>
            <ConfigBadge variant="neutral">{totalCount}</ConfigBadge>
          </div>
          {totalCount > 0 && (
            <div className="relative w-full sm:w-64">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                type="search"
                placeholder="Search variables…"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-8"
                aria-label="Search environment variables"
              />
            </div>
          )}
        </div>
        {totalCount === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-slate-300 px-4 py-8 text-center dark:border-slate-700">
            <Wrench className="h-6 w-6 text-slate-400" />
            <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
              No variables yet
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Add your first environment variable for this project.
            </p>
          </div>
        ) : filteredKeys.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-300 px-4 py-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
            No variables match &ldquo;{searchTerm}&rdquo;.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {filteredKeys.map(renderResourceCard)}
          </div>
        )}
      </div>

      {/* Delete confirmation dialog */}
      <Dialog
        open={confirmDeleteKey !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmDeleteKey(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete environment variable?</DialogTitle>
            <DialogDescription>
              This will permanently remove{" "}
              <span className="font-mono font-semibold">{confirmDeleteKey}</span>{" "}
              from the selected repositories on GitHub. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfirmDeleteKey(null)}
              disabled={deletingKey === confirmDeleteKey}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => confirmDeleteKey && performDelete(confirmDeleteKey)}
              disabled={deletingKey === confirmDeleteKey}
              data-testid="envvars-confirm-delete"
            >
              {deletingKey === confirmDeleteKey ? (
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

export default EnvVars;
