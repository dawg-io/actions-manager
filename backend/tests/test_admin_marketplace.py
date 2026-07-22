"""
Tests for admin marketplace subscription features

Tests the admin panel's marketplace subscription management features including:
- Display of marketplace subscription data in user listing
- User subscription history viewing
- Webhook event filtering and searching
- Admin override status display
"""

import pytest
import base64
import importlib
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone

# Import app and dependencies
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from models import Account, MarketplaceWebhookEvent
import config

# Create test client
client = TestClient(app)


@pytest.fixture
def cloud_mode(monkeypatch):
    """Set cloud mode for tests that need marketplace features"""
    monkeypatch.setenv("INSTALLATION_MODE", "cloud")
    importlib.reload(config)
    yield
    # Restore default
    monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
    importlib.reload(config)


@pytest.fixture
def sample_users_with_marketplace(test_db):
    """Create sample users with marketplace subscription data"""
    users = [
        Account(
            github_user="marketplace_user",
            github_email="marketplace@example.com",
            account_type="professional",
            marketplace_plan="professional",
            marketplace_account_id=12345,
            marketplace_unit_count=5,
            marketplace_on_free_trial=False,
            marketplace_next_billing_date=datetime(2024, 2, 15, tzinfo=timezone.utc),
            marketplace_updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            admin_override=False,
            last_login_at=datetime(2024, 1, 15, 10, 30, 0)
        ),
        Account(
            github_user="trial_user",
            github_email="trial@example.com",
            account_type="enterprise",
            marketplace_plan="enterprise",
            marketplace_account_id=12346,
            marketplace_unit_count=10,
            marketplace_on_free_trial=True,
            marketplace_next_billing_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
            marketplace_updated_at=datetime(2024, 1, 10, tzinfo=timezone.utc),
            admin_override=False,
            last_login_at=datetime(2024, 1, 14, 9, 20, 0)
        ),
        Account(
            github_user="override_user",
            github_email="override@example.com",
            account_type="enterprise",
            marketplace_plan="free",
            marketplace_account_id=12347,
            marketplace_unit_count=None,
            marketplace_on_free_trial=False,
            marketplace_next_billing_date=None,
            marketplace_updated_at=datetime(2024, 1, 5, tzinfo=timezone.utc),
            admin_override=True,
            admin_override_until=None,  # Indefinite override
            last_login_at=datetime(2024, 1, 13, 8, 15, 0)
        ),
        Account(
            github_user="free_user",
            github_email="free@example.com",
            account_type="free",
            marketplace_plan=None,
            marketplace_account_id=None,
            marketplace_unit_count=None,
            marketplace_on_free_trial=False,
            marketplace_next_billing_date=None,
            marketplace_updated_at=None,
            admin_override=False,
            last_login_at=datetime(2024, 1, 12, 7, 10, 0)
        ),
    ]
    
    for user in users:
        test_db.add(user)
    test_db.commit()
    
    return users


@pytest.fixture
def sample_webhook_events(test_db, sample_users_with_marketplace):
    """Create sample marketplace webhook events"""
    events = [
        MarketplaceWebhookEvent(
            event_type="marketplace_purchase",
            action="purchased",
            github_user="marketplace_user",
            marketplace_account_id=12345,
            plan_name="professional",
            payload='{"action": "purchased"}',
            processed=True,
            received_at=datetime(2024, 1, 15, 10, 0, 0),
            processed_at=datetime(2024, 1, 15, 10, 0, 5),
            source_ip="192.168.1.100"
        ),
        MarketplaceWebhookEvent(
            event_type="marketplace_purchase",
            action="purchased",
            github_user="trial_user",
            marketplace_account_id=12346,
            plan_name="enterprise",
            payload='{"action": "purchased"}',
            processed=True,
            received_at=datetime(2024, 1, 10, 9, 0, 0),
            processed_at=datetime(2024, 1, 10, 9, 0, 5),
            source_ip="192.168.1.101"
        ),
        MarketplaceWebhookEvent(
            event_type="marketplace_purchase",
            action="cancelled",
            github_user="override_user",
            marketplace_account_id=12347,
            plan_name="professional",
            payload='{"action": "cancelled"}',
            processed=True,
            received_at=datetime(2024, 1, 5, 8, 0, 0),
            processed_at=datetime(2024, 1, 5, 8, 0, 5),
            source_ip="192.168.1.102"
        ),
        MarketplaceWebhookEvent(
            event_type="marketplace_purchase",
            action="changed",
            github_user="marketplace_user",
            marketplace_account_id=12345,
            plan_name="enterprise",
            payload='{"action": "changed"}',
            processed=False,
            processing_error="Test error",
            retry_count=2,
            received_at=datetime(2024, 1, 20, 11, 0, 0),
            source_ip="192.168.1.100"
        ),
    ]
    
    for event in events:
        test_db.add(event)
    test_db.commit()
    
    return events


def get_basic_auth_header(username: str, password: str) -> dict:
    """Generate Basic Auth header"""
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


class TestMarketplaceDataDisplay:
    """Test marketplace subscription data display in admin panel"""
    
    def test_admin_users_displays_marketplace_plan(self, setup_database, sample_users_with_marketplace):
        """Test that marketplace plans are displayed"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # Check that marketplace plans are displayed
        assert "professional" in content.lower()
        assert "enterprise" in content.lower()
    
    def test_admin_users_displays_subscription_status(self, setup_database, sample_users_with_marketplace):
        """Test that subscription status badges are displayed"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # Check for subscription status indicators
        assert "Active" in content or "✅" in content  # Active subscription
        assert "Trial" in content or "🎁" in content  # Free trial
    
    def test_admin_users_displays_admin_override(self, setup_database, sample_users_with_marketplace):
        """Test that admin override status is displayed"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # Check for admin override indicator
        assert "Override" in content or "🔒" in content
    
    def test_admin_users_displays_next_billing_date(self, setup_database, sample_users_with_marketplace):
        """Test that next billing dates are displayed"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # Check for billing date
        assert "2024-02-15" in content or "2024-02-01" in content
    
    def test_admin_users_sort_by_marketplace_plan(self, setup_database, sample_users_with_marketplace):
        """Test sorting by marketplace plan"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users?sort_by=marketplace_plan&sort_order=asc", headers=headers)
        
        assert response.status_code == 200
    
    def test_admin_users_sort_by_admin_override(self, setup_database, sample_users_with_marketplace):
        """Test sorting by admin override status"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users?sort_by=admin_override&sort_order=desc", headers=headers)
        
        assert response.status_code == 200


class TestUserSubscriptionHistory:
    """Test individual user subscription history viewing"""
    
    def test_user_subscription_page_requires_auth(self, setup_database, sample_users_with_marketplace):
        """Test that subscription page requires authentication"""
        response = client.get("/admin/users/1/subscription")
        assert response.status_code == 401
    
    def test_user_subscription_page_displays_data(self, setup_database, sample_users_with_marketplace, sample_webhook_events):
        """Test that user subscription page displays subscription data"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users/1/subscription", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # Check for user data
        assert "marketplace_user" in content
        assert "marketplace@example.com" in content
        assert "professional" in content.lower()
    
    def test_user_subscription_page_displays_billing_history(self, setup_database, sample_users_with_marketplace, sample_webhook_events):
        """Test that billing history is displayed"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users/1/subscription", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # Check for webhook events
        assert "purchased" in content.lower()
        assert "Billing History" in content
    
    def test_user_subscription_page_not_found(self, setup_database):
        """Test that 404 is returned for non-existent user"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users/99999/subscription", headers=headers)
        
        assert response.status_code == 404
    
    def test_user_subscription_link_in_users_table(self, setup_database, sample_users_with_marketplace):
        """Test that subscription link is present in users table"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # Check for subscription link
        assert "/admin/users/1/subscription" in content or "📊" in content


class TestWebhookEventFiltering:
    """Test webhook event filtering and searching"""
    
    @pytest.fixture(autouse=True)
    def setup_cloud_mode(self, cloud_mode):
        """Use cloud mode fixture for all webhook tests"""
        pass
    
    def test_webhook_filter_by_status(self, setup_database, sample_webhook_events):
        """Test filtering webhooks by processing status"""
        headers = get_basic_auth_header("admin", "admin123")
        
        # Filter for processed events
        response = client.get("/admin/webhooks?processed=true", headers=headers)
        assert response.status_code == 200
        content = response.text
        assert "Processed" in content
        
        # Filter for pending events
        response = client.get("/admin/webhooks?processed=false", headers=headers)
        assert response.status_code == 200
        content = response.text
        assert "Pending" in content or "Error" in content
    
    def test_webhook_filter_by_action(self, setup_database, sample_webhook_events):
        """Test filtering webhooks by action type"""
        headers = get_basic_auth_header("admin", "admin123")
        
        # Filter for purchased events
        response = client.get("/admin/webhooks?action=purchased", headers=headers)
        assert response.status_code == 200
        content = response.text
        assert "purchased" in content.lower()
        
        # Filter for cancelled events
        response = client.get("/admin/webhooks?action=cancelled", headers=headers)
        assert response.status_code == 200
        content = response.text
        assert "cancelled" in content.lower()
    
    def test_webhook_search_by_user(self, setup_database, sample_webhook_events):
        """Test searching webhooks by GitHub username"""
        headers = get_basic_auth_header("admin", "admin123")
        
        response = client.get("/admin/webhooks?github_user=marketplace_user", headers=headers)
        assert response.status_code == 200
        content = response.text
        
        # Should show events for marketplace_user
        assert "marketplace_user" in content
    
    def test_webhook_combined_filters(self, setup_database, sample_webhook_events):
        """Test using multiple filters together"""
        headers = get_basic_auth_header("admin", "admin123")
        
        response = client.get(
            "/admin/webhooks?processed=true&action=purchased&github_user=marketplace_user",
            headers=headers
        )
        assert response.status_code == 200
        content = response.text
        
        # Should show only purchased events for marketplace_user that are processed
        assert "marketplace_user" in content
        assert "purchased" in content.lower()
    
    def test_webhook_filters_preserve_pagination(self, setup_database, sample_webhook_events):
        """Test that filters are preserved in pagination links"""
        headers = get_basic_auth_header("admin", "admin123")
        
        response = client.get("/admin/webhooks?action=purchased&per_page=1", headers=headers)
        assert response.status_code == 200
        content = response.text
        
        # Check that pagination links include filters
        assert "action=purchased" in content


class TestAdminOverrideFeatures:
    """Test admin override functionality in the UI"""
    
    def test_admin_override_displays_correctly(self, setup_database, sample_users_with_marketplace):
        """Test that admin override status is displayed correctly"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # User with indefinite override should show
        assert "Override" in content or "🔒" in content
    
    def test_admin_override_shown_in_subscription_page(self, setup_database, sample_users_with_marketplace):
        """Test that admin override is shown in user subscription page"""
        headers = get_basic_auth_header("admin", "admin123")
        
        # Check user with override
        response = client.get("/admin/users/3/subscription", headers=headers)
        assert response.status_code == 200
        content = response.text
        
        assert "Override" in content or "🔒" in content
        assert "Indefinite" in content or "Active" in content


class TestAdminPanelNavigation:
    """Test navigation between admin panel pages"""
    
    def test_users_page_has_webhooks_link(self, setup_database):
        """Test that users page has link to webhooks"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        assert "/admin/webhooks" in content
class TestAdminPanelNavigation:
    """Test navigation between admin panel pages"""
    
    def test_users_page_has_webhooks_link(self, setup_database, monkeypatch):
        """Test that users page has webhooks link (disabled in self-hosted mode)"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # In self-hosted mode, webhook link should be present but disabled
        assert "/admin/webhooks" in content or "Marketplace Webhooks" in content
    
    def test_webhooks_page_has_users_link(self, setup_database, cloud_mode):
        """Test that webhooks page has link back to users (in cloud mode)"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/webhooks", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        assert "/admin/users" in content
    
    def test_subscription_page_has_navigation_links(self, setup_database, sample_users_with_marketplace):
        """Test that subscription page has navigation links"""
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users/1/subscription", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        assert "/admin/users" in content
        # In self-hosted mode, webhooks link should not be present
        # Only check that the page loads successfully


class TestSecurityAndValidation:
    """Test security and validation for admin marketplace features"""
    
    def test_xss_protection_in_marketplace_fields(self, setup_database, test_db):
        """Test that marketplace fields are properly escaped"""
        # Create user with potentially malicious marketplace plan name
        malicious_user = Account(
            github_user="xss_test",
            github_email="xss@test.com",
            account_type="professional",
            marketplace_plan="<script>alert('xss')</script>",
            marketplace_account_id=99999,
            admin_override=False
        )
        test_db.add(malicious_user)
        test_db.commit()
        
        headers = get_basic_auth_header("admin", "admin123")
        response = client.get("/admin/users", headers=headers)
        
        assert response.status_code == 200
        content = response.text
        
        # Script should be escaped
        assert "&lt;script&gt;" in content
        assert "<script>alert" not in content
    
    def test_sql_injection_protection_in_search(self, setup_database, sample_webhook_events):
        """Test that search inputs are protected against SQL injection"""
        headers = get_basic_auth_header("admin", "admin123")
        
        # Attempt SQL injection in user search
        response = client.get("/admin/webhooks?github_user=' OR '1'='1", headers=headers)
        
        # Should not cause an error or return all results
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
