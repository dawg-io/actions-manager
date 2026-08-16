import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import RollbackCampaignModal from './RollbackCampaignModal';
import { createCampaignRollback, previewCampaignRollback } from '../api/pullRequests';

import type { Mock } from 'vitest';
vi.mock('../api/pullRequests', () => ({
  previewCampaignRollback: vi.fn(),
  createCampaignRollback: vi.fn(),
}));

const mockPreview = previewCampaignRollback as Mock;
const mockCreate = createCampaignRollback as Mock;

const OLD_YAML = 'name: ci\nruns-on: ubuntu-latest\n';
const NEW_YAML = 'name: ci\nruns-on: ubuntu-24.04\n';

const campaign: any = {
  campaign_id: 'campaign-7',
  campaign_name: 'Bump runners',
  campaign_status: 'completed',
  merged_count: 2,
};

const invertibleTarget = {
  repo_name: 'acme/api',
  target_branch: 'main',
  pr_number: 42,
  pr_url: 'https://github.com/acme/api/pull/42',
  workflow_names: 'ci',
  invertible: true,
  reason: null,
  files: [{ path: '.github/workflows/AM_RBK_ci.yml', action: 'restore', before: NEW_YAML, after: OLD_YAML }],
};

const blockedTarget = {
  repo_name: 'acme/web',
  target_branch: 'main',
  pr_number: 43,
  pr_url: 'https://github.com/acme/web/pull/43',
  workflow_names: 'ci',
  invertible: false,
  reason: '.github/workflows/AM_RBK_ci.yml changed on main after this campaign merged — rolling back would discard that change.',
  files: [],
};

const renderModal = (props: Record<string, unknown> = {}) =>
  render(
    <RollbackCampaignModal
      open
      user="historyuser"
      projectName="history_project"
      campaign={campaign}
      onClose={vi.fn()}
      onRolledBack={vi.fn()}
      {...props}
    />
  );

describe('RollbackCampaignModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test('renders the proposed inverse diff for each invertible repository', async () => {
    mockPreview.mockResolvedValue({
      campaign_id: 7, campaign_name: 'Bump runners',
      targets: [invertibleTarget], invertible_count: 1,
    });

    renderModal();

    expect(await screen.findByTestId('rollback-summary'))
      .toHaveTextContent('1 of 1 merged repository can be rolled back automatically.');
    const target = screen.getByTestId('rollback-target');
    expect(within(target).getByText('acme/api on main')).toBeInTheDocument();
    expect(within(target).getByText('.github/workflows/AM_RBK_ci.yml')).toBeInTheDocument();
    // The diff shows the current content on the left and the restored content on the right.
    expect(within(target).getByText('Current on main')).toBeInTheDocument();
    expect(within(target).getByText('After rollback')).toBeInTheDocument();
    expect(within(target).getByText('runs-on: ubuntu-24.04')).toBeInTheDocument();
    expect(within(target).getByText('runs-on: ubuntu-latest')).toBeInTheDocument();
  });

  test('a non-invertible repository shows its reason instead of a diff', async () => {
    mockPreview.mockResolvedValue({
      campaign_id: 7, campaign_name: 'Bump runners',
      targets: [invertibleTarget, blockedTarget], invertible_count: 1,
    });

    renderModal();

    const reason = await screen.findByTestId('rollback-reason');
    expect(reason).toHaveTextContent('changed on main after this campaign merged');
    expect(screen.getByText('Not invertible')).toBeInTheDocument();
    // Flagged, still listed — never silently dropped.
    expect(screen.getAllByTestId('rollback-target')).toHaveLength(2);
    expect(await screen.findByTestId('rollback-summary'))
      .toHaveTextContent('1 of 2 merged repositories');
  });

  test('confirming is disabled when nothing can be inverted', async () => {
    mockPreview.mockResolvedValue({
      campaign_id: 7, campaign_name: 'Bump runners',
      targets: [blockedTarget], invertible_count: 0,
    });

    renderModal();

    await screen.findByTestId('rollback-reason');
    expect(screen.getByTestId('rollback-confirm')).toBeDisabled();
    // The choice about ActionsManager's own copy is moot with nothing to roll back.
    expect(screen.queryByText('Keep this change to retry later')).not.toBeInTheDocument();
  });

  test('confirming sends the chosen ActionsManager action and reports the result', async () => {
    const user = userEvent.setup();
    const onRolledBack = vi.fn();
    mockPreview.mockResolvedValue({
      campaign_id: 7, campaign_name: 'Bump runners',
      targets: [invertibleTarget], invertible_count: 1,
    });
    mockCreate.mockResolvedValue({ campaign_id: 9, prs_created: 1, results: {}, skipped: [] });

    renderModal({ onRolledBack });

    await screen.findByTestId('rollback-summary');
    await user.click(screen.getByLabelText(/Keep this change to retry later/));
    await user.click(screen.getByTestId('rollback-confirm'));

    await waitFor(() => expect(mockCreate).toHaveBeenCalledWith(
      'historyuser', 'history_project', 'campaign-7', { amAction: 'keep' }
    ));
    expect(onRolledBack).toHaveBeenCalledWith(
      expect.objectContaining({ campaign_id: 9, prs_created: 1 })
    );
  });

  test('reverting ActionsManager is the default', async () => {
    const user = userEvent.setup();
    mockPreview.mockResolvedValue({
      campaign_id: 7, campaign_name: 'Bump runners',
      targets: [invertibleTarget], invertible_count: 1,
    });
    mockCreate.mockResolvedValue({ campaign_id: 9, prs_created: 1, results: {}, skipped: [] });

    renderModal();

    await screen.findByTestId('rollback-summary');
    await user.click(screen.getByTestId('rollback-confirm'));

    await waitFor(() => expect(mockCreate).toHaveBeenCalledWith(
      'historyuser', 'history_project', 'campaign-7', { amAction: 'revert' }
    ));
  });

  test('a failed preview surfaces the error and opens nothing', async () => {
    mockPreview.mockRejectedValue(new Error('GitHub rate limit exceeded'));

    renderModal();

    expect(await screen.findByTestId('rollback-error')).toHaveTextContent('GitHub rate limit exceeded');
    expect(screen.getByTestId('rollback-confirm')).toBeDisabled();
    expect(mockCreate).not.toHaveBeenCalled();
  });

  test('nothing is requested while the modal is closed', () => {
    renderModal({ open: false });

    expect(mockPreview).not.toHaveBeenCalled();
  });
});
