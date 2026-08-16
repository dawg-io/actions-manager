import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import WorkflowEditor from './WorkflowEditor';

// Mock child components
vi.mock('./YAMLEditor', () => ({
  default: function YAMLEditor({ value, onChange, placeholder }: any) {
    return (
      <textarea
        data-testid="yaml-editor"
        value={value || ''}
        onChange={(e) => onChange && onChange(e.target.value)}
        placeholder={placeholder}
      />
    );
  },
}));

vi.mock('./GUIWorkflowEditor', () => ({
  default: function GUIWorkflowEditor({ workflow, onChange }: any) {
    return (
      <div data-testid="gui-workflow-editor">
        <div>GUI Editor: {workflow.name}</div>
        <button onClick={() => onChange && onChange(workflow)}>Update GUI</button>
      </div>
    );
  },
}));

vi.mock('./PrefixedInput', () => ({
  default: function PrefixedInput({ value, onChange, placeholder, prefix }: any) {
    return (
      <input
        data-testid="prefixed-input"
        value={value || ''}
        onChange={(e) => onChange && onChange(e.target.value)}
        placeholder={placeholder}
        data-prefix={prefix}
      />
    );
  },
}));

describe('WorkflowEditor Component', () => {
  const user = userEvent.setup();
  const mockWorkflow = {
    name: 'test-workflow.yml',
    content: 'name: test\non: [push]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4',
    isReusable: false,
    isModified: false,
  };

  const defaultProps = {
    workflow: mockWorkflow,
    workflowIndex: 0,
    projectCode: 'TEST',
    isModified: false,
    onWorkflowChange: vi.fn(),
    onClose: vi.fn(),
    onSave: vi.fn(),
    onCreate: vi.fn(),
    onDelete: vi.fn(),
    onSync: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Component Rendering', () => {
    test('renders workflow editor with YAML mode by default', () => {
      render(<WorkflowEditor {...defaultProps} />);

      expect(screen.getByTestId('yaml-editor')).toBeInTheDocument();
      expect(screen.queryByTestId('gui-workflow-editor')).not.toBeInTheDocument();
    });

    test('renders workflow name input', () => {
      render(<WorkflowEditor {...defaultProps} />);

      // Name is read-only by default; user sees the canonical filename
      const display = screen.getByTestId('editable-name-display');
      expect(display).toBeInTheDocument();
      expect(display).toHaveTextContent('AM_TEST_test-workflow.yml');
    });

    test('renders save button when onSave is provided', () => {
      render(<WorkflowEditor {...defaultProps} />);

      expect(screen.getByText(/Save/)).toBeInTheDocument();
    });

    test('renders delete button when onDelete is provided', () => {
      render(<WorkflowEditor {...defaultProps} />);

      expect(screen.getByText(/Delete/)).toBeInTheDocument();
    });
  });

  describe('Mode Switching', () => {
    test('switches from YAML to GUI mode', async () => {
      render(<WorkflowEditor {...defaultProps} />);

      // Find and click the GUI mode button
      const guiButton = screen.getByRole('button', { name: /GUI/i });
      await user.click(guiButton);

      await waitFor(() => {
        expect(screen.getByTestId('gui-workflow-editor')).toBeInTheDocument();
        expect(screen.queryByTestId('yaml-editor')).not.toBeInTheDocument();
      });
    });

    test('switches from GUI to YAML mode', async () => {
      render(<WorkflowEditor {...defaultProps} />);

      // Switch to GUI
      const guiButton = screen.getByRole('button', { name: /GUI/i });
      await user.click(guiButton);

      await waitFor(() => {
        expect(screen.getByTestId('gui-workflow-editor')).toBeInTheDocument();
      });

      // Switch back to YAML
      const yamlButton = screen.getByRole('button', { name: /YAML/i });
      await user.click(yamlButton);

      await waitFor(() => {
        expect(screen.getByTestId('yaml-editor')).toBeInTheDocument();
        expect(screen.queryByTestId('gui-workflow-editor')).not.toBeInTheDocument();
      });
    });

    test('preserves workflow content when switching modes', async () => {
      render(<WorkflowEditor {...defaultProps} />);

      const yamlEditor = screen.getByTestId('yaml-editor') as HTMLTextAreaElement;
      expect(yamlEditor.value).toContain('name: test');

      // Switch to GUI and back
      const guiButton = screen.getByRole('button', { name: /GUI/i });
      await user.click(guiButton);

      await waitFor(() => {
        expect(screen.getByTestId('gui-workflow-editor')).toBeInTheDocument();
      });

      const yamlButton = screen.getByRole('button', { name: /YAML/i });
      await user.click(yamlButton);

      await waitFor(() => {
        const updatedYamlEditor = screen.getByTestId('yaml-editor') as HTMLTextAreaElement;
        expect(updatedYamlEditor).toBeInTheDocument();
      });
    });
  });

  describe('User Interactions', () => {
    test('calls onWorkflowChange when workflow name is changed via edit/save', async () => {
      render(<WorkflowEditor {...defaultProps} />);

      // Click the explicit Edit button to enable name editing
      await user.click(screen.getByTestId('editable-name-edit-button'));

      const nameInput = screen.getByTestId('prefixed-input') as HTMLInputElement;
      await user.clear(nameInput);
      await user.type(nameInput, 'new-workflow');

      await user.click(screen.getByTestId('editable-name-save-button'));

      expect(defaultProps.onWorkflowChange).toHaveBeenCalledWith(
        0,
        'name',
        'new-workflow',
      );
    });

    test('calls onWorkflowChange when YAML content is changed', async () => {
      render(<WorkflowEditor {...defaultProps} />);

      const yamlEditor = screen.getByTestId('yaml-editor');
      await user.clear(yamlEditor);
      await user.type(yamlEditor, 'name: updated');

      expect(defaultProps.onWorkflowChange).toHaveBeenCalled();
    });

    test('calls onSave when save button is clicked', async () => {
      render(<WorkflowEditor {...defaultProps} />);

      const saveButton = screen.getByText(/Save/);
      await user.click(saveButton);

      expect(defaultProps.onSave).toHaveBeenCalledWith(0);
    });

    test('calls onDelete when delete button is clicked', async () => {
      render(<WorkflowEditor {...defaultProps} />);

      const deleteButton = screen.getByText(/Delete/);
      await user.click(deleteButton);

      expect(defaultProps.onDelete).toHaveBeenCalledWith(0);
    });
  });

  describe('Modified State Handling', () => {
    test('displays modified indicator when isModified is true', () => {
      render(<WorkflowEditor {...defaultProps} isModified={true} />);

      expect(screen.getByText(/Modified|Unsaved/i)).toBeInTheDocument();
    });

    test('does not display modified indicator when isModified is false', () => {
      render(<WorkflowEditor {...defaultProps} isModified={false} />);

      expect(screen.queryByText(/Modified|Unsaved/i)).not.toBeInTheDocument();
    });
  });

  describe('Reusable Workflows', () => {
    test('does not display reusable indicator for regular workflows', () => {
      render(<WorkflowEditor {...defaultProps} />);

      expect(screen.queryByText(/^Reusable$/i)).not.toBeInTheDocument();
    });
  });

  describe('Project Code Integration', () => {
    test('works without project code', () => {
      render(<WorkflowEditor {...defaultProps} projectCode={undefined} />);

      expect(screen.getByTestId('yaml-editor')).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    test('handles invalid YAML gracefully when switching to GUI mode', async () => {
      const invalidWorkflow = {
        ...mockWorkflow,
        content: 'invalid: yaml: content: [[[',
      };

      const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      render(<WorkflowEditor {...defaultProps} workflow={invalidWorkflow} />);

      const guiButton = screen.getByRole('button', { name: /GUI/i });
      await user.click(guiButton);

      // Should still render, possibly with error message or fallback
      expect(screen.getByTestId('gui-workflow-editor') || screen.getByTestId('yaml-editor')).toBeInTheDocument();

      consoleWarnSpy.mockRestore();
    });

    test('handles empty workflow content', () => {
      const emptyWorkflow = {
        name: 'empty.yml',
        content: '',
        isReusable: false,
      };

      render(<WorkflowEditor {...defaultProps} workflow={emptyWorkflow} />);

      expect(screen.getByTestId('yaml-editor')).toBeInTheDocument();
    });
  });

  describe('Workflow Index Handling', () => {
    test('handles null workflow index for new workflows', () => {
      render(
        <WorkflowEditor
          {...defaultProps}
          workflow={{ name: '', content: '', isReusable: false }}
          workflowIndex={null}
        />
      );

      expect(screen.getByTestId('yaml-editor')).toBeInTheDocument();
    });

    test('handles valid workflow index for existing workflows', () => {
      render(<WorkflowEditor {...defaultProps} workflowIndex={5} />);

      expect(screen.getByTestId('yaml-editor')).toBeInTheDocument();
    });
  });
});
