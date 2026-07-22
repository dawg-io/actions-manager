"""
Tests for GitHub Marketplace Webhook Handler

Tests webhook signature verification, event storage, account updates,
and all supported webhook event types.
"""

import pytest
import json
import hmac
import hashlib
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
    verify_webhook_signature,
    store_webhook_event,
    update_account_from_webhook,
    router
)
from main import app
import config


# Test database setup
TEST_DATABASE_URL = "sqlite:///./test_webhooks.db"
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


@pytest.fixture
def cloud_mode(monkeypatch):
    """Set cloud mode for tests that need marketplace webhook routes"""
    monkeypatch.setenv("INSTALLATION_MODE", "cloud")
    importlib.reload(config)
    yield
    # Restore default
    monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
    importlib.reload(config)


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
def cloud_client(cloud_mode, monkeypatch):
    """Create test client in cloud mode with marketplace routes enabled"""
    from marketplace_webhooks import get_db
    import os
    
    # Set cloud mode before importing main
    os.environ["INSTALLATION_MODE"] = "cloud"
    
    # Re-import main to get app with cloud mode routes
    import importlib
    import sys
    
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


class TestWebhookSignatureVerification:
    """Test webhook signature verification"""
    
    def test_verify_signature_valid(self):
        """Test signature verification with valid signature"""
        secret = "test_secret"
        payload = b'{"action": "purchased"}'
        
        # Calculate expected signature
        mac = hmac.new(secret.encode('utf-8'), msg=payload, digestmod=hashlib.sha256)
        signature = f"sha256={mac.hexdigest()}"
        
        with patch('marketplace_webhooks.GITHUB_WEBHOOK_SECRET', secret):
            result = verify_webhook_signature(payload, signature)
            assert result is True
    
    def test_verify_signature_invalid(self):
        """Test signature verification with invalid signature"""
        secret = "test_secret"
        payload = b'{"action": "purchased"}'
        invalid_signature = "sha256=invalid_signature_hash"
        
        with patch('marketplace_webhooks.GITHUB_WEBHOOK_SECRET', secret):
            result = verify_webhook_signature(payload, invalid_signature)
            assert result is False
    
    def test_verify_signature_no_secret(self):
        """Test signature verification when no secret is configured"""
        payload = b'{"action": "purchased"}'
        signature = "sha256=some_signature"
        
        with patch('marketplace_webhooks.GITHUB_WEBHOOK_SECRET', ""):
            result = verify_webhook_signature(payload, signature)
            assert result is False  # No secret configured → reject for security
    
    def test_verify_signature_missing(self):
        """Test signature verification when signature is missing"""
        secret = "test_secret"
        payload = b'{"action": "purchased"}'
        
        with patch('marketplace_webhooks.GITHUB_WEBHOOK_SECRET', secret):
            result = verify_webhook_signature(payload, None)
            assert result is False
    
    def test_verify_signature_wrong_format(self):
        """Test signature verification with wrong format"""
        secret = "test_secret"
        payload = b'{"action": "purchased"}'
        wrong_format = "md5=some_hash"  # Wrong algorithm prefix
        
        with patch('marketplace_webhooks.GITHUB_WEBHOOK_SECRET', secret):
            result = verify_webhook_signature(payload, wrong_format)
            assert result is False


class TestWebhookEventStorage:
    """Test webhook event storage"""
    
    def test_store_webhook_event(self, test_db):
        """Test storing webhook event in database"""
        payload = {
            "action": "purchased",
            "marketplace_purchase": {
                "account": {
                    "id": 12345,
                    "login": "testuser"
                },
                "plan": {
                    "name": "professional",
                    "price": 4000
                }
            }
        }
        
        event = store_webhook_event(
            test_db,
            "marketplace_purchase",
            "purchased",
            payload,
            "sha256=test_signature"
        )
        
        assert event.event_id is not None
        assert event.event_type == "marketplace_purchase"
        assert event.action == "purchased"
        assert event.github_user == "testuser"
        assert event.marketplace_account_id == 12345
        assert event.plan_name == "professional"
        assert event.signature == "sha256=test_signature"
        assert event.processed is False
        assert event.retry_count == 0
    
    def test_store_webhook_event_minimal_payload(self, test_db):
        """Test storing webhook with minimal payload"""
        payload = {
            "action": "cancelled",
            "marketplace_purchase": {}
        }
        
        event = store_webhook_event(
            test_db,
            "marketplace_purchase",
            "cancelled",
            payload,
            None
        )
        
        assert event.event_id is not None
        assert event.event_type == "marketplace_purchase"
        assert event.action == "cancelled"
        assert event.github_user is None
        assert event.marketplace_account_id is None


class TestAccountUpdates:
    """Test account updates from webhooks"""
    
    def test_update_account_purchased(self, test_db):
        """Test account update for purchased event"""
        # Create test user
        user = Account(
            github_user="testuser",
            github_email="test@example.com",
            account_type="free"
        )
        test_db.add(user)
        test_db.commit()
        
        # Create webhook event
        payload = {
            "action": "purchased",
            "marketplace_purchase": {
                "account": {
                    "id": 12345,
                    "login": "testuser"
                },
                "plan": {
                    "name": "professional",
                    "price": 4000
                },
                "unit_count": 1,
                "on_free_trial": False,
                "next_billing_date": "2025-06-01T00:00:00Z"
            }
        }
        
        webhook_event = store_webhook_event(
            test_db, "marketplace_purchase", "purchased", payload, None
        )
        
        # Process webhook
        success = update_account_from_webhook(test_db, webhook_event, payload)
        
        assert success is True
        assert webhook_event.processed is True
        
        # Verify account updated
        updated_user = test_db.query(Account).filter(Account.github_user == "testuser").first()
        assert updated_user.account_type == "professional"
        assert updated_user.marketplace_plan == "professional"
        assert updated_user.marketplace_account_id == 12345
        assert updated_user.marketplace_unit_count == 1
        assert updated_user.marketplace_on_free_trial is False
        assert updated_user.marketplace_updated_at is not None
    
    def test_update_account_free_trial(self, test_db):
        """Test account update for free trial purchase"""
        # Create test user
        user = Account(
            github_user="trialuser",
            github_email="trial@example.com",
            account_type="free"
        )
        test_db.add(user)
        test_db.commit()
        
        # Create webhook event for free trial
        payload = {
            "action": "purchased",
            "marketplace_purchase": {
                "account": {
                    "id": 67890,
                    "login": "trialuser"
                },
                "plan": {
                    "name": "professional",
                    "price": 4000
                },
                "unit_count": 1,
                "on_free_trial": True,
                "free_trial_ends_on": "2025-12-01T00:00:00Z",
                "next_billing_date": "2025-12-01T00:00:00Z"
            }
        }
        
        webhook_event = store_webhook_event(
            test_db, "marketplace_purchase", "purchased", payload, None
        )
        
        # Process webhook
        success = update_account_from_webhook(test_db, webhook_event, payload)
        
        assert success is True
        assert webhook_event.processed is True
        
        # Verify account updated with trial status
        updated_user = test_db.query(Account).filter(Account.github_user == "trialuser").first()
        assert updated_user.account_type == "professional"
        assert updated_user.marketplace_plan == "professional"
        assert updated_user.marketplace_on_free_trial is True
        assert updated_user.marketplace_account_id == 67890
    
    def test_update_account_with_effective_date(self, test_db):
        """Test storing effective_date from webhook payload"""
        user = Account(
            github_user="testuser",
            github_email="test@example.com",
            account_type="professional"
        )
        test_db.add(user)
        test_db.commit()
        
        # Create webhook event with effective_date
        payload = {
            "action": "pending_change",
            "effective_date": "2025-12-01T00:00:00Z",
            "marketplace_purchase": {
                "account": {
                    "id": 12345,
                    "login": "testuser"
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
        
        # Verify effective_date was stored
        assert webhook_event.effective_date is not None
        assert webhook_event.effective_date.year == 2025
        assert webhook_event.effective_date.month == 12
        assert webhook_event.effective_date.day == 1
    
    def test_update_account_with_previous_plan(self, test_db):
        """Test handling previous_marketplace_purchase in upgrade scenario"""
        user = Account(
            github_user="upgradeuser",
            github_email="upgrade@example.com",
            account_type="professional",
            marketplace_plan="professional"
        )
        test_db.add(user)
        test_db.commit()
        
        # Create webhook event with previous plan info
        payload = {
            "action": "changed",
            "marketplace_purchase": {
                "account": {
                    "id": 11111,
                    "login": "upgradeuser"
                },
                "plan": {
                    "name": "enterprise",
                    "price": 20000
                },
                "unit_count": 5,
                "on_free_trial": False,
                "next_billing_date": "2025-07-01T00:00:00Z"
            },
            "previous_marketplace_purchase": {
                "plan": {
                    "name": "professional",
                    "price": 4000
                },
                "unit_count": 1
            }
        }
        
        webhook_event = store_webhook_event(
            test_db, "marketplace_purchase", "changed", payload, None
        )
        
        # Process webhook
        success = update_account_from_webhook(test_db, webhook_event, payload)
        
        assert success is True
        
        # Verify account upgraded
        updated_user = test_db.query(Account).filter(Account.github_user == "upgradeuser").first()
        assert updated_user.account_type == "enterprise"
        assert updated_user.marketplace_plan == "enterprise"
        assert updated_user.marketplace_unit_count == 5
    
    def test_update_account_cancelled(self, test_db):
        """Test account update for cancelled event"""
        # Create test user with professional plan
        user = Account(
            github_user="testuser",
            github_email="test@example.com",
            account_type="professional",
            marketplace_plan="professional",
            marketplace_account_id=12345
        )
        test_db.add(user)
        test_db.commit()
        
        # Create webhook event
        payload = {
            "action": "cancelled",
            "marketplace_purchase": {
                "account": {
                    "id": 12345,
                    "login": "testuser"
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
        assert webhook_event.processed is True
        
        # Verify account downgraded
        updated_user = test_db.query(Account).filter(Account.github_user == "testuser").first()
        assert updated_user.account_type == "free"
        assert updated_user.marketplace_plan is None
        assert updated_user.marketplace_unit_count is None
    
    def test_update_account_changed(self, test_db):
        """Test account update for plan change event"""
        # Create test user
        user = Account(
            github_user="testuser",
            github_email="test@example.com",
            account_type="professional"
        )
        test_db.add(user)
        test_db.commit()
        
        # Create webhook event for upgrade
        payload = {
            "action": "changed",
            "marketplace_purchase": {
                "account": {
                    "id": 12345,
                    "login": "testuser"
                },
                "plan": {
                    "name": "enterprise",
                    "price": 20000
                },
                "unit_count": 5
            }
        }
        
        webhook_event = store_webhook_event(
            test_db, "marketplace_purchase", "changed", payload, None
        )
        
        # Process webhook
        success = update_account_from_webhook(test_db, webhook_event, payload)
        
        assert success is True
        
        # Verify account upgraded
        updated_user = test_db.query(Account).filter(Account.github_user == "testuser").first()
        assert updated_user.account_type == "enterprise"
        assert updated_user.marketplace_plan == "enterprise"
        assert updated_user.marketplace_unit_count == 5
    
    def test_update_account_pending_change(self, test_db):
        """Test account update for pending change event"""
        # Create test user
        user = Account(
            github_user="testuser",
            github_email="test@example.com",
            account_type="professional"
        )
        test_db.add(user)
        test_db.commit()
        
        # Create webhook event
        payload = {
            "action": "pending_change",
            "marketplace_purchase": {
                "account": {
                    "id": 12345,
                    "login": "testuser"
                },
                "plan": {
                    "name": "enterprise"
                }
            }
        }
        
        webhook_event = store_webhook_event(
            test_db, "marketplace_purchase", "pending_change", payload, None
        )
        
        # Process webhook
        success = update_account_from_webhook(test_db, webhook_event, payload)
        
        assert success is True
        assert webhook_event.processed is True
        
        # Verify account NOT changed yet (pending)
        updated_user = test_db.query(Account).filter(Account.github_user == "testuser").first()
        assert updated_user.account_type == "professional"  # Should remain unchanged
        assert updated_user.marketplace_updated_at is not None
    
    def test_update_account_new_user(self, test_db):
        """Test account update for user not in database"""
        payload = {
            "action": "purchased",
            "marketplace_purchase": {
                "account": {
                    "id": 12345,
                    "login": "newuser"
                },
                "plan": {
                    "name": "professional"
                }
            }
        }
        
        webhook_event = store_webhook_event(
            test_db, "marketplace_purchase", "purchased", payload, None
        )
        
        # Process webhook
        success = update_account_from_webhook(test_db, webhook_event, payload)
        
        assert success is True
        
        # Verify placeholder account created
        new_user = test_db.query(Account).filter(Account.github_user == "newuser").first()
        assert new_user is not None
        assert new_user.account_type == "professional"
        assert new_user.marketplace_account_id == 12345
    
    def test_update_account_no_user_in_payload(self, test_db):
        """Test account update with missing user in payload"""
        payload = {
            "action": "purchased",
            "marketplace_purchase": {
                "account": {},
                "plan": {
                    "name": "professional"
                }
            }
        }
        
        webhook_event = store_webhook_event(
            test_db, "marketplace_purchase", "purchased", payload, None
        )
        
        # Process webhook
        success = update_account_from_webhook(test_db, webhook_event, payload)
        
        assert success is False
        assert webhook_event.processing_error is not None
        assert "No GitHub user" in webhook_event.processing_error


class TestWebhookEndpoints:
    """Test webhook HTTP endpoints"""
    
    @patch('marketplace_webhooks.verify_webhook_signature')
    def test_webhook_endpoint_valid(self, mock_verify, cloud_client, test_db):
        """Test webhook endpoint with valid request"""
        mock_verify.return_value = True
        
        payload = {
            "action": "purchased",
            "marketplace_purchase": {
                "account": {
                    "id": 12345,
                    "login": "testuser"
                },
                "plan": {
                    "name": "professional"
                }
            }
        }
        
        response = cloud_client.post(
            "/webhooks/marketplace",
            json=payload,
            headers={
                "X-Hub-Signature-256": "sha256=test_signature",
                "X-GitHub-Event": "marketplace_purchase"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert "event_id" in data
    
    @patch('marketplace_webhooks.verify_webhook_signature')
    def test_webhook_endpoint_invalid_signature(self, mock_verify, cloud_client):
        """Test webhook endpoint with invalid signature"""
        mock_verify.return_value = False
        
        payload = {"action": "purchased"}
        
        response = cloud_client.post(
            "/webhooks/marketplace",
            json=payload,
            headers={
                "X-Hub-Signature-256": "sha256=invalid",
                "X-GitHub-Event": "marketplace_purchase"
            }
        )
        
        assert response.status_code == 401
    
    def test_webhook_endpoint_unsupported_event(self, cloud_client):
        """Test webhook endpoint with unsupported event type"""
        payload = {"action": "opened"}

        with patch('marketplace_webhooks.verify_webhook_signature', return_value=True):
            response = cloud_client.post(
                "/webhooks/marketplace",
                json=payload,
                headers={
                    "X-Hub-Signature-256": "sha256=test",
                    "X-GitHub-Event": "pull_request"
                }
            )

        assert response.status_code == 400
        assert "Unsupported event type" in response.json()["detail"]
    
    def test_webhook_endpoint_invalid_action(self, cloud_client):
        """Test webhook endpoint with invalid action"""
        payload = {"action": "invalid_action"}
        
        with patch('marketplace_webhooks.verify_webhook_signature', return_value=True):
            response = cloud_client.post(
                "/webhooks/marketplace",
                json=payload,
                headers={
                    "X-Hub-Signature-256": "sha256=test",
                    "X-GitHub-Event": "marketplace_purchase"
                }
            )
        
        assert response.status_code == 400
        assert "Invalid action" in response.json()["detail"]
    
    def test_list_webhook_events(self, cloud_client, test_db):
        """Test listing webhook events"""
        # Create some test events
        for i in range(3):
            event = MarketplaceWebhookEvent(
                event_type="marketplace_purchase",
                action="purchased",
                github_user=f"user{i}",
                payload='{"test": "data"}',
                processed=i % 2 == 0
            )
            test_db.add(event)
        test_db.commit()
        
        response = cloud_client.get("/webhooks/marketplace/events")
        
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert len(data["events"]) == 3
    
    def test_list_webhook_events_filtered(self, cloud_client, test_db):
        """Test listing webhook events with filter"""
        # Create events with different processing status
        processed_event = MarketplaceWebhookEvent(
            event_type="marketplace_purchase",
            action="purchased",
            payload='{"test": "data"}',
            processed=True
        )
        unprocessed_event = MarketplaceWebhookEvent(
            event_type="marketplace_purchase",
            action="cancelled",
            payload='{"test": "data"}',
            processed=False
        )
        test_db.add(processed_event)
        test_db.add(unprocessed_event)
        test_db.commit()
        
        response = cloud_client.get("/webhooks/marketplace/events?processed=true")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["processed"] is True
    
    def test_retry_webhook_event(self, cloud_client, test_db):
        """Test retrying a failed webhook event"""
        # Create a failed event
        event = MarketplaceWebhookEvent(
            event_type="marketplace_purchase",
            action="purchased",
            payload='{"action": "purchased", "marketplace_purchase": {"account": {"login": "test"}}}',
            processed=False,
            processing_error="Test error"
        )
        test_db.add(event)
        test_db.commit()
        event_id = event.event_id
        
        response = cloud_client.post(f"/webhooks/marketplace/events/{event_id}/retry")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "retry_queued"
    
    def test_retry_already_processed(self, cloud_client, test_db):
        """Test retrying an already processed webhook"""
        event = MarketplaceWebhookEvent(
            event_type="marketplace_purchase",
            action="purchased",
            payload='{"test": "data"}',
            processed=True
        )
        test_db.add(event)
        test_db.commit()
        event_id = event.event_id
        
        response = cloud_client.post(f"/webhooks/marketplace/events/{event_id}/retry")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "already_processed"
    
    def test_retry_nonexistent_event(self, cloud_client):
        """Test retrying a non-existent webhook event"""
        response = cloud_client.post("/webhooks/marketplace/events/99999/retry")
        
        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
