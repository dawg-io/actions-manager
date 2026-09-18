"""
Migration: Add renamed_from column to workflows.

Renaming a workflow changed workflow_name in place, which destroyed the only
record of the name the file was delivered under. Delivery could then write the
new filename but had no way to remove the old one, so every rename left an
orphan in every repository and the user was told to go delete it by hand.

Git has no rename operation — a rename is a remove plus an add that the diff
detects — so carrying both halves in one campaign is what makes GitHub show the
change as a rename and finish it on merge. This column is the old half.

NULL means "no rename is outstanding", which is the pre-migration meaning for
every existing row: nothing recorded a previous name before this column
existed, so there is nothing to backfill. Renames made before this migration
keep their orphans; there is no way to recover a name that was never stored.

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
              "Schema will include renamed_from when the database is created.")
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
        if "renamed_from" not in existing_columns:
            cursor.execute(
                "ALTER TABLE workflows ADD COLUMN renamed_from "
                "VARCHAR(255)"
            )
            print("✅ Added column: workflows.renamed_from")
        else:
            print("✅ Column already exists (skipped): renamed_from")

        conn.commit()
        print("✅ SQLite workflow renamed_from migration complete.")
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
                "renamed_from VARCHAR(255)"
            )
            print("✅ Ensured column exists: workflows.renamed_from")

            conn.commit()
            print("✅ PostgreSQL workflow renamed_from migration complete.")
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
    print(f"🔄 Running workflow renamed_from migration for {db_type.upper()}...")

    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()


if __name__ == "__main__":
    run_migration()
