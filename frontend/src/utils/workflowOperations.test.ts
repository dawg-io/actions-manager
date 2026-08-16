import { saveDraftWorkflow, saveDraftLinkedWorkflow, deleteWorkflow, createBlankWorkflow } from './workflowOperations';
import { saveWorkflows, deleteWorkflowFromGitHub, deleteWorkflowFromDatabase, deleteReusableWorkflowFromGitHub } from '../api/workflows';
import { saveRxWorkflows } from '../api/rxworkflows';
import { updateLinkedReusableWorkflow } from '../api/projects';
import { Workflow, RXWorkflow } from '../types/workflow';

// Mock the API modules
vi.mock('../api/workflows', () => ({
  saveWorkflows: vi.fn(),
  updateWorkflows: vi.fn(),
  deleteWorkflowFromGitHub: vi.fn(),
  deleteWorkflowFromDatabase: vi.fn(),
  deleteReusableWorkflowFromGitHub: vi.fn(),
}));
vi.mock('../api/rxworkflows', () => ({
  saveRxWorkflows: vi.fn(),
}));
vi.mock('../api/projects', () => ({
  updateLinkedReusableWorkflow: vi.fn(),
}));

// Mock the toast utility so we can assert toast messages without browser popups
vi.mock('./toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

import { toast } from './toast';

import type { Mock } from 'vitest';
describe('workflowOperations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('createBlankWorkflow', () => {
    test('should create blank regular workflow and select it', () => {
      const workflows: Workflow[] = [
        { name: 'existing', content: 'test', isReusable: false }
      ];
      const setWorkflows = vi.fn();
      const setRXWorkflows = vi.fn();
      const setSelectedWorkflowId = vi.fn();

      createBlankWorkflow('regular', 'new-workflow', workflows, setWorkflows, setRXWorkflows, setSelectedWorkflowId);

      expect(setWorkflows).toHaveBeenCalledWith([
        { name: 'existing', content: 'test', isReusable: false },
        { name: 'new-workflow', content: 'name: new-workflow\n\non:\n  workflow_dispatch:\n\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v6\n', isReusable: false, isModified: true }
      ]);
      expect(setSelectedWorkflowId).toHaveBeenCalledWith('regular-1');
      expect(setRXWorkflows).not.toHaveBeenCalled();
    });

    test('should create blank reusable workflow and select it', () => {
      const workflows: Workflow[] = [];
      const setWorkflows = vi.fn();
      const setRXWorkflows = vi.fn();
      const setSelectedWorkflowId = vi.fn();

      createBlankWorkflow('reusable', 'new-reusable', workflows, setWorkflows, setRXWorkflows, setSelectedWorkflowId);

      expect(setRXWorkflows).toHaveBeenCalledTimes(1);
      expect(setWorkflows).not.toHaveBeenCalled();
      
      // Extract the callback function and test it
      const callback = (setRXWorkflows as Mock).mock.calls[0][0];
      const result = callback([]);
      
      expect(result).toEqual([
        { name: 'new-reusable', content: 'name: new-reusable\n\non:\n  workflow_dispatch:\n\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v6\n', isReusable: true, isModified: true }
      ]);
    });

    test('should handle existing reusable workflows array', () => {
      const workflows: Workflow[] = [];
      const setWorkflows = vi.fn();
      const setRXWorkflows = vi.fn();
      const setSelectedWorkflowId = vi.fn();

      createBlankWorkflow('reusable', 'new-reusable', workflows, setWorkflows, setRXWorkflows, setSelectedWorkflowId);

      const callback = (setRXWorkflows as Mock).mock.calls[0][0];
      const result = callback([
        { name: 'existing', content: 'test', isReusable: true }
      ]);
      
      expect(result).toEqual([
        { name: 'existing', content: 'test', isReusable: true },
        { name: 'new-reusable', content: 'name: new-reusable\n\non:\n  workflow_dispatch:\n\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v6\n', isReusable: true, isModified: true }
      ]);
    });
  });

  describe('saveDraftWorkflow', () => {
    test('should not save if index is null', async () => {
      const workflows: Workflow[] = [];
      const rxworkflows: RXWorkflow[] = [];
      const user = 'testuser';
      const projectName = 'testproject';

      await saveDraftWorkflow(null, 'regular', workflows, rxworkflows, user, projectName);

      expect(saveWorkflows).not.toHaveBeenCalled();
      expect(saveRxWorkflows).not.toHaveBeenCalled();
    });

    test('should show error toast if workflow has no name', async () => {
      const workflows: Workflow[] = [
        { name: '', content: 'test content', isReusable: false }
      ];
      const rxworkflows: RXWorkflow[] = [];
      const user = 'testuser';
      const projectName = 'testproject';

      await saveDraftWorkflow(0, 'regular', workflows, rxworkflows, user, projectName);

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('provide both a workflow name and content')
      );
      expect(saveWorkflows).not.toHaveBeenCalled();
    });

    test('should show error toast if workflow has no content', async () => {
      const workflows: Workflow[] = [
        { name: 'test-workflow', content: '', isReusable: false }
      ];
      const rxworkflows: RXWorkflow[] = [];
      const user = 'testuser';
      const projectName = 'testproject';

      await saveDraftWorkflow(0, 'regular', workflows, rxworkflows, user, projectName);

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('provide both a workflow name and content')
      );
      expect(saveWorkflows).not.toHaveBeenCalled();
    });

    test('should save regular workflow draft without a confirm dialog', async () => {
      const workflows: Workflow[] = [
        { name: 'test-workflow', content: 'test content', isReusable: false }
      ];
      const rxworkflows: RXWorkflow[] = [];
      const user = 'testuser';
      const projectName = 'testproject';
      const markWorkflowAsSaved = vi.fn();

      (saveWorkflows as Mock).mockResolvedValue({ success: true });

      await saveDraftWorkflow(
        0, 'regular', workflows, rxworkflows, user, projectName, 
        undefined, markWorkflowAsSaved
      );

      // Backend stores workflow_name as a stem; .yml is appended by format_workflow_name server-side
      expect(saveWorkflows).toHaveBeenCalledWith(
        user, projectName, [{ ...workflows[0], name: 'test-workflow' }]
      );
      expect(markWorkflowAsSaved).toHaveBeenCalledWith(0, 'regular', 'new');
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining("saved as draft")
      );
    });

    test('success toast includes workflow filename with .yml suffix', async () => {
      const workflows: Workflow[] = [
        { name: 'my-workflow', content: 'test content', isReusable: false }
      ];
      const rxworkflows: RXWorkflow[] = [];

      (saveWorkflows as Mock).mockResolvedValue({ success: true });

      await saveDraftWorkflow(0, 'regular', workflows, rxworkflows, 'user', 'project');

      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining('my-workflow.yml')
      );
    });

    test('success toast is shown exactly once per save action', async () => {
      const workflows: Workflow[] = [
        { name: 'test-workflow', content: 'test content', isReusable: false }
      ];
      const rxworkflows: RXWorkflow[] = [];

      (saveWorkflows as Mock).mockResolvedValue({ success: true });

      await saveDraftWorkflow(0, 'regular', workflows, rxworkflows, 'testuser', 'testproject');

      expect(toast.success).toHaveBeenCalledTimes(1);
    });

    test('should save reusable workflow draft', async () => {
      const workflows: Workflow[] = [];
      const rxworkflows: RXWorkflow[] = [
        { name: 'rx-workflow', content: 'test content', isReusable: true }
      ];
      const user = 'testuser';
      const projectName = 'testproject';
      const markWorkflowAsSaved = vi.fn();

      (saveRxWorkflows as Mock).mockResolvedValue({ success: true });

      await saveDraftWorkflow(
        0, 'reusable', workflows, rxworkflows, user, projectName,
        undefined, markWorkflowAsSaved
      );

      // Backend stores workflow_name as a stem; .yml is appended by format_workflow_name server-side
      expect(saveRxWorkflows).toHaveBeenCalledWith(
        user, projectName, [{ ...rxworkflows[0], name: 'rx-workflow' }]
      );
      expect(markWorkflowAsSaved).toHaveBeenCalledWith(0, 'reusable', 'new');
    });

    test('should propagate pr_state to onProjectStateChange after regular workflow save', async () => {
      const workflows: Workflow[] = [
        { name: 'test-workflow', content: 'test content', isReusable: false }
      ];
      const rxworkflows: RXWorkflow[] = [];
      const onProjectStateChange = vi.fn();

      (saveWorkflows as Mock).mockResolvedValue({ success: true, pr_state: 'draft' });

      await saveDraftWorkflow(
        0, 'regular', workflows, rxworkflows, 'testuser', 'testproject',
        undefined, undefined, undefined, undefined, onProjectStateChange
      );

      expect(onProjectStateChange).toHaveBeenCalledWith('draft');
    });

    test('should propagate pr_state to onProjectStateChange after reusable workflow save', async () => {
      const workflows: Workflow[] = [];
      const rxworkflows: RXWorkflow[] = [
        { name: 'rx-workflow', content: 'test content', isReusable: true }
      ];
      const onProjectStateChange = vi.fn();

      (saveRxWorkflows as Mock).mockResolvedValue({ success: true, pr_state: 'draft' });

      await saveDraftWorkflow(
        0, 'reusable', workflows, rxworkflows, 'testuser', 'testproject',
        undefined, undefined, undefined, undefined, onProjectStateChange
      );

      expect(onProjectStateChange).toHaveBeenCalledWith('draft');
    });

    test('should not call onProjectStateChange when reusable workflow save fails', async () => {
      const workflows: Workflow[] = [];
      const rxworkflows: RXWorkflow[] = [
        { name: 'rx-workflow', content: 'test content', isReusable: true }
      ];
      const onProjectStateChange = vi.fn();
      const markWorkflowAsSaved = vi.fn();

      (saveRxWorkflows as Mock).mockRejectedValue(new Error('Network error'));

      await saveDraftWorkflow(
        0, 'reusable', workflows, rxworkflows, 'testuser', 'testproject',
        undefined, markWorkflowAsSaved, undefined, undefined, onProjectStateChange
      );

      expect(onProjectStateChange).not.toHaveBeenCalled();
      expect(markWorkflowAsSaved).not.toHaveBeenCalled();
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Failed to save workflow')
      );
    });

    test('should show error toast on save error', async () => {
      const workflows: Workflow[] = [
        { name: 'test-workflow', content: 'test content', isReusable: false }
      ];
      const rxworkflows: RXWorkflow[] = [];
      const user = 'testuser';
      const projectName = 'testproject';

      (saveWorkflows as Mock).mockRejectedValue(new Error('Network error'));

      await saveDraftWorkflow(0, 'regular', workflows, rxworkflows, user, projectName);

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Failed to save workflow')
      );
    });

    test('should fetch workflows count for free accounts', async () => {
      const workflows: Workflow[] = [
        { name: 'test-workflow', content: 'test content', isReusable: false }
      ];
      const rxworkflows: RXWorkflow[] = [];
      const user = 'testuser';
      const projectName = 'testproject';
      const fetchWorkflowsCount = vi.fn();

      (saveWorkflows as Mock).mockResolvedValue({ success: true });

      await saveDraftWorkflow(
        0, 'regular', workflows, rxworkflows, user, projectName,
        'free', undefined, fetchWorkflowsCount
      );

      expect(fetchWorkflowsCount).toHaveBeenCalled();
    });
  });

  describe('deleteWorkflow', () => {
    test('should delete regular workflow', async () => {
      const workflows: Workflow[] = [
        { name: 'test-workflow', content: 'test', isReusable: false }
      ];
      const rxworkflows: RXWorkflow[] = [];
      const setWorkflows = vi.fn();
      const setRXWorkflows = vi.fn();
      const setSelectedWorkflowId = vi.fn();

      (deleteWorkflowFromGitHub as Mock).mockResolvedValue({});
      (deleteWorkflowFromDatabase as Mock).mockResolvedValue({});

      await deleteWorkflow(
        0, 'regular', workflows, rxworkflows, 'user', 'project',
        ['owner/repo'], '', setWorkflows, setRXWorkflows, setSelectedWorkflowId
      );

      expect(deleteWorkflowFromGitHub).toHaveBeenCalledWith(
        'user', ['owner/repo'], 'test-workflow', '', 'project'
      );
      expect(deleteWorkflowFromDatabase).toHaveBeenCalledWith(
        'user', 'project', 'test-workflow'
      );
      expect(setWorkflows).toHaveBeenCalledWith([]);
      expect(setSelectedWorkflowId).toHaveBeenCalledWith(null);
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining('deleted successfully')
      );
    });

    test('should delete reusable workflow', async () => {
      const workflows: Workflow[] = [];
      const rxworkflows: RXWorkflow[] = [
        { name: 'rx-workflow', content: 'test', isReusable: true }
      ];
      const setWorkflows = vi.fn();
      const setRXWorkflows = vi.fn();
      const setSelectedWorkflowId = vi.fn();

      (deleteReusableWorkflowFromGitHub as Mock).mockResolvedValue({});
      (deleteWorkflowFromDatabase as Mock).mockResolvedValue({});

      await deleteWorkflow(
        0, 'reusable', workflows, rxworkflows, 'user', 'project',
        ['owner/repo'], '', setWorkflows, setRXWorkflows, setSelectedWorkflowId
      );

      expect(deleteReusableWorkflowFromGitHub).toHaveBeenCalledWith(
        'user', 'rx-workflow', 'project'
      );
      expect(deleteWorkflowFromDatabase).toHaveBeenCalledWith(
        'user', 'project', 'rx-workflow'
      );
      expect(setSelectedWorkflowId).toHaveBeenCalledWith(null);
    });

    test('should show toast error with authentication error', async () => {
      const workflows: Workflow[] = [
        { name: 'test-workflow', content: 'test', isReusable: false }
      ];
      const rxworkflows: RXWorkflow[] = [];
      const setWorkflows = vi.fn();
      const setRXWorkflows = vi.fn();
      const setSelectedWorkflowId = vi.fn();

      const error = {
        response: { status: 401, data: { detail: 'Unauthorized' } }
      };
      (deleteWorkflowFromGitHub as Mock).mockRejectedValue(error);

      // Mock localStorage
      const mockLocalStorage = {
        removeItem: vi.fn(),
        getItem: vi.fn(),
        setItem: vi.fn(),
        clear: vi.fn(),
        length: 0,
        key: vi.fn()
      };
      Object.defineProperty(globalThis, 'localStorage', {
        value: mockLocalStorage,
        writable: true
      });

      // Mock globalThis.location.reload
      delete (globalThis as any).location;
      (globalThis as any).location = { reload: vi.fn() };

      await deleteWorkflow(
        0, 'regular', workflows, rxworkflows, 'user', 'project',
        ['owner/repo'], '', setWorkflows, setRXWorkflows, setSelectedWorkflowId
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Authentication required')
      );
    });

    test('should show toast error with 404 status', async () => {
      const workflows: Workflow[] = [
        { name: 'test-workflow', content: 'test', isReusable: false }
      ];
      const rxworkflows: RXWorkflow[] = [];
      const setWorkflows = vi.fn();
      const setRXWorkflows = vi.fn();
      const setSelectedWorkflowId = vi.fn();

      const error = {
        response: { status: 404, data: { detail: 'Not found' } }
      };
      (deleteWorkflowFromGitHub as Mock).mockRejectedValue(error);

      await deleteWorkflow(
        0, 'regular', workflows, rxworkflows, 'user', 'project',
        ['owner/repo'], '', setWorkflows, setRXWorkflows, setSelectedWorkflowId
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Workflow or project not found')
      );
    });

    test('should return early if workflow does not exist', async () => {
      const workflows: Workflow[] = [];
      const rxworkflows: RXWorkflow[] = [];
      const setWorkflows = vi.fn();
      const setRXWorkflows = vi.fn();
      const setSelectedWorkflowId = vi.fn();

      await deleteWorkflow(
        0, 'regular', workflows, rxworkflows, 'user', 'project',
        ['owner/repo'], '', setWorkflows, setRXWorkflows, setSelectedWorkflowId
      );

      expect(deleteWorkflowFromGitHub).not.toHaveBeenCalled();
    });
  });

  describe('saveDraftLinkedWorkflow', () => {
    const linkedWorkflows = [
      { workflow_id: 1, workflow_name: 'my-linked-wf', workflow_yaml: 'name: my-linked-wf\n', rwx_project_id: 10, rwx_project_name: 'my-rwx-project' }
    ];
    const STD_PROJECT = 'my-std-project';

    test('should update linked workflow via dedicated endpoint (not via saveRxWorkflows)', async () => {
      (updateLinkedReusableWorkflow as Mock).mockResolvedValue({
        message: 'Reusable workflow updated in my-rwx-project.',
        workflow_id: 1,
        workflow_name: 'my-linked-wf',
        rwx_project_id: 10,
        rwx_project_name: 'my-rwx-project',
        workflow_status: 'committed_locally',
      });
      const setLinkedWorkflows = vi.fn();
      const refreshProjectsList = vi.fn().mockResolvedValue(undefined);

      await saveDraftLinkedWorkflow(0, linkedWorkflows, 'user', STD_PROJECT, setLinkedWorkflows, refreshProjectsList);

      // Must call the dedicated endpoint with the standard project name + workflow_id
      expect(updateLinkedReusableWorkflow).toHaveBeenCalledWith(
        'user', STD_PROJECT, 1, 'name: my-linked-wf\n'
      );
      // Must NOT route through saveRxWorkflows (which would create a duplicate)
      expect(saveRxWorkflows).not.toHaveBeenCalled();
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining('my-linked-wf')
      );
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining('my-rwx-project')
      );
      expect(refreshProjectsList).toHaveBeenCalled();
    });

    test('should clear isModified and set workflowStatus from response after successful save', async () => {
      (updateLinkedReusableWorkflow as Mock).mockResolvedValue({
        workflow_status: 'committed_locally',
      });
      const setLinkedWorkflows = vi.fn();

      await saveDraftLinkedWorkflow(0, linkedWorkflows, 'user', STD_PROJECT, setLinkedWorkflows);

      expect(setLinkedWorkflows).toHaveBeenCalledTimes(1);
      const updater = setLinkedWorkflows.mock.calls[0][0];
      const prev = [{ ...linkedWorkflows[0], isModified: true, workflowStatus: 'synced_with_github' }];
      const result = updater(prev);
      expect(result[0].isModified).toBe(false);
      expect(result[0].workflowStatus).toBe('committed_locally');
    });

    test('should set workflowStatus to under_review when backend signals open PR campaign lock', async () => {
      (updateLinkedReusableWorkflow as Mock).mockResolvedValue({
        workflow_status: 'under_review',
      });
      const setLinkedWorkflows = vi.fn();

      await saveDraftLinkedWorkflow(0, linkedWorkflows, 'user', STD_PROJECT, setLinkedWorkflows);

      const updater = setLinkedWorkflows.mock.calls[0][0];
      const prev = [{ ...linkedWorkflows[0], isModified: true, workflowStatus: 'synced_with_github' }];
      const result = updater(prev);
      expect(result[0].isModified).toBe(false);
      expect(result[0].workflowStatus).toBe('under_review');
    });

    test('should fall back to committed_locally when API response omits workflow_status', async () => {
      (updateLinkedReusableWorkflow as Mock).mockResolvedValue({});
      const setLinkedWorkflows = vi.fn();

      await saveDraftLinkedWorkflow(0, linkedWorkflows, 'user', STD_PROJECT, setLinkedWorkflows);

      expect(setLinkedWorkflows).toHaveBeenCalledTimes(1);
      const updater = setLinkedWorkflows.mock.calls[0][0];
      const prev = [{ ...linkedWorkflows[0], isModified: true, workflowStatus: 'synced_with_github' }];
      const result = updater(prev);
      expect(result[0].isModified).toBe(false);
      expect(result[0].workflowStatus).toBe('committed_locally');
    });

    test('should not clear isModified if setLinkedWorkflows is not provided', async () => {
      (updateLinkedReusableWorkflow as Mock).mockResolvedValue({});
      await expect(
        saveDraftLinkedWorkflow(0, linkedWorkflows, 'user', STD_PROJECT)
      ).resolves.toBeUndefined();
    });

    test('should show error toast when linked workflow data is incomplete', async () => {
      const incompleteWorkflows = [{ workflow_id: 2, workflow_name: '', workflow_yaml: '', rwx_project_id: 10, rwx_project_name: 'rwx' }];

      await saveDraftLinkedWorkflow(0, incompleteWorkflows, 'user', STD_PROJECT);

      expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('incomplete'));
      expect(updateLinkedReusableWorkflow).not.toHaveBeenCalled();
    });

    test('should show a clear error (not create a duplicate) when source link is not found', async () => {
      const err: any = new Error('not found');
      err.response = { status: 404, data: { detail: 'Linked reusable workflow not found for this project' } };
      (updateLinkedReusableWorkflow as Mock).mockRejectedValue(err);
      const setLinkedWorkflows = vi.fn();

      await saveDraftLinkedWorkflow(0, linkedWorkflows, 'user', STD_PROJECT, setLinkedWorkflows);

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Could not find the source reusable workflow')
      );
      expect(saveRxWorkflows).not.toHaveBeenCalled();
      expect(setLinkedWorkflows).not.toHaveBeenCalled();
    });

    test('should handle save failure and not clear isModified', async () => {
      (updateLinkedReusableWorkflow as Mock).mockRejectedValue(new Error('Network error'));
      const setLinkedWorkflows = vi.fn();

      await saveDraftLinkedWorkflow(0, linkedWorkflows, 'user', STD_PROJECT, setLinkedWorkflows);

      expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('Failed to update'));
      expect(setLinkedWorkflows).not.toHaveBeenCalled();
    });
  });
});
