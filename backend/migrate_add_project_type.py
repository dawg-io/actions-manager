"""
Migration script to add project_type column to projects table.

This migration adds the project_type column with default value 'standard'.
Possible values: 'standard', 'rwx' (Reusable Workflow eXchange).
"""

from sqlalchemy import create_engine, text, inspect
from database import DATABASE_URL


def run_migration():
    """Run the migration to add project_type column."""
    print("🔄 Starting migration: add project_type column to projects table")

    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        trans = conn.begin()

        try:
            inspector = inspect(engine)
            columns = [col['name'] for col in inspector.get_columns('projects')]

            if 'project_type' not in columns:
                print("✅ Adding project_type column...")
                conn.execute(text("""
                    ALTER TABLE projects
                    ADD COLUMN project_type VARCHAR(20)
                """))
                conn.execute(text("""
                    UPDATE projects
                    SET project_type = 'standard'
                    WHERE project_type IS NULL
                """))
                print("✅ Column added and existing rows set to 'standard'")
            else:
                print("⚠️ Column project_type already exists, skipping creation")

            trans.commit()
            print("✅ Migration completed successfully!")

        except Exception as e:
            trans.rollback()
            print(f"❌ Migration failed: {e}")
            raise


if __name__ == "__main__":
    run_migration()
