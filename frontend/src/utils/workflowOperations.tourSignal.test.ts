import { saveDraftWorkflow } from './workflowOperations';
import { tour } from './tour';
import { saveWorkflows } from '../api/workflows';

vi.mock('../api/workflows', () => ({
  saveWorkflows: vi.fn(),
  updateWorkflows: vi.fn(),
  deleteWorkflowFromGitHub: vi.fn(),
  deleteWorkflowFromDatabase: vi.fn(),
  deleteReusableWorkflowFromGitHub: vi.fn(),
}));
vi.mock('../api/rxworkflows', () => ({ saveRxWorkflows: vi.fn() }));
vi.mock('../api/projects', () => ({ updateLinkedReusableWorkflow: vi.fn() }));
vi.mock('./toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const workflow = {
  name: 'demo-workflow',
  content: 'name: demo\non: push\n',
  workflowStatus: 'new',
} as never;

describe('saveDraftWorkflow — guided tour signal', () => {
  test('reports commit-workflow when the draft really saved', async () => {
    // The editor's "Commit Locally" routes here, not through ProjectMgmt's
    // toolbar save. The signal lived on that other path and never fired.
    vi.mocked(saveWorkflows).mockResolvedValue({ pr_state: 'draft' } as never);
    const completed = vi.spyOn(tour, 'completed');

    await saveDraftWorkflow(0, 'regular', [workflow], [], 'testuser', 'Demo-Project');

    expect(completed).toHaveBeenCalledWith('commit-workflow');
    completed.mockRestore();
  });

  test('does not report the step when the save failed', async () => {
    vi.mocked(saveWorkflows).mockRejectedValue(new Error('boom'));
    const completed = vi.spyOn(tour, 'completed');

    await saveDraftWorkflow(0, 'regular', [workflow], [], 'testuser', 'Demo-Project');

    expect(completed).not.toHaveBeenCalled();
    completed.mockRestore();
  });
});
