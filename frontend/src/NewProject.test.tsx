import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import NewProject from './NewProject';
import { fetchRepos, fetchRwxRepos } from './api/repos';
import { fetchProjects, saveProject } from './api/projects';
import { getUserDetails } from "./api/user";
import { toast } from "./utils/toast";



// Helper: select a repository via the new horizontal selector. The legacy
// dropdown (<select>/combobox) was replaced by a checkbox list whose rows
// expose the repo's full name as a stable data-testid.
async function selectRepoCheckbox(
  u: ReturnType<typeof userEvent.setup>,
  repoFullName: string,
) {
  const checkbox = await screen.findByTestId(
    `available-checkbox-${repoFullName}`,
  );
  await u.click(checkbox);
}

async function continueFromStep1(
  u: ReturnType<typeof userEvent.setup>,
  projectName = 'My Test Project',
) {
  const projectNameInput = screen.getByLabelText('Project Name:');
  await u.clear(projectNameInput);
  await u.type(projectNameInput, projectName);
  await u.click(screen.getByRole('button', { name: 'Continue' }));
}

async function continueFromStep2(u: ReturnType<typeof userEvent.setup>) {
  await u.click(screen.getByRole('button', { name: 'Continue' }));
}

// --- Mocks ---
const mockNavigate = jest.fn();

vi.mock(
  'react-router',
  () => ({
    useNavigate: () => mockNavigate,
  }),
  { virtual: true }
);

vi.mock('./api/repos', () => ({
  fetchRepos: jest.fn(),
  fetchRwxRepos: jest.fn(),
}));

vi.mock('./api/projects', () => ({
  fetchProjects: jest.fn(),
  saveProject: jest.fn(),
}));

vi.mock('./api/user', () => ({
  getUserDetails: jest.fn(),
}));

// Mock toast to capture notifications instead of browser alert()
vi.mock('./utils/toast', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
    warning: jest.fn(),
  },
}));


describe('NewProject', () => {
  const user = userEvent.setup();

  let logSpy: jest.SpyInstance;
  let errorSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    mockNavigate.mockResolvedValue(undefined);

    // Silence console.log/error during tests
    logSpy = jest.spyOn(console, 'log').mockImplementation(() => {});
    errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

    // Mock fetchRepos to return empty array by default
    (fetchRepos as jest.Mock).mockResolvedValue([]);
    (fetchProjects as jest.Mock).mockResolvedValue([]);
    // Default to a Professional account so the "private" visibility option
    // is not disabled in tests that don't explicitly assert tier behavior.
    (getUserDetails as jest.Mock).mockResolvedValue({
      github_user: 'testuser',
      avatar_url: '',
      account_type: 'professional',
    });
  });

  afterEach(() => {
    logSpy.mockRestore();
    errorSpy.mockRestore();
  });

  describe('Component Rendering', () => {
    it('renders the NewProject component with all required elements', () => {
      render(<NewProject user="testuser" />);

      // Check for main heading
      expect(screen.getByText('Create Project')).toBeInTheDocument();

      // Check for Project Name input
      expect(screen.getByLabelText('Project Name:')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Enter project name')).toBeInTheDocument();

      // Check for custom project key checkbox
      expect(screen.getByText('Project Summary')).toBeInTheDocument();

      // Check for repository selection section
      expect(screen.getAllByText('Caller Workflow Project').length).toBeGreaterThan(0);

      // Check for wizard navigation
      expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
    });

    it('renders the Project Color selector with Blue selected by default', () => {
      render(<NewProject user="testuser" />);
      expect(screen.getByText('Project Color')).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: 'Blue' })).toBeChecked();
    });

    it('does not render duplicate "Use custom key" checkbox once advanced options are open', async () => {
      (fetchRepos as jest.Mock).mockResolvedValue([
        { id: 1, name: 'repo1', full_name: 'user/repo1', private: false, default_branch: 'main' },
      ]);
      render(<NewProject user="testuser" />);
      await continueFromStep1(user);
      await selectRepoCheckbox(user, 'user/repo1');
      await continueFromStep2(user);
      await user.click(screen.getByRole('button', { name: 'Advanced Options' }));

      // There should be only one checkbox for custom project key (Radix UI checkbox)
      // Note: The resource naming mode uses radio inputs, not role="checkbox"
      const checkboxes = screen.getAllByRole('checkbox');
      expect(checkboxes).toHaveLength(1);
    });

    it('does not show custom project key input initially', () => {
      render(<NewProject user="testuser" />);

      // Custom project key input should not be visible
      expect(
        screen.queryByPlaceholderText('Enter project key (2-10 chars, letters/numbers)')
      ).not.toBeInTheDocument();
    });

    it('shows custom project key input when checkbox is checked', async () => {
      (fetchRepos as jest.Mock).mockResolvedValue([
        { id: 1, name: 'repo1', full_name: 'user/repo1', private: false, default_branch: 'main' },
      ]);
      render(<NewProject user="testuser" />);
      await continueFromStep1(user);
      await selectRepoCheckbox(user, 'user/repo1');
      await continueFromStep2(user);
      await user.click(screen.getByRole('button', { name: 'Advanced Options' }));

      // Check the "Use custom project key" checkbox
      const checkbox = screen.getByRole('checkbox');
      await user.click(checkbox);

      // Custom project key input should now be visible
      await waitFor(() => {
        expect(
          screen.getByPlaceholderText('Enter project key (2-10 chars, letters/numbers)')
        ).toBeInTheDocument();
      });
    });

    it('includes the selected project_color in the create payload', async () => {
      (fetchRepos as jest.Mock).mockResolvedValue([
        { id: 1, name: 'repo1', full_name: 'user/repo1', private: false, default_branch: 'main' },
      ]);
      (saveProject as jest.Mock).mockResolvedValue({ success: true });

      render(<NewProject user="testuser" />);

      await user.click(screen.getByRole('radio', { name: 'Rose' }));
      await continueFromStep1(user);
      await selectRepoCheckbox(user, 'user/repo1');
      await continueFromStep2(user);

      await user.click(screen.getByDisplayValue('prefix'));
      await user.click(screen.getByText('🚀 Create Project'));

      await waitFor(() => expect(saveProject).toHaveBeenCalled());
      const payload = (saveProject as jest.Mock).mock.calls[0][0];
      expect(payload.project_color).toBe('rose');
    });
  });

  describe('Project Name Input', () => {
    it('allows user to type in project name', async () => {
      render(<NewProject user="testuser" />);

      const projectNameInput = screen.getByLabelText('Project Name:');
      await user.type(projectNameInput, 'My Test Project');

      expect(projectNameInput).toHaveValue('My Test Project');
    });

    it('disables Continue until project name is valid', async () => {
      render(<NewProject user="testuser" />);

      const continueButton = screen.getByRole('button', { name: 'Continue' });
      expect(continueButton).toBeDisabled();

      await user.type(screen.getByLabelText('Project Name:'), 'My Test Project');
      expect(continueButton).toBeEnabled();
    });

    it('does not mark an untouched empty project name as invalid', () => {
      render(<NewProject user="testuser" />);

      const projectNameInput = screen.getByLabelText('Project Name:');
      expect(projectNameInput).toHaveAttribute('aria-invalid', 'false');
      expect(projectNameInput).toHaveAttribute('aria-describedby', 'project-name-help');
      expect(screen.queryByText('Project name is required.')).not.toBeInTheDocument();
    });
  });

  describe('Repository Selection', () => {
    it('fetches repositories on mount', async () => {
      const mockRepos = [
        { id: 1, name: 'repo1', full_name: 'user/repo1', private: false, default_branch: 'main' },
        { id: 2, name: 'repo2', full_name: 'user/repo2', private: false, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);

      render(<NewProject user="testuser" />);

      await waitFor(() => {
        expect(fetchRepos).toHaveBeenCalledWith('testuser');
      });
    });

    it('shows error when trying to create project without selecting repositories', async () => {
      render(<NewProject user="testuser" />);

      await continueFromStep1(user);

      expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
    });
  });

  describe('Custom Project Key', () => {
    it('validates custom project key length', async () => {
      const mockRepos = [
        { id: 1, name: 'repo1', full_name: 'user/repo1', private: false, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);

      render(<NewProject user="testuser" />);

      // Wait for repos to load
      await waitFor(() => {
        expect(fetchRepos).toHaveBeenCalled();
      });

      await continueFromStep1(user);

      // Select a repository first
      await selectRepoCheckbox(user, 'user/repo1');
      await continueFromStep2(user);

      // Enable custom project key
      await user.click(screen.getByRole('button', { name: 'Advanced Options' }));
      const checkbox = screen.getByLabelText('Use custom project key');
      await user.click(checkbox);

      // Enter invalid key (too short)
      const keyInput = await screen.findByPlaceholderText(
        'Enter project key (2-10 chars, letters/numbers)'
      );
      await user.type(keyInput, 'A');

      await user.click(screen.getByRole('radio', { name: /^Prefix Mode - Recommended/i }));

      const createButton = screen.getByText('🚀 Create Project');
      await user.click(createButton);

      // Should show validation error
      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          'Project key must be 2–10 characters (letters and numbers only).'
        );
      });
    });
  });

  describe('Project Creation', () => {
    it('creates project successfully with valid inputs', async () => {
      const mockRepos = [
        { id: 1, name: 'repo1', full_name: 'user/repo1', private: false, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);
      (saveProject as jest.Mock).mockResolvedValue({ success: true });

      render(<NewProject user="testuser" />);

      // Wait for repos to load
      await waitFor(() => {
        expect(fetchRepos).toHaveBeenCalled();
      });

      await continueFromStep1(user);

      // Select repository
      await selectRepoCheckbox(user, 'user/repo1');
      await continueFromStep2(user);

      await user.click(screen.getByRole('radio', { name: /^Prefix Mode - Recommended/i }));

      // Create project
      const createButton = screen.getByText('🚀 Create Project');
      await user.click(createButton);

      await waitFor(() => {
        expect(saveProject).toHaveBeenCalled();
      });

      expect(toast.success).toHaveBeenCalledWith(
        'Project created successfully! You can now add workflows to it.'
      );
      expect(mockNavigate).toHaveBeenCalledWith('/project/testuser');
    });

    it('sends use_prefix=false when No Prefix Mode option is selected', async () => {
      const mockRepos = [
        { id: 1, name: 'repo1', full_name: 'user/repo1', private: false, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);
      (saveProject as jest.Mock).mockResolvedValue({ success: true });

      render(<NewProject user="testuser" />);

      await waitFor(() => {
        expect(fetchRepos).toHaveBeenCalled();
      });

      await continueFromStep1(user);

      // Select repository
      await selectRepoCheckbox(user, 'user/repo1');
      await continueFromStep2(user);

      const noPrefixRadio = screen.getByDisplayValue('no-prefix');
      await user.click(noPrefixRadio);

      // Create project
      const createButton = screen.getByText('🚀 Create Project');
      await user.click(createButton);

      await waitFor(() => {
        expect(saveProject).toHaveBeenCalledWith(
          expect.objectContaining({
            use_prefix: false,
            project_name: 'My Test Project',
            github_user: 'testuser',
          })
        );
      });
    });

    it('requires explicit selection of Prefix Mode to send use_prefix=true', async () => {
      const mockRepos = [
        { id: 1, name: 'repo1', full_name: 'user/repo1', private: false, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);
      (saveProject as jest.Mock).mockResolvedValue({ success: true });

      render(<NewProject user="testuser" />);

      await waitFor(() => {
        expect(fetchRepos).toHaveBeenCalled();
      });

      await continueFromStep1(user);

      // Select repository
      await selectRepoCheckbox(user, 'user/repo1');
      await continueFromStep2(user);

      // Explicitly select Prefix Mode
      const prefixModeRadio = screen.getByDisplayValue('prefix');
      await user.click(prefixModeRadio);

      // Create project
      const createButton = screen.getByText('🚀 Create Project');
      await user.click(createButton);

      await waitFor(() => {
        expect(saveProject).toHaveBeenCalledWith(
          expect.objectContaining({
            use_prefix: true,
            project_name: 'My Test Project',
            github_user: 'testuser',
          })
        );
      });
    });

    it('toggles use_prefix when switching between resource naming mode options', async () => {
      const mockRepos = [
        { id: 1, name: 'repo1', full_name: 'user/repo1', private: false, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);
      (saveProject as jest.Mock).mockResolvedValue({ success: true });

      render(<NewProject user="testuser" />);

      await waitFor(() => {
        expect(fetchRepos).toHaveBeenCalled();
      });

      await continueFromStep1(user);
      await selectRepoCheckbox(user, 'user/repo1');
      await continueFromStep2(user);

      // Initially neither mode should be selected
      const prefixModeRadio = screen.getByDisplayValue('prefix') as HTMLInputElement;
      const noPrefixRadio = screen.getByDisplayValue('no-prefix') as HTMLInputElement;
      expect(prefixModeRadio.checked).toBe(false);
      expect(noPrefixRadio.checked).toBe(false);

      // Click No Prefix Mode, then switch back to Prefix Mode
      await user.click(noPrefixRadio);
      expect(noPrefixRadio.checked).toBe(true);
      await user.click(prefixModeRadio);
      expect(prefixModeRadio.checked).toBe(true);

      const createButton = screen.getByText('🚀 Create Project');
      await user.click(createButton);

      // Should send use_prefix=true since we selected Prefix Mode
      await waitFor(() => {
        expect(saveProject).toHaveBeenCalledWith(
          expect.objectContaining({
            use_prefix: true,
          })
        );
      });
    });
  });

  describe('Wizard Summary and Navigation', () => {
    it('updates the summary as basics, repositories, and naming mode change', async () => {
      const mockRepos = [
        { id: 1, name: 'repo1', full_name: 'user/repo1', private: false, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);

      render(<NewProject user="testuser" />);

      await user.type(screen.getByLabelText('Project Name:'), 'Platform Workflows');
      expect(screen.getByText('Platform Workflows')).toBeInTheDocument();
      expect(screen.getByText('Not selected')).toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: 'Continue' }));
      await selectRepoCheckbox(user, 'user/repo1');
      expect(screen.getByText('1 selected')).toBeInTheDocument();
      expect(screen.getAllByText('user/repo1').length).toBeGreaterThan(0);

      await continueFromStep2(user);
      await user.click(screen.getByDisplayValue('no-prefix'));

      expect(screen.getAllByText('No Prefix Mode').length).toBeGreaterThan(0);
      expect(
        screen.getByText(/No Prefix Mode is intended for advanced users/),
      ).toBeInTheDocument();
    });

    it('preserves project type and repository visibility when navigating back and forward', async () => {
      const mockRepos = [
        { id: 1, name: 'priv1', full_name: 'user/priv1', private: true, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);
      (fetchRwxRepos as jest.Mock).mockResolvedValue([]);

      render(<NewProject user="testuser" />);

      const rwxRadio = screen.getByDisplayValue('rwx') as HTMLInputElement;
      await user.click(rwxRadio);
      await continueFromStep1(user);

      const privateRadio = screen.getByDisplayValue('private') as HTMLInputElement;
      await user.click(privateRadio);
      expect(privateRadio.checked).toBe(true);

      await user.click(screen.getByRole('button', { name: 'Back' }));
      expect((screen.getByDisplayValue('rwx') as HTMLInputElement).checked).toBe(true);

      await user.click(screen.getByRole('button', { name: 'Continue' }));
      expect((screen.getByDisplayValue('private') as HTMLInputElement).checked).toBe(true);
    });
  });

  describe('RWX Project Type Auto-Discovery', () => {
    beforeEach(() => {
      // Mock fetchRwxRepos to return empty array by default
      (fetchRwxRepos as jest.Mock).mockResolvedValue([]);
    });

    it('does NOT show a manual owner/org input field (auto-discovery only)', async () => {
      render(<NewProject user="testuser" />);

      // Switch to RWX project type
      const rwxRadio = screen.getByDisplayValue('rwx') as HTMLInputElement;
      await user.click(rwxRadio);
      await continueFromStep1(user);

      // Should now show RWX repos heading
      expect(screen.getByText('Select Reusable Workflow Repository')).toBeInTheDocument();

      // The manual owner field has been removed in favor of auto-discovery.
      expect(screen.queryByLabelText(/GitHub Owner\/Organization/)).not.toBeInTheDocument();
    });

    it('auto-discovers RWX repos across personal and org accounts on entry', async () => {
      // Backend returns RWX repos from both the personal account AND any org
      // the user/App installation has access to. Regression for the case where
      // the dropdown only showed the personal repo and never `whatsupdawg/my-rwx`.
      const mockRwxRepos = [
        { id: 1, name: 'my-rwx-workflow', full_name: 'testuser/my-rwx-workflow', private: false, html_url: 'https://github.com/testuser/my-rwx-workflow' },
        { id: 2, name: 'my-rwx', full_name: 'whatsupdawg/my-rwx', private: false, html_url: 'https://github.com/whatsupdawg/my-rwx' },
      ];
      (fetchRwxRepos as jest.Mock).mockResolvedValue(mockRwxRepos);

      render(<NewProject user="testuser" />);

      // Switch to RWX project type
      const rwxRadio = screen.getByDisplayValue('rwx') as HTMLInputElement;
      await user.click(rwxRadio);
      await continueFromStep1(user);

      // Should fetch RWX repos for the user without any owner parameter
      // (single-arg call — no second positional arg).
      await waitFor(() => {
        expect(fetchRwxRepos).toHaveBeenCalledWith('testuser');
      });

      // Both the personal and the org RWX repos should appear in the picker.
      expect(
        await screen.findByTestId('available-repo-testuser/my-rwx-workflow'),
      ).toBeInTheDocument();
      expect(
        await screen.findByTestId('available-repo-whatsupdawg/my-rwx'),
      ).toBeInTheDocument();
    });

    it('shows a generic empty state when no accessible RWX repos are found', async () => {
      (fetchRwxRepos as jest.Mock).mockResolvedValue([]);

      render(<NewProject user="testuser" />);

      const rwxRadio = screen.getByDisplayValue('rwx') as HTMLInputElement;
      await user.click(rwxRadio);
      await continueFromStep1(user);

      expect(
        await screen.findByText(
          /No reusable workflow repository selected yet/i,
        ),
      ).toBeInTheDocument();
    });

    it('shows an error message when the RWX repos fetch returns an error payload', async () => {
      const errorResponse = { error: 'GitHub API error fetching RWX repos', status: 500 };
      (fetchRwxRepos as jest.Mock).mockResolvedValue(errorResponse);

      render(<NewProject user="testuser" />);

      const rwxRadio = screen.getByDisplayValue('rwx') as HTMLInputElement;
      await user.click(rwxRadio);
      await continueFromStep1(user);

      // The error is surfaced in the available-repositories panel of the
      // unified RepositoryBranchSelector.
      expect(await screen.findByTestId('available-error')).toHaveTextContent(
        'GitHub API error fetching RWX repos',
      );
    });

    it('clears selected repos when switching between standard and RWX project types', async () => {
      const mockStandardRepos = [
        { id: 1, name: 'repo1', full_name: 'testuser/repo1', private: false, default_branch: 'main' },
      ];
      const mockRwxRepos = [
        { id: 2, name: 'my-rwx', full_name: 'testuser/my-rwx', private: false, html_url: 'https://github.com/testuser/my-rwx' },
      ];

      (fetchRepos as jest.Mock).mockResolvedValue(mockStandardRepos);
      (fetchRwxRepos as jest.Mock).mockResolvedValue(mockRwxRepos);

      render(<NewProject user="testuser" />);
      await continueFromStep1(user);

      // Wait for repos to be fetched and rendered
      await waitFor(() => {
        expect(fetchRepos).toHaveBeenCalled();
      });

      // Wait for the repo to appear in the picker
      expect(
        await screen.findByTestId('available-repo-testuser/repo1'),
      ).toBeInTheDocument();

      await selectRepoCheckbox(user, 'testuser/repo1');

      // Verify repo is selected
      await waitFor(() => {
        expect(screen.getByText(/Selected Repositories \(1\)/)).toBeInTheDocument();
      });

      // Switch to RWX project type
      await user.click(screen.getByRole('button', { name: 'Back' }));
      const rwxRadio = screen.getByDisplayValue('rwx') as HTMLInputElement;
      await user.click(rwxRadio);
      await continueFromStep1(user);

      // Selected repos should be cleared
      await waitFor(() => {
        expect(screen.queryByText(/Selected Repositories \(1\)/)).not.toBeInTheDocument();
      });
    });

    it('replaces (does not append) the existing RWX repo selection when a second one is picked', async () => {
      // RWX projects must have exactly one repo. When the user picks a
      // second repo from the available list, the previous one must be
      // replaced atomically (otherwise the backend silently drops one).
      const mockRwxRepos = [
        { id: 1, name: 'rwx-a', full_name: 'testuser/rwx-a', private: false, html_url: 'https://github.com/testuser/rwx-a' },
        { id: 2, name: 'rwx-b', full_name: 'testuser/rwx-b', private: false, html_url: 'https://github.com/testuser/rwx-b' },
      ];
      (fetchRwxRepos as jest.Mock).mockResolvedValue(mockRwxRepos);

      render(<NewProject user="testuser" />);

      const rwxRadio = screen.getByDisplayValue('rwx') as HTMLInputElement;
      await user.click(rwxRadio);
      await continueFromStep1(user);

      expect(
        await screen.findByTestId('available-repo-testuser/rwx-a'),
      ).toBeInTheDocument();

      // Pick the first repo, then pick a second one.
      await selectRepoCheckbox(user, 'testuser/rwx-a');
      expect(
        await screen.findByText(/Selected Repositories \(1\)/),
      ).toBeInTheDocument();

      await selectRepoCheckbox(user, 'testuser/rwx-b');

      // Still exactly one selected — and it's the latest pick.
      expect(
        await screen.findByText(/Selected Repositories \(1\)/),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId('selected-repo-testuser/rwx-b'),
      ).toBeInTheDocument();
      expect(
        screen.queryByTestId('selected-repo-testuser/rwx-a'),
      ).not.toBeInTheDocument();
    });

    it('clears the picker search input when toggling between standard and RWX', async () => {
      // Stale search query from one project type must not hide every row in
      // the other type's freshly-fetched list.
      const mockStandardRepos = [
        { id: 1, name: 'std', full_name: 'testuser/std', private: false, default_branch: 'main' },
      ];
      const mockRwxRepos = [
        { id: 2, name: 'rwx-only', full_name: 'testuser/rwx-only', private: false, html_url: 'https://github.com/testuser/rwx-only' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockStandardRepos);
      (fetchRwxRepos as jest.Mock).mockResolvedValue(mockRwxRepos);

      render(<NewProject user="testuser" />);
      await continueFromStep1(user);
      await waitFor(() => expect(fetchRepos).toHaveBeenCalled());
      expect(
        await screen.findByTestId('available-repo-testuser/std'),
      ).toBeInTheDocument();

      // Type a query that matches the standard repo but no RWX repo.
      const search = screen.getByTestId('available-search-input') as HTMLInputElement;
      await user.type(search, 'std');
      expect(search.value).toBe('std');

      await user.click(screen.getByRole('button', { name: 'Back' }));
      const rwxRadio = screen.getByDisplayValue('rwx') as HTMLInputElement;
      await user.click(rwxRadio);
      await continueFromStep1(user);

      // The picker must reset its search so the RWX repo is visible.
      await waitFor(() =>
        expect(
          (screen.getByTestId('available-search-input') as HTMLInputElement).value,
        ).toBe(''),
      );
      expect(
        await screen.findByTestId('available-repo-testuser/rwx-only'),
      ).toBeInTheDocument();
    });

    it('surfaces a real /api/repos transport failure as an error in the picker', async () => {
      // The shared `fetchRepos` helper now returns `{error, status}` on
      // request failures (instead of swallowing them and returning []),
      // so the picker should show the error rather than an empty state.
      (fetchRepos as jest.Mock).mockResolvedValue({
        error: 'Network error fetching repositories',
        status: 502,
      });

      render(<NewProject user="testuser" />);
      await continueFromStep1(user);

      await waitFor(() => expect(fetchRepos).toHaveBeenCalled());
      await waitFor(() =>
        expect(screen.getByTestId('available-error')).toHaveTextContent(
          'Network error fetching repositories',
        ),
      );
    });
  });

  describe('Repository Visibility Scope', () => {
    it('renders both Public and Private visibility options with helper text', async () => {
      render(<NewProject user="testuser" />);
      // Wait for getUserDetails resolution so any tier-based UI is settled.
      await waitFor(() => expect(getUserDetails).toHaveBeenCalled());
      await continueFromStep1(user);

      expect(screen.getByText('Repository Visibility:')).toBeInTheDocument();
      expect(screen.getAllByText('Public repositories').length).toBeGreaterThan(0);
      expect(screen.getByText('Private repositories')).toBeInTheDocument();
      expect(
        screen.getByText('Use this project for public GitHub repositories only.'),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Use this project for private GitHub repositories only/),
      ).toBeInTheDocument();
    });

    it('defaults to Public scope and shows the public-only picker note', async () => {
      render(<NewProject user="testuser" />);
      await waitFor(() => expect(getUserDetails).toHaveBeenCalled());
      await continueFromStep1(user);
      expect(screen.getByTestId('visibility-scope-note')).toHaveTextContent(
        'Showing public repositories only.',
      );
    });

    it('Public scope filters out private repos from the picker', async () => {
      const mockRepos = [
        { id: 1, name: 'pub1', full_name: 'u/pub1', private: false, default_branch: 'main' },
        { id: 2, name: 'priv1', full_name: 'u/priv1', private: true, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);
      render(<NewProject user="testuser" />);
      await continueFromStep1(user);

      await waitFor(() => expect(fetchRepos).toHaveBeenCalled());
      await waitFor(() => {
        expect(screen.getByTestId('available-repo-u/pub1')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('available-repo-u/priv1')).not.toBeInTheDocument();
    });

    it('Private scope filters out public repos from the picker', async () => {
      const mockRepos = [
        { id: 1, name: 'pub1', full_name: 'u/pub1', private: false, default_branch: 'main' },
        { id: 2, name: 'priv1', full_name: 'u/priv1', private: true, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);
      render(<NewProject user="testuser" />);
      await waitFor(() => expect(fetchRepos).toHaveBeenCalled());
      await waitFor(() => expect(getUserDetails).toHaveBeenCalled());
      await continueFromStep1(user);

      const privateRadio = screen.getByDisplayValue('private') as HTMLInputElement;
      await user.click(privateRadio);

      await waitFor(() => {
        expect(screen.getByTestId('available-repo-u/priv1')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('available-repo-u/pub1')).not.toBeInTheDocument();
      expect(screen.getByTestId('visibility-scope-note')).toHaveTextContent(
        'Showing private repositories only.',
      );
    });

    it('clears selected repos that no longer match when visibility changes', async () => {
      const mockRepos = [
        { id: 1, name: 'pub1', full_name: 'u/pub1', private: false, default_branch: 'main' },
        { id: 2, name: 'priv1', full_name: 'u/priv1', private: true, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);
      render(<NewProject user="testuser" />);
      await waitFor(() => expect(fetchRepos).toHaveBeenCalled());
      await waitFor(() => expect(getUserDetails).toHaveBeenCalled());
      await continueFromStep1(user);

      // Select the public repo while in Public scope
      await selectRepoCheckbox(user, 'u/pub1');
      expect(
        await screen.findByText(/Selected Repositories \(1\)/),
      ).toBeInTheDocument();

      // Switch to Private — the selected public repo should be cleared
      const privateRadio = screen.getByDisplayValue('private') as HTMLInputElement;
      await user.click(privateRadio);

      await waitFor(() => {
        expect(screen.queryByText(/Selected Repositories \(1\)/)).not.toBeInTheDocument();
      });
    });

    it('Free tier users see private option disabled with an upgrade message', async () => {
      (getUserDetails as jest.Mock).mockResolvedValue({
        github_user: 'testuser',
        avatar_url: '',
        account_type: 'free',
      });
      render(<NewProject user="testuser" />);
      await waitFor(() => expect(getUserDetails).toHaveBeenCalled());
      await continueFromStep1(user);

      const privateRadio = screen.getByDisplayValue('private') as HTMLInputElement;
      await waitFor(() => expect(privateRadio.disabled).toBe(true));
      expect(
        screen.getByText(/Free plan accounts cannot create private repository projects/),
      ).toBeInTheDocument();
    });

    it('shows empty state when no repositories match the selected visibility', async () => {
      (fetchRepos as jest.Mock).mockResolvedValue([
        { id: 1, name: 'pub1', full_name: 'u/pub1', private: false, default_branch: 'main' },
      ]);
      render(<NewProject user="testuser" />);
      await waitFor(() => expect(fetchRepos).toHaveBeenCalled());
      await waitFor(() => expect(getUserDetails).toHaveBeenCalled());
      await continueFromStep1(user);

      const privateRadio = screen.getByDisplayValue('private') as HTMLInputElement;
      await user.click(privateRadio);

      await waitFor(() => {
        expect(screen.getByTestId('visibility-empty-state')).toHaveTextContent(
          /No private repositories were found/,
        );
      });
    });

    it('sends repository_visibility_scope in the create payload', async () => {
      const mockRepos = [
        { id: 1, name: 'priv1', full_name: 'u/priv1', private: true, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);
      (saveProject as jest.Mock).mockResolvedValue({ success: true });

      render(<NewProject user="testuser" />);
      await waitFor(() => expect(fetchRepos).toHaveBeenCalled());
      await waitFor(() => expect(getUserDetails).toHaveBeenCalled());
      await continueFromStep1(user);

      // Select Private visibility
      const privateRadio = screen.getByDisplayValue('private') as HTMLInputElement;
      await user.click(privateRadio);

      await selectRepoCheckbox(user, 'u/priv1');
      await continueFromStep2(user);

      await user.click(screen.getByRole('radio', { name: /^Prefix Mode - Recommended/i }));
      await user.click(screen.getByText('🚀 Create Project'));

      await waitFor(() => expect(saveProject).toHaveBeenCalled());
      const payload = (saveProject as jest.Mock).mock.calls[0][0];
      expect(payload.repository_visibility_scope).toBe('private');
      expect(payload.selected_repos).toEqual(['u/priv1']);
    });
  });

  describe('Self-hosted beta project type limits', () => {
    it('keeps both type options enabled when under quota', async () => {
      (getUserDetails as jest.Mock).mockResolvedValue({
        github_user: 'testuser',
        avatar_url: '',
        account_type: 'free',
        installation_mode: 'self-hosted',
      });
      (fetchProjects as jest.Mock).mockResolvedValue([
        { project_type: 'standard' },
        { project_type: 'standard' },
        { project_type: 'standard' },
        { project_type: 'rwx' },
      ]);

      render(<NewProject user="testuser" />);
      await waitFor(() => expect(fetchProjects).toHaveBeenCalledWith('testuser'));

      expect((screen.getByDisplayValue('standard') as HTMLInputElement).disabled).toBe(false);
      expect((screen.getByDisplayValue('rwx') as HTMLInputElement).disabled).toBe(false);
      expect(screen.queryByText(/Beta limit reached/)).not.toBeInTheDocument();
    });

    it('disables caller workflow type and shows helper text when caller quota is reached', async () => {
      (getUserDetails as jest.Mock).mockResolvedValue({
        github_user: 'testuser',
        avatar_url: '',
        account_type: 'free',
        installation_mode: 'self-hosted',
      });
      (fetchProjects as jest.Mock).mockResolvedValue([
        { project_type: 'standard' },
        { project_type: 'standard' },
        { project_type: 'standard' },
        { project_type: 'standard' },
      ]);

      render(<NewProject user="testuser" />);
      await waitFor(() => expect(fetchProjects).toHaveBeenCalledWith('testuser'));

      expect((screen.getByDisplayValue('standard') as HTMLInputElement).disabled).toBe(true);
      expect((screen.getByDisplayValue('rwx') as HTMLInputElement).disabled).toBe(false);
      expect(
        screen.getByText('Beta limit reached (4/4 Caller Workflow Projects).'),
      ).toBeInTheDocument();
    });

    it('disables reusable workflow type and shows helper text when reusable quota is reached', async () => {
      (getUserDetails as jest.Mock).mockResolvedValue({
        github_user: 'testuser',
        avatar_url: '',
        account_type: 'free',
        installation_mode: 'self-hosted',
      });
      (fetchProjects as jest.Mock).mockResolvedValue([
        { project_type: 'rwx' },
        { project_type: 'rwx' },
      ]);

      render(<NewProject user="testuser" />);
      await waitFor(() => expect(fetchProjects).toHaveBeenCalledWith('testuser'));

      expect((screen.getByDisplayValue('rwx') as HTMLInputElement).disabled).toBe(true);
      expect((screen.getByDisplayValue('standard') as HTMLInputElement).disabled).toBe(false);
      expect(
        screen.getByText('Beta limit reached (2/2 Reusable Workflow Projects).'),
      ).toBeInTheDocument();
    });
  });

  describe('Resource Naming Mode Selection Requirements', () => {
    it('does not pre-select any Resource Naming Mode by default', async () => {
      const mockRepos = [
        { id: 1, name: 'repo1', full_name: 'user/repo1', private: false, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);

      render(<NewProject user="testuser" />);
      await continueFromStep1(user);
      await selectRepoCheckbox(user, 'user/repo1');
      await continueFromStep2(user);

      // Neither radio should be checked
      const prefixRadio = screen.getByDisplayValue('prefix') as HTMLInputElement;
      const noPrefixRadio = screen.getByDisplayValue('no-prefix') as HTMLInputElement;
      expect(prefixRadio.checked).toBe(false);
      expect(noPrefixRadio.checked).toBe(false);
    });

    it('shows "Not selected" in summary until user selects a naming mode', async () => {
      const mockRepos = [
        { id: 1, name: 'repo1', full_name: 'user/repo1', private: false, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);

      render(<NewProject user="testuser" />);

      // Summary should show "Not selected" initially
      expect(screen.getByText('Not selected')).toBeInTheDocument();

      await continueFromStep1(user);
      await selectRepoCheckbox(user, 'user/repo1');
      await continueFromStep2(user);

      // Still showing "Not selected" on step 3
      expect(screen.getByText('Not selected')).toBeInTheDocument();

      // Select Prefix Mode
      await user.click(screen.getByDisplayValue('prefix'));

      // Now summary should show "Prefix Mode"
      expect(screen.getAllByText('Prefix Mode').length).toBeGreaterThan(0);
    });

    it('disables Create Project button until naming mode is selected', async () => {
      const mockRepos = [
        { id: 1, name: 'repo1', full_name: 'user/repo1', private: false, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);

      render(<NewProject user="testuser" />);
      await continueFromStep1(user);
      await selectRepoCheckbox(user, 'user/repo1');
      await continueFromStep2(user);

      // Create button should be disabled without naming mode selection
      const createButton = screen.getByText('🚀 Create Project');
      expect(createButton).toBeDisabled();

      // Select Prefix Mode
      await user.click(screen.getByDisplayValue('prefix'));

      // Create button should now be enabled
      expect(createButton).toBeEnabled();
    });

    it('sends use_prefix based on explicit user selection', async () => {
      const mockRepos = [
        { id: 1, name: 'repo1', full_name: 'user/repo1', private: false, default_branch: 'main' },
      ];
      (fetchRepos as jest.Mock).mockResolvedValue(mockRepos);
      (saveProject as jest.Mock).mockResolvedValue({ success: true });

      render(<NewProject user="testuser" />);
      await continueFromStep1(user);
      await selectRepoCheckbox(user, 'user/repo1');
      await continueFromStep2(user);

      // Select No Prefix Mode explicitly
      await user.click(screen.getByDisplayValue('no-prefix'));
      await user.click(screen.getByText('🚀 Create Project'));

      await waitFor(() => expect(saveProject).toHaveBeenCalled());
      const payload = (saveProject as jest.Mock).mock.calls[0][0];
      expect(payload.use_prefix).toBe(false);
    });
  });

  describe('Project Type Label Display', () => {
    it('displays "Caller Workflow Project" instead of "Standard Project"', () => {
      render(<NewProject user="testuser" />);

      // Should show "Caller Workflow Project"
      expect(screen.getAllByText('Caller Workflow Project').length).toBeGreaterThan(0);

      // Should not show old "Standard Project" label
      expect(screen.queryByText('Standard Project')).not.toBeInTheDocument();
    });
  });

  describe('Repository Step Auth State', () => {
    it('shows loading spinner while repositories are being fetched', async () => {
      // Never resolves during this test — keeps the component in loading state
      (fetchRepos as jest.Mock).mockReturnValue(new Promise(() => {}));

      render(<NewProject user="testuser" />);
      await continueFromStep1(user);

      await waitFor(() => expect(fetchRepos).toHaveBeenCalled());
      expect(screen.getByTestId('available-loading')).toBeInTheDocument();
    });

    it('does not show "Authentication required" while repos are still loading', async () => {
      (fetchRepos as jest.Mock).mockReturnValue(new Promise(() => {}));

      render(<NewProject user="testuser" />);
      await continueFromStep1(user);

      await waitFor(() => expect(fetchRepos).toHaveBeenCalled());
      expect(screen.queryByTestId('available-error')).not.toBeInTheDocument();
      expect(screen.queryByText(/Authentication required/i)).not.toBeInTheDocument();
    });

    it('loads and displays repositories for an authenticated user', async () => {
      (fetchRepos as jest.Mock).mockResolvedValue([
        { id: 1, name: 'my-repo', full_name: 'testuser/my-repo', private: false, default_branch: 'main' },
        { id: 2, name: 'another-repo', full_name: 'testuser/another-repo', private: false, default_branch: 'main' },
      ]);

      render(<NewProject user="testuser" />);
      await continueFromStep1(user);

      await waitFor(() => screen.getByTestId('available-checkbox-testuser/my-repo'));
      expect(screen.getByTestId('available-checkbox-testuser/another-repo')).toBeInTheDocument();
      expect(screen.queryByTestId('available-error')).not.toBeInTheDocument();
    });

    it('shows "Authentication required" only after fetch resolves with a 401', async () => {
      (fetchRepos as jest.Mock).mockResolvedValue({
        error: 'Authentication required',
        status: 401,
      });

      render(<NewProject user="testuser" />);
      await continueFromStep1(user);

      await waitFor(() =>
        expect(screen.getByTestId('available-error')).toHaveTextContent('Authentication required'),
      );
    });

    it('does not show error when fetch returns repos successfully', async () => {
      (fetchRepos as jest.Mock).mockResolvedValue([
        { id: 1, name: 'repo1', full_name: 'testuser/repo1', private: false, default_branch: 'main' },
      ]);

      render(<NewProject user="testuser" />);
      await continueFromStep1(user);

      await waitFor(() => screen.getByTestId('available-checkbox-testuser/repo1'));
      expect(screen.queryByTestId('available-error')).not.toBeInTheDocument();
    });

    it('switching between Public and Private visibility does not clear loaded repos', async () => {
      (fetchRepos as jest.Mock).mockResolvedValue([
        { id: 1, name: 'pub-repo', full_name: 'testuser/pub-repo', private: false, default_branch: 'main' },
        { id: 2, name: 'priv-repo', full_name: 'testuser/priv-repo', private: true, default_branch: 'main' },
      ]);

      render(<NewProject user="testuser" />);
      await continueFromStep1(user);
      await waitFor(() => screen.getByTestId('available-checkbox-testuser/pub-repo'));

      // Switch to private — repos should still be loaded (just filtered)
      await user.click(screen.getByRole('radio', { name: /private repositories/i }));
      await waitFor(() => screen.getByTestId('available-checkbox-testuser/priv-repo'));

      // fetchRepos should only have been called once — visibility change does not re-fetch
      expect(fetchRepos).toHaveBeenCalledTimes(1);
      expect(screen.queryByTestId('available-error')).not.toBeInTheDocument();
    });
  });
});
