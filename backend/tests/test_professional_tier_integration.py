"""
Comprehensive integration tests for professional tier feature.

This test suite validates end-to-end scenarios combining multiple features:
1. Complete user journey from free to professional
2. Multi-feature limit enforcement
3. Cross-feature interactions
4. Real-world usage patterns
"""

import pytest
import base64
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from unittest.mock import patch, AsyncMock, Mock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from database import Base
from models import Account, Project
from admin import get_db
from projects import get_db as projects_get_db
from github_secrets import _validate_account_limits

# Create test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_professional_tier_integration.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# Create test client
client = TestClient(app)


def get_basic_auth_header(username: str, password: str) -> dict:
    """Generate Basic Auth header"""
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {credentials}"}


@pytest.fixture(scope="function")
def setup_database():
    """Create test database and tables before each test"""
    # Set up database dependency override
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[projects_get_db] = override_get_db
    
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    
    # Clean up dependency overrides
    if get_db in app.dependency_overrides:
        del app.dependency_overrides[get_db]
    if projects_get_db in app.dependency_overrides:
        del app.dependency_overrides[projects_get_db]


@pytest.fixture
def test_db():
    """Get test database session"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestProfessionalTierCompleteScenario:
    """Test complete scenarios for professional tier users"""
    
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_complete_free_user_journey(self, setup_database, test_db):
        """Test complete journey: free user hits limits, upgrades to professional, gains access"""
        # Step 1: Create free user
        user = Account(
            github_user="journeyuser",
            github_email="journey@example.com",
            account_type="free",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Step 2: Create 3 projects (free limit)
        for i in range(3):
            project_data = {
                "github_user": "journeyuser",
                "project_name": f"Free Project {i+1}",
                "selected_repos": ["test/repo1"],
                "workflows": [],
                "rxworkflows": [],
                "branch_regex": "",
                "branch_option": "default",
                "reusable_workflows_enabled": False
            }
            response = client.post("/api/projects/", json=project_data)
            assert response.status_code == 200
        
        # Step 3: Try to create 4th project - should fail (project limit)
        project_data = {
            "github_user": "journeyuser",
            "project_name": "Free Project 4",
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False
        }
        response = client.post("/api/projects/", json=project_data)
        assert response.status_code == 403
        assert "Free accounts can only create up to 3 projects" in response.json()["detail"]
        assert "Professional" in response.json()["detail"]
        
        # Step 4: Try to create project with a private repo while at project
        # limit - the project count check should still fail (private repos
        # themselves are no longer gated for Free).
        project_data = {
            "github_user": "journeyuser",
            "project_name": "Private Project",
            "selected_repos": ["private:test/private-repo"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False
        }
        response = client.post("/api/projects/", json=project_data)
        assert response.status_code == 403
        assert "Free accounts can only create up to 3 projects" in response.json()["detail"]

        # Step 5: Delete one project and confirm a Free user CAN now create
        # a project that targets a private repo (private repos are part of
        # the core product on every tier).
        projects = client.get("/api/projects/", params={"github_user": "journeyuser"}).json()
        if len(projects) == 3:
            response = client.delete(f"/api/projects/{projects[2]['project_name']}?github_user=journeyuser")
            assert response.status_code in [200, 204]

        project_data = {
            "github_user": "journeyuser",
            "project_name": "Private Project",
            "selected_repos": ["private:test/private-repo"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False
        }
        response = client.post("/api/projects/", json=project_data)
        assert response.status_code == 200
        assert response.json()["message"] == "✅ Project saved successfully!"
        
        # Step 6: Upgrade to professional
        headers = get_basic_auth_header("admin", "admin123")
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "professional"}
        )
        assert response.status_code == 200
        
        # Step 7: Now can create more projects
        # Get current project count
        projects = client.get("/api/projects/", params={"github_user": "journeyuser"}).json()
        current_count = len(projects)
        
        for i in range(4, 8):  # Create projects 4-7
            project_data = {
                "github_user": "journeyuser",
                "project_name": f"Pro Project {i}",
                "selected_repos": ["test/repo1"],
                "workflows": [],
                "rxworkflows": [],
                "branch_regex": "",
                "branch_option": "default",
                "reusable_workflows_enabled": False
            }
            response = client.post("/api/projects/", json=project_data)
            assert response.status_code == 200
        
        # Step 8: Now can create project with private repo
        project_data = {
            "github_user": "journeyuser",
            "project_name": "Private Project Pro",
            "selected_repos": ["private:test/private-repo"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False
        }
        response = client.post("/api/projects/", json=project_data)
        assert response.status_code == 200
        
        # Verify final state: should have expected number of projects
        response = client.get("/api/projects/", params={"github_user": "journeyuser"})
        assert response.status_code == 200
        projects = response.json()
        # Should have at least 7 projects:
        # - 2-3 from free tier (may have deleted 1 in step 5)
        # - 4 from step 7 (Pro Project 4-7)
        # - 1 from step 8 (Private Project Pro)
        assert len(projects) >= 7
        assert len(projects) <= 8  # Maximum if no deletions occurred
        
        # Verify professional account type
        assert all(p.get('account_type') == 'professional' for p in projects if 'account_type' in p)
    
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_professional_user_can_mix_public_and_private_repos(self, setup_database, test_db):
        """Test that professional users can create projects with both public and private repos"""
        # Create professional user
        user = Account(
            github_user="mixeduser",
            github_email="mixed@example.com",
            account_type="professional",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Create project with mix of public and private repos
        project_data = {
            "github_user": "mixeduser",
            "project_name": "Mixed Repo Project",
            "selected_repos": [
                "test/public-repo1",
                "private:test/private-repo1",
                "test/public-repo2",
                "private:test/private-repo2"
            ],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False
        }
        
        response = client.post("/api/projects/", json=project_data)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "✅ Project saved successfully!"
    
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    @patch('github_secrets.count_project_secrets')
    @pytest.mark.asyncio
    async def test_professional_secrets_limit_enforcement(self, mock_count, setup_database, test_db):
        """Test that professional users have 10 secret limit enforced"""
        mock_count.return_value = 9  # Already have 9 secrets
        
        # Create professional user and project
        user = Account(
            github_user="secretuser",
            github_email="secret@example.com",
            account_type="professional",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user)
        test_db.commit()
        
        project = Project(
            project_name="Secret Project",
            project_code="SEC1",
            user_id=user.user_id
        )
        test_db.add(project)
        test_db.commit()
        
        # Try to add 2 secrets (would exceed limit of 10)
        secrets = [
            {"secret_key": "SECRET10", "secret_value": "value10"},
            {"secret_key": "SECRET11", "secret_value": "value11"}
        ]
        
        result = await _validate_account_limits("secretuser", "Secret Project", secrets, ["test/repo"], test_db)
        
        assert result is not None
        assert result["status"] == 403
        assert "10 secrets per project" in result["error"]
        assert "Enterprise" in result["error"]


class TestMultipleProfessionalUsers:
    """Test scenarios with multiple professional tier users"""
    
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_multiple_professional_users_independent_limits(self, setup_database, test_db):
        """Test that multiple professional users have independent project limits"""
        # Create two professional users
        user1 = Account(
            github_user="prouser1",
            github_email="pro1@example.com",
            account_type="professional",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        user2 = Account(
            github_user="prouser2",
            github_email="pro2@example.com",
            account_type="professional",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user1)
        test_db.add(user2)
        test_db.commit()
        
        # User1 creates 10 projects (at limit)
        for i in range(10):
            project_data = {
                "github_user": "prouser1",
                "project_name": f"User1 Project {i+1}",
                "selected_repos": ["test/repo1"],
                "workflows": [],
                "rxworkflows": [],
                "branch_regex": "",
                "branch_option": "default",
                "reusable_workflows_enabled": False
            }
            response = client.post("/api/projects/", json=project_data)
            assert response.status_code == 200
        
        # User1 can't create more
        project_data = {
            "github_user": "prouser1",
            "project_name": "User1 Project 11",
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False
        }
        response = client.post("/api/projects/", json=project_data)
        assert response.status_code == 403
        
        # User2 can still create projects (independent limit)
        for i in range(5):
            project_data = {
                "github_user": "prouser2",
                "project_name": f"User2 Project {i+1}",
                "selected_repos": ["test/repo1"],
                "workflows": [],
                "rxworkflows": [],
                "branch_regex": "",
                "branch_option": "default",
                "reusable_workflows_enabled": False
            }
            response = client.post("/api/projects/", json=project_data)
            assert response.status_code == 200


class TestEdgeCases:
    """Test edge cases for professional tier"""
    
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_professional_user_at_exactly_10_projects(self, setup_database, test_db):
        """Test behavior when professional user has exactly 10 projects"""
        user = Account(
            github_user="edgeuser",
            github_email="edge@example.com",
            account_type="professional",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Create exactly 10 projects
        for i in range(10):
            project_data = {
                "github_user": "edgeuser",
                "project_name": f"Edge Project {i+1}",
                "selected_repos": ["test/repo1"],
                "workflows": [],
                "rxworkflows": [],
                "branch_regex": "",
                "branch_option": "default",
                "reusable_workflows_enabled": False
            }
            response = client.post("/api/projects/", json=project_data)
            assert response.status_code == 200
        
        # Verify can get all projects
        response = client.get("/api/projects/", params={"github_user": "edgeuser"})
        assert response.status_code == 200
        projects = response.json()
        assert len(projects) == 10
        
        # 11th project should fail
        project_data = {
            "github_user": "edgeuser",
            "project_name": "Edge Project 11",
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False
        }
        response = client.post("/api/projects/", json=project_data)
        assert response.status_code == 403
        assert "Professional accounts can create up to 10 projects" in response.json()["detail"]
    
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_upgrading_user_with_existing_projects_above_new_tier_limit(self, setup_database, test_db):
        """Test edge case: downgrading user who already has more projects than new tier allows"""
        # Create enterprise user with 15 projects
        user = Account(
            github_user="downgradeuser",
            github_email="downgrade@example.com",
            account_type="enterprise",
            github_account_type="Organization",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Create 15 projects
        for i in range(15):
            project = Project(
                project_name=f"Enterprise Project {i+1}",
                project_code=f"ENT{i+1}",
                user_id=user.user_id
            )
            test_db.add(project)
        test_db.commit()
        
        # Downgrade to professional (limit 10)
        headers = get_basic_auth_header("admin", "admin123")
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "professional"}
        )
        assert response.status_code == 200
        
        # User still has 15 projects (no deletion)
        response = client.get("/api/projects/", params={"github_user": "downgradeuser"})
        assert response.status_code == 200
        projects = response.json()
        assert len(projects) == 15
        
        # But can't create new projects (over limit)
        project_data = {
            "github_user": "downgradeuser",
            "project_name": "New Project",
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False
        }
        response = client.post("/api/projects/", json=project_data)
        assert response.status_code == 403
        assert "Professional accounts can create up to 10 projects" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
