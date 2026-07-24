import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  Lock,
  Plus,
  Search,
  Copy,
  RefreshCw,
  MoreHorizontal,
  Trash2,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Eye,
  EyeOff,
} from "lucide-react";
import { deleteSecrets, createSecrets, getSecretsCount } from "../api/secrets";
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

// Visual placeholder for stored secret values. Stored secret values are never
// retrieved from the backend; this is a fixed mask rendered client-side only.
// The length is deliberately fixed (and unrelated to the real secret length)
// so the UI does not leak any information about the underlying value.
const SECRET_MASK = "••••••••••";

// TypeScript interfaces
interface Secret {
  secret_key: string;
  secret_value?: string;
  repo: string;
}

interface ManualSecret {
  secret_key: string;
  secret_value: string;
}

interface SecretsProps {
  user?: string;
  projectName?: string;
  secrets?: Secret[];
  manualSecrets: ManualSecret[];
  setManualSecrets: (
    secrets: ManualSecret[] | ((prev: ManualSecret[]) => ManualSecret[]),
  ) => void;
  selectedRepos?: string[];
  setSecrets?: (secrets: Secret[] | ((prev: Secret[]) => Secret[])) => void;
  accountType?: string;
  installationMode?: string | null;
  onAddSecret?: (addFunction: () => void) => void;
  projectCode?: string;
  usePrefix?: boolean;
}

const FREE_PLAN_LIMIT = 2;
const PROFESSIONAL_PLAN_LIMIT = 10;
const SELF_HOSTED_BETA_LIMIT = 6;
const VALID_KEY_REGEX = /^[A-Z0-9_]+$/i;

const Secrets: React.FC<SecretsProps> = ({
  user,
  projectName,
  secrets = [],
  manualSecrets,
  setManualSecrets,
  selectedRepos = [],
  setSecrets,
  accountType,
  installationMode,
  onAddSecret,
  projectCode,
  usePrefix = true,
}) => {
  const isSelfHostedBeta = installationMode?.toLowerCase() === "self-hosted";
  const [secretRepoTracker, setSecretRepoTracker] = useState<
    Map<string, Set<string>>
  >(new Map());
  const [secretsCount, setSecretsCount] = useState<number>(0);
  const [isCountLoading, setIsCountLoading] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);
  const [confirmDeleteKey, setConfirmDeleteKey] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [revealValue, setRevealValue] = useState<boolean>(false);

  const getSecretsLimit = (): number => {
    if (isSelfHostedBeta) return SELF_HOSTED_BETA_LIMIT;
    if (accountType === "free") return FREE_PLAN_LIMIT;
    if (accountType === "professional") return PROFESSIONAL_PLAN_LIMIT;
    return Infinity;
  };

  const secretsLimit = getSecretsLimit();
  const isLimitedTier = isSelfHostedBeta || accountType === "free" || accountType === "professional";

  // Use first manualSecrets entry as the working draft for the inline form.
  const draft: ManualSecret =
    manualSecrets?.[0] ?? { secret_key: "", secret_value: "" };

  const updateDraft = (next: Partial<ManualSecret>): void => {
    setManualSecrets((prev) => {
      const list =
        prev && prev.length > 0 ? [...prev] : [{ secret_key: "", secret_value: "" }];
      list[0] = { ...list[0], ...next };
      return list;
    });
  };

  const clearDraft = (): void => {
    setManualSecrets([{ secret_key: "", secret_value: "" }]);
    setErrorMessage(null);
    setRevealValue(false);
  };

  const fetchSecretsCount = useCallback(async (): Promise<void> => {
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
      const count = await getSecretsCount(user, projectName, selectedRepos);
      setSecretsCount(count);
    } catch (error) {
      console.error('Failed to load secrets usage count:', error);
      setErrorMessage("Failed to load secrets usage count.");
    } finally {
      setIsCountLoading(false);
    }
  }, [isSelfHostedBeta, accountType, user, projectName, selectedRepos]);

  // Ensure parent state always has at least one empty draft entry.
  useEffect(() => {
    if (!manualSecrets || manualSecrets.length === 0) {
      setManualSecrets([{ secret_key: "", secret_value: "" }]);
    }
  }, [manualSecrets, setManualSecrets]);

  const trimmedKey = (draft.secret_key || "").trim();
  const hasValue = (draft.secret_value || "").length > 0;
  const isKeyValid = trimmedKey.length > 0 && VALID_KEY_REGEX.test(trimmedKey);
  const isFormValid = isKeyValid && hasValue;
  const atLimit = isLimitedTier && secretsCount >= secretsLimit;
  const canAdd = isFormValid && !isSaving && !atLimit;

  const handleCreateSecret = useCallback(async (): Promise<void> => {
    if (!isFormValid || isSaving) return;
    if (atLimit) {
      setErrorMessage(
        isSelfHostedBeta
          ? `Self-Hosted Beta: You can create up to ${secretsLimit} secrets per project. You have reached the limit.`
          : `You have reached the limit of ${secretsLimit} secrets for ${accountType} accounts.`,
      );
      return;
    }
    setIsSaving(true);
    setErrorMessage(null);
    try {
      const formattedSecrets = [
        {
          secret_key: trimmedKey.toUpperCase(),
          secret_value: draft.secret_value,
        },
      ];
      await createSecrets(
        user,
        selectedRepos,
        formattedSecrets,
        projectName,
        setSecrets,
      );
      // Always clear the typed secret value after a successful save so it is
      // not retained in component state, parent state, or memory longer than
      // necessary.
      setManualSecrets([{ secret_key: "", secret_value: "" }]);
      setRevealValue(false);
      if (isLimitedTier) {
        await fetchSecretsCount();
      }
      setSuccessMessage(`Saved ${trimmedKey.toUpperCase()} to GitHub.`);
    } catch (error) {
      // Never include the secret value in the error message.
      setErrorMessage(
        error instanceof Error
          ? `Failed to save secret: ${error.message}`
          : "Failed to save secret.",
      );
    } finally {
      setIsSaving(false);
    }
    // The omitted dependencies (`setManualSecrets`) are stable React state
    // setters; including them would re-create this callback on every render
    // without changing behaviour.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    isFormValid,
    isSaving,
    atLimit,
    trimmedKey,
    draft.secret_value,
    user,
    selectedRepos,
    projectName,
    setSecrets,
    isLimitedTier,
    secretsLimit,
    accountType,
  ]);

  // Build per-key tracker for existing secrets.
  useEffect(() => {
    const tracker = new Map<string, Set<string>>();
    secrets.forEach((secret) => {
      const secretKey = secret.secret_key;
      const repoKey =
        typeof secret.repo === "string" ? secret.repo.trim() : String(secret.repo);
      if (!tracker.has(secretKey)) {
        tracker.set(secretKey, new Set());
      }
      tracker.get(secretKey)!.add(repoKey);
    });
    setSecretRepoTracker(tracker);
    if (isLimitedTier) {
      fetchSecretsCount();
    }
  }, [secrets, selectedRepos, isLimitedTier, fetchSecretsCount]);

  const focusAddForm = useCallback((): void => {
    if (atLimit) {
      if (isSelfHostedBeta) {
        setErrorMessage(
          `Self-Hosted Beta: You can create up to ${secretsLimit} secrets per project. You have reached the limit.`,
        );
      } else {
        const tierName = accountType === "free" ? "Free" : "Professional";
        const upgradeMsg =
          accountType === "free"
            ? " Upgrade to Professional for up to 10 secrets per project."
            : " Upgrade to Enterprise for unlimited secrets.";
        setErrorMessage(
          `${tierName} plan users can create up to ${secretsLimit} secrets per project. You have reached the limit.${upgradeMsg}`,
        );
      }
      return;
    }
    const el = document.getElementById("secrets-add-key");
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.focus();
    }
  }, [atLimit, accountType, secretsLimit]);

  useEffect(() => {
    if (onAddSecret) {
      onAddSecret(focusAddForm);
    }
  }, [onAddSecret, focusAddForm]);

  useEffect(() => {
    if (isLimitedTier && user && projectName && selectedRepos.length > 0) {
      fetchSecretsCount();
    }
  }, [isLimitedTier, user, projectName, selectedRepos, fetchSecretsCount]);

  useEffect(() => {
    if (!successMessage) return;
    const t = setTimeout(() => setSuccessMessage(null), 3500);
    return () => clearTimeout(t);
  }, [successMessage]);

  const performDelete = async (secretKey: string): Promise<void> => {
    setDeletingKey(secretKey);
    setErrorMessage(null);
    try {
      await deleteSecrets(user, projectName, selectedRepos, secretKey, setSecrets);
      if (isLimitedTier) {
        await fetchSecretsCount();
      }
      setSuccessMessage(`Deleted ${secretKey}.`);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? `Failed to delete ${secretKey}: ${error.message}`
          : `Failed to delete ${secretKey}.`,
      );
    } finally {
      setDeletingKey(null);
      setConfirmDeleteKey(null);
    }
  };

  const handleRotate = (secretKey: string): void => {
    // GitHub does not return secret values, so "rotate" simply pre-fills the
    // key into the inline form so the user can type a new value and save.
    updateDraft({ secret_key: secretKey, secret_value: "" });
    setRevealValue(false);
    const el = document.getElementById("secrets-add-value");
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.focus();
    }
  };

  const allKeys = useMemo(
    () => Array.from(secretRepoTracker.keys()),
    [secretRepoTracker],
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
        const repos = secretRepoTracker.get(key);
        if (!repos) return false;
        return selectedRepos.every((r) =>
          repos.has(typeof r === "string" ? r.trim() : String(r)),
        );
      }).length,
    [allKeys, secretRepoTracker, selectedRepos],
  );

  const renderSecretCard = (secretKey: string) => {
    const secretRepos = secretRepoTracker.get(secretKey) || new Set<string>();
    const missingRepos = selectedRepos.filter(
      (repo) =>
        !secretRepos.has(typeof repo === "string" ? repo.trim() : String(repo)),
    );
    const isSynced = missingRepos.length === 0;
    const isDeleting = deletingKey === secretKey;

    return (
      <div
        key={secretKey}
        data-testid={`secret-card-${secretKey}`}
        className="group relative flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 transition-colors hover:border-indigo-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900/40 dark:hover:border-indigo-500/50 dark:hover:bg-slate-900/60"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                className="truncate font-mono text-sm font-semibold text-slate-900 dark:text-slate-100"
                title={secretKey}
              >
                {secretKey}
              </span>
              <CopyButton
                textToCopy={secretKey}
                title={`Copy secret key: ${secretKey}`}
              />
            </div>
            <div
              className="mt-1 select-none font-mono text-xs tracking-widest text-slate-500 dark:text-slate-400"
              aria-label="Masked secret value"
            >
              {SECRET_MASK}
            </div>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0 text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
                aria-label={`Actions for ${secretKey}`}
                disabled={isDeleting}
              >
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuItem
                onSelect={() => {
                  copyToClipboard(secretKey);
                }}
              >
                <Copy className="mr-2 h-4 w-4" /> Copy Key
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => {
                  handleRotate(secretKey);
                }}
              >
                <RefreshCw className="mr-2 h-4 w-4" /> Rotate Value
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => {
                  setConfirmDeleteKey(secretKey);
                }}
                className="text-red-600 focus:text-red-700 dark:text-red-400 dark:focus:text-red-300"
              >
                <Trash2 className="mr-2 h-4 w-4" /> Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <ConfigBadge variant="secret">Secret</ConfigBadge>
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
          <ConfigBadge variant="writeOnly">Write-only</ConfigBadge>
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
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-300">
              <Lock className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                Environment Secrets
              </h3>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                Manage encrypted GitHub environment secrets. Values are write-only once saved.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <ConfigBadge variant="info">Total: {totalCount}</ConfigBadge>
            <ConfigBadge variant="synced">Synced: {syncedCount}</ConfigBadge>
            <ConfigBadge variant="writeOnly">Write-only</ConfigBadge>
            <ConfigBadge variant="neutral">
              {usePrefix ? "Prefix Mode" : "No Prefix Mode"}
            </ConfigBadge>
            {isLimitedTier && (
              <ConfigBadge variant="limited">
                {isCountLoading
                  ? "Loading…"
                  : `${secretsCount}/${secretsLimit} used`}
              </ConfigBadge>
            )}
          </div>
        </div>
        {isLimitedTier && (
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            {isSelfHostedBeta
              ? <><strong>Self-Hosted Beta:</strong> You can create up to {secretsLimit} secrets per project.</>
              : <><strong>{accountType === "free" ? "Free" : "Professional"} Plan:</strong>{" "}You can create up to {secretsLimit} secrets per project.</>
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

      {/* Add Secret form card */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/40">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Add Secret
          </h4>
          {atLimit && <ConfigBadge variant="limited">Limited</ConfigBadge>}
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="flex flex-col gap-1">
            <label
              htmlFor="secrets-add-key"
              className="text-xs font-medium text-slate-700 dark:text-slate-300"
            >
              Secret Key
            </label>
            <PrefixedInput
              prefix={`AM_${(projectCode || "").toUpperCase()}_`}
              value={draft.secret_key || ""}
              onChange={(value: string) =>
                updateDraft({ secret_key: value.toUpperCase() })
              }
              placeholder="e.g. DB_PASSWORD"
              className="input"
              showPrefix={usePrefix}
              id="secrets-add-key"
              data-testid="secrets-add-key"
              disabled={isSaving || atLimit}
            />
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Use letters, numbers, and underscores only.
            </span>
          </div>
          <div className="flex flex-col gap-1">
            <label
              htmlFor="secrets-add-value"
              className="text-xs font-medium text-slate-700 dark:text-slate-300"
            >
              Secret Value
            </label>
            <div className="relative">
              <Input
                id="secrets-add-value"
                data-testid="secrets-add-value"
                type={revealValue ? "text" : "password"}
                placeholder="Enter secret value"
                value={draft.secret_value || ""}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  updateDraft({ secret_value: e.target.value })
                }
                disabled={isSaving || atLimit}
                autoComplete="new-password"
                className="pr-10"
              />
              <button
                type="button"
                onClick={() => setRevealValue((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 hover:text-slate-700 focus:outline-none focus-visible:ring-1 focus-visible:ring-ring dark:text-slate-500 dark:hover:text-slate-200 disabled:opacity-50"
                aria-label={revealValue ? "Hide secret value" : "Show secret value"}
                aria-pressed={revealValue}
                title={
                  hasValue
                    ? revealValue
                      ? "Hide secret value"
                      : "Show secret value"
                    : "Enter a value to enable show/hide"
                }
                disabled={isSaving || atLimit || !hasValue}
                data-testid="secrets-toggle-reveal"
              >
                {revealValue ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </button>
            </div>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Secret values are masked and cannot be retrieved after sync.
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
            disabled={isSaving || (!draft.secret_key && !draft.secret_value)}
          >
            Clear
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={handleCreateSecret}
            disabled={!canAdd}
            data-testid="secrets-add-submit"
          >
            <Plus className="h-4 w-4" />
            Add Secret
          </Button>
        </div>
      </div>

      {/* Existing secrets section */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/40">
        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Existing Secrets
            </h4>
            <ConfigBadge variant="neutral">{totalCount}</ConfigBadge>
          </div>
          {totalCount > 0 && (
            <div className="relative w-full sm:w-64">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                type="search"
                placeholder="Search secrets…"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-8"
                aria-label="Search environment secrets"
              />
            </div>
          )}
        </div>
        {totalCount === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-slate-300 px-4 py-8 text-center dark:border-slate-700">
            <Lock className="h-6 w-6 text-slate-400" />
            <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
              No secrets yet
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Add your first GitHub Actions secret for this project.
            </p>
          </div>
        ) : filteredKeys.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-300 px-4 py-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
            No secrets match &ldquo;{searchTerm}&rdquo;.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {filteredKeys.map(renderSecretCard)}
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
            <DialogTitle>Delete environment secret?</DialogTitle>
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
              data-testid="secrets-confirm-delete"
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

export default Secrets;
