"""
Migration: Add first-class PR campaign tracking.

Adds:
  - project_pr_campaigns table – one row per PR campaign creation run
  - campaign_id column on project_pull_requests – nullable FK linking each
    PR row to the campaign that created it

The campaign_id column is nullable so existing PR rows remain valid; rows
without a campaign are grouped heuristically by the PR Campaigns endpoint.
Supports both SQLite and PostgreSQL databases.
"""

import sqlite3
import sys
import os
from pathlib import Path
from migration_utils import get_migration_database_url, get_database_type
# DATABASE_URL from database.py is the URL the application actually uses at
# runtime: it honors DATABASE_URL/POSTGRES_* env vars and resolves the
# self-hosted SQLite path (/app/data/actions_manager.db) via INSTALLATION_MODE.
from database import DATABASE_URL as APP_DATABASE_URL

SQLITE_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS project_pr_campaigns (
    campaign_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

POSTGRES_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS project_pr_campaigns (
    campaign_id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_TABLE_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_project_pr_campaigns_project_id "
    "ON project_pr_campaigns (project_id)"
)

CREATE_COLUMN_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_project_pull_requests_campaign_id "
    "ON project_pull_requests (campaign_id)"
)


def _resolve_sqlite_db_path() -> Path:
    """Resolve the SQLite database file the application actually uses.

    Uses the application's own resolved DATABASE_URL so the migration always
    targets the live runtime database (self-hosted /app/data/actions_manager.db,
    an explicit DATABASE_URL, or the development ./test.db) instead of guessing
    at file names next to this script.
    """
    return Path(APP_DATABASE_URL.replace("sqlite:///", "", 1))


def run_sqlite_migration():
    """Run the migration for SQLite database."""
    db_path = _resolve_sqlite_db_path()

    if not db_path.exists():
        print(f"⚠️ SQLite database file not found at {db_path}. "
              "Schema will include PR campaigns when the database is created.")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        cursor.execute(SQLITE_CREATE_TABLE)
        cursor.execute(CREATE_TABLE_INDEX)
        print("✅ Ensured table exists: project_pr_campaigns")

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project_pull_requests'"
        )
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(project_pull_requests)")
            existing_columns = {row[1] for row in cursor.fetchall()}
            if "campaign_id" not in existing_columns:
                cursor.execute(
                    "ALTER TABLE project_pull_requests ADD COLUMN campaign_id INTEGER "
                    "REFERENCES project_pr_campaigns (campaign_id) ON DELETE SET NULL"
                )
                print("✅ Added column: project_pull_requests.campaign_id")
            else:
                print("✅ Column already exists (skipped): campaign_id")
            cursor.execute(CREATE_COLUMN_INDEX)
        else:
            print("⚠️ Table 'project_pull_requests' does not exist. Column will be applied when the table is created.")

        conn.commit()
        print("✅ SQLite PR campaigns migration complete.")

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
            cursor.execute(POSTGRES_CREATE_TABLE)
            cursor.execute(CREATE_TABLE_INDEX)
            print("✅ Ensured table exists: project_pr_campaigns")

            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'project_pull_requests'
            """)
            if cursor.fetchone():
                cursor.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'project_pull_requests'
                """)
                existing_columns = {row[0] for row in cursor.fetchall()}
                if "campaign_id" not in existing_columns:
                    cursor.execute(
                        "ALTER TABLE project_pull_requests ADD COLUMN campaign_id INTEGER "
                        "REFERENCES project_pr_campaigns (campaign_id) ON DELETE SET NULL"
                    )
                    print("✅ Added column: project_pull_requests.campaign_id")
                else:
                    print("✅ Column already exists (skipped): campaign_id")
                cursor.execute(CREATE_COLUMN_INDEX)
            else:
                print("⚠️ Table 'project_pull_requests' does not exist. Column will be applied when the table is created.")

            conn.commit()
            print("✅ PostgreSQL PR campaigns migration complete.")

        except Exception as exc:
            err_msg = str(exc).lower()
            if 'must be owner' in err_msg or 'permission denied' in err_msg or 'insufficient privilege' in err_msg:
                print(f"❌ PostgreSQL migration failed: {exc}")
                print()
                print("   ℹ️  The migration user does not own the 'project_pull_requests' table.")
                print("   To fix this, run the following as a PostgreSQL superuser:")
                print()
                pg_user = os.getenv('POSTGRES_USER', '<app_user>')
                print(f"     ALTER TABLE project_pull_requests OWNER TO {pg_user};")
                print()
                print("   Or set dedicated migration credentials in your deployment:")
                print("     POSTGRES_MIGRATION_USER=<superuser>")
                print("     POSTGRES_MIGRATION_PASSWORD=<superuser_password>")
            else:
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
    print(f"🔄 Running PR campaigns migration for {db_type.upper()}...")

    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()


if __name__ == "__main__":
    run_migration()
