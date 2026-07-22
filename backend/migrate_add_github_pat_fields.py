#!/usr/bin/env python3
"""
Add encrypted GitHub personal access token fields to the accounts table.

This migration is idempotent for both SQLite and PostgreSQL.
"""

import sys

from sqlalchemy import inspect, text

from database import DATABASE_URL, engine


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def main() -> int:
    """
    Add GitHub PAT fields to the accounts table.
    Returns 0 on success, 1 on failure.
    """
    try:
        inspector = inspect(engine)
        is_postgres = DATABASE_URL.startswith("postgresql")

        if "accounts" not in inspector.get_table_names():
            print("⚠️ accounts table does not exist yet, skipping PAT migration")
            return 0

        # Use TIMESTAMP WITH TIME ZONE for PostgreSQL; DATETIME for SQLite
        timestamp_type = "TIMESTAMP WITH TIME ZONE" if is_postgres else "DATETIME"

        column_definitions = {
            "github_pat_token_encrypted": "TEXT NULL",
            "github_pat_token_type": "VARCHAR(50) NULL",
            "github_pat_status": "VARCHAR(50) NULL",
            "github_pat_last_error": "TEXT NULL",
            "github_pat_checked_at": f"{timestamp_type} NULL",
            "github_pat_updated_at": f"{timestamp_type} NULL",
        }

        if is_postgres:
            # PostgreSQL supports ADD COLUMN IF NOT EXISTS
            with engine.begin() as connection:
                for column_name, column_type in column_definitions.items():
                    print(f"✅ Adding {column_name} to accounts (if not exists)...")
                    connection.execute(
                        text(
                            f"ALTER TABLE accounts ADD COLUMN IF NOT EXISTS"
                            f" {column_name} {column_type}"
                        )
                    )
        else:
            # SQLite does not support IF NOT EXISTS in ALTER TABLE; check manually
            with engine.begin() as connection:
                for column_name, column_type in column_definitions.items():
                    if _column_exists(inspector, "accounts", column_name):
                        print(f"⚠️ accounts.{column_name} already exists, skipping")
                        continue
                    print(f"✅ Adding {column_name} to accounts...")
                    connection.execute(
                        text(f"ALTER TABLE accounts ADD COLUMN {column_name} {column_type}")
                    )

        print("🎉 GitHub PAT fields migration completed")
        return 0
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
