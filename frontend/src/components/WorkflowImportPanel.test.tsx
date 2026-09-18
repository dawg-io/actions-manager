/**
 * Tests for WorkflowImportPanel component and derived status labels.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { WorkflowImportPanel } from './WorkflowImportPanel';
import { deriveWorkflowStatusLabel } from '../utils/workflowImportStatus';
import { discoverWorkflows, previewWorkflow, importWorkflows } from '../api/workflowImport';
import { fetchProjects } from '../api/projects';

// Mock the API module
vi.mock('../api/workflowImport', () => ({
  discoverWorkflows: vi.fn(),
  previewWorkflow: vi.fn(),
  importWorkflows: vi.fn(),
}));

// The panel looks up Reusable Workflow Projects to offer as destinations.
vi.mock('../api/projects', () => ({
  fetchProjects: vi.fn(),
}));

describe('WorkflowImportPanel', () => {
  const defaultProps = {
    projectId: 1,
    projectName: 'TestProject',
    githubUser: 'testuser',
    onImportComplete: vi.fn(),
    onClose: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('auto-scans on mount and shows scanning state', () => {
    vi.mocked(discoverWorkflows).mockReturnValue(new Promise(() => {})); // never resolves
    render(<WorkflowImportPanel {...defaultProps} />);
    expect(screen.getByTestId('import-scanning')).toBeInTheDocument();
    expect(discoverWorkflows).toHaveBeenCalledWith(1, 'testuser', 'TestProject');
  });

  it('renders as a modal overlay', () => {
    vi.mocked(discoverWorkflows).mockReturnValue(new Promise(() => {}));
    render(<WorkflowImportPanel {...defaultProps} />);
    expect(screen.getByTestId('workflow-import-modal')).toBeInTheDocument();
  });

  it('shows empty state when no workflows found', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue({
      repositories_scanned: 1,
      workflows_found: 0,
      results: [
        {
          repo_name: 'owner/repo1',
          branch: 'main',
          workflows: [],
          warning: 'No workflow files found in .github/workflows/',
          error: null,
        },
      ],
      cross_repo_matches: [],
    });

    render(<WorkflowImportPanel {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  it('only renders unmanaged workflows returned by discovery and Select All counts importable workflows', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue({
      repositories_scanned: 1,
      workflows_found: 1,
      results: [
        {
          repo_name: 'owner/repo1',
          branch: 'main',
          workflows: [
            { repo_name: 'owner/repo1', branch: 'main', file_name: 'deploy.yaml', path: '.github/workflows/deploy.yaml', blob_sha: 'def4567890123' },
          ],
          warning: null,
          error: null,
        },
      ],
      cross_repo_matches: [],
    });

    render(<WorkflowImportPanel {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId('workflow-list')).toBeInTheDocument();
    });

    expect(screen.getByText('deploy.yaml')).toBeInTheDocument();
    expect(screen.queryByText('newrf1.yml')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Select All (1)')).toBeInTheDocument();
  });

  it('shows the already-managed empty state when discovery returns no importable workflows', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue({
      repositories_scanned: 1,
      workflows_found: 0,
      results: [
        {
          repo_name: 'owner/repo1',
          branch: 'main',
          workflows: [],
          warning: 'All discovered workflows are already managed by this project.',
          error: null,
        },
      ],
      cross_repo_matches: [],
    });

    render(<WorkflowImportPanel {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });

    expect(
      screen.getByText('All discovered workflows are already managed by this project.')
    ).toBeInTheDocument();
  });

  it('shows discovered workflows with checkboxes, repo, branch, SHA', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue({
      repositories_scanned: 1,
      workflows_found: 2,
      results: [
        {
          repo_name: 'owner/repo1',
          branch: 'main',
          workflows: [
            { repo_name: 'owner/repo1', branch: 'main', file_name: 'ci.yml', path: '.github/workflows/ci.yml', blob_sha: 'abc1234567890' },
            { repo_name: 'owner/repo1', branch: 'main', file_name: 'deploy.yaml', path: '.github/workflows/deploy.yaml', blob_sha: 'def4567890123' },
          ],
          warning: null,
          error: null,
        },
      ],
      cross_repo_matches: [],
    });

    render(<WorkflowImportPanel {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId('workflow-list')).toBeInTheDocument();
    });

    expect(screen.getByText('ci.yml')).toBeInTheDocument();
    expect(screen.getByText('deploy.yaml')).toBeInTheDocument();
    expect(screen.getAllByText('owner/repo1').length).toBeGreaterThan(0);
    expect(screen.getByText('abc1234')).toBeInTheDocument();
  });

  it('shows cross-repo indicators per workflow row', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue({
      repositories_scanned: 2,
      workflows_found: 2,
      results: [
        {
          repo_name: 'owner/repo1',
          branch: 'main',
          workflows: [
            { repo_name: 'owner/repo1', branch: 'main', file_name: 'ci.yml', path: '.github/workflows/ci.yml', blob_sha: 'aaa' },
          ],
          warning: null,
          error: null,
        },
        {
          repo_name: 'owner/repo2',
          branch: 'main',
          workflows: [
            { repo_name: 'owner/repo2', branch: 'main', file_name: 'ci.yml', path: '.github/workflows/ci.yml', blob_sha: 'bbb' },
          ],
          warning: null,
          error: null,
        },
      ],
      cross_repo_matches: [
        { file_name: 'ci.yml', path: '.github/workflows/ci.yml', repos: [{ repo_name: 'owner/repo1', branch: 'main', blob_sha: 'aaa' }, { repo_name: 'owner/repo2', branch: 'main', blob_sha: 'bbb' }], identical_across_repos: false },
      ],
    });

    render(<WorkflowImportPanel {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId('workflow-list')).toBeInTheDocument();
    });

    // Should show cross-repo indicator with "differs"
    const differsIndicators = screen.getAllByText(/repos.*differs/);
    expect(differsIndicators.length).toBeGreaterThan(0);
  });

  it('uses unique preview test ids when duplicate filenames exist across repos', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue({
      repositories_scanned: 2,
      workflows_found: 2,
      results: [
        {
          repo_name: 'owner/repo1',
          branch: 'main',
          workflows: [
            { repo_name: 'owner/repo1', branch: 'main', file_name: 'ci.yml', path: '.github/workflows/ci.yml', blob_sha: 'aaa' },
          ],
          warning: null,
          error: null,
        },
        {
          repo_name: 'owner/repo2',
          branch: 'main',
          workflows: [
            { repo_name: 'owner/repo2', branch: 'main', file_name: 'ci.yml', path: '.github/workflows/ci.yml', blob_sha: 'bbb' },
          ],
          warning: null,
          error: null,
        },
      ],
      cross_repo_matches: [],
    });

    render(<WorkflowImportPanel {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId('workflow-list')).toBeInTheDocument();
    });

    const previewButtons = screen.getAllByRole('button', { name: 'Preview' });
    const testIds = previewButtons.map((button) => button.dataset.testid);
    expect(new Set(testIds).size).toBe(2);
  });

  it('clears preview error when a later preview succeeds', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue({
      repositories_scanned: 1,
      workflows_found: 1,
      results: [
        {
          repo_name: 'owner/repo1',
          branch: 'main',
          workflows: [
            { repo_name: 'owner/repo1', branch: 'main', file_name: 'ci.yml', path: '.github/workflows/ci.yml', blob_sha: 'abc' },
          ],
          warning: null,
          error: null,
        },
      ],
      cross_repo_matches: [],
    });
    vi.mocked(previewWorkflow)
      .mockRejectedValueOnce(new Error('Preview failed'))
      .mockResolvedValueOnce({
        repo_name: 'owner/repo1',
        branch: 'main',
        path: '.github/workflows/ci.yml',
        file_name: 'ci.yml',
        content: 'name: CI',
        blob_sha: 'abc',
      });

    render(<WorkflowImportPanel {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId('workflow-list')).toBeInTheDocument();
    });

    const previewButton = screen.getByRole('button', { name: 'Preview' });
    fireEvent.click(previewButton);
    await waitFor(() => expect(screen.getByTestId('import-error')).toBeInTheDocument());

    fireEvent.click(previewButton);
    await waitFor(() => expect(screen.getByTestId('preview-panel')).toBeInTheDocument());
    expect(screen.queryByTestId('import-error')).not.toBeInTheDocument();
  });

  it('disables import buttons while importing', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue({
      repositories_scanned: 1,
      workflows_found: 1,
      results: [
        {
          repo_name: 'owner/repo1',
          branch: 'main',
          workflows: [
            { repo_name: 'owner/repo1', branch: 'main', file_name: 'ci.yml', path: '.github/workflows/ci.yml', blob_sha: 'abc' },
          ],
          warning: null,
          error: null,
        },
      ],
      cross_repo_matches: [],
    });

    // Make import take a while
    vi.mocked(importWorkflows).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve({ message: 'Done', import_mode: 'save_local_only', results: [], pr_state: 'draft', pr_results: null }), 100))
    );

    render(<WorkflowImportPanel {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId('workflow-list')).toBeInTheDocument();
    });

    // Select the workflow
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]); // first workflow checkbox (index 0 is select all)

    await waitFor(() => {
      expect(screen.getByTestId('save-local-button')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('save-local-button'));

    // Button should be disabled during import
    expect(screen.getByTestId('save-local-button')).toBeDisabled();
  });

  it('shows success message after import', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue({
      repositories_scanned: 1,
      workflows_found: 1,
      results: [
        {
          repo_name: 'owner/repo1',
          branch: 'main',
          workflows: [
            { repo_name: 'owner/repo1', branch: 'main', file_name: 'ci.yml', path: '.github/workflows/ci.yml', blob_sha: 'abc' },
          ],
          warning: null,
          error: null,
        },
      ],
      cross_repo_matches: [],
    });

    vi.mocked(importWorkflows).mockResolvedValue({
      message: 'Imported 1 workflow(s) locally.',
      import_mode: 'save_local_only',
      results: [{ workflow_path: '.github/workflows/ci.yml', source_repo: 'owner/repo1', status: 'success', message: 'ok' }],
      pr_state: 'draft',
      pr_results: null,
    });

    render(<WorkflowImportPanel {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId('workflow-list')).toBeInTheDocument();
    });

    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]);

    await waitFor(() => {
      expect(screen.getByTestId('save-local-button')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('save-local-button'));

    await waitFor(() => {
      expect(screen.getByTestId('import-success')).toBeInTheDocument();
    });

    expect(defaultProps.onImportComplete).toHaveBeenCalledWith('draft');
  });

  it('shows an error when PR campaign creation returns an explicit error payload', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue({
      repositories_scanned: 1,
      workflows_found: 1,
      results: [
        {
          repo_name: 'owner/repo1',
          branch: 'main',
          workflows: [
            { repo_name: 'owner/repo1', branch: 'main', file_name: 'ci.yml', path: '.github/workflows/ci.yml', blob_sha: 'abc' },
          ],
          warning: null,
          error: null,
        },
      ],
      cross_repo_matches: [],
    });

    vi.mocked(importWorkflows).mockResolvedValue({
      message: 'Imported 1 workflow(s) and created PR Campaign.',
      import_mode: 'save_and_create_pr_campaign',
      results: [{ workflow_path: '.github/workflows/ci.yml', source_repo: 'owner/repo1', status: 'success', message: 'ok' }],
      pr_state: 'draft',
      pr_results: { error: 'PR creation failed upstream' },
    });

    render(<WorkflowImportPanel {...defaultProps} selectedRepos={['owner/repo1']} />);

    await waitFor(() => {
      expect(screen.getByTestId('workflow-list')).toBeInTheDocument();
    });

    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]);
    fireEvent.click(screen.getByTestId('save-and-pr-button'));

    await waitFor(() => {
      expect(screen.getByTestId('import-error')).toBeInTheDocument();
    });

    expect(screen.queryByTestId('import-success')).not.toBeInTheDocument();
  });

  it('shows an error when PR campaign creation reports zero PRs created', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue({
      repositories_scanned: 1,
      workflows_found: 1,
      results: [
        {
          repo_name: 'owner/repo1',
          branch: 'main',
          workflows: [
            { repo_name: 'owner/repo1', branch: 'main', file_name: 'ci.yml', path: '.github/workflows/ci.yml', blob_sha: 'abc' },
          ],
          warning: null,
          error: null,
        },
      ],
      cross_repo_matches: [],
    });

    vi.mocked(importWorkflows).mockResolvedValue({
      message: 'Imported 1 workflow(s) and created PR Campaign.',
      import_mode: 'save_and_create_pr_campaign',
      results: [{ workflow_path: '.github/workflows/ci.yml', source_repo: 'owner/repo1', status: 'success', message: 'ok' }],
      pr_state: 'draft',
      pr_results: { prs_created: 0 },
    });

    render(<WorkflowImportPanel {...defaultProps} selectedRepos={['owner/repo1']} />);

    await waitFor(() => {
      expect(screen.getByTestId('workflow-list')).toBeInTheDocument();
    });

    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]);
    fireEvent.click(screen.getByTestId('save-and-pr-button'));

    await waitFor(() => {
      expect(screen.getByTestId('import-error')).toBeInTheDocument();
    });

    expect(screen.queryByTestId('import-success')).not.toBeInTheDocument();
  });

  it('shows error on discovery failure', async () => {
    vi.mocked(discoverWorkflows).mockRejectedValue(new Error('Network error'));

    render(<WorkflowImportPanel {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId('discovery-error')).toBeInTheDocument();
    });
  });

  it('calls onClose when close button is clicked', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue({
      repositories_scanned: 0,
      workflows_found: 0,
      results: [],
      cross_repo_matches: [],
    });

    render(<WorkflowImportPanel {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId('discovery-results')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('import-modal-close'));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });
});

describe('deriveWorkflowStatusLabel', () => {
  it('returns "Local Draft" for draft project with new workflow', () => {
    expect(
      deriveWorkflowStatusLabel({
        workflowStatus: 'new',
        workflowGitHash: '0'.repeat(40),
        projectPrState: 'draft',
        hasOpenPR: false,
        hasDrift: false,
      })
    ).toBe('Local Draft');
  });

  it('returns "Imported Locally" when import metadata present', () => {
    expect(
      deriveWorkflowStatusLabel({
        workflowStatus: 'new',
        workflowGitHash: null,
        projectPrState: 'draft',
        hasOpenPR: false,
        hasDrift: false,
        hasImportMetadata: true,
      })
    ).toBe('Imported Locally');
  });

  it('returns "Under Review" when open PR exists', () => {
    expect(
      deriveWorkflowStatusLabel({
        workflowStatus: 'under_review',
        workflowGitHash: null,
        projectPrState: 'open',
        hasOpenPR: true,
        hasDrift: false,
      })
    ).toBe('Under Review');
  });

  it('returns "Synced" when synced with real hash', () => {
    expect(
      deriveWorkflowStatusLabel({
        workflowStatus: 'synced_with_github',
        workflowGitHash: 'abc123def456789012345678901234567890abcd',
        projectPrState: 'synced',
        hasOpenPR: false,
        hasDrift: false,
      })
    ).toBe('Synced');
  });

  it('returns "Drift Detected" when drift with real hash', () => {
    expect(
      deriveWorkflowStatusLabel({
        workflowStatus: 'synced_with_github',
        workflowGitHash: 'abc123def456789012345678901234567890abcd',
        projectPrState: 'synced',
        hasOpenPR: false,
        hasDrift: true,
      })
    ).toBe('Drift Detected');
  });

  it('returns "Pending Sync" for workflow without baseline', () => {
    expect(
      deriveWorkflowStatusLabel({
        workflowStatus: 'committed_locally',
        workflowGitHash: null,
        projectPrState: 'new',
        hasOpenPR: false,
        hasDrift: false,
      })
    ).toBe('Pending Sync');
  });

  it('does NOT return "Drift Detected" when no real hash exists', () => {
    // Even if hasDrift is somehow true, without a real hash it shouldn't show drift
    const label = deriveWorkflowStatusLabel({
      workflowStatus: 'new',
      workflowGitHash: '0'.repeat(40),
      projectPrState: 'draft',
      hasOpenPR: false,
      hasDrift: true,
    });
    expect(label).not.toBe('Drift Detected');
  });
});

describe('WorkflowImportPanel reusable workflow routing', () => {
  const baseProps = {
    projectId: 1,
    projectName: 'TestProject',
    githubUser: 'testuser',
    selectedRepos: ['owner/repo1'],
    onImportComplete: vi.fn(),
    onClose: vi.fn(),
  };

  const reusableWf = {
    repo_name: 'owner/repo1',
    branch: 'main',
    file_name: 'shared-workflow.yml',
    path: '.github/workflows/shared-workflow.yml',
    blob_sha: 'shaREUSE',
    is_reusable: true,
  };

  const callerWf = {
    repo_name: 'owner/repo1',
    branch: 'main',
    file_name: 'ci.yml',
    path: '.github/workflows/ci.yml',
    blob_sha: 'shaCALL',
    is_reusable: false,
  };

  const discoveryWith = (workflows: any[]) => ({
    repositories_scanned: 1,
    workflows_found: workflows.length,
    results: [
      { repo_name: 'owner/repo1', branch: 'main', workflows, warning: null, error: null },
    ],
    cross_repo_matches: [],
  });

  const importOk = {
    message: 'Imported 1 workflow(s) locally.',
    import_mode: 'save_local_only',
    results: [],
    pr_state: 'draft',
    pr_results: null,
  };

  /** Discover, then tick Select All. */
  const openAndSelectAll = async (props: Record<string, unknown> = {}) => {
    render(<WorkflowImportPanel {...baseProps} {...props} />);
    await waitFor(() => expect(screen.getByTestId('workflow-list')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('checkbox', { name: /Select All/ }));
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchProjects).mockResolvedValue([]);
    vi.mocked(importWorkflows).mockResolvedValue(importOk as any);
  });

  it('marks reusable workflows in the scan and leaves caller workflows unmarked', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue(discoveryWith([reusableWf, callerWf]) as any);

    render(<WorkflowImportPanel {...baseProps} />);
    await waitFor(() => expect(screen.getByTestId('workflow-list')).toBeInTheDocument());

    expect(
      screen.getByTestId('reusable-dot-owner/repo1-.github/workflows/shared-workflow.yml')
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('reusable-dot-owner/repo1-.github/workflows/ci.yml')
    ).not.toBeInTheDocument();
  });

  it('asks where a reusable workflow should go instead of importing straight away', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue(discoveryWith([reusableWf]) as any);
    vi.mocked(fetchProjects).mockResolvedValue([
      { project_id: 42, project_name: 'SharedWorkflows', project_type: 'rwx' },
    ] as any);

    await openAndSelectAll();
    fireEvent.click(screen.getByTestId('save-local-button'));

    expect(screen.getByTestId('reusable-decision')).toBeInTheDocument();
    expect(importWorkflows).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.getByTestId('reusable-destination')).toHaveValue('42')
    );
  });

  it('files the reusable workflow into the chosen Reusable Workflow Project', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue(discoveryWith([reusableWf]) as any);
    vi.mocked(fetchProjects).mockResolvedValue([
      { project_id: 42, project_name: 'SharedWorkflows', project_type: 'rwx' },
    ] as any);

    await openAndSelectAll();
    fireEvent.click(screen.getByTestId('save-local-button'));
    await waitFor(() => expect(screen.getByTestId('import-into-rwx-button')).toBeEnabled());
    fireEvent.click(screen.getByTestId('import-into-rwx-button'));

    await waitFor(() => expect(importWorkflows).toHaveBeenCalledTimes(1));
    const [, , , items, mode, targetRepos, destination] = vi.mocked(importWorkflows).mock.calls[0];
    expect(items).toHaveLength(1);
    expect(items[0].workflow_path).toBe('.github/workflows/shared-workflow.yml');
    expect(mode).toBe('save_local_only');
    expect(targetRepos).toBeUndefined();
    expect(destination).toBe(42);
  });

  it('splits a mixed selection between this project and the reusable project', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue(discoveryWith([reusableWf, callerWf]) as any);
    vi.mocked(fetchProjects).mockResolvedValue([
      { project_id: 42, project_name: 'SharedWorkflows', project_type: 'rwx' },
    ] as any);

    await openAndSelectAll();
    fireEvent.click(screen.getByTestId('save-local-button'));
    await waitFor(() => expect(screen.getByTestId('import-into-rwx-button')).toBeEnabled());
    fireEvent.click(screen.getByTestId('import-into-rwx-button'));

    await waitFor(() => expect(importWorkflows).toHaveBeenCalledTimes(2));
    const [hereCall, movedCall] = vi.mocked(importWorkflows).mock.calls;
    expect(hereCall[3].map((i: any) => i.workflow_path)).toEqual(['.github/workflows/ci.yml']);
    expect(hereCall[6]).toBeUndefined();
    expect(movedCall[3].map((i: any) => i.workflow_path)).toEqual([
      '.github/workflows/shared-workflow.yml',
    ]);
    expect(movedCall[6]).toBe(42);
  });

  it('offers to create a Reusable Workflow Project when none exists', async () => {
    const onCreateReusableProject = vi.fn();
    vi.mocked(discoverWorkflows).mockResolvedValue(discoveryWith([reusableWf]) as any);
    vi.mocked(fetchProjects).mockResolvedValue([]);

    await openAndSelectAll({ onCreateReusableProject });
    fireEvent.click(screen.getByTestId('save-local-button'));

    expect(screen.getByTestId('no-rwx-project')).toBeInTheDocument();
    expect(screen.queryByTestId('reusable-destination')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('create-rwx-project-button'));
    expect(onCreateReusableProject).toHaveBeenCalledTimes(1);
  });

  it('imports into the caller project when the user chooses to keep it here', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue(discoveryWith([reusableWf]) as any);

    await openAndSelectAll();
    fireEvent.click(screen.getByTestId('save-local-button'));
    fireEvent.click(screen.getByTestId('import-here-anyway-button'));

    await waitFor(() => expect(importWorkflows).toHaveBeenCalledTimes(1));
    const call = vi.mocked(importWorkflows).mock.calls[0];
    expect(call[3]).toHaveLength(1);
    expect(call[6]).toBeUndefined();
  });

  it('does not interrupt an import inside a Reusable Workflow Project', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue(discoveryWith([reusableWf]) as any);

    await openAndSelectAll({ projectType: 'rwx' });
    fireEvent.click(screen.getByTestId('save-local-button'));

    await waitFor(() => expect(importWorkflows).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId('reusable-decision')).not.toBeInTheDocument();
  });

  it('does not claim there is no reusable project while the lookup is in flight', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue(discoveryWith([reusableWf]) as any);
    vi.mocked(fetchProjects).mockReturnValue(new Promise(() => {}) as any);

    await openAndSelectAll();
    fireEvent.click(screen.getByTestId('save-local-button'));

    expect(screen.getByTestId('rwx-lookup-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('no-rwx-project')).not.toBeInTheDocument();
    expect(screen.queryByTestId('create-rwx-project-button')).not.toBeInTheDocument();
  });

  it('warns that a redirected import creates no PR campaign', async () => {
    vi.mocked(discoverWorkflows).mockResolvedValue(discoveryWith([reusableWf]) as any);
    vi.mocked(fetchProjects).mockResolvedValue([
      { project_id: 42, project_name: 'SharedWorkflows', project_type: 'rwx' },
    ] as any);

    await openAndSelectAll();
    fireEvent.click(screen.getByTestId('save-and-pr-button'));

    expect(screen.getByTestId('reusable-campaign-note')).toBeInTheDocument();
  });

  it('keeps the first import when the redirected one fails, and still refreshes', async () => {
    const onImportComplete = vi.fn();
    vi.mocked(discoverWorkflows).mockResolvedValue(discoveryWith([reusableWf, callerWf]) as any);
    vi.mocked(fetchProjects).mockResolvedValue([
      { project_id: 42, project_name: 'SharedWorkflows', project_type: 'rwx' },
    ] as any);
    vi.mocked(importWorkflows)
      .mockResolvedValueOnce({
        message: 'Imported 1 workflow(s) locally.',
        import_mode: 'save_local_only',
        results: [],
        pr_state: 'draft',
        pr_results: null,
      } as any)
      .mockRejectedValueOnce(new Error('Destination project not found or access denied'));

    await openAndSelectAll({ onImportComplete });
    fireEvent.click(screen.getByTestId('save-local-button'));
    await waitFor(() => expect(screen.getByTestId('import-into-rwx-button')).toBeEnabled());
    fireEvent.click(screen.getByTestId('import-into-rwx-button'));

    await waitFor(() => expect(importWorkflows).toHaveBeenCalledTimes(2));
    // The caller workflow really was written, so the parent must refetch or the
    // project view stays stale until a manual reload.
    await waitFor(() => expect(onImportComplete).toHaveBeenCalledWith('draft'));
    expect(screen.getByTestId('import-error')).toHaveTextContent('Imported 1 workflow(s) locally.');
    expect(screen.getByTestId('import-error')).toHaveTextContent('The rest failed');
  });
});
