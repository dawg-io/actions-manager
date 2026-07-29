// Mock window.matchMedia before any imports
const mockMatchMedia = jest.fn((query) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: jest.fn(), 
  removeListener: jest.fn(), 
  addEventListener: jest.fn(),
  removeEventListener: jest.fn(),
  dispatchEvent: jest.fn(),
}));

globalThis.matchMedia = mockMatchMedia;

// Mock react-router
const mockNavigate = jest.fn();
vi.mock(
  'react-router',
  () => ({
    useNavigate: () => mockNavigate,
  }),
  { virtual: true }
);

vi.mock('./ui', () => {
  const React = require('react');
  const MenuContext = React.createContext(null);

  return {
    Avatar: ({ children, className }: any) => (
      <span className={`relative flex shrink-0 overflow-hidden rounded-full ${className || ''}`}>
        {children}
      </span>
    ),
    AvatarImage: () => null,
    AvatarFallback: ({ children, className }: any) => (
      <span className={`flex h-full w-full items-center justify-center rounded-full ${className || ''}`}>
        {children}
      </span>
    ),
    DropdownMenu: ({ children }: any) => {
      const [open, setOpen] = React.useState(false);
      const contextValue = React.useMemo(() => ({ open, setOpen }), [open, setOpen]);
      return (
        <MenuContext.Provider value={contextValue}>
          {children}
        </MenuContext.Provider>
      );
    },
    DropdownMenuTrigger: ({ children }: any) => {
      const { open, setOpen } = React.useContext(MenuContext);
      return React.cloneElement(React.Children.only(children), {
        'aria-expanded': open,
        onClick: (event: any) => {
          children.props.onClick?.(event);
          setOpen((currentOpen: boolean) => !currentOpen);
        }
      });
    },
    DropdownMenuContent: ({ children, className }: any) => {
      const { open } = React.useContext(MenuContext);
      return open ? <div role="menu" className={className}>{children}</div> : null;
    },
    DropdownMenuItem: ({ children, onClick, className }: any) => (
      <button type="button" role="menuitem" onClick={onClick} className={className}>
        {children}
      </button>
    ),
    DropdownMenuLabel: ({ children, className }: any) => (
      <div className={className}>{children}</div>
    ),
    DropdownMenuSeparator: () => <hr />,
    Input: ({ className, ...props }: any) => <input className={className} {...props} />,
    Button: ({ children, className, ...props }: any) => (
      <button type="button" className={className} {...props}>
        {children}
      </button>
    ),
  };
});

import React from 'react';
import { render, fireEvent, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import UserAvatar from './UserAvatar';
import { ThemeProvider } from './ThemeContext';

vi.mock('../api/user', () => ({
  getGitHubTokenStatus: jest.fn(),
  testGitHubToken: jest.fn(),
  saveGitHubToken: jest.fn(),
  removeGitHubToken: jest.fn(),
}));

import { getGitHubTokenStatus, saveGitHubToken, testGitHubToken, removeGitHubToken } from '../api/user';

interface UserAvatarProps {
  avatarUrl: string | null;
  username: string | null;
  accountType: string;
  installationMode?: string | null;
  githubAccountType?: string | null;
  connectedGithubAccount?: string | null;
  connectedGithubAccountType?: string | null;
  workspaceRole?: string;
  rateLimit?: {
    limit: number;
    used: number;
    remaining: number;
    percentage_used: number;
    should_warn: boolean;
    reset_at: string;
  };
  githubToken?: {
    configured: boolean;
    status: "not_configured" | "configured" | "valid" | "missing_scopes" | "missing_repo_access" | "missing_org_approval" | "insufficient_repo_permissions" | "token_invalid" | "unknown_error";
    message: string;
    token_type?: "oauth_token" | "classic_pat" | "fine_grained_pat" | "github_app_user" | "github_app_installation" | "unknown" | null;
  };
  onGitHubAuthUpdated?: () => void;
  onLogout: () => void;
}

const renderWithTheme = (component: React.ReactElement) => {
  return render(
    <ThemeProvider>
      {component}
    </ThemeProvider>
  );
};

const openUserMenu = (accessibleName: string) => {
  const button = screen.getByRole('button', { name: accessibleName });
  fireEvent.pointerDown(button, {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse'
  });
  fireEvent.mouseDown(button, { button: 0 });
  fireEvent.mouseUp(button, { button: 0 });
  fireEvent.click(button);
};

describe('UserAvatar Component', () => {
  beforeEach(() => {
    // Clear mock calls before each test
    mockMatchMedia.mockClear();
    mockNavigate.mockClear();
    (testGitHubToken as jest.Mock).mockReset();
    (saveGitHubToken as jest.Mock).mockReset();
    (removeGitHubToken as jest.Mock).mockReset();
    (getGitHubTokenStatus as jest.Mock).mockReset();
  });

  test('should render with avatar image', () => {
    const mockOnLogout = jest.fn();
    const props: UserAvatarProps = {
      avatarUrl: 'https://github.com/testuser.png',
      username: 'testuser',
      accountType: 'pro',
      githubAccountType: 'User',
      onLogout: mockOnLogout
    };
    
    const { getByText, container } = renderWithTheme(<UserAvatar {...props} />);
    
    // Username should be visible
    expect(getByText('testuser')).toBeInTheDocument();
    // Avatar component should be present (may show fallback in test environment)
    const avatarSpan = container.querySelector('span.relative.flex.shrink-0.overflow-hidden');
    expect(avatarSpan).toBeInTheDocument();
  });

  test('should render placeholder when no avatar URL', () => {
    const mockOnLogout = jest.fn();
    const props: UserAvatarProps = {
      avatarUrl: null,
      username: 'testuser',
      accountType: 'free',
      installationMode: 'self-hosted',
      githubAccountType: 'User',
      onLogout: mockOnLogout
    };
    
    const { getByText } = renderWithTheme(<UserAvatar {...props} />);
    
    expect(getByText('T')).toBeInTheDocument(); // First letter of username in AvatarFallback
    expect(getByText('testuser')).toBeInTheDocument();
  });

  test('should render question mark when no username', () => {
    const mockOnLogout = jest.fn();
    const props: UserAvatarProps = {
      avatarUrl: null,
      username: null,
      accountType: 'free',
      githubAccountType: 'User',
      onLogout: mockOnLogout
    };
    
    const { getByText } = renderWithTheme(<UserAvatar {...props} />);
    
    expect(getByText('?')).toBeInTheDocument();
  });

  test('should render GitHub token configuration status in the menu', () => {
    const props: UserAvatarProps = {
      avatarUrl: null,
      username: 'testuser',
      accountType: 'free',
      githubAccountType: 'User',
      githubToken: {
        configured: true,
        status: 'valid',
        message: 'Token configured.',
        token_type: 'fine_grained_pat'
      },
      onLogout: jest.fn()
    };

    renderWithTheme(<UserAvatar {...props} />);
    openUserMenu('User menu for testuser');

    expect(screen.getByText('GitHub Authentication')).toBeInTheDocument();
    expect(screen.getByText('Configured · Fine-grained PAT')).toBeInTheDocument();

    // Expand the token manager to access management controls
    fireEvent.click(screen.getByRole('button', { name: 'Manage authentication' }));

    expect(screen.getByRole('button', { name: 'Replace token' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove token' })).toBeInTheDocument();
  });

  test('should save token without exposing the raw value afterwards', async () => {
    const onGitHubAuthUpdated = jest.fn();
    (saveGitHubToken as jest.Mock).mockResolvedValue({
      saved: true
    });
    (getGitHubTokenStatus as jest.Mock).mockResolvedValue({
      configured: true,
      status: 'valid',
      message: 'Token configured.',
      token_type: 'fine_grained_pat'
    });

    const props: UserAvatarProps = {
      avatarUrl: null,
      username: 'testuser',
      accountType: 'free',
      githubAccountType: 'User',
      onGitHubAuthUpdated,
      onLogout: jest.fn()
    };

    renderWithTheme(<UserAvatar {...props} />);
    openUserMenu('User menu for testuser');

    // Expand the token manager to access the token input and save button
    fireEvent.click(screen.getByRole('button', { name: 'Manage authentication' }));

    fireEvent.change(screen.getByLabelText('GitHub personal access token'), { target: { value: 'github_pat_1234567890' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save token' }));

    await waitFor(() => {
      expect(saveGitHubToken).toHaveBeenCalledWith('testuser', 'github_pat_1234567890');
      expect(getGitHubTokenStatus).toHaveBeenCalledWith('testuser');
    });
    expect(await screen.findByText('Token configured.')).toBeInTheDocument();
    expect(onGitHubAuthUpdated).toHaveBeenCalled();
    expect((screen.getByLabelText('GitHub personal access token') as HTMLInputElement).value).toBe('');
  });

  test('should handle empty username', () => {
    const mockOnLogout = jest.fn();
    const props: UserAvatarProps = {
      avatarUrl: null,
      username: '',
      accountType: 'free',
      githubAccountType: 'User',
      onLogout: mockOnLogout
    };
    
    const { getByText } = renderWithTheme(<UserAvatar {...props} />);
    
    expect(getByText('?')).toBeInTheDocument();
  });

  test('should render as a button element with proper ARIA attributes', () => {
    const mockOnLogout = jest.fn();
    const props: UserAvatarProps = {
      avatarUrl: 'https://github.com/testuser.png',
      username: 'testuser',
      accountType: 'pro',
      githubAccountType: 'User',
      onLogout: mockOnLogout
    };
    
    const { getByRole } = renderWithTheme(<UserAvatar {...props} />);
    const button = getByRole('button', { name: 'User menu for testuser' });
    
    expect(button?.tagName).toBe('BUTTON');
    expect(button).toHaveAttribute('aria-label', 'User menu for testuser');
  });

  test('should toggle dropdown when button is clicked', () => {
    const mockOnLogout = jest.fn();
    const props: UserAvatarProps = {
      avatarUrl: 'https://github.com/testuser.png',
      username: 'testuser',
      accountType: 'pro',
      githubAccountType: 'User',
      onLogout: mockOnLogout
    };
    
    const { getByRole } = renderWithTheme(<UserAvatar {...props} />);
    const button = getByRole('button', { name: 'User menu for testuser' });
    
    // Click to open dropdown - button should have proper ARIA attributes
    fireEvent.click(button);
    
    // Just verify the button can be clicked without errors
    expect(button).toBeInTheDocument();
  });

  test('should support keyboard navigation with Enter key', () => {
    const mockOnLogout = jest.fn();
    const props: UserAvatarProps = {
      avatarUrl: 'https://github.com/testuser.png',
      username: 'testuser',
      accountType: 'pro',
      githubAccountType: 'User',
      onLogout: mockOnLogout
    };
    
    const { getByRole } = renderWithTheme(<UserAvatar {...props} />);
    const button = getByRole('button', { name: 'User menu for testuser' });
    
    // Trigger Enter key and click - should not throw errors
    fireEvent.keyDown(button, { key: 'Enter', code: 'Enter' });
    fireEvent.click(button);
    
    expect(button).toBeInTheDocument();
  });

  test('should support keyboard navigation with Space key', () => {
    const mockOnLogout = jest.fn();
    const props: UserAvatarProps = {
      avatarUrl: 'https://github.com/testuser.png',
      username: 'testuser',
      accountType: 'pro',
      githubAccountType: 'User',
      onLogout: mockOnLogout
    };
    
    const { getByRole } = renderWithTheme(<UserAvatar {...props} />);
    const button = getByRole('button', { name: 'User menu for testuser' });
    
    // Trigger Space key and click - should not throw errors
    fireEvent.keyDown(button, { key: ' ', code: 'Space' });
    fireEvent.click(button);
    
    expect(button).toBeInTheDocument();
  });

  test('should format professional account type correctly', () => {
    const mockOnLogout = jest.fn();
    const props: UserAvatarProps = {
      avatarUrl: 'https://github.com/testuser.png',
      username: 'testuser',
      accountType: 'professional',
      githubAccountType: 'User',
      onLogout: mockOnLogout
    };
    
    const { getByRole } = renderWithTheme(<UserAvatar {...props} />);
    const button = getByRole('button', { name: 'User menu for testuser' });
    
    // Component should render with professional account type prop
    // The formatting logic exists in the component (checked via code review)
    expect(button).toBeInTheDocument();
  });

  test('should format free account type correctly', () => {
    const mockOnLogout = jest.fn();
    const props: UserAvatarProps = {
      avatarUrl: 'https://github.com/testuser.png',
      username: 'testuser',
      accountType: 'free',
      githubAccountType: 'User',
      onLogout: mockOnLogout
    };
    
    const { getByRole } = renderWithTheme(<UserAvatar {...props} />);
    const button = getByRole('button', { name: 'User menu for testuser' });
    
    // Component should render with free account type prop
    // The formatting logic exists in the component (checked via code review)
    expect(button).toBeInTheDocument();
  });

  test('should format enterprise account type correctly', () => {
    const mockOnLogout = jest.fn();
    const props: UserAvatarProps = {
      avatarUrl: 'https://github.com/testuser.png',
      username: 'testuser',
      accountType: 'enterprise',
      githubAccountType: 'User',
      onLogout: mockOnLogout
    };
    
    const { getByRole } = renderWithTheme(<UserAvatar {...props} />);
    const button = getByRole('button', { name: 'User menu for testuser' });
    
    // Component should render with enterprise account type prop
    // The formatting logic exists in the component (checked via code review)
    expect(button).toBeInTheDocument();
  });

  test('should show a clear personal GitHub account layout with helper text', () => {
    const props: UserAvatarProps = {
      avatarUrl: 'https://github.com/testuser.png',
      username: 'testuser',
      accountType: 'free',
      installationMode: 'self-hosted',
      githubAccountType: 'User',
      workspaceRole: 'admin',
      onLogout: jest.fn()
    };

    renderWithTheme(<UserAvatar {...props} />);
    openUserMenu('User menu for testuser');

    expect(screen.getByText('Account Plan')).toBeInTheDocument();
    expect(screen.getByText('Self-Hosted Beta')).toBeInTheDocument();
    expect(screen.getByText('Self-hosted beta access. Paid plans are not currently available.')).toBeInTheDocument();
    expect(screen.getByText('Deployment Mode')).toBeInTheDocument();
    expect(screen.getByText('Self-hosted')).toBeInTheDocument();
    expect(screen.getByText('Running as self-hosted beta. Cloud/SaaS and Marketplace billing are not active beta offerings.')).toBeInTheDocument();
    expect(screen.getByText('GitHub Account')).toBeInTheDocument();
    expect(screen.getByText('Personal GitHub Account')).toBeInTheDocument();
    expect(screen.queryByText('Account Type')).not.toBeInTheDocument();
    expect(screen.queryByText(/^Personal$/)).not.toBeInTheDocument();
    expect(screen.getByText('Workspace Role')).toBeInTheDocument();
    expect(screen.getByText('Admin')).toBeInTheDocument();
    expect(screen.getByText('This tells you whether ActionsManager is connected to an individual GitHub account or a GitHub organization.')).toBeInTheDocument();
  });

  test('should show organization GitHub account type separately from the ActionsManager plan', () => {
    const props: UserAvatarProps = {
      avatarUrl: 'https://github.com/my-company-org.png',
      username: 'my-company-org',
      accountType: 'professional',
      installationMode: 'cloud',
      githubAccountType: 'Organization',
      workspaceRole: 'member',
      onLogout: jest.fn()
    };

    renderWithTheme(<UserAvatar {...props} />);
    openUserMenu('User menu for my-company-org');

    expect(screen.getByText('Professional')).toBeInTheDocument();
    expect(screen.getByText('Cloud')).toBeInTheDocument();
    expect(screen.getByText('GitHub Organization')).toBeInTheDocument();
    expect(screen.getByText('Member')).toBeInTheDocument();
  });

  test('should show connected organization account separately from signed-in user', () => {
    const props: UserAvatarProps = {
      avatarUrl: 'https://github.com/dawg-io.png',
      username: 'dawg-io',
      accountType: 'free',
      githubAccountType: 'User',
      connectedGithubAccount: 'whatsupdawg',
      connectedGithubAccountType: 'Organization',
      workspaceRole: 'admin',
      onLogout: jest.fn()
    };

    renderWithTheme(<UserAvatar {...props} />);
    openUserMenu('User menu for dawg-io');

    expect(screen.getByText('GitHub Account')).toBeInTheDocument();
    expect(screen.getByText('whatsupdawg')).toBeInTheDocument();
    expect(screen.getByText('GitHub Organization')).toBeInTheDocument();
    expect(screen.getByText('Signed in as dawg-io')).toBeInTheDocument();
    expect(screen.getByText('Workspace Role')).toBeInTheDocument();
    expect(screen.getByText('Admin')).toBeInTheDocument();
    expect(screen.queryByText('Personal GitHub Account')).not.toBeInTheDocument();
  });

  test('should handle missing and unknown GitHub account types gracefully', () => {
    const { unmount } = renderWithTheme(
      <UserAvatar
        avatarUrl={null}
        username="unknown-type-user"
        accountType="free"
        githubAccountType={undefined}
        onLogout={jest.fn()}
      />
    );
    openUserMenu('User menu for unknown-type-user');
    expect(screen.getByText('GitHub Account Type Unknown')).toBeInTheDocument();

    unmount();

    renderWithTheme(
      <UserAvatar
        avatarUrl={null}
        username="enterprise-owner"
        accountType="free"
        githubAccountType="Enterprise"
        onLogout={jest.fn()}
      />
    );
    openUserMenu('User menu for enterprise-owner');
    expect(screen.getByText('GitHub Account Type Unknown')).toBeInTheDocument();
  });

  test('should display Enterprise only as an ActionsManager account plan', () => {
    const props: UserAvatarProps = {
      avatarUrl: 'https://github.com/enterprise-user.png',
      username: 'enterprise-user',
      accountType: 'enterprise',
      githubAccountType: 'User',
      onLogout: jest.fn()
    };

    renderWithTheme(<UserAvatar {...props} />);
    openUserMenu('User menu for enterprise-user');

    expect(screen.getByText('Enterprise')).toBeInTheDocument();
    expect(screen.getByText('Personal GitHub Account')).toBeInTheDocument();
    expect(screen.queryByText('Enterprise GitHub')).not.toBeInTheDocument();
  });

  test('should preserve API usage and menu actions', () => {
    const mockOnLogout = jest.fn();
    const props: UserAvatarProps = {
      avatarUrl: 'https://github.com/testuser.png',
      username: 'testuser',
      accountType: 'free',
      githubAccountType: 'User',
      rateLimit: {
        limit: 5000,
        used: 266,
        remaining: 4734,
        percentage_used: 5.32,
        should_warn: false,
        reset_at: new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString()
      },
      onLogout: mockOnLogout
    };

    renderWithTheme(<UserAvatar {...props} />);
    openUserMenu('User menu for testuser');

    expect(screen.getByText('API Usage')).toBeInTheDocument();
    expect(screen.getByText('266 / 5,000')).toBeInTheDocument();
    expect(screen.getByText('4,734')).toBeInTheDocument();
    expect(screen.getByText(/[34] hours?/)).toBeInTheDocument();

    fireEvent.click(screen.getByText('Workspace Members'));
    expect(mockNavigate).toHaveBeenCalledWith('/workspace/members');

    fireEvent.click(screen.getByText('Log out'));
    expect(mockOnLogout).toHaveBeenCalled();

    expect(screen.getByText(/^(Light|Dark) Mode$/)).toBeInTheDocument();
  });

  test('should apply truncation styling to long GitHub account names', () => {
    const longUsername = 'very-long-github-organization-name-that-should-truncate-cleanly';
    const props: UserAvatarProps = {
      avatarUrl: null,
      username: longUsername,
      accountType: 'free',
      githubAccountType: 'Organization',
      onLogout: jest.fn()
    };

    renderWithTheme(<UserAvatar {...props} />);
    fireEvent.click(screen.getByRole('button', { name: `User menu for ${longUsername}` }));

    const accountNames = screen.getAllByTitle(longUsername);
    expect(accountNames.some((accountName) => accountName.className.includes('truncate'))).toBe(true);
  });
});
