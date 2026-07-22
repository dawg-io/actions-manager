/* eslint-disable no-restricted-syntax -- Legacy: TODO migrate inline styles to Tailwind CSS classes */
import React from "react";

export type RepositoryVisibilityScope = "public" | "private";

interface RepositoryVisibilityBadgeProps {
  /** Repository visibility scope from the project model (backend field). */
  visibilityScope?: RepositoryVisibilityScope | string | null;
  /** Visual size variant */
  size?: "sm" | "md";
  /** Additional inline styles */
  style?: React.CSSProperties;
  /** Additional class names */
  className?: string;
  /** Test identifier forwarded to the root span. */
  "data-testid"?: string;
}

/** Globe icon — public repositories. */
const PublicIcon: React.FC<{ size?: number }> = ({ size = 16 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="10" />
    <line x1="2" y1="12" x2="22" y2="12" />
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
  </svg>
);

/** Lock icon — private repositories. */
const PrivateIcon: React.FC<{ size?: number }> = ({ size = 16 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </svg>
);

// Color tokens chosen to mirror the Tailwind utilities suggested in the issue
// review comment:
//   Public:  border-emerald-500/40  bg-emerald-500/10  text-emerald-300
//   Private: border-slate-400/40    bg-slate-400/10    text-slate-300
// Translated to RGBA so they match the inline-style pattern used by sibling
// badges (ProjectTypeBadge / PrefixModeBadge).
const PUBLIC_BADGE = {
  color: "#6ee7b7",                       // emerald-300
  background: "rgba(16,185,129,0.10)",    // emerald-500/10
  border: "rgba(16,185,129,0.40)",        // emerald-500/40
};

const PRIVATE_BADGE = {
  color: "#cbd5e1",                       // slate-300
  background: "rgba(148,163,184,0.10)",   // slate-400/10
  border: "rgba(148,163,184,0.40)",       // slate-400/40
};

/**
 * RepositoryVisibilityBadge – small pill/chip that identifies whether a
 * project is configured for "Public Repos" (emerald) or "Private Repos"
 * (slate).
 *
 * Driven by the saved backend `repository_visibility_scope` field — never
 * inferred from the currently-selected repositories.
 */
const RepositoryVisibilityBadge: React.FC<RepositoryVisibilityBadgeProps> = ({
  visibilityScope,
  size = "md",
  style,
  className,
  "data-testid": dataTestId,
}) => {
  const isPrivate = (visibilityScope || "").toString().toLowerCase() === "private";
  const badge = isPrivate ? PRIVATE_BADGE : PUBLIC_BADGE;
  const Icon = isPrivate ? PrivateIcon : PublicIcon;
  const label = isPrivate ? "Private Repos" : "Public Repos";

  const isSmall = size === "sm";

  const badgeStyle: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: isSmall ? "0.3rem" : "0.375rem",
    padding: isSmall ? "0.15rem 0.5rem" : "0.25rem 0.6rem",
    borderRadius: "999px",
    border: `1px solid ${badge.border}`,
    backgroundColor: badge.background,
    color: badge.color,
    fontSize: isSmall ? "0.7rem" : "0.75rem",
    fontWeight: 600,
    letterSpacing: "0.01em",
    whiteSpace: "nowrap",
    lineHeight: 1.4,
    userSelect: "none",
    ...style,
  };

  return (
    <span
      className={className}
      style={badgeStyle}
      title={label}
      aria-label={`Repository visibility: ${label}`}
      data-testid={dataTestId}
    >
      <span style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
        <Icon size={isSmall ? 11 : 12} />
      </span>
      {label}
    </span>
  );
};

export default RepositoryVisibilityBadge;
