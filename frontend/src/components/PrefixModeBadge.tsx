/* eslint-disable no-restricted-syntax -- Legacy: TODO migrate inline styles to Tailwind CSS classes */
import React from "react";

interface PrefixModeBadgeProps {
  /** Whether the project uses the AM_PROJECT_CODE_ prefix */
  usePrefix: boolean;
  /** Visual size variant */
  size?: "sm" | "md";
  /** Additional inline styles */
  style?: React.CSSProperties;
  /** Additional class names */
  className?: string;
}

/** Tag icon – used for Prefix Mode */
const PrefixIcon: React.FC<{ size?: number }> = ({ size = 16 }) => (
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
    <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
    <line x1="7" y1="7" x2="7.01" y2="7" />
  </svg>
);

/** Slash / untagged icon – used for No Prefix Mode */
const NoPrefixIcon: React.FC<{ size?: number }> = ({ size = 16 }) => (
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
    <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
  </svg>
);

// Badge color tokens – mirrors the style of ProjectTypeBadge
const PREFIX_MODE_BADGE = {
  color: "#34d399",           // emerald-400
  background: "rgba(16,185,129,0.12)",
  border: "rgba(16,185,129,0.35)",
};

const NO_PREFIX_MODE_BADGE = {
  color: "#fbbf24",           // amber-400
  background: "rgba(245,158,11,0.12)",
  border: "rgba(245,158,11,0.35)",
};

/**
 * PrefixModeBadge – small pill/chip that identifies whether a project uses
 * "Prefix Mode" (emerald) or "No Prefix Mode" (amber).
 *
 * Designed for dark themes; respects the existing design language.
 */
const PrefixModeBadge: React.FC<PrefixModeBadgeProps> = ({
  usePrefix,
  size = "md",
  style,
  className,
}) => {
  const badge = usePrefix ? PREFIX_MODE_BADGE : NO_PREFIX_MODE_BADGE;
  const Icon = usePrefix ? PrefixIcon : NoPrefixIcon;
  const label = usePrefix ? "Prefix Mode" : "No Prefix Mode";

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
      aria-label={`Resource naming mode: ${label}`}
    >
      <span style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
        <Icon size={isSmall ? 11 : 12} />
      </span>
      {label}
    </span>
  );
};

export default PrefixModeBadge;
