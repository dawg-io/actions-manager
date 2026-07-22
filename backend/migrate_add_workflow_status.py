"""
Database migration script to add per-workflow status tracking.

This migration adds:
1. workflow_status column to workflows table (new, committed_locally, under_review, synced_with_github)

Supports both SQLite and PostgreSQL databases.
"""

import sqlite3
import sys
import os
from pathlib import Path
from migration_utils import get_migration_database_url, get_database_type
# DATABASE_URL from database.py resolves the self-hosted SQLite path
# (/app/data/actions_manager.db) via INSTALLATION_MODE, falling back to the
# development ./test.db only when explicitly running outside self-hosted/prod.
from database import DATABASE_URL as APP_DATABASE_URL

_MSG_WILL_APPLY = "   Migration will be applied when database is created."


def _resolve_sqlite_db_path() -> Path:
    """Resolve the SQLite database file the application actually uses."""
    return Path(APP_DATABASE_URL.replace("sqlite:///", "", 1))


def run_sqlite_migration():
    """Run the migration for SQLite database."""
    db_path = _resolve_sqlite_db_path()

    if not db_path.exists():
        print("⚠️ SQLite database file not found.")
        print(_MSG_WILL_APPLY)
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check if the workflows table exists at all
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='workflows'"
        )
        if not cursor.fetchone():
            print("   workflows table does not exist yet.")
            print(_MSG_WILL_APPLY)
            return

        # Check if workflow_status column already exists in workflows table
        cursor.execute("PRAGMA table_info(workflows)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'workflow_status' not in columns:
            print("✅ Adding workflow_status column to workflows table (SQLite)...")
            cursor.execute("""
                ALTER TABLE workflows
                ADD COLUMN workflow_status VARCHAR(30) NOT NULL DEFAULT 'new'
            """)
            print("   workflow_status column added successfully")
        else:
            print("✅ workflow_status column already exists in workflows table")

        conn.commit()
        print("✅ SQLite migration completed successfully")

    except Exception as e:
        print(f"❌ SQLite migration failed: {e}")
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
        print("⚠️ DATABASE_URL environment variable not set for PostgreSQL")
        print("   Migration will be applied when database is configured.")
        return

    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()

        try:
            # Check if the workflows table exists at all
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name='workflows'
            """)
            if not cursor.fetchone():
                print("   workflows table does not exist yet.")
                print(_MSG_WILL_APPLY)
                return

            # Check if workflow_status column already exists in workflows table
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='workflows' AND column_name='workflow_status'
            """)

            if not cursor.fetchone():
                print("✅ Adding workflow_status column to workflows table (PostgreSQL)...")
                cursor.execute("""
                    ALTER TABLE workflows
                    ADD COLUMN workflow_status VARCHAR(30) NOT NULL DEFAULT 'new'
                """)
                print("   workflow_status column added successfully")
            else:
                print("✅ workflow_status column already exists in workflows table")

            conn.commit()
            print("✅ PostgreSQL migration completed successfully")

        except Exception as e:
            err_msg = str(e).lower()
            if 'must be owner' in err_msg or 'permission denied' in err_msg or 'insufficient privilege' in err_msg:
                print(f"❌ PostgreSQL migration failed: {e}")
                print()
                print("   ℹ️  The migration user does not own the 'workflows' table.")
                print("   To fix this, run one of the following as a PostgreSQL superuser:")
                print()
                print("     Option 1 – transfer ownership to your app user:")
                pg_user = os.getenv('POSTGRES_USER', '<app_user>')
                print(f"       ALTER TABLE workflows OWNER TO {pg_user};")
                print()
                print("     Option 2 – set dedicated migration credentials in your deployment:")
                print("       POSTGRES_MIGRATION_USER=<superuser>")
                print("       POSTGRES_MIGRATION_PASSWORD=<superuser_password>")
            else:
                print(f"❌ PostgreSQL migration failed: {e}")
            conn.rollback()
            sys.exit(1)
        finally:
            cursor.close()
            conn.close()

    except Exception as e:
        print(f"❌ Failed to connect to PostgreSQL database: {e}")
        sys.exit(1)


def run_migration():
    """Run the appropriate migration based on database type."""
    db_type = get_database_type()
    print(f"🔄 Running workflow_status migration for {db_type.upper()}...")

    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()


if __name__ == "__main__":
    run_migration()
