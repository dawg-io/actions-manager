import { handleWorkflowChange } from './workflowOperations';
import { Workflow, RXWorkflow, UnifiedWorkflowItem } from '../types/workflow';
import { WorkflowGUI, DEFAULT_WORKFLOW_GUI, DEFAULT_REUSABLE_WORKFLOW_GUI } from './workflowGuiConversion';

describe('workflowChangeHandlers', () => {
  describe('handleWorkflowChange', () => {
    let mockWorkflows: Workflow[];
    let mockRXWorkflows: RXWorkflow[];
    let mockSetWorkflows: jest.Mock;
    let mockSetRXWorkflows: jest.Mock;
    let mockSetRegularGuiWorkflow: jest.Mock;
    let mockSetGuiWorkflow: jest.Mock;
    let mockMarkWorkflowAsModified: jest.Mock;
    let mockRegularGuiWorkflow: WorkflowGUI;
    let mockGuiWorkflow: WorkflowGUI;

    beforeEach(() => {
      mockWorkflows = [
        { name: 'test-workflow', content: 'name: test\non: [push]', isModified: false, isReusable: false }
      ];
      mockRXWorkflows = [
        { name: 'reusable-workflow', content: 'name: reusable\non: [workflow_call]', isModified: false, isReusable: true }
      ];
      // Mock setWorkflows to execute the functional updater (like React's useState)
      mockSetWorkflows = jest.fn((updater) => {
        if (typeof updater === 'function') {
          updater(mockWorkflows);
        }
      });
      mockSetRXWorkflows = jest.fn();
      mockSetRegularGuiWorkflow = jest.fn();
      mockSetGuiWorkflow = jest.fn();
      mockMarkWorkflowAsModified = jest.fn();
      mockRegularGuiWorkflow = { ...DEFAULT_WORKFLOW_GUI, name: 'test' };
      mockGuiWorkflow = { ...DEFAULT_REUSABLE_WORKFLOW_GUI, name: 'reusable' };
    });

    test('updates regular workflow name in YAML mode using functional updater', () => {
      const selectedWorkflow: UnifiedWorkflowItem = {
        id: 'regular-0',
        name: 'test-workflow',
        content: 'name: test\non: [push]',
        type: 'regular',
        isReusable: false,
        originalIndex: 0,
        isModified: false
      };

      handleWorkflowChange({
        field: 'name',
        value: 'new-name',
        selectedWorkflow,
        workflows: mockWorkflows,
        setWorkflows: mockSetWorkflows,
        setRXWorkflows: mockSetRXWorkflows,
        editMode: 'yaml',
        regularGuiWorkflow: mockRegularGuiWorkflow,
        guiWorkflow: mockGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow,
        setGuiWorkflow: mockSetGuiWorkflow,
        markWorkflowAsModified: mockMarkWorkflowAsModified,
      });

      // setWorkflows should be called with a functional updater
      expect(mockSetWorkflows).toHaveBeenCalledWith(expect.any(Function));
      // Execute the updater to verify the result
      const updater = mockSetWorkflows.mock.calls[0][0];
      const result = updater(mockWorkflows);
      expect(result[0].name).toBe('new-name');
      expect(result[0].isModified).toBe(true);
      // In YAML mode, GUI name should also be updated
      expect(mockSetRegularGuiWorkflow).toHaveBeenCalledWith({
        ...mockRegularGuiWorkflow,
        name: 'new-name'
      });
      expect(mockMarkWorkflowAsModified).toHaveBeenCalledWith(0, 'regular');
    });

    test('does NOT update GUI state when name changes in GUI mode (avoids redundant updates)', () => {
      const selectedWorkflow: UnifiedWorkflowItem = {
        id: 'regular-0',
        name: 'test-workflow',
        content: 'name: test\non: [push]',
        type: 'regular',
        isReusable: false,
        originalIndex: 0,
        isModified: false
      };

      handleWorkflowChange({
        field: 'name',
        value: 'new-name',
        selectedWorkflow,
        workflows: mockWorkflows,
        setWorkflows: mockSetWorkflows,
        setRXWorkflows: mockSetRXWorkflows,
        editMode: 'gui',
        regularGuiWorkflow: mockRegularGuiWorkflow,
        guiWorkflow: mockGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow,
        setGuiWorkflow: mockSetGuiWorkflow,
        markWorkflowAsModified: mockMarkWorkflowAsModified,
      });

      // setWorkflows should be called with a functional updater
      expect(mockSetWorkflows).toHaveBeenCalledWith(expect.any(Function));
      const updater = mockSetWorkflows.mock.calls[0][0];
      const result = updater(mockWorkflows);
      expect(result[0].name).toBe('new-name');
      // In GUI mode, we should NOT update the GUI workflow name here
      expect(mockSetRegularGuiWorkflow).not.toHaveBeenCalled();
      expect(mockMarkWorkflowAsModified).toHaveBeenCalledWith(0, 'regular');
    });

    test('functional updater preserves other fields when updating content', () => {
      // This is the key test for the stale closure fix.
      // Simulate a stale closure scenario: the workflows array passed to
      // handleWorkflowChange has name: '' (stale), but the actual current
      // state has name: 'MyWorkflow'. The functional updater should read
      // from the actual current state (prev), not the stale closure.
      const selectedWorkflow: UnifiedWorkflowItem = {
        id: 'regular-0',
        name: '',  // stale name from old closure
        content: '',
        type: 'regular',
        isReusable: false,
        originalIndex: 0,
        isModified: false
      };

      const staleWorkflows: Workflow[] = [
        { name: '', content: '', isModified: false, isReusable: false }
      ];

      const currentWorkflows: Workflow[] = [
        { name: 'MyWorkflow', content: '', isModified: true, isReusable: false }
      ];

      handleWorkflowChange({
        field: 'content',
        value: 'name: CI\non: [push]',
        selectedWorkflow,
        workflows: staleWorkflows,  // stale closure value
        setWorkflows: mockSetWorkflows,
        setRXWorkflows: mockSetRXWorkflows,
        editMode: 'yaml',
        regularGuiWorkflow: mockRegularGuiWorkflow,
        guiWorkflow: mockGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow,
        setGuiWorkflow: mockSetGuiWorkflow,
        markWorkflowAsModified: mockMarkWorkflowAsModified,
      });

      expect(mockSetWorkflows).toHaveBeenCalledWith(expect.any(Function));
      const updater = mockSetWorkflows.mock.calls[0][0];

      // When the updater runs with the CURRENT state, it should
      // preserve 'MyWorkflow' name and only update the content
      const result = updater(currentWorkflows);
      expect(result[0].name).toBe('MyWorkflow');  // preserved from current state!
      expect(result[0].content).toBe('name: CI\non: [push]');  // updated
      expect(result[0].isModified).toBe(true);
    });

    test('does NOT re-parse content when in GUI mode for regular workflows', () => {
      const selectedWorkflow: UnifiedWorkflowItem = {
        id: 'regular-0',
        name: 'test-workflow',
        content: '',
        type: 'regular',
        isReusable: false,
        originalIndex: 0,
        isModified: false
      };

      handleWorkflowChange({
        field: 'content',
        value: 'name: CI\non: [push]\njobs:\n  build:\n    runs-on: ubuntu-latest',
        selectedWorkflow,
        workflows: mockWorkflows,
        setWorkflows: mockSetWorkflows,
        setRXWorkflows: mockSetRXWorkflows,
        editMode: 'gui',
        regularGuiWorkflow: mockRegularGuiWorkflow,
        guiWorkflow: mockGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow,
        setGuiWorkflow: mockSetGuiWorkflow,
        markWorkflowAsModified: mockMarkWorkflowAsModified,
      });

      // Should update workflow content via functional updater
      expect(mockSetWorkflows).toHaveBeenCalledWith(expect.any(Function));

      // Should NOT re-parse and overwrite GUI state
      expect(mockSetRegularGuiWorkflow).not.toHaveBeenCalled();
    });

    test('does NOT re-parse content when in GUI mode for reusable workflows', () => {
      const selectedWorkflow: UnifiedWorkflowItem = {
        id: 'reusable-0',
        name: 'reusable-workflow',
        content: '',
        type: 'reusable',
        isReusable: true,
        originalIndex: 0,
        isModified: false
      };

      handleWorkflowChange({
        field: 'content',
        value: 'name: Reusable\non: [workflow_call]',
        selectedWorkflow,
        workflows: mockWorkflows,
        setWorkflows: mockSetWorkflows,
        setRXWorkflows: mockSetRXWorkflows,
        editMode: 'gui',
        regularGuiWorkflow: mockRegularGuiWorkflow,
        guiWorkflow: mockGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow,
        setGuiWorkflow: mockSetGuiWorkflow,
        markWorkflowAsModified: mockMarkWorkflowAsModified,
      });

      // Should update workflow content
      expect(mockSetRXWorkflows).toHaveBeenCalled();

      // Should NOT re-parse and overwrite GUI state
      expect(mockSetGuiWorkflow).not.toHaveBeenCalled();
    });

    test('updates reusable workflow name and syncs GUI state', () => {
      const selectedWorkflow: UnifiedWorkflowItem = {
        id: 'reusable-0',
        name: 'reusable-workflow',
        content: 'name: reusable\non: [workflow_call]',
        type: 'reusable',
        isReusable: true,
        originalIndex: 0,
        isModified: false
      };

      // Mock setRXWorkflows to execute the callback function
      const mockSetRXWorkflowsWithCallback = jest.fn((callback) => {
        if (typeof callback === 'function') {
          callback(mockRXWorkflows);
        }
      });

      handleWorkflowChange({
        field: 'name',
        value: 'new-reusable-name',
        selectedWorkflow,
        workflows: mockWorkflows,
        setWorkflows: mockSetWorkflows,
        setRXWorkflows: mockSetRXWorkflowsWithCallback,
        editMode: 'yaml',
        regularGuiWorkflow: mockRegularGuiWorkflow,
        guiWorkflow: mockGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow,
        setGuiWorkflow: mockSetGuiWorkflow,
        markWorkflowAsModified: mockMarkWorkflowAsModified,
      });

      expect(mockSetRXWorkflowsWithCallback).toHaveBeenCalled();
      expect(mockSetGuiWorkflow).toHaveBeenCalledWith({
        ...mockGuiWorkflow,
        name: 'new-reusable-name'
      });
      expect(mockMarkWorkflowAsModified).toHaveBeenCalledWith(0, 'reusable');
    });

    test('does NOT update GUI state when reusable workflow name changes in GUI mode (avoids redundant updates)', () => {
      const selectedWorkflow: UnifiedWorkflowItem = {
        id: 'reusable-0',
        name: 'reusable-workflow',
        content: 'name: reusable\non: [workflow_call]',
        type: 'reusable',
        isReusable: true,
        originalIndex: 0,
        isModified: false
      };

      // Mock setRXWorkflows to execute the callback function
      const mockSetRXWorkflowsWithCallback = jest.fn((callback) => {
        if (typeof callback === 'function') {
          callback(mockRXWorkflows);
        }
      });

      handleWorkflowChange({
        field: 'name',
        value: 'new-reusable-name',
        selectedWorkflow,
        workflows: mockWorkflows,
        setWorkflows: mockSetWorkflows,
        setRXWorkflows: mockSetRXWorkflowsWithCallback,
        editMode: 'gui',
        regularGuiWorkflow: mockRegularGuiWorkflow,
        guiWorkflow: mockGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow,
        setGuiWorkflow: mockSetGuiWorkflow,
        markWorkflowAsModified: mockMarkWorkflowAsModified,
      });

      expect(mockSetRXWorkflowsWithCallback).toHaveBeenCalled();
      // In GUI mode, we should NOT update the GUI workflow name here
      expect(mockSetGuiWorkflow).not.toHaveBeenCalled();
      expect(mockMarkWorkflowAsModified).toHaveBeenCalledWith(0, 'reusable');
    });

    test('does nothing when selectedWorkflow is undefined', () => {
      handleWorkflowChange({
        field: 'name',
        value: 'new-name',
        selectedWorkflow: undefined,
        workflows: mockWorkflows,
        setWorkflows: mockSetWorkflows,
        setRXWorkflows: mockSetRXWorkflows,
        editMode: 'yaml',
        regularGuiWorkflow: mockRegularGuiWorkflow,
        guiWorkflow: mockGuiWorkflow,
        setRegularGuiWorkflow: mockSetRegularGuiWorkflow,
        setGuiWorkflow: mockSetGuiWorkflow,
        markWorkflowAsModified: mockMarkWorkflowAsModified,
      });

      expect(mockSetWorkflows).not.toHaveBeenCalled();
      expect(mockSetRXWorkflows).not.toHaveBeenCalled();
      expect(mockSetRegularGuiWorkflow).not.toHaveBeenCalled();
      expect(mockSetGuiWorkflow).not.toHaveBeenCalled();
      expect(mockMarkWorkflowAsModified).not.toHaveBeenCalled();
    });
  });
});
