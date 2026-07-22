"""
Database migration script to add the ``codeowners`` table.

This migration creates the table used to store locally-managed CODEOWNERS
file content per (project, repo).  See ``models.Codeowners`` for the schema.

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
CREATE TABLE IF NOT EXISTS codeowners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    repo_id INTEGER NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    file_path VARCHAR(64) NOT NULL DEFAULT '.github/CODEOWNERS',
    git_hash VARCHAR(255),
    status VARCHAR(30) NOT NULL DEFAULT 'new',
    last_modified_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY(repo_id) REFERENCES repos(repo_id) ON DELETE CASCADE,
    CONSTRAINT uq_codeowners_project_repo UNIQUE (project_id, repo_id)
)
"""

POSTGRES_CREATE = """
CREATE TABLE IF NOT EXISTS codeowners (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    repo_id INTEGER NOT NULL REFERENCES repos(repo_id) ON DELETE CASCADE,
    content TEXT NOT NULL DEFAULT '',
    file_path VARCHAR(64) NOT NULL DEFAULT '.github/CODEOWNERS',
    git_hash VARCHAR(255),
    status VARCHAR(30) NOT NULL DEFAULT 'new',
    last_modified_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_codeowners_project_repo UNIQUE (project_id, repo_id)
)
"""


def _resolve_sqlite_db_path() -> Path:
    """Resolve the SQLite database file the application actually uses."""
    return Path(APP_DATABASE_URL.replace("sqlite:///", "", 1))


def run_sqlite_migration():
    """Run the migration for SQLite database."""
    db_path = _resolve_sqlite_db_path()
    if not db_path.exists():
        print("⚠️ SQLite database file not found.")
        print("   Migration will be applied when database is created.")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='codeowners'"
        )
        if cursor.fetchone():
            print("✅ codeowners table already exists")
            return

        print("✅ Creating codeowners table (SQLite)...")
        cursor.execute(SQLITE_CREATE)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_codeowners_project_id ON codeowners(project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_codeowners_repo_id ON codeowners(repo_id)")
        conn.commit()
        print("   codeowners table created successfully")
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
                WHERE table_name='codeowners'
            """)
            if cursor.fetchone():
                print("✅ codeowners table already exists")
                return

            print("✅ Creating codeowners table (PostgreSQL)...")
            cursor.execute(POSTGRES_CREATE)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_codeowners_project_id ON codeowners(project_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_codeowners_repo_id ON codeowners(repo_id)")
            conn.commit()
            print("   codeowners table created successfully")
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
    print(f"🔄 Running codeowners migration for {db_type.upper()}...")
    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()


if __name__ == "__main__":
    run_migration()
