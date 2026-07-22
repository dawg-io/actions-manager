"""
Tests for HTTP security features in auth module
"""
import os
import pytest
import auth
from unittest.mock import Mock, patch
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

# Import the functions we need to test
from auth import _is_localhost, _validate_secure_connection


class TestLocalhostDetection:
    """Test cases for localhost detection"""

    def test_is_localhost_with_localhost(self):
        """Test that localhost is correctly identified"""
        assert _is_localhost("localhost") is True
        assert _is_localhost("LOCALHOST") is True  # Case insensitive
        
    def test_is_localhost_with_127_0_0_1(self):
        """Test that 127.0.0.1 is correctly identified"""
        assert _is_localhost("127.0.0.1") is True
        
    def test_is_localhost_with_ipv6_loopback(self):
        """Test that ::1 is correctly identified"""
        assert _is_localhost("::1") is True
        
    def test_is_localhost_with_0_0_0_0(self):
        """Test that 0.0.0.0 is correctly identified"""
        assert _is_localhost("0.0.0.0") is True
        
    def test_is_localhost_with_port(self):
        """Test that localhost with port is correctly identified"""
        assert _is_localhost("localhost:8080") is True
        assert _is_localhost("127.0.0.1:8080") is True
        
    def test_is_localhost_with_remote_ip(self):
        """Test that remote IPs are not identified as localhost"""
        assert _is_localhost("192.168.1.100") is False
        assert _is_localhost("10.0.0.5") is False
        assert _is_localhost("example.com") is False
        
    def test_is_localhost_with_empty_string(self):
        """Test that empty string is not identified as localhost"""
        assert _is_localhost("") is False
        
    def test_is_localhost_with_none(self):
        """Test that None is not identified as localhost"""
        assert _is_localhost(None) is False


class TestSecureConnectionValidation:
    """Test cases for secure connection validation"""

    def test_validate_secure_connection_with_https(self):
        """Test that HTTPS connections are allowed"""
        request = Mock(spec=Request)
        request.url.scheme = "https"
        request.headers = {}
        
        # Should not raise an exception
        _validate_secure_connection(request)
        
    def test_validate_secure_connection_with_forwarded_proto_https(self):
        """Test that X-Forwarded-Proto: https is recognized"""
        request = Mock(spec=Request)
        request.url.scheme = "http"
        request.headers = {"X-Forwarded-Proto": "https"}
        
        # Should not raise an exception
        _validate_secure_connection(request)
        
    def test_validate_secure_connection_with_localhost(self):
        """Test that localhost HTTP connections are allowed"""
        request = Mock(spec=Request)
        request.url.scheme = "http"
        request.headers = {}
        request.client = Mock()
        request.client.host = "localhost"

        # Should not raise an exception
        _validate_secure_connection(request)

    def test_validate_secure_connection_with_127_0_0_1(self):
        """Test that 127.0.0.1 HTTP connections are allowed"""
        request = Mock(spec=Request)
        request.url.scheme = "http"
        request.headers = {}
        request.client = Mock()
        request.client.host = "127.0.0.1"

        # Should not raise an exception
        _validate_secure_connection(request)
        
    def test_validate_secure_connection_blocks_remote_http(self):
        """Test that remote HTTP connections are blocked"""
        request = Mock(spec=Request)
        request.url.scheme = "http"
        request.headers = {"Host": "192.168.1.100:8080"}
        
        with pytest.raises(HTTPException) as exc_info:
            _validate_secure_connection(request)
        
        assert exc_info.value.status_code == 400
        assert "PAT login over non-local HTTP is disabled" in exc_info.value.detail
        assert "ALLOW_INSECURE_HTTP" in exc_info.value.detail
        
    def test_validate_secure_connection_blocks_domain_http(self):
        """Test that domain HTTP connections are blocked"""
        request = Mock(spec=Request)
        request.url.scheme = "http"
        request.headers = {"Host": "actionsmanager.example.com"}
        
        with pytest.raises(HTTPException) as exc_info:
            _validate_secure_connection(request)
        
        assert exc_info.value.status_code == 400
        assert "PAT login over non-local HTTP is disabled" in exc_info.value.detail
        
    @patch.dict(os.environ, {"ALLOW_INSECURE_HTTP": "true"})
    def test_validate_secure_connection_with_override_enabled(self):
        """Test that ALLOW_INSECURE_HTTP=true disables the check"""
        request = Mock(spec=Request)
        request.url.scheme = "http"
        request.headers = {"Host": "192.168.1.100:8080"}
        
        # Should not raise an exception when override is enabled
        with patch.object(auth, "ALLOW_INSECURE_HTTP", True):
            auth._validate_secure_connection(request)
        
    def test_validate_secure_connection_with_no_host_header_https(self):
        """Test handling of requests without Host header on HTTPS"""
        request = Mock(spec=Request)
        request.url.scheme = "https"
        request.headers = {}
        
        # HTTPS should always be allowed
        _validate_secure_connection(request)


class TestPATEndpointSecurity:
    """Integration tests for PAT endpoints with security checks"""
    
    @pytest.fixture(autouse=True)
    def setup_test_env(self, monkeypatch):
        """Setup test environment"""
        # Ensure ALLOW_INSECURE_HTTP is not set for these tests
        monkeypatch.delenv("ALLOW_INSECURE_HTTP", raising=False)
        monkeypatch.setattr(auth, "ALLOW_INSECURE_HTTP", False)
        yield
        
    def test_github_token_login_blocks_insecure_http(self):
        """Test that /auth/token blocks insecure HTTP connections"""
        from main import app
        from database import SessionLocal
        from models import Account
        
        client = TestClient(app, base_url="http://192.168.1.100:8080")
        
        # Mock the validation to return a valid token
        with patch("auth._validate_github_token") as mock_validate, \
             patch("auth._fetch_user_info") as mock_user_info, \
             patch("auth._fetch_marketplace_data") as mock_marketplace:
            
            mock_validate.return_value = {"status": "valid"}
            mock_user_info.return_value = ("testuser", "test@example.com", "avatar_url", "User")
            mock_marketplace.return_value = []
            
            response = client.post(
                "/auth/token",
                json={"token": "ghp_test1234567890123456789012345678"}
            )
            
            assert response.status_code == 400
            assert "PAT login over non-local HTTP is disabled" in response.json()["detail"]
            
    def test_save_github_token_requires_auth_before_insecure_http_check(self):
        """Unauthenticated PUT /api/user/{username}/github-token is rejected by write middleware."""
        from main import app
        
        client = TestClient(app, base_url="http://192.168.1.100:8080")
        
        # Mock authentication
        with patch("auth._validate_github_token") as mock_validate:
            mock_validate.return_value = {"status": "valid"}
            
            response = client.put(
                "/api/user/testuser/github-token",
                json={"token": "ghp_test1234567890123456789012345678"},
                headers={"X-GitHub-User": "testuser"}
            )
            
            assert response.status_code == 401
            assert "Authentication required" in response.json()["detail"]
            
    def test_test_github_token_requires_auth_before_insecure_http_check(self):
        """Unauthenticated POST /api/user/{username}/github-token/test is rejected by write middleware."""
        from main import app
        
        client = TestClient(app, base_url="http://192.168.1.100:8080")
        
        # Mock authentication
        with patch("auth._validate_github_token") as mock_validate:
            mock_validate.return_value = {"status": "valid"}
            
            response = client.post(
                "/api/user/testuser/github-token/test",
                json={"token": "ghp_test1234567890123456789012345678"},
                headers={"X-GitHub-User": "testuser"}
            )
            
            assert response.status_code == 401
            assert "Authentication required" in response.json()["detail"]
            
    def test_pat_endpoints_allow_localhost_http(self):
        """Test that PAT endpoints allow HTTP when ALLOW_INSECURE_HTTP is set"""
        from main import app
        from database import Base
        from models import Account
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        client = TestClient(app, base_url="http://localhost:8080")

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        def override_get_db():
            db = TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        from auth import get_db
        previous_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = override_get_db

        db = TestingSessionLocal()
        test_user = Account(
            github_user="testuser",
            github_email="test@example.com",
            account_type="free"
        )
        db.add(test_user)
        db.commit()
        db.close()

        try:
            # TestClient uses "testclient" as TCP client IP, not "localhost", so
            # we use ALLOW_INSECURE_HTTP to verify the endpoint passes the security check.
            with patch("auth._validate_github_token") as mock_validate, \
                 patch("auth._fetch_user_info") as mock_user_info, \
                 patch("auth._fetch_marketplace_data") as mock_marketplace, \
                 patch("auth._resolve_connected_github_account") as mock_connected, \
                 patch.object(auth, "ALLOW_INSECURE_HTTP", True):

                mock_validate.return_value = {
                    "status": "valid",
                    "token_type": "fine_grained_pat",
                    "scopes": ["repo"],
                    "has_required_permissions": True,
                    "permission_issues": []
                }
                mock_user_info.return_value = ("testuser", "test@example.com", "avatar_url", "User")
                mock_marketplace.return_value = []
                mock_connected.return_value = ("testuser", "User")

                response = client.post(
                    "/auth/token",
                    json={"token": "ghp_test1234567890123456789012345678"}
                )

                assert response.status_code != 400 or "PAT login over non-local HTTP is disabled" not in response.json().get("detail", "")
        finally:
            if previous_override is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous_override


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
