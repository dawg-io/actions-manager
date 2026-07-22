export type AccountTierKey = "free" | "professional" | "enterprise" | "self-hosted-beta";

// Self-hosted beta project limits — must match backend/tier_service.py SELF_HOSTED_BETA_LIMITS.
export const SELF_HOSTED_BETA_CALLER_LIMIT = 4;
export const SELF_HOSTED_BETA_RWX_LIMIT = 2;

export const ACCOUNT_TYPE_MAP: Record<string, AccountTierKey> = {
  free: "free",
  pro: "professional",
  professional: "professional",
  enterprise: "enterprise",
};

export const PROJECT_TIER_CONFIG: Record<AccountTierKey, {
  label: string;
  limit: number | null;
  accentClassName: string;
  upgradeActionLabel?: string;
  upgradeMessage: string;
}> = {
  free: {
    label: "Free Plan",
    limit: 3,
    accentClassName: "text-slate-500 dark:text-slate-300",
    upgradeActionLabel: "Upgrade",
    upgradeMessage: "Upgrade to Professional for up to 10 projects and private repository support.",
  },
  professional: {
    label: "Professional Plan",
    limit: 10,
    accentClassName: "text-amber-600 dark:text-amber-300",
    upgradeActionLabel: "Upgrade",
    upgradeMessage: "Upgrade to Enterprise for unlimited projects and expanded team usage.",
  },
  enterprise: {
    label: "Enterprise Plan",
    limit: null,
    accentClassName: "text-amber-600 dark:text-amber-300",
    upgradeMessage: "Unlimited project capacity is included with your enterprise plan.",
  },
  "self-hosted-beta": {
    label: "Self-Hosted Beta",
    // Combined limit displayed separately per type; use null for the combined bar
    limit: null,
    accentClassName: "text-slate-500 dark:text-slate-300",
    // No upgrade action in self-hosted beta — paid plans are not available
    upgradeMessage: "Paid plans are not available during the self-hosted beta.",
  },
};

export const normalizeAccountType = (rawAccountType: string | null | undefined): AccountTierKey | null => {
  if (!rawAccountType) return null;
  const normalized = rawAccountType.trim().toLowerCase();
  return ACCOUNT_TYPE_MAP[normalized] ?? null;
};

/**
 * Returns the effective tier key for display purposes. When the
 * installation mode is "self-hosted", this always returns
 * "self-hosted-beta" so the UI shows the correct beta branding
 * regardless of the stored account_type.
 */
export const getEffectiveTierKey = (
  rawAccountType: string | null | undefined,
  installationMode: string | null | undefined,
): AccountTierKey | null => {
  if (installationMode?.toLowerCase() === "self-hosted") {
    return "self-hosted-beta";
  }
  return normalizeAccountType(rawAccountType);
};
