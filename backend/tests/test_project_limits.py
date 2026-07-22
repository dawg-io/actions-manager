"""
Tests for project limit functionality for free users.
"""
import pytest
import sys
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Base, Account, Project
from main import app
from projects import get_db

# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_project_limits.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    """Override the database dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

class TestProjectLimits:
    """Test class for project limit functionality."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Set up the test database before each test."""
        # Set up database dependency override for this test
        app.dependency_overrides[get_db] = override_get_db
        
        # Create tables
        Base.metadata.create_all(bind=engine)
        
        # Create test users
        db = TestingSessionLocal()
        try:
            # Free user
            free_user = Account(
                github_user="freeuser",
                github_email="freeuser@example.com",
                account_type="free"
            )
            db.add(free_user)
            
            # Pro user
            pro_user = Account(
                github_user="prouser",
                github_email="prouser@example.com",
                account_type="professional"
            )
            db.add(pro_user)
            
            # Enterprise user
            enterprise_user = Account(
                github_user="enterpriseuser",
                github_email="enterpriseuser@example.com",
                account_type="enterprise"
            )
            db.add(enterprise_user)
            
            db.commit()
        finally:
            db.close()
        
        yield
        
        # Clean up after test
        Base.metadata.drop_all(bind=engine)
        # Clean up dependency override
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]

    def setup_method(self):
        """Set up test client"""
        self.client = TestClient(app)

    def test_free_user_can_create_projects_under_limit(self):
        """Test that free users can create projects when under the limit."""
        # Create 3 projects for free user (under limit of 3)
        for i in range(3):
            project_data = {
                "github_user": "freeuser",
                "project_name": f"Test Project {i+1}",
                "selected_repos": ["test/repo1"],
                "workflows": [],
                "rxworkflows": [],
                "branch_regex": "",
                "branch_option": "default",
                "reusable_workflows_enabled": False
            }
            
            response = self.client.post("/api/projects/", json=project_data)
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "✅ Project saved successfully!"

    def test_free_user_blocked_at_project_limit(self):
        """Test that free users are blocked when they reach the project limit."""
        # Create 3 projects for free user (at limit)
        for i in range(3):
            project_data = {
                "github_user": "freeuser",
                "project_name": f"Test Project {i+1}",
                "selected_repos": ["test/repo1"],
                "workflows": [],
                "rxworkflows": [],
                "branch_regex": "",
                "branch_option": "default",
                "reusable_workflows_enabled": False
            }
            
            response = self.client.post("/api/projects/", json=project_data)
            assert response.status_code == 200

        # Try to create 4th project - should be blocked
        project_data = {
            "github_user": "freeuser",
            "project_name": "Test Project 4",
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False
        }
        
        response = self.client.post("/api/projects/", json=project_data)
        assert response.status_code == 403
        data = response.json()
        assert "Free accounts can only create up to 3 projects" in data["detail"]
        assert "Professional" in data["detail"]  # Should suggest Professional upgrade

    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_pro_user_project_limit(self):
        """Test that professional users can create up to 10 projects."""
        # Create 10 projects for pro user (at limit)
        for i in range(10):
            project_data = {
                "github_user": "prouser",
                "project_name": f"Pro Project {i+1}",
                "selected_repos": ["test/repo1"],
                "workflows": [],
                "rxworkflows": [],
                "branch_regex": "",
                "branch_option": "default",
                "reusable_workflows_enabled": False
            }
            
            response = self.client.post("/api/projects/", json=project_data)
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "✅ Project saved successfully!"
        
        # Try to create 11th project - should be blocked
        project_data = {
            "github_user": "prouser",
            "project_name": "Pro Project 11",
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False
        }
        
        response = self.client.post("/api/projects/", json=project_data)
        assert response.status_code == 403
        data = response.json()
        assert "Professional accounts can create up to 10 projects" in data["detail"]
        assert "Enterprise" in data["detail"]  # Should suggest Enterprise upgrade
    
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_enterprise_user_not_limited(self):
        """Test that enterprise users are not limited by the project count."""
        # Create 15 projects for enterprise user (over both free and pro limits)
        for i in range(15):
            project_data = {
                "github_user": "enterpriseuser",
                "project_name": f"Enterprise Project {i+1}",
                "selected_repos": ["test/repo1"],
                "workflows": [],
                "rxworkflows": [],
                "branch_regex": "",
                "branch_option": "default",
                "reusable_workflows_enabled": False
            }
            
            response = self.client.post("/api/projects/", json=project_data)
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "✅ Project saved successfully!"

    def test_get_projects_includes_account_type(self):
        """Test that the get projects endpoint includes account_type."""
        # Create a project for free user
        project_data = {
            "github_user": "freeuser",
            "project_name": "Test Project",
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False
        }
        
        response = self.client.post("/api/projects/", json=project_data)
        assert response.status_code == 200

        # Get projects
        response = self.client.get("/api/projects/", params={"github_user": "freeuser"})
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) == 1
        assert data[0]["account_type"] == "free"
        assert "project_name" in data[0]
        assert "project_id" in data[0]
        assert data[0]["workflow_count"] == 0

    def test_get_projects_includes_workflow_count(self):
        """Test that the get projects endpoint includes workflow_count for standard and RWX projects."""
        standard_project = {
            "github_user": "freeuser",
            "project_name": "Standard With Workflows",
            "selected_repos": ["test/repo1"],
            "workflows": [
                {"name": "build.yml", "content": "name: Build\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest"},
            ],
            "rxworkflows": [
                {"name": "rx-1.yml", "content": "name: RX 1\non: workflow_call\njobs:\n  test:\n    runs-on: ubuntu-latest"},
                {"name": "rx-2.yml", "content": "name: RX 2\non: workflow_call\njobs:\n  test:\n    runs-on: ubuntu-latest"},
            ],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": True,
            "project_type": "standard",
        }
        rwx_project = {
            "github_user": "freeuser",
            "project_name": "Reusable Workflow Project",
            "selected_repos": ["test/repo2"],
            "workflows": [],
            "rxworkflows": [
                {"name": "shared.yml", "content": "name: Shared\non: workflow_call\njobs:\n  test:\n    runs-on: ubuntu-latest"},
            ],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": True,
            "project_type": "rwx",
        }

        resp = self.client.post("/api/projects/", json=standard_project)
        assert resp.status_code == 200

        resp = self.client.post("/api/projects/", json=rwx_project)
        assert resp.status_code == 200

        resp = self.client.get("/api/projects/", params={"github_user": "freeuser"})
        assert resp.status_code == 200
        projects = {p["project_name"]: p for p in resp.json()}

        assert projects["Standard With Workflows"]["workflow_count"] == 3
        assert projects["Reusable Workflow Project"]["workflow_count"] == 1

    def test_project_update_not_affected_by_limit(self):
        """Test that updating existing projects is not affected by the limit."""
        # Create 3 projects for free user (at limit)
        project_ids = []
        for i in range(3):
            project_data = {
                "github_user": "freeuser",
                "project_name": f"Test Project {i+1}",
                "selected_repos": ["test/repo1"],
                "workflows": [],
                "rxworkflows": [],
                "branch_regex": "",
                "branch_option": "default",
                "reusable_workflows_enabled": False
            }
            
            response = self.client.post("/api/projects/", json=project_data)
            assert response.status_code == 200
            project_ids.append(response.json()["project_id"])

        # Update the first project - should work even at limit
        update_data = {
            "github_user": "freeuser",
            "project_name": "Test Project 1",
            "selected_repos": ["test/repo1", "test/repo2"],  # Adding another repo
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False
        }
        
        response = self.client.put(f"/api/projects/{project_ids[0]}/", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "✅ Project updated successfully!"
    
    def test_free_user_can_use_private_repos(self):
        """Free users can create projects with private repositories (core product)."""
        project_data = {
            "github_user": "freeuser",
            "project_name": "Private Repo Project",
            "selected_repos": ["private:test/private-repo"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False
        }

        response = self.client.post("/api/projects/", json=project_data)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "✅ Project saved successfully!"
    
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_professional_user_can_use_private_repos(self):
        """Test that professional users can create projects with private repositories."""
        project_data = {
            "github_user": "prouser",
            "project_name": "Private Repo Project",
            "selected_repos": ["private:test/private-repo"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False
        }
        
        response = self.client.post("/api/projects/", json=project_data)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "✅ Project saved successfully!"
