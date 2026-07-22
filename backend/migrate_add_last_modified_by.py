"""
Migration script to add last_modified_by column to workflows and projects tables.

This migration adds audit tracking columns so the UI can display who last
saved/committed each workflow and project.

Supports both SQLite and PostgreSQL databases.
"""

from sqlalchemy import create_engine, text
from database import DATABASE_URL


def run_migration():
    """Run the migration to add last_modified_by columns."""
    print("🔄 Starting migration: add last_modified_by columns")

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
    """Add last_modified_by columns for SQLite databases."""
    with engine.connect() as conn:
        trans = conn.begin()

        try:
            # --- workflows table ---
            # Check table exists first
            table_check = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='workflows'"
            ))
            if table_check.fetchone():
                result = conn.execute(text("PRAGMA table_info(workflows)"))
                wf_columns = [row[1] for row in result.fetchall()]

                if "last_modified_by" not in wf_columns:
                    print("✅ Adding last_modified_by column to workflows (SQLite)...")
                    conn.execute(text(
                        "ALTER TABLE workflows ADD COLUMN last_modified_by VARCHAR(255) NULL"
                    ))
                    print("   last_modified_by column added to workflows")
                else:
                    print("⚠️ workflows.last_modified_by already exists, skipping")
            else:
                print("⚠️ workflows table does not exist, skipping")

            # --- projects table ---
            table_check = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
            ))
            if table_check.fetchone():
                result = conn.execute(text("PRAGMA table_info(projects)"))
                pj_columns = [row[1] for row in result.fetchall()]

                if "last_modified_by" not in pj_columns:
                    print("✅ Adding last_modified_by column to projects (SQLite)...")
                    conn.execute(text(
                        "ALTER TABLE projects ADD COLUMN last_modified_by VARCHAR(255) NULL"
                    ))
                    print("   last_modified_by column added to projects")
                else:
                    print("⚠️ projects.last_modified_by already exists, skipping")
            else:
                print("⚠️ projects table does not exist, skipping")

            trans.commit()
            print("✅ SQLite migration completed successfully!")

        except Exception as e:
            trans.rollback()
            print(f"❌ SQLite migration failed: {e}")
            raise


def _migrate_postgresql(engine):
    """Add last_modified_by columns for PostgreSQL databases."""
    with engine.connect() as conn:
        trans = conn.begin()

        try:
            # --- workflows table ---
            table_check = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'workflows'
            """))
            if table_check.fetchone():
                result = conn.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'workflows' AND column_name = 'last_modified_by'
                """))

                if not result.fetchone():
                    print("✅ Adding last_modified_by column to workflows (PostgreSQL)...")
                    conn.execute(text(
                        "ALTER TABLE workflows ADD COLUMN last_modified_by VARCHAR(255) NULL"
                    ))
                    print("   last_modified_by column added to workflows")
                else:
                    print("⚠️ workflows.last_modified_by already exists, skipping")
            else:
                print("⚠️ workflows table does not exist, skipping")

            # --- projects table ---
            table_check = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'projects'
            """))
            if table_check.fetchone():
                result = conn.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'projects' AND column_name = 'last_modified_by'
                """))

                if not result.fetchone():
                    print("✅ Adding last_modified_by column to projects (PostgreSQL)...")
                    conn.execute(text(
                        "ALTER TABLE projects ADD COLUMN last_modified_by VARCHAR(255) NULL"
                    ))
                    print("   last_modified_by column added to projects")
                else:
                    print("⚠️ projects.last_modified_by already exists, skipping")
            else:
                print("⚠️ projects table does not exist, skipping")

            trans.commit()
            print("✅ PostgreSQL migration completed successfully!")

        except Exception as e:
            trans.rollback()
            print(f"❌ PostgreSQL migration failed: {e}")
            raise


if __name__ == "__main__":
    run_migration()
