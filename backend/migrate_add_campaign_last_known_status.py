"""
Migration: Add last_known_status column to project_pr_campaigns (issue #1794, part of #1789).

campaign_status is computed live on every read of GET /api/project-pr-campaigns
and never persisted. This column stores the last computed value so campaign
notification emission can detect the one-time open -> terminal transition
without recomputing history. No behavior change to existing campaign reads.
Supports both SQLite and PostgreSQL.
"""

import sqlite3
import sys
from pathlib import Path
from migration_utils import get_migration_database_url, get_database_type
from database import DATABASE_URL as APP_DATABASE_URL

# Backfills last_known_status from each campaign's actual current PR states
# instead of leaving every pre-existing row at the column's 'open' default.
# Mirrors _campaign_status_from_counts's exact logic (workflows.py). Without
# this, an already-completed legacy campaign would look like a fresh
# open -> terminal transition on the first read after this migration ships,
# emitting a backdated campaign.completed notification. Safe to run more
# than once — it only recomputes the current truth from project_pull_requests,
# never touched by the app's own notification-emitting code path.
BACKFILL_LAST_KNOWN_STATUS = """
UPDATE project_pr_campaigns
SET last_known_status = (
    SELECT CASE
        WHEN SUM(CASE WHEN pr_state = 'open' THEN 1 ELSE 0 END) > 0 THEN 'open'
        WHEN SUM(CASE WHEN pr_state = 'merged' THEN 1 ELSE 0 END) > 0
             AND SUM(CASE WHEN pr_state = 'closed' THEN 1 ELSE 0 END) = 0 THEN 'completed'
        WHEN SUM(CASE WHEN pr_state = 'merged' THEN 1 ELSE 0 END) > 0
             AND SUM(CASE WHEN pr_state = 'closed' THEN 1 ELSE 0 END) > 0 THEN 'partially_completed'
        WHEN SUM(CASE WHEN pr_state = 'closed' THEN 1 ELSE 0 END) > 0 THEN 'cancelled'
        ELSE 'open'
    END
    FROM project_pull_requests
    WHERE project_pull_requests.campaign_id = project_pr_campaigns.campaign_id
)
WHERE EXISTS (
    SELECT 1 FROM project_pull_requests
    WHERE project_pull_requests.campaign_id = project_pr_campaigns.campaign_id
)
"""


def _resolve_sqlite_db_path() -> Path:
    return Path(APP_DATABASE_URL.replace("sqlite:///", "", 1))


def run_sqlite_migration():
    db_path = _resolve_sqlite_db_path()

    if not db_path.exists():
        print(f"⚠️ SQLite database file not found at {db_path}. "
              "Schema will include last_known_status when the database is created.")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project_pr_campaigns'"
        )
        if not cursor.fetchone():
            print("⚠️ project_pr_campaigns table does not exist yet, skipping migration")
            return

        cursor.execute("PRAGMA table_info(project_pr_campaigns)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        if "last_known_status" not in existing_columns:
            cursor.execute(
                "ALTER TABLE project_pr_campaigns ADD COLUMN last_known_status "
                "VARCHAR(20) NOT NULL DEFAULT 'open'"
            )
            print("✅ Added column: project_pr_campaigns.last_known_status")
        else:
            print("✅ Column already exists (skipped): last_known_status")

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project_pull_requests'"
        )
        if cursor.fetchone():
            cursor.execute(BACKFILL_LAST_KNOWN_STATUS)
            print("✅ Backfilled last_known_status from current PR states")
        else:
            print("⚠️ project_pull_requests table does not exist yet, skipping backfill")

        conn.commit()
        print("✅ SQLite campaign last_known_status migration complete.")
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
            cursor.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'project_pr_campaigns'
            """)
            if not cursor.fetchone():
                print("⚠️ project_pr_campaigns table does not exist yet, skipping migration")
                return

            cursor.execute(
                "ALTER TABLE project_pr_campaigns ADD COLUMN IF NOT EXISTS "
                "last_known_status VARCHAR(20) NOT NULL DEFAULT 'open'"
            )
            print("✅ Ensured column exists: project_pr_campaigns.last_known_status")

            cursor.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'project_pull_requests'
            """)
            if cursor.fetchone():
                cursor.execute(BACKFILL_LAST_KNOWN_STATUS)
                print("✅ Backfilled last_known_status from current PR states")
            else:
                print("⚠️ project_pull_requests table does not exist yet, skipping backfill")

            conn.commit()
            print("✅ PostgreSQL campaign last_known_status migration complete.")
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
    print(f"🔄 Running campaign last_known_status migration for {db_type.upper()}...")

    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()


if __name__ == "__main__":
    run_migration()
