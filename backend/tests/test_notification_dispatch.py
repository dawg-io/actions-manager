"""
Tests for shared notification event emission + subscription fan-out
(code review fix, part of #1789).

Covers the previously-missing wiring: without this, an event was recorded
but nothing ever created a NotificationDelivery row for a matching
subscription, so the delivery worker's outbox was always empty.
"""

import sys
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Base, Account, Project, NotificationEvent, NotificationDelivery, NotificationSubscription
from notification_dispatch import emit_notification_event


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


def _setup_project(db):
    account = Account(github_user="dispatchuser", github_email="dispatch@example.com", account_type="free")
    db.add(account)
    db.commit()
    db.refresh(account)

    project = Project(project_name="dispatch_project", project_code="DSP", user_id=account.user_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


class TestEmitNotificationEvent:
    def test_matching_all_projects_subscription_gets_a_delivery(self, db_session):
        project = _setup_project(db_session)
        db_session.add(NotificationSubscription(recipient_email="team@example.com", project_id=None))
        db_session.commit()

        emit_notification_event(db_session, project.project_id, "drift.detected", "dk-1", {"a": 1})
        db_session.commit()

        deliveries = db_session.query(NotificationDelivery).all()
        assert len(deliveries) == 1
        assert deliveries[0].recipient_email == "team@example.com"
        assert deliveries[0].status == "pending"

    def test_subscription_scoped_to_a_different_project_is_not_matched(self, db_session):
        project = _setup_project(db_session)
        # A real second project, not a fabricated id: notification_subscriptions
        # .project_id is a real foreign key, and pointing it at a non-existent
        # project stopped being possible once SQLite enforcement was enabled
        # (issue #1811).
        other_project = Project(
            project_name="other_dispatch_project", project_code="OTH", user_id=project.user_id
        )
        db_session.add(other_project)
        db_session.commit()
        db_session.refresh(other_project)

        db_session.add(NotificationSubscription(
            recipient_email="other@example.com", project_id=other_project.project_id
        ))
        db_session.commit()

        emit_notification_event(db_session, project.project_id, "drift.detected", "dk-2", {})
        db_session.commit()

        assert db_session.query(NotificationDelivery).count() == 0

    def test_subscription_with_event_type_filter_only_matches_selected_types(self, db_session):
        project = _setup_project(db_session)
        db_session.add(NotificationSubscription(
            recipient_email="team@example.com", project_id=None, event_types="campaign.opened,campaign.completed",
        ))
        db_session.commit()

        emit_notification_event(db_session, project.project_id, "drift.detected", "dk-3", {})
        db_session.commit()
        assert db_session.query(NotificationDelivery).count() == 0

        emit_notification_event(db_session, project.project_id, "campaign.opened", "dk-4", {})
        db_session.commit()
        assert db_session.query(NotificationDelivery).count() == 1

    def test_notify_on_resolved_false_skips_drift_resolved_only(self, db_session):
        project = _setup_project(db_session)
        db_session.add(NotificationSubscription(
            recipient_email="team@example.com", project_id=None, notify_on_resolved=False,
        ))
        db_session.commit()

        emit_notification_event(db_session, project.project_id, "drift.resolved", "dk-5", {})
        db_session.commit()
        assert db_session.query(NotificationDelivery).count() == 0

        emit_notification_event(db_session, project.project_id, "drift.detected", "dk-6", {})
        db_session.commit()
        assert db_session.query(NotificationDelivery).count() == 1

    def test_multiple_matching_subscriptions_each_get_their_own_delivery(self, db_session):
        project = _setup_project(db_session)
        db_session.add(NotificationSubscription(recipient_email="a@example.com", project_id=None))
        db_session.add(NotificationSubscription(recipient_email="b@example.com", project_id=project.project_id))
        db_session.commit()

        emit_notification_event(db_session, project.project_id, "campaign.opened", "dk-7", {})
        db_session.commit()

        recipients = {d.recipient_email for d in db_session.query(NotificationDelivery).all()}
        assert recipients == {"a@example.com", "b@example.com"}

    def test_deduplicated_event_returns_none_and_creates_no_new_deliveries(self, db_session):
        project = _setup_project(db_session)
        db_session.add(NotificationSubscription(recipient_email="team@example.com", project_id=None))
        db_session.commit()

        first = emit_notification_event(db_session, project.project_id, "drift.detected", "dk-8", {})
        db_session.commit()
        assert first is not None
        assert db_session.query(NotificationDelivery).count() == 1

        second = emit_notification_event(db_session, project.project_id, "drift.detected", "dk-8", {})
        db_session.commit()
        assert second is None
        assert db_session.query(NotificationDelivery).count() == 1

    def test_no_subscriptions_still_creates_the_event(self, db_session):
        project = _setup_project(db_session)

        event = emit_notification_event(db_session, project.project_id, "drift.detected", "dk-9", {})
        db_session.commit()

        assert event is not None
        assert db_session.query(NotificationEvent).count() == 1
        assert db_session.query(NotificationDelivery).count() == 0
