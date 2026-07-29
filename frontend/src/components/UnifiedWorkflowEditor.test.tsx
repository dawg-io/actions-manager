import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import UnifiedWorkflowEditor from './UnifiedWorkflowEditor';
import { UnifiedWorkflowItem } from '../types/workflow';
import { WorkflowGUI } from '../utils/workflowGuiConversion';
import userEvent from '@testing-library/user-event';

// Mock the sub-components
vi.mock('./YAMLEditor', () => ({
  default: function YAMLEditor({ value, onChange, onStructuralDiagnostics, placeholder, readOnly }: any) {
    return (
      <>
        <textarea
          data-testid="yaml-editor"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          readOnly={readOnly}
        />
        <button
          type="button"
          data-testid="emit-structural-diagnostics"
          onClick={() =>
            onStructuralDiagnostics?.([
              {
                severity: 'warning',
                message: 'Mock structural diagnostic',
                line: 1,
                source: 'mock-linter',
              },
            ])
          }
        >
          Emit diagnostics
        </button>
      </>
    );
  },
}));

vi.mock('./GUIWorkflowEditor', () => ({
  default: function GUIWorkflowEditor({ workflow, onChange }: any) {
    return (
      <div data-testid="gui-workflow-editor">
        <button onClick={() => onChange(workflow)}>Update GUI</button>
      </div>
    );
  },
}));

vi.mock('./ReusableGUIWorkflowEditor', () => ({
  default: function ReusableGUIWorkflowEditor({ workflow, onChange }: any) {
    return (
      <div data-testid="reusable-gui-workflow-editor">
        <button onClick={() => onChange(workflow)}>Update Reusable GUI</button>
      </div>
    );
  },
}));

vi.mock('./VersionHistoryPanel', () => ({
  default: function VersionHistoryPanel() {
    return <div data-testid="version-history-panel">Version History Panel</div>;
  },
}));

vi.mock('./OpenInGitHubModal', () => ({
  default: function OpenInGitHubModal({ isOpen, onClose, repositories }: any) {
    if (!isOpen) return null;
    return (
      <div data-testid="github-modal">
        <span>Open in GitHub</span>
        {repositories.map((r: string) => (
          <span key={r} data-testid="github-modal-repo">{r}</span>
        ))}
        <button onClick={onClose}>Close</button>
      </div>
    );
  },
}));

const mockRegularWorkflow: UnifiedWorkflowItem = {
  id: 'regular-1',
  name: 'test-workflow',
  content: 'name: test\non: [push]',
  type: 'regular',
  isReusable: false,
  originalIndex: 0,
  isModified: false
};

const mockReusableWorkflow: UnifiedWorkflowItem = {
  id: 'reusable-1',
  name: 'reusable-workflow',
  content: 'name: reusable\non: [workflow_call]',
  type: 'reusable',
  isReusable: true,
  originalIndex: 0,
  isModified: false
};

const mockLinkedWorkflow: UnifiedWorkflowItem = {
  id: 'linked-42',
  name: 'linked-reusable-workflow',
  content: 'name: linked\non:\n  workflow_call:\n    inputs: {}',
  type: 'linked',
  isReusable: true,
  originalIndex: 0,
  isModified: false,
  rwxProjectId: 7,
  rwxProjectName: 'My RWX Project'
};

const mockGuiWorkflow: WorkflowGUI = {
  name: 'test',
  events: [],
  jobs: []
};

const defaultProps = {
  selectedWorkflow: mockRegularWorkflow,
  editMode: 'yaml' as const,
  regularGuiWorkflow: mockGuiWorkflow,
  guiWorkflow: mockGuiWorkflow,
  projectCode: 'TEST',
  user: 'test-user',
  projectName: 'test-project',
  setEditMode: jest.fn(),
  setRegularGuiWorkflow: jest.fn(),
  setGuiWorkflow: jest.fn(),
  handleWorkflowChange: jest.fn(),
  saveDraftWorkflow: jest.fn(),
  deleteWorkflow: jest.fn()
};

describe('UnifiedWorkflowEditor', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders empty-state card when no workflow is selected', () => {
    render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={null} />);

    expect(screen.getByText('Select a project file')).toBeInTheDocument();
    expect(screen.getByText(/Choose a workflow or file from the panel on the left/)).toBeInTheDocument();
  });

  test('empty state Add Workflow button invokes addWorkflowFn and is hidden when read-only', async () => {
    const addWorkflowFn = jest.fn();
    const { rerender } = render(
      <UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={null} addWorkflowFn={addWorkflowFn} />
    );

    const addButton = screen.getByRole('button', { name: /Add Workflow/i });
    await user.click(addButton);
    expect(addWorkflowFn).toHaveBeenCalledTimes(1);

    rerender(
      <UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={null} addWorkflowFn={addWorkflowFn} isReadOnly />
    );
    expect(screen.queryByRole('button', { name: /Add Workflow/i })).not.toBeInTheDocument();
  });

  test('empty state Import Existing button invokes onImportExisting and is absent when not provided', async () => {
    const onImportExisting = jest.fn();
    const { rerender } = render(
      <UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={null} onImportExisting={onImportExisting} />
    );

    const importButton = screen.getByRole('button', { name: /Import Existing/i });
    await user.click(importButton);
    expect(onImportExisting).toHaveBeenCalledTimes(1);

    rerender(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={null} />);
    expect(screen.queryByRole('button', { name: /Import Existing/i })).not.toBeInTheDocument();
  });

  test('renders regular workflow editor in YAML mode', () => {
    render(<UnifiedWorkflowEditor {...defaultProps} />);
    
    expect(screen.getByTestId('yaml-editor')).toBeInTheDocument();
    expect(screen.getByTestId('editable-name-display')).toHaveTextContent('AM_TEST_test-workflow.yml');
    expect(screen.queryByRole('textbox', { name: 'workflow filename' })).not.toBeInTheDocument();
    expect(screen.getByText('Regular Workflow')).toBeInTheDocument();
  });

  test('renders regular workflow editor in GUI mode', () => {
    render(<UnifiedWorkflowEditor {...defaultProps} editMode="gui" />);
    
    expect(screen.getByTestId('gui-workflow-editor')).toBeInTheDocument();
  });

  test('renders reusable workflow editor in YAML mode', () => {
    render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={mockReusableWorkflow} />);
    
    expect(screen.getByTestId('yaml-editor')).toBeInTheDocument();
    expect(screen.getByTestId('editable-name-display')).toHaveTextContent('AM_TEST_reusable-workflow.yml');
    expect(screen.getByText('Reusable Workflow')).toBeInTheDocument();
  });

  test('renders reusable workflow editor in GUI mode', () => {
    render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={mockReusableWorkflow} editMode="gui" />);
    
    expect(screen.getByTestId('reusable-gui-workflow-editor')).toBeInTheDocument();
  });

  test('workflow name is editable only after clicking edit, and save persists the rename', async () => {
    render(<UnifiedWorkflowEditor {...defaultProps} />);

    await user.click(screen.getByTestId('editable-name-edit-button'));
    const input = screen.getByRole('textbox', { name: 'workflow filename' });
    // In prefix mode the input only contains the editable suffix; the
    // ``AM_TEST_`` prefix and ``.yml`` suffix are rendered as locked chips
    // around the input and reconstructed on save.
    await user.clear(input);
    await user.type(input, 'new-name');
    await user.click(screen.getByTestId('editable-name-save-button'));

    expect(defaultProps.handleWorkflowChange).toHaveBeenCalledWith('name', 'new-name');
  });

  test('cancel exits edit mode and restores the original workflow filename', async () => {
    render(<UnifiedWorkflowEditor {...defaultProps} />);

    await user.click(screen.getByTestId('editable-name-edit-button'));
    const input = screen.getByRole('textbox', { name: 'workflow filename' });
    await user.clear(input);
    await user.type(input, 'renamed');

    await user.click(screen.getByTestId('editable-name-cancel-button'));

    expect(defaultProps.handleWorkflowChange).not.toHaveBeenCalled();
    expect(screen.getByTestId('editable-name-display')).toHaveTextContent('AM_TEST_test-workflow.yml');
  });

  test('rejects invalid workflow filenames and prevents save', async () => {
    render(<UnifiedWorkflowEditor {...defaultProps} />);

    await user.click(screen.getByTestId('editable-name-edit-button'));
    const input = screen.getByRole('textbox', { name: 'workflow filename' });
    await user.clear(input);
    await user.type(input, 'bad/name');

    expect(screen.getByTestId('editable-name-save-button')).toBeDisabled();
    expect(screen.getByTestId('editable-name-error')).toHaveTextContent('path separators');
    expect(defaultProps.handleWorkflowChange).not.toHaveBeenCalled();
  });

  describe('Prefix mode locks the project prefix during rename', () => {
    test('renders the project prefix as a non-editable chip in edit mode', async () => {
      render(<UnifiedWorkflowEditor {...defaultProps} />);

      await user.click(screen.getByTestId('editable-name-edit-button'));

      // The editable input contains only the suffix portion of the workflow name.
      const input = screen.getByRole('textbox', { name: 'workflow filename' }) as HTMLInputElement;
      expect(input.value).toBe('test-workflow');

      // The locked prefix and the .yml extension are rendered as non-input chips.
      const prefixChip = screen.getByTestId('prefixed-input-prefix');
      const suffixChip = screen.getByTestId('prefixed-input-suffix');
      expect(prefixChip).toBeInTheDocument();
      expect(prefixChip.textContent).toBe('AM_TEST_');
      expect(prefixChip.tagName).toBe('SPAN');
      expect(suffixChip).toBeInTheDocument();
      expect(suffixChip.textContent).toBe('.yml');
      expect(suffixChip.tagName).toBe('SPAN');
    });

    test('save reconstructs the full prefixed filename and persists only the suffix', async () => {
      render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={mockReusableWorkflow} />);

      await user.click(screen.getByTestId('editable-name-edit-button'));
      const input = screen.getByRole('textbox', { name: 'workflow filename' });
      await user.clear(input);
      await user.type(input, '111222');
      await user.click(screen.getByTestId('editable-name-save-button'));

      // The handler receives just the suffix; the backend re-applies the prefix.
      expect(defaultProps.handleWorkflowChange).toHaveBeenCalledWith('name', '111222');
    });

    test('rejects attempts to re-include the project prefix in the suffix', async () => {
      render(<UnifiedWorkflowEditor {...defaultProps} />);

      await user.click(screen.getByTestId('editable-name-edit-button'));
      const input = screen.getByRole('textbox', { name: 'workflow filename' });
      await user.clear(input);
      await user.type(input, 'AM_TEST_dup');

      expect(screen.getByTestId('editable-name-save-button')).toBeDisabled();
      expect(screen.getByTestId('editable-name-error')).toHaveTextContent(/project prefix/i);
      expect(defaultProps.handleWorkflowChange).not.toHaveBeenCalled();
    });

    test('no-prefix mode renders the .yml suffix chip and keeps only the stem editable', async () => {
      render(<UnifiedWorkflowEditor {...defaultProps} usePrefix={false} />);

      await user.click(screen.getByTestId('editable-name-edit-button'));
      const input = screen.getByRole('textbox', { name: 'workflow filename' }) as HTMLInputElement;

      // No prefix chip in no-prefix mode...
      expect(screen.queryByTestId('prefixed-input-prefix')).not.toBeInTheDocument();
      // ...but the `.yml` extension is rendered as a locked suffix chip,
      // matching the prefix-mode UI pattern.
      const suffixChip = screen.getByTestId('prefixed-input-suffix');
      expect(suffixChip).toBeInTheDocument();
      expect(suffixChip.textContent).toBe('.yml');
      // The editable input contains only the workflow stem.
      expect(input.value).toBe('test-workflow');

      await user.clear(input);
      await user.type(input, 'renamed');
      await user.click(screen.getByTestId('editable-name-save-button'));

      expect(defaultProps.handleWorkflowChange).toHaveBeenCalledWith('name', 'renamed');
    });

    test('no-prefix mode strips a manually typed .yml extension before saving', async () => {
      render(<UnifiedWorkflowEditor {...defaultProps} usePrefix={false} />);

      await user.click(screen.getByTestId('editable-name-edit-button'));
      const input = screen.getByRole('textbox', { name: 'workflow filename' }) as HTMLInputElement;

      await user.clear(input);
      await user.type(input, 'renamed.yml');
      await user.click(screen.getByTestId('editable-name-save-button'));

      // The extension is normalised away so the persisted stem never carries
      // a duplicate `.yml`/`.yaml` suffix.
      expect(defaultProps.handleWorkflowChange).toHaveBeenCalledWith('name', 'renamed');
    });

    test('no-prefix mode normalises a manually typed .yaml extension to the canonical stem', async () => {
      render(<UnifiedWorkflowEditor {...defaultProps} usePrefix={false} />);

      await user.click(screen.getByTestId('editable-name-edit-button'));
      const input = screen.getByRole('textbox', { name: 'workflow filename' }) as HTMLInputElement;

      await user.clear(input);
      await user.type(input, 'renamed.yaml');
      await user.click(screen.getByTestId('editable-name-save-button'));

      expect(defaultProps.handleWorkflowChange).toHaveBeenCalledWith('name', 'renamed');
    });
  });

  test('calls saveDraftWorkflow directly without confirmation modal', async () => {
    const user = userEvent.setup();
    render(<UnifiedWorkflowEditor {...defaultProps} />);
    
    const button = screen.getByText('💾 Commit Locally');
    await user.click(button);

    // Should NOT show confirmation modal
    expect(screen.queryByText(/Save draft for workflow "test-workflow"\?/)).not.toBeInTheDocument();

    // Should call saveDraftWorkflow directly
    expect(defaultProps.saveDraftWorkflow).toHaveBeenCalledWith(0, 'regular');
  });

  test('clears stale diagnostics when switching workflows', async () => {
    const { rerender } = render(<UnifiedWorkflowEditor {...defaultProps} />);

    await user.click(screen.getByTestId('emit-structural-diagnostics'));
    expect(screen.getByText('Mock structural diagnostic')).toBeInTheDocument();

    rerender(
      <UnifiedWorkflowEditor
        {...defaultProps}
        selectedWorkflow={mockReusableWorkflow}
      />
    );

    expect(screen.queryByText('Mock structural diagnostic')).not.toBeInTheDocument();
  });

  test('calls setEditMode when mode toggle buttons are clicked', () => {
    render(<UnifiedWorkflowEditor {...defaultProps} />);
    
    const guiButton = screen.getByText('GUI');
    fireEvent.click(guiButton);
    
    expect(defaultProps.setEditMode).toHaveBeenCalledWith('gui');
  });

  test('shows update-PR commit label when projectPRState is open', () => {
    render(<UnifiedWorkflowEditor {...defaultProps} projectPRState="open" />);
    expect(screen.getByText('💾 Commit Locally (Update PR)')).toBeInTheDocument();
  });

  describe('workflow state badge (per-workflow status, not project-wide)', () => {
    // Regression coverage for: "Editing One Synced Workflow Incorrectly Marks
    // All Workflows as Draft".  The badge in the editor header MUST be derived
    // exclusively from `selectedWorkflow.workflowStatus` / `isModified` and
    // MUST NOT change when the project-wide `projectPRState` changes.

    test('shows Synced when workflow is synced_with_github regardless of projectPRState', () => {
      const synced: UnifiedWorkflowItem = {
        ...mockRegularWorkflow,
        workflowStatus: 'synced_with_github',
        isModified: false,
      };
      // Even when another workflow in the project causes projectPRState to flip
      // to "draft", this synced workflow must still show Synced.
      render(
        <UnifiedWorkflowEditor
          {...defaultProps}
          selectedWorkflow={synced}
          projectPRState="draft"
        />
      );
      expect(screen.getByText('Synced')).toBeInTheDocument();
      expect(screen.queryByText('Draft')).not.toBeInTheDocument();
    });

    test('shows Draft only when this workflow is committed_locally', () => {
      const committed: UnifiedWorkflowItem = {
        ...mockRegularWorkflow,
        workflowStatus: 'committed_locally',
        isModified: false,
      };
      render(
        <UnifiedWorkflowEditor
          {...defaultProps}
          selectedWorkflow={committed}
          projectPRState="synced"
        />
      );
      expect(screen.getByText('Draft')).toBeInTheDocument();
      expect(screen.queryByText('Synced')).not.toBeInTheDocument();
    });

    test('shows Unsaved when this specific workflow has unsaved edits', () => {
      const edited: UnifiedWorkflowItem = {
        ...mockRegularWorkflow,
        workflowStatus: 'synced_with_github',
        isModified: true,
      };
      render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={edited} />);
      expect(screen.getByText('Unsaved')).toBeInTheDocument();
      expect(screen.queryByText('Synced')).not.toBeInTheDocument();
    });

    test('shows Under Review when workflowStatus is under_review', () => {
      const underReview: UnifiedWorkflowItem = {
        ...mockRegularWorkflow,
        workflowStatus: 'under_review',
        isModified: false,
      };
      render(
        <UnifiedWorkflowEditor
          {...defaultProps}
          selectedWorkflow={underReview}
          projectPRState="synced"
        />
      );
      expect(screen.getByText('Under Review')).toBeInTheDocument();
    });

    test('shows New Local when workflowStatus is new', () => {
      const newCommitted: UnifiedWorkflowItem = {
        ...mockRegularWorkflow,
        workflowStatus: 'new',
        isModified: false,
      };
      render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={newCommitted} />);
      expect(screen.getByText('New Local')).toBeInTheDocument();
    });
  });

  test('disables Commit Locally button when workflow name or content is missing', () => {
    const workflowWithoutContent = { ...mockRegularWorkflow, content: '' };
    render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={workflowWithoutContent} />);
    
    const button = screen.getByText('💾 Commit Locally');
    expect(button).toBeDisabled();
  });

  test('read-only mode disables write actions and keeps overlay accessible', () => {
    render(<UnifiedWorkflowEditor {...defaultProps} isReadOnly={true} />);

    // Primary save action is disabled
    const saveButton = screen.getByText('💾 Commit Locally');
    expect(saveButton).toBeDisabled();

    // Name edit affordance is disabled
    expect(screen.getByTestId('editable-name-edit-button')).toBeDisabled();

    // Mode toggles are disabled
    expect(screen.getByText('YAML')).toBeDisabled();
    expect(screen.getByText('GUI')).toBeDisabled();

    // More button is disabled in read-only mode
    const moreBtn = screen.getByLabelText('More options');
    expect(moreBtn).toBeDisabled();

    // Read-only overlay is focusable and announced
    const overlayStatus = screen.getByRole('status');
    expect(overlayStatus).toHaveAttribute('aria-live', 'polite');
    expect(overlayStatus).toHaveAttribute('tabIndex', '0');
  });

  test('applies correct CSS class for regular workflow', () => {
    const { container } = render(<UnifiedWorkflowEditor {...defaultProps} />);
    
    expect(container.querySelector('.regular-workflow-editor')).toBeInTheDocument();
  });

  test('applies correct CSS class for reusable workflow', () => {
    const { container } = render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={mockReusableWorkflow} />);
    
    expect(container.querySelector('.reusable-workflow-editor')).toBeInTheDocument();
  });

  test('uses correct placeholder for regular workflow in YAML mode', () => {
    render(<UnifiedWorkflowEditor {...defaultProps} />);
    
    const textarea = screen.getByTestId('yaml-editor');
    expect(textarea).toHaveAttribute('placeholder', '# GitHub Actions workflow YAML content');
  });

  test('uses correct placeholder for reusable workflow in YAML mode', () => {
    render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={mockReusableWorkflow} />);
    
    const textarea = screen.getByTestId('yaml-editor');
    expect(textarea).toHaveAttribute('placeholder', '# Reusable workflow YAML content');
  });

  test('does not apply prefix when secure prefix mode is disabled', () => {
    render(<UnifiedWorkflowEditor {...defaultProps} usePrefix={false} />);
    expect(screen.getByTestId('editable-name-display')).toHaveTextContent('test-workflow.yml');
  });

  test('does not apply prefix when projectCode is missing', () => {
    render(<UnifiedWorkflowEditor {...defaultProps} projectCode={null} usePrefix={true} />);
    expect(screen.getByTestId('editable-name-display')).toHaveTextContent('test-workflow.yml');
  });

  test('preserves workflow name when changing from YAML to GUI mode', () => {
    const workflowWithName: UnifiedWorkflowItem = {
      id: 'regular-1',
      name: 'MyCustomWorkflow',
      content: '',
      type: 'regular',
      isReusable: false,
      originalIndex: 0,
      isModified: true
    };

    render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={workflowWithName} />);
    
    // Verify name is displayed in YAML mode
    expect(screen.getByTestId('editable-name-display')).toHaveTextContent('AM_TEST_MyCustomWorkflow.yml');
    
    // Switch to GUI mode
    const guiButton = screen.getByText('GUI');
    fireEvent.click(guiButton);
    
    expect(defaultProps.setEditMode).toHaveBeenCalledWith('gui');
  });

  test('calls handleWorkflowChange for both name and content when GUI changes', () => {
    const mockSetRegularGuiWorkflow = jest.fn();
    const mockHandleWorkflowChange = jest.fn();
    
    const guiWorkflow: WorkflowGUI = {
      name: 'UpdatedName',
      events: [],
      jobs: []
    };

    render(
      <UnifiedWorkflowEditor 
        {...defaultProps} 
        editMode="gui"
        regularGuiWorkflow={guiWorkflow}
        setRegularGuiWorkflow={mockSetRegularGuiWorkflow}
        handleWorkflowChange={mockHandleWorkflowChange}
      />
    );
    
    // Simulate GUI change
    const updateButton = screen.getByText('Update GUI');
    fireEvent.click(updateButton);
    
    // Should update GUI state
    expect(mockSetRegularGuiWorkflow).toHaveBeenCalledWith(guiWorkflow);
    
    // Should convert to YAML and update content
    expect(mockHandleWorkflowChange).toHaveBeenCalledWith('content', expect.any(String));
  });

  describe('More dropdown menu', () => {
    test('renders More button with correct aria attributes', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} />);
      const moreBtn = screen.getByLabelText('More options');
      expect(moreBtn).toHaveAttribute('aria-haspopup', 'true');
      expect(moreBtn).toHaveAttribute('aria-expanded', 'false');
    });

    test('opens More dropdown on click and updates aria-expanded', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} />);
      const moreBtn = screen.getByLabelText('More options');
      fireEvent.click(moreBtn);
      expect(moreBtn).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByRole('menu')).toBeInTheDocument();
    });

    test('More dropdown contains all expected items', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} />);
      fireEvent.click(screen.getByLabelText('More options'));
      expect(screen.getByText(/Open in GitHub/)).toBeInTheDocument();
      expect(screen.getByText(/History/)).toBeInTheDocument();
      expect(screen.getByText(/Duplicate workflow/)).toBeInTheDocument();
      expect(screen.getByText(/Rename workflow/)).toBeInTheDocument();
      expect(screen.getByText(/Delete workflow/)).toBeInTheDocument();
    });

    test('Duplicate workflow menu item is disabled', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} />);
      fireEvent.click(screen.getByLabelText('More options'));
      const btn = screen.getByRole('menuitem', { name: /Duplicate workflow/ });
      expect(btn).toBeDisabled();
    });

    test('Rename workflow menu item is disabled', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} />);
      fireEvent.click(screen.getByLabelText('More options'));
      const btn = screen.getByRole('menuitem', { name: /Rename workflow/ });
      expect(btn).toBeDisabled();
    });

    test('Delete workflow menu item shows confirm dialog and then calls deleteWorkflow', async () => {
      const user = userEvent.setup();
      render(<UnifiedWorkflowEditor {...defaultProps} />);
      fireEvent.click(screen.getByLabelText('More options'));
      fireEvent.click(screen.getByText(/Delete workflow/));

      // ConfirmDialog should now be visible - check for dialog element
      expect(screen.getByRole('dialog')).toBeInTheDocument();

      // Click the confirm button in the dialog
      const confirmBtn = screen.getByRole('button', { name: /Delete workflow/i });
      await user.click(confirmBtn);

      expect(defaultProps.deleteWorkflow).toHaveBeenCalledWith(0, 'regular');
    });

    test('Delete workflow cancellation does not call deleteWorkflow', async () => {
      const user = userEvent.setup();
      render(<UnifiedWorkflowEditor {...defaultProps} />);
      fireEvent.click(screen.getByLabelText('More options'));
      fireEvent.click(screen.getByText(/Delete workflow/));

      // ConfirmDialog should now be visible
      expect(screen.getByRole('dialog')).toBeInTheDocument();

      // Click cancel
      await user.click(screen.getByRole('button', { name: /Cancel/i }));

      expect(defaultProps.deleteWorkflow).not.toHaveBeenCalled();
    });

    test('More dropdown closes on outside click', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} />);
      fireEvent.click(screen.getByLabelText('More options'));
      expect(screen.getByRole('menu')).toBeInTheDocument();
      fireEvent.mouseDown(document.body);
      expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    });

    test('More dropdown closes on Escape key', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} />);
      fireEvent.click(screen.getByLabelText('More options'));
      expect(screen.getByRole('menu')).toBeInTheDocument();
      fireEvent.keyDown(document, { key: 'Escape' });
      expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    });

  });

  describe('Open in GitHub modal', () => {
    test('clicking Open in GitHub opens the modal', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} selectedRepos={['owner/repo1']} />);
      fireEvent.click(screen.getByLabelText('More options'));
      fireEvent.click(screen.getByText(/Open in GitHub/));
      expect(screen.getByTestId('github-modal')).toBeInTheDocument();
    });

    test('modal is closed after clicking Close', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} selectedRepos={['owner/repo1']} />);
      fireEvent.click(screen.getByLabelText('More options'));
      fireEvent.click(screen.getByText(/Open in GitHub/));
      expect(screen.getByTestId('github-modal')).toBeInTheDocument();
      fireEvent.click(screen.getByText('Close'));
      expect(screen.queryByTestId('github-modal')).not.toBeInTheDocument();
    });

    test('modal receives repository list from selectedRepos', () => {
      render(
        <UnifiedWorkflowEditor
          {...defaultProps}
          selectedRepos={['owner/repo1', 'owner/repo2', 'owner/repo3', 'owner/repo4']}
        />
      );
      fireEvent.click(screen.getByLabelText('More options'));
      fireEvent.click(screen.getByText(/Open in GitHub/));
      expect(screen.getAllByTestId('github-modal-repo')).toHaveLength(4);
    });

    test('Open in GitHub button is disabled when no repos are available', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} selectedRepos={[]} />);
      fireEvent.click(screen.getByLabelText('More options'));
      const btn = screen.getByRole('menuitem', { name: /Open in GitHub/ });
      expect(btn).toBeDisabled();
    });
  });

  describe('linked workflow', () => {
    test('renders YAML editor in editable mode', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={mockLinkedWorkflow} />);
      const textarea = screen.getByTestId('yaml-editor');
      expect(textarea).toBeInTheDocument();
      expect(textarea).not.toHaveAttribute('readOnly');
    });

    test('shows Linked Workflow badge', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={mockLinkedWorkflow} />);
      expect(screen.getByText('Linked Workflow')).toBeInTheDocument();
    });

    test('shows source project name', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={mockLinkedWorkflow} />);
      expect(screen.getByText('My RWX Project')).toBeInTheDocument();
    });

    test('renders Save to RWX Project button when saveDraftLinkedWorkflow is provided', () => {
      const mockSaveDraftLinked = jest.fn().mockResolvedValue(undefined);
      render(
        <UnifiedWorkflowEditor
          {...defaultProps}
          selectedWorkflow={mockLinkedWorkflow}
          saveDraftLinkedWorkflow={mockSaveDraftLinked}
        />
      );
      expect(screen.getByText('💾 Save to RWX Project')).toBeInTheDocument();
    });

    test('does not render save button when saveDraftLinkedWorkflow is not provided', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={mockLinkedWorkflow} />);
      expect(screen.queryByText('💾 Save to RWX Project')).not.toBeInTheDocument();
    });

    test('calls saveDraftLinkedWorkflow when Save to RWX Project button is clicked', () => {
      const mockSaveDraftLinked = jest.fn().mockResolvedValue(undefined);
      render(
        <UnifiedWorkflowEditor
          {...defaultProps}
          selectedWorkflow={mockLinkedWorkflow}
          saveDraftLinkedWorkflow={mockSaveDraftLinked}
        />
      );
      const button = screen.getByText('💾 Save to RWX Project');
      fireEvent.click(button);
      expect(mockSaveDraftLinked).toHaveBeenCalledWith(0);
    });

    test('does not render More dropdown for linked workflow', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={mockLinkedWorkflow} />);
      expect(screen.queryByLabelText('More options')).not.toBeInTheDocument();
    });

    test('does not render YAML/GUI mode toggle', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={mockLinkedWorkflow} />);
      expect(screen.queryByText('YAML')).not.toBeInTheDocument();
      expect(screen.queryByText('GUI')).not.toBeInTheDocument();
    });

    test('applies linked-workflow-editor CSS class', () => {
      const { container } = render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={mockLinkedWorkflow} />);
      expect(container.querySelector('.linked-workflow-editor')).toBeInTheDocument();
    });

    test('uses reusable workflow placeholder for YAML editor', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={mockLinkedWorkflow} />);
      const textarea = screen.getByTestId('yaml-editor');
      expect(textarea).toHaveAttribute('placeholder', '# Reusable workflow YAML content');
    });

    test('calls handleWorkflowChange when YAML content changes', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={mockLinkedWorkflow} />);
      const textarea = screen.getByTestId('yaml-editor');
      fireEvent.change(textarea, { target: { value: 'new content' } });
      expect(defaultProps.handleWorkflowChange).toHaveBeenCalledWith('content', 'new content');
    });

    test('renders linked workflow filename as plain text by default', () => {
      render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={mockLinkedWorkflow} />);
      expect(screen.getByTestId('editable-name-display')).toHaveTextContent('linked-reusable-workflow.yml');
      expect(screen.getByTestId('editable-name-edit-button')).toBeDisabled();
      expect(screen.queryByRole('textbox', { name: 'workflow filename' })).not.toBeInTheDocument();
    });

    test('renders prefixed linked workflow filename as a single value', () => {
      const prefixedLinkedWorkflow: UnifiedWorkflowItem = {
        ...mockLinkedWorkflow,
        name: 'AM_RWW1_testrwx',
      };
      render(<UnifiedWorkflowEditor {...defaultProps} selectedWorkflow={prefixedLinkedWorkflow} />);
      expect(screen.getByTestId('editable-name-display')).toHaveTextContent('AM_RWW1_testrwx.yml');
    });
  });

  describe('Unlink Workflow', () => {
    const unlinkMock = jest.fn().mockResolvedValue(undefined);

    test('shows More menu with Unlink option for linked workflows', async () => {
      render(
        <UnifiedWorkflowEditor
          {...defaultProps}
          selectedWorkflow={mockLinkedWorkflow}
          unlinkWorkflow={unlinkMock}
        />
      );

      const moreButton = screen.getByTestId('linked-workflow-more-button');
      expect(moreButton).toBeInTheDocument();
      await user.click(moreButton);

      expect(screen.getByTestId('unlink-workflow-button')).toBeInTheDocument();
      expect(screen.getByText(/Unlink Workflow/)).toBeInTheDocument();
    });

    test('does not show More menu for linked workflows without unlinkWorkflow prop', () => {
      render(
        <UnifiedWorkflowEditor
          {...defaultProps}
          selectedWorkflow={mockLinkedWorkflow}
        />
      );

      expect(screen.queryByTestId('linked-workflow-more-button')).not.toBeInTheDocument();
    });

    test('clicking Unlink shows confirmation dialog', async () => {
      render(
        <UnifiedWorkflowEditor
          {...defaultProps}
          selectedWorkflow={mockLinkedWorkflow}
          unlinkWorkflow={unlinkMock}
        />
      );

      await user.click(screen.getByTestId('linked-workflow-more-button'));
      await user.click(screen.getByTestId('unlink-workflow-button'));

      // Confirmation dialog should appear with the workflow name in the title
      expect(screen.getByText(/Unlink workflow "linked-reusable-workflow"/i)).toBeInTheDocument();
      expect(screen.getByText(/remove the linked reusable workflow from this project only/i)).toBeInTheDocument();
    });

    test('cancel in confirmation dialog does not call unlinkWorkflow', async () => {
      render(
        <UnifiedWorkflowEditor
          {...defaultProps}
          selectedWorkflow={mockLinkedWorkflow}
          unlinkWorkflow={unlinkMock}
        />
      );

      await user.click(screen.getByTestId('linked-workflow-more-button'));
      await user.click(screen.getByTestId('unlink-workflow-button'));

      // Click Cancel
      await user.click(screen.getByText('Cancel'));

      expect(unlinkMock).not.toHaveBeenCalled();
    });

    test('confirm in confirmation dialog calls unlinkWorkflow with correct workflow id', async () => {
      render(
        <UnifiedWorkflowEditor
          {...defaultProps}
          selectedWorkflow={mockLinkedWorkflow}
          unlinkWorkflow={unlinkMock}
        />
      );

      await user.click(screen.getByTestId('linked-workflow-more-button'));
      await user.click(screen.getByTestId('unlink-workflow-button'));

      // Click confirm
      await user.click(screen.getByRole('button', { name: /Unlink Workflow/i }));

      expect(unlinkMock).toHaveBeenCalledWith(42); // workflow id parsed from 'linked-42'
    });

    test('does not show Unlink menu for regular workflows', () => {
      render(
        <UnifiedWorkflowEditor
          {...defaultProps}
          selectedWorkflow={mockRegularWorkflow}
          unlinkWorkflow={unlinkMock}
        />
      );

      expect(screen.queryByTestId('linked-workflow-more-button')).not.toBeInTheDocument();
      expect(screen.queryByTestId('unlink-workflow-button')).not.toBeInTheDocument();
    });
  });
});
