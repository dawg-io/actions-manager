/* eslint-disable no-restricted-syntax -- Legacy: TODO migrate inline styles to Tailwind CSS classes */
import React from "react";

interface ReadOnlyBadgeProps {
  /** Visual size variant */
  size?: "sm" | "md";
  /** Additional inline styles */
  style?: React.CSSProperties;
  /** Additional class names */
  className?: string;
}

// Badge color tokens – red tones to convey restricted access
const READ_ONLY_BADGE = {
  color: "#f87171",              // red-400
  background: "rgba(248,113,113,0.12)",
  border: "rgba(248,113,113,0.35)",
};

/**
 * ReadOnlyBadge – small pill/chip that indicates the user has read-only
 * access to the current project.
 *
 * Follows the same design language as ProjectTypeBadge and PrefixModeBadge.
 */
const ReadOnlyBadge: React.FC<ReadOnlyBadgeProps> = ({
  size = "md",
  style,
  className,
}) => {
  const isSmall = size === "sm";

  const badgeStyle: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: isSmall ? "0.3rem" : "0.375rem",
    padding: isSmall ? "0.15rem 0.5rem" : "0.25rem 0.6rem",
    borderRadius: "999px",
    border: `1px solid ${READ_ONLY_BADGE.border}`,
    backgroundColor: READ_ONLY_BADGE.background,
    color: READ_ONLY_BADGE.color,
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
      title="You have read-only access to this project"
      aria-label="Access level: Read Only"
    >
      🔒 Read Only
    </span>
  );
};

export default ReadOnlyBadge;
