/**
 * Tests for WorkflowImportPanel component and derived status labels.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { WorkflowImportPanel } from './WorkflowImportPanel';
import { deriveWorkflowStatusLabel } from '../utils/workflowImportStatus';
import { discoverWorkflows, previewWorkflow, importWorkflows } from '../api/workflowImport';

// Mock the API module
vi.mock('../api/workflowImport', () => ({
  discoverWorkflows: vi.fn(),
  previewWorkflow: vi.fn(),
  importWorkflows: vi.fn(),
}));

describe('WorkflowImportPanel', () => {
  const defaultProps = {
    projectId: 1,
    projectName: 'TestProject',
    githubUser: 'testuser',
    onImportComplete: jest.fn(),
    onClose: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('auto-scans on mount and shows scanning state', () => {
    discoverWorkflows.mockReturnValue(new Promise(() => {})); // never resolves
    render(<WorkflowImportPanel {...defaultProps} />);
    expect(screen.getByTestId('import-scanning')).toBeInTheDocument();
    expect(discoverWorkflows).toHaveBeenCalledWith(1, 'testuser', 'TestProject');
  });

  it('renders as a modal overlay', () => {
    discoverWorkflows.mockReturnValue(new Promise(() => {}));
    render(<WorkflowImportPanel {...defaultProps} />);
    expect(screen.getByTestId('workflow-import-modal')).toBeInTheDocument();
  });

  it('shows empty state when no workflows found', async () => {
    discoverWorkflows.mockResolvedValue({
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
    discoverWorkflows.mockResolvedValue({
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
    discoverWorkflows.mockResolvedValue({
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
    discoverWorkflows.mockResolvedValue({
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
    discoverWorkflows.mockResolvedValue({
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
    discoverWorkflows.mockResolvedValue({
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
    const testIds = previewButtons.map((button) => button.getAttribute('data-testid'));
    expect(new Set(testIds).size).toBe(2);
  });

  it('clears preview error when a later preview succeeds', async () => {
    discoverWorkflows.mockResolvedValue({
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
    previewWorkflow
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
    discoverWorkflows.mockResolvedValue({
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
    importWorkflows.mockImplementation(
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
    discoverWorkflows.mockResolvedValue({
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

    importWorkflows.mockResolvedValue({
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
    discoverWorkflows.mockResolvedValue({
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

    importWorkflows.mockResolvedValue({
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
    discoverWorkflows.mockResolvedValue({
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

    importWorkflows.mockResolvedValue({
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
    discoverWorkflows.mockRejectedValue(new Error('Network error'));

    render(<WorkflowImportPanel {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId('discovery-error')).toBeInTheDocument();
    });
  });

  it('calls onClose when close button is clicked', async () => {
    discoverWorkflows.mockResolvedValue({
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
