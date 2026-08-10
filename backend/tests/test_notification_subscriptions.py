"""
Tests for notification subscriptions and delivery history endpoints
(issue #1795, part of #1789).
"""

import sys
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Base, Account, WorkspaceMember, Project, NotificationEvent, NotificationDelivery
from main import app
from database import get_db
from authorization import get_current_user

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


def _create_project(db):
    account = Account(github_user="projowner", github_email="projowner@example.com", account_type="free")
    db.add(account)
    db.commit()
    db.refresh(account)
    project = Project(project_name="notify_target", project_code="NTG", user_id=account.user_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


class TestSubscriptionsEndpoints:
    def test_non_admin_cannot_list(self, db_session):
        _create_user(db_session, "member1", "member")
        response = client.get("/api/notifications/subscriptions")
        assert response.status_code == 403

    def test_create_and_list_subscription(self, db_session):
        _create_user(db_session, "admin1", "admin")
        response = client.post("/api/notifications/subscriptions", json={
            "recipient_email": "team@example.com",
            "project_id": None,
            "event_types": ["drift.detected", "drift.resolved"],
            "notify_on_resolved": True,
        })
        assert response.status_code == 200
        body = response.json()
        assert body["recipient_email"] == "team@example.com"
        assert body["event_types"] == ["drift.detected", "drift.resolved"]

        listed = client.get("/api/notifications/subscriptions")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

    def test_create_rejects_invalid_event_type(self, db_session):
        _create_user(db_session, "admin2", "admin")
        response = client.post("/api/notifications/subscriptions", json={
            "recipient_email": "team@example.com",
            "event_types": ["drift.imaginary_event"],
        })
        assert response.status_code == 422

    def test_create_rejects_invalid_email(self, db_session):
        _create_user(db_session, "admin3", "admin")
        response = client.post("/api/notifications/subscriptions", json={"recipient_email": "not-an-email"})
        assert response.status_code == 422

    def test_create_with_unknown_project_id_returns_404(self, db_session):
        _create_user(db_session, "admin4", "admin")
        response = client.post("/api/notifications/subscriptions", json={
            "recipient_email": "team@example.com",
            "project_id": 999999,
        })
        assert response.status_code == 404

    def test_create_scoped_to_project_includes_project_name(self, db_session):
        _create_user(db_session, "admin5", "admin")
        project = _create_project(db_session)
        response = client.post("/api/notifications/subscriptions", json={
            "recipient_email": "team@example.com",
            "project_id": project.project_id,
        })
        assert response.status_code == 200
        assert response.json()["project_name"] == "notify_target"

    def test_delete_subscription(self, db_session):
        _create_user(db_session, "admin6", "admin")
        created = client.post("/api/notifications/subscriptions", json={"recipient_email": "team@example.com"})
        subscription_id = created.json()["subscription_id"]

        deleted = client.delete(f"/api/notifications/subscriptions/{subscription_id}")
        assert deleted.status_code == 200

        listed = client.get("/api/notifications/subscriptions")
        assert listed.json() == []

    def test_delete_unknown_subscription_returns_404(self, db_session):
        _create_user(db_session, "admin7", "admin")
        response = client.delete("/api/notifications/subscriptions/999999")
        assert response.status_code == 404


class TestDeliveriesEndpoint:
    def test_non_admin_cannot_list_deliveries(self, db_session):
        _create_user(db_session, "member2", "member")
        response = client.get("/api/notifications/deliveries")
        assert response.status_code == 403

    def test_lists_deliveries_with_event_and_project_context(self, db_session):
        _create_user(db_session, "admin8", "admin")
        project = _create_project(db_session)
        event = NotificationEvent(
            project_id=project.project_id,
            event_type="drift.detected",
            dedup_key="drift.detected:1:1:1:hash",
            payload="{}",
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)

        delivery = NotificationDelivery(
            event_id=event.event_id,
            recipient_email="oncall@example.com",
            status="failed",
            attempt_count=5,
            last_error="SMTP authentication failed",
        )
        db_session.add(delivery)
        db_session.commit()

        response = client.get("/api/notifications/deliveries")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["event_type"] == "drift.detected"
        assert body[0]["project_name"] == "notify_target"
        assert body[0]["status"] == "failed"
        assert body[0]["last_error"] == "SMTP authentication failed"

    def test_limit_is_clamped(self, db_session):
        _create_user(db_session, "admin9", "admin")
        response = client.get("/api/notifications/deliveries?limit=99999")
        assert response.status_code == 200
