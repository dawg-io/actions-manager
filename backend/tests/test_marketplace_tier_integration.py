"""
Integration tests for Marketplace Subscription + Tier System

Tests the integration of marketplace subscription logic with the tier enforcement system:
- Tier enforcement respects marketplace subscription status
- Admin overrides prevent marketplace webhooks from changing tiers
- Upgrades/downgrades/cancellations work correctly
- Retention policies are respected
- Free trials and pending changes handled correctly
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import Account, Project, MarketplaceWebhookEvent
from tier_service import (
    get_effective_tier,
    check_project_limit,
    check_private_repo_access,
    set_admin_override,
    clear_admin_override,
    should_retain_data_on_downgrade
)
from marketplace_webhooks import update_account_from_webhook, store_webhook_event


# Test database setup
TEST_DATABASE_URL = "sqlite:///./test_marketplace_tier_integration.db"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestSessionLocal = sessionmaker(bind=test_engine)


@pytest.fixture
def test_db():
    """Create test database and tables"""
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=test_engine)


class TestMarketplaceTierIntegration:
    """Test marketplace subscription integration with tier system"""
    
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_marketplace_subscription_determines_tier(self, test_db):
        """Test that active marketplace subscription determines effective tier"""
        # Create user with free account_type but professional marketplace subscription
        user = Account(
            github_user="marketplaceuser",
            github_email="marketplace@example.com",
            account_type="free",
            marketplace_plan="professional",
            marketplace_on_free_trial=False,
            marketplace_next_billing_date=datetime.now(timezone.utc) + timedelta(days=30),
            admin_override=False
        )
        test_db.add(user)
        test_db.commit()
        
        # Effective tier should be professional (from marketplace)
        tier = get_effective_tier(user)
        assert tier == "professional"
        
        # Should be able to create up to 10 projects
        for i in range(9):
            project = Project(
                project_name=f"Project {i+1}",
                project_code=f"PRJ{i+1}",
                user_id=user.user_id
            )
            test_db.add(project)
        test_db.commit()
        
        # Check 10th project is allowed
        allowed, error = check_project_limit(user, 9)
        assert allowed is True
        assert error is None
        
        # Check 11th project is not allowed
        allowed, error = check_project_limit(user, 10)
        assert allowed is False
        assert "Professional accounts can create up to 10 projects" in error
    
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_free_trial_grants_access(self, test_db):
        """Test that free trial grants access to purchased tier"""
        # Create user on free trial
        user = Account(
            github_user="trialuser",
            github_email="trial@example.com",
            account_type="free",
            marketplace_plan="professional",
            marketplace_on_free_trial=True,
            marketplace_next_billing_date=datetime.now(timezone.utc) + timedelta(days=14),
            admin_override=False
        )
        test_db.add(user)
        test_db.commit()
        
        # Should have professional tier access during trial
        tier = get_effective_tier(user)
        assert tier == "professional"
        
        # Should be able to access private repos
        allowed, error = check_private_repo_access(user)
        assert allowed is True
        assert error is None
    
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_expired_subscription_falls_back_to_account_type(self, test_db):
        """Test that expired subscription falls back to account_type"""
        # Create user with expired marketplace subscription
        user = Account(
            github_user="expireduser",
            github_email="expired@example.com",
            account_type="free",
            marketplace_plan="professional",
            marketplace_on_free_trial=False,
            marketplace_next_billing_date=datetime.now(timezone.utc) - timedelta(days=1),  # Expired
            admin_override=False
        )
        test_db.add(user)
        test_db.commit()
        
        # Should fall back to free tier
        tier = get_effective_tier(user)
        assert tier == "free"
        
        # Should not be able to create 4th project
        allowed, error = check_project_limit(user, 3)
        assert allowed is False
        assert "Free accounts can only create up to 3 projects" in error


class TestAdminOverrides:
    """Test admin override functionality"""
    
    def test_admin_override_prevents_webhook_update(self, test_db):
        """Test that admin override prevents marketplace webhook from changing tier"""
        # Create user with admin override
        user = Account(
            github_user="adminuser",
            github_email="admin@example.com",
            account_type="professional",
            marketplace_plan=None,
            admin_override=True,
            admin_override_until=None  # Indefinite
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Simulate webhook cancellation
        payload = {
            "action": "cancelled",
            "marketplace_purchase": {
                "account": {
                    "id": 12345,
                    "login": "adminuser"
                },
                "plan": {
                    "name": "professional"
                }
            }
        }
        
        webhook_event = store_webhook_event(
            test_db, "marketplace_purchase", "cancelled", payload, None
        )
        
        # Process webhook
        success = update_account_from_webhook(test_db, webhook_event, payload)
        assert success is True
        
        # Verify account_type was NOT changed (admin override prevented it)
        test_db.refresh(user)
        assert user.account_type == "professional"
        
        # But marketplace metadata should be updated
        assert user.marketplace_plan is None
        assert user.marketplace_updated_at is not None
    
    def test_expired_admin_override_allows_webhook_update(self, test_db):
        """Test that expired admin override allows webhook to update tier"""
        # Create user with expired admin override
        user = Account(
            github_user="expiredadmin",
            github_email="expiredadmin@example.com",
            account_type="professional",
            marketplace_plan="professional",  # Add marketplace_plan
            admin_override=True,
            admin_override_until=datetime.now(timezone.utc) - timedelta(days=1)  # Expired
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Simulate webhook cancellation
        payload = {
            "action": "cancelled",
            "marketplace_purchase": {
                "account": {
                    "id": 12345,
                    "login": "expiredadmin"
                },
                "plan": {
                    "name": "professional"
                }
            }
        }
        
        webhook_event = store_webhook_event(
            test_db, "marketplace_purchase", "cancelled", payload, None
        )
        
        # Process webhook
        success = update_account_from_webhook(test_db, webhook_event, payload)
        assert success is True
        
        # Verify account_type WAS changed (override expired)
        test_db.refresh(user)
        assert user.account_type == "free"
        assert user.admin_override is False  # Should be cleared
    
    def test_set_admin_override_function(self, test_db):
        """Test set_admin_override helper function"""
        user = Account(
            github_user="testuser",
            github_email="test@example.com",
            account_type="free",
            admin_override=False
        )
        test_db.add(user)
        test_db.commit()
        
        # Set indefinite override
        set_admin_override(user, "enterprise", duration_days=None)
        assert user.account_type == "enterprise"
        assert user.admin_override is True
        assert user.admin_override_until is None
        
        # Set temporary override
        set_admin_override(user, "professional", duration_days=30)
        assert user.account_type == "professional"
        assert user.admin_override is True
        assert user.admin_override_until is not None
        assert user.admin_override_until > datetime.now(timezone.utc)
        
        # Clear override
        clear_admin_override(user)
        assert user.admin_override is False
        assert user.admin_override_until is None


class TestRetentionPolicy:
    """Test data retention policy for downgrades"""
    
    def test_retention_within_period(self, test_db):
        """Test that data should be retained within retention period"""
        # Create user recently downgraded
        user = Account(
            github_user="downgradeduser",
            github_email="downgraded@example.com",
            account_type="free",
            marketplace_updated_at=datetime.now(timezone.utc) - timedelta(days=15)  # 15 days ago
        )
        test_db.add(user)
        test_db.commit()
        
        # Data should be retained (within 30 day retention period)
        should_retain = should_retain_data_on_downgrade(user)
        assert should_retain is True
    
    def test_retention_expired(self, test_db):
        """Test that data cleanup allowed after retention period"""
        # Create user downgraded long ago
        user = Account(
            github_user="olddowngrade",
            github_email="old@example.com",
            account_type="free",
            marketplace_updated_at=datetime.now(timezone.utc) - timedelta(days=35)  # 35 days ago
        )
        test_db.add(user)
        test_db.commit()
        
        # Data cleanup allowed (past 30 day retention period)
        should_retain = should_retain_data_on_downgrade(user)
        assert should_retain is False


class TestWebhookUpgradesDowngrades:
    """Test webhook-driven upgrades and downgrades"""
    
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_webhook_upgrade_from_free_to_professional(self, test_db):
        """Test upgrading via webhook from free to professional"""
        user = Account(
            github_user="upgradeuser",
            github_email="upgrade@example.com",
            account_type="free",
            admin_override=False
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Before: user is free tier
        tier = get_effective_tier(user)
        assert tier == "free"
        
        # Simulate purchase webhook
        payload = {
            "action": "purchased",
            "marketplace_purchase": {
                "account": {
                    "id": 12345,
                    "login": "upgradeuser"
                },
                "plan": {
                    "name": "professional",
                    "price": 4000
                },
                "unit_count": 1,
                "on_free_trial": False,
                "next_billing_date": "2025-12-01T00:00:00Z"
            }
        }
        
        webhook_event = store_webhook_event(
            test_db, "marketplace_purchase", "purchased", payload, None
        )
        success = update_account_from_webhook(test_db, webhook_event, payload)
        assert success is True
        
        # After: user is professional tier
        test_db.refresh(user)
        tier = get_effective_tier(user)
        assert tier == "professional"
        assert user.marketplace_plan == "professional"
        assert user.account_type == "professional"
    
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_webhook_downgrade_from_professional_to_free(self, test_db):
        """Test downgrading via webhook from professional to free"""
        user = Account(
            github_user="downgradeuser",
            github_email="downgrade@example.com",
            account_type="professional",
            marketplace_plan="professional",
            admin_override=False
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Before: user is professional tier
        tier = get_effective_tier(user)
        assert tier == "professional"
        
        # Simulate cancellation webhook
        payload = {
            "action": "cancelled",
            "marketplace_purchase": {
                "account": {
                    "id": 12345,
                    "login": "downgradeuser"
                },
                "plan": {
                    "name": "professional"
                }
            }
        }
        
        webhook_event = store_webhook_event(
            test_db, "marketplace_purchase", "cancelled", payload, None
        )
        success = update_account_from_webhook(test_db, webhook_event, payload)
        assert success is True
        
        # After: user is free tier
        test_db.refresh(user)
        tier = get_effective_tier(user)
        assert tier == "free"
        assert user.marketplace_plan is None
        assert user.account_type == "free"
        
        # Verify retention policy kicks in
        assert user.marketplace_updated_at is not None
        should_retain = should_retain_data_on_downgrade(user)
        assert should_retain is True  # Recently downgraded


class TestPendingChanges:
    """Test pending change handling"""
    
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_pending_change_does_not_update_tier(self, test_db):
        """Test that pending_change action doesn't update tier"""
        user = Account(
            github_user="pendinguser",
            github_email="pending@example.com",
            account_type="professional",
            marketplace_plan="professional",
            admin_override=False
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        
        # Simulate pending change webhook
        payload = {
            "action": "pending_change",
            "effective_date": "2025-12-01T00:00:00Z",
            "marketplace_purchase": {
                "account": {
                    "id": 12345,
                    "login": "pendinguser"
                },
                "plan": {
                    "name": "enterprise",
                    "price": 20000
                }
            }
        }
        
        webhook_event = store_webhook_event(
            test_db, "marketplace_purchase", "pending_change", payload, None
        )
        success = update_account_from_webhook(test_db, webhook_event, payload)
        assert success is True
        
        # Verify tier NOT changed (pending)
        test_db.refresh(user)
        tier = get_effective_tier(user)
        assert tier == "professional"  # Still professional, not enterprise
        assert user.account_type == "professional"
        
        # Verify effective_date was stored
        assert webhook_event.effective_date is not None


class TestTierEnforcementConsistency:
    """Test that tier enforcement is consistent across features"""
    
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_free_trial_enforcement_across_features(self, test_db):
        """Test that free trial tier is enforced consistently"""
        user = Account(
            github_user="consistentuser",
            github_email="consistent@example.com",
            account_type="free",
            marketplace_plan="enterprise",
            marketplace_on_free_trial=True,
            marketplace_next_billing_date=datetime.now(timezone.utc) + timedelta(days=14),
            admin_override=False
        )
        test_db.add(user)
        test_db.commit()
        
        # Should have enterprise tier from trial
        tier = get_effective_tier(user)
        assert tier == "enterprise"
        
        # Check all features respect enterprise tier
        
        # Projects: unlimited
        allowed, error = check_project_limit(user, 100)
        assert allowed is True
        
        # Private repos: allowed
        allowed, error = check_private_repo_access(user)
        assert allowed is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
