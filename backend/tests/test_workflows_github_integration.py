"""
Comprehensive tests for workflows.py GitHub integration functions.
Tests GitHub API interactions with mocked responses.
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch, Mock
import base64
import re

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from workflows import (
    get_workflow_from_github,
    get_all_workflow_shas,
    get_default_branch,
    verify_workflow_belongs_to_project,
    _resolve_branches_for_repo,
    _check_existing_workflow_content,
    _update_workflow_to_github,
    _update_workflow_git_hash,
    _ensure_workflows_directory_exists,
    GITHUB_API_URL
)
from models import Workflow
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_github_integration.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class TestGitHubIntegration:
    """Test class for GitHub API integration functions."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Set up the test database before each test."""
        Base.metadata.create_all(bind=engine)
        yield
        Base.metadata.drop_all(bind=engine)

    def test_get_workflow_from_github_success(self):
        """Test successfully fetching a workflow from GitHub."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "default_branch": "main"
        }
        
        mock_file_response = Mock()
        mock_file_response.status_code = 200
        mock_file_response.json.return_value = {
            "content": base64.b64encode(b"name: Test\non: push").decode(),
            "sha": "abc123"
        }
        
        with patch('workflows.requests.get') as mock_get:
            mock_get.side_effect = [mock_response, mock_file_response]
            
            result = get_workflow_from_github("owner", "repo", "test.yml", "token123")
            
            assert result is not None
            assert result["content"] == "name: Test\non: push"
            assert result["sha"] == "abc123"

    def test_get_workflow_from_github_not_found(self):
        """Test fetching a workflow that doesn't exist."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "default_branch": "main"
        }
        
        mock_file_response = Mock()
        mock_file_response.status_code = 404
        
        with patch('workflows.requests.get') as mock_get:
            mock_get.side_effect = [mock_response, mock_file_response]
            
            result = get_workflow_from_github("owner", "repo", "nonexistent.yml", "token123")
            
            assert result is None

    def test_get_workflow_from_github_api_error(self):
        """Test handling GitHub API errors."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "default_branch": "main"
        }
        
        mock_file_response = Mock()
        mock_file_response.status_code = 500
        
        with patch('workflows.requests.get') as mock_get:
            mock_get.side_effect = [mock_response, mock_file_response]
            
            with pytest.raises(Exception) as exc_info:
                get_workflow_from_github("owner", "repo", "test.yml", "token123")
            
            assert "GitHub API error" in str(exc_info.value)

    def test_get_default_branch_success(self):
        """Test successfully getting default branch."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "default_branch": "develop"
        }
        
        with patch('workflows.requests.get', return_value=mock_response):
            headers = {"Authorization": "token test"}
            result = get_default_branch("owner", "repo", headers)
            
            assert result == "develop"

    def test_get_default_branch_fallback(self):
        """Test default branch fallback to 'main'."""
        mock_response = Mock()
        mock_response.status_code = 404
        
        with patch('workflows.requests.get', return_value=mock_response):
            headers = {"Authorization": "token test"}
            result = get_default_branch("owner", "repo", headers)
            
            assert result == "main"

    def test_verify_workflow_belongs_to_project_with_indicator(self):
        """Test workflow verification with project code indicator."""
        workflow_content = "name: Test\non: push\nenv:\n  PROJECT: AM_TEST_123"
        
        result = verify_workflow_belongs_to_project(workflow_content, "TEST", "test.yml")
        
        assert result == True

    def test_verify_workflow_belongs_to_project_different_project(self):
        """Test workflow verification rejects different project code."""
        # Use a hardcoded project code from the other_project_patterns list
        workflow_content = "name: Test\non: push\nenv:\n  PROJECT: AM_ABCD_workflow"
        
        result = verify_workflow_belongs_to_project(workflow_content, "TEST", "test.yml")
        
        assert result == False

    def test_verify_workflow_belongs_to_project_no_indicators(self):
        """Test workflow verification with no project indicators."""
        workflow_content = "name: Test\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest"
        
        # Should return True for backward compatibility
        result = verify_workflow_belongs_to_project(workflow_content, "TEST", "test.yml")
        
        assert result == True

    def test_verify_workflow_belongs_to_project_empty_content(self):
        """Test workflow verification with empty content."""
        result = verify_workflow_belongs_to_project("", "TEST", "test.yml")
        
        assert result == False

    def test_verify_workflow_belongs_to_project_none_content(self):
        """Test workflow verification with None content."""
        result = verify_workflow_belongs_to_project(None, "TEST", "test.yml")
        
        assert result == False

    def test_resolve_branches_for_repo_default(self):
        """Test resolving branches with 'default' option."""
        headers = {"Authorization": "token test"}
        
        with patch('workflows.get_default_branch', return_value="main"):
            result = _resolve_branches_for_repo(
                "owner", "repo", "default", "", 30, headers
            )
            
            assert result == ["main"]

    def test_resolve_branches_for_repo_pattern_match(self):
        """Test resolving branches with pattern matching."""
        mock_branches_response = Mock()
        mock_branches_response.status_code = 200
        mock_branches_response.json.return_value = [
            {"name": "main"},
            {"name": "develop"},
            {"name": "feature/test"},
            {"name": "feature/new"}
        ]
        
        # Mock commits responses for recency check
        mock_commit_response = Mock()
        mock_commit_response.status_code = 200
        from datetime import datetime, timezone
        recent_date = datetime.now(timezone.utc).isoformat()
        mock_commit_response.json.return_value = [
            {"commit": {"committer": {"date": recent_date}}}
        ]
        
        headers = {"Authorization": "token test"}
        
        with patch('workflows.requests.get') as mock_get:
            # First call returns branches, subsequent calls return commits
            mock_get.side_effect = [mock_branches_response] + [mock_commit_response] * 4
            
            result = _resolve_branches_for_repo(
                "owner", "repo", "pattern", "^feature/.*", 30, headers
            )
            
            assert len(result) == 2
            assert "feature/test" in result
            assert "feature/new" in result

    def test_resolve_branches_for_repo_pattern_no_match(self):
        """Test resolving branches with pattern that doesn't match."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"name": "main"},
            {"name": "develop"}
        ]
        
        headers = {"Authorization": "token test"}
        
        with patch('workflows.requests.get', return_value=mock_response):
            with patch('workflows.get_default_branch', return_value="main"):
                result = _resolve_branches_for_repo(
                    "owner", "repo", "pattern", "^feature/.*", 30, headers
                )
                
                # Should fall back to default branch
                assert result == ["main"]

    def test_resolve_branches_for_repo_exact_name_match(self):
        """Test resolving branches with exact branch name (invalid regex falls back to exact match)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"name": "main"},
            {"name": "develop"},
            {"name": "feature/test"}
        ]
        
        headers = {"Authorization": "token test"}
        
        # Mock commits response for recency check
        mock_commit_response = Mock()
        mock_commit_response.status_code = 200
        from datetime import datetime, timezone
        recent_date = datetime.now(timezone.utc).isoformat()
        mock_commit_response.json.return_value = [
            {"commit": {"committer": {"date": recent_date}}}
        ]
        
        with patch('workflows.requests.get') as mock_get:
            # First call returns branches, second call returns commits
            mock_get.side_effect = [mock_response, mock_commit_response]
            
            # Use invalid regex pattern (will fall back to exact match)
            result = _resolve_branches_for_repo(
                "owner", "repo", "pattern", "develop", 30, headers
            )
            
            assert result == ["develop"]
    
    def test_resolve_branches_for_repo_stale_branch_filtering(self):
        """Test that stale branches are filtered out by recency check."""
        mock_branches_response = Mock()
        mock_branches_response.status_code = 200
        mock_branches_response.json.return_value = [
            {"name": "main"},
            {"name": "feature/recent"},
            {"name": "feature/stale"}
        ]
        
        headers = {"Authorization": "token test"}
        
        from datetime import datetime, timezone, timedelta
        recent_date = datetime.now(timezone.utc).isoformat()
        stale_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        
        # Mock commits responses - recent for first two, stale for last
        mock_recent_commit = Mock()
        mock_recent_commit.status_code = 200
        mock_recent_commit.json.return_value = [
            {"commit": {"committer": {"date": recent_date}}}
        ]
        
        mock_stale_commit = Mock()
        mock_stale_commit.status_code = 200
        mock_stale_commit.json.return_value = [
            {"commit": {"committer": {"date": stale_date}}}
        ]
        
        with patch('workflows.requests.get') as mock_get:
            # First call returns branches, subsequent calls return commits.
            # Note: 'main' does NOT match '^feature/.*' so no commit call is
            # made for it – only feature/recent and feature/stale are checked.
            mock_get.side_effect = [
                mock_branches_response,
                mock_recent_commit,  # feature/recent
                mock_stale_commit    # feature/stale (will be filtered out)
            ]
            
            result = _resolve_branches_for_repo(
                "owner", "repo", "pattern", "^feature/.*", 30, headers
            )
            
            # Only feature/recent should be included (main doesn't match pattern, feature/stale is too old)
            assert len(result) == 1
            assert "feature/recent" in result
            assert "feature/stale" not in result

    def test_check_existing_workflow_content_exists_unchanged(self):
        """Test checking workflow content that hasn't changed."""
        encoded_content = base64.b64encode(b"name: Test\non: push").decode()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sha": "abc123",
            "content": encoded_content
        }
        
        headers = {"Authorization": "token test"}
        
        with patch('workflows.requests.get', return_value=mock_response):
            sha, unchanged = _check_existing_workflow_content(
                "https://api.github.com/repos/owner/repo/contents/test.yml",
                encoded_content,
                headers
            )
            
            assert sha == "abc123"
            assert unchanged == True

    def test_check_existing_workflow_content_exists_changed(self):
        """Test checking workflow content that has changed."""
        old_content = base64.b64encode(b"name: Test\non: push").decode()
        new_content = base64.b64encode(b"name: Test Updated\non: pull_request").decode()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sha": "abc123",
            "content": old_content
        }
        
        headers = {"Authorization": "token test"}
        
        with patch('workflows.requests.get', return_value=mock_response):
            sha, unchanged = _check_existing_workflow_content(
                "https://api.github.com/repos/owner/repo/contents/test.yml",
                new_content,
                headers
            )
            
            assert sha == "abc123"
            assert unchanged == False

    def test_check_existing_workflow_content_not_found(self):
        """Test checking workflow content that doesn't exist."""
        encoded_content = base64.b64encode(b"name: Test\non: push").decode()
        
        mock_response = Mock()
        mock_response.status_code = 404
        
        headers = {"Authorization": "token test"}
        
        with patch('workflows.requests.get', return_value=mock_response):
            sha, unchanged = _check_existing_workflow_content(
                "https://api.github.com/repos/owner/repo/contents/test.yml",
                encoded_content,
                headers
            )
            
            assert sha is None
            assert unchanged == False

    def test_update_workflow_to_github_new_file(self):
        """Test updating a workflow to GitHub (new file) on AM branch."""
        workflow = {
            "name": "test-workflow",
            "content": "name: Test\non: push"
        }
        
        # Mock for file check (doesn't exist)
        mock_file_response = Mock()
        mock_file_response.status_code = 404
        
        # Mock for branch check (exists)
        mock_branch_response = Mock()
        mock_branch_response.status_code = 200
        
        # Mock for directory check (already exists)
        mock_dir_response = Mock()
        mock_dir_response.status_code = 200
        mock_dir_response.json.return_value = []
        
        mock_put_response = Mock()
        mock_put_response.status_code = 201
        mock_put_response.json.return_value = {
            "content": {"sha": "new123"}
        }
        
        headers = {"Authorization": "token test"}
        
        # GET requests: file check, branch check, directory check
        with patch('workflows.requests.get', side_effect=[mock_file_response, mock_branch_response, mock_dir_response]):
            with patch('workflows.requests.put', return_value=mock_put_response):
                status_code, new_sha = _update_workflow_to_github(
                    "owner", "repo", workflow, "TEST", "actions-manager/test-main", headers, "owner/repo"
                )
                
                assert status_code == 201
                assert new_sha == "new123"

    def test_update_workflow_to_github_update_existing(self):
        """Test updating an existing workflow in GitHub on AM branch."""
        workflow = {
            "name": "test-workflow",
            "content": "name: Test Updated\non: pull_request"
        }
        
        old_content = base64.b64encode(b"name: Test\non: push").decode()
        new_content = base64.b64encode(workflow["content"].encode()).decode()
        
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "sha": "old123",
            "content": old_content
        }
        
        mock_put_response = Mock()
        mock_put_response.status_code = 200
        mock_put_response.json.return_value = {
            "content": {"sha": "updated456"}
        }
        
        headers = {"Authorization": "token test"}
        
        with patch('workflows.requests.get', return_value=mock_get_response):
            with patch('workflows.requests.put', return_value=mock_put_response):
                status_code, new_sha = _update_workflow_to_github(
                    "owner", "repo", workflow, "TEST", "actions-manager/test-main", headers, "owner/repo"
                )
                
                assert status_code == 200
                assert new_sha == "updated456"

    def test_update_workflow_to_github_no_change(self):
        """Test updating workflow when content hasn't changed on AM branch."""
        workflow = {
            "name": "test-workflow",
            "content": "name: Test\non: push"
        }
        
        encoded_content = base64.b64encode(workflow["content"].encode()).decode()
        
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "sha": "same123",
            "content": encoded_content
        }
        
        headers = {"Authorization": "token test"}
        
        with patch('workflows.requests.get', return_value=mock_get_response):
            status_code, new_sha = _update_workflow_to_github(
                "owner", "repo", workflow, "TEST", "actions-manager/test-main", headers, "owner/repo"
            )
            
            # Should return 204 (No Content) for unchanged
            assert status_code == 204
            assert new_sha == "same123"

    @pytest.mark.skip(reason="Function no longer supports multiple branches - use _process_regular_workflows_update instead")
    def test_update_workflow_to_github_multiple_branches(self):
        """Test updating workflow to multiple branches - DEPRECATED."""
        workflow = {
            "name": "test-workflow",
            "content": "name: Test\non: push"
        }
        
        # Mock for file checks (doesn't exist)
        mock_file_response = Mock()
        mock_file_response.status_code = 404
        
        # Mock for branch checks (exist)
        mock_branch_response = Mock()
        mock_branch_response.status_code = 200
        
        # Mock for directory checks (already exists)
        mock_dir_response = Mock()
        mock_dir_response.status_code = 200
        mock_dir_response.json.return_value = []
        
        mock_put_response = Mock()
        mock_put_response.status_code = 201
        mock_put_response.json.return_value = {
            "content": {"sha": "new123"}
        }
        
        headers = {"Authorization": "token test"}
        
        # For 3 branches: file check + branch check + dir check for each = 9 GET requests
        with patch('workflows.requests.get', side_effect=[
            mock_file_response, mock_branch_response, mock_dir_response,  # main
            mock_file_response, mock_branch_response, mock_dir_response,  # develop
            mock_file_response, mock_branch_response, mock_dir_response   # staging
        ]):
            with patch('workflows.requests.put', return_value=mock_put_response):
                results, new_sha = _update_workflow_to_github(
                    "owner", "repo", workflow, "TEST", 
                    ["main", "develop", "staging"], 
                    headers, "owner/repo"
                )
                
                assert len(results) == 3
                assert results["owner/repo/test-workflow on main"] == 201
                assert results["owner/repo/test-workflow on develop"] == 201
                assert results["owner/repo/test-workflow on staging"] == 201

    def test_update_workflow_git_hash_success(self):
        """Test updating workflow git hash in database."""
        db = TestingSessionLocal()
        try:
            # Create a workflow
            workflow = Workflow(
                workflow_name="test.yml",
                workflow_yaml="name: Test\non: push",
                reusable_workflow=False
            )
            db.add(workflow)
            db.commit()
            
            # Update git hash
            _update_workflow_git_hash(db, "test.yml", "newhash789")
            
            # Verify update
            updated = db.query(Workflow).filter_by(workflow_name="test.yml").first()
            assert updated.workflow_git_hash == "newhash789"
        finally:
            db.close()

    def test_update_workflow_git_hash_workflow_not_found(self):
        """Test updating git hash for non-existent workflow."""
        db = TestingSessionLocal()
        try:
            # Should not raise error, just silently fail
            _update_workflow_git_hash(db, "nonexistent.yml", "hash123")
        finally:
            db.close()

    def test_update_workflow_git_hash_none_sha(self):
        """Test updating workflow git hash with None."""
        db = TestingSessionLocal()
        try:
            # Create a workflow
            workflow = Workflow(
                workflow_name="test.yml",
                workflow_yaml="name: Test\non: push",
                reusable_workflow=False,
                workflow_git_hash="oldhash"
            )
            db.add(workflow)
            db.commit()
            
            # Try to update with None (should skip)
            _update_workflow_git_hash(db, "test.yml", None)
            
            # Verify not updated
            updated = db.query(Workflow).filter_by(workflow_name="test.yml").first()
            assert updated.workflow_git_hash == "oldhash"
        finally:
            db.close()

    def test_get_workflow_from_github_with_custom_branch(self):
        """Test fetching workflow from GitHub with non-default branch."""
        mock_repo_response = Mock()
        mock_repo_response.status_code = 200
        mock_repo_response.json.return_value = {
            "default_branch": "develop"
        }
        
        mock_file_response = Mock()
        mock_file_response.status_code = 200
        mock_file_response.json.return_value = {
            "content": base64.b64encode(b"name: Test\non: push").decode(),
            "sha": "def456"
        }
        
        with patch('workflows.requests.get') as mock_get:
            mock_get.side_effect = [mock_repo_response, mock_file_response]
            
            result = get_workflow_from_github("owner", "repo", "test.yml", "token123")
            
            # Verify it attempted to use the develop branch
            assert result is not None
            assert result["sha"] == "def456"

    def test_ensure_workflows_directory_exists_already_exists(self):
        """Test _ensure_workflows_directory_exists when directory already exists."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []  # Empty directory
        
        with patch('workflows.requests.get') as mock_get:
            mock_get.return_value = mock_response
            
            result = _ensure_workflows_directory_exists(
                "owner", "repo", "main", {"Authorization": "token abc"}
            )
            
            assert result is True
            # Verify it checked for the directory
            mock_get.assert_called_once()
            assert ".github/workflows" in mock_get.call_args[0][0]

    def test_ensure_workflows_directory_exists_creates_directory(self):
        """Test _ensure_workflows_directory_exists creates directory when missing."""
        mock_get_response = Mock()
        mock_get_response.status_code = 404  # Directory doesn't exist
        
        mock_put_response = Mock()
        mock_put_response.status_code = 201  # Successfully created
        mock_put_response.text = '{"content": {"sha": "abc123"}}'
        
        with patch('workflows.requests.get') as mock_get, \
             patch('workflows.requests.put') as mock_put:
            mock_get.return_value = mock_get_response
            mock_put.return_value = mock_put_response
            
            result = _ensure_workflows_directory_exists(
                "owner", "repo", "main", {"Authorization": "token abc"}
            )
            
            assert result is True
            # Verify it checked for the directory
            mock_get.assert_called_once()
            # Verify it created .gitkeep file
            mock_put.assert_called_once()
            assert ".github/workflows/.gitkeep" in mock_put.call_args[0][0]
            # Verify payload contains base64 encoded empty content
            payload = mock_put.call_args[1]['json']
            assert payload['content'] == base64.b64encode(b"").decode()
            assert payload['branch'] == "main"

    def test_ensure_workflows_directory_exists_creation_fails(self):
        """Test _ensure_workflows_directory_exists handles creation failure."""
        mock_get_response = Mock()
        mock_get_response.status_code = 404  # Directory doesn't exist
        
        mock_put_response = Mock()
        mock_put_response.status_code = 403  # Forbidden
        mock_put_response.text = '{"message": "Permission denied"}'
        
        with patch('workflows.requests.get') as mock_get, \
             patch('workflows.requests.put') as mock_put:
            mock_get.return_value = mock_get_response
            mock_put.return_value = mock_put_response
            
            result = _ensure_workflows_directory_exists(
                "owner", "repo", "main", {"Authorization": "token abc"}
            )
            
            assert result is False
            # Verify it tried to create the directory
            mock_put.assert_called_once()

    def test_ensure_workflows_directory_exists_with_user_db(self):
        """Test _ensure_workflows_directory_exists with user and db parameters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        
        mock_db = Mock()
        
        with patch('workflows.github_get') as mock_github_get:
            mock_github_get.return_value = mock_response
            
            result = _ensure_workflows_directory_exists(
                "owner", "repo", "main", 
                {"Authorization": "token abc"},
                user="testuser",
                db=mock_db
            )
            
            assert result is True
            # Verify it used github_get instead of requests.get
            mock_github_get.assert_called_once()
            assert mock_github_get.call_args[0][1] == "testuser"
            assert mock_github_get.call_args[0][2] == mock_db

    def test_get_all_workflow_shas_success(self):
        """Test successfully fetching all workflow SHAs using Git Trees API."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tree": [
                {"path": "workflow1.yml", "sha": "abc123", "type": "blob"},
                {"path": "workflow2.yml", "sha": "def456", "type": "blob"},
                {"path": "workflow3.yml", "sha": "ghi789", "type": "blob"},
                {"path": "subdir", "sha": "xyz000", "type": "tree"}  # Should be filtered out
            ]
        }
        
        with patch('workflows.requests.get') as mock_get:
            mock_get.return_value = mock_response
            
            result = get_all_workflow_shas("owner", "repo", "main", "token123")
            
            # Verify correct API URL was called
            expected_url = f"{GITHUB_API_URL}/repos/owner/repo/git/trees/main:.github/workflows"
            mock_get.assert_called_once()
            assert mock_get.call_args[0][0] == expected_url
            
            # Verify result only contains blobs
            assert len(result) == 3
            assert result == {
                "workflow1.yml": "abc123",
                "workflow2.yml": "def456",
                "workflow3.yml": "ghi789"
            }

    def test_get_all_workflow_shas_not_found(self):
        """Test handling when .github/workflows directory doesn't exist."""
        mock_response = Mock()
        mock_response.status_code = 404
        
        with patch('workflows.requests.get') as mock_get:
            mock_get.return_value = mock_response
            
            result = get_all_workflow_shas("owner", "repo", "main", "token123")
            
            # Should return empty dict when directory doesn't exist
            assert result == {}

    def test_get_all_workflow_shas_api_error(self):
        """Test handling GitHub API errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        
        with patch('workflows.requests.get') as mock_get:
            mock_get.return_value = mock_response
            
            result = get_all_workflow_shas("owner", "repo", "main", "token123")
            
            # Should return empty dict on API errors
            assert result == {}

    def test_get_all_workflow_shas_empty_tree(self):
        """Test handling when .github/workflows directory is empty."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tree": []
        }
        
        with patch('workflows.requests.get') as mock_get:
            mock_get.return_value = mock_response
            
            result = get_all_workflow_shas("owner", "repo", "main", "token123")
            
            # Should return empty dict when no workflows exist
            assert result == {}

    def test_get_all_workflow_shas_only_subdirs(self):
        """Test handling when .github/workflows only contains subdirectories."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tree": [
                {"path": "subdir1", "sha": "abc123", "type": "tree"},
                {"path": "subdir2", "sha": "def456", "type": "tree"}
            ]
        }
        
        with patch('workflows.requests.get') as mock_get:
            mock_get.return_value = mock_response
            
            result = get_all_workflow_shas("owner", "repo", "main", "token123")
            
            # Should return empty dict when only directories exist
            assert result == {}
