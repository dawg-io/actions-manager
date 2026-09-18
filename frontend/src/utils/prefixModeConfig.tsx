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

/**
 * Why the project key does not follow a project rename, phrased for the mode
 * the project is actually in.
 *
 * The key is generated at creation and is immutable afterwards, so a rename
 * leaves the display name and the key looking mismatched. This is the sentence
 * that explains it, shared by the sidebar and the rename confirmation so the
 * two never drift apart.
 *
 * Deliberately does not mention deployment environments: those are never
 * prefixed, in either mode. In No Prefix Mode nothing in GitHub carries the
 * key at all except the pull-request branch name, so the two modes need
 * different sentences to stay accurate.
 */
export function projectKeyFixedNote(usePrefix: boolean, projectCode?: string): string {
  const base = "Renaming the project does not change the project key.";
  if (usePrefix) {
    const prefix = projectCode ? `AM_${projectCode.toUpperCase()}_` : "AM_PROJECT_CODE_";
    return `${base} Existing secrets, variables and delivered workflow files keep their ${prefix} names.`;
  }
  return (
    `${base} This project creates resources without the key prefix; the key is used in ` +
    "ActionsManager pull request branch names."
  );
}
