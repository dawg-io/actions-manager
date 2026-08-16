"""
Migration: Add the campaign rollback columns.

Adds rollback_of_campaign_id — the campaign this one reverts, so a rollback
campaign and its source are linked in the UI — and rollback_am_action, which
records what the user chose to happen to ActionsManager's stored copy once the
rollback lands ("revert" adopts what is then on GitHub, "keep" holds the
ActionsManager version and lets drift report the divergence).

Both are nullable: every campaign that is not a rollback keeps NULL, which is
also what every pre-existing campaign reads back as.

rollback_of_campaign_id is added as a plain INTEGER with no foreign key.
SQLite cannot ALTER TABLE ADD a column carrying a REFERENCES clause, so the
declared self-FK in models.py only takes effect on databases created fresh from
create_all — the same asymmetry migrate_add_pr_campaigns.py already accepted for
project_pull_requests.campaign_id.

Supports both SQLite and PostgreSQL.
"""

import sqlite3
import sys
from pathlib import Path
from migration_utils import get_migration_database_url, get_database_type
from database import DATABASE_URL as APP_DATABASE_URL

# column name -> SQL type, shared by both backends
ROLLBACK_COLUMNS = {
    "rollback_of_campaign_id": "INTEGER",
    "rollback_am_action": "VARCHAR(20)",
}


def _resolve_sqlite_db_path() -> Path:
    return Path(APP_DATABASE_URL.replace("sqlite:///", "", 1))


def run_sqlite_migration():
    db_path = _resolve_sqlite_db_path()

    if not db_path.exists():
        print(f"⚠️ SQLite database file not found at {db_path}. "
              "Schema will include the campaign rollback columns when the database is created.")
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
        for column, sql_type in ROLLBACK_COLUMNS.items():
            if column in existing_columns:
                print(f"✅ Column already exists (skipped): {column}")
                continue
            cursor.execute(f"ALTER TABLE project_pr_campaigns ADD COLUMN {column} {sql_type}")
            print(f"✅ Added column: project_pr_campaigns.{column}")

        conn.commit()
        print("✅ SQLite campaign rollback migration complete.")
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

            for column, sql_type in ROLLBACK_COLUMNS.items():
                cursor.execute(
                    f"ALTER TABLE project_pr_campaigns ADD COLUMN IF NOT EXISTS {column} {sql_type}"
                )
                print(f"✅ Ensured column exists: project_pr_campaigns.{column}")

            conn.commit()
            print("✅ PostgreSQL campaign rollback migration complete.")
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
    print(f"🔄 Running campaign rollback migration for {db_type.upper()}...")

    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()


if __name__ == "__main__":
    run_migration()
