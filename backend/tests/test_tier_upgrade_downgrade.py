"""
Test account tier upgrades and downgrades for professional tier.

This test suite validates:
1. Account upgrades (free -> professional -> enterprise)
2. Account downgrades (enterprise -> professional -> free)
3. Limit enforcement after tier changes
4. Edge cases and invalid transitions
"""

import pytest
import base64
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from database import Base
from models import Account, Project
from admin import get_db
from projects import get_db as projects_get_db

# Create test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_tier_upgrade_downgrade.db"
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
    # Set up database dependency override for this test
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


class TestAccountUpgrades:
    """Test account upgrade scenarios"""
    
    def test_upgrade_free_to_professional(self, setup_database, test_db):
        """Test upgrading from free to professional account"""
        # Create free user
        user = Account(
            github_user="freeuser",
            github_email="free@example.com",
            account_type="free",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Verify initial state
        assert user.account_type == "free"
        
        # Upgrade to professional
        headers = get_basic_auth_header("admin", "admin123")
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "professional"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user"]["account_type"] == "professional"
        
        # Verify database was updated
        test_db.refresh(user)
        assert user.account_type == "professional"
    
    def test_upgrade_professional_to_enterprise(self, setup_database, test_db):
        """Test upgrading from professional to enterprise account"""
        # Create professional user
        user = Account(
            github_user="prouser",
            github_email="pro@example.com",
            account_type="professional",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Verify initial state
        assert user.account_type == "professional"
        
        # Upgrade to enterprise
        headers = get_basic_auth_header("admin", "admin123")
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "enterprise"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user"]["account_type"] == "enterprise"
        
        # Verify database was updated
        test_db.refresh(user)
        assert user.account_type == "enterprise"
    
    def test_upgrade_free_to_enterprise(self, setup_database, test_db):
        """Test direct upgrade from free to enterprise account"""
        # Create free user
        user = Account(
            github_user="freeuser",
            github_email="free@example.com",
            account_type="free",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Direct upgrade to enterprise
        headers = get_basic_auth_header("admin", "admin123")
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "enterprise"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user"]["account_type"] == "enterprise"


class TestAccountDowngrades:
    """Test account downgrade scenarios"""
    
    def test_downgrade_enterprise_to_professional(self, setup_database, test_db):
        """Test downgrading from enterprise to professional account"""
        # Create enterprise user
        user = Account(
            github_user="enterpriseuser",
            github_email="enterprise@example.com",
            account_type="enterprise",
            github_account_type="Organization",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Downgrade to professional
        headers = get_basic_auth_header("admin", "admin123")
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "professional"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user"]["account_type"] == "professional"
        
        # Verify database was updated
        test_db.refresh(user)
        assert user.account_type == "professional"
    
    def test_downgrade_professional_to_free(self, setup_database, test_db):
        """Test downgrading from professional to free account"""
        # Create professional user
        user = Account(
            github_user="prouser",
            github_email="pro@example.com",
            account_type="professional",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Downgrade to free
        headers = get_basic_auth_header("admin", "admin123")
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "free"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user"]["account_type"] == "free"
        
        # Verify database was updated
        test_db.refresh(user)
        assert user.account_type == "free"
    
    def test_downgrade_enterprise_to_free(self, setup_database, test_db):
        """Test direct downgrade from enterprise to free account"""
        # Create enterprise user
        user = Account(
            github_user="enterpriseuser",
            github_email="enterprise@example.com",
            account_type="enterprise",
            github_account_type="Organization",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Direct downgrade to free
        headers = get_basic_auth_header("admin", "admin123")
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "free"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user"]["account_type"] == "free"


class TestLimitEnforcementAfterTierChange:
    """Test that limits are enforced correctly after tier changes"""
    
    def test_project_limit_enforced_after_downgrade_to_free(self, setup_database, test_db):
        """Test that project creation is blocked after downgrading to free with existing projects"""
        # Create professional user with 5 projects
        user = Account(
            github_user="prouser",
            github_email="pro@example.com",
            account_type="professional",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Create 5 projects
        for i in range(5):
            project = Project(
                project_name=f"Test Project {i+1}",
                project_code=f"TEST{i+1}",
                user_id=user.user_id
            )
            test_db.add(project)
        test_db.commit()
        
        # Downgrade to free
        headers = get_basic_auth_header("admin", "admin123")
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "free"}
        )
        assert response.status_code == 200
        
        # Try to create another project (should fail - free limit is 3)
        project_data = {
            "github_user": "prouser",
            "project_name": "Test Project 6",
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False
        }
        
        response = client.post("/api/projects/", json=project_data)
        assert response.status_code == 403
        data = response.json()
        assert "Free accounts can only create up to 3 projects" in data["detail"]
    
    def test_project_limit_relaxed_after_upgrade_to_professional(self, setup_database, test_db):
        """Test that project creation is allowed after upgrading to professional"""
        # Create free user with 3 projects (at free limit)
        user = Account(
            github_user="freeuser",
            github_email="free@example.com",
            account_type="free",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Create 3 projects (free limit)
        for i in range(3):
            project = Project(
                project_name=f"Test Project {i+1}",
                project_code=f"TEST{i+1}",
                user_id=user.user_id
            )
            test_db.add(project)
        test_db.commit()
        
        # Verify can't create more at free limit
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
        
        response = client.post("/api/projects/", json=project_data)
        assert response.status_code == 403
        
        # Upgrade to professional
        headers = get_basic_auth_header("admin", "admin123")
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "professional"}
        )
        assert response.status_code == 200
        
        # Now should be able to create more projects (up to 10)
        for i in range(4, 8):  # Create projects 4-7
            project_data = {
                "github_user": "freeuser",
                "project_name": f"Test Project {i}",
                "selected_repos": ["test/repo1"],
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
    
    def test_private_repo_access_available_on_free_tier(self, setup_database, test_db):
        """Private repos are part of the core product and available to free users."""
        # Create free user
        user = Account(
            github_user="freeuser",
            github_email="free@example.com",
            account_type="free",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        # Free user should be able to create a project with a private repo
        project_data = {
            "github_user": "freeuser",
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
        data = response.json()
        assert data["message"] == "✅ Project saved successfully!"

        # And the same project survives an upgrade to professional
        headers = get_basic_auth_header("admin", "admin123")
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "professional"}
        )
        assert response.status_code == 200


class TestContinuousUpgradeDowngrade:
    """Test multiple consecutive upgrades and downgrades"""
    
    def test_multiple_tier_changes(self, setup_database, test_db):
        """Test changing tiers multiple times"""
        # Create free user
        user = Account(
            github_user="testuser",
            github_email="test@example.com",
            account_type="free",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            last_login_at=datetime.now(),
            last_login_ip="127.0.0.1"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        headers = get_basic_auth_header("admin", "admin123")
        
        # Free -> Professional
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "professional"}
        )
        assert response.status_code == 200
        test_db.refresh(user)
        assert user.account_type == "professional"
        
        # Professional -> Enterprise
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "enterprise"}
        )
        assert response.status_code == 200
        test_db.refresh(user)
        assert user.account_type == "enterprise"
        
        # Enterprise -> Professional
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "professional"}
        )
        assert response.status_code == 200
        test_db.refresh(user)
        assert user.account_type == "professional"
        
        # Professional -> Free
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "free"}
        )
        assert response.status_code == 200
        test_db.refresh(user)
        assert user.account_type == "free"
        
        # Free -> Enterprise (direct upgrade)
        response = client.patch(
            f"/admin/users/{user.user_id}/account-type",
            headers=headers,
            json={"account_type": "enterprise"}
        )
        assert response.status_code == 200
        test_db.refresh(user)
        assert user.account_type == "enterprise"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
