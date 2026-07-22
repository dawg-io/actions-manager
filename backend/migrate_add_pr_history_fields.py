"""
Migration: Add PR history fields to project_pull_requests table.

Adds the following columns to support the Pull Request History feature:
  - title          VARCHAR(500)  – PR title captured from GitHub at creation time
  - author         VARCHAR(255)  – PR author's GitHub login
  - body           TEXT          – PR description/body from GitHub
  - merged_at      TIMESTAMP     – When the PR was merged (NULL if not merged)
  - closed_at      TIMESTAMP     – When the PR was closed without merge (NULL if not)
  - workflow_names TEXT          – Comma-separated list of associated workflow names

These columns are nullable so existing rows remain valid after migration.
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

# ---------------------------------------------------------------------------
# New columns to add (column_name, SQL type)
# ---------------------------------------------------------------------------
NEW_COLUMNS = [
    ("title",          "VARCHAR(500)"),
    ("author",         "VARCHAR(255)"),
    ("body",           "TEXT"),
    ("merged_at",      "TIMESTAMP"),
    ("closed_at",      "TIMESTAMP"),
    ("workflow_names", "TEXT"),
]


def _resolve_sqlite_db_path() -> Path:
    """Resolve the SQLite database file the application actually uses."""
    return Path(APP_DATABASE_URL.replace("sqlite:///", "", 1))


def run_sqlite_migration():
    """Run the migration for SQLite database."""
    db_path = _resolve_sqlite_db_path()

    if not db_path.exists():
        print("⚠️ SQLite database file not found. Migration will be applied when database is created.")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Verify the target table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project_pull_requests'"
        )
        if not cursor.fetchone():
            print("⚠️ Table 'project_pull_requests' does not exist. Migration will be applied when the table is created.")
            conn.close()
            return

        # Determine which columns are already present
        cursor.execute("PRAGMA table_info(project_pull_requests)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        added = []

        for col_name, col_type in NEW_COLUMNS:
            if col_name not in existing_columns:
                cursor.execute(
                    f"ALTER TABLE project_pull_requests ADD COLUMN {col_name} {col_type}"
                )
                added.append(col_name)
                print(f"✅ Added column: {col_name} {col_type}")
            else:
                print(f"✅ Column already exists (skipped): {col_name}")

        conn.commit()
        if added:
            print(f"✅ SQLite migration complete. Added {len(added)} column(s): {', '.join(added)}")
        else:
            print("✅ SQLite migration complete. No new columns needed.")

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
            # Verify the target table exists
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'project_pull_requests'
            """)
            if not cursor.fetchone():
                print("⚠️ Table 'project_pull_requests' does not exist. Migration will be applied when the table is created.")
                return

            # Fetch all existing column names for the table
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'project_pull_requests'
            """)
            existing_columns = {row[0] for row in cursor.fetchall()}
            added = []

            for col_name, col_type in NEW_COLUMNS:
                if col_name not in existing_columns:
                    cursor.execute(
                        f"ALTER TABLE project_pull_requests ADD COLUMN {col_name} {col_type}"
                    )
                    added.append(col_name)
                    print(f"✅ Added column: {col_name} {col_type}")
                else:
                    print(f"✅ Column already exists (skipped): {col_name}")

            conn.commit()
            if added:
                print(f"✅ PostgreSQL migration complete. Added {len(added)} column(s): {', '.join(added)}")
            else:
                print("✅ PostgreSQL migration complete. No new columns needed.")

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
    print(f"🔄 Running PR history fields migration for {db_type.upper()}...")

    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()


if __name__ == "__main__":
    run_migration()
