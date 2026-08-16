import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import ActionsProjectsList from './ActionsProjectsList';
import { listActionsProjects } from './api/actionsProjects';
import { listActionGroups, createActionGroup } from './api/actionGroups';

import type { Mock } from 'vitest';
const mockNavigate = vi.fn();

vi.mock('react-router', () => ({
  useNavigate: () => mockNavigate,
}));

vi.mock('./api/actionsProjects', () => ({
  listActionsProjects: vi.fn(),
}));

vi.mock('./api/actionGroups', () => ({
  listActionGroups: vi.fn(),
  createActionGroup: vi.fn(),
  updateActionGroup: vi.fn(),
  deleteActionGroup: vi.fn(),
  addActionToGroup: vi.fn(),
  removeActionFromGroup: vi.fn(),
}));

vi.mock('./utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

describe('ActionsProjectsList', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
    (listActionGroups as Mock).mockResolvedValue([]);
  });

  it('renders cards for each returned project', async () => {
    (listActionsProjects as Mock).mockResolvedValue([
      {
        actions_project_id: 1,
        name: 'Setup Node',
        description: null,
        source_url: 'https://github.com/actions/setup-node',
        owner: 'actions',
        repo: 'setup-node',
        ref: 'main',
        yaml_path: 'actions.yaml',
        inputs: [{ name: 'node-version', description: null, required: false, default: '20', type: 'string', options: null }],
      },
    ]);

    render(<ActionsProjectsList user="testuser" />);

    await waitFor(() => expect(screen.getByText('Setup Node')).toBeInTheDocument());
    expect(screen.getByText('actions/setup-node · 1 input')).toBeInTheDocument();
  });

  it('shows an empty state when there are no projects', async () => {
    (listActionsProjects as Mock).mockResolvedValue([]);

    render(<ActionsProjectsList user="testuser" />);

    await waitFor(() =>
      expect(screen.getByText(/No Managed Actions yet/)).toBeInTheDocument()
    );
  });

  it('navigates to the detail page when a card is clicked', async () => {
    (listActionsProjects as Mock).mockResolvedValue([
      {
        actions_project_id: 7,
        name: 'Setup Node',
        description: null,
        source_url: 'https://github.com/actions/setup-node',
        owner: 'actions',
        repo: 'setup-node',
        ref: 'main',
        yaml_path: 'actions.yaml',
        inputs: [],
      },
    ]);

    render(<ActionsProjectsList user="testuser" />);

    const card = await screen.findByTestId('actions-project-card-7');
    await user.click(card);

    expect(mockNavigate).toHaveBeenCalledWith('/project/testuser/actions-projects/7');
  });

  it('navigates to the add flow when "Add Actions Project" is clicked', async () => {
    (listActionsProjects as Mock).mockResolvedValue([]);

    render(<ActionsProjectsList user="testuser" />);

    await user.click(await screen.findByTestId('add-actions-project-button'));

    expect(mockNavigate).toHaveBeenCalledWith('/project/testuser/actions-projects/new');
  });

  it('renders the marketplace branding icon when present, falling back to a generic icon otherwise', async () => {
    (listActionsProjects as Mock).mockResolvedValue([
      {
        actions_project_id: 1,
        name: 'Branded Action',
        description: null,
        source_url: 'https://github.com/actions/branded',
        owner: 'actions',
        repo: 'branded',
        ref: 'main',
        yaml_path: 'action.yml',
        inputs: [],
        branding_icon: 'rocket',
        branding_color: 'blue',
      },
      {
        actions_project_id: 2,
        name: 'Unbranded Action',
        description: null,
        source_url: 'https://github.com/actions/unbranded',
        owner: 'actions',
        repo: 'unbranded',
        ref: 'main',
        yaml_path: 'action.yml',
        inputs: [],
        branding_icon: null,
        branding_color: null,
      },
    ]);

    render(<ActionsProjectsList user="testuser" />);

    const brandedCard = await screen.findByTestId('actions-project-card-1');
    const unbrandedCard = await screen.findByTestId('actions-project-card-2');

    await waitFor(() => expect(brandedCard.querySelector('svg')).toBeInTheDocument());
    expect(unbrandedCard.querySelector('svg')).toBeInTheDocument();
  });

  const twoProjects = [
    {
      actions_project_id: 1,
      name: 'Checkout',
      description: null,
      source_url: 'https://github.com/actions/checkout',
      owner: 'actions',
      repo: 'checkout',
      ref: 'main',
      yaml_path: 'action.yml',
      inputs: [],
      branding_icon: null,
      branding_color: null,
    },
    {
      actions_project_id: 2,
      name: 'Setup Node',
      description: null,
      source_url: 'https://github.com/actions/setup-node',
      owner: 'actions',
      repo: 'setup-node',
      ref: 'main',
      yaml_path: 'action.yml',
      inputs: [],
      branding_icon: null,
      branding_color: null,
    },
  ];

  it('narrows the list to a selected group without duplicating an action in multiple groups', async () => {
    (listActionsProjects as Mock).mockResolvedValue(twoProjects);
    (listActionGroups as Mock).mockResolvedValue([
      { action_group_id: 10, name: 'Deployment', description: null, actions_project_ids: [1] },
      { action_group_id: 11, name: 'Setup', description: null, actions_project_ids: [1, 2] },
    ]);

    render(<ActionsProjectsList user="testuser" />);

    await screen.findByTestId('actions-project-card-1');
    expect(screen.getByTestId('actions-filtered-count')).toHaveTextContent('Showing 2 of 2');

    await user.selectOptions(screen.getByTestId('actions-group-filter'), '10');
    expect(screen.getByTestId('actions-project-card-1')).toBeInTheDocument();
    expect(screen.queryByTestId('actions-project-card-2')).not.toBeInTheDocument();
    expect(screen.getAllByText('Checkout')).toHaveLength(1);

    await user.selectOptions(screen.getByTestId('actions-group-filter'), '11');
    expect(screen.getByTestId('actions-project-card-1')).toBeInTheDocument();
    expect(screen.getByTestId('actions-project-card-2')).toBeInTheDocument();
    expect(screen.getAllByText('Checkout')).toHaveLength(1);
  });

  it('reflects a newly created group in the filter dropdown immediately, without a refresh', async () => {
    (listActionsProjects as Mock).mockResolvedValue(twoProjects);
    (listActionGroups as Mock).mockResolvedValue([]);
    (createActionGroup as Mock).mockResolvedValue({
      action_group_id: 99,
      name: 'Deployment',
      description: null,
      actions_project_ids: [],
    });

    render(<ActionsProjectsList user="testuser" />);
    await screen.findByTestId('actions-project-card-1');

    await user.click(screen.getByTestId('manage-action-groups-button'));
    await user.type(await screen.findByTestId('new-action-group-name'), 'Deployment');
    await user.click(screen.getByTestId('create-action-group-button'));

    await waitFor(() => expect(createActionGroup).toHaveBeenCalledWith('testuser', 'Deployment', null));

    const filterSelect = screen.getByTestId('actions-group-filter') as HTMLSelectElement;
    await waitFor(() =>
      expect(Array.from(filterSelect.options).map((o) => o.textContent)).toContain('Deployment')
    );
  });
});
