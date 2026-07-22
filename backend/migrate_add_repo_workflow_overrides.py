"""
Database migration script to add the ``repo_workflow_overrides`` table.

This migration creates the table used to record per-repository workflow
overrides for the scope-aware drift resolution flow.  See
``models.RepoWorkflowOverride`` for schema details.

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
CREATE TABLE IF NOT EXISTS repo_workflow_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    repo_id INTEGER NOT NULL,
    workflow_id INTEGER NOT NULL,
    workflow_name VARCHAR(255) NOT NULL,
    workflow_yaml TEXT NOT NULL,
    workflow_git_hash VARCHAR(255),
    source_repo_name VARCHAR(255),
    last_modified_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY(repo_id) REFERENCES repos(repo_id) ON DELETE CASCADE,
    FOREIGN KEY(workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE,
    CONSTRAINT uq_repo_workflow_override UNIQUE (project_id, repo_id, workflow_id)
)
"""

POSTGRES_CREATE = """
CREATE TABLE IF NOT EXISTS repo_workflow_overrides (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    repo_id INTEGER NOT NULL REFERENCES repos(repo_id) ON DELETE CASCADE,
    workflow_id INTEGER NOT NULL REFERENCES workflows(workflow_id) ON DELETE CASCADE,
    workflow_name VARCHAR(255) NOT NULL,
    workflow_yaml TEXT NOT NULL,
    workflow_git_hash VARCHAR(255),
    source_repo_name VARCHAR(255),
    last_modified_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_repo_workflow_override UNIQUE (project_id, repo_id, workflow_id)
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
            "SELECT name FROM sqlite_master WHERE type='table' AND name='repo_workflow_overrides'"
        )
        if cursor.fetchone():
            print("✅ repo_workflow_overrides table already exists")
            return

        print("✅ Creating repo_workflow_overrides table (SQLite)...")
        cursor.execute(SQLITE_CREATE)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_repo_workflow_overrides_project_id ON repo_workflow_overrides(project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_repo_workflow_overrides_repo_id ON repo_workflow_overrides(repo_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_repo_workflow_overrides_workflow_id ON repo_workflow_overrides(workflow_id)")
        conn.commit()
        print("   repo_workflow_overrides table created successfully")
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
                WHERE table_name='repo_workflow_overrides'
            """)
            if cursor.fetchone():
                print("✅ repo_workflow_overrides table already exists")
                return

            print("✅ Creating repo_workflow_overrides table (PostgreSQL)...")
            cursor.execute(POSTGRES_CREATE)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_repo_workflow_overrides_project_id ON repo_workflow_overrides(project_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_repo_workflow_overrides_repo_id ON repo_workflow_overrides(repo_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_repo_workflow_overrides_workflow_id ON repo_workflow_overrides(workflow_id)")
            conn.commit()
            print("   repo_workflow_overrides table created successfully")
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
    print(f"🔄 Running repo_workflow_overrides migration for {db_type.upper()}...")
    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()


if __name__ == "__main__":
    run_migration()
