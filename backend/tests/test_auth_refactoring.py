"""
Tests for refactored auth module helper functions
Validates that the github_callback refactoring maintains correct functionality
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from auth import (
    _exchange_code_for_token,
    _fetch_user_info,
    _fetch_marketplace_data,
    _fetch_installation_account,
    _resolve_connected_github_account,
    _normalize_github_account_type,
    _manage_user_in_database
)


class TestAuthRefactoring:
    """Test cases for refactored auth helper functions"""

    @patch('auth.requests.post')
    @patch('auth.debug_log')
    def test_exchange_code_for_token_success(self, mock_debug, mock_post):
        """Test successful token exchange"""
        # Mock successful response
        mock_response = Mock()
        mock_response.json.return_value = {"access_token": "test_token_123"}
        mock_post.return_value = mock_response
        
        token = _exchange_code_for_token("test_code")
        
        assert token == "test_token_123"
        assert mock_post.called
        mock_debug.assert_any_call("✅ Access token retrieved")

    @patch('auth.requests.post')
    @patch('auth.debug_log')
    def test_exchange_code_for_token_failure(self, mock_debug, mock_post):
        """Test token exchange failure raises ValueError"""
        # Mock failed response (no access token)
        mock_response = Mock()
        mock_response.json.return_value = {"error": "bad_verification_code"}
        mock_post.return_value = mock_response
        
        with pytest.raises(ValueError, match="GitHub authentication failed"):
            _exchange_code_for_token("invalid_code")
        
        mock_debug.assert_any_call("❌ Error: Failed to retrieve access token")

    @patch('auth.requests.get')
    @patch('auth.debug_log')
    def test_fetch_user_info_success(self, mock_debug, mock_get):
        """Test successful user info fetching"""
        # Mock successful user info response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "login": "testuser",
            "email": "test@example.com",
            "avatar_url": "https://avatars.githubusercontent.com/u/12345",
            "type": "User"
        }
        mock_get.return_value = mock_response
        
        username, email, avatar_url, account_type = _fetch_user_info("test_token")
        
        assert username == "testuser"
        assert email == "test@example.com"
        assert avatar_url == "https://avatars.githubusercontent.com/u/12345"
        assert account_type == "User"

    @patch('auth.requests.get')
    @patch('auth.debug_log')
    def test_fetch_user_info_no_public_email(self, mock_debug, mock_get):
        """Test user info fetching when email is null"""
        # Mock response with no public email
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "login": "testuser",
            "email": None,  # No public email
            "avatar_url": "https://avatars.githubusercontent.com/u/12345",
            "type": "User"
        }
        mock_get.return_value = mock_response
        
        username, email, avatar_url, account_type = _fetch_user_info("test_token")
        
        assert username == "testuser"
        assert email == "testuser@users.noreply.github.com"  # Default email

    @patch('auth.requests.get')
    @patch('auth.debug_log')
    def test_fetch_user_info_normalizes_organization_type(self, mock_debug, mock_get):
        """Test user info normalizes GitHub organization type casing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "login": "my-company-org",
            "email": "org@example.com",
            "avatar_url": "https://avatars.githubusercontent.com/u/67890",
            "type": "organization"
        }
        mock_get.return_value = mock_response

        username, email, avatar_url, account_type = _fetch_user_info("test_token")

        assert username == "my-company-org"
        assert email == "org@example.com"
        assert avatar_url == "https://avatars.githubusercontent.com/u/67890"
        assert account_type == "Organization"

    def test_normalize_github_account_type_returns_supported_values_only(self):
        """Test GitHub account type normalization only returns supported API values"""
        assert _normalize_github_account_type("User") == "User"
        assert _normalize_github_account_type(" user ") == "User"
        assert _normalize_github_account_type("Organization") == "Organization"
        assert _normalize_github_account_type("organization") == "Organization"
        assert _normalize_github_account_type("Enterprise") is None
        assert _normalize_github_account_type(None) is None

    def test_resolve_connected_account_prefers_marketplace_account(self):
        """Test connected account uses marketplace/GitHub App account when present"""
        billing_data = [{
            "account": {
                "login": "whatsupdawg",
                "type": "Organization"
            },
            "plan": {
                "name": "professional"
            }
        }]

        account_login, account_type = _resolve_connected_github_account(
            "dawg-io",
            "User",
            billing_data,
            "test_token"
        )

        assert account_login == "whatsupdawg"
        assert account_type == "Organization"

    @patch('auth.requests.get')
    def test_resolve_connected_account_keeps_marketplace_login_with_unknown_type(self, mock_get):
        """Test connected account preserves marketplace login when GitHub type is unknown"""
        billing_data = [{
            "account": {
                "login": "unknown-type-owner",
                "type": "Enterprise"
            }
        }]

        account_login, account_type = _resolve_connected_github_account(
            "signed-in-user",
            "User",
            billing_data,
            "test_token"
        )

        assert account_login == "unknown-type-owner"
        assert account_type is None
        mock_get.assert_not_called()

    @patch('auth.USE_MOCK_RESPONSES', False)
    @patch('auth.requests.get')
    def test_resolve_connected_account_uses_installation_account(self, mock_get):
        """Test connected account falls back to GitHub App installation account"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "installations": [{
                "account": {
                    "login": "my-org",
                    "type": "Organization"
                }
            }]
        }
        mock_get.return_value = mock_response

        account_login, account_type = _resolve_connected_github_account(
            "signed-in-user",
            "User",
            [],
            "test_token"
        )

        assert account_login == "my-org"
        assert account_type == "Organization"

    @patch('auth.requests.get')
    def test_fetch_installation_account_keeps_login_with_unknown_type(self, mock_get):
        """Test installation account preserves login even when GitHub type is unknown"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "installations": [{
                "account": {
                    "login": "installation-owner",
                    "type": "Enterprise"
                }
            }]
        }
        mock_get.return_value = mock_response

        account_login, account_type = _fetch_installation_account("test_token")

        assert account_login == "installation-owner"
        assert account_type is None

    @patch('auth.USE_MOCK_RESPONSES', True)
    @patch('auth.requests.get')
    def test_resolve_connected_account_does_not_fetch_installations_in_mock_mode(self, mock_get):
        """Test mock mode does not make live installation API calls"""
        account_login, account_type = _resolve_connected_github_account(
            "mock-user",
            "User",
            [{"plan": {"name": "enterprise"}}],
            "test_token"
        )

        assert account_login == "mock-user"
        assert account_type == "User"
        mock_get.assert_not_called()

    @patch('auth.USE_MOCK_RESPONSES', False)
    @patch('auth.requests.get')
    def test_resolve_connected_account_falls_back_to_oauth_user(self, mock_get):
        """Test connected account falls back to OAuth user when no installation data exists"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"installations": []}
        mock_get.return_value = mock_response

        account_login, account_type = _resolve_connected_github_account(
            "personal-user",
            "User",
            [],
            "test_token"
        )

        assert account_login == "personal-user"
        assert account_type == "User"

    @patch('auth.requests.get')
    @patch('auth.debug_log')
    def test_fetch_user_info_failure(self, mock_debug, mock_get):
        """Test user info fetching failure"""
        # Mock failed response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response
        
        with pytest.raises(ValueError, match="Failed to fetch user information"):
            _fetch_user_info("invalid_token")

    @patch('auth.requests.get')
    @patch('auth.debug_log')
    @patch('auth.USE_MOCK_RESPONSES', False)
    def test_fetch_marketplace_data_success(self, mock_debug, mock_get):
        """Test successful marketplace data fetching"""
        # Mock successful marketplace response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "plan": {
                    "name": "professional",
                    "price": 4000
                },
                "unit_count": 1
            }
        ]
        mock_get.return_value = mock_response
        
        billing_data = _fetch_marketplace_data("testuser", "User", "test_token")
        
        assert len(billing_data) == 1
        assert billing_data[0]["plan"]["name"] == "professional"

    @patch('auth.debug_log')
    @patch('auth.USE_MOCK_RESPONSES', True)
    @patch('auth.get_mock_marketplace_purchases')
    def test_fetch_marketplace_data_mock(self, mock_get_purchases, mock_debug):
        """Test marketplace data fetching with mock responses"""
        mock_get_purchases.return_value = [{"plan": {"name": "enterprise"}}]
        
        billing_data = _fetch_marketplace_data("testuser", "User", "test_token")
        
        assert len(billing_data) == 1
        mock_debug.assert_any_call("📌 Using mock marketplace purchases")

    @patch('auth.config.INSTALLATION_MODE', 'cloud')
    @patch('auth.debug_log')
    def test_manage_user_in_database_create_new(self, mock_debug):
        """Test creating a new user in database"""
        # Mock database session
        mock_db = Mock()
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = None  # User doesn't exist
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query
        
        billing_data = [{"plan": {"name": "professional"}}]
        
        user = _manage_user_in_database(
            "newuser", 
            "new@example.com", 
            "User", 
            "https://avatar.url",
            billing_data,
            mock_db
        )
        
        # Verify user creation
        assert mock_db.add.called
        assert mock_db.commit.called
        mock_debug.assert_any_call(
            "✅ New user created in database: newuser (Account Type: professional, GitHub Type: User, Avatar URL: https://avatar.url)"
        )

    @patch('auth.config.INSTALLATION_MODE', 'cloud')
    @patch('auth.debug_log')
    def test_manage_user_in_database_update_existing(self, mock_debug):
        """Test updating an existing user in database"""
        # Mock database session with existing user
        mock_db = Mock()
        mock_user = Mock()
        mock_user.account_type = "free"
        mock_user.github_account_type = "User"
        mock_user.avatar_url = "https://old.avatar.url"
        
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query
        
        billing_data = [{"plan": {"name": "professional"}}]
        
        user = _manage_user_in_database(
            "existinguser",
            "existing@example.com",
            "User",
            "https://new.avatar.url",
            billing_data,
            mock_db
        )
        
        # Verify user update
        assert mock_user.account_type == "professional"
        assert mock_user.avatar_url == "https://new.avatar.url"
        assert mock_db.commit.called
        mock_debug.assert_any_call(
            "✅ Updated user in database: existinguser (Account Type: professional, GitHub Type: User, Avatar URL: https://new.avatar.url)"
        )

    @patch('auth.config.INSTALLATION_MODE', 'cloud')
    @patch('auth.debug_log')
    def test_manage_user_in_database_no_billing_data(self, mock_debug):
        """Test user management with no billing data"""
        # Mock database session
        mock_db = Mock()
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = None
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query
        
        billing_data = []  # No billing data
        
        user = _manage_user_in_database(
            "freeuser",
            "free@example.com",
            "User",
            "https://avatar.url",
            billing_data,
            mock_db
        )
        
        # Verify user created with "unknown" account type
        assert mock_db.add.called
        mock_debug.assert_any_call("📌 Debug: Cloud mode - account type from billing: unknown")


class TestComplexityReduction:
    """Verify that refactoring maintains low cognitive complexity"""

    def test_helper_functions_exist(self):
        """Verify all helper functions exist and are callable"""
        # These should not raise NameError
        assert callable(_exchange_code_for_token)
        assert callable(_fetch_user_info)
        assert callable(_fetch_marketplace_data)
        assert callable(_manage_user_in_database)

    def test_functions_have_docstrings(self):
        """Verify helper functions have documentation"""
        assert _exchange_code_for_token.__doc__ is not None
        assert _fetch_user_info.__doc__ is not None
        assert _fetch_marketplace_data.__doc__ is not None
        assert _manage_user_in_database.__doc__ is not None
