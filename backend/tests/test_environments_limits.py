"""
Test script for deployment environments limits feature for free accounts
"""
import pytest
import sys
import os
from unittest.mock import patch, Mock, AsyncMock

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

from github_env_vars import count_project_environments


class TestEnvironmentLimits:
    """Test deployment environment limits for free accounts"""
    
    @pytest.mark.asyncio
    async def test_count_project_environments_no_auth(self):
        """Test count function with no authenticated user"""
        count = await count_project_environments("nonexistent_user", ["test/repo"])
        assert count == 0
    
    @pytest.mark.asyncio
    @patch('github_env_vars.user_tokens', {'testuser': 'fake_token'})
    @patch('httpx.AsyncClient')
    async def test_count_project_environments_success(self, mock_client):
        """Test count function with mocked GitHub API response"""
        # Mock GitHub API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "environments": [
                {"name": "development"},
                {"name": "staging"},
                {"name": "production"}
            ]
        }
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get
        
        count = await count_project_environments("testuser", ["test/repo"])
        assert count == 3
    
    @pytest.mark.asyncio
    @patch('github_env_vars.user_tokens', {'testuser': 'fake_token'})
    @patch('httpx.AsyncClient')
    async def test_count_project_environments_multiple_repos(self, mock_client):
        """Test count function with multiple repositories"""
        # Mock GitHub API response for both repos
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "environments": [
                {"name": "development"},
                {"name": "staging"}
            ]
        }
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get
        
        count = await count_project_environments("testuser", ["test/repo1", "test/repo2"])
        # Should return unique count (both repos have same environments)
        assert count == 2
        # Should have called GitHub API for both repos
        assert mock_get.call_count == 2
    
    @pytest.mark.asyncio
    @patch('github_env_vars.user_tokens', {'testuser': 'fake_token'})
    @patch('httpx.AsyncClient')
    async def test_count_project_environments_api_error(self, mock_client):
        """Test count function with GitHub API error"""
        # Mock GitHub API error response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get
        
        count = await count_project_environments("testuser", ["test/repo"])
        assert count == 0  # Should return 0 on error
    
    @pytest.mark.asyncio
    @patch('github_env_vars.user_tokens', {'testuser': 'fake_token'})
    @patch('httpx.AsyncClient')
    async def test_count_project_environments_empty_response(self, mock_client):
        """Test count function with empty GitHub API response"""
        # Mock GitHub API response with no environments
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"environments": []}
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get
        
        count = await count_project_environments("testuser", ["test/repo"])
        assert count == 0


if __name__ == "__main__":
    # Run tests using pytest
    pytest.main([__file__, "-v"])