import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import PRHistoryPanel from './PRHistoryPanel';
import { getPRCampaigns, mergePullRequest } from '../api/pullRequests';

vi.mock('../api/pullRequests', () => ({
  getPRCampaigns: jest.fn(),
  mergePullRequest: jest.fn(),
  closePullRequest: jest.fn(),
}));

const mockGetPRCampaigns = getPRCampaigns as jest.Mock;
const mockMergePullRequest = mergePullRequest as jest.Mock;

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
    const onCampaignStateRefresh = jest.fn().mockResolvedValue(undefined);
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
        onCampaignStateRefresh={jest.fn().mockRejectedValue(new Error('refresh failed'))}
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
});
