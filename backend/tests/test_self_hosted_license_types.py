"""
Test cases for self-hosted license type handling.
Ensures new license types are properly recognized and displayed.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import Account
from auth import _manage_user_in_database, get_user_details, create_auth_session, set_request_user
from repos import _should_restrict_to_public_repos
from tier_service import get_effective_tier
from starlette.requests import Request as StarletteRequest


# Test database setup
TEST_DATABASE_URL = "sqlite:///./test_self_hosted_license_types.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def setup_test_db():
    """Create test database tables"""
    Base.metadata.create_all(bind=engine)


def teardown_test_db():
    """Clean up test database"""
    Base.metadata.drop_all(bind=engine)


def get_test_db():
    """Get test database session"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestSelfHostedLicenseTypes:
    """Test license type handling in self-hosted mode"""
    
    def setup_method(self):
        setup_test_db()
        self.db = next(get_test_db())

    def teardown_method(self):
        set_request_user(None)
        self.db.close()
        teardown_test_db()

    @patch('config.INSTALLATION_MODE', 'self-hosted')
    @patch('license.get_installation_tier')
    def test_self_hosted_professional_license(self, mock_get_tier):
        """Test that professional license tier is recognized in self-hosted mode"""
        mock_get_tier.return_value = "professional"
        
        # Simulate user login/creation with empty billing data (self-hosted has no marketplace)
        user = _manage_user_in_database(
            username="test_user",
            email="test@example.com",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            billing_data=[],  # No billing data in self-hosted mode
            db=self.db,
            client_ip="192.168.1.1"
        )
        
        # Verify account_type is set to professional from license
        assert user.account_type == "professional"
        
        # Verify user is not restricted
        restricted = _should_restrict_to_public_repos("test_user", self.db)
        assert restricted is False

    @patch('config.INSTALLATION_MODE', 'self-hosted')
    @patch('license.get_installation_tier')
    def test_self_hosted_enterprise_license(self, mock_get_tier):
        """Test that enterprise license tier is recognized in self-hosted mode"""
        mock_get_tier.return_value = "enterprise"
        
        # Simulate user login/creation
        user = _manage_user_in_database(
            username="enterprise_user",
            email="enterprise@example.com",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            billing_data=[],
            db=self.db,
            client_ip="192.168.1.1"
        )
        
        # Verify account_type is set to enterprise from license
        assert user.account_type == "enterprise"
        
        # Verify user has full access
        restricted = _should_restrict_to_public_repos("enterprise_user", self.db)
        assert restricted is False

    @patch('config.INSTALLATION_MODE', 'self-hosted')
    @patch('license.get_installation_tier')
    def test_self_hosted_free_license(self, mock_get_tier):
        """Test that free tier works correctly in self-hosted mode"""
        mock_get_tier.return_value = "free"
        
        # Simulate user login/creation
        user = _manage_user_in_database(
            username="free_user",
            email="free@example.com",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            billing_data=[],
            db=self.db,
            client_ip="192.168.1.1"
        )
        
        # Verify account_type is set to free from license
        assert user.account_type == "free"
        
        # Verify user is restricted
        restricted = _should_restrict_to_public_repos("free_user", self.db)
        assert restricted is True

    @patch('config.INSTALLATION_MODE', 'cloud')
    def test_cloud_mode_uses_billing_data(self):
        """Test that cloud mode still uses billing data from marketplace"""
        # Simulate user login with marketplace billing data
        billing_data = [{
            "plan": {"name": "professional"},
            "unit_count": 1
        }]
        
        user = _manage_user_in_database(
            username="cloud_user",
            email="cloud@example.com",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            billing_data=billing_data,
            db=self.db,
            client_ip="192.168.1.1"
        )
        
        # Verify account_type is set from billing data
        assert user.account_type == "professional"

    @patch('config.INSTALLATION_MODE', 'cloud')
    def test_cloud_mode_no_billing_defaults_to_unknown(self):
        """Test that cloud mode without billing data defaults to unknown (then normalizes to free)"""
        # Simulate user login with no billing data
        user = _manage_user_in_database(
            username="no_billing_user",
            email="no_billing@example.com",
            github_account_type="User",
            avatar_url="https://example.com/avatar.png",
            billing_data=[],
            db=self.db,
            client_ip="192.168.1.1"
        )
        
        # Verify account_type defaults to unknown in cloud mode without billing
        assert user.account_type == "unknown"

    @patch('tier_service.INSTALLATION_MODE', 'self-hosted')
    @patch('config.INSTALLATION_MODE', 'self-hosted')
    @patch('license.get_installation_tier')
    def test_effective_tier_in_self_hosted_mode(self, mock_get_tier):
        """Test that get_effective_tier returns license tier in self-hosted mode"""
        mock_get_tier.return_value = "professional"
        
        # Create a user (with any account_type)
        account = Account(
            github_user="tier_test_user",
            github_email="tier_test@example.com",
            account_type="free"  # This should be overridden by license
        )
        self.db.add(account)
        self.db.commit()
        
        # Get effective tier
        effective_tier = get_effective_tier(account)
        
        # Should return professional from license, not free from account_type
        assert effective_tier == "professional"

    @patch('tier_service.INSTALLATION_MODE', 'self-hosted')
    @patch('config.INSTALLATION_MODE', 'self-hosted')
    @patch('config.get_installation_mode', return_value='self-hosted')
    @patch('license.get_installation_tier')
    def test_user_api_returns_effective_tier(self, mock_get_tier, mock_get_mode):
        """Test that /api/user/{username} returns effective tier from tier_service"""
        mock_get_tier.return_value = "enterprise"
        
        # Create a user with free account_type
        account = Account(
            github_user="api_test_user",
            github_email="api_test@example.com",
            account_type="free"  # Stored type
        )
        self.db.add(account)
        self.db.commit()
        
        # Mock rate limiter
        with patch('rate_limiter.check_rate_limit') as mock_rate_limit:
            mock_rate_limit.return_value = (True, {
                "limit": 5000,
                "used": 100,
                "remaining": 4900,
                "percentage_used": 2.0,
                "should_warn": False,
                "reset_at": "2025-01-20T12:00:00Z"
            })
            
            # Call the API endpoint
            session_token = create_auth_session("api_test_user", self.db)
            scope = {
                "type": "http", "method": "GET", "path": "/api/user/api_test_user",
                "headers": [(b"authorization", ("Bearer " + session_token).encode())],
                "query_string": b"",
            }
            request = StarletteRequest(scope)
            result = get_user_details("api_test_user", request, self.db)
            
            # Should return enterprise from license, not free from database
            assert result["account_type"] == "enterprise"
            assert result["installation_mode"] == "self-hosted"
            assert result["github_user"] == "api_test_user"
            assert result["connected_github_account"] == "api_test_user"
            assert result["connected_github_account_type"] == "User"

    def test_user_api_normalizes_unknown_github_account_type(self):
        """Test that /api/user/{username} only returns supported GitHub account type values"""
        account = Account(
            github_user="unknown_github_type_user",
            github_email="unknown_type@example.com",
            account_type="free",
            github_account_type="Enterprise"
        )
        self.db.add(account)
        self.db.commit()

        with patch('rate_limiter.check_rate_limit') as mock_rate_limit:
            mock_rate_limit.return_value = (True, {
                "limit": 5000,
                "used": 100,
                "remaining": 4900,
                "percentage_used": 2.0,
                "should_warn": False,
                "reset_at": "2025-01-20T12:00:00Z"
            })

            session_token = create_auth_session("unknown_github_type_user", self.db)
            scope = {
                "type": "http", "method": "GET", "path": "/api/user/unknown_github_type_user",
                "headers": [(b"authorization", ("Bearer " + session_token).encode())],
                "query_string": b"",
            }
            request = StarletteRequest(scope)
            result = get_user_details("unknown_github_type_user", request, self.db)

            assert result["account_type"] == "free"
            assert result["github_account_type"] is None
            assert result["connected_github_account"] == "unknown_github_type_user"
            assert result["connected_github_account_type"] is None

    def test_user_api_returns_connected_github_account_when_available(self):
        """Test /api/user/{username} returns installation account separately from signed-in user"""
        account = Account(
            github_user="dawg-io",
            github_email="dawg-io@example.com",
            account_type="free",
            github_account_type="User",
            connected_github_account="whatsupdawg",
            connected_github_account_type="Organization"
        )
        self.db.add(account)
        self.db.commit()

        with patch('rate_limiter.check_rate_limit') as mock_rate_limit:
            mock_rate_limit.return_value = (True, {
                "limit": 5000,
                "used": 100,
                "remaining": 4900,
                "percentage_used": 2.0,
                "should_warn": False,
                "reset_at": "2025-01-20T12:00:00Z"
            })

            session_token = create_auth_session("dawg-io", self.db)
            scope = {
                "type": "http", "method": "GET", "path": "/api/user/dawg-io",
                "headers": [(b"authorization", ("Bearer " + session_token).encode())],
                "query_string": b"",
            }
            request = StarletteRequest(scope)
            result = get_user_details("dawg-io", request, self.db)

            assert result["github_user"] == "dawg-io"
            assert result["github_account_type"] == "User"
            assert result["connected_github_account"] == "whatsupdawg"
            assert result["connected_github_account_type"] == "Organization"


class TestLicenseTypeNormalization:
    """Test that new license types are properly normalized"""
    
    def setup_method(self):
        setup_test_db()
        self.db = next(get_test_db())

    def teardown_method(self):
        self.db.close()
        teardown_test_db()

    def test_pro_alias_normalized_to_professional(self):
        """Test that 'pro' is normalized to 'professional'"""
        from tier_service import normalize_tier_name
        
        assert normalize_tier_name("pro") == "professional"
        assert normalize_tier_name("Pro") == "professional"
        assert normalize_tier_name("PRO") == "professional"

    def test_professional_remains_professional(self):
        """Test that 'professional' stays as 'professional'"""
        from tier_service import normalize_tier_name
        
        assert normalize_tier_name("professional") == "professional"
        assert normalize_tier_name("Professional") == "professional"
        assert normalize_tier_name("PROFESSIONAL") == "professional"

    def test_enterprise_normalized(self):
        """Test that enterprise tier is properly handled"""
        from tier_service import normalize_tier_name
        
        assert normalize_tier_name("enterprise") == "enterprise"
        assert normalize_tier_name("Enterprise") == "enterprise"
        assert normalize_tier_name("ENTERPRISE") == "enterprise"

    def test_free_normalized(self):
        """Test that free tier is properly handled"""
        from tier_service import normalize_tier_name
        
        assert normalize_tier_name("free") == "free"
        assert normalize_tier_name("Free") == "free"
        assert normalize_tier_name("FREE") == "free"

    def test_unknown_normalized_to_free(self):
        """Test that unknown types default to free"""
        from tier_service import normalize_tier_name
        
        assert normalize_tier_name("unknown") == "free"
        assert normalize_tier_name("weird_type") == "free"
        assert normalize_tier_name("") == "free"
        assert normalize_tier_name(None) == "free"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
