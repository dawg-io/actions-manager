import React from "react";

// Canonical project type union – shared across the entire frontend
export type ProjectType = "standard" | "rwx";

export interface ProjectTypeDefinition {
  /** Human-readable label */
  label: string;
  /** Short sentence shown next to the project name (detail page) */
  tagline: string;
  /** Longer sentence used in the create-project flow */
  description: string;
  /** Icon component – accepts an optional `size` prop (pixels) */
  icon: React.FC<{ size?: number }>;
  /** Badge colours (CSS variables-friendly, dark-theme safe) */
  badge: {
    color: string;
    background: string;
    border: string;
  };
}

// ── Icons ──────────────────────────────────────────────────────────────────

/** Folder / package icon – Caller Workflow Project */
const StandardIcon: React.FC<{ size?: number }> = ({ size = 16 }) => (
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
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
  </svg>
);

/** Repeat / reuse icon – Reusable Workflow Project */
const ReusableIcon: React.FC<{ size?: number }> = ({ size = 16 }) => (
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
    <polyline points="17 1 21 5 17 9" />
    <path d="M3 11V9a4 4 0 0 1 4-4h14" />
    <polyline points="7 23 3 19 7 15" />
    <path d="M21 13v2a4 4 0 0 1-4 4H3" />
  </svg>
);

// ── Config map ─────────────────────────────────────────────────────────────

export const PROJECT_TYPE_CONFIG: Record<ProjectType, ProjectTypeDefinition> = {
  standard: {
    label: "Caller Workflow Project",
    tagline: "Manages workflows that call reusable workflows.",
    description: "Manage repositories that consume reusable workflows.",
    icon: StandardIcon,
    badge: {
      color: "#60a5fa",       // blue-400
      background: "rgba(59,130,246,0.12)",
      border: "rgba(59,130,246,0.35)",
    },
  },
  rwx: {
    label: "Reusable Workflow Project",
    tagline: "Authors reusable workflows for caller workflow projects.",
    description: "Author and manage reusable workflows used by caller workflow projects.",
    icon: ReusableIcon,
    badge: {
      color: "#c084fc",       // purple-400
      background: "rgba(168,85,247,0.12)",
      border: "rgba(168,85,247,0.35)",
    },
  },
};

/**
 * Returns the config for a given project type, falling back to "standard"
 * when the value is undefined or unrecognised.
 */
export function getProjectTypeConfig(type?: string | null): ProjectTypeDefinition {
  if (type === "rwx") return PROJECT_TYPE_CONFIG.rwx;
  return PROJECT_TYPE_CONFIG.standard;
}
