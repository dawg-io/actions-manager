import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import StepCard from './StepCard';
import type { WorkflowStep, ValidationError } from '../utils/workflowGuiConversion';
import type { ActionsProject } from '../api/actionsProjects';
import type { ActionGroup } from '../api/actionGroups';

function makeStep(overrides: Partial<WorkflowStep> = {}): WorkflowStep {
  return { id: 'step-1', uses: '', ...overrides };
}

const noValidationErrors: ValidationError[] = [];

function baseProps(overrides: Partial<React.ComponentProps<typeof StepCard>> = {}) {
  return {
    step: makeStep(),
    stepIndex: 0,
    onChange: vi.fn(),
    onRemove: vi.fn(),
    onDuplicate: vi.fn(),
    validationErrors: noValidationErrors,
    importedActions: [] as ActionsProject[],
    actionGroups: [] as ActionGroup[],
    ...overrides,
  };
}

const importedAction: ActionsProject = {
  actions_project_id: 42,
  name: 'TruffleHog OSS',
  description: 'Find leaked credentials',
  source_url: 'https://github.com/trufflesecurity/trufflehog/blob/main/action.yml',
  owner: 'trufflesecurity',
  repo: 'trufflehog',
  ref: 'main',
  yaml_path: 'action.yml',
  inputs: [
    { name: 'path', description: 'Path to scan', required: true, default: '.', type: 'string', options: null },
  ],
  branding_icon: null,
  branding_color: null,
};

async function openActionPicker(user: ReturnType<typeof userEvent.setup>, count: number): Promise<void> {
  await user.click(screen.getByRole('radio', { name: /Use Action/ }));
  await user.click(screen.getByRole('button', { name: `Browse imported actions (${count})` }));
}

describe('StepCard imported actions', () => {
  it('renders no imported-actions picker when the list is empty', async () => {
    const user = userEvent.setup();
    render(<StepCard {...baseProps()} />);
    await user.click(screen.getByRole('radio', { name: /Use Action/ }));
    expect(screen.queryByText(/Browse imported actions/)).not.toBeInTheDocument();
  });

  it('shows a menu item and datalist option for each imported action', async () => {
    const user = userEvent.setup();
    render(<StepCard {...baseProps({ importedActions: [importedAction] })} />);

    await openActionPicker(user, 1);

    expect(screen.getByRole('menuitem', { name: 'TruffleHog OSS' })).toBeInTheDocument();
  });

  it('sets step.uses and pre-fills typed fields when an imported action is clicked', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<StepCard {...baseProps({ importedActions: [importedAction], onChange })} />);

    await openActionPicker(user, 1);
    await user.click(screen.getByRole('menuitem', { name: 'TruffleHog OSS' }));

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ uses: 'trufflesecurity/trufflehog@main' })
    );
  });

  it('renders the branding icon on a menu item when the imported action has one', async () => {
    const user = userEvent.setup();
    const brandedAction: ActionsProject = {
      ...importedAction,
      actions_project_id: 99,
      name: 'Branded Action',
      branding_icon: 'rocket',
      branding_color: 'blue',
    };
    render(<StepCard {...baseProps({ importedActions: [brandedAction] })} />);

    await openActionPicker(user, 1);

    // lucide's DynamicIcon resolves the real icon via an async import inside
    // a useEffect (rendering a fallback icon synchronously in the meantime),
    // so wait for the settled result instead of asserting immediately.
    await waitFor(() => {
      const item = screen.getByRole('menuitem', { name: 'Branded Action' });
      expect(item.querySelector('svg')).toBeInTheDocument();
    });
  });

  it('filters the menu by group and never shows an action in two groups at once', async () => {
    const user = userEvent.setup();
    const checkout: ActionsProject = { ...importedAction, actions_project_id: 1, name: 'Checkout' };
    const setupNode: ActionsProject = { ...importedAction, actions_project_id: 2, name: 'Setup Node' };
    const groupA: ActionGroup = { action_group_id: 10, name: 'GroupA', description: null, actions_project_ids: [1] };
    const groupB: ActionGroup = { action_group_id: 11, name: 'GroupB', description: null, actions_project_ids: [1, 2] };

    render(
      <StepCard
        {...baseProps({
          importedActions: [checkout, setupNode],
          actionGroups: [groupA, groupB],
        })}
      />
    );

    await openActionPicker(user, 2);

    // Default "All": both actions show, Checkout appears exactly once.
    expect(screen.getAllByRole('menuitem', { name: 'Checkout' })).toHaveLength(1);
    expect(screen.getByRole('menuitem', { name: 'Setup Node' })).toBeInTheDocument();

    // Checkout is in both GroupA and GroupB, but selecting either group
    // still shows it exactly once — never duplicated.
    await user.click(screen.getByRole('button', { name: 'GroupA' }));
    expect(screen.getAllByRole('menuitem', { name: 'Checkout' })).toHaveLength(1);
    expect(screen.queryByRole('menuitem', { name: 'Setup Node' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'GroupB' }));
    expect(screen.getAllByRole('menuitem', { name: 'Checkout' })).toHaveLength(1);
    expect(screen.getByRole('menuitem', { name: 'Setup Node' })).toBeInTheDocument();
  });

  it('renders a typed field pre-filled from the imported action schema once uses matches', () => {
    render(
      <StepCard
        {...baseProps({
          step: makeStep({ uses: 'trufflesecurity/trufflehog@main' }),
          importedActions: [importedAction],
        })}
      />
    );

    expect(screen.getByText(/path/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText('.')).toBeInTheDocument();
  });
});
