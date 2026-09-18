"""
Migration: Add pending_delete column to workflows.

Deleting a workflow from GitHub was direct-commit-only: the file was removed
from every branch immediately, with no review. This column lets a deletion ride
a PR Campaign instead, the way CustomFile.pending_delete already does — the
campaign removes the file on the AM branch, and the row is dropped when that
campaign merges.

Existing rows default to false, which is the pre-migration meaning: no workflow
was marked for deletion before this column existed, so there is nothing to
backfill.

Supports both SQLite and PostgreSQL, and is safe to run more than once.
"""

import sqlite3
import sys
from pathlib import Path
from migration_utils import get_migration_database_url, get_database_type
from database import DATABASE_URL as APP_DATABASE_URL


def _resolve_sqlite_db_path() -> Path:
    return Path(APP_DATABASE_URL.replace("sqlite:///", "", 1))


def run_sqlite_migration():
    db_path = _resolve_sqlite_db_path()

    if not db_path.exists():
        print(f"⚠️ SQLite database file not found at {db_path}. "
              "Schema will include pending_delete when the database is created.")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='workflows'"
        )
        if not cursor.fetchone():
            print("⚠️ workflows table does not exist yet, skipping migration")
            return

        cursor.execute("PRAGMA table_info(workflows)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        if "pending_delete" not in existing_columns:
            cursor.execute(
                "ALTER TABLE workflows ADD COLUMN pending_delete "
                "BOOLEAN NOT NULL DEFAULT 0"
            )
            print("✅ Added column: workflows.pending_delete")
        else:
            print("✅ Column already exists (skipped): pending_delete")

        conn.commit()
        print("✅ SQLite workflow pending_delete migration complete.")
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
                WHERE table_schema = 'public' AND table_name = 'workflows'
            """)
            if not cursor.fetchone():
                print("⚠️ workflows table does not exist yet, skipping migration")
                return

            cursor.execute(
                "ALTER TABLE workflows ADD COLUMN IF NOT EXISTS "
                "pending_delete BOOLEAN NOT NULL DEFAULT FALSE"
            )
            print("✅ Ensured column exists: workflows.pending_delete")

            conn.commit()
            print("✅ PostgreSQL workflow pending_delete migration complete.")
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
    print(f"🔄 Running workflow pending_delete migration for {db_type.upper()}...")

    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()


if __name__ == "__main__":
    run_migration()
