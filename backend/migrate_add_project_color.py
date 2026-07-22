"""
Migration script to add project_color column to projects table.

`project_color` stores a safe, fixed key chosen by the user (e.g. "blue",
"purple"). It is an identity accent for project cards and is NOT used to
communicate project status.

The column is nullable for backward compatibility. UI falls back to "blue"
when the DB value is NULL or missing.
"""

from sqlalchemy import create_engine, inspect, text

from database import DATABASE_URL


def run_migration():
    """Run the migration to add project_color column."""
    print("🔄 Starting migration: add project_color column to projects table")

    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            inspector = inspect(engine)

            if "projects" not in inspector.get_table_names():
                print("⚠️ projects table does not exist yet.")
                print("   Migration will be applied when database is created.")
                trans.rollback()
                return

            columns = [col["name"] for col in inspector.get_columns("projects")]

            if "project_color" not in columns:
                print("✅ Adding project_color column...")
                conn.execute(
                    text(
                        """
                        ALTER TABLE projects
                        ADD COLUMN project_color VARCHAR(20)
                        """
                    )
                )
                print("✅ Column project_color added (nullable)")
            else:
                print("⚠️ Column project_color already exists, skipping creation")

            trans.commit()
            print("✅ Migration completed successfully!")
        except Exception as e:
            trans.rollback()
            print(f"❌ Migration failed: {e}")
            raise


if __name__ == "__main__":
    run_migration()

