"""
Database migration script to add the ``custom_files`` table.

This migration creates the table used to store locally-managed custom file
content (scripts, action definitions, config files, etc.) per project.
Custom files are deployed to every repository in a project alongside workflow
YAML files and participate in the same PR Campaign / drift-detection lifecycle.

Supports both SQLite and PostgreSQL databases.
"""

import sys
import sqlite3
from pathlib import Path
from migration_utils import get_migration_database_url, get_database_type
# DATABASE_URL from database.py resolves the self-hosted SQLite path
# (/app/data/actions_manager.db) via INSTALLATION_MODE, falling back to the
# development ./test.db only when explicitly running outside self-hosted/prod.
from database import DATABASE_URL as APP_DATABASE_URL


SQLITE_CREATE = """
CREATE TABLE IF NOT EXISTS custom_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    display_name VARCHAR(255),
    file_path VARCHAR(500) NOT NULL,
    file_content TEXT NOT NULL DEFAULT '',
    git_hash VARCHAR(255),
    file_status VARCHAR(30) NOT NULL DEFAULT 'new',
    pending_delete BOOLEAN NOT NULL DEFAULT 0,
    last_modified_by VARCHAR(255),
    description VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    CONSTRAINT uq_custom_file_project_path UNIQUE (project_id, file_path)
)
"""

POSTGRES_CREATE = """
CREATE TABLE IF NOT EXISTS custom_files (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    display_name VARCHAR(255),
    file_path VARCHAR(500) NOT NULL,
    file_content TEXT NOT NULL DEFAULT '',
    git_hash VARCHAR(255),
    file_status VARCHAR(30) NOT NULL DEFAULT 'new',
    pending_delete BOOLEAN NOT NULL DEFAULT FALSE,
    last_modified_by VARCHAR(255),
    description VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_custom_file_project_path UNIQUE (project_id, file_path)
)
"""


def _resolve_sqlite_db_path() -> Path:
    """Resolve the SQLite database file the application actually uses."""
    return Path(APP_DATABASE_URL.replace("sqlite:///", "", 1))


def run_sqlite_migration():
    db_path = _resolve_sqlite_db_path()
    if not db_path.exists():
        print("⚠️ SQLite database file not found.")
        print("   Migration will be applied when database is created.")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='custom_files'"
        )
        if cursor.fetchone():
            print("✅ custom_files table already exists")
            return

        print("✅ Creating custom_files table (SQLite)...")
        cursor.execute(SQLITE_CREATE)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_custom_files_project_id ON custom_files(project_id)"
        )
        conn.commit()
        print("   custom_files table created successfully")
    except Exception as e:
        print(f"❌ SQLite migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


def run_postgresql_migration():
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 module not installed. Please install it to use PostgreSQL.")
        sys.exit(1)

    db_url = get_migration_database_url()
    if not db_url or ('postgresql' not in db_url and 'postgres' not in db_url):
        print("⚠️ DATABASE_URL not set for PostgreSQL")
        return

    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_name='custom_files' AND table_schema = current_schema()
            """)
            if cursor.fetchone():
                print("✅ custom_files table already exists")
                return

            print("✅ Creating custom_files table (PostgreSQL)...")
            cursor.execute(POSTGRES_CREATE)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_custom_files_project_id ON custom_files(project_id)"
            )
            conn.commit()
            print("   custom_files table created successfully")
        except Exception as e:
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
    db_type = get_database_type()
    print(f"🔄 Running custom_files migration for {db_type.upper()}...")
    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()


if __name__ == "__main__":
    run_migration()
