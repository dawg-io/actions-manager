"""
Tests for PR-based workflow updates with dedicated Actions Manager branches.
Tests the new flow: create unique AM branch -> commit workflows -> create/update PR.
"""
import pytest
import re
import sys
import os
from unittest.mock import MagicMock, patch, Mock, call
import base64

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from workflows import (
    _create_or_get_am_branch,
    _initialize_am_branch_in_empty_repo,
    _ensure_reusable_repo_exists,
    _get_reusable_workflow_repo,
    _check_existing_pr,
    _create_pull_request,
    _update_workflow_to_github,
    _process_regular_workflows_update,
    _process_reusable_workflows_update,
    GITHUB_API_URL
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_pr_updates.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _unprotected_branch():
    """GitHub's 404 for a branch with no protection configured.

    Campaign creation snapshots each target's protection rules right after it
    resolves the base commit, so every delivery flow makes this extra GET.
    """
    response = Mock()
    response.status_code = 404
    return response

class TestPRWorkflowUpdates:
    """Test class for PR-based workflow update functions."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Set up the test database before each test."""
        Base.metadata.create_all(bind=engine)
        yield
        Base.metadata.drop_all(bind=engine)

    def test_create_or_get_am_branch_new(self):
        """Test creating a new unique Actions Manager branch."""
        headers = {"Authorization": "token test123"}
        
        # Mock: Target branch exists
        mock_target_response = Mock()
        mock_target_response.status_code = 200
        mock_target_response.json.return_value = {
            "object": {"sha": "abc123def456"}
        }
        
        # Mock: Branch creation succeeds
        mock_create_response = Mock()
        mock_create_response.status_code = 201
        
        with patch('workflows.requests.get') as mock_get, \
             patch('workflows.requests.post') as mock_post:
            mock_get.side_effect = [mock_target_response]
            mock_post.return_value = mock_create_response
            
            am_branch, created, error = _create_or_get_am_branch(
                "owner", "repo", "main", "MYAPP", headers
            )
            
            # New format: actions-manager/<project_code>/<repo_slug>/<short_id>-<base_branch>
            assert re.match(r'^actions-manager/myapp/repo/[0-9a-f]{8}-main$', am_branch), \
                f"Branch '{am_branch}' does not match expected pattern"
            assert created is True
            assert error is None
            
            # Verify correct API calls: 1 GET (target branch), 1 POST (create branch)
            assert mock_get.call_count == 1
            assert mock_post.call_count == 1

    def test_create_or_get_am_branch_always_unique(self):
        """Test that every call generates a brand-new unique branch name."""
        headers = {"Authorization": "token test123"}

        mock_target_response = Mock()
        mock_target_response.status_code = 200
        mock_target_response.json.return_value = {"object": {"sha": "abc123def456"}}

        mock_create_response = Mock()
        mock_create_response.status_code = 201

        branches = []
        with patch('workflows.requests.get', return_value=mock_target_response), \
             patch('workflows.requests.post', return_value=mock_create_response):
            for _ in range(3):
                am_branch, created, error = _create_or_get_am_branch(
                    "owner", "repo", "main", "MYAPP", headers
                )
                assert created is True
                assert error is None
                branches.append(am_branch)

        # All branch names must be distinct
        assert len(set(branches)) == 3, "Branch names must be unique on every call"

    def test_create_or_get_am_branch_target_not_found(self):
        """Test error when target branch doesn't exist in a non-empty repo."""
        headers = {"Authorization": "token test123"}
        
        # Mock: Target branch doesn't exist (404)
        mock_target_response = Mock()
        mock_target_response.status_code = 404

        # Mock: Commits check — repo IS non-empty (has commits)
        mock_commits_response = Mock()
        mock_commits_response.status_code = 200
        mock_commits_response.json.return_value = [{"sha": "abc123"}]
        
        with patch('workflows.requests.get') as mock_get:
            mock_get.side_effect = [mock_target_response, mock_commits_response]
            
            am_branch, created, error = _create_or_get_am_branch(
                "owner", "repo", "nonexistent", "MYAPP", headers
            )
            
            assert am_branch is None
            assert created is False
            assert "does not exist in non-empty repository" in error

    def test_create_or_get_am_branch_empty_repo_initialized(self):
        """Test that an empty repository is initialized with both the target branch and AM branch."""
        headers = {"Authorization": "token test123"}

        # Mock: Target branch doesn't exist (empty repo — 404)
        mock_target_response = Mock()
        mock_target_response.status_code = 404

        # Mock: Commits check — GitHub returns 409 for repos with zero commits.
        # Since status != 200, the code correctly falls through to bootstrap.
        mock_commits_response = Mock()
        mock_commits_response.status_code = 409

        # Mock: Repository exists but is empty (Step 0 GET /repos/{owner}/{repo} returns 200)
        mock_repo_exists_response = Mock()
        mock_repo_exists_response.status_code = 200

        # Mock: Contents API (PUT) creates README.md successfully
        mock_contents_response = Mock()
        mock_contents_response.status_code = 201
        mock_contents_response.json.return_value = {"commit": {"sha": "commitsha789"}}

        # Mock: Target branch ref creation succeeds (Step 2)
        mock_target_ref_response = Mock()
        mock_target_ref_response.status_code = 201

        # Mock: AM branch ref creation succeeds (Step 3)
        mock_am_ref_response = Mock()
        mock_am_ref_response.status_code = 201

        with patch('workflows.requests.get') as mock_get, \
             patch('workflows.requests.post') as mock_post, \
             patch('workflows.requests.put') as mock_put:
            mock_get.side_effect = [
                mock_target_response,      # target branch check (404)
                mock_commits_response,     # commits check (empty)
                mock_repo_exists_response, # repo exists check
            ]
            mock_put.return_value = mock_contents_response
            mock_post.side_effect = [
                mock_target_ref_response,  # target branch (e.g. 'main') created first
                mock_am_ref_response,       # AM branch created second
            ]

            am_branch, created, error = _create_or_get_am_branch(
                "owner", "repo", "main", "MYAPP", headers
            )

            assert re.match(r'^actions-manager/myapp/repo/[0-9a-f]{8}-main$', am_branch), \
                f"Branch '{am_branch}' does not match expected pattern"
            assert created is True
            assert error is None
            # Verify the PUT call to Contents API
            assert mock_put.call_count == 1
            put_args, put_kwargs = mock_put.call_args
            assert "/contents/README.md" in put_args[0]
            # Verify the 2 POST calls: target branch ref, AM branch ref
            assert mock_post.call_count == 2
            _, target_ref_call_kwargs = mock_post.call_args_list[0]
            assert target_ref_call_kwargs["json"]["ref"] == "refs/heads/main"
            assert target_ref_call_kwargs["json"]["sha"] == "commitsha789"
            _, am_ref_call_kwargs = mock_post.call_args_list[1]
            assert am_ref_call_kwargs["json"]["ref"] == f"refs/heads/{am_branch}"
            assert am_ref_call_kwargs["json"]["sha"] == "commitsha789"

    def test_create_or_get_am_branch_missing_repo_created_and_initialized(self):
        """Test that a missing repository is auto-created before branch initialization."""
        headers = {"Authorization": "token test123"}

        # Mock: Target branch doesn't exist (repo missing)
        mock_target_response = Mock()
        mock_target_response.status_code = 404

        # Mock: Commits check — GitHub returns 409 for repos with zero commits.
        mock_commits_response = Mock()
        mock_commits_response.status_code = 409

        # Mock: Repository does not exist (Step 0 GET returns 404)
        mock_repo_missing_response = Mock()
        mock_repo_missing_response.status_code = 404

        # Mock: Repository creation succeeds (Step 0 POST /user/repos)
        mock_repo_create_response = Mock()
        mock_repo_create_response.status_code = 201

        # Mock: Contents API (PUT) creates README.md successfully
        mock_contents_response = Mock()
        mock_contents_response.status_code = 201
        mock_contents_response.json.return_value = {"commit": {"sha": "commitsha789"}}

        # Mock: Target branch ref creation succeeds
        mock_target_ref_response = Mock()
        mock_target_ref_response.status_code = 201

        # Mock: AM branch ref creation succeeds
        mock_am_ref_response = Mock()
        mock_am_ref_response.status_code = 201

        with patch('workflows.requests.get') as mock_get, \
             patch('workflows.requests.post') as mock_post, \
             patch('workflows.requests.put') as mock_put:
            mock_get.side_effect = [
                mock_target_response,        # target branch check (404)
                mock_commits_response,       # commits check (empty)
                mock_repo_missing_response,  # repo exists check
            ]
            mock_put.return_value = mock_contents_response
            mock_post.side_effect = [
                mock_repo_create_response,  # POST /user/repos to create the repo
                mock_target_ref_response,
                mock_am_ref_response,
            ]

            am_branch, created, error = _create_or_get_am_branch(
                "owner", "repo", "main", "MYAPP", headers
            )

            assert re.match(r'^actions-manager/myapp/repo/[0-9a-f]{8}-main$', am_branch), \
                f"Branch '{am_branch}' does not match expected pattern"
            assert created is True
            assert error is None
            # 3 POST calls in order:
            # 1) POST /user/repos       — create the repository
            # 2) POST …/git/refs        — create target branch ref (e.g. 'main')
            # 3) POST …/git/refs        — create AM branch ref
            assert mock_post.call_count == 3
            # Verify first POST is to create the repo at /user/repos
            first_post_args, first_post_kwargs = mock_post.call_args_list[0]
            assert first_post_args[0].endswith("/user/repos")
            assert first_post_kwargs["json"]["name"] == "repo"
            # Verify PUT was used for Contents API
            assert mock_put.call_count == 1

    def test_create_or_get_am_branch_readme_already_exists(self):
        """Test initialization when README.md already exists (Contents API returns 409)."""
        headers = {"Authorization": "token test123"}

        # Mock: Target branch doesn't exist (404)
        mock_target_response = Mock()
        mock_target_response.status_code = 404

        # Mock: Commits check — GitHub returns 409 for repos with zero commits.
        mock_commits_response = Mock()
        mock_commits_response.status_code = 409

        # Mock: Repository exists (Step 0)
        mock_repo_exists_response = Mock()
        mock_repo_exists_response.status_code = 200

        # Mock: Contents API returns 409 (file already exists)
        mock_contents_response = Mock()
        mock_contents_response.status_code = 409

        # Mock: Fallback GET to fetch target branch SHA succeeds
        mock_ref_response = Mock()
        mock_ref_response.status_code = 200
        mock_ref_response.json.return_value = {"object": {"sha": "existingsha123"}}

        # Mock: Target branch ref creation returns 422 (already exists)
        mock_target_ref_response = Mock()
        mock_target_ref_response.status_code = 422

        # Mock: AM branch ref creation succeeds
        mock_am_ref_response = Mock()
        mock_am_ref_response.status_code = 201

        with patch('workflows.requests.get') as mock_get, \
             patch('workflows.requests.post') as mock_post, \
             patch('workflows.requests.put') as mock_put:
            mock_get.side_effect = [
                mock_target_response,      # target branch check (404)
                mock_commits_response,     # commits check (empty)
                mock_repo_exists_response, # repo exists check
                mock_ref_response,         # fallback: get target branch SHA
            ]
            mock_put.return_value = mock_contents_response
            mock_post.side_effect = [
                mock_target_ref_response,
                mock_am_ref_response,
            ]

            am_branch, created, error = _create_or_get_am_branch(
                "owner", "repo", "main", "MYAPP", headers
            )

            assert re.match(r'^actions-manager/myapp/repo/[0-9a-f]{8}-main$', am_branch), \
                f"Branch '{am_branch}' does not match expected pattern"
            assert created is True
            assert error is None

    def test_create_or_get_am_branch_409_empty_repo(self):
        """Test that a 409 'Git Repository is empty' on the target branch triggers initialization."""
        headers = {"Authorization": "token test123"}

        # Mock: Target branch returns 409 (empty repo)
        mock_target_response = Mock()
        mock_target_response.status_code = 409

        # Mock: Repository exists (Step 0)
        mock_repo_exists_response = Mock()
        mock_repo_exists_response.status_code = 200

        # Mock: Contents API creates README.md successfully
        mock_contents_response = Mock()
        mock_contents_response.status_code = 201
        mock_contents_response.json.return_value = {"commit": {"sha": "commitsha789"}}

        # Mock: Target branch ref creation succeeds
        mock_target_ref_response = Mock()
        mock_target_ref_response.status_code = 201

        # Mock: AM branch ref creation succeeds
        mock_am_ref_response = Mock()
        mock_am_ref_response.status_code = 201

        with patch('workflows.requests.get') as mock_get, \
             patch('workflows.requests.post') as mock_post, \
             patch('workflows.requests.put') as mock_put:
            mock_get.side_effect = [mock_target_response, mock_repo_exists_response]
            mock_put.return_value = mock_contents_response
            mock_post.side_effect = [
                mock_target_ref_response,
                mock_am_ref_response,
            ]

            am_branch, created, error = _create_or_get_am_branch(
                "owner", "repo", "main", "MYAPP", headers
            )

            assert re.match(r'^actions-manager/myapp/repo/[0-9a-f]{8}-main$', am_branch), \
                f"Branch '{am_branch}' does not match expected pattern"
            assert created is True
            assert error is None

    def test_get_reusable_workflow_repo_rwx_project(self):
        """Test that _get_reusable_workflow_repo returns the RWX project's repo."""
        from models import Account, Project, Repo, ProjectRepo

        db = TestingSessionLocal()

        account = Account(github_user="testuser", github_email="test@test.com", account_type="professional")
        db.add(account)
        db.commit()
        db.refresh(account)

        project = Project(
            project_name="My RWX",
            user_id=account.user_id,
            project_code="MYRWX",
            project_type="rwx",
            branch_regex="",
            branch_option="default",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        repo = Repo(repo_name="testuser/my-rwx-workflow")
        db.add(repo)
        db.commit()
        db.refresh(repo)

        db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))
        db.commit()

        result = _get_reusable_workflow_repo(project, "testuser", db)
        assert result == "testuser/my-rwx-workflow"

        db.close()

    def test_get_reusable_workflow_repo_fallback(self):
        """Test that _get_reusable_workflow_repo falls back to am-reuseable-workflow when no DB data."""
        result = _get_reusable_workflow_repo(None, "testuser", None)
        assert result == "testuser/am-reuseable-workflow"

    def test_process_reusable_workflows_update_custom_repo(self):
        """Test that _process_reusable_workflows_update uses a custom repo when provided."""
        from models import Account

        db = TestingSessionLocal()

        test_account = Account(
            user_id=998,
            github_user="testuser",
            github_email="testuser@example.com",
            account_type="professional"
        )
        db.add(test_account)
        db.commit()

        headers = {"Authorization": "token test123"}

        rxworkflows = [{"name": "shared-build", "content": "name: Shared\non: workflow_call"}]

        # Mock: Branch resolution
        mock_repo_response = Mock()
        mock_repo_response.status_code = 200
        mock_repo_response.json.return_value = {"default_branch": "main"}

        # Mock: AM branch creation
        mock_am_check = Mock()
        mock_am_check.status_code = 404
        mock_target_ref = Mock()
        mock_target_ref.status_code = 200
        mock_target_ref.json.return_value = {"object": {"sha": "abc123"}}
        mock_create_branch = Mock()
        mock_create_branch.status_code = 201

        # Mock: File operations
        mock_file_check = Mock()
        mock_file_check.status_code = 404
        mock_branch_check = Mock()
        mock_branch_check.status_code = 200
        mock_dir_check = Mock()
        mock_dir_check.status_code = 200
        mock_put = Mock()
        mock_put.status_code = 201
        mock_put.json.return_value = {"content": {"sha": "newsha"}}

        # Mock: No existing PR
        mock_pr_check = Mock()
        mock_pr_check.status_code = 200
        mock_pr_check.json.return_value = []

        # Mock: PR creation
        mock_pr_create = Mock()
        mock_pr_create.status_code = 201
        mock_pr_create.json.return_value = {
            "number": 61,
            "html_url": "https://github.com/testuser/my-rwx-workflow/pull/61"
        }

        mock_user_tokens = {"testuser": "test_token_123"}

        with patch('workflows.github_get') as mock_github_get, \
             patch('workflows.github_put') as mock_github_put, \
             patch('workflows.requests.get') as mock_get, \
             patch('workflows.requests.post') as mock_post, \
             patch('auth.user_tokens', mock_user_tokens):
            mock_github_get.side_effect = [
                mock_repo_response,  # get_default_branch
                mock_target_ref,     # get target branch SHA
                _unprotected_branch(),  # branch protection snapshot
                mock_file_check,     # check workflow file
                mock_branch_check,   # verify branch exists
                mock_dir_check,      # check directory exists
                mock_pr_check        # check existing PR
            ]
            mock_github_put.return_value = mock_put
            mock_post.side_effect = [mock_create_branch, mock_pr_create]

            results = _process_reusable_workflows_update(
                rxworkflows, "testuser", "MYAPP", False, "", headers, db,
                reusable_repo="testuser/my-rwx-workflow"
            )

            # The results key should use the custom repo name, not the hardcoded one
            assert "testuser/my-rwx-workflow on main" in results
            result = results["testuser/my-rwx-workflow on main"]
            assert result["status"] == "pr_created"
            assert result["pr_number"] == 61

        db.close()

    def test_check_existing_pr_found(self):
        """Test finding an existing open PR."""
        headers = {"Authorization": "token test123"}
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "number": 42,
                "html_url": "https://github.com/owner/repo/pull/42",
                "title": "[Actions Manager] Update MYAPP workflows"
            }
        ]
        
        with patch('workflows.requests.get') as mock_get:
            mock_get.return_value = mock_response
            
            pr = _check_existing_pr(
                "owner", "repo", "actions-manager/myapp-main", 
                "main", headers
            )
            
            assert pr is not None
            assert pr["number"] == 42
            assert pr["html_url"] == "https://github.com/owner/repo/pull/42"

    def test_check_existing_pr_not_found(self):
        """Test when no existing PR is found."""
        headers = {"Authorization": "token test123"}
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        
        with patch('workflows.requests.get') as mock_get:
            mock_get.return_value = mock_response
            
            pr = _check_existing_pr(
                "owner", "repo", "actions-manager/myapp-main",
                "main", headers
            )
            
            assert pr is None

    def test_create_pull_request_success(self):
        """Test creating a new PR."""
        headers = {"Authorization": "token test123"}
        
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 43,
            "html_url": "https://github.com/owner/repo/pull/43",
            "title": "[Actions Manager] Update MYAPP workflows"
        }
        
        with patch('workflows.requests.post') as mock_post:
            mock_post.return_value = mock_response
            
            pr = _create_pull_request(
                "owner", "repo", "actions-manager/myapp-main",
                "main", "MYAPP", ["ci-build", "deploy"], headers
            )
            
            assert pr is not None
            assert pr["number"] == 43
            assert pr["html_url"] == "https://github.com/owner/repo/pull/43"

    def test_create_pull_request_failure(self):
        """Test PR creation failure."""
        headers = {"Authorization": "token test123"}
        
        mock_response = Mock()
        mock_response.status_code = 422
        mock_response.text = "Validation failed"
        
        with patch('workflows.requests.post') as mock_post:
            mock_post.return_value = mock_response
            
            pr = _create_pull_request(
                "owner", "repo", "actions-manager/myapp-main",
                "main", "MYAPP", ["ci-build"], headers
            )
            
            assert pr is None

    def test_update_workflow_to_github_new_file(self):
        """Test committing a new workflow file to AM branch."""
        headers = {"Authorization": "token test123"}
        workflow = {
            "name": "ci-build",
            "content": "name: CI\non: push"
        }
        
        # Mock: File doesn't exist yet (404)
        mock_file_check = Mock()
        mock_file_check.status_code = 404
        
        # Mock: Branch exists
        mock_branch_check = Mock()
        mock_branch_check.status_code = 200
        
        # Mock: Directory check succeeds
        mock_dir_check = Mock()
        mock_dir_check.status_code = 200
        
        # Mock: PUT succeeds
        mock_put_response = Mock()
        mock_put_response.status_code = 201
        mock_put_response.json.return_value = {
            "content": {"sha": "newsha123"}
        }
        
        with patch('workflows.requests.get') as mock_get, \
             patch('workflows.requests.put') as mock_put:
            mock_get.side_effect = [mock_file_check, mock_branch_check, mock_dir_check]
            mock_put.return_value = mock_put_response
            
            status, sha = _update_workflow_to_github(
                "owner", "repo", workflow, "MYAPP",
                "actions-manager/myapp-main", headers, "owner/repo"
            )
            
            assert status == 201
            assert sha == "newsha123"

    def test_update_workflow_to_github_unchanged(self):
        """Test skipping update when content hasn't changed."""
        headers = {"Authorization": "token test123"}
        workflow = {
            "name": "ci-build",
            "content": "name: CI\non: push"
        }
        
        encoded_content = base64.b64encode(b"name: CI\non: push").decode()
        
        # Mock: File exists with same content
        mock_file_check = Mock()
        mock_file_check.status_code = 200
        mock_file_check.json.return_value = {
            "sha": "existingsha",
            "content": encoded_content
        }
        
        with patch('workflows.requests.get') as mock_get:
            mock_get.return_value = mock_file_check
            
            status, sha = _update_workflow_to_github(
                "owner", "repo", workflow, "MYAPP",
                "actions-manager/myapp-main", headers, "owner/repo"
            )
            
            assert status == 204  # No Content
            assert sha == "existingsha"

    def test_update_workflow_to_github_empty_name(self):
        """Test error handling for empty workflow name."""
        headers = {"Authorization": "token test123"}
        workflow = {
            "name": "",
            "content": "name: CI\non: push"
        }
        
        status, sha = _update_workflow_to_github(
            "owner", "repo", workflow, "MYAPP",
            "actions-manager/myapp-main", headers, "owner/repo"
        )
        
        assert status == 400  # Bad Request
        assert sha is None

    def test_process_regular_workflows_update_pr_created(self):
        """Test full flow: create branch, commit workflows, create PR."""
        db = TestingSessionLocal()
        headers = {"Authorization": "token test123"}
        
        workflows = [
            {"name": "ci-build", "content": "name: CI\non: push"},
            {"name": "deploy", "content": "name: Deploy\non: push"}
        ]
        
        # Mock: Branch resolution returns main
        mock_repo_response = Mock()
        mock_repo_response.status_code = 200
        mock_repo_response.json.return_value = {"default_branch": "main"}
        
        # Mock: AM branch creation
        mock_am_check = Mock()
        mock_am_check.status_code = 404
        mock_target_ref = Mock()
        mock_target_ref.status_code = 200
        mock_target_ref.json.return_value = {"object": {"sha": "abc123"}}
        mock_create_branch = Mock()
        mock_create_branch.status_code = 201
        
        # Mock: File operations for both workflows
        mock_file_check = Mock()
        mock_file_check.status_code = 404
        mock_branch_check = Mock()
        mock_branch_check.status_code = 200
        mock_dir_check = Mock()
        mock_dir_check.status_code = 200
        mock_put = Mock()
        mock_put.status_code = 201
        mock_put.json.return_value = {"content": {"sha": "newsha"}}
        
        # Mock: No existing PR
        mock_pr_check = Mock()
        mock_pr_check.status_code = 200
        mock_pr_check.json.return_value = []
        
        # Mock: PR creation
        mock_pr_create = Mock()
        mock_pr_create.status_code = 201
        mock_pr_create.json.return_value = {
            "number": 50,
            "html_url": "https://github.com/owner/repo/pull/50"
        }
        
        with patch('workflows.requests.get') as mock_get, \
             patch('workflows.requests.put') as mock_put_req, \
             patch('workflows.requests.post') as mock_post:
            # Set up get calls sequence
            mock_get.side_effect = [
                mock_repo_response,  # get_default_branch
                mock_target_ref,     # get target branch SHA
                _unprotected_branch(),  # branch protection snapshot
                mock_file_check,     # check workflow 1 file
                mock_branch_check,   # verify branch exists
                mock_dir_check,      # check directory exists
                mock_file_check,     # check workflow 2 file
                mock_branch_check,   # verify branch exists
                mock_dir_check,      # check directory exists
                mock_pr_check        # check existing PR
            ]
            mock_put_req.return_value = mock_put
            mock_post.side_effect = [mock_create_branch, mock_pr_create]
            
            results = _process_regular_workflows_update(
                ["owner/repo"], workflows, "MYAPP", "default",
                False, "", headers, db
            )
            
            assert "owner/repo on main" in results
            result = results["owner/repo on main"]
            assert result["status"] == "pr_created"
            assert result["pr_number"] == 50
            assert "ci-build" in result["workflows_committed"]
            assert "deploy" in result["workflows_committed"]
            # branch_name should now be included in the result
            assert result.get("branch_name", "").startswith("actions-manager/")
        
        db.close()

    def test_process_regular_workflows_update_pr_updated(self):
        """Test flow when an existing open PR is found for the unique branch — should update it."""
        db = TestingSessionLocal()
        headers = {"Authorization": "token test123"}
        
        workflows = [{"name": "ci-build", "content": "name: CI\non: push"}]
        
        # Mock: Branch resolution
        mock_repo_response = Mock()
        mock_repo_response.status_code = 200
        mock_repo_response.json.return_value = {"default_branch": "main"}
        
        # Mock: Target branch SHA for new unique branch creation
        mock_target_ref = Mock()
        mock_target_ref.status_code = 200
        mock_target_ref.json.return_value = {"object": {"sha": "abc123"}}

        # Mock: Branch creation
        mock_create_branch = Mock()
        mock_create_branch.status_code = 201
        
        # Mock: File operations
        mock_file_check = Mock()
        mock_file_check.status_code = 404
        mock_branch_check = Mock()
        mock_branch_check.status_code = 200
        mock_dir_check = Mock()
        mock_dir_check.status_code = 200
        mock_put = Mock()
        mock_put.status_code = 201
        mock_put.json.return_value = {"content": {"sha": "newsha"}}
        
        # Mock: Existing PR found (simulating an unusual case where a PR already
        # exists from a freshly created branch — e.g. race condition)
        mock_pr_check = Mock()
        mock_pr_check.status_code = 200
        mock_pr_check.json.return_value = [
            {
                "number": 45,
                "html_url": "https://github.com/owner/repo/pull/45"
            }
        ]
        
        with patch('workflows.requests.get') as mock_get, \
             patch('workflows.requests.put') as mock_put_req, \
             patch('workflows.requests.post') as mock_post:
            mock_get.side_effect = [
                mock_repo_response,
                mock_target_ref,
                _unprotected_branch(),  # branch protection snapshot
                mock_file_check,
                mock_branch_check,
                mock_dir_check,
                mock_pr_check
            ]
            mock_put_req.return_value = mock_put
            mock_post.return_value = mock_create_branch
            
            results = _process_regular_workflows_update(
                ["owner/repo"], workflows, "MYAPP", "default",
                False, "", headers, db
            )
            
            assert "owner/repo on main" in results
            result = results["owner/repo on main"]
            assert result["status"] == "pr_updated"
            assert result["pr_number"] == 45
            assert "ci-build" in result["workflows_committed"]
            assert result.get("branch_name", "").startswith("actions-manager/")
        
        db.close()

    def test_process_reusable_workflows_update_pr_created(self):
        """Test reusable workflow update flow with PR creation."""
        from models import Account
        
        db = TestingSessionLocal()
        
        # Create test account to avoid rate limit issues
        test_account = Account(
            user_id=999,
            github_user="testuser",
            github_email="testuser@example.com",
            account_type="professional"
        )
        db.add(test_account)
        db.commit()
        
        headers = {"Authorization": "token test123"}
        
        rxworkflows = [{"name": "shared-build", "content": "name: Shared\non: workflow_call"}]
        
        # Mock: Branch resolution
        mock_repo_response = Mock()
        mock_repo_response.status_code = 200
        mock_repo_response.json.return_value = {"default_branch": "main"}
        
        # Mock: AM branch creation
        mock_am_check = Mock()
        mock_am_check.status_code = 404
        mock_target_ref = Mock()
        mock_target_ref.status_code = 200
        mock_target_ref.json.return_value = {"object": {"sha": "abc123"}}
        mock_create_branch = Mock()
        mock_create_branch.status_code = 201
        
        # Mock: File operations
        mock_file_check = Mock()
        mock_file_check.status_code = 404
        mock_branch_check = Mock()
        mock_branch_check.status_code = 200
        mock_dir_check = Mock()
        mock_dir_check.status_code = 200
        mock_put = Mock()
        mock_put.status_code = 201
        mock_put.json.return_value = {"content": {"sha": "newsha"}}
        
        # Mock: No existing PR
        mock_pr_check = Mock()
        mock_pr_check.status_code = 200
        mock_pr_check.json.return_value = []
        
        # Mock: PR creation
        mock_pr_create = Mock()
        mock_pr_create.status_code = 201
        mock_pr_create.json.return_value = {
            "number": 60,
            "html_url": "https://github.com/testuser/am-reuseable-workflow/pull/60"
        }
        
        # Mock user_tokens dictionary - this is what the function checks internally
        mock_user_tokens = {"testuser": "test_token_123"}
        
        with patch('workflows.github_get') as mock_github_get, \
             patch('workflows.github_put') as mock_github_put, \
             patch('workflows.requests.get') as mock_get, \
             patch('workflows.requests.post') as mock_post, \
             patch('auth.user_tokens', mock_user_tokens):
            # Setup github_get responses (when user/db is passed)
            mock_github_get.side_effect = [
                mock_repo_response,  # get_default_branch
                mock_target_ref,     # get target branch SHA
                _unprotected_branch(),  # branch protection snapshot
                mock_file_check,     # check workflow file
                mock_branch_check,   # verify branch exists
                mock_dir_check,      # check directory exists
                mock_pr_check        # check existing PR
            ]
            mock_github_put.return_value = mock_put
            mock_post.side_effect = [mock_create_branch, mock_pr_create]
            
            results = _process_reusable_workflows_update(
                rxworkflows, "testuser", "MYAPP", False, "", headers, db
            )
            
            assert "testuser/am-reuseable-workflow on main" in results
            result = results["testuser/am-reuseable-workflow on main"]
            assert result["status"] == "pr_created"
            assert result["pr_number"] == 60
            assert "shared-build" in result["workflows_committed"]
        
        db.close()

    def test_batch_multiple_workflows_single_pr(self):
        """Test that multiple workflows are batched into a single PR."""
        db = TestingSessionLocal()
        headers = {"Authorization": "token test123"}
        
        # Three workflows should all go to the same AM branch and PR
        workflows = [
            {"name": "build", "content": "name: Build\non: push"},
            {"name": "test", "content": "name: Test\non: push"},
            {"name": "deploy", "content": "name: Deploy\non: push"}
        ]
        
        # Mock responses for all operations
        mock_repo_response = Mock()
        mock_repo_response.status_code = 200
        mock_repo_response.json.return_value = {"default_branch": "main"}
        
        mock_am_check = Mock()
        mock_am_check.status_code = 404
        mock_target_ref = Mock()
        mock_target_ref.status_code = 200
        mock_target_ref.json.return_value = {"object": {"sha": "abc123"}}
        mock_create_branch = Mock()
        mock_create_branch.status_code = 201
        
        mock_file_check = Mock()
        mock_file_check.status_code = 404
        mock_branch_check = Mock()
        mock_branch_check.status_code = 200
        mock_dir_check = Mock()
        mock_dir_check.status_code = 200
        mock_put = Mock()
        mock_put.status_code = 201
        mock_put.json.return_value = {"content": {"sha": "newsha"}}
        
        mock_pr_check = Mock()
        mock_pr_check.status_code = 200
        mock_pr_check.json.return_value = []
        
        mock_pr_create = Mock()
        mock_pr_create.status_code = 201
        mock_pr_create.json.return_value = {
            "number": 100,
            "html_url": "https://github.com/owner/repo/pull/100"
        }
        
        with patch('workflows.requests.get') as mock_get, \
             patch('workflows.requests.put') as mock_put_req, \
             patch('workflows.requests.post') as mock_post:
            # Set up sequence for 3 workflows (no AM branch check — always creates unique)
            mock_get.side_effect = [
                mock_repo_response,
                mock_target_ref,
                _unprotected_branch(),  # branch protection snapshot
                # Workflow 1
                mock_file_check, mock_branch_check, mock_dir_check,
                # Workflow 2
                mock_file_check, mock_branch_check, mock_dir_check,
                # Workflow 3
                mock_file_check, mock_branch_check, mock_dir_check,
                # PR check
                mock_pr_check
            ]
            mock_put_req.return_value = mock_put
            mock_post.side_effect = [mock_create_branch, mock_pr_create]
            
            results = _process_regular_workflows_update(
                ["owner/repo"], workflows, "MYAPP", "default",
                False, "", headers, db
            )
            
            # Verify only ONE result entry (one PR)
            assert len(results) == 1
            assert "owner/repo on main" in results
            
            result = results["owner/repo on main"]
            assert result["status"] == "pr_created"
            assert result["pr_number"] == 100
            # All three workflows should be in the same PR
            assert len(result["workflows_committed"]) == 3
            assert "build" in result["workflows_committed"]
            assert "test" in result["workflows_committed"]
            assert "deploy" in result["workflows_committed"]
            
            # Verify only ONE PR was created (not 3)
            pr_create_calls = [call for call in mock_post.call_args_list 
                             if 'pulls' in str(call)]
            assert len(pr_create_calls) == 1
        
        db.close()
