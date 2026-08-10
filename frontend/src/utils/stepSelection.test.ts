import { describe, it, expect } from 'vitest';
import { findSelectedStep, replaceStepAt, uniqueId, isFieldUnder } from './stepSelection';
import type { WorkflowGUI } from './workflowGuiConversion';

function makeWorkflow(): WorkflowGUI {
  return {
    name: 'CI',
    events: [{ type: 'push' }],
    jobs: [
      {
        id: 'build',
        name: 'Build',
        runsOn: 'ubuntu-latest',
        steps: [
          { id: 'step-1', name: 'Checkout' },
          { id: 'step-2', name: 'Setup Node' },
        ],
      },
      {
        id: 'test',
        name: 'Test',
        runsOn: 'ubuntu-latest',
        steps: [{ id: 'step-1', name: 'Run tests' }],
      },
    ],
  };
}

describe('uniqueId', () => {
  it('returns the candidate untouched when it is free', () => {
    expect(uniqueId(['step-1'], 'step-2')).toBe('step-2');
  });

  it('suffixes a taken candidate', () => {
    expect(uniqueId(['step-2'], 'step-2')).toBe('step-2-2');
  });

  it('keeps counting past taken suffixes', () => {
    expect(uniqueId(['step-2', 'step-2-2', 'step-2-3'], 'step-2')).toBe('step-2-4');
  });

  it('resolves the add-after-delete collision', () => {
    // Deleting step 1 of 2 leaves ['step-2']; the next add proposes 'step-2'.
    expect(uniqueId(['step-2'], 'step-2')).not.toBe('step-2');
  });

  it('resolves the duplicate-twice collision', () => {
    expect(uniqueId(['step-1', 'step-1-copy'], 'step-1-copy')).toBe('step-1-copy-2');
  });

  it('handles an empty list', () => {
    expect(uniqueId([], 'step-1')).toBe('step-1');
  });
});

describe('isFieldUnder', () => {
  it('matches the prefix itself and its descendants', () => {
    expect(isFieldUnder('jobs[0].steps[1]', 'jobs[0].steps[1]')).toBe(true);
    expect(isFieldUnder('jobs[0].steps[1].uses', 'jobs[0].steps[1]')).toBe(true);
  });

  it('does not let a single-digit index swallow its double-digit neighbours', () => {
    expect(isFieldUnder('jobs[0].steps[10].uses', 'jobs[0].steps[1]')).toBe(false);
    expect(isFieldUnder('jobs[0].steps[19].run', 'jobs[0].steps[1]')).toBe(false);
    expect(isFieldUnder('jobs[10].id', 'jobs[1]')).toBe(false);
  });

  it('does not match an unrelated path', () => {
    expect(isFieldUnder('jobs[1].steps[0].uses', 'jobs[0].steps[0]')).toBe(false);
  });
});

describe('findSelectedStep', () => {
  it('resolves a selection to its job and step indices', () => {
    const resolved = findSelectedStep(makeWorkflow(), { jobId: 'build', stepId: 'step-2' });
    expect(resolved).toMatchObject({ jobIndex: 0, stepIndex: 1 });
    expect(resolved?.step.name).toBe('Setup Node');
  });

  it('scopes the lookup by job, so a step id reused across jobs stays distinct', () => {
    const resolved = findSelectedStep(makeWorkflow(), { jobId: 'test', stepId: 'step-1' });
    expect(resolved).toMatchObject({ jobIndex: 1, stepIndex: 0 });
    expect(resolved?.step.name).toBe('Run tests');
  });

  it('returns null for a null selection', () => {
    expect(findSelectedStep(makeWorkflow(), null)).toBeNull();
  });

  it('returns null when the step id no longer exists', () => {
    expect(findSelectedStep(makeWorkflow(), { jobId: 'build', stepId: 'gone' })).toBeNull();
  });

  it('returns null when the job id no longer exists', () => {
    expect(findSelectedStep(makeWorkflow(), { jobId: 'gone', stepId: 'step-1' })).toBeNull();
  });

  it('follows the step after a reorder', () => {
    const workflow = makeWorkflow();
    workflow.jobs[0].steps.reverse();

    const resolved = findSelectedStep(workflow, { jobId: 'build', stepId: 'step-2' });
    expect(resolved).toMatchObject({ stepIndex: 0 });
    expect(resolved?.step.name).toBe('Setup Node');
  });

  it('returns null once the selected step is deleted', () => {
    const workflow = makeWorkflow();
    workflow.jobs[0].steps = workflow.jobs[0].steps.filter(s => s.id !== 'step-2');

    expect(findSelectedStep(workflow, { jobId: 'build', stepId: 'step-2' })).toBeNull();
  });
});

describe('replaceStepAt', () => {
  it('returns a new workflow with the step replaced', () => {
    const workflow = makeWorkflow();
    const updated = replaceStepAt(workflow, 0, 1, { id: 'step-2', name: 'Setup Bun' });

    expect(updated.jobs[0].steps[1].name).toBe('Setup Bun');
    expect(updated.jobs[0].steps[0].name).toBe('Checkout');
  });

  it('does not mutate the original workflow', () => {
    const workflow = makeWorkflow();
    replaceStepAt(workflow, 0, 1, { id: 'step-2', name: 'Setup Bun' });

    expect(workflow.jobs[0].steps[1].name).toBe('Setup Node');
  });

  it('leaves other jobs untouched by identity', () => {
    const workflow = makeWorkflow();
    const updated = replaceStepAt(workflow, 0, 0, { id: 'step-1', name: 'Checkout v5' });

    expect(updated.jobs[1]).toBe(workflow.jobs[1]);
  });
});
