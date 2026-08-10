"""
Tests for the notification delivery worker (issue #1792, part of #1789).

Seeds outbox rows directly — no real drift/campaign producers needed yet.
Mocks smtplib.SMTP at the boundary via email_sender, same as issue #1791's tests.
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Base, Account, Project, NotificationEvent, NotificationDelivery
import email_sender
from notification_worker import (
    deliver_pending_notifications,
    notification_worker_loop,
    start_notification_worker,
    stop_notification_worker,
    MAX_ATTEMPTS,
)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def smtp_env(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM_ADDRESS", "notify@example.com")


def _seed_event_and_delivery(db, **delivery_overrides):
    account = Account(github_user="wu", github_email="wu@example.com", account_type="free")
    db.add(account)
    db.commit()
    db.refresh(account)

    project = Project(project_name="wu_project", project_code="WKR", user_id=account.user_id)
    db.add(project)
    db.commit()
    db.refresh(project)

    event = NotificationEvent(
        project_id=project.project_id,
        event_type="drift.detected",
        dedup_key=f"drift.detected:{project.project_id}:1:1:hash",
        payload='{"workflow_name": "ci.yml"}',
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    delivery_kwargs = dict(event_id=event.event_id, recipient_email="oncall@example.com")
    delivery_kwargs.update(delivery_overrides)
    delivery = NotificationDelivery(**delivery_kwargs)
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    return event, delivery


class TestDeliverPendingNotifications:
    def test_successful_delivery_marks_sent(self, db_session):
        _, delivery = _seed_event_and_delivery(db_session)

        with patch.object(email_sender.smtplib, "SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_server
            processed = deliver_pending_notifications(db_session)

        db_session.refresh(delivery)
        assert processed == 1
        assert delivery.status == "sent"
        assert delivery.sent_at is not None
        mock_server.sendmail.assert_called_once()

    def test_failed_delivery_schedules_retry_with_backoff(self, db_session):
        _, delivery = _seed_event_and_delivery(db_session)

        with patch.object(email_sender.smtplib, "SMTP") as mock_smtp_cls:
            mock_smtp_cls.side_effect = ConnectionRefusedError("refused")
            deliver_pending_notifications(db_session)

        db_session.refresh(delivery)
        assert delivery.status == "pending"
        assert delivery.attempt_count == 1
        assert delivery.next_attempt_at is not None
        assert delivery.next_attempt_at > datetime.now(timezone.utc).replace(tzinfo=None)
        assert "Could not connect" in delivery.last_error

    def test_delivery_marked_failed_after_max_attempts(self, db_session):
        _, delivery = _seed_event_and_delivery(db_session, attempt_count=MAX_ATTEMPTS - 1)

        with patch.object(email_sender.smtplib, "SMTP") as mock_smtp_cls:
            mock_smtp_cls.side_effect = ConnectionRefusedError("refused")
            deliver_pending_notifications(db_session)

        db_session.refresh(delivery)
        assert delivery.status == "failed"
        assert delivery.attempt_count == MAX_ATTEMPTS

    def test_delivery_not_yet_due_is_skipped(self, db_session):
        _, delivery = _seed_event_and_delivery(
            db_session, next_attempt_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
        )

        with patch.object(email_sender.smtplib, "SMTP") as mock_smtp_cls:
            processed = deliver_pending_notifications(db_session)

        db_session.refresh(delivery)
        assert processed == 0
        assert delivery.status == "pending"
        mock_smtp_cls.assert_not_called()

    def test_already_sent_delivery_is_not_reprocessed(self, db_session):
        _, delivery = _seed_event_and_delivery(db_session, status="sent")

        with patch.object(email_sender.smtplib, "SMTP") as mock_smtp_cls:
            processed = deliver_pending_notifications(db_session)

        assert processed == 0
        mock_smtp_cls.assert_not_called()

    def test_missing_smtp_config_schedules_retry_without_crashing(self, db_session, monkeypatch):
        monkeypatch.delenv("SMTP_HOST", raising=False)
        monkeypatch.delenv("SMTP_FROM_ADDRESS", raising=False)
        _, delivery = _seed_event_and_delivery(db_session)

        deliver_pending_notifications(db_session)

        db_session.refresh(delivery)
        assert delivery.status == "pending"
        assert delivery.attempt_count == 1
        assert "not configured" in delivery.last_error.lower()


class TestNotificationWorkerLoop:
    @pytest.mark.asyncio
    async def test_loop_sleeps_before_first_poll_so_cancel_never_touches_db(self):
        session_factory = MagicMock(side_effect=AssertionError("DB should not be touched before first sleep completes"))

        task = asyncio.create_task(notification_worker_loop(session_factory, poll_interval_seconds=60))
        await asyncio.sleep(0)  # let the task start and hit the sleep
        await stop_notification_worker(task)

        session_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_and_stop_notification_worker(self):
        session_factory = MagicMock(side_effect=AssertionError("DB should not be touched before first sleep completes"))
        task = start_notification_worker(session_factory)
        assert not task.done()
        await stop_notification_worker(task)
        assert task.cancelled() or task.done()
