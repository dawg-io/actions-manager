"""
Tests for reusable workflow functionality, specifically the issue where
blank workflows are saved even when reusable workflows are disabled.
"""
import pytest
import sys
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Base, Account, Project, Workflow, ProjectWorkflow
from main import app
from projects import get_db

# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_reusable_workflows.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    """Override the database dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

class TestReusableWorkflows:
    """Test class for reusable workflow functionality."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Set up the test database before each test."""
        # Set up database dependency override for this test
        app.dependency_overrides[get_db] = override_get_db
        
        # Create tables
        Base.metadata.create_all(bind=engine)
        
        # Create a test user
        db = TestingSessionLocal()
        try:
            test_user = Account(
                github_user="testuser",
                github_email="testuser@example.com",
                account_type="free"
            )
            db.add(test_user)
            db.commit()
            db.refresh(test_user)
            self.user_id = test_user.user_id
        finally:
            db.close()
        
        yield
        
        # Clean up after test
        Base.metadata.drop_all(bind=engine)
        # Clean up dependency override
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]

    def test_reusable_workflows_disabled_should_not_save_blank_rxworkflows(self):
        """
        Test that when reusable_workflows_enabled is False, blank rxworkflows 
        should not be saved to the database.
        """
        client = TestClient(app)
        
        # Create project payload with reusable workflows disabled and blank rxworkflows
        project_data = {
            "project_name": "test_project",
            "github_user": "testuser",
            "selected_repos": ["test-repo"],
            "workflows": [
                {"name": "test_workflow", "content": "name: Test\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest"}
            ],
            "rxworkflows": [
                {"name": "", "content": ""}  # Blank reusable workflow
            ],
            "reusable_workflows_enabled": False,  # Key: reusable workflows are disabled
            "branch_regex": "",
            "branch_option": "default"
        }
        
        # Save the project
        response = client.post("/api/projects/", json=project_data)
        assert response.status_code == 200
        
        # Verify project was created
        project_id = response.json()["project_id"]
        assert project_id is not None
        
        # Check database state
        db = TestingSessionLocal()
        try:
            # Verify the project was created with reusable workflows disabled
            project = db.query(Project).filter(Project.project_id == project_id).first()
            assert project is not None
            assert project.reusable_workflows_enabled is False
            
            # Verify only regular workflows were saved, not reusable workflows
            project_workflows = db.query(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == project_id
            ).all()
            
            workflow_ids = [pw.workflow_id for pw in project_workflows]
            workflows = db.query(Workflow).filter(
                Workflow.workflow_id.in_(workflow_ids)
            ).all()
            
            # Should only have 1 workflow (the regular one)
            assert len(workflows) == 1
            
            # The workflow should be a regular workflow, not reusable
            regular_workflows = [w for w in workflows if not w.reusable_workflow]
            reusable_workflows = [w for w in workflows if w.reusable_workflow]
            
            assert len(regular_workflows) == 1
            assert len(reusable_workflows) == 0  # No reusable workflows should be saved
            assert regular_workflows[0].workflow_name == "test_workflow"
            
        finally:
            db.close()

    def test_reusable_workflows_enabled_should_save_rxworkflows(self):
        """
        Test that when reusable_workflows_enabled is True, rxworkflows 
        should be saved to the database.
        """
        client = TestClient(app)
        
        # Create project payload with reusable workflows enabled
        project_data = {
            "project_name": "test_project_enabled",
            "github_user": "testuser",
            "selected_repos": ["test-repo"],
            "workflows": [
                {"name": "test_workflow", "content": "name: Test\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest"}
            ],
            "rxworkflows": [
                {"name": "test_reusable", "content": "name: Reusable\non: workflow_call\njobs:\n  reusable:\n    runs-on: ubuntu-latest"}
            ],
            "reusable_workflows_enabled": True,  # Key: reusable workflows are enabled
            "branch_regex": "",
            "branch_option": "default"
        }
        
        # Save the project
        response = client.post("/api/projects/", json=project_data)
        assert response.status_code == 200
        
        # Verify project was created
        project_id = response.json()["project_id"]
        assert project_id is not None
        
        # Check database state
        db = TestingSessionLocal()
        try:
            # Verify the project was created with reusable workflows enabled
            project = db.query(Project).filter(Project.project_id == project_id).first()
            assert project is not None
            assert project.reusable_workflows_enabled is True
            
            # Verify both regular and reusable workflows were saved
            project_workflows = db.query(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == project_id
            ).all()
            
            workflow_ids = [pw.workflow_id for pw in project_workflows]
            workflows = db.query(Workflow).filter(
                Workflow.workflow_id.in_(workflow_ids)
            ).all()
            
            # Should have 2 workflows (regular + reusable)
            assert len(workflows) == 2
            
            # Separate workflows by type
            regular_workflows = [w for w in workflows if not w.reusable_workflow]
            reusable_workflows = [w for w in workflows if w.reusable_workflow]
            
            assert len(regular_workflows) == 1
            assert len(reusable_workflows) == 1
            assert regular_workflows[0].workflow_name == "test_workflow"
            assert reusable_workflows[0].workflow_name == "test_reusable"
            
        finally:
            db.close()

    def test_reusable_workflows_disabled_with_non_blank_rxworkflows(self):
        """
        Test that when reusable_workflows_enabled is False, even non-blank 
        rxworkflows should not be saved to the database.
        """
        client = TestClient(app)
        
        # Create project payload with reusable workflows disabled but non-blank rxworkflows
        project_data = {
            "project_name": "test_project_nonblank",
            "github_user": "testuser",
            "selected_repos": ["test-repo"],
            "workflows": [
                {"name": "test_workflow", "content": "name: Test\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest"}
            ],
            "rxworkflows": [
                {"name": "should_not_save", "content": "name: Should Not Save\non: workflow_call\njobs:\n  test:\n    runs-on: ubuntu-latest"}
            ],
            "reusable_workflows_enabled": False,  # Key: reusable workflows are disabled
            "branch_regex": "",
            "branch_option": "default"
        }
        
        # Save the project
        response = client.post("/api/projects/", json=project_data)
        assert response.status_code == 200
        
        # Check database state
        db = TestingSessionLocal()
        try:
            project_id = response.json()["project_id"]
            
            # Verify only regular workflows were saved
            project_workflows = db.query(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == project_id
            ).all()
            
            workflow_ids = [pw.workflow_id for pw in project_workflows]
            workflows = db.query(Workflow).filter(
                Workflow.workflow_id.in_(workflow_ids)
            ).all()
            
            # Should only have the regular workflow
            reusable_workflows = [w for w in workflows if w.reusable_workflow]
            assert len(reusable_workflows) == 0  # No reusable workflows should be saved
            
            # Verify no workflow with name "should_not_save" exists
            should_not_save_workflow = db.query(Workflow).filter(
                Workflow.workflow_name == "should_not_save"
            ).first()
            assert should_not_save_workflow is None
            
        finally:
            db.close()