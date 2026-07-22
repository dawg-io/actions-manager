"""
Tests for use_prefix field in project creation and updates.
Verifies that the checkbox value is properly captured, sent, and stored.
"""
import pytest
import sys
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Base, Account, Project
from main import app
from projects import get_db

# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_use_prefix.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    """Override the database dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

class TestUsePrefixField:
    """Test class for use_prefix field handling."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Set up the test database before each test."""
        # Set up database dependency override for this test
        app.dependency_overrides[get_db] = override_get_db

        # Create tables
        Base.metadata.create_all(bind=engine)

        # Create test user
        db = TestingSessionLocal()
        try:
            test_user = Account(
                github_user="testuser",
                github_email="testuser@example.com",
                account_type="free"
            )
            db.add(test_user)
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

    def test_create_project_with_use_prefix_true(self):
        """Test creating a project with use_prefix=true (Secure Mode enabled)."""
        project_data = {
            "github_user": "testuser",
            "project_name": "Secure Project",
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "branch_max_age_days": 30,
            "reusable_workflows_enabled": False,
            "use_prefix": True
        }

        response = self.client.post("/api/projects/", json=project_data)

        assert response.status_code == 200
        data = response.json()
        assert "project_id" in data

        # Verify in database
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_name == "Secure Project").first()
            assert project is not None
            assert project.use_prefix is True
        finally:
            db.close()

    def test_create_project_with_use_prefix_false(self):
        """Test creating a project with use_prefix=false (No Prefix Mode)."""
        project_data = {
            "github_user": "testuser",
            "project_name": "No Prefix Project",
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "branch_max_age_days": 30,
            "reusable_workflows_enabled": False,
            "use_prefix": False
        }

        response = self.client.post("/api/projects/", json=project_data)

        assert response.status_code == 200
        data = response.json()
        assert "project_id" in data

        # Verify in database
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_name == "No Prefix Project").first()
            assert project is not None
            assert project.use_prefix is False
        finally:
            db.close()

    def test_create_project_without_use_prefix_defaults_to_true(self):
        """Test that omitting use_prefix defaults to true (backend schema default)."""
        project_data = {
            "github_user": "testuser",
            "project_name": "Default Prefix Project",
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "branch_max_age_days": 30,
            "reusable_workflows_enabled": False
            # use_prefix omitted
        }

        response = self.client.post("/api/projects/", json=project_data)

        assert response.status_code == 200
        data = response.json()
        assert "project_id" in data

        # Verify in database - should default to True
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_name == "Default Prefix Project").first()
            assert project is not None
            assert project.use_prefix is True
        finally:
            db.close()

    def test_update_project_use_prefix_from_true_to_false(self):
        """Test updating an existing project's use_prefix from true to false."""
        # Create project with use_prefix=true
        project_data = {
            "github_user": "testuser",
            "project_name": "Update Test Project",
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "branch_max_age_days": 30,
            "reusable_workflows_enabled": False,
            "use_prefix": True
        }

        create_response = self.client.post("/api/projects/", json=project_data)
        assert create_response.status_code == 200
        project_id = create_response.json()["project_id"]

        # Verify initial state
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == project_id).first()
            assert project.use_prefix is True
        finally:
            db.close()

        # Update to use_prefix=false
        project_data["use_prefix"] = False
        update_response = self.client.post("/api/projects/", json=project_data)
        assert update_response.status_code == 200

        # Verify updated state
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == project_id).first()
            assert project.use_prefix is False
        finally:
            db.close()

    def test_update_project_use_prefix_from_false_to_true(self):
        """Test updating an existing project's use_prefix from false to true."""
        # Create project with use_prefix=false
        project_data = {
            "github_user": "testuser",
            "project_name": "Toggle Test Project",
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "branch_max_age_days": 30,
            "reusable_workflows_enabled": False,
            "use_prefix": False
        }

        create_response = self.client.post("/api/projects/", json=project_data)
        assert create_response.status_code == 200
        project_id = create_response.json()["project_id"]

        # Verify initial state
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == project_id).first()
            assert project.use_prefix is False
        finally:
            db.close()

        # Update to use_prefix=true
        project_data["use_prefix"] = True
        update_response = self.client.post("/api/projects/", json=project_data)
        assert update_response.status_code == 200

        # Verify updated state
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == project_id).first()
            assert project.use_prefix is True
        finally:
            db.close()

    def test_get_project_returns_use_prefix_field(self):
        """Test that GET /api/projects/{project_name} returns the use_prefix field."""
        # Create project with use_prefix=false
        project_data = {
            "github_user": "testuser",
            "project_name": "Get Test Project",
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "branch_max_age_days": 30,
            "reusable_workflows_enabled": False,
            "use_prefix": False
        }

        create_response = self.client.post("/api/projects/", json=project_data)
        assert create_response.status_code == 200

        # Get project
        get_response = self.client.get(
            "/api/projects/Get%20Test%20Project",
            params={"github_user": "testuser"}
        )

        assert get_response.status_code == 200
        project = get_response.json()
        assert "use_prefix" in project
        assert project["use_prefix"] is False

    def test_database_column_type_is_boolean(self):
        """Test that the database column is properly configured as Boolean."""
        db = TestingSessionLocal()
        try:
            # Create a project
            project_data = {
                "github_user": "testuser",
                "project_name": "Type Test Project",
                "selected_repos": ["test/repo1"],
                "workflows": [],
                "rxworkflows": [],
                "branch_regex": "",
                "branch_option": "default",
                "branch_max_age_days": 30,
                "reusable_workflows_enabled": False,
                "use_prefix": False
            }

            response = self.client.post("/api/projects/", json=project_data)
            assert response.status_code == 200

            # Query directly from database
            project = db.query(Project).filter(Project.project_name == "Type Test Project").first()

            # Verify type is boolean
            assert isinstance(project.use_prefix, bool)
            assert project.use_prefix is False

            # Test with True value
            project.use_prefix = True
            db.commit()
            db.refresh(project)

            assert isinstance(project.use_prefix, bool)
            assert project.use_prefix is True
        finally:
            db.close()
