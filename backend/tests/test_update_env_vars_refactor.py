"""
Test script for the refactored update_env_vars helper functions
"""
import pytest
import sys
import os
from unittest.mock import patch, Mock, AsyncMock

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

from github_env_vars import (
    _validate_request_data,
    _get_auth_headers,
    _format_env_var_key,
    _check_variable_exists_in_repos,
    _get_truly_new_variables,
    _check_free_account_limits,
    _update_or_create_variable
)


class TestEnvVarsRefactor:
    """Test the refactored helper functions"""
    
    def test_validate_request_data(self):
        """Test request data validation"""
        data = {
            "user": "testuser",
            "repo_names": ["repo1", "repo2"],
            "env": [{"key": "VAR1", "value": "value1"}],
            "project_name": "  TEST_PROJECT  "
        }
        
        user, repo_names, env_vars, project_name = _validate_request_data(data)
        
        assert user == "testuser"
        assert repo_names == ["repo1", "repo2"]
        assert len(env_vars) == 1
        assert env_vars[0]["key"] == "VAR1"
        assert project_name == "TEST_PROJECT"
    
    def test_validate_request_data_missing_env(self):
        """Test request data validation with missing env"""
        data = {
            "user": "testuser",
            "repo_names": ["repo1"],
            "project_name": "TEST"
        }
        
        user, repo_names, env_vars, project_name = _validate_request_data(data)
        assert env_vars == []
    
    @patch('github_env_vars.user_tokens', {'testuser': 'fake_token'})
    def test_get_auth_headers_success(self):
        """Test getting auth headers for valid user"""
        headers = _get_auth_headers("testuser")
        
        assert headers is not None
        assert headers["Authorization"] == "token fake_token"
        assert "Accept" in headers
        assert "X-GitHub-Api-Version" in headers
    
    def test_get_auth_headers_no_user(self):
        """Test getting auth headers for invalid user"""
        headers = _get_auth_headers("nonexistent_user")
        assert headers == {}
    
    def test_format_env_var_key_simple(self):
        """Test formatting simple environment variable key"""
        formatted = _format_env_var_key("MY_VAR", "TEST")
        assert formatted == "AM_TEST_MY_VAR"
    
    def test_format_env_var_key_with_prefix(self):
        """Test formatting key that already has prefix"""
        formatted = _format_env_var_key("AM_TEST_MY_VAR", "TEST")
        assert formatted == "AM_TEST_MY_VAR"
    
    def test_format_env_var_key_lowercase(self):
        """Test formatting with lowercase input"""
        formatted = _format_env_var_key("my_var", "test")
        assert formatted == "AM_TEST_MY_VAR"
    
    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_check_variable_exists_in_repos_found(self, mock_client):
        """Test checking if variable exists - found"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get
        
        headers = {"Authorization": "token fake_token"}
        exists = await _check_variable_exists_in_repos("AM_TEST_VAR1", ["test/repo1", "test/repo2"], headers)
        
        assert exists is True
        assert mock_get.call_count == 1  # Should stop at first found
    
    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_check_variable_exists_in_repos_not_found(self, mock_client):
        """Test checking if variable exists - not found"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get
        
        headers = {"Authorization": "token fake_token"}
        exists = await _check_variable_exists_in_repos("AM_TEST_VAR1", ["test/repo1", "test/repo2"], headers)
        
        assert exists is False
        assert mock_get.call_count == 2  # Should check both repos
    
    @pytest.mark.asyncio
    @patch('github_env_vars._check_variable_exists_in_repos')
    async def test_get_truly_new_variables(self, mock_check_exists):
        """Test getting truly new variables"""
        # Mock that first variable exists, second doesn't
        mock_check_exists.side_effect = [True, False]
        
        env_vars = [
            {"key": "VAR1", "value": "value1"},
            {"key": "VAR2", "value": "value2"}
        ]
        
        new_vars = await _get_truly_new_variables(env_vars, "TEST", ["test/repo"], {})
        
        assert len(new_vars) == 1
        assert new_vars[0]["key"] == "VAR2"
    
    @pytest.mark.asyncio
    @patch('github_env_vars.count_project_env_vars')
    @patch('github_env_vars._get_truly_new_variables')
    async def test_check_free_account_limits_within_limits(self, mock_get_new_vars, mock_count):
        """Test free account limits check - within limits"""
        mock_count.return_value = 1
        mock_get_new_vars.return_value = [{"key": "VAR1"}]  # 1 new variable
        
        user_obj = Mock()
        user_obj.account_type = "free"
        
        result = await _check_free_account_limits(user_obj, "user", "TEST", ["repo"], [], {})
        
        assert result == {}  # No error (returns empty dict)
    
    @pytest.mark.asyncio
    @patch('github_env_vars.count_project_env_vars')
    @patch('github_env_vars._get_truly_new_variables')
    async def test_check_free_account_limits_exceeds_limits(self, mock_get_new_vars, mock_count):
        """Test free account limits check - exceeds limits"""
        mock_count.return_value = 2  # Already at limit
        mock_get_new_vars.return_value = [{"key": "VAR1"}]  # 1 new variable would exceed
        
        user_obj = Mock()
        user_obj.account_type = "free"
        
        result = await _check_free_account_limits(user_obj, "user", "TEST", ["repo"], [], {})
        
        assert result is not None
        assert result["status"] == 403
        assert "Free plan users can create up to 2" in result["error"]
    
    @pytest.mark.asyncio
    async def test_check_free_account_limits_premium_user(self):
        """Test free account limits check - premium user (no limits)"""
        user_obj = Mock()
        user_obj.account_type = "premium"
        
        result = await _check_free_account_limits(user_obj, "user", "TEST", ["repo"], [], {})
        
        assert result == {}  # No limits for premium users (returns empty dict)
    
    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_update_or_create_variable_update_existing(self, mock_client):
        """Test updating existing variable"""
        # Mock that variable exists
        mock_get_response = Mock(status_code=200)
        mock_patch_response = Mock(status_code=200)
        
        mock_client_instance = Mock()
        mock_client_instance.get = AsyncMock(return_value=mock_get_response)
        mock_client_instance.patch = AsyncMock(return_value=mock_patch_response)
        mock_client.return_value.__aenter__.return_value = mock_client_instance
        
        headers = {"Authorization": "token fake_token"}
        status = await _update_or_create_variable("test/repo", "AM_TEST_VAR1", "value1", headers)
        
        assert status == 200
        mock_client_instance.get.assert_called_once()
        mock_client_instance.patch.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_update_or_create_variable_create_new(self, mock_client):
        """Test creating new variable"""
        # Mock that variable doesn't exist
        mock_get_response = Mock(status_code=404)
        mock_post_response = Mock(status_code=201)
        
        mock_client_instance = Mock()
        mock_client_instance.get = AsyncMock(return_value=mock_get_response)
        mock_client_instance.post = AsyncMock(return_value=mock_post_response)
        mock_client.return_value.__aenter__.return_value = mock_client_instance
        
        headers = {"Authorization": "token fake_token"}
        status = await _update_or_create_variable("test/repo", "AM_TEST_VAR1", "value1", headers)
        
        assert status == 201
        mock_client_instance.get.assert_called_once()
        mock_client_instance.post.assert_called_once()


if __name__ == "__main__":
    # Run tests using pytest
    pytest.main([__file__, "-v"])