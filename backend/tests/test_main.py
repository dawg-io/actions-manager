"""
Tests for main.py endpoints
"""
import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from main import app


class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware applied to all responses."""

    def setup_method(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_x_content_type_options_present(self):
        """X-Content-Type-Options: nosniff is set on every response."""
        response = self.client.get("/")
        assert response.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options_present(self):
        """X-Frame-Options: DENY is set on every response."""
        response = self.client.get("/")
        assert response.headers.get("x-frame-options") == "DENY"

    def test_referrer_policy_present(self):
        """Referrer-Policy is set on every response."""
        response = self.client.get("/")
        assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    def test_permissions_policy_present(self):
        """Permissions-Policy is set on every response."""
        response = self.client.get("/")
        assert response.headers.get("permissions-policy") == "geolocation=(), camera=(), microphone=()"

    def test_hsts_absent_over_plain_http(self):
        """Strict-Transport-Security is NOT set when the request is plain HTTP."""
        response = self.client.get("/")
        assert "strict-transport-security" not in response.headers

    def test_hsts_present_with_forwarded_proto_https(self):
        """Strict-Transport-Security IS set when X-Forwarded-Proto: https is sent."""
        response = self.client.get("/", headers={"X-Forwarded-Proto": "https"})
        hsts = response.headers.get("strict-transport-security")
        assert hsts is not None
        assert "max-age=63072000" in hsts
        assert "includeSubDomains" in hsts

    def test_headers_present_on_404_response(self):
        """Security headers are set even on 404 error responses."""
        response = self.client.get("/nonexistent-path-xyz")
        assert response.headers.get("x-content-type-options") == "nosniff"
        assert response.headers.get("x-frame-options") == "DENY"


class TestMainEndpoints:
    """Test class for main.py endpoints"""
    
    def setup_method(self):
        """Set up test client"""
        self.client = TestClient(app)
    
    def test_root_endpoint(self):
        """Test the root health check endpoint"""
        response = self.client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "ActionsManager API is running"
        assert data["version"] == "1.0.0"
        assert isinstance(data["allow_insecure_http"], bool)

    def test_healthz_endpoint(self):
        """Test the /healthz endpoint returns the same payload as /"""
        response = self.client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "ActionsManager API is running"
        assert data["version"] == "1.0.0"
        assert isinstance(data["allow_insecure_http"], bool)

