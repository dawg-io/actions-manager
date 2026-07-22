"""
Test script for environment variables limits feature for free accounts
"""
import pytest
import sys
import os
from unittest.mock import patch, Mock, AsyncMock

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

from github_env_vars import count_project_env_vars


class TestEnvVarsLimits:
    """Test environment variables limits for free accounts"""
    
    @pytest.mark.asyncio
    async def test_count_project_env_vars_no_auth(self):
        """Test count function returns 0 when user not authenticated"""
        count = await count_project_env_vars("nonexistent_user", "TEST", ["test/repo"])
        assert count == 0
    
    @pytest.mark.asyncio
    @patch('github_env_vars.user_tokens', {'testuser': 'fake_token'})
    @patch('httpx.AsyncClient')
    async def test_count_project_env_vars_success(self, mock_client):
        """Test count function with mocked GitHub API response"""
        # Mock GitHub API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "variables": [
                {"name": "AM_TEST_VAR1"},
                {"name": "AM_TEST_VAR2"},
                {"name": "OTHER_VAR"},  # Should be ignored
                {"name": "AM_OTHER_PROJECT_VAR"}  # Should be ignored
            ]
        }
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get
        
        count = await count_project_env_vars("testuser", "TEST", ["test/repo"])
        assert count == 2  # Only AM_TEST_* variables should be counted
    
    @pytest.mark.asyncio
    @patch('github_env_vars.user_tokens', {'testuser': 'fake_token'})
    @patch('httpx.AsyncClient')
    async def test_count_project_env_vars_multiple_repos(self, mock_client):
        """Test count function with multiple repositories"""
        # Mock GitHub API response for both repos
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "variables": [
                {"name": "AM_TEST_VAR1"},
                {"name": "AM_TEST_VAR2"}
            ]
        }
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get
        
        count = await count_project_env_vars("testuser", "TEST", ["test/repo1", "test/repo2"])
        # Should return unique count (both repos have same variables)
        assert count == 2
        # Should have called GitHub API for both repos
        assert mock_get.call_count == 2
    
    @pytest.mark.asyncio
    @patch('github_env_vars.user_tokens', {'testuser': 'fake_token'})
    @patch('httpx.AsyncClient')
    async def test_count_project_env_vars_api_error(self, mock_client):
        """Test count function handles API errors gracefully"""
        # Mock GitHub API error response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get
        
        count = await count_project_env_vars("testuser", "TEST", ["test/repo"])
        assert count == 0  # Should return 0 on error


if __name__ == "__main__":
    # Run tests using pytest
    pytest.main([__file__, "-v"])