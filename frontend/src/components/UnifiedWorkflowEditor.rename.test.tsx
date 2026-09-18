/**
 * Renaming a workflow is verified where the user renames it.
 *
 * The name field's own Save is the rename: it is the only control that changes
 * a workflow's filename. Guarding a later save instead — Commit Locally, or the
 * project toolbar's Save — asks the question long after the user has moved on,
 * and asks it again at every subsequent save.
 *
 * Renaming changes the delivered filename: the old file stays in every
 * repository under its old name and a caller's `uses:` line still points at it.
 * The backend enforces the refusals it cannot reconcile, but a 409 is not a
 * verification, so the impact is fetched and shown before the name changes.
 */
import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import UnifiedWorkflowEditor from './UnifiedWorkflowEditor';
import { getRenameImpact } from '../api/workflows';
import { UnifiedWorkflowItem } from '../types/workflow';

vi.mock('../api/workflows', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/workflows')>()),
  getRenameImpact: vi.fn(),
}));

vi.mock('../api/environments', () => ({ getEnvironments: vi.fn().mockResolvedValue([]) }));

vi.mock('./YAMLEditor', () => ({
  default: React.forwardRef(function YAMLEditor(_: any, ref: any) {
    React.useImperativeHandle(ref, () => ({ insertAtCursor: vi.fn() }), []);
    return <div data-testid="yaml-editor" />;
  }),
}));

vi.mock('./GUIWorkflowEditor', () => ({
  default: function GUIWorkflowEditor({ workflow, onChange }: any) {
    return (
      <div data-testid="gui-workflow-editor">
        <button type="button" onClick={() => onChange({ ...workflow, name: 'renamed-from-gui' })}>
          Update GUI
        </button>
      </div>
    );
  },
}));

vi.mock('./VersionHistoryPanel', () => ({
  default: function VersionHistoryPanel() { return null; },
}));

const mockedImpact = vi.mocked(getRenameImpact);

const IMPACT = {
  classification: 'delivered' as const,
  blocked_reason: null,
  old_filename: 'AM_TEST_ci.yml',
  new_filename: 'AM_TEST_renamed.yml',
  targets: [],
  consumers: [],
  overrides: [],
  warnings: [],
};

/** A workflow already persisted under `savedName`, as a loaded project supplies it. */
const workflow = (over: Partial<UnifiedWorkflowItem> = {}): UnifiedWorkflowItem => ({
  id: 'regular-0',
  name: 'ci',
  savedName: 'ci',
  content: 'name: ci\non: [push]',
  type: 'regular',
  isReusable: false,
  originalIndex: 0,
  isModified: false,
  ...over,
});

const handleWorkflowChange = vi.fn();
const saveDraftWorkflow = vi.fn();

const props = {
  editMode: 'yaml' as const,
  regularGuiWorkflow: { name: 'ci', events: [], jobs: [] },
  guiWorkflow: { name: 'ci', events: [], jobs: [] },
  projectCode: 'TEST',
  user: 'octocat',
  projectName: 'Payments',
  setEditMode: vi.fn(),
  setRegularGuiWorkflow: vi.fn(),
  setGuiWorkflow: vi.fn(),
  handleWorkflowChange,
  saveDraftWorkflow,
  deleteWorkflow: vi.fn(),
  importedActions: [],
  actionGroups: [],
};

const user = userEvent.setup();

/** Drive the inline name control: pencil, type, Save. */
const renameTo = async (newName: string) => {
  await user.click(screen.getByTestId('editable-name-edit-button'));
  const input = screen.getByRole('textbox', { name: 'workflow filename' });
  await user.clear(input);
  await user.type(input, newName);
  await user.click(screen.getByTestId('editable-name-save-button'));
};

describe('renaming a workflow from the editor name field', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedImpact.mockResolvedValue(IMPACT as never);
  });

  test('the Save next to the name opens the impact dialog and changes nothing yet', async () => {
    render(<UnifiedWorkflowEditor {...props} selectedWorkflow={workflow()} />);

    await renameTo('renamed');

    // The caller is named. The route answers 401 without it, which failed
    // every preview and left the dialog with only a fetch error to show.
    expect(mockedImpact).toHaveBeenCalledWith('octocat', 'Payments', 'ci', 'renamed', false);
    expect(handleWorkflowChange).not.toHaveBeenCalled();

    expect(await screen.findByText('Rename this workflow?')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Rename' }));

    expect(handleWorkflowChange).toHaveBeenCalledWith('name', 'renamed');
  });

  test('confirming the rename commits it locally, with the new name', async () => {
    // Agreeing to a dialog that spells out what the rename does and then having
    // to press Commit Locally for it to be saved at all is not a flow anyone
    // expects. The name is handed to the save explicitly because the state
    // update applying it is not readable from the same render.
    render(<UnifiedWorkflowEditor {...props} selectedWorkflow={workflow()} />);

    await renameTo('renamed');
    await screen.findByText('Rename this workflow?');
    expect(saveDraftWorkflow).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Rename' }));

    expect(saveDraftWorkflow).toHaveBeenCalledWith(0, 'regular', 'renamed');
  });

  test('naming a never-saved workflow does not commit it', async () => {
    // No dialog, so nothing was agreed to — and a brand-new workflow may have
    // no content yet, which the save rejects with an error toast.
    render(<UnifiedWorkflowEditor {...props} selectedWorkflow={workflow({ savedName: undefined })} />);

    await renameTo('renamed');

    await waitFor(() => expect(handleWorkflowChange).toHaveBeenCalledWith('name', 'renamed'));
    expect(saveDraftWorkflow).not.toHaveBeenCalled();
  });

  test('cancelling the rename commits nothing', async () => {
    render(<UnifiedWorkflowEditor {...props} selectedWorkflow={workflow()} />);

    await renameTo('renamed');
    await screen.findByText('Rename this workflow?');
    await user.click(screen.getByTestId('rename-dismiss'));

    expect(saveDraftWorkflow).not.toHaveBeenCalled();
  });

  test('a blocked rename commits nothing', async () => {
    mockedImpact.mockResolvedValue({
      ...IMPACT, classification: 'blocked', blocked_reason: 'This workflow is under review.',
    } as never);
    render(<UnifiedWorkflowEditor {...props} selectedWorkflow={workflow()} />);

    await renameTo('renamed');

    expect(await screen.findByText('This save cannot be applied')).toBeInTheDocument();
    expect(saveDraftWorkflow).not.toHaveBeenCalled();
  });

  test('cancelling the dialog leaves the name alone', async () => {
    render(<UnifiedWorkflowEditor {...props} selectedWorkflow={workflow()} />);

    await renameTo('renamed');
    await screen.findByText('Rename this workflow?');
    await user.click(screen.getByTestId('rename-dismiss'));

    expect(handleWorkflowChange).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.queryByText('Rename this workflow?')).not.toBeInTheDocument()
    );
  });

  test('a blocked rename cannot be confirmed at all', async () => {
    mockedImpact.mockResolvedValue({
      ...IMPACT,
      classification: 'blocked',
      blocked_reason: 'This workflow is under review. Merge or close its pull request before renaming.',
    } as never);
    render(<UnifiedWorkflowEditor {...props} selectedWorkflow={workflow()} />);

    await renameTo('renamed');

    expect(await screen.findByText('This save cannot be applied')).toBeInTheDocument();
    expect(screen.getByTestId('rename-blocked-reason')).toHaveTextContent('under review');
    expect(screen.queryByRole('button', { name: 'Rename' })).not.toBeInTheDocument();
    expect(handleWorkflowChange).not.toHaveBeenCalled();
  });

  test('an unreachable impact check still offers the rename', async () => {
    // Advisory only — the save enforces the same refusals. Failing closed would
    // make an outage block every rename.
    mockedImpact.mockRejectedValue(new Error('network'));
    render(<UnifiedWorkflowEditor {...props} selectedWorkflow={workflow()} />);

    await renameTo('renamed');

    expect(await screen.findByTestId('rename-check-failed')).toHaveTextContent('network');
    await user.click(screen.getByRole('button', { name: 'Rename' }));
    expect(handleWorkflowChange).toHaveBeenCalledWith('name', 'renamed');
  });

  test('naming a never-saved workflow is not a rename', async () => {
    // No savedName: nothing is delivered under an old name, so there is nothing
    // to warn about and no dialog to sit through.
    render(<UnifiedWorkflowEditor {...props} selectedWorkflow={workflow({ savedName: undefined })} />);

    await renameTo('renamed');

    expect(mockedImpact).not.toHaveBeenCalled();
    await waitFor(() => expect(handleWorkflowChange).toHaveBeenCalledWith('name', 'renamed'));
    expect(screen.queryByText('Rename this workflow?')).not.toBeInTheDocument();
  });

  test('typing the .yml extension onto the current name is not a rename', async () => {
    // The backend stores a stem and appends .yml itself, so "ci.yml" over "ci"
    // changes nothing — prompting for it would be a dialog about no change.
    render(<UnifiedWorkflowEditor {...props} selectedWorkflow={workflow()} />);

    await renameTo('ci.yml');

    expect(mockedImpact).not.toHaveBeenCalled();
    await waitFor(() => expect(handleWorkflowChange).toHaveBeenCalledWith('name', 'ci'));
  });

  test('a reusable workflow is checked as reusable, not as a caller workflow', async () => {
    // Names are not globally unique: a project may own a regular and a reusable
    // workflow with the same name, and the report has to resolve the right one.
    render(
      <UnifiedWorkflowEditor
        {...props}
        selectedWorkflow={workflow({ id: 'reusable-0', type: 'reusable', isReusable: true })}
      />
    );

    await renameTo('renamed');

    expect(mockedImpact).toHaveBeenCalledWith('octocat', 'Payments', 'ci', 'renamed', true);
  });

  test('selecting another workflow drops the pending rename instead of applying it there', async () => {
    const { rerender } = render(
      <UnifiedWorkflowEditor {...props} selectedWorkflow={workflow()} />
    );

    await renameTo('renamed');
    await screen.findByText('Rename this workflow?');

    rerender(
      <UnifiedWorkflowEditor
        {...props}
        selectedWorkflow={workflow({ id: 'regular-1', name: 'build', savedName: 'build' })}
      />
    );

    await waitFor(() =>
      expect(screen.queryByText('Rename this workflow?')).not.toBeInTheDocument()
    );
    expect(handleWorkflowChange).not.toHaveBeenCalled();
  });

  test('a refetch that swaps the workflow at the same index still drops it', async () => {
    // The id is positional (`regular-${index}`), so a refetch that leaves a
    // DIFFERENT workflow at the same index leaves the id unchanged. Keying the
    // reset on the id meant it never fired here: the dialog went on describing
    // ci while confirming renamed build, and sent build's savedName as
    // original_name — a rename never previewed, on a workflow never chosen.
    const { rerender } = render(
      <UnifiedWorkflowEditor {...props} selectedWorkflow={workflow()} />
    );

    await renameTo('renamed');
    await screen.findByText('Rename this workflow?');

    rerender(
      <UnifiedWorkflowEditor
        {...props}
        selectedWorkflow={workflow({ name: 'build', savedName: 'build' })}
      />
    );

    await waitFor(() =>
      expect(screen.queryByText('Rename this workflow?')).not.toBeInTheDocument()
    );
    expect(handleWorkflowChange).not.toHaveBeenCalled();
    expect(saveDraftWorkflow).not.toHaveBeenCalled();
  });

  test('cancelling mid-check does not let the late response reopen the dialog', async () => {
    // cancel() dropped the proceed callback but not the in-flight request, so
    // it resolved, setItems ran, and the dialog came back for a rename the user
    // had dismissed — with a Rename button that then did nothing at all.
    let release: (v: unknown) => void = () => {};
    mockedImpact.mockReturnValue(new Promise((resolve) => { release = resolve; }) as never);

    render(<UnifiedWorkflowEditor {...props} selectedWorkflow={workflow()} />);
    await renameTo('renamed');
    await screen.findByText('Rename this workflow?');

    await user.click(screen.getByTestId('rename-dismiss'));
    await waitFor(() =>
      expect(screen.queryByText('Rename this workflow?')).not.toBeInTheDocument()
    );

    await act(async () => { release(IMPACT); });

    expect(screen.queryByText('Rename this workflow?')).not.toBeInTheDocument();
    expect(handleWorkflowChange).not.toHaveBeenCalled();
    expect(saveDraftWorkflow).not.toHaveBeenCalled();
  });

  test('a GUI name edit does not rename the delivered file', async () => {
    // The GUI's name box edits the YAML `name:` label. It used to be copied
    // into the workflow's filename too, so editing a label renamed the file
    // with no dialog — and once a save carries original_name, that queues the
    // old file for deletion from every repository.
    render(<UnifiedWorkflowEditor {...props} selectedWorkflow={workflow()} editMode="gui" />);

    await user.click(screen.getByRole('button', { name: /update gui/i }));

    expect(handleWorkflowChange).not.toHaveBeenCalledWith('name', expect.anything());
    expect(mockedImpact).not.toHaveBeenCalled();
  });

  test('a linked workflow cannot be renamed here at all', async () => {
    // It belongs to the RWX project that owns it; the field is disabled.
    render(
      <UnifiedWorkflowEditor
        {...props}
        selectedWorkflow={workflow({ id: 'linked-7', type: 'linked', isReusable: true, savedName: undefined })}
      />
    );

    expect(screen.getByTestId('editable-name-edit-button')).toBeDisabled();
  });
});
