/**
 * Derived display labels for workflow import/sync status.
 *
 * These are display-only labels derived from existing state values.
 * They do NOT change backend state values or introduce new persisted enums.
 *
 * Rules:
 * - "Local Draft" - project.pr_state=draft, workflow new/committed_locally, no real hash, no open PR
 * - "Imported Locally" - import metadata exists, no real hash, no open PR
 * - "Pending Sync" - local workflow not synced, no real GitHub baseline
 * - "Under Review" - open PR exists or workflow_status=under_review
 * - "Synced" - workflow_status=synced_with_github and content matches
 * - "Drift Detected" - drift detection reports has_drift=true
 */

export type DerivedStatusLabel =
  | 'Local Draft'
  | 'Imported Locally'
  | 'Pending Sync'
  | 'Under Review'
  | 'Synced'
  | 'Drift Detected';

const ALL_ZEROS_HASH = '0'.repeat(40);

interface WorkflowStatusContext {
  workflowStatus: string | null;
  workflowGitHash: string | null;
  projectPrState: string | null;
  hasOpenPR: boolean;
  hasDrift: boolean;
  hasImportMetadata?: boolean;
}

/**
 * Derive a display-only status label from existing state values.
 * Does NOT change any backend state.
 */
export function deriveWorkflowStatusLabel(ctx: WorkflowStatusContext): DerivedStatusLabel {
  const hasRealHash =
    ctx.workflowGitHash != null &&
    ctx.workflowGitHash !== '' &&
    ctx.workflowGitHash !== ALL_ZEROS_HASH;

  // Drift takes priority when a real baseline exists
  if (ctx.hasDrift && hasRealHash) {
    return 'Drift Detected';
  }

  // Synced state
  if (ctx.workflowStatus === 'synced_with_github' && hasRealHash && !ctx.hasDrift) {
    return 'Synced';
  }

  // Under review: open PR or explicit status
  if (ctx.hasOpenPR || ctx.workflowStatus === 'under_review') {
    return 'Under Review';
  }

  // Imported locally (display-only hint when import metadata available)
  if (ctx.hasImportMetadata && !hasRealHash && !ctx.hasOpenPR) {
    return 'Imported Locally';
  }

  // Local draft: project in draft, workflow not synced
  if (
    ctx.projectPrState === 'draft' &&
    (ctx.workflowStatus === 'new' || ctx.workflowStatus === 'committed_locally') &&
    !hasRealHash &&
    !ctx.hasOpenPR
  ) {
    return 'Local Draft';
  }

  // Pending sync: local workflow without a real baseline
  if (!hasRealHash && !ctx.hasOpenPR) {
    return 'Pending Sync';
  }

  // Fallback to Synced if we have a real hash and no drift
  if (hasRealHash && !ctx.hasDrift) {
    return 'Synced';
  }

  return 'Pending Sync';
}
