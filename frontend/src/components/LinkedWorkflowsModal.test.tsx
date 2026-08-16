import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import LinkedWorkflowsModal from './LinkedWorkflowsModal';
import * as projectsApi from '../api/projects';

import type { Mock } from 'vitest';
vi.mock('../api/projects', () => ({
  getAvailableRwxWorkflows: vi.fn(),
}));

// Minimal Dialog shim — renders children directly
vi.mock('./ui/dialog', () => ({
  Dialog: ({ open, children }: any) => open ? <div>{children}</div> : null,
  DialogContent: ({ children }: any) => <div>{children}</div>,
  DialogHeader: ({ children }: any) => <div>{children}</div>,
  DialogTitle: ({ children }: any) => <h2>{children}</h2>,
  DialogDescription: ({ children }: any) => <p>{children}</p>,
  DialogFooter: ({ children }: any) => <div>{children}</div>,
}));

vi.mock('./ui/button', () => ({
  Button: ({ children, onClick, disabled }: any) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
}));

const mockWorkflows: projectsApi.RwxWorkflow[] = [
  {
    workflow_id: 1,
    workflow_name: 'build-workflow',
    workflow_yaml: 'name: build',
    rwx_project_id: 10,
    rwx_project_name: 'Project Alpha',
    rwx_repo_visibility: 'public',
    link_validation: { allowed: true },
  },
  {
    workflow_id: 2,
    workflow_name: 'deploy-workflow',
    workflow_yaml: 'name: deploy',
    rwx_project_id: 10,
    rwx_project_name: 'Project Alpha',
    rwx_repo_visibility: 'private',
    link_validation: { allowed: true },
  },
  {
    workflow_id: 3,
    workflow_name: 'test-workflow',
    workflow_yaml: 'name: test',
    rwx_project_id: 20,
    rwx_project_name: 'Project Beta',
    rwx_repo_visibility: 'public',
    link_validation: { allowed: true },
  },
];

const invalidPrivateWorkflow: projectsApi.RwxWorkflow = {
  workflow_id: 4,
  workflow_name: 'private-workflow',
  workflow_yaml: 'name: private',
  rwx_project_id: 30,
  rwx_project_name: 'Private RWX',
  rwx_repo_visibility: 'private',
  link_validation: {
    allowed: false,
    reason: 'public projects cannot call private reusable workflows.',
  },
};

const defaultProps = {
  isOpen: true,
  user: 'test-user',
  projectName: 'My Project',
  alreadyLinkedIds: [],
  onLink: vi.fn(),
  onClose: vi.fn(),
};

describe('LinkedWorkflowsModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (projectsApi.getAvailableRwxWorkflows as Mock).mockResolvedValue(mockWorkflows);
  });

  test('shows loading state initially', () => {
    render(<LinkedWorkflowsModal {...defaultProps} />);
    expect(screen.getByText(/Loading available workflows/i)).toBeInTheDocument();
  });

  test('renders workflows after loading', async () => {
    render(<LinkedWorkflowsModal {...defaultProps} />);
    expect(projectsApi.getAvailableRwxWorkflows).toHaveBeenCalledWith('test-user', 'My Project');
    await waitFor(() => {
      expect(screen.getByText('build-workflow')).toBeInTheDocument();
      expect(screen.getByText('deploy-workflow')).toBeInTheDocument();
      expect(screen.getByText('test-workflow')).toBeInTheDocument();
    });
  });

  test('shows error when API fails', async () => {
    (projectsApi.getAvailableRwxWorkflows as Mock).mockRejectedValue(new Error('Network error'));
    render(<LinkedWorkflowsModal {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText(/Failed to load reusable workflows/i)).toBeInTheDocument();
    });
  });

  test('Add button is disabled when nothing is selected', async () => {
    render(<LinkedWorkflowsModal {...defaultProps} />);
    await waitFor(() => screen.getByText('build-workflow'));
    const addButton = screen.getByRole('button', { name: /^Add$/ });
    expect(addButton).toBeDisabled();
  });

  test('selecting a workflow enables the Add button with count', async () => {
    render(<LinkedWorkflowsModal {...defaultProps} />);
    await waitFor(() => screen.getByText('build-workflow'));

    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]); // select build-workflow

    expect(screen.getByRole('button', { name: 'Add (1)' })).not.toBeDisabled();
  });

  test('already-linked workflows are disabled and checked', async () => {
    render(<LinkedWorkflowsModal {...defaultProps} alreadyLinkedIds={[1]} />);
    await waitFor(() => screen.getByText('build-workflow'));

    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes[0]).toBeDisabled();
    expect(checkboxes[0]).toBeChecked();
    expect(screen.getByText('✅ Already linked')).toBeInTheDocument();
  });

  test('already-linked workflows are not counted in Add button', async () => {
    render(<LinkedWorkflowsModal {...defaultProps} alreadyLinkedIds={[1]} />);
    await waitFor(() => screen.getByText('build-workflow'));

    // deploy-workflow is not linked — select it
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]); // deploy-workflow

    expect(screen.getByRole('button', { name: 'Add (1)' })).not.toBeDisabled();
  });

  test('calls onLink with selected non-linked workflows', async () => {
    const onLink = vi.fn().mockResolvedValue(undefined);
    render(<LinkedWorkflowsModal {...defaultProps} onLink={onLink} />);
    await waitFor(() => screen.getByText('build-workflow'));

    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]); // build-workflow
    fireEvent.click(checkboxes[1]); // deploy-workflow

    const addButton = screen.getByRole('button', { name: 'Add (2)' });
    await act(async () => fireEvent.click(addButton));

    expect(onLink).toHaveBeenCalledWith([
      expect.objectContaining({ workflow_id: 1 }),
      expect.objectContaining({ workflow_id: 2 }),
    ]);
  });

  test('selection resets when filterProjectId changes', async () => {
    const { rerender } = render(<LinkedWorkflowsModal {...defaultProps} filterProjectId={10} />);
    await waitFor(() => screen.getByText('build-workflow'));

    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]);
    expect(screen.getByRole('button', { name: 'Add (1)' })).not.toBeDisabled();

    rerender(<LinkedWorkflowsModal {...defaultProps} filterProjectId={20} />);
    await waitFor(() => {
      // After filterProjectId change, Add button count should be 0 (selection reset)
      const addBtn = screen.getByRole('button', { name: /^Add$/ });
      expect(addBtn).toBeDisabled();
    });
  });

  test('filterProjectId scopes displayed workflows', async () => {
    render(<LinkedWorkflowsModal {...defaultProps} filterProjectId={20} />);
    await waitFor(() => screen.getByText('test-workflow'));

    expect(screen.queryByText('build-workflow')).not.toBeInTheDocument();
    expect(screen.queryByText('deploy-workflow')).not.toBeInTheDocument();
  });

  test('does not render when isOpen is false', () => {
    render(<LinkedWorkflowsModal {...defaultProps} isOpen={false} />);
    expect(screen.queryByText(/Link Reusable Workflow/)).not.toBeInTheDocument();
  });

  test('calls onClose when Close button is clicked', async () => {
    const onClose = vi.fn();
    render(<LinkedWorkflowsModal {...defaultProps} onClose={onClose} />);
    await waitFor(() => screen.getByText('build-workflow'));

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalled();
  });

  test('invalid private RWX option is disabled with a clear reason', async () => {
    (projectsApi.getAvailableRwxWorkflows as Mock).mockResolvedValue([
      mockWorkflows[0],
      invalidPrivateWorkflow,
    ]);

    render(<LinkedWorkflowsModal {...defaultProps} />);
    await waitFor(() => screen.getByText('private-workflow'));

    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes[1]).toBeDisabled();
    expect(screen.getByText(/Not available: public projects cannot call private reusable workflows/i)).toBeInTheDocument();
    expect(screen.getByText('Private')).toBeInTheDocument();
  });

  test('connect action stays disabled when only selected option is invalid', async () => {
    (projectsApi.getAvailableRwxWorkflows as Mock).mockResolvedValue([invalidPrivateWorkflow]);
    render(<LinkedWorkflowsModal {...defaultProps} />);
    await waitFor(() => screen.getByText('private-workflow'));

    fireEvent.click(screen.getByRole('checkbox'));

    expect(screen.getByRole('button', { name: /^Add$/ })).toBeDisabled();
    expect(defaultProps.onLink).not.toHaveBeenCalled();
  });

  test('valid public RWX option remains selectable when invalid options exist', async () => {
    (projectsApi.getAvailableRwxWorkflows as Mock).mockResolvedValue([
      mockWorkflows[0],
      invalidPrivateWorkflow,
    ]);
    render(<LinkedWorkflowsModal {...defaultProps} />);
    await waitFor(() => screen.getByText('build-workflow'));

    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]);

    expect(checkboxes[0]).not.toBeDisabled();
    expect(screen.getByRole('button', { name: 'Add (1)' })).not.toBeDisabled();
  });
});
