import { getGitHubTokenStatus, getUserDetails, loginWithGitHubToken, removeGitHubToken, saveGitHubToken, testGitHubToken, UserDetails } from './user';
import config from '../config';

import type { MockedFunction } from 'vitest';
// Mock fetch globally
globalThis.fetch = vi.fn() as MockedFunction<typeof fetch>;

describe('user API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getUserDetails', () => {
    test('should fetch user details successfully', async () => {
      const mockUserData: UserDetails = {
        username: 'testuser',
        avatar_url: 'https://github.com/testuser.png',
        github_user: 'testuser',
        account_type: 'user',
        github_account_type: 'User',
        github_token: {
          configured: false,
          status: 'not_configured',
          message: 'No personal access token configured.'
        }
      };

      (fetch as MockedFunction<typeof fetch>).mockResolvedValueOnce({
        ok: true,
        json: async () => mockUserData,
      } as Response);

      const result = await getUserDetails('testuser');

      expect(fetch).toHaveBeenCalledWith(
        `${config.BACKEND_URL}/api/user/testuser`,
        expect.objectContaining({
          credentials: 'include'
        })
      );
      expect(result).toEqual(mockUserData);
    });

    test('should handle HTTP error responses', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      (fetch as MockedFunction<typeof fetch>).mockResolvedValueOnce({
        ok: false,
        status: 404,
      } as Response);

      const result = await getUserDetails('nonexistent');

      expect(fetch).toHaveBeenCalledWith(
        `${config.BACKEND_URL}/api/user/nonexistent`,
        expect.objectContaining({
          credentials: 'include'
        })
      );
      expect(result).toBeNull();
      expect(consoleSpy).toHaveBeenCalledWith(
        '❌ Error fetching user details:', 
        expect.any(Error)
      );
      
      consoleSpy.mockRestore();
    });

    test('should handle network errors', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      (fetch as MockedFunction<typeof fetch>).mockRejectedValueOnce(new Error('Network error'));

      const result = await getUserDetails('testuser');

      expect(result).toBeNull();
      expect(consoleSpy).toHaveBeenCalledWith(
        '❌ Error fetching user details:', 
        expect.any(Error)
      );
      
      consoleSpy.mockRestore();
    });

    test('should handle invalid JSON response', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      (fetch as MockedFunction<typeof fetch>).mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockRejectedValue(new Error('Invalid JSON')),
      } as unknown as Response);

      const result = await getUserDetails('testuser');

      expect(result).toBeNull();
      expect(consoleSpy).toHaveBeenCalledWith(
        '❌ Error fetching user details:', 
        expect.any(Error)
      );
      
      consoleSpy.mockRestore();
    });
  });

  describe('GitHub token APIs', () => {
    test('should fetch masked GitHub token status successfully', async () => {
      const mockStatus = {
        configured: true,
        status: 'valid',
        message: 'Token configured.',
        token_type: 'fine_grained_pat'
      };

      (fetch as MockedFunction<typeof fetch>).mockResolvedValueOnce({
        ok: true,
        json: async () => mockStatus,
      } as Response);

      const result = await getGitHubTokenStatus('testuser');

      expect(fetch).toHaveBeenCalledWith(
        `${config.BACKEND_URL}/api/user/testuser/github-token`,
        expect.objectContaining({
          credentials: 'include'
        })
      );
      expect(result).toEqual(mockStatus);
    });

    test('should send test token request with session credentials', async () => {
      const mockValidation = { status: 'valid', valid: true };
      (fetch as MockedFunction<typeof fetch>).mockResolvedValueOnce({
        ok: true,
        json: async () => mockValidation,
      } as Response);

      const result = await testGitHubToken('testuser', 'github_pat_123');

      expect(fetch).toHaveBeenCalledWith(
        `${config.BACKEND_URL}/api/user/testuser/github-token/test`,
        expect.objectContaining({
          method: 'POST',
          credentials: 'include',
          body: JSON.stringify({ token: 'github_pat_123' }),
          headers: expect.objectContaining({
            'Content-Type': 'application/json'
          })
        })
      );
      expect(result).toEqual(mockValidation);
    });

    test('should save token without returning the raw token', async () => {
      const mockSaveResult = {
        saved: true
      };

      (fetch as MockedFunction<typeof fetch>).mockResolvedValueOnce({
        ok: true,
        json: async () => mockSaveResult,
      } as Response);

      const result = await saveGitHubToken('testuser', 'ghp_secret');

      expect(result).toEqual(mockSaveResult);
    });

    test('should remove saved token', async () => {
      const mockRemoveResult = {
        removed: true,
        token: {
          configured: false,
          status: 'not_configured',
          message: 'No personal access token configured.'
        }
      };

      (fetch as MockedFunction<typeof fetch>).mockResolvedValueOnce({
        ok: true,
        json: async () => mockRemoveResult,
      } as Response);

      const result = await removeGitHubToken('testuser');

      expect(fetch).toHaveBeenCalledWith(
        `${config.BACKEND_URL}/api/user/testuser/github-token`,
        expect.objectContaining({
          method: 'DELETE',
          credentials: 'include',
          headers: expect.objectContaining({
            'Content-Type': 'application/json'
          })
        })
      );
      expect(result).toEqual(mockRemoveResult);
    });

    test('should authenticate directly with a GitHub token', async () => {
      const mockLoginResult = {
        user: 'testuser'
      };

      (fetch as MockedFunction<typeof fetch>).mockResolvedValueOnce({
        ok: true,
        json: async () => mockLoginResult,
      } as Response);

      const result = await loginWithGitHubToken('github_pat_123');

      expect(fetch).toHaveBeenCalledWith(
        `${config.BACKEND_URL}/auth/token`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ token: 'github_pat_123' })
        })
      );
      expect(result).toEqual(mockLoginResult);
    });
  });
});
