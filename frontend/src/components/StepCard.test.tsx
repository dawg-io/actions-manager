import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import StepCard from './StepCard';
import { StepSelectionProvider, StepSelection } from './StepSelectionContext';
import type { WorkflowStep, ValidationError } from '../utils/workflowGuiConversion';

function makeStep(overrides: Partial<WorkflowStep> = {}): WorkflowStep {
  return { id: 'step-1', name: 'Checkout', uses: '', ...overrides };
}

const noValidationErrors: ValidationError[] = [];

function baseProps(overrides: Partial<React.ComponentProps<typeof StepCard>> = {}) {
  return {
    step: makeStep(),
    stepIndex: 0,
    jobId: 'build',
    onRemove: vi.fn(),
    onDuplicate: vi.fn(),
    validationErrors: noValidationErrors,
    ...overrides,
  };
}

interface SelectionValue {
  selected: StepSelection | null;
  onSelect: (s: StepSelection | null) => void;
}

const noSelection = (): SelectionValue => ({ selected: null, onSelect: vi.fn() });

function renderCard(
  props: Partial<React.ComponentProps<typeof StepCard>> = {},
  selection: SelectionValue = noSelection()
) {
  return render(
    <StepSelectionProvider value={selection}>
      <StepCard {...baseProps(props)} />
    </StepSelectionProvider>
  );
}

describe('StepCard row', () => {
  it('renders the step number and title', () => {
    renderCard();

    expect(screen.getByText('1.')).toBeInTheDocument();
    expect(screen.getByText('Checkout')).toBeInTheDocument();
  });

  it('falls back to a positional title for an unnamed step', () => {
    renderCard({ step: makeStep({ name: undefined }), stepIndex: 2 });

    expect(screen.getByText('Step 3')).toBeInTheDocument();
  });

  it('is a row only - the panel is the sole place a step is edited', () => {
    renderCard();

    expect(screen.queryByLabelText('Step Name (optional)')).not.toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: /Use Action/ })).not.toBeInTheDocument();
  });

  it('selects the step when its title row is clicked', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderCard({}, { selected: null, onSelect });

    await user.click(screen.getByText('Checkout'));

    expect(onSelect).toHaveBeenCalledWith({ jobId: 'build', stepId: 'step-1' });
  });

  it('marks the selected row with aria-current', () => {
    renderCard({}, { selected: { jobId: 'build', stepId: 'step-1' }, onSelect: vi.fn() });

    expect(screen.getByRole('button', { name: /Checkout/ })).toHaveAttribute('aria-current', 'true');
  });

  it('leaves a same-id step in a different job unselected', () => {
    renderCard({}, { selected: { jobId: 'test', stepId: 'step-1' }, onSelect: vi.fn() });

    expect(screen.getByRole('button', { name: /Checkout/ })).toHaveAttribute('aria-current', 'false');
  });

  it('surfaces error and warning badges', () => {
    renderCard({
      validationErrors: [
        { field: 'jobs[0].steps[0].uses', message: 'Required', severity: 'error' },
        { field: 'jobs[0].steps[0].name', message: 'Consider naming', severity: 'warning' },
      ],
    });

    expect(screen.getByText('❌')).toBeInTheDocument();
    expect(screen.getByText('⚠️')).toBeInTheDocument();
  });

  it('renders the move, duplicate and remove actions', () => {
    renderCard({ onMoveUp: vi.fn(), onMoveDown: vi.fn() });

    expect(screen.getByTitle('Move up')).toBeInTheDocument();
    expect(screen.getByTitle('Move down')).toBeInTheDocument();
    expect(screen.getByTitle('Duplicate step')).toBeInTheDocument();
    expect(screen.getByTitle('Remove step')).toBeInTheDocument();
  });

  it('omits move controls at the ends of the list', () => {
    renderCard();

    expect(screen.queryByTitle('Move up')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Move down')).not.toBeInTheDocument();
  });
});
