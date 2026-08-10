import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import StepWithFields from './StepWithFields';
import type { ActionInput, ActionsProject } from '../api/actionsProjects';

function makeInput(name: string, overrides: Partial<ActionInput> = {}): ActionInput {
  return {
    name,
    description: null,
    required: false,
    default: null,
    type: 'string',
    options: null,
    ...overrides,
  };
}

// Shaped like actions/checkout: two inputs that matter, a pile that don't.
const checkout: ActionsProject = {
  actions_project_id: 1,
  name: 'Checkout',
  description: 'Check out repository content',
  source_url: 'https://github.com/actions/checkout/blob/v4/action.yml',
  owner: 'actions',
  repo: 'checkout',
  ref: 'v4',
  yaml_path: 'action.yml',
  inputs: [
    makeInput('repository', { required: true, description: 'Repository name with owner' }),
    makeInput('ref', { required: true }),
    makeInput('token'),
    makeInput('ssh-key'),
    makeInput('ssh-strict', { type: 'boolean', default: 'true' }),
    makeInput('persist-credentials', { type: 'boolean' }),
    makeInput('path'),
    makeInput('clean'),
    makeInput('fetch-depth', { type: 'number', default: '1' }),
    makeInput('lfs'),
    makeInput('submodules'),
    makeInput('set-safe-directory'),
    makeInput('github-server-url'),
  ],
  branding_icon: null,
  branding_color: null,
};

function baseProps(overrides: Partial<React.ComponentProps<typeof StepWithFields>> = {}) {
  return {
    stepId: 'step-1',
    uses: 'actions/checkout@v4',
    withValues: undefined,
    onWithChange: vi.fn(),
    importedActions: [checkout],
    ...overrides,
  };
}

const disclosure = () => screen.getByRole('button', { name: /option/ });

describe('StepWithFields progressive disclosure', () => {
  it('shows only required inputs by default', () => {
    render(<StepWithFields {...baseProps()} />);

    expect(screen.getByLabelText(/^repository \*/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^ref \*/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^token/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^fetch-depth/)).not.toBeInTheDocument();
  });

  it('offers the remaining optional inputs behind a disclosure', () => {
    render(<StepWithFields {...baseProps()} />);

    expect(disclosure()).toHaveTextContent('Show 11 more options');
    expect(disclosure()).toHaveAttribute('aria-expanded', 'false');
  });

  it('reveals the optional inputs when the disclosure is clicked', async () => {
    const user = userEvent.setup();
    render(<StepWithFields {...baseProps()} />);

    await user.click(disclosure());

    expect(disclosure()).toHaveAttribute('aria-expanded', 'true');
    expect(disclosure()).toHaveTextContent('Hide 11 options');
    expect(screen.getByLabelText(/^token/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^github-server-url/)).toBeInTheDocument();
  });

  it('hides them again on a second click', async () => {
    const user = userEvent.setup();
    render(<StepWithFields {...baseProps()} />);

    await user.click(disclosure());
    await user.click(disclosure());

    expect(screen.queryByLabelText(/^token/)).not.toBeInTheDocument();
  });

  it('shows an optional input the user has already set, with a Set badge', () => {
    render(<StepWithFields {...baseProps({ withValues: { 'fetch-depth': '0' } })} />);

    expect(screen.getByLabelText(/^fetch-depth/)).toHaveValue(0);
    expect(screen.getByTitle('Optional input — you set this value')).toHaveTextContent('Set');
    expect(disclosure()).toHaveTextContent('Show 10 more options');
  });

  it('does not badge a required input', () => {
    render(<StepWithFields {...baseProps({ withValues: { repository: 'octo/repo' } })} />);

    expect(screen.queryByTitle('Optional input — you set this value')).not.toBeInTheDocument();
  });

  it('renders no disclosure when every input is required', () => {
    const allRequired = { ...checkout, inputs: [makeInput('repository', { required: true })] };
    render(<StepWithFields {...baseProps({ importedActions: [allRequired] })} />);

    expect(screen.queryByRole('button', { name: /option/ })).not.toBeInTheDocument();
  });

  it('drops the "more" wording when nothing is visible above the disclosure', () => {
    const allOptional = { ...checkout, inputs: [makeInput('token'), makeInput('path')] };
    render(<StepWithFields {...baseProps({ importedActions: [allOptional] })} />);

    expect(disclosure()).toHaveTextContent('Show 2 options');
  });

  it('renders the generic key/value editor and no disclosure for an unrecognized uses', () => {
    render(<StepWithFields {...baseProps({ uses: 'some-org/unlisted@v1', withValues: { foo: 'bar' } })} />);

    expect(screen.queryByRole('button', { name: /option/ })).not.toBeInTheDocument();
    expect(screen.getByDisplayValue('foo')).toBeInTheDocument();
    expect(screen.getByDisplayValue('bar')).toBeInTheDocument();
  });

  it('collapses the disclosure again when the action changes on the same step', async () => {
    const user = userEvent.setup();
    const setupNode: ActionsProject = {
      ...checkout,
      actions_project_id: 2,
      name: 'Setup Node',
      owner: 'actions',
      repo: 'setup-node',
      inputs: [
        makeInput('node-version', { required: true }),
        makeInput('cache'),
        makeInput('registry-url'),
      ],
    };
    const { rerender } = render(
      <StepWithFields {...baseProps({ importedActions: [checkout, setupNode] })} />
    );

    await user.click(disclosure());
    expect(screen.getByLabelText(/^token/)).toBeInTheDocument();

    // Switching the action without a step-selection remount (same stepId)
    // must not carry checkout's expanded/sticky state onto setup-node's
    // unrelated input set.
    rerender(
      <StepWithFields
        {...baseProps({ uses: 'actions/setup-node@v4', importedActions: [checkout, setupNode] })}
      />
    );

    expect(screen.queryByLabelText(/^cache/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /option/ })).toHaveAttribute('aria-expanded', 'false');
  });
});

describe('StepWithFields value editing', () => {
  it('writes a typed value into with', async () => {
    const user = userEvent.setup();
    const onWithChange = vi.fn();
    render(<StepWithFields {...baseProps({ onWithChange })} />);

    await user.type(screen.getByLabelText(/^repository \*/), 'o');

    expect(onWithChange).toHaveBeenLastCalledWith({ repository: 'o' });
  });

  it('deletes the key when a value is cleared', async () => {
    const user = userEvent.setup();
    const onWithChange = vi.fn();
    render(<StepWithFields {...baseProps({ withValues: { 'fetch-depth': '0' }, onWithChange })} />);

    await user.clear(screen.getByLabelText(/^fetch-depth/));

    expect(onWithChange).toHaveBeenLastCalledWith({});
  });

  it('keeps focus while typing into a revealed optional input', async () => {
    const user = userEvent.setup();
    // Mirrors the real parent: `with` is controlled and updates per keystroke.
    function Harness() {
      const [withValues, setWithValues] = React.useState<{ [k: string]: string }>({});
      return <StepWithFields {...baseProps({ withValues, onWithChange: setWithValues })} />;
    }
    render(<Harness />);

    await user.click(disclosure());
    await user.type(screen.getByLabelText(/^token/), 'abc');

    // The first keystroke marks the input "set". If that moved it from the
    // hidden group into the visible group it would change DOM parent, remount,
    // and swallow every character after the first.
    expect(screen.getByLabelText(/^token/)).toHaveValue('abc');
    expect(screen.getByLabelText(/^token/)).toHaveFocus();
  });

  it('keeps a cleared optional input on screen while the disclosure is collapsed', async () => {
    const user = userEvent.setup();
    const onWithChange = vi.fn();
    const { rerender } = render(
      <StepWithFields {...baseProps({ withValues: { 'fetch-depth': '0' }, onWithChange })} />
    );

    await user.clear(screen.getByLabelText(/^fetch-depth/));

    // The parent commits the delete; the field must not vanish under the cursor.
    rerender(<StepWithFields {...baseProps({ withValues: {}, onWithChange })} />);

    expect(screen.getByLabelText(/^fetch-depth/)).toBeInTheDocument();
    expect(screen.queryByTitle('Optional input — you set this value')).not.toBeInTheDocument();
    expect(disclosure()).toHaveTextContent('Show 10 more options');
  });
});
