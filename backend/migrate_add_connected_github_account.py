"""
Database Migration: Add connected GitHub account fields

Adds nullable columns that track the GitHub App installation account separately
from the signed-in OAuth user.

Run this script to update an existing database:
    python migrate_add_connected_github_account.py
"""

import os
from urllib.parse import quote_plus

from sqlalchemy import create_engine, inspect, text


POSTGRES_USER = os.getenv("POSTGRES_USER", "").strip()
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "").strip()
POSTGRES_DB = os.getenv("POSTGRES_DB", "").strip()
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "").strip()
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "").strip()

if not (POSTGRES_USER and POSTGRES_PASSWORD and POSTGRES_DB and POSTGRES_HOST and POSTGRES_PORT):
    DATABASE_URL = "sqlite:///./test.db"
    print("⚠️ Using SQLite for testing - PostgreSQL not configured")
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False
    )
else:
    safe_password = quote_plus(POSTGRES_PASSWORD)
    DATABASE_URL = f"postgresql://{POSTGRES_USER}:{safe_password}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_recycle=1800,
        pool_pre_ping=True,
        echo=False
    )


def add_connected_github_account_columns() -> None:
    """Add connected GitHub account columns to accounts table."""
    columns_to_add = [
        ("connected_github_account", "ALTER TABLE accounts ADD COLUMN connected_github_account VARCHAR(255)"),
        ("connected_github_account_type", "ALTER TABLE accounts ADD COLUMN connected_github_account_type VARCHAR(20)"),
    ]

    with engine.connect() as conn:
        if not inspect(engine).has_table("accounts"):
            print("ℹ️ accounts table does not exist yet; fresh databases will include these columns automatically")
            return

        for column_name, sql in columns_to_add:
            try:
                conn.execute(text(sql))
                print(f"✅ Added column: {column_name}")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    print(f"ℹ️ Column {column_name} already exists, skipping")
                else:
                    raise
        conn.commit()


if __name__ == "__main__":
    add_connected_github_account_columns()
    print("✅ Connected GitHub account migration completed")
