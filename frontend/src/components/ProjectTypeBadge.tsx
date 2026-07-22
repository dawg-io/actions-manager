/* eslint-disable no-restricted-syntax -- Legacy: TODO migrate inline styles to Tailwind CSS classes */
import React from "react";
import { getProjectTypeConfig, ProjectType } from "../utils/projectTypeConfig";

interface ProjectTypeBadgeProps {
  /** The project type value from the data model */
  projectType?: ProjectType | string | null;
  /** Visual size variant */
  size?: "sm" | "md";
  /** Additional inline styles */
  style?: React.CSSProperties;
  /** Additional class names */
  className?: string;
}

/**
 * ProjectTypeBadge – small pill/chip that identifies a project as
 * "Caller Workflow Project" (blue) or "Reusable Workflow Project" (purple).
 *
 * Designed for dark themes; respects the existing design language.
 */
const ProjectTypeBadge: React.FC<ProjectTypeBadgeProps> = ({
  projectType,
  size = "md",
  style,
  className,
}) => {
  const config = getProjectTypeConfig(projectType);
  const { badge, label, icon: Icon } = config;

  const isSmall = size === "sm";

  const badgeStyle: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    minWidth: 0,
    maxWidth: "100%",
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
      aria-label={`Project type: ${label}`}
    >
      {/* Render icon at correct size */}
      <span style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
        <Icon size={isSmall ? 11 : 12} />
      </span>
      <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>{label}</span>
    </span>
  );
};

export default ProjectTypeBadge;
