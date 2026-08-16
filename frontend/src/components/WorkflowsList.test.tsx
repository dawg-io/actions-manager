import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import WorkflowsList from './WorkflowsList';

// Mock workflow data for testing
const mockWorkflows = [
  {
    name: 'Test Workflow 1',
    content: 'name: test\non: [push]',
    isModified: false
  },
  {
    name: 'Test Workflow 2',
    content: 'name: test2\non: [pull_request]',
    isModified: true
  }
];

const mockProps = {
  workflows: mockWorkflows,
  selectedWorkflowIndex: 0,
  onSelectWorkflow: vi.fn(),
  projectCode: 'TEST',
  workflowStatuses: {},
  loadingStatuses: false,
  getWorkflowStatusDisplay: vi.fn().mockReturnValue([]),
  getStatusIcon: vi.fn().mockReturnValue('✓'),
  getStatusColor: vi.fn().mockReturnValue('#green'),
  isCollapsed: false,
  onToggleCollapse: vi.fn()
};

describe('WorkflowsList', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  test('renders workflows list when expanded', () => {
    render(<WorkflowsList {...mockProps} />);

    // Should show the full title when expanded
    expect(screen.getByText('📝 Workflows')).toBeInTheDocument();
    
    // Should show all workflows
    expect(screen.getByText('Test Workflow 1.yml')).toBeInTheDocument();
    expect(screen.getByText('Test Workflow 2.yml')).toBeInTheDocument();
    
    // Should show the toggle button
    expect(screen.getByTitle('Collapse workflows list')).toBeInTheDocument();
  });

  test('renders workflows list when collapsed', () => {
    const collapsedProps = { ...mockProps, isCollapsed: true };
    render(<WorkflowsList {...collapsedProps} />);

    // Should show the short title when collapsed
    expect(screen.getByText('📝')).toBeInTheDocument();
    expect(screen.queryByText('📝 Workflows')).not.toBeInTheDocument();
    
    // Should not show workflows when collapsed
    expect(screen.queryByText('Test Workflow 1')).not.toBeInTheDocument();
    expect(screen.queryByText('Test Workflow 2')).not.toBeInTheDocument();
    
    // Should show the toggle button with correct title
    expect(screen.getByTitle('Expand workflows list')).toBeInTheDocument();
  });

  test('toggle button shows correct arrow direction', () => {
    const { rerender } = render(<WorkflowsList {...mockProps} />);
    
    // When expanded, should show left arrow
    const toggleButton = screen.getByTitle('Collapse workflows list');
    expect(toggleButton).toHaveTextContent('◄');
    
    // When collapsed, should show right arrow
    const collapsedProps = { ...mockProps, isCollapsed: true };
    rerender(<WorkflowsList {...collapsedProps} />);
    const expandButton = screen.getByTitle('Expand workflows list');
    expect(expandButton).toHaveTextContent('►');
  });

  test('clicking toggle button calls onToggleCollapse', async () => {
    render(<WorkflowsList {...mockProps} />);
    
    const toggleButton = screen.getByTitle('Collapse workflows list');
    await user.click(toggleButton);
    
    expect(mockProps.onToggleCollapse).toHaveBeenCalledTimes(1);
  });

  test('applies correct styling for collapsed and expanded states', () => {
    const { rerender } = render(<WorkflowsList {...mockProps} />);
    
    // When expanded - workflows should be visible
    expect(screen.getByText('Test Workflow 1.yml')).toBeInTheDocument();
    expect(screen.getByText('Test Workflow 2.yml')).toBeInTheDocument();
    
    // When collapsed - workflows should not be visible
    const collapsedProps = { ...mockProps, isCollapsed: true };
    rerender(<WorkflowsList {...collapsedProps} />);
    expect(screen.queryByText('Test Workflow 1')).not.toBeInTheDocument();
    expect(screen.queryByText('Test Workflow 2')).not.toBeInTheDocument();
  });

  test('workflow selection works when expanded', async () => {
    render(<WorkflowsList {...mockProps} />);
    
    const workflow = screen.getByText('Test Workflow 2.yml');
    await user.click(workflow);
    
    expect(mockProps.onSelectWorkflow).toHaveBeenCalledWith(1);
  });

  test('shows modified indicator for modified workflows', () => {
    render(<WorkflowsList {...mockProps} />);
    
    // Test Workflow 2 is marked as modified
    const modifiedIndicators = screen.getAllByTitle('Unsaved changes');
    expect(modifiedIndicators).toHaveLength(1);
  });

  test('shows empty state when no workflows', () => {
    const emptyProps = { ...mockProps, workflows: [] };
    render(<WorkflowsList {...emptyProps} />);
    
    expect(screen.getByText('No workflows created yet')).toBeInTheDocument();
    expect(screen.getByText('Click "Add Workflow" to create your first workflow')).toBeInTheDocument();
  });

  test('does not render workflows when collapsed', () => {
    const collapsedProps = { ...mockProps, isCollapsed: true };
    render(<WorkflowsList {...collapsedProps} />);
    
    // Workflows should not be visible when collapsed
    expect(screen.queryByText('Test Workflow 1')).not.toBeInTheDocument();
    expect(screen.queryByText('Test Workflow 2')).not.toBeInTheDocument();
  });

  test('toggle button functionality without onToggleCollapse callback', async () => {
    const propsWithoutCallback = { ...mockProps, onToggleCollapse: undefined };
    render(<WorkflowsList {...propsWithoutCallback} />);
    
    const toggleButton = screen.getByTitle('Collapse workflows list');
    
    // Should not throw error when clicking without callback
    await expect(user.click(toggleButton)).resolves.not.toThrow();
  });

  // Accessibility tests for keyboard navigation (SonarQube typescript:S6847 and typescript:S1082)
  describe('Accessibility - Keyboard Navigation', () => {
    test('workflow items are semantic buttons', () => {
      render(<WorkflowsList {...mockProps} />);
      
      // Should have workflow buttons - get all buttons and exclude the toggle button
      const allButtons = screen.getAllByRole('button');
      const toggleButton = screen.getByTitle('Collapse workflows list');
      
      const workflowButtons = allButtons.filter(btn => btn !== toggleButton);
      
      expect(workflowButtons).toHaveLength(2);
      
      // Semantic buttons have implicit role and are keyboard accessible
      workflowButtons.forEach(item => {
        expect(item.tagName).toBe('BUTTON');
      });
    });

    test('workflow selection works with Enter key', async () => {
      render(<WorkflowsList {...mockProps} />);
      
      const allButtons = screen.getAllByRole('button');
      const toggleButton = screen.getByTitle('Collapse workflows list');
      const workflowItems = allButtons.filter(btn => btn !== toggleButton);
      
      const secondWorkflow = workflowItems[1];
      secondWorkflow.focus();
      
      // Semantic button elements handle Enter key natively
      await user.keyboard('{Enter}');
      
      expect(mockProps.onSelectWorkflow).toHaveBeenCalledWith(1);
    });

    test('workflow selection works with Space key', async () => {
      render(<WorkflowsList {...mockProps} />);
      
      const allButtons = screen.getAllByRole('button');
      const toggleButton = screen.getByTitle('Collapse workflows list');
      const workflowItems = allButtons.filter(btn => btn !== toggleButton);
      
      const firstWorkflow = workflowItems[0];
      firstWorkflow.focus();
      
      // Semantic button elements handle Space key natively
      await user.keyboard(' ');
      
      expect(mockProps.onSelectWorkflow).toHaveBeenCalledWith(0);
    });

    test('other keys do not trigger workflow selection', async () => {
      render(<WorkflowsList {...mockProps} />);
      
      const allButtons = screen.getAllByRole('button');
      const toggleButton = screen.getByTitle('Collapse workflows list');
      const workflowItems = allButtons.filter(btn => btn !== toggleButton);
      
      const firstWorkflow = workflowItems[0];
      firstWorkflow.focus();
      
      // Try various keys that should not trigger selection
      await user.keyboard('{Escape}');
      await user.keyboard('a');
      await user.keyboard('{Tab}');
      
      expect(mockProps.onSelectWorkflow).not.toHaveBeenCalled();
    });

    test('workflow selection with Enter key works correctly', async () => {
      render(<WorkflowsList {...mockProps} />);
      
      const allButtons = screen.getAllByRole('button');
      const toggleButton = screen.getByTitle('Collapse workflows list');
      const workflowItems = allButtons.filter(btn => btn !== toggleButton);
      
      if (workflowItems.length > 0) {
        const firstWorkflow = workflowItems[0];
        firstWorkflow.focus();
        
        // Semantic button handles Enter key natively, no custom event handling needed
        await user.keyboard('{Enter}');
        
        expect(mockProps.onSelectWorkflow).toHaveBeenCalledWith(0);
      }
    });

    test('workflow selection with Space key works correctly', async () => {
      render(<WorkflowsList {...mockProps} />);
      
      const allButtons = screen.getAllByRole('button');
      const toggleButton = screen.getByTitle('Collapse workflows list');
      const workflowItems = allButtons.filter(btn => btn !== toggleButton);
      
      if (workflowItems.length > 0) {
        const firstWorkflow = workflowItems[0];
        firstWorkflow.focus();
        
        // Semantic button handles Space key natively, no custom event handling needed
        await user.keyboard(' ');
        
        expect(mockProps.onSelectWorkflow).toHaveBeenCalledWith(0);
      }
    });

    test('workflow items are keyboard focusable', () => {
      render(<WorkflowsList {...mockProps} />);
      
      const allButtons = screen.getAllByRole('button');
      const toggleButton = screen.getByTitle('Collapse workflows list');
      const workflowItems = allButtons.filter(btn => btn !== toggleButton);
      
      workflowItems.forEach(item => {
        // Semantic buttons are focusable by default (tabIndex defaults to 0)
        expect(item.tabIndex).toBe(0);
      });
    });
  });

});