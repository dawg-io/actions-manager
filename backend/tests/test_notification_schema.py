"""
Tests for the notification system foundation schema (issue #1790, part of #1789).

Verifies:
- NotificationEvent/NotificationDelivery/NotificationSubscription/NotificationSettings
  can be created and queried through the ORM
- dedup_key uniqueness on notification_events is enforced
- The SQLite migration creates all four tables and is idempotent
"""

import sys
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (
    Base, Account, Project,
    NotificationEvent, NotificationDelivery, NotificationSubscription, NotificationSettings,
)

TEST_USER = "notifyuser"
TEST_PROJECT = "notify_project"


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


def _create_account_and_project(db):
    account = Account(
        github_user=TEST_USER,
        github_email="notify@example.com",
        account_type="free",
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    project = Project(
        project_name=TEST_PROJECT,
        project_code="NTF",
        user_id=account.user_id,
        branch_option="default",
        reusable_workflows_enabled=False,
        pr_state="synced",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return account, project


class TestNotificationModels:
    def test_event_and_delivery_created_and_linked(self, db_session):
        _, project = _create_account_and_project(db_session)

        event = NotificationEvent(
            project_id=project.project_id,
            event_type="drift.detected",
            dedup_key=f"drift.detected:{project.project_id}:1:1:abc123",
            payload='{"workflow_name": "ci.yml"}',
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)

        delivery = NotificationDelivery(
            event_id=event.event_id,
            recipient_email="oncall@example.com",
        )
        db_session.add(delivery)
        db_session.commit()
        db_session.refresh(delivery)

        assert delivery.status == "pending"
        assert delivery.attempt_count == 0
        assert delivery.event_id == event.event_id

    def test_dedup_key_must_be_unique(self, db_session):
        _, project = _create_account_and_project(db_session)
        dedup_key = f"drift.detected:{project.project_id}:1:1:abc123"

        db_session.add(NotificationEvent(
            project_id=project.project_id, event_type="drift.detected",
            dedup_key=dedup_key, payload="{}",
        ))
        db_session.commit()

        db_session.add(NotificationEvent(
            project_id=project.project_id, event_type="drift.detected",
            dedup_key=dedup_key, payload="{}",
        ))
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_subscription_defaults_notify_on_resolved_true(self, db_session):
        _, project = _create_account_and_project(db_session)

        subscription = NotificationSubscription(
            recipient_email="team@example.com",
            project_id=project.project_id,
        )
        db_session.add(subscription)
        db_session.commit()
        db_session.refresh(subscription)

        assert subscription.notify_on_resolved is True
        assert subscription.event_types is None

    def test_subscription_project_id_null_means_all_projects(self, db_session):
        subscription = NotificationSubscription(recipient_email="team@example.com")
        db_session.add(subscription)
        db_session.commit()
        db_session.refresh(subscription)

        assert subscription.project_id is None

    def test_settings_defaults_enabled_true(self, db_session):
        settings = NotificationSettings()
        db_session.add(settings)
        db_session.commit()
        db_session.refresh(settings)

        assert settings.notifications_enabled is True


class TestNotificationSchemaMigration:
    def test_sqlite_migration_creates_tables_and_is_idempotent(self, tmp_path, monkeypatch):
        """The migration must target the application's resolved database
        (e.g. /app/data/actions_manager.db in self-hosted mode), not a
        hard-coded file next to the migration script."""
        import sqlite3
        import migrate_add_notifications_schema as migration

        db_file = tmp_path / "actions_manager.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE projects (project_id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        monkeypatch.setattr(migration, "APP_DATABASE_URL", f"sqlite:///{db_file}")
        migration.run_sqlite_migration()

        conn = sqlite3.connect(str(db_file))
        try:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            assert {
                "notification_events",
                "notification_deliveries",
                "notification_subscriptions",
                "notification_settings",
            }.issubset(tables)

            # Idempotent: running again must not fail
            migration.run_sqlite_migration()
        finally:
            conn.close()

    def test_sqlite_migration_skips_when_db_file_missing(self, tmp_path, monkeypatch):
        import migrate_add_notifications_schema as migration

        missing_db_file = tmp_path / "does_not_exist.db"
        monkeypatch.setattr(migration, "APP_DATABASE_URL", f"sqlite:///{missing_db_file}")

        # Should not raise even though the database file doesn't exist yet.
        migration.run_sqlite_migration()
