import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import PRHistoryPanel from './PRHistoryPanel';
import { createCampaignRollback, getPRCampaigns, mergePullRequest, previewCampaignRollback, type PRCampaign } from '../api/pullRequests';

import type { Mock } from 'vitest';
vi.mock('../api/pullRequests', () => ({
  getPRCampaigns: vi.fn(),
  mergePullRequest: vi.fn(),
  closePullRequest: vi.fn(),
  previewCampaignRollback: vi.fn(),
  createCampaignRollback: vi.fn(),
}));

const mockGetPRCampaigns = getPRCampaigns as Mock;
const mockMergePullRequest = mergePullRequest as Mock;

const baseResponse = {
  campaigns: [],
  pull_requests: [],
  total_campaigns: 0,
  active_campaigns: 0,
  completed_campaigns: 0,
  open_prs: 0,
  merged_prs: 0,
  closed_prs: 0,
  repositories_affected: 0,
};

const openPR = {
  pr_id: 1,
  repo_name: 'org/repo',
  pr_number: 42,
  pr_url: 'https://github.com/org/repo/pull/42',
  pr_state: 'open',
  branch_name: 'actions-manager/hps-main-42',
  target_branch: 'main',
  title: 'Update okok.yml',
  author: 'aireland1010',
  actor: 'aireland1010',
  body: null,
  workflow_names: 'okok.yml',
  created_at: '2026-05-21T06:00:00+00:00',
  updated_at: '2026-05-21T06:05:00+00:00',
  merged_at: null,
  closed_at: null,
  source_project_name: null,
};

const makeCampaign = (n: number) => ({
  campaign_id: `campaign-${n}`,
  campaign_name: `Campaign ${n}`,
  campaign_status: 'merged',
  project_name: 'history_project',
  project_code: 'HPS',
  created_by: 'historyuser',
  created_at: '2026-05-21T06:00:00+00:00',
  updated_at: '2026-05-21T06:05:00+00:00',
  completed_at: '2026-05-21T06:05:00+00:00',
  target_branches: ['main'],
  workflow_names: ['done.yml'],
  repositories: ['org/repo'],
  open_count: 0,
  merged_count: 1,
  closed_count: 0,
  failed_count: 0,
  completion_percentage: 100,
  pull_requests: [{ ...openPR, pr_id: n, pr_number: 100 + n, pr_state: 'merged', merged_at: '2026-05-21T06:05:00+00:00' }],
});

describe('PRHistoryPanel as PR Campaigns', () => {
  beforeEach(() => {
    mockGetPRCampaigns.mockReset();
    mockMergePullRequest.mockReset();
  });

  test('renders PR Campaigns empty state', async () => {
    mockGetPRCampaigns.mockResolvedValue(baseResponse);

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);

    expect(await screen.findByRole('heading', { name: /PR Campaigns/i })).toBeInTheDocument();
    expect(screen.queryByRole('tablist', { name: /PR Campaigns tabs/i })).not.toBeInTheDocument();
    expect(await screen.findByText('No PR campaigns yet')).toBeInTheDocument();
    expect(screen.getByText(/A PR Campaign is a tracked rollout/i)).toBeInTheDocument();
  });

  test('Active Campaigns tab renders open PRs', async () => {
    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [{
        campaign_id: 'campaign-1',
        campaign_name: 'Update okok.yml',
        campaign_status: 'open',
        project_name: 'history_project',
        project_code: 'HPS',
        created_by: 'aireland1010',
        created_at: '2026-05-21T06:00:00+00:00',
        updated_at: '2026-05-21T06:05:00+00:00',
        completed_at: null,
        target_branches: ['main'],
        workflow_names: ['okok.yml'],
        repositories: ['org/repo'],
        open_count: 1,
        merged_count: 0,
        closed_count: 0,
        failed_count: 0,
        completion_percentage: 0,
        pull_requests: [openPR],
      }],
      pull_requests: [openPR],
      total_campaigns: 1,
      active_campaigns: 1,
      open_prs: 1,
      repositories_affected: 1,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);

    expect(await screen.findByText('Campaign: Update okok.yml')).toBeInTheDocument();
    expect(screen.getByText(/#42/)).toBeInTheDocument();
    expect(screen.getByText('Merge Open PRs')).toBeInTheDocument();
    expect(screen.getByText('Close Open PRs')).toBeInTheDocument();

    // Merge actions are green, refresh stays blue (default), close stays red
    expect(screen.getByRole('button', { name: 'Refresh Status' })).not.toHaveClass('bg-merge');
    expect(screen.getByRole('button', { name: 'Merge Open PRs' })).toHaveClass('bg-merge');
    expect(screen.getByRole('button', { name: 'Merge' })).toHaveClass('bg-merge');
    expect(screen.getByRole('button', { name: 'Close Open PRs' })).toHaveClass('bg-danger');
    expect(screen.getByRole('button', { name: 'Close' })).toHaveClass('bg-danger');
  });

  test('Completed Campaigns tab renders merged and closed PRs without action buttons', async () => {
    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [{
        campaign_id: 'campaign-2',
        campaign_name: 'Update done.yml',
        campaign_status: 'partially_completed',
        project_name: 'history_project',
        project_code: 'HPS',
        created_by: 'historyuser',
        created_at: '2026-05-21T06:00:00+00:00',
        updated_at: '2026-05-21T06:05:00+00:00',
        completed_at: '2026-05-21T06:05:00+00:00',
        target_branches: ['main'],
        workflow_names: ['done.yml'],
        repositories: ['org/repo'],
        open_count: 0,
        merged_count: 1,
        closed_count: 1,
        failed_count: 0,
        completion_percentage: 100,
        pull_requests: [
          { ...openPR, pr_id: 2, pr_number: 43, pr_state: 'merged', merged_at: '2026-05-21T06:05:00+00:00', workflow_names: 'done.yml' },
          { ...openPR, pr_id: 3, pr_number: 44, pr_state: 'closed', closed_at: '2026-05-21T06:05:00+00:00', workflow_names: 'done.yml' },
        ],
      }],
      total_campaigns: 1,
      completed_campaigns: 1,
      merged_prs: 1,
      closed_prs: 1,
      repositories_affected: 1,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);
    await userEvent.click(await screen.findByRole('button', { name: /Completed Campaigns/i }));

    expect(screen.getByText('Campaign: Update done.yml')).toBeInTheDocument();
    expect(screen.queryByText('Merge Open PRs')).not.toBeInTheDocument();
    expect(screen.queryByText('Close Open PRs')).not.toBeInTheDocument();
  });

  test('Completed Campaigns tab cards start collapsed and toggle open/closed on click', async () => {
    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [{
        campaign_id: 'campaign-2',
        campaign_name: 'Update done.yml',
        campaign_status: 'partially_completed',
        project_name: 'history_project',
        project_code: 'HPS',
        created_by: 'historyuser',
        created_at: '2026-05-21T06:00:00+00:00',
        updated_at: '2026-05-21T06:05:00+00:00',
        completed_at: '2026-05-21T06:05:00+00:00',
        target_branches: ['main'],
        workflow_names: ['done.yml'],
        repositories: ['org/repo'],
        open_count: 0,
        merged_count: 1,
        closed_count: 1,
        failed_count: 0,
        completion_percentage: 100,
        pull_requests: [
          { ...openPR, pr_id: 2, pr_number: 43, pr_state: 'merged', merged_at: '2026-05-21T06:05:00+00:00', workflow_names: 'done.yml' },
        ],
      }],
      total_campaigns: 1,
      completed_campaigns: 1,
      merged_prs: 1,
      repositories_affected: 1,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);
    await userEvent.click(await screen.findByRole('button', { name: /Completed Campaigns/i }));

    expect(await screen.findByText('Campaign: Update done.yml')).toBeInTheDocument();
    expect(screen.queryByText(/#43/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('repo-pr-row')).not.toBeInTheDocument();

    const trigger = screen.getByRole('button', { name: /Update done\.yml/i });
    await userEvent.click(trigger);

    expect(await screen.findByText(/#43/)).toBeInTheDocument();

    await userEvent.click(trigger);

    expect(screen.queryByText(/#43/)).not.toBeInTheDocument();
  });

  test('expanding one Completed campaign does not expand a sibling campaign', async () => {
    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [makeCampaign(1), makeCampaign(2)],
      total_campaigns: 2,
      completed_campaigns: 2,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);
    await userEvent.click(await screen.findByRole('button', { name: /Completed Campaigns/i }));
    await screen.findByText('Campaign: Campaign 1');

    await userEvent.click(screen.getByRole('button', { name: /Campaign 1\b/i }));

    expect(await screen.findByText(/#101/)).toBeInTheDocument();
    expect(screen.queryByText(/#102/)).not.toBeInTheDocument();
  });

  test('Completed Campaigns tab paginates and defaults to 5 per page', async () => {
    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: Array.from({ length: 7 }, (_, i) => makeCampaign(i + 1)),
      total_campaigns: 7,
      completed_campaigns: 7,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);
    await userEvent.click(await screen.findByRole('button', { name: /Completed Campaigns/i }));

    expect(await screen.findByText('Campaign: Campaign 1')).toBeInTheDocument();
    expect(screen.getByText('Campaign: Campaign 5')).toBeInTheDocument();
    expect(screen.queryByText('Campaign: Campaign 6')).not.toBeInTheDocument();
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));

    expect(screen.getByText('Campaign: Campaign 6')).toBeInTheDocument();
    expect(screen.getByText('Campaign: Campaign 7')).toBeInTheDocument();
    expect(screen.queryByText('Campaign: Campaign 1')).not.toBeInTheDocument();
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  test('All PRs tab filters campaign activity by repository', async () => {
    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [{
        campaign_id: 'campaign-1',
        campaign_name: 'Update okok.yml',
        campaign_status: 'open',
        project_name: 'history_project',
        project_code: 'HPS',
        created_by: 'aireland1010',
        created_at: '2026-05-21T06:00:00+00:00',
        updated_at: '2026-05-21T06:05:00+00:00',
        completed_at: null,
        target_branches: ['main'],
        workflow_names: ['okok.yml'],
        repositories: ['org/repo', 'org/other'],
        open_count: 2,
        merged_count: 0,
        closed_count: 0,
        failed_count: 0,
        completion_percentage: 0,
        pull_requests: [openPR, { ...openPR, pr_id: 2, repo_name: 'org/other', pr_number: 43 }],
      }],
      pull_requests: [openPR, { ...openPR, pr_id: 2, repo_name: 'org/other', pr_number: 43 }],
      total_campaigns: 1,
      active_campaigns: 1,
      open_prs: 2,
      repositories_affected: 2,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);
    await userEvent.click(await screen.findByRole('button', { name: /All PRs/i }));
    await userEvent.selectOptions(screen.getByDisplayValue('All repositories'), 'org/other');

    await waitFor(() => expect(screen.getByText(/#43/)).toBeInTheDocument());
    expect(screen.queryByText(/#42/)).not.toBeInTheDocument();
  });

  test('All PRs tab paginates the flat PR list, not repo groups', async () => {
    const prs = [
      ...Array.from({ length: 4 }, (_, i) => ({ ...openPR, pr_id: i + 1, pr_number: 100 + i, repo_name: 'org/repo-a' })),
      ...Array.from({ length: 3 }, (_, i) => ({ ...openPR, pr_id: i + 10, pr_number: 200 + i, repo_name: 'org/repo-b' })),
    ];

    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [],
      pull_requests: prs,
      total_campaigns: 1,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);
    await userEvent.click(await screen.findByRole('button', { name: /All PRs/i }));

    expect(await screen.findAllByTestId('repo-pr-row')).toHaveLength(5);
  });

  test('changing page size on the All PRs tab shows more items and hides pagination nav', async () => {
    const prs = Array.from({ length: 7 }, (_, i) => ({ ...openPR, pr_id: i + 1, pr_number: 100 + i }));

    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [],
      pull_requests: prs,
      total_campaigns: 1,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);
    await userEvent.click(await screen.findByRole('button', { name: /All PRs/i }));

    expect(await screen.findAllByTestId('repo-pr-row')).toHaveLength(5);
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByDisplayValue('5'), '25');

    expect(screen.getAllByTestId('repo-pr-row')).toHaveLength(7);
    expect(screen.queryByText(/Page \d+ of \d+/)).not.toBeInTheDocument();
  });

  test('selecting the "All" page size shows every item with no nav controls', async () => {
    const prs = Array.from({ length: 12 }, (_, i) => ({ ...openPR, pr_id: i + 1, pr_number: 100 + i }));

    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [],
      pull_requests: prs,
      total_campaigns: 1,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);
    await userEvent.click(await screen.findByRole('button', { name: /All PRs/i }));

    await userEvent.selectOptions(screen.getByDisplayValue('5'), 'all');

    expect(await screen.findAllByTestId('repo-pr-row')).toHaveLength(12);
    expect(screen.queryByRole('button', { name: 'Previous' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument();
  });

  test('changing a filter on the All PRs tab resets pagination to page 1', async () => {
    const repoAPRs = Array.from({ length: 6 }, (_, i) => ({ ...openPR, pr_id: i + 1, pr_number: 100 + i, repo_name: 'org/repo-a' }));
    const repoBPRs = [{ ...openPR, pr_id: 20, pr_number: 999, repo_name: 'org/repo-b' }];

    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [],
      pull_requests: [...repoAPRs, ...repoBPRs],
      total_campaigns: 1,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);
    await userEvent.click(await screen.findByRole('button', { name: /All PRs/i }));

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByDisplayValue('All repositories'), 'org/repo-b');

    await waitFor(() => expect(screen.getByText(/#999/)).toBeInTheDocument());
    expect(screen.queryByText(/Page \d+ of \d+/)).not.toBeInTheDocument();
  });

  test('merge completion refreshes project state and moves campaign to Completed Campaigns', async () => {
    const onCampaignStateRefresh = vi.fn().mockResolvedValue(undefined);
    mockMergePullRequest.mockResolvedValue({ merged: true });
    mockGetPRCampaigns
      .mockResolvedValueOnce({
        ...baseResponse,
        campaigns: [{
          campaign_id: 'campaign-1',
          campaign_name: 'Update okok.yml',
          campaign_status: 'open',
          project_name: 'history_project',
          project_code: 'HPS',
          created_by: 'aireland1010',
          created_at: '2026-05-21T06:00:00+00:00',
          updated_at: '2026-05-21T06:05:00+00:00',
          completed_at: null,
          target_branches: ['main'],
          workflow_names: ['okok.yml'],
          repositories: ['org/repo'],
          open_count: 1,
          merged_count: 0,
          closed_count: 0,
          failed_count: 0,
          completion_percentage: 0,
          pull_requests: [openPR],
        }],
        pull_requests: [openPR],
        total_campaigns: 1,
        active_campaigns: 1,
        open_prs: 1,
        repositories_affected: 1,
      })
      .mockResolvedValueOnce({
        ...baseResponse,
        campaigns: [{
          campaign_id: 'campaign-1',
          campaign_name: 'Update okok.yml',
          campaign_status: 'completed',
          project_name: 'history_project',
          project_code: 'HPS',
          created_by: 'aireland1010',
          created_at: '2026-05-21T06:00:00+00:00',
          updated_at: '2026-05-21T06:10:00+00:00',
          completed_at: '2026-05-21T06:10:00+00:00',
          target_branches: ['main'],
          workflow_names: ['okok.yml'],
          repositories: ['org/repo'],
          open_count: 0,
          merged_count: 1,
          closed_count: 0,
          failed_count: 0,
          completion_percentage: 100,
          pull_requests: [{ ...openPR, pr_state: 'merged', merged_at: '2026-05-21T06:10:00+00:00' }],
        }],
        pull_requests: [{ ...openPR, pr_state: 'merged', merged_at: '2026-05-21T06:10:00+00:00' }],
        total_campaigns: 1,
        completed_campaigns: 1,
        merged_prs: 1,
        repositories_affected: 1,
      });

    render(
      <PRHistoryPanel
        user="historyuser"
        projectName="history_project"
        onCampaignStateRefresh={onCampaignStateRefresh}
      />
    );

    await screen.findByText('Campaign: Update okok.yml');
    await userEvent.click(screen.getByRole('button', { name: 'Merge' }));
    await userEvent.click(screen.getAllByRole('button', { name: 'Merge Open PRs' }).pop()!);

    await waitFor(() => expect(onCampaignStateRefresh).toHaveBeenCalledWith(false));
    await userEvent.click(screen.getByRole('button', { name: /Completed Campaigns/i }));
    expect(await screen.findByText(/Status:/)).toHaveTextContent('Completed');
    expect(screen.queryByText('Merge Open PRs')).not.toBeInTheDocument();
  });

  test('refresh failure after successful mutation shows the requested warning', async () => {
    mockMergePullRequest.mockResolvedValue({ merged: true });
    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [{
        campaign_id: 'campaign-1',
        campaign_name: 'Update okok.yml',
        campaign_status: 'open',
        project_name: 'history_project',
        project_code: 'HPS',
        created_by: 'aireland1010',
        created_at: '2026-05-21T06:00:00+00:00',
        updated_at: '2026-05-21T06:05:00+00:00',
        completed_at: null,
        target_branches: ['main'],
        workflow_names: ['okok.yml'],
        repositories: ['org/repo'],
        open_count: 1,
        merged_count: 0,
        closed_count: 0,
        failed_count: 0,
        completion_percentage: 0,
        pull_requests: [openPR],
      }],
      pull_requests: [openPR],
      total_campaigns: 1,
      active_campaigns: 1,
      open_prs: 1,
      repositories_affected: 1,
    });

    render(
      <PRHistoryPanel
        user="historyuser"
        projectName="history_project"
        onCampaignStateRefresh={vi.fn().mockRejectedValue(new Error('refresh failed'))}
      />
    );

    await screen.findByText('Campaign: Update okok.yml');
    await userEvent.click(screen.getByRole('button', { name: 'Merge' }));
    await userEvent.click(screen.getAllByRole('button', { name: 'Merge Open PRs' }).pop()!);

    expect(await screen.findByText(/latest project state could not be refreshed/i)).toBeInTheDocument();
  });

  test('workflow filenames without .yml get .yml appended in campaign workflow chips', async () => {
    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [{
        campaign_id: 'campaign-wf',
        campaign_name: 'Update workflows',
        campaign_status: 'open',
        project_name: 'history_project',
        project_code: 'HPS',
        created_by: 'historyuser',
        created_at: '2026-05-21T06:00:00+00:00',
        updated_at: '2026-05-21T06:05:00+00:00',
        completed_at: null,
        target_branches: ['main'],
        workflow_names: ['build', 'deploy.yml', 'test.yaml'],
        repositories: ['org/repo'],
        open_count: 1,
        merged_count: 0,
        closed_count: 0,
        failed_count: 0,
        completion_percentage: 0,
        pull_requests: [openPR],
      }],
      pull_requests: [openPR],
      total_campaigns: 1,
      active_campaigns: 1,
      open_prs: 1,
      repositories_affected: 1,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);

    // Standard workflow without extension gets .yml
    await waitFor(() => {
      expect(screen.getByText(/build\.yml/)).toBeInTheDocument();
    });
    // Workflow with .yml stays as-is
    expect(screen.getByText(/deploy\.yml/)).toBeInTheDocument();
    // Workflow with .yaml gets normalized to .yml
    expect(screen.getByText(/test\.yml/)).toBeInTheDocument();
    // No double extensions
    expect(screen.queryByText(/\.yml\.yml/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\.yaml\.yml/)).not.toBeInTheDocument();
  });

  test('linked reusable workflow filenames display with .yml in grouped PR view', async () => {
    const prWithReusable = {
      ...openPR,
      workflow_names: 'standard_wf, linked_rwx',
    };
    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [{
        campaign_id: 'campaign-rwx',
        campaign_name: 'Update mixed',
        campaign_status: 'open',
        project_name: 'history_project',
        project_code: 'HPS',
        created_by: 'historyuser',
        created_at: '2026-05-21T06:00:00+00:00',
        updated_at: '2026-05-21T06:05:00+00:00',
        completed_at: null,
        target_branches: ['main'],
        workflow_names: ['standard_wf', 'linked_rwx'],
        repositories: ['org/repo'],
        open_count: 1,
        merged_count: 0,
        closed_count: 0,
        failed_count: 0,
        completion_percentage: 0,
        pull_requests: [prWithReusable],
      }],
      pull_requests: [prWithReusable],
      total_campaigns: 1,
      active_campaigns: 1,
      open_prs: 1,
      repositories_affected: 1,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);

    // Both get .yml - standard and linked reusable
    await waitFor(() => {
      expect(screen.getAllByText(/standard_wf\.yml/).length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText(/linked_rwx\.yml/).length).toBeGreaterThan(0);
  });

  test('reusable-workflow PR row is purple; caller PR row is not', async () => {
    // Reusable-workflow PR: is_reusable_workflow_pr=true, source_project_name may be null
    const rwxPR = {
      ...openPR,
      pr_id: 20,
      pr_number: 55,
      repo_name: 'org/rwx-repo',
      source_project_name: null,
      is_reusable_workflow_pr: true,
    };
    // Caller PR: is_reusable_workflow_pr falsy, source_project_name set (cross-project badge only)
    const callerPRWithBadge = {
      ...openPR,
      pr_id: 21,
      pr_number: 56,
      repo_name: 'org/caller-repo',
      source_project_name: 'some-other-project',
      is_reusable_workflow_pr: false,
    };
    const campaign = {
      campaign_id: 'campaign-linked',
      campaign_name: 'Update linked.yml',
      campaign_status: 'open',
      project_name: 'history_project',
      project_code: 'HPS',
      created_by: 'historyuser',
      created_at: '2026-05-21T06:00:00+00:00',
      updated_at: '2026-05-21T06:05:00+00:00',
      completed_at: null,
      target_branches: ['main'],
      workflow_names: ['linked.yml'],
      repositories: ['org/repo', 'org/rwx-repo', 'org/caller-repo'],
      open_count: 3,
      merged_count: 0,
      closed_count: 0,
      failed_count: 0,
      completion_percentage: 0,
      pull_requests: [openPR, rwxPR, callerPRWithBadge],
    };
    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [campaign],
      pull_requests: [openPR, rwxPR, callerPRWithBadge],
      total_campaigns: 1,
      active_campaigns: 1,
      open_prs: 3,
      repositories_affected: 3,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);

    const prRows = await screen.findAllByTestId('repo-pr-row');

    // RWX PR row should have the purple class
    const rwxRow = prRows.find(row => within(row).queryByText(/#55/));
    expect(rwxRow).toBeDefined();
    expect(rwxRow).toHaveClass('pr-campaign-grouped-pr--linked');
    // No source_project_name badge on this row (null)
    expect(within(rwxRow!).queryByText(/🔗/)).not.toBeInTheDocument();

    // Regular caller PR row must NOT be purple
    const regularRow = prRows.find(row => within(row).queryByText(/#42/));
    expect(regularRow).toBeDefined();
    expect(regularRow).not.toHaveClass('pr-campaign-grouped-pr--linked');
    expect(within(regularRow!).queryByText(/🔗/)).not.toBeInTheDocument();

    // Cross-project caller row has badge but NOT the purple row class
    const callerRow = prRows.find(row => within(row).queryByText(/#56/));
    expect(callerRow).toBeDefined();
    expect(callerRow).not.toHaveClass('pr-campaign-grouped-pr--linked');
    expect(within(callerRow!).getByText(/🔗 some-other-project/)).toBeInTheDocument();
  });

  test('reusable-workflow PR row is purple in Completed Campaigns', async () => {
    const rwxPRMerged = {
      ...openPR,
      pr_id: 30,
      pr_number: 60,
      pr_state: 'merged',
      merged_at: '2026-05-21T07:00:00+00:00',
      is_reusable_workflow_pr: true,
      source_project_name: null,
    };
    const callerPRMerged = {
      ...openPR,
      pr_id: 31,
      pr_number: 61,
      pr_state: 'merged',
      merged_at: '2026-05-21T07:00:00+00:00',
      is_reusable_workflow_pr: false,
      source_project_name: null,
    };
    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [{
        campaign_id: 'campaign-done',
        campaign_name: 'Done campaign',
        campaign_status: 'completed',
        project_name: 'history_project',
        project_code: 'HPS',
        created_by: 'historyuser',
        created_at: '2026-05-21T06:00:00+00:00',
        updated_at: '2026-05-21T07:00:00+00:00',
        completed_at: '2026-05-21T07:00:00+00:00',
        target_branches: ['main'],
        workflow_names: ['linked.yml'],
        repositories: ['org/rwx-repo', 'org/caller-repo'],
        open_count: 0,
        merged_count: 2,
        closed_count: 0,
        failed_count: 0,
        completion_percentage: 100,
        pull_requests: [rwxPRMerged, callerPRMerged],
      }],
      total_campaigns: 1,
      completed_campaigns: 1,
      merged_prs: 2,
      repositories_affected: 2,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);
    await userEvent.click(await screen.findByRole('button', { name: /Completed Campaigns/i }));
    await userEvent.click(await screen.findByRole('button', { name: /Done campaign/i }));

    const prRows = await screen.findAllByTestId('repo-pr-row');

    const rwxRow = prRows.find(row => within(row).queryByText(/#60/));
    expect(rwxRow).toBeDefined();
    expect(rwxRow).toHaveClass('pr-campaign-grouped-pr--linked');

    const callerRow = prRows.find(row => within(row).queryByText(/#61/));
    expect(callerRow).toBeDefined();
    expect(callerRow).not.toHaveClass('pr-campaign-grouped-pr--linked');
  });

  test('per-PR file list renders recorded paths and stays hidden when absent', async () => {
    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [{
        campaign_id: 'campaign-files',
        campaign_name: 'Update files',
        campaign_status: 'open',
        project_name: 'history_project',
        project_code: 'HPS',
        created_by: 'historyuser',
        created_at: '2026-05-21T06:00:00+00:00',
        updated_at: '2026-05-21T06:05:00+00:00',
        completed_at: null,
        target_branches: ['main'],
        workflow_names: ['okok.yml'],
        repositories: ['org/repo', 'org/other'],
        open_count: 2,
        merged_count: 0,
        closed_count: 0,
        failed_count: 0,
        completion_percentage: 0,
        pull_requests: [
          { ...openPR, pr_id: 10, file_names: '.github/CODEOWNERS, .github/scripts/setup.sh' },
          { ...openPR, pr_id: 11, pr_number: 43, repo_name: 'org/other', file_names: null },
        ],
      }],
      pull_requests: [
        { ...openPR, pr_id: 10, file_names: '.github/CODEOWNERS, .github/scripts/setup.sh' },
        { ...openPR, pr_id: 11, pr_number: 43, repo_name: 'org/other', file_names: null },
      ],
      total_campaigns: 1,
      active_campaigns: 1,
      open_prs: 2,
      repositories_affected: 2,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);

    const prRows = await screen.findAllByTestId('repo-pr-row');
    expect(within(prRows[0]).getByTestId('repo-pr-files')).toBeInTheDocument();
    expect(within(prRows[0]).getByText('.github/CODEOWNERS')).toBeInTheDocument();
    expect(within(prRows[0]).getByText('.github/scripts/setup.sh')).toBeInTheDocument();
    expect(within(prRows[1]).queryByTestId('repo-pr-files')).not.toBeInTheDocument();
  });

  test('campaign PR cards use theme-aware classes without hardcoded light backgrounds', async () => {
    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [{
        campaign_id: 'campaign-theme',
        campaign_name: 'Theme test',
        campaign_status: 'open',
        project_name: 'history_project',
        project_code: 'HPS',
        created_by: 'historyuser',
        created_at: '2026-05-21T06:00:00+00:00',
        updated_at: '2026-05-21T06:05:00+00:00',
        completed_at: null,
        target_branches: ['main'],
        workflow_names: ['test.yml'],
        repositories: ['org/repo'],
        open_count: 1,
        merged_count: 0,
        closed_count: 0,
        failed_count: 0,
        completion_percentage: 0,
        pull_requests: [openPR],
      }],
      pull_requests: [openPR],
      total_campaigns: 1,
      active_campaigns: 1,
      open_prs: 1,
      repositories_affected: 1,
    });

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);

    await waitFor(() => {
      expect(screen.getByText('Campaign: Theme test')).toBeInTheDocument();
    });
    // Verify campaign cards use CSS class-based styling (no inline white backgrounds)
    const cards = document.querySelectorAll('.pr-campaign-card');
    expect(cards.length).toBeGreaterThan(0);
    cards.forEach((card) => {
      expect((card as HTMLElement).style.background).not.toBe('white');
      expect((card as HTMLElement).style.backgroundColor).not.toBe('white');
    });
    // Verify grouped PR elements exist with proper class names
    const groupedPRs = document.querySelectorAll('.pr-campaign-grouped-pr');
    expect(groupedPRs.length).toBeGreaterThan(0);
    groupedPRs.forEach((el) => {
      expect((el as HTMLElement).style.background).not.toBe('white');
      expect((el as HTMLElement).style.backgroundColor).not.toBe('white');
    });
  });

  describe('creation-time snapshot', () => {
    const snapshotCampaign = {
      campaign_id: 'campaign-9',
      campaign_name: 'Snapshot rollout',
      campaign_status: 'open',
      project_name: 'history_project',
      project_code: 'HPS',
      created_by: 'aireland1010',
      created_at: '2026-05-21T06:00:00+00:00',
      updated_at: '2026-05-21T06:05:00+00:00',
      completed_at: null,
      target_branches: ['main'],
      workflow_names: ['okok.yml'],
      repositories: ['org/repo'],
      open_count: 1,
      merged_count: 0,
      closed_count: 0,
      failed_count: 0,
      completion_percentage: 0,
      pull_requests: [openPR],
      target_repos: ['org/repo', 'org/skipped'],
      base_commits: {
        'org/repo on main': '4f2a91c3d5e7b90a1c2d3e4f5a6b7c8d9e0f1a2b',
        'org/skipped on main': '88de1039f2a4b6c8d0e2f4a6b8c0d2e4f6a8b0c2',
      },
      target_pr_urls: {
        'org/repo on main': 'https://github.com/org/repo/pull/42',
      },
      branch_protection: {
        'org/repo on main': {
          status: 'protected',
          required_reviews: 2,
          required_status_checks: ['ci/test', 'lint'],
          enforce_admins: true,
        },
        'org/skipped on main': { status: 'none' },
      },
      policy_version: {
        'okok.yml': { version: 7, sha256: 'a1b2c3d4e5f6a7b8' },
        'never-saved.yml': { version: null, sha256: '9f8e7d6c5b4a3210' },
      },
    };

    const renderSnapshot = (campaignOverrides: Partial<PRCampaign> = {}) => {
      mockGetPRCampaigns.mockResolvedValue({
        ...baseResponse,
        campaigns: [{ ...snapshotCampaign, ...campaignOverrides }],
        pull_requests: [openPR],
        total_campaigns: 1,
        active_campaigns: 1,
        open_prs: 1,
        repositories_affected: 1,
      });
      render(<PRHistoryPanel user="historyuser" projectName="history_project" />);
    };

    test('a snapshotted target that produced no PR still shows, with its base commit', async () => {
      renderSnapshot();

      expect(await screen.findByText('Campaign: Snapshot rollout')).toBeInTheDocument();
      expect(screen.getByText('org/skipped')).toBeInTheDocument();
      expect(screen.getByTestId('repo-no-pr-row')).toHaveTextContent('No PR opened');
      expect(screen.getByText('base main 4f2a91c')).toBeInTheDocument();
      expect(screen.getByText('base main 88de103')).toBeInTheDocument();
    });

    test('the base line names the branch, since each repo has its own default', async () => {
      renderSnapshot({
        base_commits: { 'org/repo on release/2026': '4f2a91c3d5e7b90a1c2d3e4f5a6b7c8d9e0f1a2b' },
        target_repos: ['org/repo'],
      });

      expect(await screen.findByText('base release/2026 4f2a91c')).toBeInTheDocument();
    });

    test('repositories affected shows the shortfall when a target opened no PR', async () => {
      renderSnapshot();

      expect(await screen.findByText('1 of 2 targeted')).toBeInTheDocument();
      expect(screen.queryByText('Targets at creation')).not.toBeInTheDocument();
    });

    test('remaining to merge counts the still-open PRs', async () => {
      renderSnapshot();

      expect(await screen.findByText('Remaining to merge')).toBeInTheDocument();
      const tile = screen.getByText('Remaining to merge').closest('div');
      expect(tile).toHaveTextContent('1');
    });

    test('target branch shows the configured mode, not the resolved branch', async () => {
      renderSnapshot({ branch_option: 'default' as const });

      expect(await screen.findByText('Default branch')).toBeInTheDocument();
    });

    test('target branch falls back to the resolved branches when the mode is absent', async () => {
      renderSnapshot();

      expect(await screen.findByText('Campaign: Snapshot rollout')).toBeInTheDocument();
      const tile = screen.getByText('Target branch').closest('div');
      expect(tile).toHaveTextContent('main');
    });

    test('the applied version rides on the existing workflow chip, not a second row', async () => {
      renderSnapshot();

      await screen.findByText('Campaign: Snapshot rollout');
      // okok.yml is both a delivered workflow and a snapshotted one — it must
      // render once, carrying its version, rather than as two separate chips.
      const chips = [...document.querySelectorAll('.pr-history-workflow-chip')];
      const okok = chips.filter((chip) => chip.textContent?.includes('okok.yml'));
      expect(okok).toHaveLength(1);
      expect(okok[0]).toHaveTextContent('okok.yml · v7');
      expect(okok[0].getAttribute('title')).toContain('sha256 a1b2c3d4e5f6a7b8');
    });

    test('a snapshotted workflow with no chip of its own still renders', async () => {
      renderSnapshot();

      await screen.findByText('Campaign: Snapshot rollout');
      // never-saved.yml has no version, so it falls back to its content hash.
      const chips = [...document.querySelectorAll('.pr-history-workflow-chip')];
      expect(chips.some((chip) => chip.textContent?.includes('never-saved.yml · 9f8e7d6'))).toBe(true);
    });

    test('a campaign without a snapshot renders exactly as it did before', async () => {
      // Open, so the accordion is expanded by default — a completed campaign
      // renders nothing until clicked, which would make these checks vacuous.
      mockGetPRCampaigns.mockResolvedValue({
        ...baseResponse,
        campaigns: [{ ...makeCampaign(1), campaign_status: 'open' }],
        pull_requests: [],
        total_campaigns: 1,
        active_campaigns: 1,
      });
      render(<PRHistoryPanel user="historyuser" projectName="history_project" />);

      expect(await screen.findByText('Campaign: Campaign 1')).toBeInTheDocument();
      expect(screen.queryByTestId('repo-no-pr-row')).not.toBeInTheDocument();
      expect(screen.queryByTestId('repo-snapshot-line')).not.toBeInTheDocument();
      // No snapshot, so the workflow chip carries no version suffix.
      const chips = [...document.querySelectorAll('.pr-history-workflow-chip')];
      expect(chips.map((chip) => chip.textContent)).toEqual(['🔀 done.yml']);
    });

    test('the repo header carries the PR link and protection summary', async () => {
      renderSnapshot();

      await screen.findByText('Campaign: Snapshot rollout');
      const lines = screen.getAllByTestId('repo-snapshot-line');
      const protectedLine = lines.find((el) => el.textContent?.includes('4f2a91c'))!;
      expect(within(protectedLine).getByRole('link', { name: 'PR #42' }))
        .toHaveAttribute('href', 'https://github.com/org/repo/pull/42');
      expect(protectedLine).toHaveTextContent('2 reviews');
      expect(protectedLine).toHaveTextContent('checks: ci/test, lint');
      expect(protectedLine).toHaveTextContent('admins enforced');
    });

    test('an unprotected target reads as no protection, not as unreadable', async () => {
      renderSnapshot();

      await screen.findByText('Campaign: Snapshot rollout');
      const lines = screen.getAllByTestId('repo-snapshot-line');
      const skipped = lines.find((el) => el.textContent?.includes('88de103'))!;
      expect(skipped).toHaveTextContent('no branch protection');
      expect(skipped).not.toHaveTextContent('protection unreadable');
      expect(within(skipped).queryByRole('link')).not.toBeInTheDocument();
    });

    test('a target whose protection could not be read is called out separately', async () => {
      mockGetPRCampaigns.mockResolvedValue({
        ...baseResponse,
        campaigns: [{
          ...snapshotCampaign,
          branch_protection: {
            'org/repo on main': { status: 'unknown', error: '403 Resource not accessible' },
          },
        }],
        pull_requests: [openPR],
        total_campaigns: 1,
        active_campaigns: 1,
        open_prs: 1,
        repositories_affected: 1,
      });
      render(<PRHistoryPanel user="historyuser" projectName="history_project" />);

      await screen.findByText('Campaign: Snapshot rollout');
      expect(screen.getByText('protection unreadable'))
        .toHaveAttribute('title', '403 Resource not accessible');
    });

    test('a named campaign shows its description', async () => {
      mockGetPRCampaigns.mockResolvedValue({
        ...baseResponse,
        campaigns: [{
          ...snapshotCampaign,
          campaign_name: 'Q3 security rollout',
          campaign_description: 'Pinning all actions to commit SHAs.',
        }],
        pull_requests: [openPR],
        total_campaigns: 1,
        active_campaigns: 1,
        open_prs: 1,
      });
      render(<PRHistoryPanel user="historyuser" projectName="history_project" />);

      expect(await screen.findByText('Q3 security rollout', { selector: 'h3' })).toBeInTheDocument();
      expect(screen.getByText('Pinning all actions to commit SHAs.')).toBeInTheDocument();
    });

    test('a campaign with no description renders none', async () => {
      renderSnapshot();

      await screen.findByText('Campaign: Snapshot rollout');
      expect(document.querySelector('.pr-campaign-description')).toBeNull();
    });
  });
});

describe('campaign rollback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /** Active campaigns render expanded, so the card body is visible without a click. */
  const activeCampaign = (overrides: Record<string, unknown> = {}) => ({
    ...makeCampaign(1),
    campaign_id: 'campaign-1',
    campaign_name: 'Bump runners',
    campaign_status: 'open',
    open_count: 1,
    merged_count: 1,
    ...overrides,
  });

  const renderWith = (campaigns: Record<string, unknown>[]) => {
    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns,
      pull_requests: [openPR],
      total_campaigns: campaigns.length,
      active_campaigns: campaigns.length,
    });
    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);
  };

  test('a campaign with merged PRs offers a rollback', async () => {
    renderWith([activeCampaign()]);

    expect(await screen.findByTestId('rollback-campaign-button')).toBeInTheDocument();
  });

  test('a campaign with nothing merged offers no rollback', async () => {
    renderWith([activeCampaign({ merged_count: 0, open_count: 2 })]);

    await screen.findByText('Campaign: Bump runners');
    expect(screen.queryByTestId('rollback-campaign-button')).not.toBeInTheDocument();
  });

  test('the header rollback control sits beside the toggle, not inside it', async () => {
    const user = userEvent.setup();
    renderWith([activeCampaign()]);

    const eyebrow = await screen.findByText('Campaign: Bump runners');
    const accordionTrigger = eyebrow.closest('[data-state]') as HTMLElement;
    const rollback = screen.getByTestId('rollback-campaign-button');

    // A <button> nested in the trigger's <button> is invalid markup and trips
    // typescript:S6819 when faked with role="button".
    expect(rollback.tagName).toBe('BUTTON');
    expect(accordionTrigger.contains(rollback)).toBe(false);

    // ...and clicking it must not toggle the card shut behind the modal.
    expect(accordionTrigger).toHaveAttribute('data-state', 'open');
    await user.click(rollback);
    expect(accordionTrigger).toHaveAttribute('data-state', 'open');
  });

  test('a rollback campaign names the campaign it reverts, and vice versa', async () => {
    renderWith([
      activeCampaign(),
      activeCampaign({
        campaign_id: 'campaign-2',
        campaign_name: 'Rollback of Bump runners',
        rollback_of_campaign_id: 1,
        rollback_am_action: 'revert',
      }),
    ]);

    expect(await screen.findByTestId('rollback-of-badge'))
      .toHaveTextContent('Rollback of Bump runners');
    expect(screen.getByTestId('rolled-back-by-badge'))
      .toHaveTextContent('Rolled back by Rollback of Bump runners');
  });

  test('an ordinary campaign shows neither rollback link', async () => {
    renderWith([activeCampaign()]);

    await screen.findByText('Campaign: Bump runners');
    expect(screen.queryByTestId('rollback-of-badge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('rolled-back-by-badge')).not.toBeInTheDocument();
  });

  test('the rollback button opens the review modal', async () => {
    const user = userEvent.setup();
    renderWith([activeCampaign()]);

    await user.click(await screen.findByTestId('rollback-campaign-button'));

    expect(await screen.findByText('Roll back Bump runners')).toBeInTheDocument();
  });
});

describe('rollback result reporting', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const campaign = {
    ...makeCampaign(1),
    campaign_id: 'campaign-1',
    campaign_name: 'Bump runners',
    campaign_status: 'open',
    open_count: 1,
    merged_count: 1,
  };

  const openModalAndConfirm = async (createResult: Record<string, unknown>) => {
    const user = userEvent.setup();
    mockGetPRCampaigns.mockResolvedValue({
      ...baseResponse,
      campaigns: [campaign],
      pull_requests: [openPR],
      total_campaigns: 1,
      active_campaigns: 1,
    });
    (previewCampaignRollback as Mock).mockResolvedValue({
      campaign_id: 1,
      campaign_name: 'Bump runners',
      invertible_count: 1,
      targets: [{
        repo_name: 'org/repo', target_branch: 'main', pr_number: 42,
        pr_url: 'https://github.com/org/repo/pull/42', workflow_names: 'ci',
        invertible: true, reason: null,
        files: [{ path: '.github/workflows/ci.yml', action: 'restore', before: 'a\n', after: 'b\n' }],
      }],
    });
    (createCampaignRollback as Mock).mockResolvedValue(createResult);

    render(<PRHistoryPanel user="historyuser" projectName="history_project" />);
    await user.click(await screen.findByTestId('rollback-campaign-button'));
    await user.click(await screen.findByTestId('rollback-confirm'));
  };

  test('a rollback that opened no PRs is reported as a failure, not a success', async () => {
    await openModalAndConfirm({
      campaign_id: null,
      prs_created: 0,
      results: { 'org/repo on main': { status: 'error', error: 'Some files could not be committed' } },
      skipped: [],
    });

    expect(await screen.findByText(/No rollback pull requests were opened/)).toBeInTheDocument();
    expect(screen.getByText(/Some files could not be committed/)).toBeInTheDocument();
    expect(document.querySelector('.pr-campaign-success')).toBeNull();
  });

  test('a partial rollback reports the successes and the failures together', async () => {
    await openModalAndConfirm({
      campaign_id: 9,
      prs_created: 1,
      results: {
        'org/repo on main': { status: 'pr_created', pr_number: 101 },
        'org/other on main': { status: 'error', error: 'branch missing' },
      },
      skipped: [{ repo_name: 'org/third', target_branch: 'main', reason: 'changed since merge' }],
      aborted: null,
    });

    const success = await screen.findByText(/Rollback campaign opened with 1 pull request\./);
    expect(success).toHaveTextContent('1 repository was skipped as non-invertible');
    expect(success).toHaveTextContent('org/other on main: branch missing');
  });

  test('delivery that stopped early says so', async () => {
    await openModalAndConfirm({
      campaign_id: 9,
      prs_created: 1,
      results: { 'org/repo on main': { status: 'pr_created', pr_number: 101 } },
      skipped: [],
      aborted: 'org/other: RateLimitExceeded: API rate limit exceeded',
    });

    expect(await screen.findByText(/Delivery stopped early at org\/other/)).toBeInTheDocument();
  });
});
