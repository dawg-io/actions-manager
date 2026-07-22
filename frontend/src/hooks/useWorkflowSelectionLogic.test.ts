import { renderHook, act } from '@testing-library/react';
import { useWorkflowSelectionLogic } from './useWorkflowSelectionLogic';
import { WorkflowGUI, DEFAULT_WORKFLOW_GUI, DEFAULT_REUSABLE_WORKFLOW_GUI } from '../utils/workflowGuiConversion';
import { UnifiedWorkflowItem } from '../types/workflow';

// Mock the workflowGuiConversion module
vi.mock('../utils/workflowGuiConversion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/workflowGuiConversion')>();
  return {
    ...actual,
    yamlToGui: vi.fn(),
  };
});

import { yamlToGui } from '../utils/workflowGuiConversion';

describe('useWorkflowSelectionLogic', () => {
  const mockSetSelectedWorkflowId = jest.fn();
  const mockSetGuiWorkflow = jest.fn();
  const mockSetRegularGuiWorkflow = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    (yamlToGui as jest.Mock).mockImplementation((content: string) => ({
      ...DEFAULT_WORKFLOW_GUI,
      name: 'Parsed Workflow'
    }));
  });

  test('should initialize with correct props', () => {
    const unifiedWorkflows: UnifiedWorkflowItem[] = [];
    
    const { result } = renderHook(() =>
      useWorkflowSelectionLogic({
        unifiedWorkflows,
        setSelectedWorkflowId: mockSetSelectedWorkflowId,
        setGuiWorkflow: mockSetGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow
      })
    );

    expect(result.current.handleSelectWorkflow).toBeDefined();
    expect(typeof result.current.handleSelectWorkflow).toBe('function');
  });

  test('should handle selecting a regular workflow', () => {
    const unifiedWorkflows: UnifiedWorkflowItem[] = [
      {
        id: 'regular-0',
        name: 'Test Workflow',
        content: 'name: Test\non: push',
        isReusable: false,
        isModified: false,
        originalIndex: 0,
        type: 'regular'
      }
    ];

    const { result } = renderHook(() =>
      useWorkflowSelectionLogic({
        unifiedWorkflows,
        setSelectedWorkflowId: mockSetSelectedWorkflowId,
        setGuiWorkflow: mockSetGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow
      })
    );

    act(() => {
      result.current.handleSelectWorkflow('regular-0');
    });

    expect(mockSetSelectedWorkflowId).toHaveBeenCalledWith('regular-0');
    expect(yamlToGui).toHaveBeenCalledWith('name: Test\non: push');
    expect(mockSetRegularGuiWorkflow).toHaveBeenCalled();
  });

  test('should handle selecting a reusable workflow', () => {
    const mockGuiWorkflow: WorkflowGUI = {
      ...DEFAULT_REUSABLE_WORKFLOW_GUI,
      name: 'Reusable Workflow'
    };
    
    (yamlToGui as jest.Mock).mockReturnValue(mockGuiWorkflow);

    const unifiedWorkflows: UnifiedWorkflowItem[] = [
      {
        id: 'reusable-0',
        name: 'Reusable Workflow',
        content: 'name: Reusable\non:\n  workflow_call:',
        isReusable: true,
        isModified: false,
        originalIndex: 0,
        type: 'reusable'
      }
    ];

    const { result } = renderHook(() =>
      useWorkflowSelectionLogic({
        unifiedWorkflows,
        setSelectedWorkflowId: mockSetSelectedWorkflowId,
        setGuiWorkflow: mockSetGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow
      })
    );

    act(() => {
      result.current.handleSelectWorkflow('reusable-0');
    });

    expect(mockSetSelectedWorkflowId).toHaveBeenCalledWith('reusable-0');
    expect(mockSetGuiWorkflow).toHaveBeenCalled();
    expect(mockSetRegularGuiWorkflow).not.toHaveBeenCalled();
  });

  test('should handle selecting a workflow with empty content', () => {
    const unifiedWorkflows: UnifiedWorkflowItem[] = [
      {
        id: 'regular-1',
        name: 'Empty Workflow',
        content: '',
        isReusable: false,
        isModified: true,
        originalIndex: 1,
        type: 'regular'
      }
    ];

    const { result } = renderHook(() =>
      useWorkflowSelectionLogic({
        unifiedWorkflows,
        setSelectedWorkflowId: mockSetSelectedWorkflowId,
        setGuiWorkflow: mockSetGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow
      })
    );

    act(() => {
      result.current.handleSelectWorkflow('regular-1');
    });

    expect(mockSetSelectedWorkflowId).toHaveBeenCalledWith('regular-1');
    // Should preserve the workflow's name even if it's empty string
    expect(mockSetRegularGuiWorkflow).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Empty Workflow'
      })
    );
  });

  test('should handle selecting non-existent workflow', () => {
    const unifiedWorkflows: UnifiedWorkflowItem[] = [];

    const { result } = renderHook(() =>
      useWorkflowSelectionLogic({
        unifiedWorkflows,
        setSelectedWorkflowId: mockSetSelectedWorkflowId,
        setGuiWorkflow: mockSetGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow
      })
    );

    act(() => {
      result.current.handleSelectWorkflow('non-existent');
    });

    expect(mockSetSelectedWorkflowId).toHaveBeenCalledWith('non-existent');
    expect(mockSetRegularGuiWorkflow).toHaveBeenCalledWith(DEFAULT_WORKFLOW_GUI);
  });

  test('should handle YAML parsing errors gracefully', () => {
    (yamlToGui as jest.Mock).mockImplementation(() => {
      throw new Error('Parse error');
    });

    const unifiedWorkflows: UnifiedWorkflowItem[] = [
      {
        id: 'regular-0',
        name: 'Invalid YAML',
        content: 'invalid yaml content',
        isReusable: false,
        isModified: false,
        originalIndex: 0,
        type: 'regular'
      }
    ];

    const { result } = renderHook(() =>
      useWorkflowSelectionLogic({
        unifiedWorkflows,
        setSelectedWorkflowId: mockSetSelectedWorkflowId,
        setGuiWorkflow: mockSetGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow
      })
    );

    // Should not throw error but handle it gracefully
    act(() => {
      result.current.handleSelectWorkflow('regular-0');
    });

    expect(mockSetSelectedWorkflowId).toHaveBeenCalledWith('regular-0');
    // Should use the workflow's name even when parsing fails
    expect(mockSetRegularGuiWorkflow).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Invalid YAML'
      })
    );
  });

  test('should add workflow_call event if missing for reusable workflows', () => {
    const mockGuiWithoutWorkflowCall: WorkflowGUI = {
      name: 'Reusable Without Call',
      events: [{ type: 'push' }],
      jobs: []
    };
    
    (yamlToGui as jest.Mock).mockReturnValue(mockGuiWithoutWorkflowCall);

    const unifiedWorkflows: UnifiedWorkflowItem[] = [
      {
        id: 'reusable-0',
        name: 'Reusable Without Call',
        content: 'name: Test\non: push',
        isReusable: true,
        isModified: false,
        originalIndex: 0,
        type: 'reusable'
      }
    ];

    const { result } = renderHook(() =>
      useWorkflowSelectionLogic({
        unifiedWorkflows,
        setSelectedWorkflowId: mockSetSelectedWorkflowId,
        setGuiWorkflow: mockSetGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow
      })
    );

    act(() => {
      result.current.handleSelectWorkflow('reusable-0');
    });

    expect(mockSetGuiWorkflow).toHaveBeenCalledWith(
      expect.objectContaining({
        events: expect.arrayContaining([
          expect.objectContaining({ type: 'workflow_call' })
        ])
      })
    );
  });

  test('should preserve workflow name from unified workflow', () => {
    const unifiedWorkflows: UnifiedWorkflowItem[] = [
      {
        id: 'regular-0',
        name: 'Custom Name',
        content: 'name: Different Name\non: push',
        isReusable: false,
        isModified: false,
        originalIndex: 0,
        type: 'regular'
      }
    ];

    const { result } = renderHook(() =>
      useWorkflowSelectionLogic({
        unifiedWorkflows,
        setSelectedWorkflowId: mockSetSelectedWorkflowId,
        setGuiWorkflow: mockSetGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow
      })
    );

    act(() => {
      result.current.handleSelectWorkflow('regular-0');
    });

    // The name should be overridden from the unified workflow
    const callArgs = (mockSetRegularGuiWorkflow as jest.Mock).mock.calls[0][0];
    expect(callArgs.name).toBe('Custom Name');
  });

  test('should update when unifiedWorkflows prop changes', () => {
    const initialWorkflows: UnifiedWorkflowItem[] = [
      {
        id: 'regular-0',
        name: 'Workflow 1',
        content: 'name: Test 1',
        isReusable: false,
        isModified: false,
        originalIndex: 0,
        type: 'regular'
      }
    ];

    const { result, rerender } = renderHook(
      (props) => useWorkflowSelectionLogic(props),
      {
        initialProps: {
          unifiedWorkflows: initialWorkflows,
          setSelectedWorkflowId: mockSetSelectedWorkflowId,
          setGuiWorkflow: mockSetGuiWorkflow,
          setRegularGuiWorkflow: mockSetRegularGuiWorkflow
        }
      }
    );

    const updatedWorkflows: UnifiedWorkflowItem[] = [
      {
        id: 'regular-1',
        name: 'Workflow 2',
        content: 'name: Test 2',
        isReusable: false,
        isModified: false,
        originalIndex: 1,
        type: 'regular'
      }
    ];

    rerender({
      unifiedWorkflows: updatedWorkflows,
      setSelectedWorkflowId: mockSetSelectedWorkflowId,
      setGuiWorkflow: mockSetGuiWorkflow,
      setRegularGuiWorkflow: mockSetRegularGuiWorkflow
    });

    act(() => {
      result.current.handleSelectWorkflow('regular-1');
    });

    expect(mockSetSelectedWorkflowId).toHaveBeenCalledWith('regular-1');
  });

  test('should preserve empty workflow name for new blank workflows', () => {
    // This test ensures the fix for the name erasure bug
    // When a new blank workflow is created with empty name and content,
    // the GUI workflow should be initialized with the empty name, not 'CI'
    const unifiedWorkflows: UnifiedWorkflowItem[] = [
      {
        id: 'regular-0',
        name: '',
        content: '',
        isReusable: false,
        isModified: true,
        originalIndex: 0,
        type: 'regular'
      }
    ];

    const { result } = renderHook(() =>
      useWorkflowSelectionLogic({
        unifiedWorkflows,
        setSelectedWorkflowId: mockSetSelectedWorkflowId,
        setGuiWorkflow: mockSetGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow
      })
    );

    act(() => {
      result.current.handleSelectWorkflow('regular-0');
    });

    expect(mockSetSelectedWorkflowId).toHaveBeenCalledWith('regular-0');
    // Should use empty string, NOT default 'CI'
    expect(mockSetRegularGuiWorkflow).toHaveBeenCalledWith(
      expect.objectContaining({
        name: ''
      })
    );
  });
});
