/* eslint-disable no-restricted-syntax -- Need inline style to set progress bar width from runtime usage percent */
import React, { useMemo } from "react";
import { Crown } from "lucide-react";
import { PROJECT_TIER_CONFIG, getEffectiveTierKey } from "../utils/accountTier";

// Self-hosted beta project limits (must match backend SELF_HOSTED_BETA_LIMITS)
const BETA_STANDARD_LIMIT = 4;
const BETA_RWX_LIMIT = 2;

const formatProjectCount = (count: number): string => (
  `${count} project${count === 1 ? "" : "s"}`
);

export interface PlanUsagePillProps {
  accountType?: string | null;
  projectsUsed: number;
  installationMode?: string | null;
  /** Number of standard (Caller Workflow) projects used — required for self-hosted beta display. */
  callerProjectsUsed?: number;
  /** Number of rwx (Reusable Workflow) projects used — required for self-hosted beta display. */
  rwxProjectsUsed?: number;
  className?: string;
}

const PlanUsagePill: React.FC<PlanUsagePillProps> = ({
  accountType,
  projectsUsed,
  installationMode,
  callerProjectsUsed,
  rwxProjectsUsed,
  className,
}) => {
  const tierKey = useMemo(
    () => getEffectiveTierKey(accountType, installationMode),
    [accountType, installationMode],
  );
  const tier = tierKey ? PROJECT_TIER_CONFIG[tierKey] : null;
  const isBeta = tierKey === "self-hosted-beta";

  const usage = useMemo(() => {
    if (!tier) return null;

    // Self-hosted beta: show per-type usage
    if (isBeta) {
      const caller = Number.isFinite(callerProjectsUsed) ? Math.max(0, callerProjectsUsed!) : 0;
      const rwx = Number.isFinite(rwxProjectsUsed) ? Math.max(0, rwxProjectsUsed!) : 0;
      const callerPct = Math.min((caller / BETA_STANDARD_LIMIT) * 100, 100);
      const rwxPct = Math.min((rwx / BETA_RWX_LIMIT) * 100, 100);
      // Use the higher utilisation for the progress bar
      const progressPercent = Math.max(callerPct, rwxPct);
      return {
        label: `Caller: ${caller}/${BETA_STANDARD_LIMIT} · Reusable: ${rwx}/${BETA_RWX_LIMIT}`,
        progressPercent,
        aria: {
          min: 0,
          max: 100,
          now: Math.round(progressPercent),
          label: "Self-Hosted Beta project usage",
        },
      };
    }

    const limit = tier.limit;
    const used = Number.isFinite(projectsUsed) ? Math.max(0, projectsUsed) : 0;

    if (!limit) {
      return {
        label: `${formatProjectCount(used)} · Unlimited`,
        progressPercent: 100,
        aria: {
          min: 0,
          max: 100,
          now: 100,
          label: `${tier.label} project usage (unlimited)`,
        },
      };
    }

    const progressPercent = Math.min((used / limit) * 100, 100);
    return {
      label: `${used} / ${limit} projects`,
      progressPercent,
      aria: {
        min: 0,
        max: limit,
        now: Math.min(used, limit),
        label: `${tier.label} project usage`,
      },
    };
  }, [tier, isBeta, projectsUsed, callerProjectsUsed, rwxProjectsUsed]);

  if (!tier || !usage) return null;

  // Hide upgrade button in self-hosted beta (paid plans not available)
  const showUpgrade = !isBeta && Boolean(tier.upgradeActionLabel && tierKey !== "enterprise");
  const showCrown = tierKey !== "free" && tierKey !== "self-hosted-beta";
  const barClassName = (tierKey === "free" || isBeta)
    ? "bg-slate-500/70 dark:bg-slate-300/70"
    : "bg-amber-400 dark:bg-amber-300";

  return (
    <div
      className={[
        "flex h-14 items-center gap-3 rounded-md border border-border bg-hover-bg px-3 py-2 text-left shadow-sm dark:border-border-dark dark:bg-hover-dark-bg",
        "w-[168px] sm:w-[260px] md:w-[320px] lg:w-[400px] max-w-[420px] min-w-0",
        className ?? "",
      ].join(" ").trim()}
      aria-label="Plan usage"
      data-testid="plan-usage-pill"
    >
      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800/60">
        {showCrown ? (
          <Crown className={`h-4 w-4 ${tier.accentClassName}`} aria-hidden="true" />
        ) : (
          <span className="text-xs font-semibold text-slate-500 dark:text-slate-300" aria-hidden="true">P</span>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center justify-between gap-2">
          <div className="min-w-0">
            <div
              className="truncate text-sm font-semibold text-text-primary dark:text-text-primary-dark"
              title={tier.label}
            >
              <span className="hidden md:inline">{tier.label}</span>
              <span className="md:hidden">{tier.label.replace(" Plan", "").replace(" Beta", " β")}</span>
            </div>
            <div
              className="truncate text-xs text-text-secondary dark:text-text-secondary-dark"
              title={usage.label}
            >
              {usage.label}
            </div>
          </div>

          {showUpgrade && (
            <a
              href="https://github.com/marketplace"
              target="_blank"
              rel="noreferrer"
              className="hidden sm:inline-flex shrink-0 items-center rounded-md border border-slate-300 bg-white/70 px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-white dark:border-slate-600 dark:bg-slate-950/30 dark:text-slate-200 dark:hover:bg-slate-950/50"
              aria-label="Upgrade plan"
              title={tier.upgradeMessage}
            >
              {tier.upgradeActionLabel}
            </a>
          )}
        </div>

        <div
          className="mt-2 h-1 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
          role="progressbar"
          aria-label={usage.aria.label}
          aria-valuemin={usage.aria.min}
          aria-valuemax={usage.aria.max}
          aria-valuenow={usage.aria.now}
        >
          <div
            className={`h-full rounded-full transition-all ${barClassName}`}
            style={{ width: `${usage.progressPercent}%` }}
          />
        </div>
      </div>
    </div>
  );
};

export default PlanUsagePill;
