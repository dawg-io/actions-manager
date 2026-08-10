"""
Migration: Add project_display_order table (issue #1804).

Stores each user's manual ordering of the Projects grid. Previously the grid
sorted by projects.updated_at, so opening or editing a project moved it to the
front. Position is per user, so one user's arrangement never affects another's,
and reordering never touches projects.updated_at.
Supports both SQLite and PostgreSQL.
"""

import sqlite3
import sys
from pathlib import Path
from migration_utils import get_migration_database_url, get_database_type
from database import DATABASE_URL as APP_DATABASE_URL

SQLITE_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS project_display_order (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES accounts (user_id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_project_display_order UNIQUE (user_id, project_id)
)
"""

POSTGRES_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS project_display_order (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES accounts (user_id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_project_display_order UNIQUE (user_id, project_id)
)
"""

CREATE_USER_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_project_display_order_user_id "
    "ON project_display_order (user_id)"
)

CREATE_PROJECT_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_project_display_order_project_id "
    "ON project_display_order (project_id)"
)


def _resolve_sqlite_db_path() -> Path:
    return Path(APP_DATABASE_URL.replace("sqlite:///", "", 1))


def run_sqlite_migration():
    db_path = _resolve_sqlite_db_path()

    if not db_path.exists():
        print(f"⚠️ SQLite database file not found at {db_path}. "
              "Schema will include project_display_order when the database is created.")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # The table's FKs reference accounts and projects. On a database old
        # enough to predate either, creating it would fail — skip instead, the
        # table is created from the model when those tables first appear.
        for required in ("accounts", "projects"):
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (required,)
            )
            if not cursor.fetchone():
                print(f"⚠️ {required} table does not exist yet, skipping migration")
                return

        cursor.execute(SQLITE_CREATE_TABLE)
        cursor.execute(CREATE_USER_INDEX)
        cursor.execute(CREATE_PROJECT_INDEX)
        conn.commit()
        print("✅ Ensured table exists: project_display_order")
        print("✅ SQLite project_display_order migration complete.")
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
                WHERE table_schema = 'public' AND table_name IN ('accounts', 'projects')
            """)
            if len(cursor.fetchall()) < 2:
                print("⚠️ accounts/projects tables do not exist yet, skipping migration")
                return

            cursor.execute(POSTGRES_CREATE_TABLE)
            cursor.execute(CREATE_USER_INDEX)
            cursor.execute(CREATE_PROJECT_INDEX)
            conn.commit()
            print("✅ Ensured table exists: project_display_order")
            print("✅ PostgreSQL project_display_order migration complete.")
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
    print(f"🔄 Running project_display_order migration for {db_type.upper()}...")

    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()


if __name__ == "__main__":
    run_migration()
