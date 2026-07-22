"""
Tests for Marketplace Webhook Security Features

Tests new security enhancements:
- Source IP verification
- Rate limiting
- Header logging
- Admin panel endpoints
"""

import pytest
import json
import hmac
import hashlib
import time
import importlib
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Account, MarketplaceWebhookEvent, WorkspaceMember
from authorization import get_current_member
from marketplace_webhooks import (
    verify_source_ip,
    check_rate_limit,
    store_webhook_event,
    router,
    webhook_request_times
)
from main import app
import config


# Test database setup
TEST_DATABASE_URL = "sqlite:///./test_webhook_security.db"
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


def override_get_db():
    """Override database dependency for testing"""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    """Create test client with database override"""
    from marketplace_webhooks import get_db
    
    # Create test database tables
    Base.metadata.create_all(bind=test_engine)
    
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    if previous_override is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous_override
    
    # Drop test database tables
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def cloud_mode(monkeypatch):
    """Set cloud mode for tests that need marketplace webhook routes"""
    monkeypatch.setenv("INSTALLATION_MODE", "cloud")
    importlib.reload(config)
    yield
    # Restore default
    monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
    importlib.reload(config)


@pytest.fixture
def cloud_client(cloud_mode, monkeypatch):
    """Create test client in cloud mode with marketplace routes enabled"""
    from marketplace_webhooks import get_db
    import os
    import sys
    
    # Set cloud mode before importing main
    os.environ["INSTALLATION_MODE"] = "cloud"
    
    # Remove main from cache to force reload
    if 'main' in sys.modules:
        del sys.modules['main']
    
    # Import main fresh with cloud mode
    import main as main_module
    cloud_app = main_module.app
    
    # Create test database tables
    Base.metadata.create_all(bind=test_engine)
    
    def _mock_admin_member():
        member = WorkspaceMember()
        member.workspace_role = "admin"
        member.user_id = 1
        return member

    previous_override = cloud_app.dependency_overrides.get(get_db)
    cloud_app.dependency_overrides[get_db] = override_get_db
    cloud_app.dependency_overrides[get_current_member] = _mock_admin_member
    client = TestClient(cloud_app)
    yield client
    if previous_override is None:
        cloud_app.dependency_overrides.pop(get_db, None)
    else:
        cloud_app.dependency_overrides[get_db] = previous_override
    cloud_app.dependency_overrides.pop(get_current_member, None)

    # Drop test database tables
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """Reset rate limit tracking between tests"""
    webhook_request_times.clear()
    yield
    webhook_request_times.clear()


class TestSourceIPVerification:
    """Test source IP verification functionality"""
    
    def test_verify_ip_disabled(self):
        """Test IP verification when disabled"""
        with patch('marketplace_webhooks.VERIFY_WEBHOOK_IP', False):
            result = verify_source_ip("1.2.3.4")
            assert result is True
    
    def test_verify_ip_no_config(self):
        """Test IP verification with no configured ranges"""
        with patch('marketplace_webhooks.VERIFY_WEBHOOK_IP', True), \
             patch('marketplace_webhooks.GITHUB_WEBHOOK_IPS', ""):
            result = verify_source_ip("1.2.3.4")
            assert result is True  # Should allow when not configured
    
    def test_verify_ip_in_range(self):
        """Test IP verification for IP in allowed range"""
        with patch('marketplace_webhooks.VERIFY_WEBHOOK_IP', True), \
             patch('marketplace_webhooks.GITHUB_WEBHOOK_IPS', "192.30.252.0/22,185.199.108.0/22"):
            result = verify_source_ip("192.30.252.100")
            assert result is True
    
    def test_verify_ip_not_in_range(self):
        """Test IP verification for IP not in allowed range"""
        with patch('marketplace_webhooks.VERIFY_WEBHOOK_IP', True), \
             patch('marketplace_webhooks.GITHUB_WEBHOOK_IPS', "192.30.252.0/22,185.199.108.0/22"):
            result = verify_source_ip("10.0.0.1")
            assert result is False
    
    def test_verify_ip_invalid_format(self):
        """Test IP verification with invalid IP format"""
        with patch('marketplace_webhooks.VERIFY_WEBHOOK_IP', True), \
             patch('marketplace_webhooks.GITHUB_WEBHOOK_IPS', "192.30.252.0/22"):
            result = verify_source_ip("invalid-ip")
            assert result is False
    
    def test_verify_ip_no_source_ip(self):
        """Test IP verification with no source IP"""
        with patch('marketplace_webhooks.VERIFY_WEBHOOK_IP', True), \
             patch('marketplace_webhooks.GITHUB_WEBHOOK_IPS', "192.30.252.0/22"):
            result = verify_source_ip(None)
            assert result is False
    
    def test_verify_ipv6_in_range(self):
        """Test IPv6 address verification"""
        with patch('marketplace_webhooks.VERIFY_WEBHOOK_IP', True), \
             patch('marketplace_webhooks.GITHUB_WEBHOOK_IPS', "2620:112:3000::/44"):
            result = verify_source_ip("2620:112:3000::1")
            assert result is True


class TestRateLimiting:
    """Test webhook rate limiting functionality"""
    
    def test_rate_limit_first_request(self):
        """Test rate limiting allows first request"""
        result = check_rate_limit("1.2.3.4")
        assert result is True
    
    def test_rate_limit_within_limit(self):
        """Test rate limiting allows requests within limit"""
        ip = "1.2.3.4"
        with patch('marketplace_webhooks.WEBHOOK_RATE_LIMIT', 10):
            for i in range(9):
                result = check_rate_limit(ip)
                assert result is True
    
    def test_rate_limit_exceeds_limit(self):
        """Test rate limiting blocks requests exceeding limit"""
        ip = "1.2.3.4"
        with patch('marketplace_webhooks.WEBHOOK_RATE_LIMIT', 5):
            # Make requests up to limit
            for i in range(5):
                result = check_rate_limit(ip)
                assert result is True
            
            # Next request should be blocked
            result = check_rate_limit(ip)
            assert result is False
    
    def test_rate_limit_different_ips(self):
        """Test rate limiting is per IP address"""
        with patch('marketplace_webhooks.WEBHOOK_RATE_LIMIT', 5):
            # IP 1 makes 5 requests
            for i in range(5):
                assert check_rate_limit("1.2.3.4") is True
            
            # IP 2 should still be allowed
            assert check_rate_limit("5.6.7.8") is True
    
    def test_rate_limit_cleanup_old_entries(self):
        """Test rate limiting cleans up old entries"""
        from marketplace_webhooks import RATE_LIMIT_WINDOW_SECONDS
        
        ip = "1.2.3.4"
        with patch('marketplace_webhooks.WEBHOOK_RATE_LIMIT', 5):
            # Make requests
            for i in range(5):
                check_rate_limit(ip)
            
            # Manually set old timestamps (beyond rate limit window)
            expired_time = time.time() - (RATE_LIMIT_WINDOW_SECONDS + 5)
            webhook_request_times[ip] = [expired_time, expired_time, expired_time]
            
            # Should allow new request since old ones expired
            result = check_rate_limit(ip)
            assert result is True


class TestHeaderAndIPLogging:
    """Test logging of headers and source IP"""
    
    def test_store_webhook_with_ip_and_headers(self, test_db):
        """Test storing webhook event with source IP and headers"""
        payload = {
            "action": "purchased",
            "marketplace_purchase": {
                "account": {"id": 12345, "login": "testuser"},
                "plan": {"name": "professional"}
            }
        }
        
        headers = {
            "X-GitHub-Event": "marketplace_purchase",
            "X-GitHub-Delivery": "12345-67890",
            "User-Agent": "GitHub-Hookshot/abc123"
        }
        
        event = store_webhook_event(
            test_db,
            "marketplace_purchase",
            "purchased",
            payload,
            "sha256=test_sig",
            source_ip="192.30.252.100",
            headers=headers
        )
        
        assert event.source_ip == "192.30.252.100"
        assert event.headers is not None
        
        stored_headers = json.loads(event.headers)
        assert stored_headers["X-GitHub-Event"] == "marketplace_purchase"
        assert stored_headers["X-GitHub-Delivery"] == "12345-67890"
    
    def test_store_webhook_without_ip_and_headers(self, test_db):
        """Test storing webhook event without source IP and headers"""
        payload = {
            "action": "purchased",
            "marketplace_purchase": {
                "account": {"id": 12345, "login": "testuser"},
                "plan": {"name": "professional"}
            }
        }
        
        event = store_webhook_event(
            test_db,
            "marketplace_purchase",
            "purchased",
            payload,
            "sha256=test_sig"
        )
        
        assert event.source_ip is None
        assert event.headers is None


class TestWebhookSecurityEndpoint:
    """Test webhook endpoint with security features"""
    
    @patch('marketplace_webhooks.verify_webhook_signature')
    @patch('marketplace_webhooks.verify_source_ip')
    @patch('marketplace_webhooks.check_rate_limit')
    def test_webhook_with_all_security_checks(
        self, mock_rate_limit, mock_verify_ip, mock_verify_sig, cloud_client
    ):
        """Test webhook endpoint passes all security checks"""
        mock_verify_sig.return_value = True
        mock_verify_ip.return_value = True
        mock_rate_limit.return_value = True
        
        payload = {
            "action": "purchased",
            "marketplace_purchase": {
                "account": {"id": 12345, "login": "testuser"},
                "plan": {"name": "professional"}
            }
        }
        
        response = cloud_client.post(
            "/webhooks/marketplace",
            json=payload,
            headers={
                "X-Hub-Signature-256": "sha256=test_signature",
                "X-GitHub-Event": "marketplace_purchase",
                "X-GitHub-Delivery": "test-delivery-123"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        
        # Verify security checks were called
        mock_verify_sig.assert_called_once()
        mock_verify_ip.assert_called_once()
        mock_rate_limit.assert_called_once()
    
    @patch('marketplace_webhooks.verify_webhook_signature')
    @patch('marketplace_webhooks.check_rate_limit')
    def test_webhook_rate_limit_exceeded(
        self, mock_rate_limit, mock_verify_sig, cloud_client
    ):
        """Test webhook endpoint blocks when rate limit exceeded"""
        mock_verify_sig.return_value = True
        mock_rate_limit.return_value = False
        
        payload = {"action": "purchased", "marketplace_purchase": {}}
        
        response = cloud_client.post(
            "/webhooks/marketplace",
            json=payload,
            headers={
                "X-Hub-Signature-256": "sha256=test",
                "X-GitHub-Event": "marketplace_purchase"
            }
        )
        
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]
    
    @patch('marketplace_webhooks.verify_webhook_signature')
    @patch('marketplace_webhooks.verify_source_ip')
    @patch('marketplace_webhooks.check_rate_limit')
    def test_webhook_invalid_source_ip(
        self, mock_rate_limit, mock_verify_ip, mock_verify_sig, cloud_client
    ):
        """Test webhook endpoint blocks invalid source IP"""
        mock_verify_sig.return_value = True
        mock_verify_ip.return_value = False
        mock_rate_limit.return_value = True
        
        payload = {"action": "purchased", "marketplace_purchase": {}}
        
        response = cloud_client.post(
            "/webhooks/marketplace",
            json=payload,
            headers={
                "X-Hub-Signature-256": "sha256=test",
                "X-GitHub-Event": "marketplace_purchase"
            }
        )
        
        assert response.status_code == 403
        assert "not authorized" in response.json()["detail"]


class TestWebhookEventDetailsEndpoint:
    """Test webhook event details endpoint"""
    
    def test_get_event_details(self, cloud_client, test_db):
        """Test retrieving detailed information about a webhook event"""
        # Create a test event
        payload = {
            "action": "purchased",
            "marketplace_purchase": {
                "account": {"id": 12345, "login": "testuser"},
                "plan": {"name": "professional"}
            }
        }
        
        headers = {"X-GitHub-Event": "marketplace_purchase"}
        
        event = store_webhook_event(
            test_db,
            "marketplace_purchase",
            "purchased",
            payload,
            "sha256=test_sig",
            source_ip="192.30.252.100",
            headers=headers
        )
        
        # Fetch event details
        response = cloud_client.get(f"/webhooks/marketplace/events/{event.event_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["event_id"] == event.event_id
        assert data["source_ip"] == "192.30.252.100"
        assert data["headers"] == headers
        assert data["payload"] == payload
    
    def test_get_nonexistent_event(self, cloud_client):
        """Test retrieving details for non-existent event"""
        response = cloud_client.get("/webhooks/marketplace/events/99999")
        
        assert response.status_code == 404


class TestListWebhookEventsWithNewFields:
    """Test listing webhook events includes new security fields"""
    
    def test_list_events_includes_ip_and_headers(self, cloud_client, test_db):
        """Test that listing events includes source IP and headers"""
        # Create test events with security fields
        for i in range(3):
            payload = {
                "action": "purchased",
                "marketplace_purchase": {
                    "account": {"id": 12345 + i, "login": f"user{i}"},
                    "plan": {"name": "professional"}
                }
            }
            
            headers = {
                "X-GitHub-Event": "marketplace_purchase",
                "X-GitHub-Delivery": f"delivery-{i}"
            }
            
            store_webhook_event(
                test_db,
                "marketplace_purchase",
                "purchased",
                payload,
                f"sha256=sig{i}",
                source_ip=f"192.30.252.{100 + i}",
                headers=headers
            )
        
        # List events
        response = cloud_client.get("/webhooks/marketplace/events")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 3
        
        # Verify new fields are present
        for event in data["events"]:
            assert "source_ip" in event
            assert "headers" in event
            assert event["source_ip"].startswith("192.30.252.")
            assert event["headers"]["X-GitHub-Event"] == "marketplace_purchase"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
