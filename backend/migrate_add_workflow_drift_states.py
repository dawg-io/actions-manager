"""
Migration: Add workflow_drift_states table (issue #1793, part of #1789).

Stores the last known per-(workflow, repo) drift check result so drift
notifications can diff a newly-computed check against the previous one to
detect state transitions. No behavior change to existing drift checks.
Supports both SQLite and PostgreSQL.
"""

import sqlite3
import sys
from pathlib import Path
from migration_utils import get_migration_database_url, get_database_type
from database import DATABASE_URL as APP_DATABASE_URL

SQLITE_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS workflow_drift_states (
    state_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    workflow_id INTEGER NOT NULL REFERENCES workflows (workflow_id) ON DELETE CASCADE,
    repo_id INTEGER NOT NULL REFERENCES repos (repo_id) ON DELETE CASCADE,
    has_drift BOOLEAN NOT NULL DEFAULT 0,
    content_hash VARCHAR(64),
    drift_cycle_count INTEGER NOT NULL DEFAULT 0,
    last_checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (workflow_id, repo_id)
)
"""

POSTGRES_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS workflow_drift_states (
    state_id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    workflow_id INTEGER NOT NULL REFERENCES workflows (workflow_id) ON DELETE CASCADE,
    repo_id INTEGER NOT NULL REFERENCES repos (repo_id) ON DELETE CASCADE,
    has_drift BOOLEAN NOT NULL DEFAULT FALSE,
    content_hash VARCHAR(64),
    drift_cycle_count INTEGER NOT NULL DEFAULT 0,
    last_checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (workflow_id, repo_id)
)
"""

CREATE_PROJECT_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_workflow_drift_states_project_id "
    "ON workflow_drift_states (project_id)"
)


def _resolve_sqlite_db_path() -> Path:
    return Path(APP_DATABASE_URL.replace("sqlite:///", "", 1))


def run_sqlite_migration():
    db_path = _resolve_sqlite_db_path()

    if not db_path.exists():
        print(f"⚠️ SQLite database file not found at {db_path}. "
              "Schema will include workflow_drift_states when the database is created.")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        cursor.execute(SQLITE_CREATE_TABLE)
        cursor.execute(CREATE_PROJECT_INDEX)
        conn.commit()
        print("✅ Ensured table exists: workflow_drift_states")
        print("✅ SQLite workflow_drift_states migration complete.")
    except Exception as exc:
        print(f"❌ SQLite migration failed: {exc}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


def run_postgresql_migration():
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
            cursor.execute(POSTGRES_CREATE_TABLE)
            cursor.execute(CREATE_PROJECT_INDEX)
            conn.commit()
            print("✅ Ensured table exists: workflow_drift_states")
            print("✅ PostgreSQL workflow_drift_states migration complete.")
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
    db_type = get_database_type()
    print(f"🔄 Running workflow_drift_states migration for {db_type.upper()}...")

    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()


if __name__ == "__main__":
    run_migration()
