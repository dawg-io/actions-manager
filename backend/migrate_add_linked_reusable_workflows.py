"""
Migration script to create the linked_reusable_workflows table.

This table allows users to link specific reusable workflows from RWX projects
into standard projects, replacing the old global enable/disable toggle.

Supports both SQLite and PostgreSQL databases.
"""

from sqlalchemy import create_engine, text
from database import DATABASE_URL


def run_migration():
    """Create the linked_reusable_workflows table if it does not exist."""
    print("🔄 Starting migration: create linked_reusable_workflows table")

    try:
        engine = create_engine(DATABASE_URL)

        if "sqlite" in DATABASE_URL:
            _migrate_sqlite(engine)
        else:
            _migrate_postgresql(engine)

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise


def _migrate_sqlite(engine):
    """Create the table for SQLite databases."""
    with engine.begin() as conn:
        result = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='linked_reusable_workflows'"
        ))

        if result.fetchone():
            print("⚠️ Table linked_reusable_workflows already exists, skipping creation")
        else:
            print("✅ Creating linked_reusable_workflows table (SQLite)...")
            conn.execute(text("""
                CREATE TABLE linked_reusable_workflows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    standard_project_id INTEGER NOT NULL
                        REFERENCES projects(project_id) ON DELETE CASCADE,
                    rwx_project_id INTEGER NOT NULL
                        REFERENCES projects(project_id) ON DELETE CASCADE,
                    workflow_id INTEGER NOT NULL
                        REFERENCES workflows(workflow_id) ON DELETE CASCADE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT unique_standard_workflow
                        UNIQUE (standard_project_id, workflow_id)
                )
            """))
            conn.execute(text("""
                CREATE INDEX ix_linked_reusable_workflows_standard_project_id
                    ON linked_reusable_workflows (standard_project_id)
            """))
            print("✅ Table and index created successfully")

    print("✅ SQLite migration completed successfully!")


def _migrate_postgresql(engine):
    """Create the table for PostgreSQL databases."""
    with engine.begin() as conn:
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'linked_reusable_workflows'
        """))

        if result.fetchone():
            print("⚠️ Table linked_reusable_workflows already exists, skipping creation")
        else:
            print("✅ Creating linked_reusable_workflows table (PostgreSQL)...")
            conn.execute(text("""
                CREATE TABLE linked_reusable_workflows (
                    id SERIAL PRIMARY KEY,
                    standard_project_id INTEGER NOT NULL
                        REFERENCES projects(project_id) ON DELETE CASCADE,
                    rwx_project_id INTEGER NOT NULL
                        REFERENCES projects(project_id) ON DELETE CASCADE,
                    workflow_id INTEGER NOT NULL
                        REFERENCES workflows(workflow_id) ON DELETE CASCADE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT unique_standard_workflow
                        UNIQUE (standard_project_id, workflow_id)
                )
            """))
            conn.execute(text("""
                CREATE INDEX ix_linked_reusable_workflows_standard_project_id
                    ON linked_reusable_workflows (standard_project_id)
            """))
            print("✅ Table and index created successfully")

    print("✅ PostgreSQL migration completed successfully!")


if __name__ == "__main__":
    run_migration()
