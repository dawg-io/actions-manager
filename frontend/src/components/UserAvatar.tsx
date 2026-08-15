import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { useTheme } from './ThemeContext';
import { ChevronDown, Sun, Moon, LogOut } from 'lucide-react';
import { getGitHubTokenStatus, removeGitHubToken, saveGitHubToken, testGitHubToken } from '../api/user';
import type { GitHubTokenStatus } from '../api/user';
import {
  Avatar,
  AvatarImage,
  AvatarFallback,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
} from './ui';
import { getDocsUrl } from '../help/helpLinks';

// Define the props interface for the UserAvatar component
interface RateLimitInfo {
  limit: number;
  used: number;
  remaining: number;
  percentage_used: number;
  should_warn: boolean;
  reset_at: string;
}

interface UserAvatarProps {
  avatarUrl: string | null;
  username: string | null;
  accountType: string;
  installationMode?: string | null;
  githubAccountType?: string | null;
  connectedGithubAccount?: string | null;
  connectedGithubAccountType?: string | null;
  workspaceRole?: string;
  rateLimit?: RateLimitInfo;
  githubToken?: GitHubTokenStatus;
  onGitHubAuthUpdated?: () => void;
  onLogout?: () => void;
}

const UserAvatar: React.FC<UserAvatarProps> = ({
  avatarUrl,
  username,
  accountType,
  installationMode,
  githubAccountType,
  connectedGithubAccount,
  connectedGithubAccountType,
  workspaceRole,
  rateLimit,
  githubToken,
  onGitHubAuthUpdated,
  onLogout
}) => {
  const { isDarkMode, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [tokenValue, setTokenValue] = useState<string>('');
  const [tokenStatus, setTokenStatus] = useState<GitHubTokenStatus | undefined>(githubToken);
  const [tokenFeedback, setTokenFeedback] = useState<string | null>(githubToken?.message ?? null);
  const [tokenAction, setTokenAction] = useState<'idle' | 'testing' | 'saving' | 'removing'>('idle');
  const [showTokenManager, setShowTokenManager] = useState<boolean>(false);

  useEffect(() => {
    setTokenStatus(githubToken);
    setTokenFeedback(githubToken?.message ?? null);
  }, [githubToken]);

  const handleThemeToggle = (): void => {
    toggleTheme();
    // Keep dropdown open after theme change - DropdownMenu handles this automatically
  };

  const handleLogout = (): void => {
    if (onLogout) {
      onLogout();
    }
  };

  const formatAccountPlan = (type: string, mode?: string | null): string => {
    if (mode?.toLowerCase() === 'self-hosted') return 'Self-Hosted Beta';
    if (!type) return 'Unknown';
    if (type.toLowerCase() === 'pro') return 'Professional';
    if (type.toLowerCase() === 'professional') return 'Professional';
    return type.charAt(0).toUpperCase() + type.slice(1);
  };

  const formatGitHubAccountType = (type?: string | null): string => {
    if (type === 'User') return 'Personal GitHub Account';
    if (type === 'Organization') return 'GitHub Organization';
    return 'GitHub Account Type Unknown';
  };

  const formatInstallationMode = (mode?: string | null): string => {
    if (!mode) return 'Unknown';
    return mode.toLowerCase() === 'cloud' ? 'Cloud' : 'Self-hosted';
  };

  const formatWorkspaceRole = (role?: string): string => {
    if (role === 'admin') return 'Admin';
    if (role === 'member') return 'Member';
    return 'Read Only';
  };

  const formatResetTime = (resetAt: string): string => {
    if (!resetAt) return 'Unknown';
    try {
      const resetDate = new Date(resetAt);
      const now = new Date();
      const diffMs = resetDate.getTime() - now.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      
      if (diffMins < 60) {
        return `${diffMins} minute${diffMins !== 1 ? 's' : ''}`;
      }
      const diffHours = Math.floor(diffMins / 60);
      return `${diffHours} hour${diffHours !== 1 ? 's' : ''}`;
    } catch {
      return 'Unknown';
    }
  };

  const getRateLimitIcon = (): string => {
    if (!rateLimit) return '✅';
    if (rateLimit.percentage_used >= 100) return '🚫';
    if (rateLimit.should_warn) return '⚠️';
    return '✅';
  };

  const displayedGitHubAccount = connectedGithubAccount || username;
  const displayedGitHubAccountType = connectedGithubAccountType || githubAccountType || null;
  const shouldShowSignedInUser = Boolean(
    username
      && displayedGitHubAccount
      && username.toLowerCase() !== displayedGitHubAccount.toLowerCase()
  );
  const tokenConfigured = Boolean(tokenStatus?.configured);

  const tokenStatusLabel = useMemo((): string => {
    if (!tokenConfigured) return 'Not configured';
    switch (tokenStatus?.status) {
      case 'token_invalid':
        return 'Invalid or expired';
      case 'missing_scopes':
      case 'insufficient_repo_permissions':
        return 'Missing required permissions';
      default:
        return 'Configured';
    }
  }, [tokenConfigured, tokenStatus?.status]);

  const tokenTypeLabel = useMemo((): string | null => {
    switch (tokenStatus?.token_type) {
      case 'fine_grained_pat':
        return 'Fine-grained PAT';
      case 'classic_pat':
        return 'Classic PAT';
      case 'oauth_token':
        return 'OAuth token';
      default:
        return null;
    }
  }, [tokenStatus?.token_type]);

  const handleTestToken = async (): Promise<void> => {
    if (!username || !tokenValue.trim()) {
      setTokenFeedback('Enter a GitHub token before testing.');
      return;
    }

    try {
      setTokenAction('testing');
      const result = await testGitHubToken(username, tokenValue);
      setTokenFeedback(result.message);
    } catch (error: any) {
      setTokenFeedback(error?.message || 'Failed to test token.');
    } finally {
      setTokenAction('idle');
    }
  };

  const handleSaveToken = async (): Promise<void> => {
    if (!username || !tokenValue.trim()) {
      setTokenFeedback('Enter a GitHub token before saving.');
      return;
    }

    try {
      setTokenAction('saving');
      await saveGitHubToken(username, tokenValue);
      const refreshedStatus = await getGitHubTokenStatus(username);
      if (refreshedStatus) {
        setTokenStatus(refreshedStatus);
        setTokenFeedback(refreshedStatus.message);
      } else {
        setTokenFeedback('Token saved.');
      }
      setTokenValue('');
      onGitHubAuthUpdated?.();
    } catch (error: any) {
      setTokenFeedback(error?.message || 'Failed to save token.');
    } finally {
      setTokenAction('idle');
    }
  };

  const handleRemoveToken = async (): Promise<void> => {
    if (!username) return;
    try {
      setTokenAction('removing');
      const result = await removeGitHubToken(username);
      setTokenStatus(result.token);
      setTokenFeedback('Stored token removed. OAuth will be used when available.');
      setTokenValue('');
      onGitHubAuthUpdated?.();
    } catch (error: any) {
      setTokenFeedback(error?.message || 'Failed to remove token.');
    } finally {
      setTokenAction('idle');
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button 
          className="flex items-center gap-2 px-3 py-2 rounded-md bg-hover-bg dark:bg-hover-dark-bg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors border border-border dark:border-border-dark"
          aria-label={`User menu for ${username || 'user'}`}
        >
          <Avatar className="h-8 w-8">
            <AvatarImage 
              src={avatarUrl || undefined} 
              alt={`${username}'s avatar`}
            />
            <AvatarFallback className="text-sm font-medium">
              {username ? username.charAt(0).toUpperCase() : '?'}
            </AvatarFallback>
          </Avatar>
          <span
            className="max-w-[10rem] truncate text-sm font-medium text-text-primary dark:text-text-primary-dark"
            title={username || undefined}
          >
            {username}
          </span>
          <ChevronDown className="h-4 w-4 text-text-secondary dark:text-secondary-dark" />
        </button>
      </DropdownMenuTrigger>
      
      <DropdownMenuContent align="end" className="w-80 max-w-[calc(100vw-1rem)] max-h-[85vh] overflow-y-auto">
        {/* Account Information */}
        <DropdownMenuLabel className="font-normal">
          <div className="space-y-3">
            <div className="space-y-1">
              <p className="text-xs font-medium text-text-secondary dark:text-secondary-dark">Account Plan</p>
              <p className="truncate text-sm font-semibold text-text-primary dark:text-text-primary-dark">
                {formatAccountPlan(accountType, installationMode)}
              </p>
              <p className="text-xs leading-snug text-text-secondary dark:text-secondary-dark">
                {installationMode?.toLowerCase() === 'self-hosted'
                  ? 'Self-hosted beta access. Paid plans are not currently available.'
                  : 'Your ActionsManager subscription tier.'}
              </p>
            </div>

            <div className="space-y-1">
              <p className="text-xs font-medium text-text-secondary dark:text-secondary-dark">Deployment Mode</p>
              <p className="truncate text-sm font-semibold text-text-primary dark:text-text-primary-dark">
                {formatInstallationMode(installationMode)}
              </p>
              <p className="text-xs leading-snug text-text-secondary dark:text-secondary-dark">
                {installationMode?.toLowerCase() === 'self-hosted'
                  ? 'Running as self-hosted beta. Cloud/SaaS and Marketplace billing are not active beta offerings.'
                  : 'Self-hosted tiers use license keys. Cloud tiers are managed by GitHub Marketplace.'}
              </p>
            </div>

            <div className="space-y-1">
              <p className="text-xs font-medium text-text-secondary dark:text-secondary-dark">GitHub Account</p>
              <div className="flex min-w-0 items-center gap-2">
                <p
                  className="min-w-0 flex-1 truncate text-sm font-semibold text-text-primary dark:text-text-primary-dark"
                  title={displayedGitHubAccount || undefined}
                >
                  {displayedGitHubAccount || 'Unknown GitHub Account'}
                </p>
                <span className="shrink-0 whitespace-nowrap rounded-full border border-border bg-hover-bg px-2 py-0.5 text-[11px] font-medium text-text-secondary dark:border-border-dark dark:bg-hover-dark-bg dark:text-secondary-dark">
                  {formatGitHubAccountType(displayedGitHubAccountType)}
                </span>
              </div>
              {shouldShowSignedInUser && (
                <p className="truncate text-xs text-text-secondary dark:text-secondary-dark" title={username || undefined}>
                  Signed in as {username}
                </p>
              )}
              <p className="text-xs leading-snug text-text-secondary dark:text-secondary-dark">
                This tells you whether ActionsManager is connected to an individual GitHub account or a GitHub organization.
              </p>
            </div>

            {workspaceRole && (
              <div className="space-y-1">
                <p className="text-xs font-medium text-text-secondary dark:text-secondary-dark">Workspace Role</p>
                <p className="text-sm font-semibold text-text-primary dark:text-text-primary-dark">
                  {formatWorkspaceRole(workspaceRole)}
                </p>
              </div>
            )}

            <div className="space-y-2 rounded-md border border-border p-3 dark:border-border-dark">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-xs font-medium text-text-secondary dark:text-secondary-dark">GitHub Authentication</p>
                  <p className="text-sm font-semibold text-text-primary dark:text-text-primary-dark">
                    {tokenStatusLabel}{tokenTypeLabel ? ` · ${tokenTypeLabel}` : ''}
                  </p>
                </div>
                <Button
                  onClick={() => setShowTokenManager((prev) => !prev)}
                  size="sm"
                  type="button"
                  variant="outline"
                  className="shrink-0"
                >
                  {showTokenManager ? 'Close' : 'Manage authentication'}
                </Button>
              </div>

              {showTokenManager && (
                <div className="space-y-2 pt-1 border-t border-border dark:border-border-dark">
                  <p className="text-xs leading-snug text-text-secondary dark:text-secondary-dark">
                    OAuth remains the default. Fine-grained personal access tokens are recommended for simpler self-hosted setup, with classic PATs also supported.
                  </p>
                  <p className="text-xs leading-snug text-text-secondary dark:text-secondary-dark">
                    Recommended minimum permissions: Metadata read, Contents read/write, Actions read/write, plus Pull requests / Secrets / Variables only if you use those features.
                  </p>
                  <div className="flex flex-col gap-1">
                    <a
                      className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
                      href="https://github.com/settings/tokens"
                      rel="noreferrer"
                      target="_blank"
                    >
                      Create or review tokens in GitHub developer settings
                    </a>
                    <a
                      className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
                      href={getDocsUrl("tokenHandling")}
                      rel="noreferrer"
                      target="_blank"
                    >
                      Authentication &amp; settings docs →
                    </a>
                  </div>

                  {tokenTypeLabel && (
                    <p className="text-xs text-text-secondary dark:text-secondary-dark">
                      Saved token type: <span className="font-medium text-text-primary dark:text-text-primary-dark">{tokenTypeLabel}</span>
                    </p>
                  )}

                  <div className="space-y-2">
                    <Input
                      aria-label="GitHub personal access token"
                      autoComplete="off"
                      onChange={(event) => setTokenValue(event.target.value)}
                      placeholder={tokenConfigured ? 'Replace configured token' : 'Paste GitHub token'}
                      type="password"
                      value={tokenValue}
                    />
                    <div className="flex flex-wrap gap-2">
                      <Button
                        disabled={tokenAction !== 'idle'}
                        onClick={handleTestToken}
                        size="sm"
                        type="button"
                        variant="outline"
                      >
                        {tokenAction === 'testing' ? 'Testing…' : 'Test token'}
                      </Button>
                      <Button
                        disabled={tokenAction !== 'idle'}
                        onClick={handleSaveToken}
                        size="sm"
                        type="button"
                      >
                        {tokenAction === 'saving'
                          ? 'Saving…'
                          : tokenConfigured
                            ? 'Replace token'
                            : 'Save token'}
                      </Button>
                      {tokenConfigured && (
                        <Button
                          disabled={tokenAction !== 'idle'}
                          onClick={handleRemoveToken}
                          size="sm"
                          type="button"
                          variant="outline"
                        >
                          {tokenAction === 'removing' ? 'Removing…' : 'Remove token'}
                        </Button>
                      )}
                    </div>
                  </div>

                  {tokenFeedback && (
                    <p className="text-xs leading-snug text-text-secondary dark:text-secondary-dark">
                      {tokenFeedback}
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </DropdownMenuLabel>
        
        {/* Rate Limit Information */}
        {rateLimit && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="font-normal">
              <div className="flex flex-col space-y-2">
                <div className="flex items-center gap-2">
                  <span>{getRateLimitIcon()}</span>
                  <span className="text-sm font-medium">API Usage</span>
                </div>
                
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-text-secondary dark:text-secondary-dark">Used:</span>
                    <span className="text-text-primary dark:text-text-primary-dark">
                      {rateLimit.used.toLocaleString()} / {rateLimit.limit.toLocaleString()}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary dark:text-secondary-dark">Remaining:</span>
                    <span className="text-text-primary dark:text-text-primary-dark">
                      {rateLimit.remaining.toLocaleString()}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary dark:text-secondary-dark">Resets in:</span>
                    <span className="text-text-primary dark:text-text-primary-dark">
                      {formatResetTime(rateLimit.reset_at)}
                    </span>
                  </div>
                </div>
                
                {rateLimit.percentage_used >= 100 && (
                  <div className="mt-2 p-2 rounded-md bg-red-50 dark:bg-red-900/20 text-xs">
                    <p className="font-semibold text-red-900 dark:text-red-200">Limit Exceeded</p>
                    <p className="text-red-700 dark:text-red-300">API calls are blocked until reset.</p>
                  </div>
                )}
                
                {rateLimit.should_warn && rateLimit.percentage_used < 100 && (
                  <div className="mt-2 p-2 rounded-md bg-yellow-50 dark:bg-yellow-900/20 text-xs">
                    <p className="font-semibold text-yellow-900 dark:text-yellow-200">Low API Quota</p>
                    <p className="text-yellow-700 dark:text-yellow-300">Less than 10% remaining.</p>
                  </div>
                )}
              </div>
            </DropdownMenuLabel>
          </>
        )}
        
        <DropdownMenuSeparator />
        
        {/* Workspace Members Link */}
        <DropdownMenuItem
          onClick={() => { navigate('/workspace/members'); }}
          className="cursor-pointer"
        >
          <span className="mr-2">👥</span>
          <span>Workspace Members</span>
        </DropdownMenuItem>

        {/* Notifications Link */}
        <DropdownMenuItem
          onClick={() => { navigate('/workspace/notifications'); }}
          className="cursor-pointer"
        >
          <span className="mr-2">🔔</span>
          <span>Notifications</span>
        </DropdownMenuItem>

        {/* Drift Settings Link */}
        <DropdownMenuItem
          onClick={() => { navigate('/workspace/drift'); }}
          className="cursor-pointer"
        >
          <span className="mr-2">🔍</span>
          <span>Drift Settings</span>
        </DropdownMenuItem>

        {/* Backup Link */}
        <DropdownMenuItem
          onClick={() => { navigate('/workspace/backup'); }}
          className="cursor-pointer"
        >
          <span className="mr-2">💾</span>
          <span>Backup</span>
        </DropdownMenuItem>

        {/* Theme Toggle */}
        <DropdownMenuItem 
          onClick={handleThemeToggle}
          className="cursor-pointer"
        >
          {isDarkMode ? (
            <>
              <Sun className="mr-2 h-4 w-4" />
              <span>Light Mode</span>
            </>
          ) : (
            <>
              <Moon className="mr-2 h-4 w-4" />
              <span>Dark Mode</span>
            </>
          )}
        </DropdownMenuItem>
        
        {/* Logout */}
        {onLogout && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem 
              onClick={handleLogout}
              className="cursor-pointer text-red-600 dark:text-red-400"
            >
              <LogOut className="mr-2 h-4 w-4" />
              <span>Log out</span>
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default UserAvatar;
