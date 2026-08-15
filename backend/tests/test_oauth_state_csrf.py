"""
Tests for OAuth state parameter CSRF protection

Validates that:
1. github_auth() generates a state parameter
2. github_callback() requires and validates the state parameter
3. State parameters expire after TTL
4. State parameters are single-use only
5. Invalid/missing/replayed states are rejected
"""
import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import auth as auth_module
from auth import github_auth, github_callback, oauth_states, OAuthStateStore
from database import Base
from models import Account


class TestOAuthStateStore:
    """Test cases for OAuthStateStore class"""
    
    def test_create_generates_unique_states(self):
        """Test that create() generates unique state values"""
        store = OAuthStateStore()
        state1 = store.create()
        state2 = store.create()
        
        assert state1 != state2
        assert len(state1) >= 32  # URL-safe base64 of 32 random bytes
        assert len(state2) >= 32
    
    def test_validate_and_consume_accepts_valid_state(self):
        """Test that a freshly created state is valid"""
        store = OAuthStateStore()
        state = store.create()
        
        assert store.validate_and_consume(state) is True
    
    def test_validate_and_consume_rejects_unknown_state(self):
        """Test that an unknown state is rejected"""
        store = OAuthStateStore()
        
        assert store.validate_and_consume("unknown_state") is False
    
    def test_validate_and_consume_is_single_use(self):
        """Test that a state can only be used once"""
        store = OAuthStateStore()
        state = store.create()
        
        # First use succeeds
        assert store.validate_and_consume(state) is True
        
        # Second use fails (state was consumed)
        assert store.validate_and_consume(state) is False
    
    def test_validate_and_consume_rejects_expired_state(self):
        """Test that expired states are rejected"""
        store = OAuthStateStore()
        store.STATE_TTL = 0.1  # 100ms for testing
        
        state = store.create()
        time.sleep(0.2)  # Wait for expiration
        
        assert store.validate_and_consume(state) is False
    
    def test_cleanup_expired_removes_old_states(self):
        """Test that expired states are cleaned up"""
        store = OAuthStateStore()
        store.STATE_TTL = 0.1  # 100ms for testing
        
        state1 = store.create()
        time.sleep(0.2)  # Wait for expiration
        state2 = store.create()  # This triggers cleanup
        
        # state1 should be expired and cleaned up
        assert state1 not in store._states
        # state2 should still be valid
        assert state2 in store._states


class TestGitHubAuthEndpoint:
    """Test cases for /auth/github endpoint"""
    
    def test_github_auth_includes_state_parameter(self):
        """Test that github_auth() includes a state parameter in the OAuth URL"""
        # Clear any existing states
        oauth_states._states.clear()
        
        response = github_auth()
        
        assert isinstance(response, RedirectResponse)
        assert "state=" in response.headers["location"]
        assert "https://github.com/login/oauth/authorize" in response.headers["location"]
        
        # Verify a state was created
        assert len(oauth_states._states) == 1
    
    def test_github_auth_creates_unique_state_each_time(self):
        """Test that each call to github_auth() creates a unique state"""
        oauth_states._states.clear()
        
        response1 = github_auth()
        response2 = github_auth()
        
        url1 = response1.headers["location"]
        url2 = response2.headers["location"]
        
        # Extract state parameters
        state1 = url1.split("state=")[1] if "state=" in url1 else None
        state2 = url2.split("state=")[1] if "state=" in url2 else None
        
        assert state1 is not None
        assert state2 is not None
        assert state1 != state2
        
        # Both states should be stored
        assert len(oauth_states._states) == 2


class TestGitHubCallbackEndpoint:
    """Test cases for /auth/callback endpoint"""
    
    def setup_method(self):
        """Setup test database and mock request"""
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        SessionMaker = sessionmaker(bind=self.engine)
        self.db = SessionMaker()
        
        self.mock_request = Mock(spec=Request)
        self.mock_request.client = Mock()
        self.mock_request.client.host = "127.0.0.1"
        self.mock_request.headers = {"X-Forwarded-For": "192.168.1.1"}
    
    def teardown_method(self):
        """Cleanup test database"""
        if self.db:
            self.db.close()
    
    def test_github_callback_rejects_missing_state(self):
        """Test that github_callback rejects requests without a state parameter"""
        # Missing state parameter should be caught by FastAPI parameter validation
        # But let's test the empty string case
        result = github_callback(code="test_code", state="", request=self.mock_request, db=self.db)
        
        assert "error" in result
        assert "Invalid or expired authentication request" in result["error"]
    
    def test_github_callback_rejects_invalid_state(self):
        """Test that github_callback rejects requests with an invalid state"""
        oauth_states._states.clear()
        
        result = github_callback(
            code="test_code",
            state="invalid_state_12345",
            request=self.mock_request,
            db=self.db
        )
        
        assert "error" in result
        assert "Invalid or expired authentication request" in result["error"]
    
    def test_github_callback_rejects_expired_state(self):
        """Test that github_callback rejects expired states"""
        oauth_states._states.clear()
        oauth_states.STATE_TTL = 0.1  # 100ms for testing
        
        state = oauth_states.create()
        time.sleep(0.2)  # Wait for expiration
        
        result = github_callback(
            code="test_code",
            state=state,
            request=self.mock_request,
            db=self.db
        )
        
        assert "error" in result
        assert "Invalid or expired authentication request" in result["error"]
        
        # Restore normal TTL
        oauth_states.STATE_TTL = 600
    
    def test_github_callback_rejects_replayed_state(self):
        """Test that github_callback rejects a replayed (reused) state"""
        oauth_states._states.clear()
        state = oauth_states.create()
        
        # First use: consume the state
        oauth_states.validate_and_consume(state)
        
        # Second use: replay attack - should be rejected
        result = github_callback(
            code="test_code",
            state=state,
            request=self.mock_request,
            db=self.db
        )
        
        assert "error" in result
        assert "Invalid or expired authentication request" in result["error"]
    
    @patch('auth._exchange_code_for_token')
    @patch('auth._fetch_user_info')
    @patch('auth._fetch_marketplace_data')
    @patch('auth._resolve_connected_github_account')
    def test_github_callback_accepts_valid_state(
        self,
        mock_resolve_account,
        mock_fetch_marketplace,
        mock_fetch_user,
        mock_exchange_code
    ):
        """Test that github_callback accepts a valid state and processes the OAuth flow"""
        oauth_states._states.clear()
        state = oauth_states.create()
        
        # Mock all the OAuth flow functions
        mock_exchange_code.return_value = "gho_test_token_12345"
        mock_fetch_user.return_value = ("testuser", "test@example.com", "https://avatar.url", "User")
        mock_fetch_marketplace.return_value = []
        mock_resolve_account.return_value = (None, None)
        
        result = github_callback(
            code="test_code",
            state=state,
            request=self.mock_request,
            db=self.db
        )
        
        # Should succeed and redirect
        assert isinstance(result, RedirectResponse)
        assert "testuser" in result.headers["location"]
        
        # State should be consumed
        assert state not in oauth_states._states

    @patch('auth._exchange_code_for_token')
    @patch('auth._fetch_user_info')
    @patch('auth._fetch_marketplace_data')
    @patch('auth._resolve_connected_github_account')
    def test_github_callback_persists_token_for_background_use(
        self,
        mock_resolve_account,
        mock_fetch_marketplace,
        mock_fetch_user,
        mock_exchange_code,
        monkeypatch,
    ):
        """A normal OAuth/App login must save a durable token, not just an
        in-memory one, or the drift-check background sweep can never find a
        credential for the project owner once this process's memory is gone."""
        monkeypatch.setattr(auth_module, "SECRET_KEY", "test-secret-key")
        oauth_states._states.clear()
        state = oauth_states.create()

        mock_exchange_code.return_value = "gho_test_token_12345"
        mock_fetch_user.return_value = ("testuser", "test@example.com", "https://avatar.url", "User")
        mock_fetch_marketplace.return_value = []
        mock_resolve_account.return_value = (None, None)

        result = github_callback(
            code="test_code",
            state=state,
            request=self.mock_request,
            db=self.db,
        )

        assert isinstance(result, RedirectResponse)

        saved_user = self.db.query(Account).filter(Account.github_user == "testuser").first()
        assert saved_user is not None
        assert saved_user.github_pat_token_encrypted is not None
        assert saved_user.github_pat_updated_at is not None

    @patch('auth._exchange_code_for_token')
    def test_github_callback_consumes_state_even_on_oauth_failure(
        self,
        mock_exchange_code
    ):
        """Test that github_callback consumes the state even if OAuth exchange fails"""
        oauth_states._states.clear()
        state = oauth_states.create()
        
        # Make the OAuth exchange fail
        mock_exchange_code.side_effect = ValueError("GitHub authentication failed")
        
        result = github_callback(
            code="test_code",
            state=state,
            request=self.mock_request,
            db=self.db
        )
        
        # Should return an error
        assert "error" in result
        
        # State should still be consumed (to prevent replay attacks)
        assert state not in oauth_states._states


class TestOAuthFlowIntegration:
    """Integration tests for the complete OAuth flow"""
    
    def setup_method(self):
        """Setup test database"""
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        SessionMaker = sessionmaker(bind=self.engine)
        self.db = SessionMaker()
        
        self.mock_request = Mock(spec=Request)
        self.mock_request.client = Mock()
        self.mock_request.client.host = "127.0.0.1"
        self.mock_request.headers = {"X-Forwarded-For": "192.168.1.1"}
    
    def teardown_method(self):
        """Cleanup test database"""
        if self.db:
            self.db.close()
    
    @patch('auth._exchange_code_for_token')
    @patch('auth._fetch_user_info')
    @patch('auth._fetch_marketplace_data')
    @patch('auth._resolve_connected_github_account')
    def test_complete_oauth_flow_with_state(
        self,
        mock_resolve_account,
        mock_fetch_marketplace,
        mock_fetch_user,
        mock_exchange_code
    ):
        """Test the complete OAuth flow from github_auth to github_callback"""
        oauth_states._states.clear()
        
        # Step 1: User initiates OAuth login
        auth_response = github_auth()
        auth_url = auth_response.headers["location"]
        
        # Extract state from the OAuth URL
        state = auth_url.split("state=")[1] if "state=" in auth_url else None
        assert state is not None
        
        # Step 2: User authorizes on GitHub and is redirected back with code and state
        # Mock the OAuth flow functions
        mock_exchange_code.return_value = "gho_test_token_12345"
        mock_fetch_user.return_value = ("testuser", "test@example.com", "https://avatar.url", "User")
        mock_fetch_marketplace.return_value = []
        mock_resolve_account.return_value = (None, None)
        
        callback_response = github_callback(
            code="authorization_code_12345",
            state=state,
            request=self.mock_request,
            db=self.db
        )
        
        # Should succeed and redirect to frontend
        assert isinstance(callback_response, RedirectResponse)
        assert "testuser" in callback_response.headers["location"]
        
        # State should be consumed and removed
        assert state not in oauth_states._states
    
    def test_oauth_flow_blocked_without_valid_state(self):
        """Test that the OAuth flow is blocked when state validation fails"""
        oauth_states._states.clear()
        
        # Attacker tries to use a callback with a fake state
        callback_response = github_callback(
            code="attacker_code_12345",
            state="fake_state_12345",
            request=self.mock_request,
            db=self.db
        )
        
        # Should be rejected
        assert "error" in callback_response
        assert "Invalid or expired authentication request" in callback_response["error"]
