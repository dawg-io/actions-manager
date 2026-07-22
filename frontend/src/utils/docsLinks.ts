/**
 * Backward-compatible re-exports from the canonical docs/help map.
 *
 * New code should import directly from "help/helpLinks" and call
 * getDocsUrl(topic) rather than using the DOCS_LINKS constants below.
 */
export { DOCS_BASE_URL, HELP_TOPICS, getDocsUrl } from "../help/helpLinks";
export type { HelpTopic } from "../help/helpLinks";

import { getDocsUrl } from "../help/helpLinks";

/** @deprecated Use getDocsUrl(topic) imported from help/helpLinks instead. */
export const DOCS_LINKS = {
  /** Login, OAuth and Personal Access Token setup */
  PAT_SETUP: getDocsUrl("patSetup"),
  /** Creating and configuring projects */
  PROJECT_CREATION: getDocsUrl("projects"),
  /** Workflow editor (YAML + GUI editor) */
  WORKFLOW_EDITOR: getDocsUrl("workflows"),
  /** PR-based workflow delivery and campaigns */
  PR_CAMPAIGNS: getDocsUrl("prCampaigns"),
  /** Drift detection and resolution */
  DRIFT_DETECTION: getDocsUrl("driftDetection"),
  /** Token handling and authentication settings */
  SETTINGS: getDocsUrl("tokenHandling"),
} as const;
