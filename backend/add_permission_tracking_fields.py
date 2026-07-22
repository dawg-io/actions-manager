"""
Database migration script to add GitHub permission tracking fields to Account table.

Adds:
- github_permission_status: Stores the current permission validation status
- github_permission_checked_at: Timestamp of the last permission check

Supports both SQLite and PostgreSQL databases.

Run this script to update existing database schemas:
    python add_permission_tracking_fields.py
"""

from sqlalchemy import create_engine, text
from database import DATABASE_URL
import sys


def run_migration():
    """Run the migration to add permission tracking fields."""
    print("=" * 70)
    print("GitHub Permission Tracking Migration")
    print("=" * 70)

    try:
        engine = create_engine(DATABASE_URL)

        if "sqlite" in DATABASE_URL:
            _migrate_sqlite(engine)
        else:
            _migrate_postgresql(engine)

        print("\n✅ Migration completed successfully")
        return 0

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


def _migrate_sqlite(engine):
    """Add permission tracking columns for SQLite databases."""
    print("🔧 Starting migration for SQLite database...")

    with engine.connect() as conn:
        trans = conn.begin()

        try:
            # Check if accounts table exists
            table_check = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'"
            ))
            if not table_check.fetchone():
                print("⚠️ accounts table does not exist, skipping")
                trans.commit()
                return

            # Get existing columns
            result = conn.execute(text("PRAGMA table_info(accounts)"))
            columns = [row[1] for row in result.fetchall()]

            # Add github_permission_status if it doesn't exist
            if "github_permission_status" not in columns:
                print("✅ Adding github_permission_status column to accounts (SQLite)...")
                conn.execute(text(
                    "ALTER TABLE accounts ADD COLUMN github_permission_status VARCHAR(50) NULL"
                ))
                print("   github_permission_status column added")
            else:
                print("⚠️ accounts.github_permission_status already exists, skipping")

            # Add github_permission_checked_at if it doesn't exist
            if "github_permission_checked_at" not in columns:
                print("✅ Adding github_permission_checked_at column to accounts (SQLite)...")
                conn.execute(text(
                    "ALTER TABLE accounts ADD COLUMN github_permission_checked_at DATETIME NULL"
                ))
                print("   github_permission_checked_at column added")
            else:
                print("⚠️ accounts.github_permission_checked_at already exists, skipping")

            trans.commit()
            print("✅ SQLite migration completed successfully!")

        except Exception as e:
            trans.rollback()
            print(f"❌ SQLite migration failed: {e}")
            raise


def _migrate_postgresql(engine):
    """Add permission tracking columns for PostgreSQL databases."""
    print("🔧 Starting migration for PostgreSQL database...")

    with engine.connect() as conn:
        trans = conn.begin()

        try:
            # Check if accounts table exists
            table_check = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'accounts'
            """))
            if not table_check.fetchone():
                print("⚠️ accounts table does not exist, skipping")
                trans.commit()
                return

            # Check if github_permission_status column exists
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'accounts' AND column_name = 'github_permission_status'
            """))

            if not result.fetchone():
                print("✅ Adding github_permission_status column to accounts (PostgreSQL)...")
                conn.execute(text(
                    "ALTER TABLE accounts ADD COLUMN github_permission_status VARCHAR(50) NULL"
                ))
                print("   github_permission_status column added")
            else:
                print("⚠️ accounts.github_permission_status already exists, skipping")

            # Check if github_permission_checked_at column exists
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'accounts' AND column_name = 'github_permission_checked_at'
            """))

            if not result.fetchone():
                print("✅ Adding github_permission_checked_at column to accounts (PostgreSQL)...")
                conn.execute(text(
                    "ALTER TABLE accounts ADD COLUMN github_permission_checked_at TIMESTAMP NULL"
                ))
                print("   github_permission_checked_at column added")
            else:
                print("⚠️ accounts.github_permission_checked_at already exists, skipping")

            trans.commit()
            print("✅ PostgreSQL migration completed successfully!")

        except Exception as e:
            trans.rollback()
            print(f"❌ PostgreSQL migration failed: {e}")
            raise


if __name__ == "__main__":
    sys.exit(run_migration())
