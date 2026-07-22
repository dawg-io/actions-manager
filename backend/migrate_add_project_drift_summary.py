"""
Migration script to add cached project-level drift summary columns.
"""

from sqlalchemy import create_engine, inspect, text

from database import DATABASE_URL


def run_migration():
    """Run the migration to add project drift summary columns."""
    print("🔄 Starting migration: add project drift summary columns to projects table")

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

            if "drift_status" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE projects ADD COLUMN drift_status VARCHAR(20) NOT NULL DEFAULT 'unknown'"
                    )
                )
                print("✅ Added projects.drift_status")
            else:
                print("⚠️ projects.drift_status already exists, skipping")

            if "drift_count" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE projects ADD COLUMN drift_count INTEGER NOT NULL DEFAULT 0"
                    )
                )
                print("✅ Added projects.drift_count")
            else:
                print("⚠️ projects.drift_count already exists, skipping")

            if "last_drift_check_at" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE projects ADD COLUMN last_drift_check_at TIMESTAMP NULL"
                    )
                )
                print("✅ Added projects.last_drift_check_at")
            else:
                print("⚠️ projects.last_drift_check_at already exists, skipping")

            if "drift_error_summary" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE projects ADD COLUMN drift_error_summary VARCHAR(500) NULL"
                    )
                )
                print("✅ Added projects.drift_error_summary")
            else:
                print("⚠️ projects.drift_error_summary already exists, skipping")

            trans.commit()
            print("✅ Migration completed successfully!")
        except Exception as e:
            trans.rollback()
            print(f"❌ Migration failed: {e}")
            raise


if __name__ == "__main__":
    run_migration()
