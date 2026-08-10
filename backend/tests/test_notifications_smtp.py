"""
Tests for the Send Test Email endpoint (issue #1791, part of #1789).

POST /api/notifications/test-email — admin-only, surfaces specific SMTP
connection/auth/config errors instead of a generic failure.
"""

import smtplib
import sys
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Base, Account, WorkspaceMember
from main import app
from database import get_db
from authorization import get_current_user
import email_sender

client = TestClient(app)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def _create_user(db, github_user, role):
    account = Account(github_user=github_user, github_email=f"{github_user}@example.com", account_type="free")
    db.add(account)
    db.commit()
    db.refresh(account)
    db.add(WorkspaceMember(user_id=account.user_id, workspace_role=role))
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: account
    return account


class TestSendTestEmailEndpoint:
    def test_non_admin_is_rejected(self, db_session):
        _create_user(db_session, "member1", "member")
        response = client.post("/api/notifications/test-email", json={"recipient_email": "a@example.com"})
        assert response.status_code == 403

    def test_invalid_email_is_rejected(self, db_session):
        _create_user(db_session, "admin1", "admin")
        response = client.post("/api/notifications/test-email", json={"recipient_email": "not-an-email"})
        assert response.status_code == 422

    def test_missing_smtp_config_returns_400(self, db_session, monkeypatch):
        _create_user(db_session, "admin2", "admin")
        monkeypatch.delenv("SMTP_HOST", raising=False)
        monkeypatch.delenv("SMTP_FROM_ADDRESS", raising=False)
        response = client.post("/api/notifications/test-email", json={"recipient_email": "a@example.com"})
        assert response.status_code == 400
        assert "SMTP is not configured" in response.json()["detail"]

    def test_successful_send_returns_200(self, db_session, monkeypatch):
        _create_user(db_session, "admin3", "admin")
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_FROM_ADDRESS", "notify@example.com")

        with patch.object(email_sender.smtplib, "SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_server
            response = client.post("/api/notifications/test-email", json={"recipient_email": "a@example.com"})

        assert response.status_code == 200
        mock_server.sendmail.assert_called_once()

    def test_smtp_auth_failure_returns_502_with_specific_detail(self, db_session, monkeypatch):
        _create_user(db_session, "admin4", "admin")
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_FROM_ADDRESS", "notify@example.com")
        monkeypatch.setenv("SMTP_USERNAME", "user")
        monkeypatch.setenv("SMTP_PASSWORD", "pass")

        with patch.object(email_sender.smtplib, "SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad credentials")
            mock_smtp_cls.return_value.__enter__.return_value = mock_server
            response = client.post("/api/notifications/test-email", json={"recipient_email": "a@example.com"})

        assert response.status_code == 502
        assert "authentication failed" in response.json()["detail"].lower()
