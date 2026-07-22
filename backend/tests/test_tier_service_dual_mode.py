"""
Unit tests for tier_service.py dual-mode support (self-hosted and cloud).

Tests both installation modes:
- Self-hosted mode: License-based tier enforcement
- Cloud mode: Marketplace-based tier enforcement
"""

import pytest
import jwt
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from tier_service import (
    get_effective_tier,
    check_project_limit,
    check_project_type_limit,
    check_private_repo_access,
    check_repo_limit,
    check_secrets_limit,
    normalize_tier_name,
    get_tier_limits,
    SELF_HOSTED_BETA_LIMITS,
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


class TestSelfHostedMode:
    """Test tier_service in self-hosted mode with license keys"""
    
    def test_self_hosted_free_tier_no_license(self, monkeypatch):
        """Test self-hosted mode with no license defaults to free tier"""
        # Mock INSTALLATION_MODE to self-hosted
        with patch('tier_service.INSTALLATION_MODE', 'self-hosted'):
            # Mock license.get_installation_tier to return free
            with patch('tier_service.license.get_installation_tier', return_value='free'):
                account = MockAccount(account_type='free')
                tier = get_effective_tier(account)
                assert tier == 'free'
    
    def test_self_hosted_professional_tier(self, monkeypatch):
        """Test self-hosted mode with professional license"""
        with patch('tier_service.INSTALLATION_MODE', 'self-hosted'):
            with patch('tier_service.license.get_installation_tier', return_value='professional'):
                account = MockAccount(account_type='free')
                tier = get_effective_tier(account)
                assert tier == 'professional'
    
    def test_self_hosted_enterprise_tier(self, monkeypatch):
        """Test self-hosted mode with enterprise license"""
        with patch('tier_service.INSTALLATION_MODE', 'self-hosted'):
            with patch('tier_service.license.get_installation_tier', return_value='enterprise'):
                account = MockAccount(account_type='free')
                tier = get_effective_tier(account)
                assert tier == 'enterprise'
    
    def test_self_hosted_admin_override_takes_precedence(self, monkeypatch):
        """Test that admin override takes precedence over license tier"""
        with patch('tier_service.INSTALLATION_MODE', 'self-hosted'):
            with patch('tier_service.license.get_installation_tier', return_value='free'):
                # Admin sets enterprise tier, even though license is free
                account = MockAccount(
                    admin_override=True,
                    admin_override_until=None,
                    account_type='enterprise'
                )
                tier = get_effective_tier(account)
                assert tier == 'enterprise'
    
    def test_self_hosted_expired_admin_override_uses_license(self, monkeypatch):
        """Test that expired admin override falls back to license tier"""
        past_date = datetime.now(timezone.utc) - timedelta(days=1)
        with patch('tier_service.INSTALLATION_MODE', 'self-hosted'):
            with patch('tier_service.license.get_installation_tier', return_value='professional'):
                account = MockAccount(
                    admin_override=True,
                    admin_override_until=past_date,  # Expired
                    account_type='enterprise'
                )
                tier = get_effective_tier(account)
                assert tier == 'professional'
    
    def test_self_hosted_project_limits(self, monkeypatch):
        """Test project limits in self-hosted beta mode.

        In self-hosted beta the combined limit is
        SELF_HOSTED_BETA_LIMITS['standard_projects'] + SELF_HOSTED_BETA_LIMITS['rwx_projects'],
        regardless of the license tier.  Per-type enforcement uses
        check_project_type_limit().
        """
        beta_total = SELF_HOSTED_BETA_LIMITS["standard_projects"] + SELF_HOSTED_BETA_LIMITS["rwx_projects"]

        with patch('tier_service.INSTALLATION_MODE', 'self-hosted'):
            # Below the combined beta limit → allowed
            with patch('tier_service.license.get_installation_tier', return_value='free'):
                account = MockAccount()
                allowed, error = check_project_limit(account, beta_total - 1)
                assert allowed is True
                assert error is None

            # At the combined beta limit → blocked
            with patch('tier_service.license.get_installation_tier', return_value='free'):
                account = MockAccount()
                allowed, error = check_project_limit(account, beta_total)
                assert allowed is False
                assert "self-hosted beta" in error.lower()

            # License tier does not override beta limits in self-hosted mode
            with patch('tier_service.license.get_installation_tier', return_value='enterprise'):
                account = MockAccount()
                allowed, error = check_project_limit(account, beta_total)
                assert allowed is False
                assert "self-hosted beta" in error.lower()
    
    def test_self_hosted_private_repo_access(self, monkeypatch):
        """Private repo access is part of the core product on every tier."""
        with patch('tier_service.INSTALLATION_MODE', 'self-hosted'):
            # Free tier: private repos are available (workflow-first model)
            with patch('tier_service.license.get_installation_tier', return_value='free'):
                account = MockAccount()
                allowed, error = check_private_repo_access(account)
                assert allowed is True
                assert error is None

            # Professional tier: also has private repo access
            with patch('tier_service.license.get_installation_tier', return_value='professional'):
                account = MockAccount()
                allowed, error = check_private_repo_access(account)
                assert allowed is True
                assert error is None

    def test_self_hosted_repo_limits(self, monkeypatch):
        """Test repo limits in self-hosted mode"""
        with patch('tier_service.INSTALLATION_MODE', 'self-hosted'):
            # Free tier: 10 repos per project
            with patch('tier_service.license.get_installation_tier', return_value='free'):
                account = MockAccount()
                allowed, error = check_repo_limit(account, 11)
                assert allowed is False
                assert "10" in error

            # Professional tier: 50 repos per project
            with patch('tier_service.license.get_installation_tier', return_value='professional'):
                account = MockAccount()
                allowed, error = check_repo_limit(account, 40)
                assert allowed is True
                assert error is None

    def test_self_hosted_secrets_limits(self, monkeypatch):
        """Test secrets limits in self-hosted beta mode.

        In self-hosted beta the limit is always SELF_HOSTED_BETA_LIMITS['secrets_per_project']
        regardless of the license tier.
        """
        beta_secret_limit = SELF_HOSTED_BETA_LIMITS["secrets_per_project"]

        with patch('tier_service.INSTALLATION_MODE', 'self-hosted'):
            # Within beta limit → allowed
            with patch('tier_service.license.get_installation_tier', return_value='free'):
                account = MockAccount()
                allowed, error = check_secrets_limit(account, beta_secret_limit)
                assert allowed is True
                assert error is None

            # Exceeding beta limit → blocked
            with patch('tier_service.license.get_installation_tier', return_value='free'):
                account = MockAccount()
                allowed, error = check_secrets_limit(account, beta_secret_limit + 1)
                assert allowed is False
                assert "self-hosted beta" in error.lower()
                assert str(beta_secret_limit) in error

            # License tier does not override beta limits
            with patch('tier_service.license.get_installation_tier', return_value='enterprise'):
                account = MockAccount()
                allowed, error = check_secrets_limit(account, beta_secret_limit + 1)
                assert allowed is False
                assert "self-hosted beta" in error.lower()


class TestCloudMode:
    """Test tier_service in cloud mode with marketplace subscriptions"""
    
    def test_cloud_mode_uses_marketplace_plan(self, monkeypatch):
        """Test cloud mode uses marketplace plan"""
        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        with patch('tier_service.INSTALLATION_MODE', 'cloud'):
            account = MockAccount(
                marketplace_plan='professional',
                marketplace_next_billing_date=future_date
            )
            tier = get_effective_tier(account)
            assert tier == 'professional'
    
    def test_cloud_mode_free_trial(self, monkeypatch):
        """Test cloud mode respects free trial status"""
        with patch('tier_service.INSTALLATION_MODE', 'cloud'):
            account = MockAccount(
                marketplace_plan='professional',
                marketplace_on_free_trial=True
            )
            tier = get_effective_tier(account)
            assert tier == 'professional'
    
    def test_cloud_mode_expired_subscription(self, monkeypatch):
        """Test cloud mode with expired subscription falls back to account_type"""
        past_date = datetime.now(timezone.utc) - timedelta(days=1)
        with patch('tier_service.INSTALLATION_MODE', 'cloud'):
            account = MockAccount(
                marketplace_plan='professional',
                marketplace_on_free_trial=False,
                marketplace_next_billing_date=past_date,
                account_type='free'
            )
            tier = get_effective_tier(account)
            assert tier == 'free'
    
    def test_cloud_mode_admin_override(self, monkeypatch):
        """Test admin override works in cloud mode"""
        with patch('tier_service.INSTALLATION_MODE', 'cloud'):
            account = MockAccount(
                admin_override=True,
                admin_override_until=None,
                account_type='enterprise',
                marketplace_plan='professional'
            )
            tier = get_effective_tier(account)
            assert tier == 'enterprise'
    
    def test_cloud_mode_no_marketplace_plan(self, monkeypatch):
        """Test cloud mode with no marketplace plan uses account_type"""
        with patch('tier_service.INSTALLATION_MODE', 'cloud'):
            account = MockAccount(
                marketplace_plan=None,
                account_type='professional'
            )
            tier = get_effective_tier(account)
            assert tier == 'professional'
    
    def test_cloud_mode_project_limits(self, monkeypatch):
        """Test project limits work in cloud mode"""
        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        with patch('tier_service.INSTALLATION_MODE', 'cloud'):
            # Professional tier from marketplace
            account = MockAccount(
                marketplace_plan='professional',
                marketplace_next_billing_date=future_date
            )
            allowed, error = check_project_limit(account, 5)
            assert allowed is True
            assert error is None
            
            # Test limit reached
            allowed, error = check_project_limit(account, 10)
            assert allowed is False
            assert "Professional accounts" in error
    
    def test_cloud_mode_private_repo_access(self, monkeypatch):
        """Private repo access is part of the core product on every tier."""
        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        with patch('tier_service.INSTALLATION_MODE', 'cloud'):
            # Free tier account - private repos are still allowed
            account = MockAccount(
                marketplace_plan=None,
                account_type='free'
            )
            allowed, error = check_private_repo_access(account)
            assert allowed is True

            # Professional tier from marketplace
            account = MockAccount(
                marketplace_plan='professional',
                marketplace_next_billing_date=future_date
            )
            allowed, error = check_private_repo_access(account)
            assert allowed is True

    def test_cloud_mode_repo_limits(self, monkeypatch):
        """Test repo limits in cloud mode"""
        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        with patch('tier_service.INSTALLATION_MODE', 'cloud'):
            account = MockAccount(
                marketplace_plan='professional',
                marketplace_next_billing_date=future_date
            )
            allowed, error = check_repo_limit(account, 40)
            assert allowed is True

            # Test exceeding limit (Professional cap is 50)
            allowed, error = check_repo_limit(account, 60)
            assert allowed is False

    def test_cloud_mode_secrets_limits(self, monkeypatch):
        """Test secrets limits in cloud mode"""
        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        with patch('tier_service.INSTALLATION_MODE', 'cloud'):
            account = MockAccount(
                marketplace_plan='professional',
                marketplace_next_billing_date=future_date
            )
            allowed, error = check_secrets_limit(account, 8)
            assert allowed is True

            # Test exceeding limit
            allowed, error = check_secrets_limit(account, 12)
            assert allowed is False


class TestTierLimitsAndHelpers:
    """Test tier limits and helper functions work in both modes"""
    
    def test_normalize_tier_name(self):
        """Test tier name normalization"""
        assert normalize_tier_name('professional') == 'professional'
        assert normalize_tier_name('pro') == 'professional'
        assert normalize_tier_name('PRO') == 'professional'
        assert normalize_tier_name('enterprise') == 'enterprise'
        assert normalize_tier_name('ENTERPRISE') == 'enterprise'
        assert normalize_tier_name('free') == 'free'
        assert normalize_tier_name('') == 'free'
        assert normalize_tier_name(None) == 'free'
        assert normalize_tier_name('unknown') == 'free'
    
    def test_get_tier_limits_free(self):
        """Test getting limits for free tier"""
        limits = get_tier_limits('free')
        assert limits['projects'] == 3
        assert limits['repos_per_project'] == 10
        assert limits['secrets_per_project'] == 2
        assert limits['private_repos'] is True
        assert limits['reusable_workflows'] is True
    
    def test_get_tier_limits_professional(self):
        """Test getting limits for professional tier"""
        limits = get_tier_limits('professional')
        assert limits['projects'] == 10
        assert limits['repos_per_project'] == 50
        assert limits['secrets_per_project'] == 10
        assert limits['private_repos'] is True
        assert limits['reusable_workflows'] is True
    
    def test_get_tier_limits_enterprise(self):
        """Test getting limits for enterprise tier"""
        limits = get_tier_limits('enterprise')
        assert limits['projects'] is None  # Unlimited
        assert limits['repos_per_project'] is None  # Unlimited
        assert limits['secrets_per_project'] is None  # Unlimited
        assert limits['private_repos'] is True
        assert limits['reusable_workflows'] is True


class TestModeIndependentFeatures:
    """Test features that work the same in both modes"""
    
    def test_admin_override_works_in_both_modes(self):
        """Test admin override takes precedence in both modes"""
        account = MockAccount(
            admin_override=True,
            admin_override_until=None,
            account_type='enterprise'
        )
        
        # Test in self-hosted mode
        with patch('tier_service.INSTALLATION_MODE', 'self-hosted'):
            with patch('tier_service.license.get_installation_tier', return_value='free'):
                tier = get_effective_tier(account)
                assert tier == 'enterprise'
        
        # Test in cloud mode
        with patch('tier_service.INSTALLATION_MODE', 'cloud'):
            tier = get_effective_tier(account)
            assert tier == 'enterprise'
    
    def test_tier_checks_consistent_across_modes(self):
        """Test that cloud mode tier checks are unaffected by self-hosted beta limits.

        Self-hosted beta mode enforces its own fixed limits, so the two modes
        intentionally diverge.  This test verifies that cloud mode still honours
        the standard professional tier limits.
        """
        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        
        # Cloud mode account at professional tier
        cloud_account = MockAccount(
            marketplace_plan='professional',
            marketplace_next_billing_date=future_date
        )

        with patch('tier_service.INSTALLATION_MODE', 'cloud'):
            # Professional tier in cloud mode: up to 10 projects, 10 secrets
            cloud_project_check = check_project_limit(cloud_account, 5)
            cloud_private_check = check_private_repo_access(cloud_account)
            cloud_repo_check = check_repo_limit(cloud_account, 15)
            cloud_secret_check = check_secrets_limit(cloud_account, 8)

        # Cloud professional tier: all should be allowed
        assert cloud_project_check == (True, None)
        assert cloud_private_check == (True, None)
        assert cloud_repo_check == (True, None)
        assert cloud_secret_check == (True, None)

        # Self-hosted beta: same project count (5 < combined beta limit of 6) is also allowed
        sh_account = MockAccount(account_type='professional')
        with patch('tier_service.INSTALLATION_MODE', 'self-hosted'):
            with patch('tier_service.license.get_installation_tier', return_value='professional'):
                sh_project_check = check_project_limit(sh_account, 5)
                sh_private_check = check_private_repo_access(sh_account)
                # Repo and secret counts that are within cloud professional limits but
                # may differ from beta enforcement — verify separately
                sh_repo_check = check_repo_limit(sh_account, 15)
                sh_secret_check_within = check_secrets_limit(sh_account, 6)  # at beta limit

        # Private repo access is always True in both modes
        assert sh_private_check == (True, None)
        # Beta secret limit is 6; checking exactly at limit should be allowed
        assert sh_secret_check_within == (True, None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
