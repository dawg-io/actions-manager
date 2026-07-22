"""
Migration script to normalize legacy workspace role values.

Converts deprecated `co_admin` workspace roles to `admin`.
Also ensures at least one admin exists when workspace members are present.

The migration is idempotent and safe to re-run.
"""

from sqlalchemy import create_engine, text

from migration_utils import get_migration_database_url


def run_migration():
    """Normalize legacy workspace role values."""
    database_url = get_migration_database_url()
    if not database_url:
        print("⚠️ No database URL configured, skipping migration")
        return

    engine = create_engine(database_url)
    print("🔄 Starting migration: co_admin -> admin")

    with engine.begin() as conn:
        table_exists = False
        if "sqlite" in database_url:
            row = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='workspace_members'")
            ).fetchone()
            table_exists = bool(row)
        else:
            row = conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'workspace_members'
                    """
                )
            ).fetchone()
            table_exists = bool(row)

        if not table_exists:
            print("⏭️ workspace_members table does not exist yet, skipping migration")
            return

        updated = conn.execute(
            text(
                """
                UPDATE workspace_members
                SET workspace_role = 'admin'
                WHERE workspace_role = 'co_admin'
                """
            )
        ).rowcount
        print(f"✅ Converted {updated or 0} legacy co_admin row(s) to admin")

        total_members = conn.execute(text("SELECT COUNT(*) FROM workspace_members")).scalar() or 0
        if total_members > 0:
            admin_count = conn.execute(
                text("SELECT COUNT(*) FROM workspace_members WHERE workspace_role = 'admin'")
            ).scalar() or 0

            if admin_count == 0:
                promoted = conn.execute(
                    text(
                        """
                        UPDATE workspace_members
                        SET workspace_role = 'admin'
                        WHERE id = (
                            SELECT id FROM workspace_members
                            ORDER BY id ASC
                            LIMIT 1
                        )
                        """
                    )
                ).rowcount
                if promoted:
                    print("⚠️ No admin found — promoted the earliest workspace member row to admin")

    print("✅ co_admin normalization migration completed successfully")


if __name__ == "__main__":
    run_migration()
