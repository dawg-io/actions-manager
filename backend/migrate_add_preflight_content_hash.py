"""
Migration script to add last_preflight_content_hash column to the projects table.

This column stores a SHA-256 fingerprint of the workflow content that was validated
in a preflight run.  When the fingerprint of the project's current workflows differs
from the stored hash, the preflight approval is automatically marked as stale so the
user must re-run preflight before creating a new campaign.
"""

from sqlalchemy import create_engine, inspect, text

from migration_utils import get_migration_database_url
# DATABASE_URL from database.py resolves the self-hosted SQLite path
# (/app/data/actions_manager.db) via INSTALLATION_MODE, falling back to the
# development ./test.db only when explicitly running outside self-hosted/prod.
from database import DATABASE_URL as APP_DATABASE_URL


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def run_migration(database_url: str | None = None):
    """Run the migration to add last_preflight_content_hash to projects."""
    print("🔄 Starting migration: add preflight content hash column")

    db_url = database_url or get_migration_database_url() or APP_DATABASE_URL
    engine = create_engine(db_url)
    is_postgres = engine.dialect.name == "postgresql"

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            inspector = inspect(conn)
            if "projects" not in inspector.get_table_names():
                print("⚠️ projects table does not exist yet.")
                trans.rollback()
                return

            column_name = "last_preflight_content_hash"
            column_type = "VARCHAR(64) NULL"

            if is_postgres:
                print(f"✅ Adding projects.{column_name} (if not exists)...")
                conn.execute(
                    text(
                        f"ALTER TABLE projects ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
                    )
                )
            elif not _column_exists(inspector, "projects", column_name):
                print(f"✅ Adding projects.{column_name}...")
                conn.execute(
                    text(f"ALTER TABLE projects ADD COLUMN {column_name} {column_type}")
                )
            else:
                print(f"⚠️ projects.{column_name} already exists, skipping")

            trans.commit()
            print("✅ Migration completed successfully!")
        except Exception as e:
            trans.rollback()
            print(f"❌ Migration failed: {e}")
            raise


if __name__ == "__main__":
    run_migration()
