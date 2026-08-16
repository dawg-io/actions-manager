import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import RepoBranchOverridesPanel from './RepoBranchOverridesPanel';

import type { MockedFunction } from 'vitest';
// Mock the API module — these are the only network calls the component makes.
vi.mock('../api/projects', () => ({
  fetchProjectRepoBranchConfigs: vi.fn(),
  updateProjectRepoBranchConfig: vi.fn(),
  resetProjectRepoBranchConfig: vi.fn(),
}));

import {
  fetchProjectRepoBranchConfigs,
  updateProjectRepoBranchConfig,
  resetProjectRepoBranchConfig,
} from '../api/projects';

const mockFetch = fetchProjectRepoBranchConfigs as MockedFunction<
  typeof fetchProjectRepoBranchConfigs
>;
const mockUpdate = updateProjectRepoBranchConfig as MockedFunction<
  typeof updateProjectRepoBranchConfig
>;
const mockReset = resetProjectRepoBranchConfig as MockedFunction<
  typeof resetProjectRepoBranchConfig
>;

const repoInherit = {
  repo_id: 1,
  repo_name: 'whatsupdawg/test1',
  branch_config_mode: 'inherit' as const,
  branch_option: null,
  branch_regex: null,
  branch_max_age_days: null,
  effective_branch_option: 'default' as const,
  effective_branch_regex: '',
  effective_branch_max_age_days: 30,
  using_project_default: true,
};

const repoOverride = {
  repo_id: 2,
  repo_name: 'whatsupdawg/test2',
  branch_config_mode: 'override' as const,
  branch_option: 'pattern' as const,
  branch_regex: 'develop',
  branch_max_age_days: 14,
  effective_branch_option: 'pattern' as const,
  effective_branch_regex: 'develop',
  effective_branch_max_age_days: 14,
  using_project_default: false,
};

const baseResponse = {
  project_id: 42,
  project_branch_option: 'default' as const,
  project_branch_regex: '',
  project_branch_max_age_days: 30,
  repos: [repoInherit, repoOverride],
};

describe('RepoBranchOverridesPanel', () => {
  const mockOnRemoveRepo = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockResolvedValue({ ...baseResponse });
  });

  test('renders inherit and override badges per repo', async () => {
    render(
      <RepoBranchOverridesPanel
        user="alice"
        projectId={42}
        selectedRepos={['whatsupdawg/test1', 'whatsupdawg/test2']}
        onRemoveRepo={mockOnRemoveRepo}
        branchOption="default"
        regexPattern=""
        branchMaxAgeDays={30}
      />
    );
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(await screen.findByTestId('badge-inherit-1')).toHaveTextContent(
      'Using Project Default'
    );
    expect(screen.getByTestId('badge-override-2')).toHaveTextContent(
      'Custom Branch Config'
    );
  });

  test('clicking Configure opens inline editor and disables override fields when inheriting', async () => {
    render(
      <RepoBranchOverridesPanel
        user="alice"
        projectId={42}
        selectedRepos={['whatsupdawg/test1', 'whatsupdawg/test2']}
        onRemoveRepo={mockOnRemoveRepo}
        branchOption="default"
        regexPattern=""
        branchMaxAgeDays={30}
      />
    );
    // Click the Configure button for repo 1
    const configureButtons = await screen.findAllByText('Configure');
    fireEvent.click(configureButtons[0]);

    expect(screen.getByTestId('mode-inherit')).toBeChecked();
    expect(screen.getByTestId('mode-override')).not.toBeChecked();
    // Override fields are inside a disabled fieldset
    const optionDefault = screen.getByTestId('option-default') as HTMLInputElement;
    expect(optionDefault.closest('fieldset')).toBeDisabled();
    // Save button is disabled with no changes
    expect(screen.getByTestId('save-btn')).toBeDisabled();
  });

  test('switching to override mode enables fields and save button activates', async () => {
    render(
      <RepoBranchOverridesPanel
        user="alice"
        projectId={42}
        selectedRepos={['whatsupdawg/test1', 'whatsupdawg/test2']}
        onRemoveRepo={mockOnRemoveRepo}
        branchOption="default"
        regexPattern=""
        branchMaxAgeDays={30}
      />
    );
    const configureButtons = await screen.findAllByText('Configure');
    fireEvent.click(configureButtons[0]);
    fireEvent.click(screen.getByTestId('mode-override'));

    const optionDefault = screen.getByTestId('option-default') as HTMLInputElement;
    expect(optionDefault.closest('fieldset')).not.toBeDisabled();
    expect(screen.getByTestId('save-btn')).not.toBeDisabled();
  });

  test('save button calls update API and surfaces success', async () => {
    mockUpdate.mockResolvedValue({
      ...repoInherit,
      branch_config_mode: 'override',
      branch_option: 'pattern',
      branch_regex: 'main',
      branch_max_age_days: 30,
      effective_branch_option: 'pattern',
      effective_branch_regex: 'main',
      effective_branch_max_age_days: 30,
      using_project_default: false,
    });

    render(
      <RepoBranchOverridesPanel
        user="alice"
        projectId={42}
        selectedRepos={['whatsupdawg/test1', 'whatsupdawg/test2']}
        onRemoveRepo={mockOnRemoveRepo}
        branchOption="default"
        regexPattern=""
        branchMaxAgeDays={30}
      />
    );
    const configureButtons = await screen.findAllByText('Configure');
    fireEvent.click(configureButtons[0]);
    fireEvent.click(screen.getByTestId('mode-override'));
    fireEvent.click(screen.getByTestId('option-pattern'));
    fireEvent.change(screen.getByTestId('input-regex'), { target: { value: 'main' } });
    fireEvent.click(screen.getByTestId('save-btn'));

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
    expect(mockUpdate).toHaveBeenCalledWith('alice', 42, 1, expect.objectContaining({
      branch_config_mode: 'override',
      branch_option: 'pattern',
      branch_regex: 'main',
    }));
    expect(await screen.findByTestId('save-success')).toHaveTextContent('Saved');
    // Badge should now reflect the override after a successful save
    expect(await screen.findByTestId('badge-override-1')).toBeInTheDocument();
  });

  test('shows error message when API fails', async () => {
    mockUpdate.mockRejectedValue({ response: { data: { detail: 'boom' } } });

    render(
      <RepoBranchOverridesPanel
        user="alice"
        projectId={42}
        selectedRepos={['whatsupdawg/test1', 'whatsupdawg/test2']}
        onRemoveRepo={mockOnRemoveRepo}
        branchOption="default"
        regexPattern=""
        branchMaxAgeDays={30}
      />
    );
    const configureButtons = await screen.findAllByText('Configure');
    fireEvent.click(configureButtons[0]);
    fireEvent.click(screen.getByTestId('mode-override'));
    fireEvent.click(screen.getByTestId('option-pattern'));
    fireEvent.change(screen.getByTestId('input-regex'), { target: { value: 'main' } });
    fireEvent.click(screen.getByTestId('save-btn'));

    expect(await screen.findByTestId('save-error')).toHaveTextContent('boom');
  });

  test('reset button calls reset API for an overridden repo', async () => {
    mockReset.mockResolvedValue({ ...repoInherit, repo_id: 2, repo_name: 'whatsupdawg/test2' });

    render(
      <RepoBranchOverridesPanel
        user="alice"
        projectId={42}
        selectedRepos={['whatsupdawg/test1', 'whatsupdawg/test2']}
        onRemoveRepo={mockOnRemoveRepo}
        branchOption="default"
        regexPattern=""
        branchMaxAgeDays={30}
      />
    );
    const configureButtons = await screen.findAllByText('Configure');
    fireEvent.click(configureButtons[1]); // Click Configure for repo 2
    fireEvent.click(screen.getByTestId('reset-btn'));

    await waitFor(() => expect(mockReset).toHaveBeenCalledWith('alice', 42, 2));
  });

  test('removing the active repo closes the editor', async () => {
    const { rerender } = render(
      <RepoBranchOverridesPanel
        user="alice"
        projectId={42}
        selectedRepos={['whatsupdawg/test1', 'whatsupdawg/test2']}
        onRemoveRepo={mockOnRemoveRepo}
        branchOption="default"
        regexPattern=""
        branchMaxAgeDays={30}
      />
    );
    const configureButtons = await screen.findAllByText('Configure');
    fireEvent.click(configureButtons[0]);
    expect(screen.getByTestId('mode-inherit')).toBeInTheDocument();

    rerender(
      <RepoBranchOverridesPanel
        user="alice"
        projectId={42}
        selectedRepos={['whatsupdawg/test2']}
        onRemoveRepo={mockOnRemoveRepo}
        branchOption="default"
        regexPattern=""
        branchMaxAgeDays={30}
      />
    );
    // Editor should be closed (no inline editor visible)
    expect(screen.queryByTestId('repo-editor-inline')).not.toBeInTheDocument();
  });
});
