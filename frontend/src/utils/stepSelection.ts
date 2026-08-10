import { WorkflowGUI, WorkflowStep } from './workflowGuiConversion';
import { StepSelection } from '../components/StepSelectionContext';

/**
 * Returns `candidate`, or the first `candidate-2`, `candidate-3`… not already
 * taken. Step and job ids double as React keys and as the handle the detail
 * panel selects by, so a collision either mis-renders the list or opens the
 * wrong step. Every minting site could previously collide: adding a step after
 * deleting a middle one, duplicating the same step twice, and duplicating the
 * same job twice.
 */
export function uniqueId(existingIds: string[], candidate: string): string {
  if (!existingIds.includes(candidate)) return candidate;

  let suffix = 2;
  while (existingIds.includes(`${candidate}-${suffix}`)) {
    suffix++;
  }
  return `${candidate}-${suffix}`;
}

/**
 * Whether a validation error's `field` path sits at or under `prefix`.
 *
 * A bare `startsWith` is wrong here: `jobs[0].steps[1]` is a string prefix of
 * `jobs[0].steps[10]`, so single-digit steps would inherit the errors of every
 * step from 10 up. The separator is what makes the boundary explicit.
 */
export function isFieldUnder(field: string, prefix: string): boolean {
  return field === prefix || field.startsWith(`${prefix}.`);
}

export interface ResolvedStep {
  jobIndex: number;
  stepIndex: number;
  step: WorkflowStep;
}

/**
 * Resolves a `{ jobId, stepId }` selection against the current workflow.
 *
 * Selection is held by id rather than index so it survives reorder, duplicate
 * and delete without any mutation-aware fixups: a step that no longer exists
 * simply fails to resolve, and the caller falls back to its empty state.
 *
 * Step ids are not guaranteed unique across the workflow (see the id minting
 * in JobCard.addStep and StepList.duplicateStep), which is why the lookup is
 * scoped to the owning job and takes the first match.
 */
export function findSelectedStep(
  workflow: WorkflowGUI,
  selection: StepSelection | null
): ResolvedStep | null {
  if (!selection) return null;

  const jobIndex = workflow.jobs.findIndex(job => job.id === selection.jobId);
  if (jobIndex === -1) return null;

  const stepIndex = workflow.jobs[jobIndex].steps.findIndex(step => step.id === selection.stepId);
  if (stepIndex === -1) return null;

  return { jobIndex, stepIndex, step: workflow.jobs[jobIndex].steps[stepIndex] };
}

/** Returns a new workflow with one step replaced. Does not mutate the input. */
export function replaceStepAt(
  workflow: WorkflowGUI,
  jobIndex: number,
  stepIndex: number,
  step: WorkflowStep
): WorkflowGUI {
  const jobs = workflow.jobs.map((job, i) => {
    if (i !== jobIndex) return job;
    return { ...job, steps: job.steps.map((s, j) => (j === stepIndex ? step : s)) };
  });
  return { ...workflow, jobs };
}
