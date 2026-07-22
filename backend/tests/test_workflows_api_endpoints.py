"""
Comprehensive tests for workflows.py API endpoints.
Tests all REST API endpoints exposed by the workflows router.
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Base, Account, Project, Workflow, ProjectWorkflow, LinkedReusableWorkflow
from main import app
from workflows import get_db
from auth import user_tokens

# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_workflows_api.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override the database dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


class TestWorkflowAPIEndpoints:
    """Test class for workflow API endpoints."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Set up the test database before each test."""
        # Set up database dependency override
        app.dependency_overrides[get_db] = override_get_db
        
        # Create tables
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
                branch_option="default",
                reusable_workflows_enabled=True
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
        # Clean up dependency override
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]
        # Clean up any user tokens that were added
        if "testuser" in user_tokens:
            del user_tokens["testuser"]

    def test_save_workflows_success(self):
        """Test successful workflow save with regular workflows."""
        client = TestClient(app)
        
        payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflows": [
                {"name": "test-workflow.yml", "content": "name: Test\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest"}
            ],
            "rxworkflows": []
        }
        
        response = client.post("/api/save-workflows", json=payload)
        assert response.status_code == 200
        assert response.json()["message"] == "Workflows saved successfully"
        
        # Verify workflow was saved
        db = TestingSessionLocal()
        try:
            workflow = db.query(Workflow).filter_by(workflow_name="test-workflow.yml").first()
            assert workflow is not None
            assert workflow.reusable_workflow == False
        finally:
            db.close()

    def test_save_workflows_with_reusable(self):
        """Test successful workflow save with reusable workflows."""
        client = TestClient(app)
        
        payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflows": [
                {"name": "test-workflow.yml", "content": "name: Test\non: push"}
            ],
            "rxworkflows": [
                {"name": "reusable-workflow.yml", "content": "name: Reusable\non: workflow_call"}
            ]
        }
        
        response = client.post("/api/save-workflows", json=payload)
        assert response.status_code == 200
        
        # Verify both workflow types were saved
        db = TestingSessionLocal()
        try:
            regular = db.query(Workflow).filter_by(workflow_name="test-workflow.yml").first()
            reusable = db.query(Workflow).filter_by(workflow_name="reusable-workflow.yml").first()
            
            assert regular is not None
            assert regular.reusable_workflow == False
            assert reusable is not None
            assert reusable.reusable_workflow == True
        finally:
            db.close()

    def test_save_workflows_account_not_found(self):
        """Test workflow save with non-existent account."""
        client = TestClient(app)
        
        payload = {
            "github_user": "nonexistent",
            "project_name": "test_project",
            "workflows": [
                {"name": "test.yml", "content": "name: Test"}
            ],
            "rxworkflows": []
        }
        
        response = client.post("/api/save-workflows", json=payload)
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_save_workflows_project_not_found(self):
        """Test workflow save with non-existent project."""
        client = TestClient(app)
        
        payload = {
            "github_user": "testuser",
            "project_name": "nonexistent_project",
            "workflows": [
                {"name": "test.yml", "content": "name: Test"}
            ],
            "rxworkflows": []
        }
        
        response = client.post("/api/save-workflows", json=payload)
        assert response.status_code == 404
        assert "Project not found" in response.json()["detail"]

    def test_save_workflows_update_existing(self):
        """Test updating an existing workflow."""
        client = TestClient(app)
        
        # First save
        payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflows": [
                {"name": "test-workflow.yml", "content": "name: Test V1\non: push"}
            ],
            "rxworkflows": []
        }
        
        response = client.post("/api/save-workflows", json=payload)
        assert response.status_code == 200
        
        # Update with new content
        payload["workflows"][0]["content"] = "name: Test V2\non: pull_request"
        response = client.post("/api/save-workflows", json=payload)
        assert response.status_code == 200
        
        # Verify only one workflow exists with updated content
        db = TestingSessionLocal()
        try:
            workflows = db.query(Workflow).filter_by(workflow_name="test-workflow.yml").all()
            assert len(workflows) == 1
            assert "V2" in workflows[0].workflow_yaml
        finally:
            db.close()

    def test_save_workflows_trims_workflow_name(self):
        """Workflow names are trimmed before storage."""
        client = TestClient(app)

        payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflows": [
                {"name": "  trimmed-workflow  ", "content": "name: Trimmed\non: push"}
            ],
            "rxworkflows": []
        }

        response = client.post("/api/save-workflows", json=payload)
        assert response.status_code == 200

        db = TestingSessionLocal()
        try:
            workflow = db.query(Workflow).filter_by(workflow_name="trimmed-workflow").first()
            assert workflow is not None
        finally:
            db.close()

    def test_save_workflows_rejects_unsafe_workflow_name(self):
        """Unsafe workflow path names are rejected server-side."""
        client = TestClient(app)

        payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflows": [
                {"name": "../bad", "content": "name: Bad\non: push"}
            ],
            "rxworkflows": []
        }

        response = client.post("/api/save-workflows", json=payload)
        assert response.status_code == 400
        assert "Workflow name" in response.json()["detail"]

    def test_save_workflows_rename_replaces_old(self):
        """Renaming a workflow must update the existing record and not leave the old one behind."""
        client = TestClient(app)

        # Create original workflow
        payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflows": [
                {"name": "old-workflow", "content": "name: Old\non: push"}
            ],
            "rxworkflows": []
        }
        response = client.post("/api/save-workflows", json=payload)
        assert response.status_code == 200

        # Rename: same content, new name, supply original_name so backend can rename
        rename_payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflows": [
                {"name": "new-workflow", "content": "name: Old\non: push", "original_name": "old-workflow"}
            ],
            "rxworkflows": []
        }
        response = client.post("/api/save-workflows", json=rename_payload)
        assert response.status_code == 200

        db = TestingSessionLocal()
        try:
            old_wf = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == self.project_id,
                Workflow.workflow_name.ilike("old-workflow")
            ).first()
            new_wf = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == self.project_id,
                Workflow.workflow_name.ilike("new-workflow")
            ).first()
            # Old name must be gone
            assert old_wf is None, "Old workflow should have been removed after rename"
            # New name must exist
            assert new_wf is not None, "Renamed workflow should exist with new name"
        finally:
            db.close()

    def test_save_reusable_workflows_rename_replaces_old(self):
        """Renaming a reusable workflow must update the existing record and not create a duplicate."""
        client = TestClient(app)

        payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflows": [],
            "rxworkflows": [
                {"name": "old-rx-workflow", "content": "name: Old RX\non:\n  workflow_call:"}
            ]
        }
        response = client.post("/api/save-workflows", json=payload)
        assert response.status_code == 200

        rename_payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflows": [],
            "rxworkflows": [
                {
                    "name": "new-rx-workflow",
                    "content": "name: Old RX\non:\n  workflow_call:",
                    "original_name": "old-rx-workflow"
                }
            ]
        }
        response = client.post("/api/save-workflows", json=rename_payload)
        assert response.status_code == 200

        db = TestingSessionLocal()
        try:
            old_wf = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == self.project_id,
                Workflow.workflow_name.ilike("old-rx-workflow")
            ).first()
            new_wf = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == self.project_id,
                Workflow.workflow_name.ilike("new-rx-workflow")
            ).first()
            assert old_wf is None, "Old reusable workflow should have been removed after rename"
            assert new_wf is not None, "Renamed reusable workflow should exist with new name"
        finally:
            db.close()

    def test_save_workflows_rename_cleans_up_accidental_duplicate(self):
        """If the new name already exists (accidental duplicate), rename removes it."""
        client = TestClient(app)

        # Simulate the broken state: both old and new names exist
        db = TestingSessionLocal()
        try:
            old_wf = Workflow(
                workflow_name="dup-old",
                workflow_yaml="name: Old\non: push",
                reusable_workflow=False,
                workflow_git_hash="0" * 40,
                workflow_status="new",
            )
            new_dup_wf = Workflow(
                workflow_name="dup-new",
                workflow_yaml="name: New\non: push",
                reusable_workflow=False,
                workflow_git_hash="0" * 40,
                workflow_status="new",
            )
            db.add_all([old_wf, new_dup_wf])
            db.commit()
            db.refresh(old_wf)
            db.refresh(new_dup_wf)
            db.add(ProjectWorkflow(project_id=self.project_id, workflow_id=old_wf.workflow_id))
            db.add(ProjectWorkflow(project_id=self.project_id, workflow_id=new_dup_wf.workflow_id))
            db.commit()
        finally:
            db.close()

        # Now rename dup-old → dup-new (duplicate cleanup should happen)
        rename_payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflows": [
                {
                    "name": "dup-new",
                    "content": "name: Old\non: push",
                    "original_name": "dup-old",
                }
            ],
            "rxworkflows": []
        }
        response = client.post("/api/save-workflows", json=rename_payload)
        assert response.status_code == 200

        db = TestingSessionLocal()
        try:
            all_wf = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == self.project_id,
                Workflow.reusable_workflow.isnot(True),
                Workflow.workflow_name.in_(["dup-old", "dup-new"])
            ).all()
            assert len(all_wf) == 1, "Only the renamed workflow should remain"
            assert all_wf[0].workflow_name == "dup-new"
        finally:
            db.close()

    def test_save_workflows_rename_removes_all_duplicates(self):
        """Rename cleanup must remove ALL duplicate entries, not just the first one."""
        db = TestingSessionLocal()
        try:
            # Simulate broken state: old name + two duplicates under the new name
            old_wf = Workflow(
                workflow_name="multi-old",
                workflow_yaml="name: Old\non: push",
                reusable_workflow=False,
                workflow_git_hash="0" * 40,
                workflow_status="new",
            )
            dup1 = Workflow(
                workflow_name="multi-new",
                workflow_yaml="name: Dup1\non: push",
                reusable_workflow=False,
                workflow_git_hash="0" * 40,
                workflow_status="new",
            )
            dup2 = Workflow(
                workflow_name="multi-new",
                workflow_yaml="name: Dup2\non: push",
                reusable_workflow=False,
                workflow_git_hash="0" * 40,
                workflow_status="new",
            )
            db.add_all([old_wf, dup1, dup2])
            db.commit()
            db.refresh(old_wf)
            db.refresh(dup1)
            db.refresh(dup2)
            db.add(ProjectWorkflow(project_id=self.project_id, workflow_id=old_wf.workflow_id))
            db.add(ProjectWorkflow(project_id=self.project_id, workflow_id=dup1.workflow_id))
            db.add(ProjectWorkflow(project_id=self.project_id, workflow_id=dup2.workflow_id))
            db.commit()
        finally:
            db.close()

        rename_payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflows": [
                {
                    "name": "multi-new",
                    "content": "name: Old\non: push",
                    "original_name": "multi-old",
                }
            ],
            "rxworkflows": [],
        }
        response = TestClient(app).post("/api/save-workflows", json=rename_payload)
        assert response.status_code == 200

        db = TestingSessionLocal()
        try:
            remaining = (
                db.query(Workflow)
                .join(ProjectWorkflow)
                .filter(
                    ProjectWorkflow.project_id == self.project_id,
                    Workflow.workflow_name.ilike("multi-new"),
                )
                .all()
            )
            assert len(remaining) == 1, "All duplicates should be removed; only one renamed entry should remain"
        finally:
            db.close()

    def test_save_workflows_rename_migrates_linked_reusable_workflows(self):
        """LinkedReusableWorkflow rows on an accidental duplicate must be migrated, not orphaned."""
        db = TestingSessionLocal()
        try:
            # Create a second project to act as the standard project linked to the dup
            linked_project = Project(
                project_name="linked_project",
                project_code="LNK",
                user_id=self.user_id,
                branch_option="default",
                reusable_workflows_enabled=True,
                pr_state="new",
            )
            db.add(linked_project)
            db.commit()
            db.refresh(linked_project)

            # Old (to-be-renamed) reusable workflow
            old_rx = Workflow(
                workflow_name="rx-old",
                workflow_yaml="name: RX Old\non:\n  workflow_call:",
                reusable_workflow=True,
                workflow_git_hash="0" * 40,
                workflow_status="new",
            )
            # Accidental duplicate under the new name (created by the old broken rename)
            dup_rx = Workflow(
                workflow_name="rx-new",
                workflow_yaml="name: RX New\non:\n  workflow_call:",
                reusable_workflow=True,
                workflow_git_hash="0" * 40,
                workflow_status="new",
            )
            db.add_all([old_rx, dup_rx])
            db.commit()
            db.refresh(old_rx)
            db.refresh(dup_rx)

            db.add(ProjectWorkflow(project_id=self.project_id, workflow_id=old_rx.workflow_id))
            db.add(ProjectWorkflow(project_id=self.project_id, workflow_id=dup_rx.workflow_id))
            # The linked standard project is currently pointing to the accidental duplicate
            db.add(LinkedReusableWorkflow(
                standard_project_id=linked_project.project_id,
                rwx_project_id=self.project_id,
                workflow_id=dup_rx.workflow_id,
            ))
            db.commit()
            self.linked_project_id = linked_project.project_id
        finally:
            db.close()

        rename_payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflows": [],
            "rxworkflows": [
                {
                    "name": "rx-new",
                    "content": "name: RX Old\non:\n  workflow_call:",
                    "original_name": "rx-old",
                }
            ],
        }
        response = TestClient(app).post("/api/save-workflows", json=rename_payload)
        assert response.status_code == 200

        db = TestingSessionLocal()
        try:
            renamed_wf = (
                db.query(Workflow)
                .join(ProjectWorkflow)
                .filter(
                    ProjectWorkflow.project_id == self.project_id,
                    Workflow.workflow_name.ilike("rx-new"),
                )
                .first()
            )
            assert renamed_wf is not None, "Renamed workflow must exist"

            # The LinkedReusableWorkflow must now point to the surviving (renamed) workflow
            link = db.query(LinkedReusableWorkflow).filter_by(
                standard_project_id=self.linked_project_id
            ).first()
            assert link is not None, "LinkedReusableWorkflow row must still exist"
            assert link.workflow_id == renamed_wf.workflow_id, (
                "LinkedReusableWorkflow must be re-pointed to the renamed workflow, not deleted"
            )
        finally:
            db.close()

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    def test_detect_drift_endpoint_success(self):
        """Test drift detection endpoint."""
        client = TestClient(app)
        
        # Create a workflow first
        db = TestingSessionLocal()
        try:
            workflow = Workflow(
                workflow_name="test.yml",
                workflow_yaml="name: Test\non: push",
                reusable_workflow=False
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            
            # Associate with project
            db.add(ProjectWorkflow(
                project_id=self.project_id,
                workflow_id=workflow.workflow_id
            ))
            db.commit()
        finally:
            db.close()
        
        # Mock GitHub API calls
        with patch('workflows.get_workflow_from_github') as mock_get:
            mock_get.return_value = None  # No drift - workflow not in GitHub
            
            payload = {
                "github_user": "testuser",
                "project_name": "test_project",
                "repo_names": ["owner/repo"],
                "check_deployment_vars": False
            }
            
            response = client.post("/api/detect-drift", json=payload)
            assert response.status_code == 200
            assert "drift_results" in response.json()

    def test_detect_drift_endpoint_unauthenticated(self):
        """Test drift detection with unauthenticated user."""
        client = TestClient(app)
        
        payload = {
            "github_user": "unauthenticated",
            "project_name": "test_project",
            "repo_names": ["owner/repo"],
            "check_deployment_vars": False
        }
        
        response = client.post("/api/detect-drift", json=payload)
        assert response.status_code == 401
        assert "User not authenticated" in response.json()["detail"]

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    def test_resolve_drift_use_github(self):
        """Test resolving drift by using GitHub version."""
        client = TestClient(app)

        # Create a workflow and associate it with the test project
        db = TestingSessionLocal()
        try:
            workflow = Workflow(
                workflow_name="test.yml",
                workflow_yaml="name: Test Local\non: push",
                reusable_workflow=False
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            db.add(ProjectWorkflow(project_id=self.project_id, workflow_id=workflow.workflow_id))
            db.commit()
        finally:
            db.close()
        
        payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflow_name": "test.yml",
            "resolution": "use_github",
            "github_content": "name: Test GitHub\non: pull_request",
            "github_sha": "abc123"
        }
        
        response = client.post("/api/resolve-drift", json=payload)
        assert response.status_code == 200
        assert "database_updated" in response.json()["action"]
        
        # Verify workflow was updated
        db = TestingSessionLocal()
        try:
            workflow = db.query(Workflow).filter_by(workflow_name="test.yml").first()
            assert "GitHub" in workflow.workflow_yaml
            assert workflow.workflow_git_hash == "abc123"
        finally:
            db.close()

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    def test_resolve_drift_use_local(self):
        """Test resolving drift by using local version."""
        client = TestClient(app)

        # Create a workflow and associate it with the test project
        db = TestingSessionLocal()
        try:
            workflow = Workflow(
                workflow_name="test.yml",
                workflow_yaml="name: Test Local\non: push",
                reusable_workflow=False
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            db.add(ProjectWorkflow(project_id=self.project_id, workflow_id=workflow.workflow_id))
            db.commit()
        finally:
            db.close()
        
        payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflow_name": "test.yml",
            "resolution": "use_local"
        }
        
        response = client.post("/api/resolve-drift", json=payload)
        assert response.status_code == 200
        assert "use_update_github" in response.json()["action"]

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    def test_resolve_drift_workflow_not_found(self):
        """Test resolving drift with non-existent workflow."""
        client = TestClient(app)
        
        payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflow_name": "nonexistent.yml",
            "resolution": "use_github",
            "github_content": "name: Test"
        }
        
        response = client.post("/api/resolve-drift", json=payload)
        assert response.status_code == 404
        assert "Workflow not found" in response.json()["detail"]

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    def test_resolve_drift_invalid_resolution(self):
        """Test resolving drift with invalid resolution."""
        client = TestClient(app)

        # Create a workflow and associate it with the test project
        db = TestingSessionLocal()
        try:
            workflow = Workflow(
                workflow_name="test.yml",
                workflow_yaml="name: Test\non: push",
                reusable_workflow=False
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)
            db.add(ProjectWorkflow(project_id=self.project_id, workflow_id=workflow.workflow_id))
            db.commit()
        finally:
            db.close()
        
        payload = {
            "github_user": "testuser",
            "project_name": "test_project",
            "workflow_name": "test.yml",
            "resolution": "invalid_option"
        }
        
        response = client.post("/api/resolve-drift", json=payload)
        assert response.status_code == 400
        assert "Invalid resolution" in response.json()["detail"]

    @patch("auth.resolve_authenticated_user")
    def test_get_template_types(self, mock_auth):
        """Test getting available template types."""
        mock_auth.return_value = MagicMock()
        client = TestClient(app)

        response = client.get("/api/workflow-templates/types")
        assert response.status_code == 200
        assert "template_types" in response.json()

    @patch("auth.resolve_authenticated_user")
    def test_generate_workflow_templates(self, mock_auth):
        """Test generating workflow templates."""
        mock_auth.return_value = MagicMock()
        client = TestClient(app)

        payload = {
            "user_org": "testuser",
            "build_type": "python",
            "project_code": "TEST"
        }

        response = client.post("/api/workflow-templates/generate", json=payload)
        assert response.status_code == 200
        assert "templates" in response.json()

    @patch("auth.resolve_authenticated_user")
    def test_generate_standard_template(self, mock_auth):
        """Test generating a standard workflow template."""
        mock_auth.return_value = MagicMock()
        client = TestClient(app)

        payload = {
            "user_org": "testuser",
            "build_type": "nodejs",
            "project_code": "TEST"
        }

        response = client.post("/api/workflow-templates/standard", json=payload)
        assert response.status_code == 200
        assert "template" in response.json()

    @patch("auth.resolve_authenticated_user")
    def test_generate_reusable_template(self, mock_auth):
        """Test generating a reusable workflow template."""
        mock_auth.return_value = MagicMock()
        client = TestClient(app)

        payload = {
            "user_org": "testuser",
            "build_type": "docker",
            "project_code": "TEST"
        }

        response = client.post("/api/workflow-templates/reusable", json=payload)
        assert response.status_code == 200
        assert "template" in response.json()

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    @patch('workflows.count_project_workflows', return_value=3)
    @pytest.mark.asyncio
    async def test_get_workflows_count(self, mock_count):
        """Test getting workflow count."""
        client = TestClient(app)
        
        response = client.get("/api/workflows-count?user=testuser&project_name=test_project")
        assert response.status_code == 200
        assert response.json()["count"] == 3
        mock_count.assert_called_once_with("testuser", "test_project")

    @patch('workflows.user_tokens', {'testuser': 'test_token'})
    @patch('workflows.count_project_reusable_workflows', return_value=2)
    @pytest.mark.asyncio
    async def test_get_rxworkflows_count(self, mock_count):
        """Test getting reusable workflow count."""
        client = TestClient(app)
        
        response = client.get("/api/rxworkflows-count?user=testuser&project_name=test_project")
        assert response.status_code == 200
        assert response.json()["count"] == 2
        mock_count.assert_called_once_with("testuser", "test_project")

    def test_get_workflows_count_unauthenticated(self):
        """Test getting workflow count without authentication."""
        client = TestClient(app)
        
        response = client.get("/api/workflows-count?user=unknown&project_name=test_project")
        assert response.status_code == 200
        # The endpoint returns error dict instead of count
        assert "error" in response.json()
        assert response.json()["status"] == 401
