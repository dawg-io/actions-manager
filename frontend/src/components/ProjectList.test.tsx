import React from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import ProjectList from './ProjectList';

// --- Mocks ---
const mockNavigate = jest.fn();

vi.mock(
  'react-router',
  () => ({
    useNavigate: () => mockNavigate,
  }),
  { virtual: true } // <-- this tells Jest not to look for a real package
);

function renderedOrder(): string[] {
  return screen
    .getAllByTestId(/^project-row-/)
    .map((el) => (el as HTMLElement).dataset.testid!.replace('project-row-', ''));
}

describe('ProjectList', () => {
  const user = userEvent.setup();

  let logSpy: jest.SpyInstance;
  let errorSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    mockNavigate.mockResolvedValue(undefined);

    // Silence console.log/error during tests
    logSpy = jest.spyOn(console, 'log').mockImplementation(() => {});
    errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    logSpy.mockRestore();
    errorSpy.mockRestore();
  });

  function renderProjectList(extraProps: Partial<React.ComponentProps<typeof ProjectList>> = {}) {
    const defaultProps: React.ComponentProps<typeof ProjectList> = {
      user: 'alice',
      projects: [
        { id: 1, project_name: 'Alpha', project_code: 'ALPHA', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-06-01T00:00:00Z', pr_state: 'draft' },
        { id: 2, project_name: 'Beta', project_code: 'BETA', created_at: '2024-03-01T00:00:00Z', updated_at: '2024-05-01T00:00:00Z', pr_state: 'open' },
      ],
    };

    render(<ProjectList {...defaultProps} {...extraProps} />);
  }

  test('clicking a project navigates to the project URL', async () => {
    renderProjectList();

    const alphaRow = screen.getByTestId('project-row-Alpha');
    await user.click(within(alphaRow).getByRole('button', { name: /open project alpha/i }));

    expect(mockNavigate).toHaveBeenCalledWith('/project/alice/Alpha');
  });

  test('does not render a redundant Open button in the actions column', () => {
    renderProjectList();
    expect(screen.queryByTestId('project-open-Alpha')).not.toBeInTheDocument();
  });

  test('renders projects as a responsive two-column card grid', () => {
    renderProjectList();

    const grid = screen.getByTestId('project-row-Alpha').parentElement;
    expect(grid).toHaveClass('grid');
    expect(grid).toHaveClass('sm:grid-cols-2');
    expect(screen.getByTestId('project-row-Alpha')).toBeInTheDocument();
    expect(screen.getByTestId('project-row-Beta')).toBeInTheDocument();
  });

  test('no user -> does not navigate when clicking a project', async () => {
    renderProjectList({ user: undefined });

    const projectRow = screen.getByTestId('project-row-Alpha');
    await user.click(within(projectRow).getByRole('button', { name: /open project alpha/i }));

    expect(mockNavigate).not.toHaveBeenCalled();

    // assert error log
    expect(errorSpy).toHaveBeenCalledWith('❌ Error: GitHub user is missing!');
  });

  describe('Project Color Accent', () => {
    test('applies the project_color as a tinted icon background and icon color', () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Purple', project_code: 'P1', updated_at: '2024-01-01T00:00:00Z', project_color: 'purple' as any },
        ],
      });

      const iconContainer = screen.getByTestId('project-icon-1');
      expect(iconContainer.className).toContain('bg-purple-500/10');
      expect(iconContainer.querySelector('svg')?.getAttribute('class')).toContain('text-purple-500');
    });

    test('falls back to blue when project_color is missing or unknown', () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Missing', project_code: 'M1', updated_at: '2024-01-01T00:00:00Z' },
          { id: 2, project_name: 'Unknown', project_code: 'U1', updated_at: '2024-01-01T00:00:00Z', project_color: 'magenta' as any },
        ],
      });

      expect(screen.getByTestId('project-icon-1').className).toContain('bg-blue-500/10');
      expect(screen.getByTestId('project-icon-2').className).toContain('bg-blue-500/10');
    });
  });

  describe('Project Status Filter Pills', () => {
    test('shows counts derived from loaded project states', () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Synced Project', project_code: 'SYNC', updated_at: '2024-01-01T00:00:00Z', pr_state: 'synced', drift_status: 'clean' },
          { id: 2, project_name: 'Draft Project', project_code: 'DRFT', updated_at: '2024-01-01T00:00:00Z', pr_state: 'draft', drift_status: 'clean' },
          { id: 3, project_name: 'New Project', project_code: 'NEW', updated_at: '2024-01-01T00:00:00Z', pr_state: 'new', drift_status: 'clean' },
          { id: 4, project_name: 'Review Project', project_code: 'OPEN', updated_at: '2024-01-01T00:00:00Z', pr_state: 'open', drift_status: 'clean' },
          {
            id: 5,
            project_name: 'Drifted Project',
            project_code: 'DRFTD',
            updated_at: '2024-01-01T00:00:00Z',
            pr_state: 'synced',
            drift_status: 'drifted',
            workflows: [{ name: 'deploy.yml', content: '', isReusable: false, workflowStatus: 'drifted' }],
          },
        ],
      });

      expect(within(screen.getByTestId('project-status-pill-all')).getByText('5')).toBeInTheDocument();
      expect(within(screen.getByTestId('project-status-pill-synced')).getByText('1')).toBeInTheDocument();
      expect(within(screen.getByTestId('project-status-pill-draft')).getByText('2')).toBeInTheDocument();
      expect(within(screen.getByTestId('project-status-pill-review')).getByText('1')).toBeInTheDocument();
      expect(within(screen.getByTestId('project-status-pill-needs_attention')).getByText('1')).toBeInTheDocument();
    });

    test('counts one drifted project even when multiple workflows are drifted', () => {
      renderProjectList({
        projects: [
          {
            id: 1,
            project_name: 'Drifted Twice',
            project_code: 'DR2',
            updated_at: '2024-01-01T00:00:00Z',
            pr_state: 'synced',
            drift_status: 'drifted',
            drift_count: 2,
            workflows: [
              { name: 'deploy.yml', content: '', isReusable: false, workflowStatus: 'drifted' },
              { name: 'release.yml', content: '', isReusable: false, workflowStatus: 'drifted' },
            ],
          },
        ],
      });

      expect(within(screen.getByTestId('project-status-pill-needs_attention')).getByText('1')).toBeInTheDocument();
    });

    test('shows zero counts when there are no projects', () => {
      renderProjectList({ projects: [] });

      expect(within(screen.getByTestId('project-status-pill-all')).getByText('0')).toBeInTheDocument();
      expect(within(screen.getByTestId('project-status-pill-synced')).getByText('0')).toBeInTheDocument();
      expect(within(screen.getByTestId('project-status-pill-draft')).getByText('0')).toBeInTheDocument();
      expect(within(screen.getByTestId('project-status-pill-review')).getByText('0')).toBeInTheDocument();
      expect(within(screen.getByTestId('project-status-pill-needs_attention')).getByText('0')).toBeInTheDocument();
    });

    test('keeps synced pill count aligned with synced row state when drift is unknown', () => {
      renderProjectList({
        projects: [
          {
            id: 1,
            project_name: 'Unchecked Sync',
            project_code: 'USYNC',
            updated_at: '2024-01-01T00:00:00Z',
            pr_state: 'synced',
            drift_status: 'unknown',
          },
        ],
      });

      expect(within(screen.getByTestId('project-status-pill-synced')).getByText('1')).toBeInTheDocument();
      expect(within(screen.getByTestId('project-status-1')).getByText('Synced')).toBeInTheDocument();
    });
  });

  describe('Status Filter Pills and Select Stay In Sync', () => {
    test('clicking a pill updates the status select value and filters cards', async () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Drafty', project_code: 'D1', updated_at: '2024-01-01T00:00:00Z', pr_state: 'draft' },
          { id: 2, project_name: 'Syncedy', project_code: 'S1', updated_at: '2024-01-01T00:00:00Z', pr_state: 'synced' },
        ],
      });

      await user.click(screen.getByTestId('project-status-pill-synced'));

      expect(screen.getByTestId('project-status-filter')).toHaveValue('synced');
      expect(screen.getByTestId('project-status-pill-synced')).toHaveAttribute('aria-pressed', 'true');
      expect(screen.getByTestId('projects-filtered-count')).toHaveTextContent('Showing 1 of 2');
      expect(screen.getByTestId('project-row-Syncedy')).toBeInTheDocument();
      expect(screen.queryByTestId('project-row-Drafty')).not.toBeInTheDocument();
    });

    test('selecting a status option updates the matching pill', async () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Drafty', project_code: 'D1', updated_at: '2024-01-01T00:00:00Z', pr_state: 'draft' },
        ],
      });

      await user.selectOptions(screen.getByTestId('project-status-filter'), 'draft');
      expect(screen.getByTestId('project-status-pill-draft')).toHaveAttribute('aria-pressed', 'true');
    });

    test('clicking the active pill again clears the status filter back to All', async () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Drafty', project_code: 'D1', updated_at: '2024-01-01T00:00:00Z', pr_state: 'draft' },
          { id: 2, project_name: 'Syncedy', project_code: 'S1', updated_at: '2024-01-01T00:00:00Z', pr_state: 'synced' },
        ],
      });

      await user.click(screen.getByTestId('project-status-pill-draft'));
      expect(screen.getByTestId('projects-filtered-count')).toHaveTextContent('Showing 1 of 2');

      await user.click(screen.getByTestId('project-status-pill-draft'));
      expect(screen.getByTestId('project-status-filter')).toHaveValue('all');
      expect(screen.getByTestId('projects-filtered-count')).toHaveTextContent('Showing 2 of 2');
    });
  });

  describe('PR Status Column', () => {
    test('displays "Draft" status for projects in draft state', () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Test Project', project_code: 'TEST', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z', pr_state: 'draft' }
        ]
      });

      expect(within(screen.getByTestId('project-status-1')).getByText('Draft')).toBeInTheDocument();
    });

    test('displays "Under Review" status for projects with open PRs', () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Test Project', project_code: 'TEST', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z', pr_state: 'open' }
        ]
      });

      expect(within(screen.getByTestId('project-status-1')).getByText('Under Review')).toBeInTheDocument();
    });

    test('defaults to "New" when pr_state is missing', () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Test Project', project_code: 'TEST', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }
        ]
      });

      expect(within(screen.getByTestId('project-status-1')).getByText('New')).toBeInTheDocument();
    });

    test('shows correct statuses for multiple projects with different states', () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Project A', project_code: 'PRJA', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z', pr_state: 'new' },
          { id: 2, project_name: 'Project B', project_code: 'PRJB', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z', pr_state: 'open' },
          { id: 3, project_name: 'Project C', project_code: 'PRJC', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z', pr_state: 'draft' },
          { id: 4, project_name: 'Project D', project_code: 'PRJD', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z', pr_state: 'synced' }
        ]
      });

      expect(within(screen.getByTestId('project-status-1')).getByText('New')).toBeInTheDocument();
      expect(within(screen.getByTestId('project-status-2')).getByText('Under Review')).toBeInTheDocument();
      expect(within(screen.getByTestId('project-status-3')).getByText('Draft')).toBeInTheDocument();
      expect(within(screen.getByTestId('project-status-4')).getByText('Synced')).toBeInTheDocument();
    });

    test('displays "Drift Detected" when workflows report drift', () => {
      renderProjectList({
        projects: [
          {
            id: 1,
            project_name: 'Drifty',
            project_code: 'DRIFT',
            updated_at: '2024-01-01T00:00:00Z',
            pr_state: 'synced',
            workflows: [{ name: 'deploy.yml', content: '', isReusable: false, workflowStatus: 'drifted' }],
          },
        ],
      });

      expect(within(screen.getByTestId('project-status-1')).getByText('Drift Detected')).toBeInTheDocument();
    });

    test('shows a subtle "Not checked" drift indicator for unknown cached drift status', () => {
      renderProjectList({
        projects: [
          {
            id: 1,
            project_name: 'Unchecked',
            project_code: 'UNCHK',
            updated_at: '2024-01-01T00:00:00Z',
            pr_state: 'synced',
            drift_status: 'unknown',
          },
        ],
      });

      expect(screen.getByTestId('project-drift-indicator-1')).toHaveTextContent('Not checked');
    });

    test('shows the last drift check time on the card when it has been checked', () => {
      renderProjectList({
        projects: [
          {
            id: 1,
            project_name: 'Checked',
            project_code: 'CHKD',
            updated_at: '2024-01-01T00:00:00Z',
            pr_state: 'synced',
            drift_status: 'clean',
            last_drift_check_at: '2024-03-05T12:30:00Z',
          },
        ],
      });

      expect(screen.getByTestId('project-drift-checked-1')).toHaveTextContent(
        new Date('2024-03-05T12:30:00Z').toLocaleString(),
      );
    });

    test('omits the last drift check time when the project has never been checked', () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Never', project_code: 'NVR', updated_at: '2024-01-01T00:00:00Z', pr_state: 'new' },
        ],
      });

      expect(screen.queryByTestId('project-drift-checked-1')).not.toBeInTheDocument();
    });

    test('displays "Needs Sync" when workflows report failed sync', () => {
      renderProjectList({
        projects: [
          {
            id: 1,
            project_name: 'NeedsSync',
            project_code: 'SYNC',
            updated_at: '2024-01-01T00:00:00Z',
            pr_state: 'synced',
            drift_status: 'unknown',
            workflows: [{ name: 'deploy.yml', content: '', isReusable: false, workflowStatus: 'failed_sync' }],
          },
        ],
      });

      expect(within(screen.getByTestId('project-status-1')).getByText('Needs Sync')).toBeInTheDocument();
      expect(within(screen.getByTestId('project-status-pill-needs_attention')).getByText('1')).toBeInTheDocument();
    });
  });

  describe('Scope Column', () => {
    test('renders scope metadata in the project item', () => {
      renderProjectList();
      expect(within(screen.getByTestId('project-scope-1')).getByText(/Public/i)).toBeInTheDocument();
    });

    test('shows "Public" and "Prefix" when visibility is public and use_prefix is true', () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'WithPrefix', project_code: 'WP', updated_at: '2024-01-01T00:00:00Z', repository_visibility_scope: 'public', use_prefix: true },
        ],
      });
      const scope = screen.getByTestId('project-scope-1');
      expect(scope).toHaveTextContent(/Public/i);
      expect(scope).toHaveTextContent(/Prefix/i);
    });

    test('shows "Private" and "No Prefix" when visibility is private and use_prefix is false', () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'NoPrefix', project_code: 'NP', updated_at: '2024-01-01T00:00:00Z', repository_visibility_scope: 'private', use_prefix: false },
        ],
      });
      const scope = screen.getByTestId('project-scope-1');
      expect(scope).toHaveTextContent(/Private/i);
      expect(scope).toHaveTextContent(/No Prefix/i);
    });

    test('defaults to "Prefix" when use_prefix is missing', () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Default', project_code: 'DEF', updated_at: '2024-01-01T00:00:00Z' },
        ],
      });
      const scope = screen.getByTestId('project-scope-1');
      expect(scope).toHaveTextContent(/Prefix/i);
    });
  });

  describe('Workflows Column', () => {
    test('renders workflow metadata in the updated section', () => {
      renderProjectList();
      expect(within(screen.getByTestId('project-workflows-1')).getByText(/No workflows/i)).toBeInTheDocument();
    });

    test('renders state-aware workflow counts with correct pluralization', () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Zero', project_code: 'Z', updated_at: '2024-01-01T00:00:00Z', workflow_count: 0 },
          { id: 2, project_name: 'One', project_code: 'O', updated_at: '2024-01-01T00:00:00Z', workflow_count: 1 },
          { id: 3, project_name: 'Many', project_code: 'M', updated_at: '2024-01-01T00:00:00Z', workflow_count: 3 },
        ],
      });

      const zeroCell = screen.getByTestId('project-workflows-1');
      const oneCell = screen.getByTestId('project-workflows-2');
      const manyCell = screen.getByTestId('project-workflows-3');

      const zeroText = within(zeroCell).getByText('No workflows');
      expect(zeroText).toHaveClass('text-slate-500');

      expect(within(oneCell).getByText('1 workflow')).toBeInTheDocument();
      expect(within(manyCell).getByText('3 workflows')).toBeInTheDocument();
    });
  });

  describe('Accessibility and Keyboard Navigation', () => {
    test('ellipsis menu trigger is keyboard accessible', async () => {
      renderProjectList();

      const moreButton = screen.getByTestId('project-more-Alpha');
      expect(moreButton.tagName).toBe('BUTTON');

      moreButton.focus();
      await user.keyboard('{Enter}');

      expect(screen.getByTestId('project-action-continue-editing')).toBeInTheDocument();
    });
  });

  describe('Search and Filters Toolbar', () => {
    test('filters by project name search', async () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Alpha', project_code: 'ALPHA', updated_at: '2024-01-01T00:00:00Z', pr_state: 'draft' },
          { id: 2, project_name: 'Beta', project_code: 'BETA', updated_at: '2024-01-01T00:00:00Z', pr_state: 'open' },
          { id: 3, project_name: 'Gamma', project_code: 'GAMMA', updated_at: '2024-01-01T00:00:00Z', pr_state: 'synced' },
        ],
      });

      await user.type(screen.getByTestId('project-search-input'), 'ga');

      expect(screen.getByTestId('projects-filtered-count')).toHaveTextContent('Showing 1 of 3');
      expect(screen.queryByTestId('project-row-Alpha')).not.toBeInTheDocument();
      expect(screen.queryByTestId('project-row-Beta')).not.toBeInTheDocument();
      expect(screen.getByTestId('project-row-Gamma')).toBeInTheDocument();
    });

    test('filters by type, visibility, naming mode, and status', async () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'StdPublicPrefix', project_code: 'S1', updated_at: '2024-01-01T00:00:00Z', project_type: 'standard', repository_visibility_scope: 'public', use_prefix: true, pr_state: 'draft' },
          { id: 2, project_name: 'RwxPrivateNoPrefix', project_code: 'R1', updated_at: '2024-01-01T00:00:00Z', project_type: 'rwx', repository_visibility_scope: 'private', use_prefix: false, pr_state: 'open' },
          { id: 3, project_name: 'StdPublicSynced', project_code: 'S2', updated_at: '2024-01-01T00:00:00Z', project_type: 'standard', repository_visibility_scope: 'public', use_prefix: true, pr_state: 'synced' },
        ],
      });

      await user.selectOptions(screen.getByTestId('project-type-filter'), 'rwx');
      expect(screen.getByTestId('projects-filtered-count')).toHaveTextContent('Showing 1 of 3');
      expect(screen.getByTestId('project-row-RwxPrivateNoPrefix')).toBeInTheDocument();

      await user.click(screen.getByTestId('more-filters-trigger'));
      await user.selectOptions(screen.getByTestId('project-visibility-filter'), 'private');
      expect(screen.getByTestId('projects-filtered-count')).toHaveTextContent('Showing 1 of 3');

      await user.selectOptions(screen.getByTestId('project-naming-mode-filter'), 'no_prefix');
      expect(screen.getByTestId('projects-filtered-count')).toHaveTextContent('Showing 1 of 3');
      await user.keyboard('{Escape}');

      await user.selectOptions(screen.getByTestId('project-status-filter'), 'review');
      expect(screen.getByTestId('projects-filtered-count')).toHaveTextContent('Showing 1 of 3');
      expect(screen.getByTestId('project-row-RwxPrivateNoPrefix')).toBeInTheDocument();
    });

    test('Clear Filters resets search and filters', async () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Alpha', project_code: 'ALPHA', updated_at: '2024-01-01T00:00:00Z', pr_state: 'draft' },
          { id: 2, project_name: 'Beta', project_code: 'BETA', updated_at: '2024-01-01T00:00:00Z', pr_state: 'open' },
        ],
      });

      await user.type(screen.getByTestId('project-search-input'), 'al');
      expect(screen.getByTestId('clear-project-filters')).toBeInTheDocument();
      expect(screen.getByTestId('projects-filtered-count')).toHaveTextContent('Showing 1 of 2');

      await user.click(screen.getByTestId('clear-project-filters'));
      expect(screen.getByTestId('projects-filtered-count')).toHaveTextContent('Showing 2 of 2');
      expect(screen.getByTestId('project-row-Alpha')).toBeInTheDocument();
      expect(screen.getByTestId('project-row-Beta')).toBeInTheDocument();
    });

    test('shows empty state when filters match nothing', async () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Alpha', project_code: 'ALPHA', updated_at: '2024-01-01T00:00:00Z', pr_state: 'draft' },
        ],
      });

      await user.type(screen.getByTestId('project-search-input'), 'zzz');
      expect(screen.getByText(/No projects match your current search and filters/i)).toBeInTheDocument();
    });
  });

  describe('Row Actions Menu', () => {
    test('shows state-aware menu actions for draft, new, synced, and under review', async () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Drafty', project_code: 'D1', updated_at: '2024-01-01T00:00:00Z', pr_state: 'draft' },
          { id: 2, project_name: 'Newbie', project_code: 'N1', updated_at: '2024-01-01T00:00:00Z', pr_state: 'new' },
          { id: 3, project_name: 'Syncedy', project_code: 'S1', updated_at: '2024-01-01T00:00:00Z', pr_state: 'synced' },
          { id: 4, project_name: 'Reviewy', project_code: 'R1', updated_at: '2024-01-01T00:00:00Z', pr_state: 'open' },
        ],
      });

      await user.click(screen.getByTestId('project-more-Drafty'));
      expect(screen.getByTestId('project-action-continue-editing')).toBeInTheDocument();

      await user.keyboard('{Escape}');
      await user.click(screen.getByTestId('project-more-Newbie'));
      expect(screen.getByTestId('project-action-configure')).toBeInTheDocument();

      await user.keyboard('{Escape}');
      await user.click(screen.getByTestId('project-more-Syncedy'));
      expect(screen.getByTestId('project-action-view')).toBeInTheDocument();

      await user.keyboard('{Escape}');
      await user.click(screen.getByTestId('project-more-Reviewy'));
      expect(screen.queryByTestId('project-action-add-workflow')).not.toBeInTheDocument();
      expect(screen.getByTestId('project-action-view')).toBeInTheDocument();
      expect(screen.queryByTestId('project-action-open-pr')).not.toBeInTheDocument();
    });

    test('shows Open PR only when a PR URL is available', async () => {
      const openSpy = jest.spyOn(globalThis, 'open').mockImplementation(() => null);
      renderProjectList({
        projects: [
          {
            id: 1,
            project_name: 'Reviewy',
            project_code: 'R1',
            updated_at: '2024-01-01T00:00:00Z',
            pr_state: 'open',
            pr_url: 'https://github.com/example/example/pull/123',
          },
        ],
      });

      await user.click(screen.getByTestId('project-more-Reviewy'));
      await user.click(screen.getByTestId('project-action-open-pr'));

      expect(openSpy).toHaveBeenCalledWith(
        'https://github.com/example/example/pull/123',
        '_blank',
        'noopener,noreferrer'
      );
      openSpy.mockRestore();
    });

    test('clicking the action-menu trigger does not navigate the card', async () => {
      renderProjectList({
        projects: [
          { id: 1, project_name: 'Drafty', project_code: 'D1', updated_at: '2024-01-01T00:00:00Z', pr_state: 'draft' },
        ],
      });

      await user.click(screen.getByTestId('project-more-Drafty'));
      expect(mockNavigate).not.toHaveBeenCalled();
    });
  });

  test('does not render a "Create RWX Repository" button (removed per UX improvement)', () => {
    renderProjectList();

    expect(screen.queryByRole('button', { name: /Create RWX Repository/i })).not.toBeInTheDocument();
  });

  test('renders New Project and Managed Actions alongside the status pills, not the title row or toolbar', async () => {
    const onCreateProject = jest.fn();
    renderProjectList({ onCreateProject });

    const newProjectButton = screen.getByTestId('new-project-button');
    const managedActionsButton = screen.getByTestId('actions-projects-nav-button');
    expect(newProjectButton).toBeInTheDocument();
    expect(managedActionsButton).toBeInTheDocument();

    expect(screen.getByRole('heading', { name: 'Projects' }).closest('div')).not.toContainElement(newProjectButton);
    expect(screen.getByRole('heading', { name: 'Projects' }).closest('div')).not.toContainElement(managedActionsButton);
    expect(within(screen.getByTestId('projects-toolbar')).queryByTestId('new-project-button')).not.toBeInTheDocument();
    expect(within(screen.getByTestId('projects-toolbar')).queryByTestId('actions-projects-nav-button')).not.toBeInTheDocument();

    const statusPills = screen.getByRole('region', { name: /Project status summary/i });
    expect(statusPills.parentElement).toContainElement(newProjectButton);
    expect(statusPills.parentElement).toContainElement(managedActionsButton);

    await user.click(newProjectButton);
    expect(onCreateProject).toHaveBeenCalledTimes(1);
  });

  test('New Project respects the disabled state', () => {
    renderProjectList({ onCreateProject: jest.fn(), isCreateProjectDisabled: true });

    expect(screen.getByTestId('new-project-button')).toBeDisabled();
  });

  test('Managed Actions navigates from its new location', async () => {
    renderProjectList();

    await user.click(screen.getByTestId('actions-projects-nav-button'));
    expect(mockNavigate).toHaveBeenCalledWith('/project/alice/actions-projects');
  });

  // --- Persistent manual ordering (issue #1804) ---
  describe('Project ordering', () => {
    // 12 projects so the removed 10-item slice would be visible if it came back.
    // updated_at deliberately runs opposite to array order: if anything still
    // sorted by updated_at, these would render reversed.
    const manyProjects = Array.from({ length: 12 }, (_, i) => ({
      id: i + 1,
      project_id: i + 1,
      project_name: `Project${String(i + 1).padStart(2, '0')}`,
      project_code: `P${String(i + 1).padStart(2, '0')}`,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: `2024-01-${String(12 - i).padStart(2, '0')}T00:00:00Z`,
      pr_state: 'draft' as const,
    }));

    test('renders projects in the given order, not sorted by updated_at', () => {
      renderProjectList({ projects: manyProjects });

      expect(renderedOrder()).toEqual(manyProjects.map((p) => p.project_name));
    });

    test('renders every project — no hidden slice past the tenth card', () => {
      renderProjectList({ projects: manyProjects });

      expect(screen.getAllByTestId(/^project-row-/)).toHaveLength(12);
      expect(screen.getByTestId('projects-filtered-count')).toHaveTextContent('12');
    });

    test('a newer updated_at does not move a card', () => {
      const bumped = manyProjects.map((p, i) =>
        i === 11 ? { ...p, updated_at: '2099-01-01T00:00:00Z' } : p,
      );
      renderProjectList({ projects: bumped });

      // The freshly-"edited" project stays last instead of jumping to first.
      expect(renderedOrder()[11]).toBe('Project12');
    });

    test('drag handles are enabled when no filter is active', () => {
      renderProjectList({ projects: manyProjects, onReorder: jest.fn() });

      expect(screen.getByTestId('project-drag-handle-Project01')).toBeEnabled();
    });

    test('drag handles are disabled while a filter is active, with an explanation', async () => {
      renderProjectList({ projects: manyProjects, onReorder: jest.fn() });

      await user.type(screen.getByTestId('project-search-input'), 'Project01');

      const handle = screen.getByTestId('project-drag-handle-Project01');
      expect(handle).toBeDisabled();
      expect(handle).toHaveAttribute('aria-label', 'Clear filters to reorder projects');
    });

    test('clearing filters restores the complete saved order', async () => {
      renderProjectList({ projects: manyProjects, onReorder: jest.fn() });

      await user.type(screen.getByTestId('project-search-input'), 'Project01');
      expect(screen.getAllByTestId(/^project-row-/)).toHaveLength(1);

      await user.click(screen.getByTestId('clear-project-filters'));

      expect(renderedOrder()).toEqual(manyProjects.map((p) => p.project_name));
      expect(screen.getByTestId('project-drag-handle-Project01')).toBeEnabled();
    });

    test('clicking the drag handle does not navigate', async () => {
      renderProjectList({ projects: manyProjects, onReorder: jest.fn() });

      await user.click(screen.getByTestId('project-drag-handle-Project01'));

      expect(mockNavigate).not.toHaveBeenCalled();
    });

    test('card navigation still works alongside the drag handle', async () => {
      renderProjectList({ projects: manyProjects, onReorder: jest.fn() });

      await user.click(screen.getByRole('button', { name: 'Open project Project03' }));

      expect(mockNavigate).toHaveBeenCalledWith('/project/alice/Project03');
    });

    test('the three-dot menu still opens alongside the drag handle', async () => {
      renderProjectList({ projects: manyProjects, onReorder: jest.fn() });

      await user.click(screen.getByTestId('project-more-Project01'));

      expect(await screen.findByTestId('project-action-continue-editing')).toBeInTheDocument();
      expect(mockNavigate).not.toHaveBeenCalled();
    });

    test('a reorder failure surfaces an error to the user', () => {
      renderProjectList({
        projects: manyProjects,
        onReorder: jest.fn(),
        reorderError: 'Failed to save project order.',
      });

      expect(screen.getByTestId('project-reorder-error')).toHaveTextContent(
        'Failed to save project order.',
      );
    });

    test('the responsive grid still wraps the cards directly', () => {
      renderProjectList({ projects: manyProjects, onReorder: jest.fn() });

      const grid = screen.getByTestId('project-row-Project01').parentElement;
      expect(grid).toHaveClass('grid');
      expect(grid).toHaveClass('sm:grid-cols-2');
    });
  });
});
