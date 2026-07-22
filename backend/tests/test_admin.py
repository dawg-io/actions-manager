"""
Tests for admin module

Tests the admin users page functionality including:
- Basic Auth authentication
- User listing with pagination
- Security headers
- Login attempt logging
"""

import pytest
import base64
from fastapi.testclient import TestClient
from datetime import datetime

# Import app and dependencies
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from models import Account

# Create test client
client = TestClient(app)


@pytest.fixture
def sample_users(test_db):
    """Create sample users for testing"""
    users = [
        Account(
            github_user="user1",
            github_email="user1@example.com",
            account_type="enterprise",
            github_account_type="User",
            avatar_url="https://example.com/avatar1.jpg",
            last_login_at=datetime(2024, 1, 15, 10, 30, 0),
            last_login_ip="192.168.1.100"
        ),
        Account(
            github_user="user2",
            github_email="user2@example.com",
            account_type="professional",
            github_account_type="User",
            avatar_url="https://example.com/avatar2.jpg",
            last_login_at=datetime(2024, 1, 14, 9, 20, 0),
            last_login_ip="10.0.0.50"
        ),
        Account(
            github_user="user3",
            github_email="user3@example.com",
            account_type="unknown",
            github_account_type="Organization",
            avatar_url=None,
            last_login_at=None,
            last_login_ip=None
        ),
    ]
    
    for user in users:
        test_db.add(user)
    test_db.commit()
    
    return users


def get_basic_auth_header(username: str, password: str) -> dict:
    """Generate Basic Auth header"""
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


class TestAdminAuthentication:
    """Test admin authentication and security"""
    
    def test_admin_users_requires_auth(self, setup_database):
        """Test that /admin/users requires authentication"""
        response = client.get("/admin/users")
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers
    
    def test_admin_users_with_invalid_credentials(self, setup_database):
        """Test that invalid credentials are rejected"""
        headers = get_basic_auth_header("wrong", "credentials")
        response = client.get("/admin/users", headers=headers)
        assert response.status_code == 401
    
    def test_admin_users_with_valid_credentials(self, setup_database, sample_users):
        """Test that valid credentials allow access"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    def test_admin_security_headers(self, setup_database, sample_users):
        """Test that security headers are present"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        assert "Cache-Control" in response.headers
        assert "no-store" in response.headers["Cache-Control"]
        assert "X-Robots-Tag" in response.headers
        assert "noindex" in response.headers["X-Robots-Tag"]
        assert "X-Content-Type-Options" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "X-Frame-Options" in response.headers
        assert response.headers["X-Frame-Options"] == "DENY"


class TestAdminUserListing:
    """Test user listing functionality"""
    
    def test_admin_users_displays_users(self, setup_database, sample_users):
        """Test that users are displayed in the table"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # Check that user data is present
        assert "user1" in content
        assert "user1@example.com" in content
        assert "user2" in content
        assert "user2@example.com" in content
        assert "user3" in content
    
    def test_admin_users_displays_null_values(self, setup_database, sample_users):
        """Test that null values are displayed as em-dash"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # user3 has null login data
        assert "—" in content or "null-value" in content
    
    def test_admin_users_empty_database(self, setup_database):
        """Test admin page with no users"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        assert "No users found" in content
    
    def test_admin_users_displays_avatar(self, setup_database, sample_users):
        """Test that avatar URLs are displayed"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # Check that avatar images are present
        assert "https://example.com/avatar1.jpg" in content or "avatar" in content.lower()


class TestAdminPagination:
    """Test pagination functionality"""
    
    def test_admin_users_pagination_default(self, setup_database, sample_users):
        """Test default pagination"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # Should display page 1
        assert "Page 1" in content
    
    def test_admin_users_pagination_per_page(self, setup_database, sample_users):
        """Test custom per_page parameter"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users?per_page=1", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # With per_page=1 and 3 users, should have 3 pages
        assert "Page 1 of 3" in content or "Total Users" in content
    
    def test_admin_users_pagination_max_limit(self, setup_database, sample_users):
        """Test that per_page is limited to 200"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users?per_page=300", headers=headers)
        
        # Should not error, but limit to 200
        assert response.status_code == 200


class TestAdminSorting:
    """Test sorting functionality"""
    
    def test_admin_users_default_sort(self, setup_database, sample_users):
        """Test default sorting by last_login_at DESC"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # user1 logged in most recently, should appear first
        user1_pos = content.find("user1@example.com")
        user2_pos = content.find("user2@example.com")
        
        # Both should be found and user1 should come before user2
        assert user1_pos > 0
        assert user2_pos > 0
        assert user1_pos < user2_pos
    
    def test_admin_users_sort_by_user_id(self, setup_database, sample_users):
        """Test sorting by user_id"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users?sort_by=user_id&sort_order=asc", headers=headers)
        
        assert response.status_code == 200
    
    def test_admin_users_invalid_sort_column(self, setup_database, sample_users):
        """Test that invalid sort columns are handled gracefully"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users?sort_by=invalid_column", headers=headers)
        
        # Should not error, should fall back to default
        assert response.status_code == 200
    
    def test_admin_users_invalid_sort_order(self, setup_database, sample_users):
        """Test that invalid sort orders are handled gracefully"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users?sort_order=invalid", headers=headers)
        
        # Should not error, should fall back to default
        assert response.status_code == 200


class TestAdminStatistics:
    """Test statistics display"""
    
    def test_admin_users_displays_total_count(self, setup_database, sample_users):
        """Test that total user count is displayed"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # Should show 3 total users
        assert "3" in content
        assert "Total Users" in content


class TestAdminBadgeDisplay:
    """Test account type badge display"""
    
    def test_admin_users_account_type_badges(self, setup_database, sample_users):
        """Test that account types are displayed as badges"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # Should have badge CSS classes
        assert "badge" in content
        assert "enterprise" in content.lower()
        assert "pro" in content.lower()


class TestAdminXSSProtection:
    """Test XSS protection through HTML escaping"""
    
    def test_admin_users_escapes_html_in_usernames(self, setup_database, test_db):
        """Test that HTML in usernames is escaped"""
        # Create a user with HTML/script in username
        malicious_user = Account(
            github_user="<script>alert('xss')</script>",
            github_email="test@example.com",
            account_type="professional",
            github_account_type="User",
            avatar_url=None,
            last_login_at=None,
            last_login_ip=None
        )
        test_db.add(malicious_user)
        test_db.commit()
        
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # Script tag should be escaped, not executed
        assert "&lt;script&gt;" in content
        assert "<script>alert" not in content
    
    def test_admin_users_escapes_html_in_email(self, setup_database, test_db):
        """Test that HTML in email is escaped"""
        malicious_user = Account(
            github_user="testuser",
            github_email="<img src=x onerror=alert('xss')>@test.com",
            account_type="professional",
            github_account_type="User",
            avatar_url=None,
            last_login_at=None,
            last_login_ip=None
        )
        test_db.add(malicious_user)
        test_db.commit()
        
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # Image tag should be escaped
        assert "&lt;img" in content
        assert "<img src=x onerror=" not in content


class TestAccountTypeUpdate:
    """Test account type update endpoint"""
    
    def test_update_account_type_requires_auth(self, setup_database, sample_users):
        """Test that account type update requires authentication"""
        response = client.patch("/admin/users/1/account-type", json={"account_type": "enterprise"})
        assert response.status_code == 401
    
    def test_update_account_type_with_invalid_credentials(self, setup_database, sample_users):
        """Test that invalid credentials are rejected"""
        headers = get_basic_auth_header("wrong", "credentials")
        response = client.patch("/admin/users/1/account-type", headers=headers, json={"account_type": "enterprise"})
        assert response.status_code == 401
    
    def test_update_account_type_success(self, setup_database, sample_users, test_db):
        """Test successfully updating account type"""
        headers = get_basic_auth_header("admin", "admin123")
        
        # Get initial user
        user = test_db.query(Account).filter(Account.user_id == 1).first()
        initial_type = user.account_type
        
        # Update to different type
        new_type = "professional"
        response = client.patch(
            "/admin/users/1/account-type",
            headers=headers,
            json={"account_type": new_type}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == f"Account type updated successfully to '{new_type}' (admin override active)"
        assert data["user"]["account_type"] == new_type
        
        # Verify database was updated
        test_db.refresh(user)
        assert user.account_type == new_type
    
    def test_update_account_type_invalid_type(self, setup_database, sample_users):
        """Test that invalid account types are rejected"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.patch(
            "/admin/users/1/account-type",
            headers=headers,
            json={"account_type": "invalid_type"}
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_update_account_type_user_not_found(self, setup_database, sample_users):
        """Test updating non-existent user returns 404"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.patch(
            "/admin/users/99999/account-type",
            headers=headers,
            json={"account_type": "enterprise"}
        )
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
    
    def test_update_account_type_all_valid_types(self, setup_database, sample_users, test_db):
        """Test all valid account types can be set"""
        headers = get_basic_auth_header("admin", "admin123")
        valid_types = ["free", "professional", "enterprise"]
        
        user = test_db.query(Account).filter(Account.user_id == 1).first()
        
        for account_type in valid_types:
            response = client.patch(
                "/admin/users/1/account-type",
                headers=headers,
                json={"account_type": account_type}
            )
            
            assert response.status_code == 200
            test_db.refresh(user)
            assert user.account_type == account_type


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
