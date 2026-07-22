"""
Unit tests for refactored tier_service.py helper functions.

Tests the helper functions introduced to reduce cognitive complexity:
- _is_admin_override_active
- _is_marketplace_subscription_active
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from tier_service import (
    _is_admin_override_active,
    _is_marketplace_subscription_active,
    get_effective_tier,
    normalize_tier_name
)


class MockAccount:
    """Mock Account object for testing"""
    def __init__(self, **kwargs):
        self.admin_override = kwargs.get('admin_override', False)
        self.admin_override_until = kwargs.get('admin_override_until', None)
        self.marketplace_plan = kwargs.get('marketplace_plan', None)
        self.marketplace_on_free_trial = kwargs.get('marketplace_on_free_trial', False)
        self.marketplace_next_billing_date = kwargs.get('marketplace_next_billing_date', None)
        self.account_type = kwargs.get('account_type', 'free')


class TestAdminOverrideActive:
    """Test _is_admin_override_active helper function"""
    
    def test_no_admin_override(self):
        """Test when admin_override is False"""
        account = MockAccount(admin_override=False)
        assert _is_admin_override_active(account) is False
    
    def test_indefinite_admin_override(self):
        """Test when admin_override is True with no expiration"""
        account = MockAccount(
            admin_override=True,
            admin_override_until=None
        )
        assert _is_admin_override_active(account) is True
    
    def test_active_temporary_override(self):
        """Test when admin_override is active with future expiration"""
        future_date = datetime.now(timezone.utc) + timedelta(days=7)
        account = MockAccount(
            admin_override=True,
            admin_override_until=future_date
        )
        assert _is_admin_override_active(account) is True
    
    def test_expired_temporary_override(self):
        """Test when admin_override has expired"""
        past_date = datetime.now(timezone.utc) - timedelta(days=7)
        account = MockAccount(
            admin_override=True,
            admin_override_until=past_date
        )
        assert _is_admin_override_active(account) is False
    
    def test_timezone_naive_override_date(self):
        """Test when override date is timezone naive"""
        future_date = datetime.now() + timedelta(days=7)
        account = MockAccount(
            admin_override=True,
            admin_override_until=future_date  # Naive datetime
        )
        assert _is_admin_override_active(account) is True


class TestMarketplaceSubscriptionActive:
    """Test _is_marketplace_subscription_active helper function"""
    
    def test_no_marketplace_plan(self):
        """Test when marketplace_plan is None"""
        account = MockAccount(marketplace_plan=None)
        assert _is_marketplace_subscription_active(account) is False
    
    def test_free_trial_active(self):
        """Test when on free trial"""
        account = MockAccount(
            marketplace_plan='professional',
            marketplace_on_free_trial=True
        )
        assert _is_marketplace_subscription_active(account) is True
    
    def test_active_subscription_with_future_billing(self):
        """Test when subscription has future billing date"""
        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        account = MockAccount(
            marketplace_plan='professional',
            marketplace_on_free_trial=False,
            marketplace_next_billing_date=future_date
        )
        assert _is_marketplace_subscription_active(account) is True
    
    def test_expired_subscription(self):
        """Test when subscription billing date has passed"""
        past_date = datetime.now(timezone.utc) - timedelta(days=1)
        account = MockAccount(
            marketplace_plan='professional',
            marketplace_on_free_trial=False,
            marketplace_next_billing_date=past_date
        )
        assert _is_marketplace_subscription_active(account) is False
    
    def test_no_billing_date_with_plan(self):
        """Test when plan exists but no billing date set"""
        account = MockAccount(
            marketplace_plan='professional',
            marketplace_on_free_trial=False,
            marketplace_next_billing_date=None
        )
        assert _is_marketplace_subscription_active(account) is True
    
    def test_timezone_naive_billing_date(self):
        """Test when billing date is timezone naive"""
        future_date = datetime.now() + timedelta(days=30)
        account = MockAccount(
            marketplace_plan='professional',
            marketplace_on_free_trial=False,
            marketplace_next_billing_date=future_date  # Naive datetime
        )
        assert _is_marketplace_subscription_active(account) is True


class TestGetEffectiveTierRefactored:
    """Test get_effective_tier with refactored implementation"""
    
    def test_admin_override_takes_precedence(self):
        """Test that admin override takes precedence over marketplace"""
        # Admin override works in both modes, so we don't need to mock the mode
        account = MockAccount(
            admin_override=True,
            admin_override_until=None,
            account_type='enterprise',
            marketplace_plan='professional',
            marketplace_on_free_trial=True
        )
        assert get_effective_tier(account) == 'enterprise'
    
    def test_marketplace_plan_without_override(self):
        """Test marketplace plan is used when no admin override (cloud mode)"""
        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        account = MockAccount(
            admin_override=False,
            account_type='free',
            marketplace_plan='professional',
            marketplace_next_billing_date=future_date
        )
        # Mock installation mode to cloud for marketplace-based tier logic
        with patch('tier_service.INSTALLATION_MODE', 'cloud'):
            assert get_effective_tier(account) == 'professional'
    
    def test_fallback_to_account_type(self):
        """Test fallback to account_type when no override or marketplace (cloud mode)"""
        account = MockAccount(
            admin_override=False,
            account_type='professional',
            marketplace_plan=None
        )
        # Mock installation mode to cloud for marketplace-based tier logic
        with patch('tier_service.INSTALLATION_MODE', 'cloud'):
            assert get_effective_tier(account) == 'professional'
    
    def test_expired_override_uses_marketplace(self):
        """Test that expired override falls through to marketplace (cloud mode)"""
        past_date = datetime.now(timezone.utc) - timedelta(days=1)
        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        account = MockAccount(
            admin_override=True,
            admin_override_until=past_date,  # Expired
            account_type='enterprise',
            marketplace_plan='professional',
            marketplace_next_billing_date=future_date
        )
        # Mock installation mode to cloud for marketplace-based tier logic
        with patch('tier_service.INSTALLATION_MODE', 'cloud'):
            assert get_effective_tier(account) == 'professional'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
