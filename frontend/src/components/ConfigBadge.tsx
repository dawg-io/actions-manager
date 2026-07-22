import React from "react";
import { cn } from "../lib/utils";

/**
 * Visual variant for status / type badges used on the Environment Variables
 * and Environment Secrets configuration pages. Centralised here so that the
 * two pages stay visually consistent and the colour vocabulary stays small.
 */
export type ConfigBadgeVariant =
  | "variable"
  | "secret"
  | "synced"
  | "saving"
  | "failed"
  | "limited"
  | "writeOnly"
  | "info"
  | "neutral"
  | "warning";

interface ConfigBadgeProps {
  variant?: ConfigBadgeVariant;
  icon?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}

/**
 * Variant → Tailwind class map. A few variants intentionally share the same
 * underlying colour palette (e.g. `warning`/`limited`, `saving`/`writeOnly`)
 * to keep the visual vocabulary small while still letting callers express
 * semantic intent at the call-site. Keep them as separate keys so the
 * meaning of a badge is clear when reading JSX, and so the styling of one
 * can be tightened later without disturbing the other.
 */
const VARIANT_CLASSES: Record<ConfigBadgeVariant, string> = {
  // Blue — non-sensitive variable / type label
  variable:
    "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/30",
  // Indigo — sensitive secret / type label
  secret:
    "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-300 dark:border-indigo-500/30",
  // Green — successfully written to GitHub
  synced:
    "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/30",
  // Slate — transient saving state
  saving:
    "bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-500/10 dark:text-slate-300 dark:border-slate-500/30",
  // Red — last action failed
  failed:
    "bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/30",
  // Amber — tier / capability restriction
  limited:
    "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/30",
  // Slate / muted — write-only helper badge
  writeOnly:
    "bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-500/10 dark:text-slate-300 dark:border-slate-500/30",
  // Generic informational badge
  info:
    "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:border-sky-500/30",
  // Neutral / default
  neutral:
    "bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-500/10 dark:text-slate-300 dark:border-slate-500/30",
  // Amber warning — same palette as `limited` by design (see header comment);
  // kept as a separate variant so the call-site reads as a warning rather
  // than a tier limit.
  warning:
    "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/30",
};

const ConfigBadge: React.FC<ConfigBadgeProps> = ({
  variant = "neutral",
  icon,
  className,
  children,
}) => {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
        VARIANT_CLASSES[variant],
        className,
      )}
    >
      {icon ? <span className="flex h-3 w-3 items-center justify-center">{icon}</span> : null}
      {children}
    </span>
  );
};

export default ConfigBadge;
