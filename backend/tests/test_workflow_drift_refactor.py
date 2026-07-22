"""
Test that the refactored detect_workflow_drift function still works correctly.
This test verifies that the cognitive complexity reduction didn't break functionality.
"""
import pytest
from unittest.mock import MagicMock, patch
from workflows import (
    detect_workflow_drift, 
    _validate_user_and_get_project,
    _get_project_workflows,
    _compare_workflow_content,
    _process_regular_workflows,
    _process_reusable_workflows,
    _handle_deployment_variables,
    _create_drift_status
)
from models import Account, Project, Workflow, ProjectWorkflow
from fastapi import HTTPException


class TestWorkflowDriftRefactor:
    """Test the refactored drift detection functions."""
    
    def test_create_drift_status(self):
        """Test the helper function to create drift status objects."""
        drift_status = _create_drift_status(
            workflow_name="test-workflow",
            has_drift=True,
            github_content="github content",
            local_content="local content",
            github_sha="abc123",
            local_sha="def456",
            message="Test message",
            drift_type="workflow"
        )
        
        assert drift_status.workflow_name == "test-workflow"
        assert drift_status.has_drift == True
        assert drift_status.github_content == "github content"
        assert drift_status.local_content == "local content"
        assert drift_status.github_sha == "abc123"
        assert drift_status.local_sha == "def456"
        assert drift_status.message == "Test message"
        assert drift_status.drift_type == "workflow"
    
    @patch('workflows.user_tokens', {'test_user': 'test_token'})
    @patch('workflows._find_project_by_name')
    def test_validate_user_and_get_project_success(self, mock_find_project):
        """Test successful user validation and project retrieval."""
        # Create mock database session
        mock_db = MagicMock()
        
        # Mock project returned by _find_project_by_name
        mock_project = MagicMock()
        mock_project.project_code = "TEST"
        mock_find_project.return_value = mock_project
        
        token, project, project_code = _validate_user_and_get_project(
            mock_db, 'test_user', 'test_project'
        )
        
        assert token == 'test_token'
        assert project == mock_project
        assert project_code == 'TEST'
        mock_find_project.assert_called_once_with(mock_db, 'test_user', 'test_project')
    
    @patch('workflows.user_tokens', {})
    def test_validate_user_and_get_project_auth_failure(self):
        """Test authentication failure in user validation."""
        mock_db = MagicMock()
        
        with pytest.raises(HTTPException) as exc_info:
            _validate_user_and_get_project(mock_db, 'invalid_user', 'test_project')
        
        assert exc_info.value.status_code == 401
        assert "User not authenticated" in str(exc_info.value.detail)
    
    def test_get_project_workflows(self):
        """Test workflow retrieval and separation by type."""
        mock_db = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = 1
        
        # Create mock workflows
        regular_workflow = MagicMock()
        regular_workflow.reusable_workflow = False
        
        reusable_workflow = MagicMock()
        reusable_workflow.reusable_workflow = True
        
        mock_workflows = [regular_workflow, reusable_workflow]
        
        # Configure query mock
        mock_db.query.return_value.join.return_value.filter.return_value.all.return_value = mock_workflows
        
        regular, reusable = _get_project_workflows(mock_db, mock_project)
        
        assert len(regular) == 1
        assert len(reusable) == 1
        assert regular[0] == regular_workflow
        assert reusable[0] == reusable_workflow
    
    def test_handle_deployment_variables_disabled(self):
        """Test deployment variables handling when disabled."""
        result = _handle_deployment_variables(False)
        assert result == []
    
    def test_handle_deployment_variables_enabled(self):
        """Test deployment variables handling when enabled."""
        result = _handle_deployment_variables(True)
        assert len(result) == 1
        assert result[0].workflow_name == "deployment_variables"
        assert result[0].has_drift == True
        assert result[0].drift_type == "deployment_vars"
    
    @patch('workflows.get_workflow_from_github')
    @patch('workflows.verify_workflow_belongs_to_project')
    def test_compare_workflow_content_no_drift(self, mock_verify, mock_get_github):
        """Test content comparison when there's no drift."""
        # Set up mocks
        mock_verify.return_value = True
        github_data = {"content": "test content", "sha": "abc123"}
        mock_get_github.return_value = github_data
        
        # Create mock workflow
        mock_workflow = MagicMock()
        mock_workflow.workflow_name = "test-workflow"
        mock_workflow.workflow_yaml = "test content"
        mock_workflow.workflow_git_hash = "def456"
        
        # Test comparison
        result = _compare_workflow_content(
            mock_workflow, github_data, "test/repo", "TEST", "workflow"
        )
        
        assert result is not None
        assert result.workflow_name == "test-workflow"
        assert result.has_drift == False
        assert "synchronized" in result.message
    
    @patch('workflows.get_workflow_from_github')
    @patch('workflows.verify_workflow_belongs_to_project')
    def test_compare_workflow_content_with_drift(self, mock_verify, mock_get_github):
        """Test content comparison when there is drift."""
        # Set up mocks
        mock_verify.return_value = True
        github_data = {"content": "different content", "sha": "abc123"}
        mock_get_github.return_value = github_data
        
        # Create mock workflow
        mock_workflow = MagicMock()
        mock_workflow.workflow_name = "test-workflow"
        mock_workflow.workflow_yaml = "original content"
        mock_workflow.workflow_git_hash = "def456"
        
        # Test comparison
        result = _compare_workflow_content(
            mock_workflow, github_data, "test/repo", "TEST", "workflow"
        )
        
        assert result is not None
        assert result.workflow_name == "test-workflow"
        assert result.has_drift == True
        assert "differs" in result.message
    
    def test_compare_workflow_content_github_none(self):
        """Test content comparison when workflow doesn't exist on GitHub."""
        # Create mock workflow with git hash (previously synced)
        mock_workflow = MagicMock()
        mock_workflow.workflow_name = "test-workflow"
        mock_workflow.workflow_yaml = "test content"
        mock_workflow.workflow_git_hash = "def456"
        
        # Test comparison with None from GitHub
        result = _compare_workflow_content(
            mock_workflow, None, "test/repo", "TEST", "workflow"
        )
        
        assert result is not None
        assert result.workflow_name == "test-workflow"
        assert result.has_drift == True
        assert "deleted" in result.message
    
    def test_compare_workflow_content_github_none_no_hash(self):
        """Test content comparison when workflow was never synced."""
        # Create mock workflow without git hash (never synced)
        mock_workflow = MagicMock()
        mock_workflow.workflow_name = "test-workflow"
        mock_workflow.workflow_yaml = "test content"
        mock_workflow.workflow_git_hash = None
        
        # Test comparison with None from GitHub
        result = _compare_workflow_content(
            mock_workflow, None, "test/repo", "TEST", "workflow"
        )
        
        # Should return None as this is not drift, just not synced yet
        assert result is None
    
    @patch('workflows._validate_user_and_get_project')
    @patch('workflows._get_project_workflows')
    @patch('workflows._process_regular_workflows')
    @patch('workflows._process_reusable_workflows')
    @patch('workflows._handle_deployment_variables')
    def test_detect_workflow_drift_integration(self, mock_handle_vars, mock_process_reusable,
                                             mock_process_regular, mock_get_workflows,
                                             mock_validate):
        """Test the main detect_workflow_drift function integration."""
        # Set up mocks
        mock_validate.return_value = ("token", MagicMock(), "TEST")
        mock_get_workflows.return_value = ([], [])
        mock_process_regular.return_value = [_create_drift_status("regular", False, "", "", "", "", "No drift", "workflow")]
        mock_process_reusable.return_value = [_create_drift_status("reusable", True, "", "", "", "", "Has drift", "reusable_workflow")]
        mock_handle_vars.return_value = []
        
        # Call the main function
        result = detect_workflow_drift(
            MagicMock(), "test_user", "test_project", ["test/repo"], False
        )
        
        # Verify results
        assert len(result) == 2
        assert result[0].workflow_name == "regular"
        assert result[0].has_drift == False
        assert result[1].workflow_name == "reusable"
        assert result[1].has_drift == True
        
        # Verify all helper functions were called
        mock_validate.assert_called_once()
        mock_get_workflows.assert_called_once()
        mock_process_regular.assert_called_once()
        mock_process_reusable.assert_called_once()
        mock_handle_vars.assert_called_once_with(False)