"""
Tests for the project_deletion module to ensure refactoring maintains functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from project_deletion import (
    _get_project_and_user,
    _get_project_repositories,
    _get_project_workflows,
    _fetch_repository_secrets,
    _fetch_repository_variables,
    _fetch_environment_secrets,
    _fetch_environment_variables,
    _fetch_deployment_environments,
    _process_repository_resources,
    _validate_repository_access,
    _build_deletion_summary,
    _delete_project_workflows,
    _delete_workflow_file,
    _delete_github_resources_for_repository
)
from models import Account, Project, Repo, Workflow, ProjectRepo, ProjectWorkflow
from database import Base


def _make_empty_middleware_factory():
    """Return a DB factory backed by an empty in-memory SQLite database.

    The WriteProtectionMiddleware skips enforcement when the workspace_members
    table has zero rows, so pointing it at a fresh in-memory DB is sufficient to
    let test requests through without auth headers.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


class TestProjectDeletionHelpers:
    """Test class for project deletion helper functions."""

    def test_get_project_and_user_success(self):
        """Test successful user and project retrieval."""
        # Mock database session
        mock_db = Mock(spec=Session)
        
        # Mock user
        mock_user = Mock(spec=Account)
        mock_user.user_id = 1
        mock_user.github_user = "testuser"
        
        # Mock project
        mock_project = Mock(spec=Project)
        mock_project.project_id = 1
        mock_project.project_name = "Test Project"
        mock_project.user_id = 1
        
        # Configure database queries
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_project]
        
        # Test the function
        user, project = _get_project_and_user("Test Project", "testuser", mock_db)
        
        assert user == mock_user
        assert project == mock_project

    def test_get_project_and_user_user_not_found(self):
        """Test user not found scenario."""
        mock_db = Mock(spec=Session)
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            _get_project_and_user("Test Project", "nonexistent", mock_db)
        
        assert exc_info.value.status_code == 404
        assert "GitHub user not found" in str(exc_info.value.detail)

    def test_get_project_and_user_project_not_found(self):
        """Test project not found scenario."""
        mock_db = Mock(spec=Session)
        
        # Mock user exists but project doesn't
        mock_user = Mock(spec=Account)
        mock_user.user_id = 1
        
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_user, None]
        
        with pytest.raises(HTTPException) as exc_info:
            _get_project_and_user("Nonexistent Project", "testuser", mock_db)
        
        assert exc_info.value.status_code == 404
        assert "Project not found or access denied" in str(exc_info.value.detail)

    def test_get_project_repositories(self):
        """Test repository retrieval for a project."""
        mock_db = Mock(spec=Session)
        mock_project = Mock(spec=Project)
        mock_project.project_id = 1
        
        # Mock project repo associations
        mock_project_repo = Mock(spec=ProjectRepo)
        mock_project_repo.repo_id = 1
        
        # Mock repository names query
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_project_repo]
        mock_db.query.return_value.filter.return_value.scalar.return_value = "test-repo"
        
        repos = _get_project_repositories(mock_project, mock_db)
        
        assert repos == ["test-repo"]

    def test_get_project_workflows(self):
        """Test workflow categorization."""
        mock_db = Mock(spec=Session)
        mock_project = Mock(spec=Project)
        mock_project.project_id = 1
        
        # Mock workflows
        mock_regular_workflow = Mock(spec=Workflow)
        mock_regular_workflow.workflow_name = "Regular Workflow"
        mock_regular_workflow.reusable_workflow = False
        mock_regular_workflow.created_at = None
        mock_regular_workflow.updated_at = None
        
        mock_reusable_workflow = Mock(spec=Workflow)
        mock_reusable_workflow.workflow_name = "Reusable Workflow"
        mock_reusable_workflow.reusable_workflow = True
        mock_reusable_workflow.created_at = None
        mock_reusable_workflow.updated_at = None
        
        mock_db.query.return_value.join.return_value.filter.return_value.all.return_value = [
            mock_regular_workflow, mock_reusable_workflow
        ]
        
        workflows, reusable_workflows = _get_project_workflows(mock_project, mock_db)
        
        assert len(workflows) == 1
        assert len(reusable_workflows) == 1
        assert workflows[0]["name"] == "Regular Workflow"
        assert workflows[0]["is_reusable"] is False
        assert reusable_workflows[0]["name"] == "Reusable Workflow"
        assert reusable_workflows[0]["is_reusable"] is True

    @patch('project_deletion.requests.get')
    def test_validate_repository_access_success(self, mock_get):
        """Test successful repository access validation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        headers = {"Authorization": "token test-token"}
        result = _validate_repository_access("test/repo", headers)
        
        assert result is True

    @patch('project_deletion.requests.get')
    def test_validate_repository_access_failure(self, mock_get):
        """Test repository access validation failure."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        headers = {"Authorization": "token test-token"}
        result = _validate_repository_access("test/repo", headers)
        
        assert result is False

    @patch('project_deletion.requests.get')
    def test_fetch_repository_secrets(self, mock_get):
        """Test repository secrets fetching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "secrets": [
                {"name": "AM_TEST_SECRET1", "created_at": "2024-01-01", "updated_at": "2024-01-02"},
                {"name": "OTHER_SECRET", "created_at": "2024-01-01", "updated_at": "2024-01-02"}
            ]
        }
        mock_get.return_value = mock_response
        
        headers = {"Authorization": "token test-token"}
        secrets = _fetch_repository_secrets("test/repo", headers, "AM_TEST_")
        
        assert len(secrets) == 1
        assert secrets[0]["name"] == "AM_TEST_SECRET1"
        assert secrets[0]["repository"] == "test/repo"

    @patch('project_deletion.requests.get')
    def test_fetch_repository_variables(self, mock_get):
        """Test repository variables fetching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "variables": [
                {"name": "AM_TEST_VAR1", "value": "value1", "created_at": "2024-01-01", "updated_at": "2024-01-02"},
                {"name": "OTHER_VAR", "value": "value2", "created_at": "2024-01-01", "updated_at": "2024-01-02"}
            ]
        }
        mock_get.return_value = mock_response
        
        headers = {"Authorization": "token test-token"}
        variables = _fetch_repository_variables("test/repo", headers, "AM_TEST_")
        
        assert len(variables) == 1
        assert variables[0]["name"] == "AM_TEST_VAR1"
        assert variables[0]["repository"] == "test/repo"
        assert variables[0]["environment"] == "repository"

    @patch('project_deletion.requests.get')
    def test_fetch_deployment_environments(self, mock_get):
        """Test deployment environments fetching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "environments": [
                {"name": "production", "created_at": "2024-01-01", "updated_at": "2024-01-02"},
                {"name": "staging", "created_at": "2024-01-01", "updated_at": "2024-01-02"}
            ]
        }
        mock_get.return_value = mock_response
        
        headers = {"Authorization": "token test-token"}
        environments, _, _ = _fetch_deployment_environments("test/repo", headers)
        
        assert len(environments) == 2
        assert environments[0]["name"] == "production"
        assert environments[1]["name"] == "staging"

    def test_build_deletion_summary(self):
        """Test deletion summary construction."""
        mock_project = Mock(spec=Project)
        mock_project.project_name = "Test Project"
        mock_project.project_code = "TEST"
        
        workflows = [{"name": "workflow1", "is_reusable": False}]
        reusable_workflows = [{"name": "reusable1", "is_reusable": True}]
        secrets = [{"name": "AM_TEST_SECRET", "repository": "test/repo"}]
        env_vars = [{"name": "AM_TEST_VAR", "repository": "test/repo"}]
        environments = [{"name": "production", "repository": "test/repo"}]
        
        summary = _build_deletion_summary(
            mock_project, workflows, reusable_workflows, secrets, env_vars, environments
        )
        
        assert summary.project_name == "Test Project"
        assert summary.project_code == "TEST"
        assert len(summary.workflows) == 1
        assert len(summary.reusable_workflows) == 1
        assert len(summary.secrets) == 1
        assert len(summary.environment_variables) == 1
        assert len(summary.deployment_environments) == 1

    @patch('project_deletion._validate_repository_access')
    @patch('project_deletion._fetch_repository_secrets')
    @patch('project_deletion._fetch_repository_variables')
    @patch('project_deletion._fetch_deployment_environments')
    @patch('project_deletion._process_single_environment')
    def test_process_repository_resources(self, mock_process_env, mock_fetch_envs, 
                                         mock_fetch_vars, mock_fetch_secrets, mock_validate):
        """Test complete repository resource processing."""
        # Setup mocks
        mock_validate.return_value = True
        mock_fetch_secrets.return_value = [{"name": "AM_TEST_SECRET", "repository": "test/repo"}]
        mock_fetch_vars.return_value = [{"name": "AM_TEST_VAR", "repository": "test/repo"}]
        mock_fetch_envs.return_value = ([{"name": "production"}], [], [])
        mock_process_env.return_value = ([{"name": "AM_TEST_ENV_SECRET"}], [{"name": "AM_TEST_ENV_VAR"}])
        
        headers = {"Authorization": "token test-token"}
        secrets, variables, environments = _process_repository_resources("test/repo", headers, "AM_TEST_")
        
        assert len(secrets) == 2  # repo secret + env secret
        assert len(variables) == 2  # repo variable + env variable
        assert len(environments) == 1

    @patch('project_deletion._validate_repository_access')
    def test_process_repository_resources_access_denied(self, mock_validate):
        """Test repository resource processing when access is denied."""
        mock_validate.return_value = False
        
        headers = {"Authorization": "token test-token"}
        secrets, variables, environments = _process_repository_resources("test/repo", headers, "AM_TEST_")
        
        assert secrets == []
        assert variables == []
        assert environments == []


class TestDeleteProjectWorkflows:
    """Tests for _delete_project_workflows to verify no-prefix workflow name matching."""

    @patch('project_deletion.requests.get')
    @patch('project_deletion.requests.delete')
    def test_no_prefix_workflow_name_without_yml_extension_is_deleted(self, mock_delete, mock_get):
        """
        Regression test: workflow names stored without .yml extension in the database
        must still match the .yml filename returned by the GitHub API.
        """
        # GitHub API response listing workflows in the repo
        github_workflow_list_response = Mock()
        github_workflow_list_response.status_code = 200
        github_workflow_list_response.json.return_value = {
            "workflows": [
                {
                    "name": "Build and Test",
                    "path": ".github/workflows/build.yml"
                }
            ]
        }

        # GitHub API response for the file content (needed to get SHA before deleting)
        github_file_response = Mock()
        github_file_response.status_code = 200
        github_file_response.json.return_value = {"sha": "abc123"}

        mock_get.side_effect = [github_workflow_list_response, github_file_response]

        # Successful delete response
        delete_response = Mock()
        delete_response.status_code = 200
        mock_delete.return_value = delete_response

        # Mock database: no-prefix project with workflow stored as "build" (no .yml)
        mock_db = Mock(spec=Session)
        mock_project = Mock(spec=Project)
        mock_project.project_id = 1
        mock_project.use_prefix = False

        # New join query returns (workflow_name,) tuples directly
        mock_db.query.return_value.join.return_value.filter.return_value.all.return_value = [("build",)]

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        _delete_project_workflows("owner/repo", headers, "", deletion_results, mock_project, mock_db)

        # The workflow file should have been deleted
        assert len(deletion_results["github_resources_deleted"]) == 1
        assert "build.yml" in deletion_results["github_resources_deleted"][0]
        assert len(deletion_results["errors"]) == 0

    @patch('project_deletion.requests.get')
    @patch('project_deletion.requests.delete')
    def test_no_prefix_workflow_name_with_yml_extension_is_deleted(self, mock_delete, mock_get):
        """
        Workflow names already stored with .yml extension in the database
        must also match correctly.
        """
        github_workflow_list_response = Mock()
        github_workflow_list_response.status_code = 200
        github_workflow_list_response.json.return_value = {
            "workflows": [
                {
                    "name": "Deploy",
                    "path": ".github/workflows/deploy.yml"
                }
            ]
        }

        github_file_response = Mock()
        github_file_response.status_code = 200
        github_file_response.json.return_value = {"sha": "def456"}

        mock_get.side_effect = [github_workflow_list_response, github_file_response]

        delete_response = Mock()
        delete_response.status_code = 200
        mock_delete.return_value = delete_response

        mock_db = Mock(spec=Session)
        mock_project = Mock(spec=Project)
        mock_project.project_id = 1
        mock_project.use_prefix = False

        # New join query returns (workflow_name,) tuples directly
        mock_db.query.return_value.join.return_value.filter.return_value.all.return_value = [("deploy.yml",)]

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        _delete_project_workflows("owner/repo", headers, "", deletion_results, mock_project, mock_db)

        assert len(deletion_results["github_resources_deleted"]) == 1
        assert "deploy.yml" in deletion_results["github_resources_deleted"][0]
        assert len(deletion_results["errors"]) == 0

    @patch('project_deletion.requests.get')
    @patch('project_deletion.requests.delete')
    def test_no_prefix_untracked_workflow_is_not_deleted(self, mock_delete, mock_get):
        """Workflows not tracked in the database for a no-prefix project must not be deleted."""
        github_workflow_list_response = Mock()
        github_workflow_list_response.status_code = 200
        github_workflow_list_response.json.return_value = {
            "workflows": [
                {
                    "name": "Other CI",
                    "path": ".github/workflows/other-ci.yml"
                }
            ]
        }

        mock_get.return_value = github_workflow_list_response

        mock_db = Mock(spec=Session)
        mock_project = Mock(spec=Project)
        mock_project.project_id = 1
        mock_project.use_prefix = False

        # New join query returns (workflow_name,) tuples directly; "build" != "other-ci"
        mock_db.query.return_value.join.return_value.filter.return_value.all.return_value = [("build",)]

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        _delete_project_workflows("owner/repo", headers, "", deletion_results, mock_project, mock_db)

        # Should not delete untracked workflow
        assert len(deletion_results["github_resources_deleted"]) == 0
        mock_delete.assert_not_called()


class TestDeleteDeploymentEnvironmentsOptOut:
    """Tests for the delete_deployment_environments opt-out (issue #487)."""

    @patch('project_deletion.requests.get')
    @patch('project_deletion.requests.delete')
    def test_default_true_deletes_environments(self, mock_delete, mock_get):
        """Flag omitted/True: default behavior is unchanged, environments are still deleted."""
        def get_side_effect(url, headers=None):
            resp = Mock()
            if url.endswith("/environments"):
                resp.status_code = 200
                resp.json.return_value = {"environments": [{"name": "production"}, {"name": "staging"}]}
            else:
                resp.status_code = 404
            return resp
        mock_get.side_effect = get_side_effect
        mock_delete.return_value = Mock(status_code=204)

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        _delete_github_resources_for_repository("owner/repo", headers, "", deletion_results, None, None, True)

        deleted_envs = [d for d in deletion_results["github_resources_deleted"] if d.startswith("Deployment Environment:")]
        assert len(deleted_envs) == 2

    @patch('project_deletion.requests.get')
    @patch('project_deletion.requests.delete')
    def test_flag_false_preserves_environments(self, mock_delete, mock_get):
        """delete_deployment_environments=False: environments must be preserved, not deleted."""
        def get_side_effect(url, headers=None):
            resp = Mock()
            if url.endswith("/environments"):
                resp.status_code = 200
                resp.json.return_value = {"environments": [{"name": "production"}, {"name": "staging"}]}
            else:
                resp.status_code = 404
            return resp
        mock_get.side_effect = get_side_effect

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        _delete_github_resources_for_repository("owner/repo", headers, "", deletion_results, None, None, False)

        assert not any(d.startswith("Deployment Environment:") for d in deletion_results["github_resources_deleted"])
        mock_delete.assert_not_called()


class TestCascadeDeletion:
    """Tests for cascade deletion behavior during project deletion."""

    @patch('project_deletion.requests.get')
    @patch('project_deletion.requests.delete')
    def test_cascade_deletes_all_resource_types(self, mock_delete, mock_get):
        """Deleting a project cascades to workflows, secrets, variables, and environments."""
        def get_side_effect(url, headers=None):
            resp = Mock()
            if "/actions/workflows" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "workflows": [
                        {"name": "CI", "path": ".github/workflows/AM_TEST_ci.yml"}
                    ]
                }
            elif "/contents/" in url:
                resp.status_code = 200
                resp.json.return_value = {"sha": "abc123"}
            elif "/actions/secrets" in url and "/environments/" not in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "secrets": [{"name": "AM_TEST_SECRET", "created_at": "2024-01-01", "updated_at": "2024-01-01"}]
                }
            elif "/actions/variables" in url and "/environments/" not in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "variables": [{"name": "AM_TEST_VAR", "value": "v1", "created_at": "2024-01-01", "updated_at": "2024-01-01"}]
                }
            elif "/environments" in url and "/secrets" not in url and "/variables" not in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "environments": [{"name": "production"}]
                }
            elif "/environments/" in url and "/secrets" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "secrets": [{"name": "AM_TEST_ENV_SECRET", "created_at": "2024-01-01", "updated_at": "2024-01-01"}]
                }
            else:
                resp.status_code = 404
            return resp

        mock_get.side_effect = get_side_effect
        mock_delete.return_value = Mock(status_code=204)
        # Workflow file deletion returns 200
        mock_delete.side_effect = lambda url, headers=None, json=None: Mock(
            status_code=200 if "/contents/" in url else 204
        )

        mock_project = Mock(spec=Project)
        mock_project.project_id = 1
        mock_project.use_prefix = True

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        _delete_github_resources_for_repository(
            "owner/repo", headers, "AM_TEST_", deletion_results, mock_project, None, True
        )

        # Verify multiple resource types were deleted
        deleted = deletion_results["github_resources_deleted"]
        assert any("Workflow" in d for d in deleted)
        assert any("Repository Secret" in d for d in deleted)
        assert any("Repository Variable" in d for d in deleted)
        assert any("Deployment Environment" in d for d in deleted)
        assert len(deletion_results["errors"]) == 0

    @patch('project_deletion.requests.get')
    @patch('project_deletion.requests.delete')
    def test_cascade_across_multiple_repositories(self, mock_delete, mock_get):
        """_delete_all_github_resources processes all repositories in the list."""
        call_log = []

        def get_side_effect(url, headers=None):
            resp = Mock()
            if "/actions/workflows" in url:
                resp.status_code = 200
                resp.json.return_value = {"workflows": []}
            elif "/actions/secrets" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "secrets": [{"name": "AM_CODE_SECRET", "created_at": "2024-01-01", "updated_at": "2024-01-01"}]
                }
            elif "/actions/variables" in url:
                resp.status_code = 200
                resp.json.return_value = {"variables": []}
            elif "/environments" in url:
                resp.status_code = 200
                resp.json.return_value = {"environments": []}
            else:
                resp.status_code = 404
            return resp

        def delete_side_effect(url, headers=None, json=None):
            call_log.append(url)
            return Mock(status_code=204)

        mock_get.side_effect = get_side_effect
        mock_delete.side_effect = delete_side_effect

        mock_project = Mock(spec=Project)
        mock_project.use_prefix = True

        from project_deletion import _delete_all_github_resources

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        _delete_all_github_resources(
            ["owner/repo1", "owner/repo2", "owner/repo3"],
            headers, "CODE", deletion_results, mock_project, None, True
        )

        # Secrets from each repo should be deleted
        assert len(deletion_results["github_resources_deleted"]) == 3
        assert any("repo1" in d for d in deletion_results["github_resources_deleted"])
        assert any("repo2" in d for d in deletion_results["github_resources_deleted"])
        assert any("repo3" in d for d in deletion_results["github_resources_deleted"])

    def test_cascade_prefix_derived_from_project_code(self):
        """_delete_all_github_resources builds AM_{code}_ prefix when use_prefix=True."""
        from project_deletion import _delete_all_github_resources

        mock_project = Mock(spec=Project)
        mock_project.use_prefix = True

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        with patch('project_deletion._delete_github_resources_for_repository') as mock_del:
            _delete_all_github_resources(
                ["owner/repo"], headers, "MYCODE", deletion_results, mock_project, None, True
            )
            mock_del.assert_called_once_with(
                "owner/repo", headers, "AM_MYCODE_", deletion_results, mock_project, None, True
            )

    def test_cascade_no_prefix_when_use_prefix_false(self):
        """_delete_all_github_resources passes empty prefix when use_prefix=False."""
        from project_deletion import _delete_all_github_resources

        mock_project = Mock(spec=Project)
        mock_project.use_prefix = False

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        with patch('project_deletion._delete_github_resources_for_repository') as mock_del:
            _delete_all_github_resources(
                ["owner/repo"], headers, "MYCODE", deletion_results, mock_project, None, True
            )
            mock_del.assert_called_once_with(
                "owner/repo", headers, "", deletion_results, mock_project, None, True
            )


class TestOrphanedResourceCleanup:
    """Tests for orphaned resource cleanup after project deletion."""

    @patch('project_deletion.requests.get')
    def test_fetch_secrets_no_prefix_uses_database_tracking(self, mock_get):
        """No-prefix projects use DB-tracked secret names instead of prefix matching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "secrets": [
                {"name": "MY_SECRET", "created_at": "2024-01-01", "updated_at": "2024-01-01"},
                {"name": "OTHER_SECRET", "created_at": "2024-01-01", "updated_at": "2024-01-01"}
            ]
        }
        mock_get.return_value = mock_response

        mock_project = Mock(spec=Project)
        mock_project.project_id = 42
        mock_project.use_prefix = False

        mock_db = Mock(spec=Session)
        mock_secret = Mock()
        mock_secret.secret_name = "MY_SECRET"
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_secret]

        headers = {"Authorization": "token test-token"}
        secrets = _fetch_repository_secrets("test/repo", headers, "", mock_project, mock_db)

        assert len(secrets) == 1
        assert secrets[0]["name"] == "MY_SECRET"

    @patch('project_deletion.requests.get')
    def test_fetch_variables_no_prefix_uses_database_tracking(self, mock_get):
        """No-prefix projects use DB-tracked variable names instead of prefix matching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "variables": [
                {"name": "MY_VAR", "value": "v1", "created_at": "2024-01-01", "updated_at": "2024-01-01"},
                {"name": "UNTRACKED_VAR", "value": "v2", "created_at": "2024-01-01", "updated_at": "2024-01-01"}
            ]
        }
        mock_get.return_value = mock_response

        mock_project = Mock(spec=Project)
        mock_project.project_id = 42
        mock_project.use_prefix = False

        mock_db = Mock(spec=Session)
        mock_var = Mock()
        mock_var.env_var_name = "MY_VAR"
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_var]

        headers = {"Authorization": "token test-token"}
        variables = _fetch_repository_variables("test/repo", headers, "", mock_project, mock_db)

        assert len(variables) == 1
        assert variables[0]["name"] == "MY_VAR"

    @patch('project_deletion.requests.get')
    def test_empty_prefix_does_not_match_all_secrets(self, mock_get):
        """Empty prefix with use_prefix=True must not match all secrets."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "secrets": [
                {"name": "SECRET1", "created_at": "2024-01-01", "updated_at": "2024-01-01"},
                {"name": "SECRET2", "created_at": "2024-01-01", "updated_at": "2024-01-01"}
            ]
        }
        mock_get.return_value = mock_response

        # project with use_prefix=True but we pass empty prefix
        mock_project = Mock(spec=Project)
        mock_project.use_prefix = True

        headers = {"Authorization": "token test-token"}
        secrets = _fetch_repository_secrets("test/repo", headers, "", mock_project, None)

        # Should return nothing since empty prefix must not match everything
        assert len(secrets) == 0

    @patch('project_deletion.requests.get')
    def test_empty_prefix_does_not_match_all_variables(self, mock_get):
        """Empty prefix with use_prefix=True must not match all variables."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "variables": [
                {"name": "VAR1", "value": "v1", "created_at": "2024-01-01", "updated_at": "2024-01-01"},
                {"name": "VAR2", "value": "v2", "created_at": "2024-01-01", "updated_at": "2024-01-01"}
            ]
        }
        mock_get.return_value = mock_response

        mock_project = Mock(spec=Project)
        mock_project.use_prefix = True

        headers = {"Authorization": "token test-token"}
        variables = _fetch_repository_variables("test/repo", headers, "", mock_project, None)

        assert len(variables) == 0

    @patch('project_deletion.requests.get')
    @patch('project_deletion.requests.delete')
    def test_delete_secrets_no_prefix_only_tracked(self, mock_delete, mock_get):
        """Only secrets tracked in the database should be deleted for no-prefix projects."""
        from project_deletion import _delete_repository_secrets

        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "secrets": [
                {"name": "TRACKED_SECRET"},
                {"name": "UNTRACKED_SECRET"}
            ]
        }
        mock_get.return_value = mock_get_response
        mock_delete.return_value = Mock(status_code=204)

        mock_project = Mock(spec=Project)
        mock_project.project_id = 1
        mock_project.use_prefix = False

        mock_db = Mock(spec=Session)
        mock_secret = Mock()
        mock_secret.secret_name = "TRACKED_SECRET"
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_secret]

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        _delete_repository_secrets("owner/repo", headers, "", deletion_results, mock_project, mock_db)

        assert len(deletion_results["github_resources_deleted"]) == 1
        assert "TRACKED_SECRET" in deletion_results["github_resources_deleted"][0]


class TestPartialDeletionHandling:
    """Tests for partial deletion when some resources fail to delete."""

    @patch('project_deletion.requests.get')
    @patch('project_deletion.requests.delete')
    def test_partial_secret_deletion_failure(self, mock_delete, mock_get):
        """Some secrets fail to delete; errors are recorded but deletion continues."""
        from project_deletion import _delete_repository_secrets

        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "secrets": [
                {"name": "AM_TEST_SECRET1"},
                {"name": "AM_TEST_SECRET2"},
                {"name": "AM_TEST_SECRET3"}
            ]
        }
        mock_get.return_value = mock_get_response

        # First delete succeeds, second fails, third succeeds
        mock_delete.side_effect = [
            Mock(status_code=204),
            Mock(status_code=403),
            Mock(status_code=204),
        ]

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        _delete_repository_secrets("owner/repo", headers, "AM_TEST_", deletion_results)

        assert len(deletion_results["github_resources_deleted"]) == 2
        assert len(deletion_results["errors"]) == 1
        assert "AM_TEST_SECRET2" in deletion_results["errors"][0]

    @patch('project_deletion.requests.get')
    @patch('project_deletion.requests.delete')
    def test_partial_variable_deletion_failure(self, mock_delete, mock_get):
        """Some variables fail to delete; errors are recorded but deletion continues."""
        from project_deletion import _delete_repository_variables

        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "variables": [
                {"name": "AM_TEST_VAR1", "value": "v1"},
                {"name": "AM_TEST_VAR2", "value": "v2"}
            ]
        }
        mock_get.return_value = mock_get_response

        mock_delete.side_effect = [
            Mock(status_code=204),
            Mock(status_code=500),
        ]

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        _delete_repository_variables("owner/repo", headers, "AM_TEST_", deletion_results)

        assert len(deletion_results["github_resources_deleted"]) == 1
        assert len(deletion_results["errors"]) == 1
        assert "AM_TEST_VAR2" in deletion_results["errors"][0]

    @patch('project_deletion.requests.get')
    @patch('project_deletion.requests.delete')
    def test_partial_environment_deletion_failure(self, mock_delete, mock_get):
        """Some environments fail to delete; errors are recorded but deletion continues."""
        from project_deletion import _delete_deployment_environments

        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "environments": [
                {"name": "production"},
                {"name": "staging"},
                {"name": "dev"}
            ]
        }
        mock_get.return_value = mock_get_response

        mock_delete.side_effect = [
            Mock(status_code=204),
            Mock(status_code=422),
            Mock(status_code=204),
        ]

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        _delete_deployment_environments("owner/repo", headers, deletion_results)

        assert len(deletion_results["github_resources_deleted"]) == 2
        assert len(deletion_results["errors"]) == 1
        assert "staging" in deletion_results["errors"][0]

    @patch('project_deletion.requests.get')
    @patch('project_deletion.requests.delete')
    def test_workflow_file_sha_missing_records_error(self, mock_delete, mock_get):
        """Missing SHA in file metadata records error without crashing."""
        from project_deletion import _delete_workflow_file

        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {}  # No 'sha' key
        mock_get.return_value = mock_get_response

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        _delete_workflow_file("owner/repo", headers, "ci.yml", ".github/workflows/ci.yml", deletion_results)

        assert len(deletion_results["errors"]) == 1
        assert "Missing SHA" in deletion_results["errors"][0]
        mock_delete.assert_not_called()

    @patch('project_deletion.requests.get')
    @patch('project_deletion.requests.delete')
    def test_workflow_file_get_failure_records_error(self, mock_delete, mock_get):
        """HTTP error fetching workflow file metadata records error."""
        from project_deletion import _delete_workflow_file

        mock_get_response = Mock()
        mock_get_response.status_code = 404
        mock_get.return_value = mock_get_response

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        _delete_workflow_file("owner/repo", headers, "ci.yml", ".github/workflows/ci.yml", deletion_results)

        assert len(deletion_results["errors"]) == 1
        assert "HTTP 404" in deletion_results["errors"][0]
        mock_delete.assert_not_called()


class TestTransactionRollback:
    """Tests for transaction rollback behavior on errors."""

    @patch('project_deletion.cleanup_orphaned_workflows')
    @patch('project_deletion.user_tokens', {"testuser": "test-token"})
    def test_enhanced_delete_rolls_back_on_db_commit_failure(self, mock_cleanup):
        """If db.commit() fails, transaction is rolled back and 500 is raised."""
        from fastapi.testclient import TestClient
        from main import app

        mock_db = Mock(spec=Session)
        mock_user = Mock(spec=Account)
        mock_user.user_id = 1
        mock_user.github_user = "testuser"

        mock_project = Mock(spec=Project)
        mock_project.project_id = 1
        mock_project.project_name = "Test Project"
        mock_project.project_code = "TST"
        mock_project.user_id = 1
        mock_project.use_prefix = True

        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_project]
        mock_db.delete.return_value = None
        mock_db.commit.side_effect = Exception("Database write failure")
        mock_db.rollback.return_value = None
        mock_db.close.return_value = None

        from database import get_db

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        original_middleware_factory = app.state.middleware_db_factory
        app.state.middleware_db_factory = _make_empty_middleware_factory()
        try:
            client = TestClient(app)
            response = client.request(
                "DELETE",
                "/api/projects/Test%20Project/enhanced",
                json={
                    "github_user": "testuser",
                    "project_name": "Test Project",
                    "delete_github_resources": False,
                    "delete_deployment_environments": True
                }
            )

            assert response.status_code == 500
            assert "Error deleting project" in response.json()["detail"]
            mock_db.rollback.assert_called_once()
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.state.middleware_db_factory = original_middleware_factory

    @patch('project_deletion.cleanup_orphaned_workflows')
    @patch('project_deletion.user_tokens', {"testuser": "test-token"})
    def test_enhanced_delete_closes_db_on_success(self, mock_cleanup):
        """Database session is closed even on successful deletion."""
        from fastapi.testclient import TestClient
        from main import app

        mock_db = Mock(spec=Session)
        mock_user = Mock(spec=Account)
        mock_user.user_id = 1
        mock_user.github_user = "testuser"

        mock_project = Mock(spec=Project)
        mock_project.project_id = 1
        mock_project.project_name = "Test Project"
        mock_project.project_code = "TST"
        mock_project.user_id = 1
        mock_project.use_prefix = True

        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_project]
        mock_db.delete.return_value = None
        mock_db.commit.return_value = None
        mock_db.close.return_value = None

        from database import get_db

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        original_middleware_factory = app.state.middleware_db_factory
        app.state.middleware_db_factory = _make_empty_middleware_factory()
        try:
            client = TestClient(app)
            response = client.request(
                "DELETE",
                "/api/projects/Test%20Project/enhanced",
                json={
                    "github_user": "testuser",
                    "project_name": "Test Project",
                    "delete_github_resources": False,
                    "delete_deployment_environments": True
                }
            )

            assert response.status_code == 200
            mock_db.close.assert_called_once()
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.state.middleware_db_factory = original_middleware_factory

    @patch('project_deletion.cleanup_orphaned_workflows')
    @patch('project_deletion.user_tokens', {"testuser": "test-token"})
    def test_enhanced_delete_closes_db_on_failure(self, mock_cleanup):
        """Database session is closed even when deletion fails."""
        from fastapi.testclient import TestClient
        from main import app

        mock_db = Mock(spec=Session)
        mock_user = Mock(spec=Account)
        mock_user.user_id = 1
        mock_user.github_user = "testuser"

        mock_project = Mock(spec=Project)
        mock_project.project_id = 1
        mock_project.project_name = "Test Project"
        mock_project.project_code = "TST"
        mock_project.user_id = 1
        mock_project.use_prefix = True

        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_project]
        mock_db.delete.side_effect = Exception("Deletion failed")
        mock_db.rollback.return_value = None
        mock_db.close.return_value = None

        from database import get_db

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        original_middleware_factory = app.state.middleware_db_factory
        app.state.middleware_db_factory = _make_empty_middleware_factory()
        try:
            client = TestClient(app)
            response = client.request(
                "DELETE",
                "/api/projects/Test%20Project/enhanced",
                json={
                    "github_user": "testuser",
                    "project_name": "Test Project",
                    "delete_github_resources": False,
                    "delete_deployment_environments": True
                }
            )

            assert response.status_code == 500
            mock_db.close.assert_called_once()
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.state.middleware_db_factory = original_middleware_factory


class TestErrorRecovery:
    """Tests for error recovery during GitHub resource deletion."""

    @patch('project_deletion.requests.get')
    def test_github_api_network_error_handled_gracefully(self, mock_get):
        """Network errors fetching secrets are caught without crashing."""
        mock_get.side_effect = Exception("Connection refused")

        headers = {"Authorization": "token test-token"}
        secrets = _fetch_repository_secrets("test/repo", headers, "AM_TEST_")

        # Returns empty list instead of raising
        assert secrets == []

    @patch('project_deletion.requests.get')
    def test_github_api_network_error_variables(self, mock_get):
        """Network errors fetching variables are caught without crashing."""
        mock_get.side_effect = Exception("Timeout")

        headers = {"Authorization": "token test-token"}
        variables = _fetch_repository_variables("test/repo", headers, "AM_TEST_")

        assert variables == []

    @patch('project_deletion.requests.get')
    def test_github_api_network_error_environments(self, mock_get):
        """Network errors fetching environments are caught without crashing."""
        mock_get.side_effect = Exception("DNS resolution failed")

        headers = {"Authorization": "token test-token"}
        environments, secrets, variables = _fetch_deployment_environments("test/repo", headers)

        assert environments == []
        assert secrets == []
        assert variables == []

    @patch('project_deletion.requests.get')
    def test_validate_repository_access_network_error(self, mock_get):
        """Network errors during repository access validation return False."""
        mock_get.side_effect = Exception("Connection reset")

        headers = {"Authorization": "token test-token"}
        result = _validate_repository_access("test/repo", headers)

        assert result is False

    @patch('project_deletion.requests.get')
    def test_validate_repository_access_auth_failure(self, mock_get):
        """401 during repository access validation returns False."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        headers = {"Authorization": "token invalid-token"}
        result = _validate_repository_access("test/repo", headers)

        assert result is False

    @patch('project_deletion.requests.get')
    def test_validate_repository_access_forbidden(self, mock_get):
        """403 during repository access validation returns False."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response

        headers = {"Authorization": "token test-token"}
        result = _validate_repository_access("test/repo", headers)

        assert result is False

    @patch('project_deletion.requests.get')
    @patch('project_deletion.requests.delete')
    def test_error_in_one_repo_does_not_stop_other_repos(self, mock_delete, mock_get):
        """Errors processing one repository don't prevent processing other repos."""
        from project_deletion import _delete_all_github_resources

        call_count = {"get": 0}

        def get_side_effect(url, headers=None):
            call_count["get"] += 1
            resp = Mock()
            if "repo1" in url and "/actions/workflows" in url:
                raise Exception("repo1 network error")
            elif "/actions/workflows" in url:
                resp.status_code = 200
                resp.json.return_value = {"workflows": []}
            elif "/actions/secrets" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "secrets": [{"name": "AM_X_SECRET"}]
                }
            elif "/actions/variables" in url:
                resp.status_code = 200
                resp.json.return_value = {"variables": []}
            elif "/environments" in url:
                resp.status_code = 200
                resp.json.return_value = {"environments": []}
            else:
                resp.status_code = 404
            return resp

        mock_get.side_effect = get_side_effect
        mock_delete.return_value = Mock(status_code=204)

        mock_project = Mock(spec=Project)
        mock_project.use_prefix = True

        deletion_results = {"github_resources_deleted": [], "errors": []}
        headers = {"Authorization": "token test-token"}

        _delete_all_github_resources(
            ["owner/repo1", "owner/repo2"],
            headers, "X", deletion_results, mock_project, None, True
        )

        # repo1 should have an error, but repo2 should still be processed
        assert len(deletion_results["errors"]) >= 1
        assert any("repo1" in e for e in deletion_results["errors"])
        # repo2 should have processed successfully
        assert any("repo2" in d for d in deletion_results["github_resources_deleted"])

    @patch('project_deletion.requests.get')
    def test_environment_secrets_fetch_api_error_handled(self, mock_get):
        """Errors fetching environment secrets are handled gracefully."""
        mock_get.side_effect = Exception("API rate limited")

        headers = {"Authorization": "token test-token"}
        secrets = _fetch_environment_secrets("test/repo", "production", headers, "AM_TEST_")

        assert secrets == []

    @patch('project_deletion.requests.get')
    def test_environment_variables_fetch_api_error_handled(self, mock_get):
        """Errors fetching environment variables are handled gracefully."""
        mock_get.side_effect = Exception("API unavailable")

        headers = {"Authorization": "token test-token"}
        variables = _fetch_environment_variables("test/repo", "production", headers, "AM_TEST_")

        assert variables == []

    def test_get_project_and_user_strips_whitespace(self):
        """Whitespace in github_user is stripped before lookup."""
        mock_db = Mock(spec=Session)
        mock_user = Mock(spec=Account)
        mock_user.user_id = 1

        mock_project = Mock(spec=Project)
        mock_project.project_id = 1

        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_user, mock_project]

        user, project = _get_project_and_user("Test Project", "  testuser  ", mock_db)

        assert user == mock_user
        assert project == mock_project

    @patch('project_deletion.requests.get')
    def test_fetch_secrets_api_non_200_returns_empty(self, mock_get):
        """Non-200 response from secrets API returns empty list."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response

        headers = {"Authorization": "token test-token"}
        secrets = _fetch_repository_secrets("test/repo", headers, "AM_TEST_")

        assert secrets == []

    @patch('project_deletion.requests.get')
    def test_fetch_variables_api_non_200_returns_empty(self, mock_get):
        """Non-200 response from variables API returns empty list."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        headers = {"Authorization": "token test-token"}
        variables = _fetch_repository_variables("test/repo", headers, "AM_TEST_")

        assert variables == []