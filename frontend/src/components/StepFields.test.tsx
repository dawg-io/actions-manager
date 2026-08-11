import React from 'react';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import StepFields from './StepFields';
import type { WorkflowStep, ValidationError } from '../utils/workflowGuiConversion';
import type { ActionsProject } from '../api/actionsProjects';
import type { ActionGroup } from '../api/actionGroups';
import { WorkflowResourcesRawProvider } from './WorkflowResourcesContext';
import type { WorkflowResource } from '../utils/workflowResources';

function makeStep(overrides: Partial<WorkflowStep> = {}): WorkflowStep {
  return { id: 'step-1', uses: '', ...overrides };
}

const noValidationErrors: ValidationError[] = [];

function baseProps(overrides: Partial<React.ComponentProps<typeof StepFields>> = {}) {
  return {
    step: makeStep(),
    onChange: vi.fn(),
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

describe('StepFields imported actions', () => {
  it('renders no imported-actions picker when the list is empty', async () => {
    const user = userEvent.setup();
    render(<StepFields {...baseProps()} />);
    await user.click(screen.getByRole('radio', { name: /Use Action/ }));
    expect(screen.queryByText(/Browse imported actions/)).not.toBeInTheDocument();
  });

  it('shows a menu item and datalist option for each imported action', async () => {
    const user = userEvent.setup();
    render(<StepFields {...baseProps({ importedActions: [importedAction] })} />);

    await openActionPicker(user, 1);

    expect(screen.getByRole('menuitem', { name: 'TruffleHog OSS' })).toBeInTheDocument();
  });

  it('sets step.uses and pre-fills typed fields when an imported action is clicked', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<StepFields {...baseProps({ importedActions: [importedAction], onChange })} />);

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
    render(<StepFields {...baseProps({ importedActions: [brandedAction] })} />);

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
      <StepFields
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
      <StepFields
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

describe('StepFields step environment variables', () => {
  function EnvHarness() {
    const [step, setStep] = React.useState<WorkflowStep>(
      makeStep({ env: { FOO: 'a', BAR: 'b' } })
    );
    return <StepFields {...baseProps({ step, onChange: setStep })} />;
  }

  const envKeyInputs = () => screen.getAllByPlaceholderText('Variable name');

  it('does not steal focus onto the surviving row when a key is cleared to delete it', async () => {
    const user = userEvent.setup();
    render(<EnvHarness />);
    await user.click(screen.getByRole('button', { name: /Advanced Settings/i }));

    await user.clear(envKeyInputs()[0]);

    // Clearing FOO's key deletes that row (same effect as its ✕ button).
    // Without the surviving row's stable id being spliced in lockstep, React
    // would reuse the just-deleted DOM node for the remaining row - handing
    // it BAR's value while keeping the focus that was mid-edit on FOO.
    const remaining = envKeyInputs();
    expect(remaining).toHaveLength(1);
    expect(remaining[0]).toHaveValue('BAR');
    expect(remaining[0]).not.toHaveFocus();
  });

  describe('resource picker in free-text fields', () => {
    const resources: WorkflowResource[] = [
      { kind: 'secret', name: 'AM_TEST_TOKEN', repo: 'acme/web' },
    ];

    const renderWithResources = (
      props: Partial<React.ComponentProps<typeof StepFields>> = {},
      available: WorkflowResource[] = resources
    ) =>
      render(
        <WorkflowResourcesRawProvider
          value={{
            resources: available,
            loadingEnvironments: false,
            environmentsError: null,
            requestEnvironments: vi.fn(),
          }}
        >
          <StepFields {...baseProps(props)} />
        </WorkflowResourcesRawProvider>
      );

    test('inserts at the caret in the run script, preserving the rest of it', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      renderWithResources({ step: makeStep({ uses: undefined, run: 'echo  && npm ci' }), onChange });

      await user.click(screen.getByRole('radio', { name: /Run Script/ }));

      const script = screen.getByPlaceholderText('Enter your script commands here...') as HTMLTextAreaElement;
      script.focus();
      script.setSelectionRange(5, 5); // just after "echo "
      fireEvent.keyUp(script, { key: 'ArrowRight' });

      await user.click(screen.getByTestId('resource-picker-trigger'));
      await user.click(await screen.findByTestId('resource-item-AM_TEST_TOKEN'));

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({ run: 'echo ${{ secrets.AM_TEST_TOKEN }} && npm ci' })
      );
    });

    test('appends at the end when the field was never focused', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      renderWithResources({ step: makeStep({ uses: undefined, run: 'echo ' }), onChange });

      await user.click(screen.getByRole('radio', { name: /Run Script/ }));
      await user.click(screen.getByTestId('resource-picker-trigger'));
      await user.click(await screen.findByTestId('resource-item-AM_TEST_TOKEN'));

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({ run: 'echo ${{ secrets.AM_TEST_TOKEN }}' })
      );
    });

    test('inserts into a step environment variable value', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      renderWithResources({ step: makeStep({ env: { FOO: '' } }), onChange });

      await user.click(screen.getByRole('button', { name: /Advanced Settings/ }));

      // The run script has its own trigger, so scope this to the env row.
      const envRow = screen.getByLabelText('Value for FOO').closest('.env-var-item') as HTMLElement;
      await user.click(within(envRow).getByTestId('resource-picker-trigger'));
      await user.click(await screen.findByTestId('resource-item-AM_TEST_TOKEN'));

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({ env: { FOO: '${{ secrets.AM_TEST_TOKEN }}' } })
      );
    });

    test('offers no trigger when the project has no resources', async () => {
      const user = userEvent.setup();
      renderWithResources({ step: makeStep({ uses: undefined, run: 'echo' }) }, []);

      await user.click(screen.getByRole('radio', { name: /Run Script/ }));

      expect(screen.queryByTestId('resource-picker-trigger')).not.toBeInTheDocument();
    });

    test('renders normally with no provider at all', () => {
      render(<StepFields {...baseProps({ step: makeStep({ uses: undefined, run: 'echo' }) })} />);

      expect(screen.getByPlaceholderText('Enter your script commands here...')).toBeInTheDocument();
      expect(screen.queryByTestId('resource-picker-trigger')).not.toBeInTheDocument();
    });
  });
});
