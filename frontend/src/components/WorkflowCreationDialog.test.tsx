import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import WorkflowCreationDialog from './WorkflowCreationDialog';

describe('WorkflowCreationDialog', () => {
  let user: ReturnType<typeof userEvent.setup>;
  
  const defaultProps = {
    showWorkflowCreationDialog: true,
    workflowCreationType: null as 'regular' | 'reusable' | null,
    showDetectionResultsInModal: false,
    isDetecting: false,
    detectedBuildTypesState: [],
    isGeneratingTemplates: false,
    reusableWorkflowsEnabled: true,
    setShowWorkflowCreationDialog: jest.fn(),
    selectWorkflowType: jest.fn(),
    createBlankWorkflow: jest.fn(),
    handleDetectBuildTypes: jest.fn(),
    handleCreateFromTemplates: jest.fn(),
    addWorkflowFromDetection: jest.fn(),
    setWorkflowCreationType: jest.fn(),
    setShowDetectionResultsInModal: jest.fn(),
    setDetectedBuildTypes: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    user = userEvent.setup();
  });

  test('should not render when showWorkflowCreationDialog is false', () => {
    render(<WorkflowCreationDialog {...defaultProps} showWorkflowCreationDialog={false} />);
    expect(screen.queryByText('Create New Workflow')).not.toBeInTheDocument();
  });

  test('should render workflow type selection when workflowCreationType is null', () => {
    render(<WorkflowCreationDialog {...defaultProps} />);
    
    expect(screen.getByText('Create New Workflow')).toBeInTheDocument();
    expect(screen.getByText('What type of workflow would you like to create?')).toBeInTheDocument();
    expect(screen.getByText('Regular Workflow')).toBeInTheDocument();
    expect(screen.getByText('Reusable Workflow')).toBeInTheDocument();
    expect(screen.queryByText('Link Reusable Workflow')).not.toBeInTheDocument();
  });

  test('should render link reusable workflow option for caller projects when enabled', () => {
    render(
      <WorkflowCreationDialog
        {...defaultProps}
        showLinkReusableWorkflow={true}
        onLinkReusableWorkflow={jest.fn()}
      />
    );

    expect(screen.getByText('Link Reusable Workflow')).toBeInTheDocument();
    expect(
      screen.getByText('Connect an existing reusable workflow from an RWX project to this caller project')
    ).toBeInTheDocument();
  });

  test('clicking link reusable workflow closes create dialog and opens link flow', async () => {
    const onLinkReusableWorkflow = jest.fn();
    render(
      <WorkflowCreationDialog
        {...defaultProps}
        showLinkReusableWorkflow={true}
        onLinkReusableWorkflow={onLinkReusableWorkflow}
      />
    );

    await user.click(screen.getByRole('button', { name: /Link Reusable Workflow/i }));

    expect(defaultProps.setShowWorkflowCreationDialog).toHaveBeenCalledWith(false);
    expect(onLinkReusableWorkflow).toHaveBeenCalledTimes(1);
  });

  test('should not render link reusable workflow option when linking is invalid', () => {
    const { rerender } = render(
      <WorkflowCreationDialog
        {...defaultProps}
        showLinkReusableWorkflow={false}
        onLinkReusableWorkflow={jest.fn()}
      />
    );

    expect(screen.queryByText('Link Reusable Workflow')).not.toBeInTheDocument();

    rerender(
      <WorkflowCreationDialog
        {...defaultProps}
        reusableWorkflowsEnabled={false}
        showLinkReusableWorkflow={true}
        onLinkReusableWorkflow={undefined}
      />
    );

    expect(screen.queryByText('Link Reusable Workflow')).not.toBeInTheDocument();
  });

  test('should enable reusable workflow button when reusableWorkflowsEnabled is true', async () => {
    render(<WorkflowCreationDialog {...defaultProps} reusableWorkflowsEnabled={true} />);
    
    const reusableWorkflowButton = screen.getByRole('button', { name: /Reusable Workflow/i });
    expect(reusableWorkflowButton).toBeEnabled();
    expect(reusableWorkflowButton).not.toHaveClass('disabled');
    
    await user.click(reusableWorkflowButton);
    expect(defaultProps.selectWorkflowType).toHaveBeenCalledWith('reusable');
  });

  test('should disable reusable workflow button when reusableWorkflowsEnabled is false', async () => {
    render(<WorkflowCreationDialog {...defaultProps} reusableWorkflowsEnabled={false} />);
    
    const reusableWorkflowButton = screen.getByRole('button', { name: /Reusable Workflow/i });
    expect(reusableWorkflowButton).toBeDisabled();
    
    // The button should have the appropriate tooltip
    expect(reusableWorkflowButton).toHaveAttribute('title', 'Reusable workflows are disabled. Enable them first in the sidebar.');
    
    await user.click(reusableWorkflowButton);
    expect(defaultProps.selectWorkflowType).not.toHaveBeenCalled();
  });

  test('should always enable regular workflow button regardless of reusableWorkflowsEnabled', async () => {
    const { rerender } = render(<WorkflowCreationDialog {...defaultProps} reusableWorkflowsEnabled={false} />);
    
    let regularWorkflowButton = screen.getByRole('button', { name: /Regular Workflow/i });
    expect(regularWorkflowButton).toBeEnabled();
    
    await user.click(regularWorkflowButton);
    expect(defaultProps.selectWorkflowType).toHaveBeenCalledWith('regular');
    
    // Test with reusableWorkflowsEnabled true as well
    rerender(<WorkflowCreationDialog {...defaultProps} reusableWorkflowsEnabled={true} />);
    regularWorkflowButton = screen.getByRole('button', { name: /Regular Workflow/i });
    expect(regularWorkflowButton).toBeEnabled();
  });

  test('should show appropriate tooltip text for reusable workflow button', () => {
    const { rerender } = render(<WorkflowCreationDialog {...defaultProps} reusableWorkflowsEnabled={true} />);
    
    let reusableWorkflowButton = screen.getByRole('button', { name: /Reusable Workflow/i });
    expect(reusableWorkflowButton).toHaveAttribute('title', 'Create reusable workflows that can be called by other workflows across repositories');
    
    // Test disabled state tooltip
    rerender(<WorkflowCreationDialog {...defaultProps} reusableWorkflowsEnabled={false} />);
    reusableWorkflowButton = screen.getByRole('button', { name: /Reusable Workflow/i });
    expect(reusableWorkflowButton).toHaveAttribute('title', 'Reusable workflows are disabled. Enable them first in the sidebar.');
  });

  test('should have proper ARIA attributes for accessibility', () => {
    render(<WorkflowCreationDialog {...defaultProps} />);
    
    const dialog = screen.getByRole('dialog', { name: /Create New Workflow/i });
    expect(dialog).toBeInTheDocument();
    
    // Check for proper heading
    const title = screen.getByRole('heading', { name: /Create New Workflow/i });
    expect(title).toBeInTheDocument();
  });

  test('should render shadcn/ui Dialog component', () => {
    render(<WorkflowCreationDialog {...defaultProps} />);
    
    // Verify dialog is rendered using shadcn/ui Dialog
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
  });

  test('requires a valid workflow name before creating a blank workflow', async () => {
    render(<WorkflowCreationDialog {...defaultProps} workflowCreationType="regular" />);

    const createButton = screen.getByRole('button', { name: /Open Blank Workflow/i });
    expect(createButton).toBeDisabled();
    expect(screen.getByText('Workflow name cannot be empty.')).toBeInTheDocument();

    await user.type(screen.getByLabelText(/Workflow Name/i), ' build-and-test ');

    expect(createButton).toBeEnabled();
    await user.click(createButton);
    expect(defaultProps.createBlankWorkflow).toHaveBeenCalledWith('regular', 'build-and-test');
  });

  test('shows inline validation for unsafe and duplicate workflow names', async () => {
    render(
      <WorkflowCreationDialog
        {...defaultProps}
        workflowCreationType="reusable"
        existingWorkflowNames={['existing-workflow']}
      />
    );

    const input = screen.getByLabelText(/Workflow Name/i);
    await user.type(input, 'bad/name');
    expect(screen.getByText('Workflow name cannot contain path separators.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Open Blank Workflow/i })).toBeDisabled();

    await user.clear(input);
    await user.type(input, 'Existing-Workflow');
    expect(screen.getByText('A workflow with this name already exists in this project.')).toBeInTheDocument();
  });
});
