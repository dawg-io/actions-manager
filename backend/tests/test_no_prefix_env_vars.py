"""
Tests for no-prefix environment variable operations.

Validates that when a project has use_prefix=False:
- Variables are created/updated using the raw key name (no AM_ prefix)
- Variables are deleted using the raw key name
- Variables are synced using the raw key name
- Variable names are stored/removed in the ProjectEnvVar DB table
"""
import pytest
import sys
import os
from unittest.mock import patch, Mock, AsyncMock, MagicMock
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(__file__))

from github_env_vars import (
    _format_env_var_key,
    _update_or_create_variable,
    _store_env_var_names_in_db,
    update_env_vars,
    delete_env_vars,
    sync_env_var,
)
from models import Project, ProjectEnvVar


class TestFormatEnvVarKeyNoPrefix:
    """Test _format_env_var_key with use_prefix=False"""

    def test_simple_key_no_prefix(self):
        result = _format_env_var_key("API_URL", "MYPROJ", use_prefix=False)
        assert result == "API_URL"

    def test_lowercase_key_no_prefix(self):
        result = _format_env_var_key("api_url", "MYPROJ", use_prefix=False)
        assert result == "API_URL"

    def test_key_that_looks_like_prefix_no_prefix(self):
        """Even if key looks like it has AM_ prefix, no-prefix mode should just uppercase it"""
        result = _format_env_var_key("AM_MYPROJ_VAR", "MYPROJ", use_prefix=False)
        assert result == "AM_MYPROJ_VAR"

    def test_simple_key_with_prefix(self):
        result = _format_env_var_key("API_URL", "MYPROJ", use_prefix=True)
        assert result == "AM_MYPROJ_API_URL"


class TestUpdateEnvVarsNoPrefix:
    """Test the update_env_vars endpoint for no-prefix projects"""

    @pytest.mark.asyncio
    @patch('github_env_vars.user_tokens', {'testuser': 'fake_token'})
    async def test_update_creates_variable_without_prefix(self):
        """When use_prefix=False, variable should be created with raw key name"""
        mock_db = MagicMock(spec=Session)

        # Mock Account query
        mock_account = Mock()
        mock_account.account_type = "pro"

        # Mock Project query
        mock_project = Mock()
        mock_project.project_code = "MYPROJ"
        mock_project.use_prefix = False
        mock_project.project_id = 42

        def query_side_effect(model):
            mock_q = MagicMock()
            if model.__name__ == "Account":
                mock_q.filter.return_value.first.return_value = mock_account
            elif model.__name__ == "Project":
                mock_q.filter.return_value.first.return_value = mock_project
            elif model.__name__ == "ProjectEnvVar":
                # For _store_env_var_names_in_db existing names check
                mock_q.filter.return_value.all.return_value = []
            return mock_q

        mock_db.query.side_effect = query_side_effect

        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "user": "testuser",
            "repo_names": ["owner/repo1"],
            "env": [{"key": "API_URL", "value": "https://api.example.com"}],
            "project_name": "No Prefix Project"
        })

        with patch('github_env_vars._check_free_account_limits', new_callable=AsyncMock, return_value={}):
            with patch('github_env_vars._update_or_create_variable', new_callable=AsyncMock, return_value=201) as mock_create:
                with patch('github_env_vars._store_env_var_names_in_db') as mock_store:
                    result = await update_env_vars(mock_request, mock_db)

                    # Verify variable was created with raw key (no prefix)
                    mock_create.assert_called_once_with(
                        "owner/repo1", "API_URL", "https://api.example.com",
                        {
                            "Authorization": "token fake_token",
                            "Accept": "application/vnd.github+json",
                            "X-GitHub-Api-Version": "2022-11-28"
                        }
                    )
                    assert "message" in result
                    assert "results" in result
                    assert result["results"]["owner/repo1/env/API_URL"] == 201
                    # Verify DB store was called for no-prefix project
                    mock_store.assert_called_once()

    @pytest.mark.asyncio
    @patch('github_env_vars.user_tokens', {'testuser': 'fake_token'})
    async def test_update_with_prefix_true_adds_prefix(self):
        """When use_prefix=True, variable should be created with AM_ prefix"""
        mock_db = MagicMock(spec=Session)

        mock_account = Mock()
        mock_account.account_type = "pro"

        mock_project = Mock()
        mock_project.project_code = "MYPROJ"
        mock_project.use_prefix = True
        mock_project.project_id = 42

        def query_side_effect(model):
            mock_q = MagicMock()
            if model.__name__ == "Account":
                mock_q.filter.return_value.first.return_value = mock_account
            elif model.__name__ == "Project":
                mock_q.filter.return_value.first.return_value = mock_project
            return mock_q

        mock_db.query.side_effect = query_side_effect

        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "user": "testuser",
            "repo_names": ["owner/repo1"],
            "env": [{"key": "API_URL", "value": "https://api.example.com"}],
            "project_name": "Prefix Project"
        })

        with patch('github_env_vars._check_free_account_limits', new_callable=AsyncMock, return_value={}):
            with patch('github_env_vars._update_or_create_variable', new_callable=AsyncMock, return_value=201) as mock_create:
                result = await update_env_vars(mock_request, mock_db)

                mock_create.assert_called_once_with(
                    "owner/repo1", "AM_MYPROJ_API_URL", "https://api.example.com",
                    {
                        "Authorization": "token fake_token",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28"
                    }
                )
                assert result["results"]["owner/repo1/env/AM_MYPROJ_API_URL"] == 201


class TestDeleteEnvVarsNoPrefix:
    """Test the delete_env_vars endpoint for no-prefix projects"""

    @pytest.mark.asyncio
    @patch('github_env_vars.user_tokens', {'testuser': 'fake_token'})
    async def test_delete_uses_raw_key_for_no_prefix(self):
        """When use_prefix=False, delete should use raw key name"""
        mock_db = MagicMock(spec=Session)

        mock_project = Mock()
        mock_project.project_code = "MYPROJ"
        mock_project.use_prefix = False
        mock_project.project_id = 42

        mock_db.query.return_value.filter.return_value.first.return_value = mock_project
        mock_db.query.return_value.filter.return_value.delete.return_value = 1

        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "user": "testuser",
            "repo_names": ["owner/repo1"],
            "env": [{"env_key": "API_URL"}],
            "project_name": "No Prefix Project"
        })

        with patch('httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            mock_delete_response = Mock()
            mock_delete_response.status_code = 204
            mock_client.delete = AsyncMock(return_value=mock_delete_response)

            result = await delete_env_vars(mock_request, mock_db)

            # Verify delete URL uses raw key (no prefix)
            mock_client.delete.assert_called_once()
            call_url = mock_client.delete.call_args[0][0]
            assert call_url.endswith("/actions/variables/API_URL")
            assert "AM_MYPROJ_" not in call_url

            assert result["results"]["owner/repo1/env/API_URL"] == 204

    @pytest.mark.asyncio
    @patch('github_env_vars.user_tokens', {'testuser': 'fake_token'})
    async def test_delete_uses_prefix_for_prefix_project(self):
        """When use_prefix=True, delete should use prefixed key name"""
        mock_db = MagicMock(spec=Session)

        mock_project = Mock()
        mock_project.project_code = "MYPROJ"
        mock_project.use_prefix = True
        mock_project.project_id = 42

        mock_db.query.return_value.filter.return_value.first.return_value = mock_project

        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "user": "testuser",
            "repo_names": ["owner/repo1"],
            "env": [{"env_key": "API_URL"}],
            "project_name": "Prefix Project"
        })

        with patch('httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            mock_delete_response = Mock()
            mock_delete_response.status_code = 204
            mock_client.delete = AsyncMock(return_value=mock_delete_response)

            result = await delete_env_vars(mock_request, mock_db)

            call_url = mock_client.delete.call_args[0][0]
            assert call_url.endswith("/actions/variables/AM_MYPROJ_API_URL")

    @pytest.mark.asyncio
    @patch('github_env_vars.user_tokens', {'testuser': 'fake_token'})
    async def test_delete_removes_db_record_for_no_prefix(self):
        """When use_prefix=False, delete should also remove the DB record"""
        mock_db = MagicMock(spec=Session)

        mock_project = Mock()
        mock_project.project_code = "MYPROJ"
        mock_project.use_prefix = False
        mock_project.project_id = 42

        mock_db.query.return_value.filter.return_value.first.return_value = mock_project

        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "user": "testuser",
            "repo_names": ["owner/repo1"],
            "env": [{"env_key": "API_URL"}],
            "project_name": "No Prefix Project"
        })

        with patch('httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            mock_delete_response = Mock()
            mock_delete_response.status_code = 204
            mock_client.delete = AsyncMock(return_value=mock_delete_response)

            result = await delete_env_vars(mock_request, mock_db)

            # Verify DB commit was called (for removing the ProjectEnvVar record)
            mock_db.commit.assert_called()


class TestSyncEnvVarNoPrefix:
    """Test the sync_env_var endpoint for no-prefix projects"""

    @pytest.mark.asyncio
    @patch('github_env_vars.user_tokens', {'testuser': 'fake_token'})
    async def test_sync_uses_raw_key_for_no_prefix(self):
        """When use_prefix=False, sync should use raw key name"""
        mock_db = MagicMock(spec=Session)

        mock_project = Mock()
        mock_project.project_code = "MYPROJ"
        mock_project.use_prefix = False
        mock_project.project_id = 42

        mock_db.query.return_value.filter.return_value.first.return_value = mock_project

        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "user": "testuser",
            "repo_names": ["owner/repo1", "owner/repo2"],
            "env_key": "API_URL",
            "project_name": "No Prefix Project"
        })

        with patch('httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            # First repo has the variable, second doesn't
            mock_get_response = Mock()
            mock_get_response.status_code = 200
            mock_get_response.json.return_value = {"value": "https://api.example.com"}
            mock_client.get = AsyncMock(return_value=mock_get_response)

            with patch('github_env_vars._sync_env_var_to_repo', new_callable=AsyncMock, return_value=201) as mock_sync:
                result = await sync_env_var(mock_request, mock_db)

                # Verify the GET check uses raw key (no prefix)
                get_call_url = mock_client.get.call_args[0][0]
                assert "/actions/variables/API_URL" in get_call_url
                assert "AM_MYPROJ_" not in get_call_url

                # Verify sync uses raw key
                for call in mock_sync.call_args_list:
                    assert call[0][2] == "API_URL"  # formatted_key arg

    @pytest.mark.asyncio
    @patch('github_env_vars.user_tokens', {'testuser': 'fake_token'})
    async def test_sync_uses_prefix_for_prefix_project(self):
        """When use_prefix=True, sync should use prefixed key name"""
        mock_db = MagicMock(spec=Session)

        mock_project = Mock()
        mock_project.project_code = "MYPROJ"
        mock_project.use_prefix = True
        mock_project.project_id = 42

        mock_db.query.return_value.filter.return_value.first.return_value = mock_project

        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "user": "testuser",
            "repo_names": ["owner/repo1", "owner/repo2"],
            "env_key": "API_URL",
            "project_name": "Prefix Project"
        })

        with patch('httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            mock_get_response = Mock()
            mock_get_response.status_code = 200
            mock_get_response.json.return_value = {"value": "https://api.example.com"}
            mock_client.get = AsyncMock(return_value=mock_get_response)

            with patch('github_env_vars._sync_env_var_to_repo', new_callable=AsyncMock, return_value=201) as mock_sync:
                result = await sync_env_var(mock_request, mock_db)

                get_call_url = mock_client.get.call_args[0][0]
                assert "/actions/variables/AM_MYPROJ_API_URL" in get_call_url

                for call in mock_sync.call_args_list:
                    assert call[0][2] == "AM_MYPROJ_API_URL"


class TestStoreEnvVarNamesInDb:
    """Test _store_env_var_names_in_db for no-prefix mode"""

    def test_stores_uppercased_key_names(self):
        """Env var names should be stored uppercased"""
        mock_db = MagicMock(spec=Session)
        mock_project = Mock()
        mock_project.project_id = 42

        # No existing records
        mock_db.query.return_value.filter.return_value.all.return_value = []

        env_vars = [{"key": "api_url", "value": "test"}, {"key": "debug_mode", "value": "true"}]
        _store_env_var_names_in_db(env_vars, mock_project, mock_db)

        mock_db.add_all.assert_called_once()
        added_records = mock_db.add_all.call_args[0][0]
        names = {r.env_var_name for r in added_records}
        assert names == {"API_URL", "DEBUG_MODE"}
        mock_db.commit.assert_called_once()

    def test_skips_existing_names(self):
        """Should not duplicate already-stored names"""
        mock_db = MagicMock(spec=Session)
        mock_project = Mock()
        mock_project.project_id = 42

        # Simulate API_URL already exists in DB
        existing_row = Mock()
        existing_row.env_var_name = "API_URL"
        mock_db.query.return_value.filter.return_value.all.return_value = [existing_row]

        env_vars = [{"key": "API_URL", "value": "test"}]
        _store_env_var_names_in_db(env_vars, mock_project, mock_db)

        # Should not add any new records since it already exists
        # add_all may be called with empty list or not called
        if mock_db.add_all.called:
            added_records = mock_db.add_all.call_args[0][0]
            assert len(added_records) == 0
