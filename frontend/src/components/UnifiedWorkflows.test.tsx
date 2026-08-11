import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import UnifiedWorkflows from './UnifiedWorkflows';
import { toast } from '../utils/toast';
import { guiToYaml } from '../utils/workflowGuiConversion';

// The list only needs to let a test select a workflow.
vi.mock('./UnifiedWorkflowList', () => ({
  default: function UnifiedWorkflowList({ unifiedWorkflows, handleSelectWorkflow }: any) {
    return (
      <div>
        {unifiedWorkflows.map((w: any) => (
          <button key={w.id} data-testid={`select-${w.id}`} onClick={() => handleSelectWorkflow(w.id)}>
            {w.name}
          </button>
        ))}
      </div>
    );
  },
}));

// Surfaces exactly what the editor was handed, so the test can assert on the
// model the GUI would render and on the mode it is actually in.
vi.mock('./UnifiedWorkflowEditor', () => ({
  default: function UnifiedWorkflowEditor({
    editMode,
    regularGuiWorkflow,
    handleWorkflowChange,
    setEditMode,
  }: any) {
    return (
      <div>
        <span data-testid="edit-mode">{editMode}</span>
        <span data-testid="gui-model">{JSON.stringify(regularGuiWorkflow)}</span>
        <button data-testid="switch-to-gui" onClick={() => setEditMode('gui')}>
          GUI
        </button>
        <button data-testid="switch-to-yaml" onClick={() => setEditMode('yaml')}>
          YAML
        </button>
        <button
          data-testid="edit-yaml"
          onClick={() =>
            handleWorkflowChange(
              'content',
              'name: Edited\non: push\njobs:\n  edited-job:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo edited\n'
            )
          }
        >
          Edit YAML
        </button>
        <button
          data-testid="break-yaml"
          onClick={() => handleWorkflowChange('content', 'name: [unclosed\non: push')}
        >
          Break YAML
        </button>
        {/* Mirrors the real editor's handleGUIChange: any GUI edit serialises the
            loaded model straight back over the document. */}
        <button
          data-testid="edit-in-gui"
          onClick={() => handleWorkflowChange('content', guiToYaml(regularGuiWorkflow))}
        >
          Edit in GUI
        </button>
      </div>
    );
  },
}));

vi.mock('./WorkflowCreationDialog', () => ({ default: () => null }));
vi.mock('./TemplateSelectionModal', () => ({ default: () => null }));
vi.mock('./CodeownersManager', () => ({ default: () => null }));
vi.mock('./CustomFiles', () => ({ CustomFilePanel: () => null }));

vi.mock('../utils/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

vi.mock('../hooks/useWorkflowOperations', () => ({
  useWorkflowOperations: () => ({
    fetchWorkflowsCount: vi.fn(),
    openWorkflowCreationDialog: vi.fn(),
    selectWorkflowType: vi.fn(),
    handleGenerateTemplates: vi.fn(),
    handleSaveDraftWorkflow: vi.fn(),
    handleSaveDraftLinkedWorkflow: vi.fn(),
    handleCommitAndUpdatePR: vi.fn(),
    handleCommitAndUpdatePRLinked: vi.fn(),
    handleDeleteWorkflow: vi.fn(),
    handleUnlinkWorkflow: vi.fn(),
  }),
}));

const ORIGINAL_YAML =
  'name: Original\non: push\njobs:\n  original-job:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo original\n';

function renderSubject() {
  const setWorkflows = vi.fn();
  const props: any = {
    user: 'test-user',
    projectName: 'test-project',
    projectCode: 'TEST',
    selectedRepos: ['acme/web'],
    regexPattern: '',
    workflows: [{ name: 'build', content: ORIGINAL_YAML }],
    setWorkflows,
    rxworkflows: [],
    setRXWorkflows: vi.fn(),
    addWorkflowToMain: vi.fn(),
    onGenerateTemplates: vi.fn(),
    onAddRXWorkflow: vi.fn(),
    detectedBuildTypes: [],
    reusableWorkflowsEnabled: false,
    repoExists: true,
  };

  const view = render(<UnifiedWorkflows {...props} />);
  return { ...view, setWorkflows, props };
}

const guiModel = () => JSON.parse(screen.getByTestId('gui-model').textContent || '{}');

describe('UnifiedWorkflows YAML/GUI mode switching', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test('rebuilds the GUI model from YAML edited since the workflow was selected', async () => {
    const user = userEvent.setup();
    const { rerender, setWorkflows, props } = renderSubject();

    await user.click(screen.getByTestId('select-regular-0'));
    expect(guiModel().jobs[0].id).toBe('original-job');

    // Edit in YAML mode; the parent owns workflow state, so feed the update back
    // in the way ProjectMgmt does.
    await user.click(screen.getByTestId('edit-yaml'));
    const updated = setWorkflows.mock.calls.at(-1)?.[0];
    const nextWorkflows = typeof updated === 'function' ? updated(props.workflows) : updated;
    rerender(<UnifiedWorkflows {...props} workflows={nextWorkflows} />);

    await user.click(screen.getByTestId('switch-to-gui'));

    await waitFor(() => expect(screen.getByTestId('edit-mode')).toHaveTextContent('gui'));
    expect(guiModel().jobs[0].id).toBe('edited-job');
    expect(guiModel().jobs[0].steps[0].run).toBe('echo edited');
  });

  test('refuses to enter GUI mode when the YAML no longer parses', async () => {
    const user = userEvent.setup();
    const { rerender, setWorkflows, props } = renderSubject();

    await user.click(screen.getByTestId('select-regular-0'));
    await user.click(screen.getByTestId('break-yaml'));
    const updated = setWorkflows.mock.calls.at(-1)?.[0];
    const nextWorkflows = typeof updated === 'function' ? updated(props.workflows) : updated;
    rerender(<UnifiedWorkflows {...props} workflows={nextWorkflows} />);

    setWorkflows.mockClear();
    await user.click(screen.getByTestId('switch-to-gui'));

    expect(screen.getByTestId('edit-mode')).toHaveTextContent('yaml');
    expect(toast.error).toHaveBeenCalledWith('Fix the YAML errors before switching to GUI mode.');
  });

  // The bug's real cost: the GUI model is written back over the document on the
  // first GUI edit, so a stale model silently reverts the YAML edits.
  test('a GUI edit after switching does not revert the YAML edit', async () => {
    const user = userEvent.setup();
    const { rerender, setWorkflows, props } = renderSubject();

    await user.click(screen.getByTestId('select-regular-0'));
    await user.click(screen.getByTestId('edit-yaml'));
    const edited = setWorkflows.mock.calls.at(-1)?.[0];
    const editedWorkflows = typeof edited === 'function' ? edited(props.workflows) : edited;
    rerender(<UnifiedWorkflows {...props} workflows={editedWorkflows} />);

    await user.click(screen.getByTestId('switch-to-gui'));
    await waitFor(() => expect(screen.getByTestId('edit-mode')).toHaveTextContent('gui'));

    setWorkflows.mockClear();
    await user.click(screen.getByTestId('edit-in-gui'));

    const written = setWorkflows.mock.calls.at(-1)?.[0];
    const writtenWorkflows = typeof written === 'function' ? written(editedWorkflows) : written;
    expect(writtenWorkflows[0].content).toContain('edited-job');
    expect(writtenWorkflows[0].content).not.toContain('original-job');
  });

  test('a refused switch does not write anything back over the document', async () => {
    const user = userEvent.setup();
    const { rerender, setWorkflows, props } = renderSubject();

    await user.click(screen.getByTestId('select-regular-0'));
    await user.click(screen.getByTestId('break-yaml'));
    const updated = setWorkflows.mock.calls.at(-1)?.[0];
    const nextWorkflows = typeof updated === 'function' ? updated(props.workflows) : updated;
    rerender(<UnifiedWorkflows {...props} workflows={nextWorkflows} />);

    setWorkflows.mockClear();
    await user.click(screen.getByTestId('switch-to-gui'));

    expect(setWorkflows).not.toHaveBeenCalled();
  });

  test('switching back to YAML is never blocked', async () => {
    const user = userEvent.setup();
    renderSubject();

    await user.click(screen.getByTestId('select-regular-0'));
    await user.click(screen.getByTestId('switch-to-gui'));
    await waitFor(() => expect(screen.getByTestId('edit-mode')).toHaveTextContent('gui'));

    await user.click(screen.getByTestId('switch-to-yaml'));

    expect(screen.getByTestId('edit-mode')).toHaveTextContent('yaml');
    expect(toast.error).not.toHaveBeenCalled();
  });
});
