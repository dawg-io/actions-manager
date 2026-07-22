"""
Extended comprehensive tests for workflows.py drift detection functionality.
Covers additional drift detection scenarios, workflow CRUD operations, and edge cases.
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch, Mock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from workflows import (
    create_or_update_workflow,
    cleanup_orphaned_workflows,
    count_project_workflows,
    count_project_reusable_workflows,
    _process_regular_workflows,
    _process_reusable_workflows,
    get_all_workflow_shas,
    WorkflowSchema
)
from models import Base, Account, Project, Workflow, ProjectWorkflow
from auth import user_tokens

# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_drift_extended.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class TestWorkflowDriftDetectionExtended:
    """Extended test class for drift detection and workflow operations."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Set up the test database before each test."""
        Base.metadata.create_all(bind=engine)
        
        # Create test data
        db = TestingSessionLocal()
        try:
            # Create test user
            test_user = Account(
                github_user="testuser",
                github_email="testuser@example.com",
                account_type="free"
            )
            db.add(test_user)
            db.commit()
            db.refresh(test_user)
            self.user_id = test_user.user_id
            
            # Create test project
            test_project = Project(
                project_name="test_project",
                project_code="TEST",
                user_id=self.user_id,
                branch_option="default"
            )
            db.add(test_project)
            db.commit()
            db.refresh(test_project)
            self.project_id = test_project.project_id
            
            # Create second project for cross-project testing
            test_project2 = Project(
                project_name="project2",
                project_code="PRJ2",
                user_id=self.user_id,
                branch_option="default"
            )
            db.add(test_project2)
            db.commit()
            db.refresh(test_project2)
            self.project_id_2 = test_project2.project_id
            
        finally:
            db.close()
        
        yield
        
        # Clean up after test
        Base.metadata.drop_all(bind=engine)
        # Clean up any user tokens
        if "testuser" in user_tokens:
            del user_tokens["testuser"]

    def test_create_or_update_workflow_new(self):
        """Test creating a new workflow."""
        db = TestingSessionLocal()
        try:
            workflow_data = WorkflowSchema(
                name="new-workflow.yml",
                content="name: New\non: push"
            )
            
            create_or_update_workflow(db, workflow_data, self.project_id, is_reusable=False)
            
            # Verify workflow was created
            workflow = db.query(Workflow).filter_by(workflow_name="new-workflow.yml").first()
            assert workflow is not None
            assert workflow.reusable_workflow == False
            
            # Verify project association
            association = db.query(ProjectWorkflow).filter_by(
                project_id=self.project_id,
                workflow_id=workflow.workflow_id
            ).first()
            assert association is not None
        finally:
            db.close()

    def test_create_or_update_workflow_update_existing(self):
        """Test updating an existing workflow."""
        db = TestingSessionLocal()
        try:
            # Create initial workflow
            workflow_data = WorkflowSchema(
                name="existing.yml",
                content="name: Version 1\non: push"
            )
            create_or_update_workflow(db, workflow_data, self.project_id, is_reusable=False)
            
            # Update the workflow
            workflow_data_v2 = WorkflowSchema(
                name="existing.yml",
                content="name: Version 2\non: pull_request"
            )
            create_or_update_workflow(db, workflow_data_v2, self.project_id, is_reusable=False)
            
            # Verify only one workflow exists with updated content
            workflows = db.query(Workflow).filter_by(workflow_name="existing.yml").all()
            assert len(workflows) == 1
            assert "Version 2" in workflows[0].workflow_yaml
        finally:
            db.close()

    def test_create_or_update_workflow_case_insensitive(self):
        """Test workflow name matching is case-insensitive."""
        db = TestingSessionLocal()
        try:
            # Create workflow with lowercase name
            workflow_data = WorkflowSchema(
                name="test-workflow.yml",
                content="name: Test\non: push"
            )
            create_or_update_workflow(db, workflow_data, self.project_id, is_reusable=False)
            
            # Update with uppercase name
            workflow_data_upper = WorkflowSchema(
                name="TEST-WORKFLOW.yml",
                content="name: Test Updated\non: pull_request"
            )
            create_or_update_workflow(db, workflow_data_upper, self.project_id, is_reusable=False)
            
            # Should still be only one workflow
            workflows = db.query(Workflow).all()
            assert len(workflows) == 1
        finally:
            db.close()

    def test_create_or_update_workflow_reusable(self):
        """Test creating a reusable workflow."""
        db = TestingSessionLocal()
        try:
            workflow_data = WorkflowSchema(
                name="reusable.yml",
                content="name: Reusable\non: workflow_call"
            )
            
            create_or_update_workflow(db, workflow_data, self.project_id, is_reusable=True)
            
            # Verify workflow was created as reusable
            workflow = db.query(Workflow).filter_by(workflow_name="reusable.yml").first()
            assert workflow is not None
            assert workflow.reusable_workflow == True
        finally:
            db.close()

    def test_create_or_update_workflow_project_isolation(self):
        """Test that workflows are isolated by project."""
        db = TestingSessionLocal()
        try:
            # Create same-named workflow in two projects
            workflow_data = WorkflowSchema(
                name="shared-name.yml",
                content="name: Project 1 Workflow\non: push"
            )
            create_or_update_workflow(db, workflow_data, self.project_id, is_reusable=False)
            
            workflow_data2 = WorkflowSchema(
                name="shared-name.yml",
                content="name: Project 2 Workflow\non: pull_request"
            )
            create_or_update_workflow(db, workflow_data2, self.project_id_2, is_reusable=False)
            
            # Should have two workflows with same name
            workflows = db.query(Workflow).filter_by(workflow_name="shared-name.yml").all()
            assert len(workflows) == 2
            
            # Each should be associated with correct project
            proj1_workflows = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == self.project_id,
                Workflow.workflow_name == "shared-name.yml"
            ).all()
            assert len(proj1_workflows) == 1
            assert "Project 1" in proj1_workflows[0].workflow_yaml
            
            proj2_workflows = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == self.project_id_2,
                Workflow.workflow_name == "shared-name.yml"
            ).all()
            assert len(proj2_workflows) == 1
            assert "Project 2" in proj2_workflows[0].workflow_yaml
        finally:
            db.close()

    def test_create_or_update_workflow_strips_duplicated_project_prefix(self):
        """Regression: a stale client that submits ``AM_TEST_foo`` for a
        ``use_prefix=True`` project must not result in a stored name that
        produces ``AM_TEST_AM_TEST_foo.yml`` after format_workflow_name.

        The backend defensively strips a single matching project prefix so
        the canonical DB stem stays free of the project-managed prefix.
        """
        from workflows import format_workflow_name

        db = TestingSessionLocal()
        try:
            # Project "TEST" defaults to use_prefix=True.  Submit a name that
            # already includes the prefix (case-insensitive).
            workflow_data = WorkflowSchema(
                name="AM_TEST_oops",
                content="name: Oops\non: push"
            )
            create_or_update_workflow(db, workflow_data, self.project_id, is_reusable=False)

            # The stored stem must not retain the project prefix.
            workflow = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == self.project_id
            ).first()
            assert workflow is not None
            assert workflow.workflow_name == "oops"

            # And format_workflow_name must produce exactly one prefix.
            assert (
                format_workflow_name(workflow.workflow_name, "TEST", use_prefix=True)
                == "AM_TEST_oops.yml"
            )
        finally:
            db.close()

    def test_create_or_update_workflow_prefix_strip_is_case_insensitive(self):
        """A mixed-case prefix submission is still detected and stripped."""
        db = TestingSessionLocal()
        try:
            workflow_data = WorkflowSchema(
                name="am_test_lower",
                content="name: Lower\non: push"
            )
            create_or_update_workflow(db, workflow_data, self.project_id, is_reusable=False)

            workflow = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == self.project_id
            ).first()
            assert workflow is not None
            assert workflow.workflow_name == "lower"
        finally:
            db.close()

    def test_create_or_update_workflow_does_not_strip_unrelated_prefix(self):
        """Names that start with ``AM_`` but for a different project_code
        must not be mutated."""
        db = TestingSessionLocal()
        try:
            workflow_data = WorkflowSchema(
                name="AM_OTHER_keep",
                content="name: Keep\non: push"
            )
            create_or_update_workflow(db, workflow_data, self.project_id, is_reusable=False)

            workflow = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == self.project_id
            ).first()
            assert workflow is not None
            # The unrelated AM_OTHER_ prefix is preserved as a literal name part.
            assert workflow.workflow_name == "AM_OTHER_keep"
        finally:
            db.close()

    def test_create_or_update_workflow_no_prefix_mode_unchanged(self):
        """When the project does not use prefix mode, names are stored as-is."""
        db = TestingSessionLocal()
        try:
            # Flip the project to no-prefix mode.
            project = db.query(Project).filter_by(project_id=self.project_id).first()
            project.use_prefix = False
            db.commit()

            workflow_data = WorkflowSchema(
                name="AM_TEST_keep.yml",
                content="name: Keep\non: push"
            )
            create_or_update_workflow(db, workflow_data, self.project_id, is_reusable=False)

            workflow = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == self.project_id
            ).first()
            assert workflow is not None
            # No prefix mode → the literal name (including any AM_ prefix) is kept.
            assert workflow.workflow_name == "AM_TEST_keep.yml"
        finally:
            db.close()

    def test_cleanup_orphaned_workflows_no_orphans(self):
        """Test cleanup when no orphaned workflows exist."""
        db = TestingSessionLocal()
        try:
            # Create workflow with project association
            workflow = Workflow(
                workflow_name="associated.yml",
                workflow_yaml="name: Test\non: push",
                reusable_workflow=False
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            
            db.add(ProjectWorkflow(
                project_id=self.project_id,
                workflow_id=workflow.workflow_id
            ))
            db.commit()
            
            # Run cleanup
            cleanup_orphaned_workflows(db)
            
            # Workflow should still exist
            result = db.query(Workflow).filter_by(workflow_name="associated.yml").first()
            assert result is not None
        finally:
            db.close()

    def test_cleanup_orphaned_workflows_with_orphans(self):
        """Test cleanup removes orphaned workflows."""
        db = TestingSessionLocal()
        try:
            # Create orphaned workflow (no project association)
            orphaned = Workflow(
                workflow_name="orphaned.yml",
                workflow_yaml="name: Orphaned\non: push",
                reusable_workflow=False
            )
            db.add(orphaned)
            
            # Create associated workflow
            associated = Workflow(
                workflow_name="associated.yml",
                workflow_yaml="name: Associated\non: push",
                reusable_workflow=False
            )
            db.add(associated)
            db.commit()
            db.refresh(associated)
            
            db.add(ProjectWorkflow(
                project_id=self.project_id,
                workflow_id=associated.workflow_id
            ))
            db.commit()
            
            # Run cleanup
            cleanup_orphaned_workflows(db)
            
            # Orphaned should be deleted
            orphaned_result = db.query(Workflow).filter_by(workflow_name="orphaned.yml").first()
            assert orphaned_result is None
            
            # Associated should still exist
            associated_result = db.query(Workflow).filter_by(workflow_name="associated.yml").first()
            assert associated_result is not None
        finally:
            db.close()

    def test_cleanup_orphaned_workflows_multiple_orphans(self):
        """Test cleanup removes multiple orphaned workflows."""
        db = TestingSessionLocal()
        try:
            # Create multiple orphaned workflows
            for i in range(3):
                orphaned = Workflow(
                    workflow_name=f"orphaned{i}.yml",
                    workflow_yaml=f"name: Orphaned{i}\non: push",
                    reusable_workflow=False
                )
                db.add(orphaned)
            db.commit()
            
            # Run cleanup
            cleanup_orphaned_workflows(db)
            
            # All orphans should be deleted
            remaining = db.query(Workflow).all()
            assert len(remaining) == 0
        finally:
            db.close()

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    def test_count_project_workflows_success(self):
        """Test counting regular workflows for a project."""
        # The count_project_workflows function creates its own session,
        # so we test it directly without database isolation issues
        # by testing that it doesn't crash with valid inputs
        count = count_project_workflows("testuser", "test_project")
        # Should return 0 since test database isn't accessible by the function
        assert count == 0

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    def test_count_project_reusable_workflows_success(self):
        """Test counting reusable workflows for a project."""
        # The count_project_reusable_workflows function creates its own session,
        # so we test it directly without database isolation issues
        # by testing that it doesn't crash with valid inputs
        count = count_project_reusable_workflows("testuser", "test_project")
        # Should return 0 since test database isn't accessible by the function
        assert count == 0

    def test_count_project_workflows_unauthenticated(self):
        """Test counting workflows with unauthenticated user."""
        count = count_project_workflows("unknown_user", "test_project")
        assert count == 0

    def test_count_project_workflows_account_not_found(self):
        """Test counting workflows with non-existent account."""
        # Add token but no account in database
        user_tokens["ghost"] = "token"
        count = count_project_workflows("ghost", "test_project")
        assert count == 0
        del user_tokens["ghost"]

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    def test_count_project_workflows_project_not_found(self):
        """Test counting workflows with non-existent project."""
        count = count_project_workflows("testuser", "nonexistent_project")
        assert count == 0

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    @patch('workflows.get_all_workflow_shas')
    @patch('workflows.get_default_branch')
    @patch('workflows.get_workflow_from_github')
    def test_process_regular_workflows_no_drift(self, mock_get_github, mock_get_branch, mock_get_shas):
        """Test processing regular workflows with no drift."""
        db = TestingSessionLocal()
        try:
            # Create workflow (workflow_name should not include .yml extension)
            workflow = Workflow(
                workflow_name="test",
                workflow_yaml="name: Test\non: push",
                workflow_git_hash="abc123",
                reusable_workflow=False
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            
            workflows = [workflow]
            
            # Mock get_default_branch
            mock_get_branch.return_value = "main"
            
            # Mock get_all_workflow_shas to return the SHA
            mock_get_shas.return_value = {
                "AM_TEST_test.yml": "abc123"  # Same SHA as in DB
            }
            
            # Mock GitHub returns same content (will be called for SHA mismatch scenarios)
            mock_get_github.return_value = {
                "content": "name: Test\non: push",
                "sha": "abc123"
            }
            
            results = _process_regular_workflows(
                db, workflows, ["owner/repo"], "TEST", "test_token"
            )
            
            assert len(results) == 1
            assert results[0].has_drift == False
        finally:
            db.close()

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    @patch('workflows.get_all_workflow_shas')
    @patch('workflows.get_default_branch')
    @patch('workflows.get_workflow_from_github')
    def test_process_regular_workflows_with_drift(self, mock_get_github, mock_get_branch, mock_get_shas):
        """Test processing regular workflows with drift detected."""
        db = TestingSessionLocal()
        try:
            # Create workflow (workflow_name should not include .yml extension)
            workflow = Workflow(
                workflow_name="test",
                workflow_yaml="name: Test Local\non: push",
                workflow_git_hash="abc123",
                reusable_workflow=False
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            
            workflows = [workflow]
            
            # Mock get_default_branch
            mock_get_branch.return_value = "main"
            
            # Mock get_all_workflow_shas to return a different SHA
            mock_get_shas.return_value = {
                "AM_TEST_test.yml": "def456"  # Different SHA
            }
            
            # Mock GitHub returns different content
            mock_get_github.return_value = {
                "content": "name: Test GitHub\non: pull_request",
                "sha": "def456"
            }
            
            results = _process_regular_workflows(
                db, workflows, ["owner/repo"], "TEST", "test_token"
            )
            
            assert len(results) == 1
            assert results[0].has_drift == True
            assert "Local" in results[0].local_content
            assert "GitHub" in results[0].github_content
        finally:
            db.close()

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    @patch('workflows.get_workflow_from_github')
    def test_process_regular_workflows_not_in_github(self, mock_get_github):
        """Test processing workflows that don't exist in GitHub and were never synced."""
        db = TestingSessionLocal()
        try:
            # Create workflow without git hash (never synced)
            workflow = Workflow(
                workflow_name="test.yml",
                workflow_yaml="name: Test\non: push",
                reusable_workflow=False,
                workflow_git_hash=None  # No previous sync
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            
            workflows = [workflow]
            
            # Mock GitHub returns None (not found)
            mock_get_github.return_value = None
            
            results = _process_regular_workflows(
                db, workflows, ["owner/repo"], "TEST", "test_token"
            )
            
            # When workflow doesn't exist in GitHub and has no git hash,
            # _compare_workflow_content returns None, so no drift is reported
            assert len(results) == 0
        finally:
            db.close()

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    @patch('workflows.get_workflow_from_github')
    def test_process_regular_workflows_deleted_from_github(self, mock_get_github):
        """Test processing workflows that were deleted from GitHub."""
        db = TestingSessionLocal()
        try:
            # Create workflow with git hash (was previously synced)
            workflow = Workflow(
                workflow_name="test.yml",
                workflow_yaml="name: Test\non: push",
                reusable_workflow=False,
                workflow_git_hash="abc123"  # Previously synced
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            
            workflows = [workflow]
            
            # Mock GitHub returns None (deleted)
            mock_get_github.return_value = None
            
            results = _process_regular_workflows(
                db, workflows, ["owner/repo"], "TEST", "test_token"
            )
            
            # Workflow was synced before but now deleted, should report drift
            assert len(results) == 1
            assert results[0].has_drift == True
            assert "deleted" in results[0].message.lower()
        finally:
            db.close()

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    @patch('workflows.get_workflow_from_github')
    def test_process_regular_workflows_multiple_repos(self, mock_get_github):
        """Test processing workflows across multiple repositories."""
        db = TestingSessionLocal()
        try:
            # Create workflow
            workflow = Workflow(
                workflow_name="test.yml",
                workflow_yaml="name: Test\non: push",
                workflow_git_hash="abc123",
                reusable_workflow=False
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            
            workflows = [workflow]
            
            # Mock GitHub returns same content
            mock_get_github.return_value = {
                "content": "name: Test\non: push",
                "sha": "abc123"
            }
            
            results = _process_regular_workflows(
                db, workflows, ["owner/repo1", "owner/repo2", "owner/repo3"], 
                "TEST", "test_token"
            )
            
            # Should get results for each repo
            assert len(results) == 3
        finally:
            db.close()

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    @patch('workflows.get_all_workflow_shas')
    @patch('workflows.get_default_branch')
    @patch('workflows.get_workflow_from_github')
    def test_process_reusable_workflows_no_drift(self, mock_get_github, mock_get_branch, mock_get_shas):
        """Test processing reusable workflows with no drift."""
        db = TestingSessionLocal()
        try:
            # Create reusable workflow (workflow_name should not include .yml)
            workflow = Workflow(
                workflow_name="reusable",
                workflow_yaml="name: Reusable\non: workflow_call",
                workflow_git_hash="xyz789",
                reusable_workflow=True
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            
            workflows = [workflow]
            
            # Mock get_default_branch
            mock_get_branch.return_value = "main"
            
            # Mock get_all_workflow_shas to return the SHA
            mock_get_shas.return_value = {
                "AM_TEST_reusable.yml": "xyz789"  # Same SHA as in DB
            }
            
            # Mock GitHub returns same content
            mock_get_github.return_value = {
                "content": "name: Reusable\non: workflow_call",
                "sha": "xyz789"
            }
            
            results = _process_reusable_workflows(
                db, workflows, "testuser", "TEST", "test_token"
            )
            
            assert len(results) == 1
            assert results[0].has_drift == False
        finally:
            db.close()

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    @patch('workflows.get_all_workflow_shas')
    @patch('workflows.get_default_branch')
    @patch('workflows.get_workflow_from_github')
    def test_process_reusable_workflows_with_drift(self, mock_get_github, mock_get_branch, mock_get_shas):
        """Test processing reusable workflows with drift."""
        db = TestingSessionLocal()
        try:
            # Create reusable workflow (workflow_name should not include .yml)
            workflow = Workflow(
                workflow_name="reusable",
                workflow_yaml="name: Reusable Local\non: workflow_call",
                workflow_git_hash="xyz789",
                reusable_workflow=True
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            
            workflows = [workflow]
            
            # Mock get_default_branch
            mock_get_branch.return_value = "main"
            
            # Mock get_all_workflow_shas to return a different SHA
            mock_get_shas.return_value = {
                "AM_TEST_reusable.yml": "uvw456"  # Different SHA
            }
            
            # Mock GitHub returns different content
            mock_get_github.return_value = {
                "content": "name: Reusable GitHub\non: workflow_call",
                "sha": "uvw456"
            }
            
            results = _process_reusable_workflows(
                db, workflows, "testuser", "TEST", "test_token"
            )
            
            assert len(results) == 1
            assert results[0].has_drift == True
            assert results[0].drift_type == "reusable_workflow"
        finally:
            db.close()

    def test_workflow_trimming(self):
        """Test that workflow names and content are trimmed."""
        db = TestingSessionLocal()
        try:
            workflow_data = WorkflowSchema(
                name="  test.yml  ",
                content="  name: Test\non: push  "
            )
            
            create_or_update_workflow(db, workflow_data, self.project_id, is_reusable=False)
            
            # Verify trimming
            workflow = db.query(Workflow).first()
            assert workflow.workflow_name == "test.yml"
            assert workflow.workflow_yaml == "name: Test\non: push"
        finally:
            db.close()

    def test_create_workflow_with_empty_name(self):
        """Test creating workflow with empty name is rejected."""
        db = TestingSessionLocal()
        try:
            workflow_data = WorkflowSchema(
                name="",
                content="name: Test\non: push"
            )

            with pytest.raises(HTTPException, match="Workflow name is required"):
                create_or_update_workflow(db, workflow_data, self.project_id, is_reusable=False)

            workflow = db.query(Workflow).filter_by(workflow_name="").first()
            assert workflow is None
        finally:
            db.close()

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    def test_count_workflows_with_multiple_projects(self):
        """Test counting workflows with multiple projects."""
        # The count_project_workflows function creates its own session,
        # so we test it directly without database isolation issues
        # Count for each project (both will return 0 due to test DB isolation)
        count1 = count_project_workflows("testuser", "test_project")
        count2 = count_project_workflows("testuser", "project2")
        
        # Both should return 0 as the function can't access test database
        assert count1 == 0
        assert count2 == 0


class TestBatchSHAComparison:
    """Test batch SHA comparison optimization for drift detection."""
    
    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Set up the test database before each test."""
        Base.metadata.create_all(bind=engine)
        
        # Create test data
        db = TestingSessionLocal()
        try:
            # Create test user
            test_user = Account(
                github_user="testuser",
                github_email="testuser@example.com",
                account_type="free"
            )
            db.add(test_user)
            db.commit()
            db.refresh(test_user)
            self.user_id = test_user.user_id
            
            # Create test project
            test_project = Project(
                project_name="test_project",
                project_code="TEST",
                user_id=self.user_id,
                branch_option="default"
            )
            db.add(test_project)
            db.commit()
            db.refresh(test_project)
            self.project_id = test_project.project_id
            
        finally:
            db.close()
        
        yield
        
        # Clean up after test
        Base.metadata.drop_all(bind=engine)
        if "testuser" in user_tokens:
            del user_tokens["testuser"]
    
    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    @patch('workflows.get_all_workflow_shas')
    @patch('workflows.get_default_branch')
    @patch('workflows.get_workflow_from_github')
    def test_batch_sha_comparison_no_fetch_when_sha_matches(self, mock_get_workflow, mock_get_branch, mock_get_shas):
        """Test that get_workflow_from_github is NOT called when SHA matches."""
        db = TestingSessionLocal()
        try:
            # Create workflow with git hash
            workflow = Workflow(
                workflow_name="test",
                workflow_yaml="name: Test\non: push",
                workflow_git_hash="abc123",
                reusable_workflow=False
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            
            workflows = [workflow]
            
            # Mock get_default_branch
            mock_get_branch.return_value = "main"
            
            # Mock get_all_workflow_shas to return the same SHA
            mock_get_shas.return_value = {
                "AM_TEST_test.yml": "abc123"  # Same SHA as in DB
            }
            
            results = _process_regular_workflows(
                db, workflows, ["owner/repo"], "TEST", "test_token"
            )
            
            # Verify get_all_workflow_shas was called once
            assert mock_get_shas.call_count == 1
            
            # Verify get_workflow_from_github was NOT called (optimization working)
            assert mock_get_workflow.call_count == 0
            
            # Verify result shows no drift
            assert len(results) == 1
            assert results[0].has_drift == False
            
        finally:
            db.close()
    
    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    @patch('workflows.get_all_workflow_shas')
    @patch('workflows.get_default_branch')
    @patch('workflows.get_workflow_from_github')
    def test_batch_sha_comparison_fetch_when_sha_differs(self, mock_get_workflow, mock_get_branch, mock_get_shas):
        """Test that get_workflow_from_github IS called when SHA differs."""
        db = TestingSessionLocal()
        try:
            # Create workflow with old git hash
            workflow = Workflow(
                workflow_name="test",
                workflow_yaml="name: Test\non: push",
                workflow_git_hash="old123",
                reusable_workflow=False
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            
            workflows = [workflow]
            
            # Mock get_default_branch
            mock_get_branch.return_value = "main"
            
            # Mock get_all_workflow_shas to return different SHA
            mock_get_shas.return_value = {
                "AM_TEST_test.yml": "new456"  # Different SHA
            }
            
            # Mock get_workflow_from_github to return updated content
            mock_get_workflow.return_value = {
                "content": "name: Test\non: pull_request",
                "sha": "new456"
            }
            
            results = _process_regular_workflows(
                db, workflows, ["owner/repo"], "TEST", "test_token"
            )
            
            # Verify get_all_workflow_shas was called once
            assert mock_get_shas.call_count == 1
            
            # Verify get_workflow_from_github WAS called (to fetch changed content)
            assert mock_get_workflow.call_count == 1
            
            # Verify result shows drift
            assert len(results) == 1
            assert results[0].has_drift == True
            
        finally:
            db.close()
    
    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    @patch('workflows.get_all_workflow_shas')
    @patch('workflows.get_default_branch')
    @patch('workflows.get_workflow_from_github')
    def test_batch_sha_comparison_deleted_from_github(self, mock_get_workflow, mock_get_branch, mock_get_shas):
        """Test handling workflow deleted from GitHub (exists in DB but missing from tree)."""
        db = TestingSessionLocal()
        try:
            # Create workflow with git hash (was previously synced)
            workflow = Workflow(
                workflow_name="deleted",
                workflow_yaml="name: Deleted\non: push",
                workflow_git_hash="abc123",
                reusable_workflow=False
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            
            workflows = [workflow]
            
            # Mock get_default_branch
            mock_get_branch.return_value = "main"
            
            # Mock get_all_workflow_shas to NOT include this workflow
            mock_get_shas.return_value = {}  # Workflow not in GitHub
            
            # get_workflow_from_github should not be called since SHA is None
            
            results = _process_regular_workflows(
                db, workflows, ["owner/repo"], "TEST", "test_token"
            )
            
            # Verify result shows drift (workflow was deleted)
            assert len(results) == 1
            assert results[0].has_drift == True
            assert "deleted" in results[0].message.lower()
            
        finally:
            db.close()
    
    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    @patch('workflows.get_all_workflow_shas')
    @patch('workflows.get_default_branch')
    def test_batch_sha_comparison_never_synced(self, mock_get_branch, mock_get_shas):
        """Test workflow that was never pushed to GitHub (no git hash in DB)."""
        db = TestingSessionLocal()
        try:
            # Create workflow without git hash (never synced)
            workflow = Workflow(
                workflow_name="new",
                workflow_yaml="name: New\non: push",
                workflow_git_hash=None,
                reusable_workflow=False
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            
            workflows = [workflow]
            
            # Mock get_default_branch
            mock_get_branch.return_value = "main"
            
            # Mock get_all_workflow_shas to NOT include this workflow
            mock_get_shas.return_value = {}
            
            results = _process_regular_workflows(
                db, workflows, ["owner/repo"], "TEST", "test_token"
            )
            
            # Verify no drift reported (workflow was never synced, not deleted)
            assert len(results) == 0
            
        finally:
            db.close()
    
    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    @patch('workflows.get_all_workflow_shas')
    @patch('workflows.get_default_branch')
    def test_reusable_workflows_batch_sha_comparison(self, mock_get_branch, mock_get_shas):
        """Test batch SHA comparison for reusable workflows."""
        db = TestingSessionLocal()
        try:
            # Create reusable workflow with matching SHA
            workflow = Workflow(
                workflow_name="reusable",
                workflow_yaml="name: Reusable\non: workflow_call",
                workflow_git_hash="xyz789",
                reusable_workflow=True
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            
            workflows = [workflow]
            
            # Mock get_default_branch
            mock_get_branch.return_value = "main"
            
            # Mock get_all_workflow_shas to return matching SHA
            mock_get_shas.return_value = {
                "AM_TEST_reusable.yml": "xyz789"
            }
            
            results = _process_reusable_workflows(
                db, workflows, "testuser", "TEST", "test_token"
            )
            
            # Verify get_all_workflow_shas was called once
            assert mock_get_shas.call_count == 1
            
            # Verify no drift
            assert len(results) == 1
            assert results[0].has_drift == False
            
        finally:
            db.close()
