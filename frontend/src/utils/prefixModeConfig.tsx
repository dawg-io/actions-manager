import React from "react";

/**
 * Shared configuration for the Resource Naming Mode feature.
 *
 * The `usePrefix` boolean stored in the backend maps to:
 *   true  → Prefix Mode
 *   false → No Prefix Mode
 */

export const PREFIX_MODE_CONFIG = {
  label: "Prefix Mode",
  shortLabel: "Prefix",
  bullets: [
    <>Resources use the <code>AM_PROJECT_CODE_</code> prefix</>,
    "Prevents naming conflicts across projects",
    "Resources are clearly identifiable as Actions Manager resources",
    "No local storage of secret or environment variable names",
  ] as Array<React.ReactNode>,
  summary:
    "Resources use the project code prefix to reduce naming conflicts and keep resources clearly scoped to this project.",
};

export const NO_PREFIX_MODE_CONFIG = {
  label: "No Prefix Mode",
  shortLabel: "No Prefix",
  bullets: [
    <>Resources are created without the <code>AM_PROJECT_CODE_</code> prefix</>,
    "Resource names must be unique to avoid conflicts",
    "Resources are not clearly identifiable as Actions Manager resources",
    "Secret and environment variable names are stored locally for tracking (values remain in GitHub)",
  ] as Array<React.ReactNode>,
  summary:
    "Resources are created without the project code prefix. Names must remain unique and secret/env variable names are tracked locally while values remain in GitHub.",
};

/**
 * Returns the mode config for a given `usePrefix` boolean.
 */
export function getPrefixModeConfig(usePrefix: boolean) {
  return usePrefix ? PREFIX_MODE_CONFIG : NO_PREFIX_MODE_CONFIG;
}
