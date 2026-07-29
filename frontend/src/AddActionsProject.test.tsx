import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import AddActionsProject from './AddActionsProject';
import { previewActionsProject, createActionsProject } from './api/actionsProjects';

const mockNavigate = jest.fn();

vi.mock('react-router', () => ({
  useNavigate: () => mockNavigate,
}), { virtual: true });

vi.mock('./api/actionsProjects', () => ({
  previewActionsProject: jest.fn(),
  createActionsProject: jest.fn(),
}));

vi.mock('./utils/toast', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
    warning: jest.fn(),
  },
}));

const previewResponse = {
  name: 'Setup Node',
  description: 'Sets up a Node.js environment',
  owner: 'actions',
  repo: 'setup-node',
  ref: 'main',
  yaml_path: 'actions.yaml',
  source_url: 'https://github.com/actions/setup-node',
  inputs: [{ name: 'node-version', description: 'Version to use', required: false, default: '20', type: 'string', options: null }],
};

describe('AddActionsProject', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('fetches a preview and shows the review step with prefilled fields', async () => {
    (previewActionsProject as jest.Mock).mockResolvedValue(previewResponse);

    render(<AddActionsProject user="testuser" />);

    await user.type(screen.getByLabelText('GitHub URL'), 'https://github.com/actions/setup-node');
    await user.click(screen.getByTestId('fetch-preview-button'));

    await waitFor(() => expect(previewActionsProject).toHaveBeenCalledWith('testuser', 'https://github.com/actions/setup-node'));
    expect(await screen.findByDisplayValue('Setup Node')).toBeInTheDocument();
    expect(screen.getByDisplayValue('node-version')).toBeInTheDocument();
  });

  it('saves the reviewed project and navigates back to the list', async () => {
    (previewActionsProject as jest.Mock).mockResolvedValue(previewResponse);
    (createActionsProject as jest.Mock).mockResolvedValue({ ...previewResponse, actions_project_id: 1 });

    render(<AddActionsProject user="testuser" />);

    await user.type(screen.getByLabelText('GitHub URL'), 'https://github.com/actions/setup-node');
    await user.click(screen.getByTestId('fetch-preview-button'));
    await screen.findByDisplayValue('Setup Node');

    await user.click(screen.getByTestId('save-actions-project-button'));

    await waitFor(() => expect(createActionsProject).toHaveBeenCalled());
    expect(mockNavigate).toHaveBeenCalledWith('/project/testuser/actions-projects');
  });
});
