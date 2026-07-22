"""
Migration: Add file_names column to project_pull_requests.

Stores the comma-separated list of custom file paths and CODEOWNERS path
committed as part of the PR. Nullable so existing rows are unaffected.
Supports both SQLite and PostgreSQL.
"""

import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, str(Path(__file__).parent))
from migration_utils import get_migration_database_url, get_database_type
from database import DATABASE_URL as APP_DATABASE_URL


def run_migration():
    db_type = get_database_type()
    db_url = get_migration_database_url() if db_type == "postgresql" else APP_DATABASE_URL

    engine = create_engine(db_url, connect_args={"check_same_thread": False} if db_type == "sqlite" else {})
    inspector = inspect(engine)

    if "project_pull_requests" not in inspector.get_table_names():
        print("⚠️  project_pull_requests table not found — skipping migration.")
        return

    existing_columns = [col["name"] for col in inspector.get_columns("project_pull_requests")]
    if "file_names" in existing_columns:
        print("✅ file_names column already exists — skipping.")
        return

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE project_pull_requests ADD COLUMN file_names TEXT"))
    print("✅ Added file_names column to project_pull_requests.")


if __name__ == "__main__":
    run_migration()
