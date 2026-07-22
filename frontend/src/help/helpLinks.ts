/**
 * Centralised docs/help map for the frontend.
 *
 * All in-app documentation links must reference a named topic from
 * HELP_TOPICS instead of embedding raw URLs.  To build a full URL call
 * getDocsUrl(topic).  Changing DOCS_BASE_URL here updates every link
 * across the application automatically.
 *
 * Topic paths follow the live actionsmanager.io documentation structure.
 */

export const DOCS_BASE_URL = "https://actionsmanager.io";

export const HELP_TOPICS = {
  // Getting started
  home: "/",
  quickStart: "/getting-started/quick-start.html",
  installation: "/getting-started/installation.html",
  patSetup: "/getting-started/github-pat-setup.html",
  oauthSetup: "/getting-started/github-oauth-setup.html",

  // Features
  projects: "/features/projects.html",
  workflows: "/features/workflows.html",
  prCampaigns: "/features/pr-campaigns.html",
  driftDetection: "/features/drift-detection.html",
  reusableWorkflows: "/features/reusable-workflows.html",
  reusableWorkflowSetup: "/features/reusable-workflow-repository-setup.html",

  // Security
  securityPolicy: "/security/security.html",
  privacy: "/security/privacy.html",
  tokenHandling: "/security/token-handling.html",

  // Troubleshooting
  commonErrors: "/troubleshooting/common-errors.html",
  githubPermissions: "/troubleshooting/github-permissions.html",
  containerStartup: "/troubleshooting/container-startup.html",

  // Beta
  betaNotes: "/beta/beta-notes.html",
} as const;

export type HelpTopic = keyof typeof HELP_TOPICS;

/**
 * Returns the full documentation URL for the given named topic.
 *
 * @example
 *   getDocsUrl("patSetup")
 *   // => "https://actionsmanager.io/getting-started/github-pat-setup.html"
 */
export function getDocsUrl(topic: HelpTopic): string {
  return `${DOCS_BASE_URL}${HELP_TOPICS[topic]}`;
}
