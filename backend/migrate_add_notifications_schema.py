"""
Migration: Add notification system foundation tables (issue #1790, part of #1789).

Adds:
  - notification_events        – domain events (drift/campaign transitions), deduplicated
  - notification_deliveries    – outbox rows tracking per-recipient delivery status/retries
  - notification_subscriptions – per-recipient project/event-type preferences
  - notification_settings      – single-row global notification enable/disable

No behavior change — pure schema addition. Supports both SQLite and PostgreSQL.
"""

import sqlite3
import sys
from pathlib import Path
from migration_utils import get_migration_database_url, get_database_type
# DATABASE_URL from database.py is the URL the application actually uses at
# runtime: it honors DATABASE_URL/POSTGRES_* env vars and resolves the
# self-hosted SQLite path (/app/data/actions_manager.db) via INSTALLATION_MODE.
from database import DATABASE_URL as APP_DATABASE_URL

SQLITE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS notification_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
        event_type VARCHAR(100) NOT NULL,
        dedup_key VARCHAR(500) NOT NULL UNIQUE,
        payload TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_notification_events_project_id ON notification_events (project_id)",
    "CREATE INDEX IF NOT EXISTS ix_notification_events_event_type ON notification_events (event_type)",
    "CREATE INDEX IF NOT EXISTS ix_notification_events_created_at ON notification_events (created_at)",
    """
    CREATE TABLE IF NOT EXISTS notification_deliveries (
        delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL REFERENCES notification_events (event_id) ON DELETE CASCADE,
        recipient_email VARCHAR(255) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        attempt_count INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        sent_at TIMESTAMP,
        next_attempt_at TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_notification_deliveries_event_id ON notification_deliveries (event_id)",
    "CREATE INDEX IF NOT EXISTS ix_notification_deliveries_status ON notification_deliveries (status)",
    "CREATE INDEX IF NOT EXISTS ix_notification_deliveries_next_attempt_at ON notification_deliveries (next_attempt_at)",
    """
    CREATE TABLE IF NOT EXISTS notification_subscriptions (
        subscription_id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient_email VARCHAR(255) NOT NULL,
        project_id INTEGER REFERENCES projects (project_id) ON DELETE CASCADE,
        event_types TEXT,
        notify_on_resolved BOOLEAN NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_notification_subscriptions_recipient_email ON notification_subscriptions (recipient_email)",
    "CREATE INDEX IF NOT EXISTS ix_notification_subscriptions_project_id ON notification_subscriptions (project_id)",
    """
    CREATE TABLE IF NOT EXISTS notification_settings (
        settings_id INTEGER PRIMARY KEY AUTOINCREMENT,
        notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
]

POSTGRES_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS notification_events (
        event_id SERIAL PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
        event_type VARCHAR(100) NOT NULL,
        dedup_key VARCHAR(500) NOT NULL UNIQUE,
        payload TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_notification_events_project_id ON notification_events (project_id)",
    "CREATE INDEX IF NOT EXISTS ix_notification_events_event_type ON notification_events (event_type)",
    "CREATE INDEX IF NOT EXISTS ix_notification_events_created_at ON notification_events (created_at)",
    """
    CREATE TABLE IF NOT EXISTS notification_deliveries (
        delivery_id SERIAL PRIMARY KEY,
        event_id INTEGER NOT NULL REFERENCES notification_events (event_id) ON DELETE CASCADE,
        recipient_email VARCHAR(255) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        attempt_count INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        sent_at TIMESTAMP,
        next_attempt_at TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_notification_deliveries_event_id ON notification_deliveries (event_id)",
    "CREATE INDEX IF NOT EXISTS ix_notification_deliveries_status ON notification_deliveries (status)",
    "CREATE INDEX IF NOT EXISTS ix_notification_deliveries_next_attempt_at ON notification_deliveries (next_attempt_at)",
    """
    CREATE TABLE IF NOT EXISTS notification_subscriptions (
        subscription_id SERIAL PRIMARY KEY,
        recipient_email VARCHAR(255) NOT NULL,
        project_id INTEGER REFERENCES projects (project_id) ON DELETE CASCADE,
        event_types TEXT,
        notify_on_resolved BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_notification_subscriptions_recipient_email ON notification_subscriptions (recipient_email)",
    "CREATE INDEX IF NOT EXISTS ix_notification_subscriptions_project_id ON notification_subscriptions (project_id)",
    """
    CREATE TABLE IF NOT EXISTS notification_settings (
        settings_id SERIAL PRIMARY KEY,
        notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
]


def _resolve_sqlite_db_path() -> Path:
    """Resolve the SQLite database file the application actually uses."""
    return Path(APP_DATABASE_URL.replace("sqlite:///", "", 1))


def run_sqlite_migration():
    """Run the migration for SQLite database."""
    db_path = _resolve_sqlite_db_path()

    if not db_path.exists():
        print(f"⚠️ SQLite database file not found at {db_path}. "
              "Schema will include notification tables when the database is created.")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        for statement in SQLITE_STATEMENTS:
            cursor.execute(statement)
        conn.commit()
        print("✅ Ensured tables exist: notification_events, notification_deliveries, "
              "notification_subscriptions, notification_settings")
        print("✅ SQLite notifications schema migration complete.")

    except Exception as exc:
        print(f"❌ SQLite migration failed: {exc}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


def run_postgresql_migration():
    """Run the migration for PostgreSQL database."""
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 module not installed. Please install it to use PostgreSQL.")
        print("   Run: pip install psycopg2-binary")
        sys.exit(1)

    db_url = get_migration_database_url()

    if not db_url or ('postgresql' not in db_url and 'postgres' not in db_url):
        print("⚠️ DATABASE_URL environment variable not set for PostgreSQL.")
        print("   Migration will be applied when database is configured.")
        return

    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()

        try:
            for statement in POSTGRES_STATEMENTS:
                cursor.execute(statement)
            conn.commit()
            print("✅ Ensured tables exist: notification_events, notification_deliveries, "
                  "notification_subscriptions, notification_settings")
            print("✅ PostgreSQL notifications schema migration complete.")

        except Exception as exc:
            print(f"❌ PostgreSQL migration failed: {exc}")
            conn.rollback()
            sys.exit(1)
        finally:
            cursor.close()
            conn.close()

    except Exception as exc:
        print(f"❌ Failed to connect to PostgreSQL database: {exc}")
        sys.exit(1)


def run_migration():
    """Run the appropriate migration based on database type."""
    db_type = get_database_type()
    print(f"🔄 Running notifications schema migration for {db_type.upper()}...")

    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()


if __name__ == "__main__":
    run_migration()
