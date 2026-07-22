"""
Migration script to add optional validation repository preflight fields.
"""

from sqlalchemy import create_engine, inspect, text

from migration_utils import get_migration_database_url
# DATABASE_URL from database.py resolves the self-hosted SQLite path
# (/app/data/actions_manager.db) via INSTALLATION_MODE, falling back to the
# development ./test.db only when explicitly running outside self-hosted/prod.
from database import DATABASE_URL as APP_DATABASE_URL


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _column_definitions(is_postgres: bool) -> dict[str, str]:
    timestamp_type = "TIMESTAMP WITH TIME ZONE" if is_postgres else "DATETIME"
    boolean_default = "FALSE" if is_postgres else "0"

    return {
        "validation_repo_id": "INTEGER NULL",
        "preflight_required": f"BOOLEAN NOT NULL DEFAULT {boolean_default}",
        "last_preflight_status": "VARCHAR(40) NULL",
        "last_preflight_run_at": f"{timestamp_type} NULL",
        "last_preflight_error": "VARCHAR(500) NULL",
        "last_preflight_pr_url": "VARCHAR(500) NULL",
        "last_preflight_content_hash": "VARCHAR(64) NULL",
    }


def run_migration(database_url: str | None = None):
    """Run the migration to add validation/preflight columns to projects."""
    print("🔄 Starting migration: add validation preflight columns")

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

            for column_name, column_type in _column_definitions(is_postgres).items():
                if is_postgres:
                    print(f"✅ Adding projects.{column_name} (if not exists)...")
                    conn.execute(
                        text(
                            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS "
                            f"{column_name} {column_type}"
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
